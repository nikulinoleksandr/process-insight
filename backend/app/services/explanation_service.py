"""Anwendungsfall: ein Insight von der KI erklären lassen.

Zwischengespeichert wird pro Insight, Prompt-Version und Modell. Ohne API-Schlüssel oder
wenn die KI nicht antwortet, gibt es die feste Zusammenfassung des Detektors zurück.
"""

import hashlib
import json
import threading
import time
from collections import deque

from app.core.insights.base import Insight
from app.llm.checks import unverified_numbers
from app.llm.explainer import Explainer, ExplainerError
from app.llm.payload import build_payload
from app.llm.prompts import PROMPT_VERSION
from app.llm.schemas import ExplanationOut
from app.services.analysis_service import AnalysisService
from app.services.errors import ConflictError, NotFoundError, RateLimitedError
from app.storage.files import FileStore


class RateLimiter:
    """Erlaubt höchstens `limit` Aufrufe pro `window` Sekunden (gleitendes Fenster)."""

    def __init__(self, limit: int, window: float = 3600):
        self.limit = limit
        self.window = window
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] > self.window:
                self._calls.popleft()
            if len(self._calls) >= self.limit:
                wait = int(self.window - (now - self._calls[0])) // 60 + 1
                raise RateLimitedError(
                    f"Zu viele KI-Anfragen. Bitte in etwa {wait} Minuten erneut versuchen."
                )
            self._calls.append(now)


class ExplanationService:
    def __init__(
        self,
        analyses: AnalysisService,
        files: FileStore,
        explainer: Explainer | None,
        requests_per_hour: int,
    ):
        self.analyses = analyses
        self.explainer = explainer
        self.limiter = RateLimiter(requests_per_hour)
        self.cache_dir = files.root / "explanations"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.explainer is not None

    def explain(self, analysis_id: str, insight_id: str, refresh: bool = False) -> ExplanationOut:
        result = self.analyses.result(analysis_id)
        if result is None:
            raise ConflictError("Analyse ist noch nicht fertig.")
        insight = next((i for i in result.insights if i.id == insight_id), None)
        if insight is None:
            raise NotFoundError(f"Insight {insight_id} nicht gefunden.")

        if self.explainer is None:
            return _fallback(
                insight,
                "KI-Erklärungen sind nicht eingerichtet: Es ist kein API-Schlüssel hinterlegt.",
            )

        cache = self.cache_dir / f"{self._cache_key(insight)}.json"
        if cache.exists() and not refresh:
            cached = ExplanationOut.model_validate_json(cache.read_text(encoding="utf-8"))
            return cached.model_copy(update={"cached": True})

        self.limiter.acquire()
        payload = build_payload(insight, result.log_summary)
        try:
            explanation = self.explainer.explain(payload)
        except ExplainerError as exc:
            return _fallback(insight, str(exc))

        out = ExplanationOut(
            source="ai",
            **explanation.model_dump(),
            model=self.explainer.model,
            unverified_numbers=unverified_numbers(explanation, payload),
        )
        cache.write_text(out.model_dump_json(), encoding="utf-8")
        return out

    def _cache_key(self, insight: Insight) -> str:
        # Fall-IDs ändern nichts an der Erklärung und bleiben deshalb außen vor.
        content = insight.model_dump(exclude={"affected_case_ids"})
        raw = json.dumps([content, PROMPT_VERSION, self.explainer.model], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _fallback(insight: Insight, note: str) -> ExplanationOut:
    return ExplanationOut(
        source="fallback",
        headline=insight.title,
        explanation=insight.summary,
        possible_causes=[],
        next_steps=[],
        note=note,
    )

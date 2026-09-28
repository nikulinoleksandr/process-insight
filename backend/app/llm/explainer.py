"""Die Verbindung zum Sprachmodell.

Explainer ist die Schnittstelle. ClaudeExplainer spricht mit der Claude API,
FakeExplainer liefert feste Texte für Tests und für die Entwicklung ohne API-Schlüssel.
"""

import logging
from typing import Any, Protocol

from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.schemas import Explanation

logger = logging.getLogger(__name__)


class ExplainerError(Exception):
    """Das Sprachmodell hat nicht oder nicht brauchbar geantwortet."""


class Explainer(Protocol):
    model: str

    def explain(self, payload: dict[str, Any]) -> Explanation: ...


class ClaudeExplainer:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 1200,
        timeout: float = 45,
        http_client=None,  # nur für Tests: simuliert die API ohne Netz
    ):
        import anthropic  # erst hier, damit das Tool auch ohne das Paket startet

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(
            api_key=api_key, max_retries=1, timeout=timeout, http_client=http_client
        )
        self.model = model
        self.max_tokens = max_tokens

    def explain(self, payload: dict[str, Any]) -> Explanation:
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(payload)}],
                output_format=Explanation,
            )
        except self._anthropic.APIError as exc:
            logger.warning("Claude API Fehler: %s", type(exc).__name__)
            reason = type(exc).__name__
            raise ExplainerError(f"Die KI ist gerade nicht erreichbar ({reason}).") from exc
        parsed = response.parsed_output
        if parsed is None:
            raise ExplainerError("Die KI hat keine gültige Antwort geliefert.")
        return clean(parsed)


def clean(explanation: Explanation) -> Explanation:
    """Leere Listeneinträge entfernen und »…« wieder als „…“ darstellen, wie in der Oberfläche."""

    def text(value: str) -> str:
        return value.strip().replace("»", "„").replace("«", "“")

    def items(values: list[str]) -> list[str]:
        return [text(v) for v in values if v.strip()]

    return Explanation(
        headline=text(explanation.headline),
        explanation=text(explanation.explanation),
        possible_causes=items(explanation.possible_causes),
        next_steps=items(explanation.next_steps),
    )


class FakeExplainer:
    """Antwortet ohne Netz. Zählt die Aufrufe, damit Tests den Cache prüfen können."""

    model = "fake"

    def __init__(self, answer: Explanation | None = None, fail: bool = False):
        self.calls = 0
        self.fail = fail
        self.answer = answer

    def explain(self, payload: dict[str, Any]) -> Explanation:
        self.calls += 1
        if self.fail:
            raise ExplainerError("Test: KI nicht erreichbar.")
        if self.answer:
            return self.answer
        befund = payload["befund"]
        return Explanation(
            headline=befund["titel"],
            explanation=befund["zusammenfassung"],
            possible_causes=["Möglicherweise fehlen klare Regeln für diesen Schritt."],
            next_steps=["Prüfen Sie die betroffenen Fälle stichprobenartig."],
        )

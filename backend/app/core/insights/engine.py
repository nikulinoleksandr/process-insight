"""Führt alle Detektoren auf einem Log aus und sammelt die Ergebnisse."""

import logging
import time
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.core.insights.base import SEVERITY_ORDER, Detector, Insight, NotApplicable
from app.core.insights.registry import DETECTORS
from app.core.process.stats import LogSummary, summarize

logger = logging.getLogger(__name__)


class DetectorRun(BaseModel):
    detector_id: str
    status: Literal["ok", "not_applicable", "failed"]
    duration_ms: float
    insight_count: int = 0
    message: str | None = None


class AnalysisResult(BaseModel):
    log_summary: LogSummary
    insights: list[Insight]
    detector_runs: list[DetectorRun]


class InvalidConfigError(ValueError):
    pass


def validate_config(
    config: dict[str, dict[str, Any]] | None, detectors: list[Detector] | None = None
) -> dict[str, BaseModel]:
    """Prüft die Konfiguration aller Detektoren vorab, damit Fehler sofort gemeldet werden."""
    config = config or {}
    detectors = detectors if detectors is not None else DETECTORS
    known = {d.id for d in detectors}
    unknown = set(config) - known
    if unknown:
        raise InvalidConfigError(f"Unbekannte Detektoren: {', '.join(sorted(unknown))}")
    validated = {}
    for detector in detectors:
        try:
            validated[detector.id] = detector.config_model.model_validate(
                config.get(detector.id, {})
            )
        except ValidationError as exc:
            raise InvalidConfigError(f"Konfiguration für '{detector.id}' ungültig: {exc}") from exc
    return validated


def run_analysis(
    log: pd.DataFrame,
    config: dict[str, dict[str, Any]] | None = None,
    detectors: list[Detector] | None = None,
) -> AnalysisResult:
    detectors = detectors if detectors is not None else DETECTORS
    configs = validate_config(config, detectors)
    insights: list[Insight] = []
    runs: list[DetectorRun] = []

    for detector in detectors:
        start = time.perf_counter()
        present = detector.required_columns & set(log.columns)
        missing = detector.required_columns - present
        if missing or any(log[c].isna().all() for c in present):
            runs.append(
                DetectorRun(
                    detector_id=detector.id,
                    status="not_applicable",
                    duration_ms=0.0,
                    message="Benötigte Spalten fehlen: " + ", ".join(sorted(missing))
                    if missing
                    else "Benötigte Spalten sind leer.",
                )
            )
            continue
        try:
            found = detector.detect(log, configs[detector.id])
            insights.extend(found)
            runs.append(
                DetectorRun(
                    detector_id=detector.id,
                    status="ok",
                    duration_ms=_ms(start),
                    insight_count=len(found),
                )
            )
        except NotApplicable as exc:
            runs.append(
                DetectorRun(
                    detector_id=detector.id,
                    status="not_applicable",
                    duration_ms=_ms(start),
                    message=str(exc),
                )
            )
        except Exception as exc:  # ein kaputter Detektor darf nicht die ganze Analyse stoppen
            logger.exception("Detektor %s fehlgeschlagen", detector.id)
            runs.append(
                DetectorRun(
                    detector_id=detector.id,
                    status="failed",
                    duration_ms=_ms(start),
                    message=f"{type(exc).__name__}: {exc}",
                )
            )

    insights.sort(key=lambda i: (SEVERITY_ORDER[i.severity], -i.affected_case_share))
    return AnalysisResult(log_summary=summarize(log), insights=insights, detector_runs=runs)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)

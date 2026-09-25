"""Gemeinsame Bausteine aller Detektoren: das Ergebnisformat (Insight) und die Schnittstelle."""

import hashlib
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

import pandas as pd
from pydantic import BaseModel

Category = Literal["efficiency", "quality", "compliance", "deviation"]
Severity = Literal["low", "medium", "high"]
SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class Insight(BaseModel):
    """Ein gefundenes Prozessproblem. Alle Detektoren liefern genau dieses Format."""

    id: str
    detector_id: str
    category: Category
    severity: Severity
    title: str
    summary: str
    severity_rule: str
    metrics: dict[str, float | int | str]
    evidence: dict[str, Any]
    affected_case_count: int
    affected_case_share: float
    affected_case_ids: list[str]


class NotApplicable(Exception):
    """Der Detektor kann auf diesem Log nicht sinnvoll laufen (z.B. fehlende Konfiguration)."""


class Detector(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[Category]
    required_columns: ClassVar[set[str]]
    config_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def detect(self, log: pd.DataFrame, config: BaseModel) -> list[Insight]:
        """Untersucht das Log und gibt gefundene Probleme zurück (auch eine leere Liste)."""

    def make_insight(
        self,
        *,
        key: str,
        severity: Severity,
        title: str,
        summary: str,
        severity_rule: str,
        metrics: dict[str, float | int | str],
        evidence: dict[str, Any],
        affected_cases: pd.Index | list[str],
        total_cases: int,
    ) -> Insight:
        """Hilfsfunktion, damit jeder Detektor Insights einheitlich aufbaut."""
        ids = sorted(str(c) for c in affected_cases)
        digest = hashlib.sha1(f"{self.id}:{key}".encode()).hexdigest()[:10]
        return Insight(
            id=f"{self.id}-{digest}",
            detector_id=self.id,
            category=self.category,
            severity=severity,
            title=title,
            summary=summary,
            severity_rule=severity_rule,
            metrics=metrics,
            evidence=evidence,
            affected_case_count=len(ids),
            affected_case_share=len(ids) / total_cases if total_cases else 0.0,
            affected_case_ids=ids,
        )


def severity_by_share(share: float, high: float, medium: float) -> Severity:
    if share >= high:
        return "high"
    if share >= medium:
        return "medium"
    return "low"


def pct(share: float) -> str:
    return f"{share * 100:.1f} %".replace(".", ",")


def days(seconds: float, dative: bool = False) -> str:
    """Formatiert Sekunden als Tage, z.B. '6,0 Tage' (dative=True: '6,0 Tagen')."""
    value = f"{seconds / 86400:.1f}".replace(".", ",")
    return f"{value} {'Tagen' if dative else 'Tage'}"

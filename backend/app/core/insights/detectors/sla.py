"""Lange Durchlaufzeiten: Fälle, die länger dauern als ein Schwellenwert."""

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.core.columns import CASE, TIMESTAMP
from app.core.insights.base import Detector, Insight, days, pct, severity_by_share
from app.core.process.stats import case_durations


class SlaConfig(BaseModel):
    max_days: float | None = Field(None, gt=0, description="Fester Schwellenwert in Tagen")
    percentile: float = Field(0.9, gt=0, lt=1, description="Wird genutzt, wenn max_days leer ist")
    high_share: float = Field(0.20, ge=0, le=1)
    medium_share: float = Field(0.05, ge=0, le=1)
    high_ratio: float = Field(3.0, gt=1, description="Perzentil-Modus: Verhältnis zum Median")
    medium_ratio: float = Field(1.5, gt=1)

    @model_validator(mode="after")
    def _check(self):
        if self.medium_ratio > self.high_ratio:
            raise ValueError("medium_ratio darf nicht größer als high_ratio sein")
        return self


class SlaDetector(Detector):
    id = "sla"
    name = "Lange Durchlaufzeiten"
    category = "efficiency"
    required_columns = {CASE, TIMESTAMP}
    config_model = SlaConfig

    def detect(self, log: pd.DataFrame, config: SlaConfig) -> list[Insight]:
        durations = case_durations(log).dt.total_seconds()
        total = len(durations)
        median = float(durations.median())

        if config.max_days is not None:
            threshold = config.max_days * 86400
            affected = durations[durations > threshold]
            share = len(affected) / total
            severity = severity_by_share(share, config.high_share, config.medium_share)
            rule = (
                f"hoch ab {pct(config.high_share)} der Fälle über der Frist, "
                f"mittel ab {pct(config.medium_share)}, sonst niedrig"
            )
            title = f"Fristüberschreitung: Fälle über {days(threshold, dative=True)}"
            summary = (
                f"{len(affected)} von {total} Fällen ({pct(share)}) dauern länger als "
                f"{days(threshold)}. Der Median liegt bei {days(median, dative=True)}."
            )
        else:
            threshold = float(durations.quantile(config.percentile))
            affected = durations[durations > threshold]
            # Wie viel langsamer sind die langsamen Fälle als ein typischer Fall?
            slow_median = float(affected.median()) if not affected.empty else 0.0
            ratio = slow_median / median if median > 0 else 0.0
            if ratio >= config.high_ratio:
                severity = "high"
            elif ratio >= config.medium_ratio:
                severity = "medium"
            else:
                severity = "low"
            rule = (
                f"hoch, wenn die langsamen Fälle im Median mindestens {config.high_ratio:g}-mal "
                f"so lange dauern wie ein typischer Fall, mittel ab {config.medium_ratio:g}-mal"
            )
            ratio_text = f"{ratio:.1f}".replace(".", ",")
            title = (
                "1 auffällig langsamer Fall"
                if len(affected) == 1
                else f"{len(affected)} auffällig langsame Fälle"
            )
            summary = (
                f"{len(affected)} von {total} Fällen dauern länger als {days(threshold)} "
                f"(langsamer als {pct(config.percentile)} aller Fälle). Im Median brauchen sie "
                f"{days(slow_median)}, das {ratio_text}-Fache eines typischen Falls "
                f"({days(median)})."
            )

        if affected.empty:
            return []
        return [
            self.make_insight(
                key="threshold",
                severity=severity,
                title=title,
                summary=summary,
                severity_rule=rule,
                metrics={
                    "threshold_seconds": float(threshold),
                    "median_seconds": median,
                    "max_seconds": float(durations.max()),
                },
                evidence={"mode": "fixed" if config.max_days else "percentile"},
                affected_cases=affected.index,
                total_cases=total,
            )
        ]

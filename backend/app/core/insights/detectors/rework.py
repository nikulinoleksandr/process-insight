"""Nacharbeit: Dieselbe Aktivität kommt innerhalb eines Falls mehrmals vor."""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE
from app.core.insights.base import Detector, Insight, pct, severity_by_share


class ReworkConfig(BaseModel):
    min_case_share: float = Field(0.02, ge=0, le=1, description="Mindestanteil betroffener Fälle")
    high_share: float = Field(0.20, ge=0, le=1)
    medium_share: float = Field(0.05, ge=0, le=1)


class ReworkDetector(Detector):
    id = "rework"
    name = "Nacharbeit"
    category = "quality"
    required_columns = {CASE, ACTIVITY}
    config_model = ReworkConfig

    def detect(self, log: pd.DataFrame, config: ReworkConfig) -> list[Insight]:
        total = log[CASE].nunique()
        counts = log.groupby([CASE, ACTIVITY], sort=False).size()
        repeated = counts[counts > 1]
        rule = (
            f"hoch ab {pct(config.high_share)} betroffener Fälle, "
            f"mittel ab {pct(config.medium_share)}, sonst niedrig"
        )

        insights = []
        for activity, group in repeated.groupby(level=ACTIVITY, sort=False):
            cases = group.index.get_level_values(CASE)
            share = len(cases) / total
            if share < config.min_case_share:
                continue
            extra = int((group - 1).sum())
            insights.append(
                self.make_insight(
                    key=str(activity),
                    severity=severity_by_share(share, config.high_share, config.medium_share),
                    title=f"Nacharbeit bei „{activity}“",
                    summary=(
                        f"In {len(cases)} von {total} Fällen ({pct(share)}) wird „{activity}“ "
                        f"mehrfach ausgeführt, insgesamt {extra} zusätzliche "
                        f"{'Ausführung' if extra == 1 else 'Ausführungen'}."
                    ),
                    severity_rule=rule,
                    metrics={
                        "affected_cases": len(cases),
                        "extra_executions": extra,
                        "max_executions_per_case": int(group.max()),
                    },
                    evidence={"activity": str(activity)},
                    affected_cases=cases,
                    total_cases=total,
                )
            )
        return insights

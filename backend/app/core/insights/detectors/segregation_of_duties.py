"""Vier-Augen-Prinzip: Dieselbe Person führt zwei Aktivitäten aus, die getrennt sein müssen."""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE, RESOURCE
from app.core.insights.base import Detector, Insight, NotApplicable, pct


class ActivityPair(BaseModel):
    first: str
    second: str


class SegregationConfig(BaseModel):
    pairs: list[ActivityPair] = Field(
        default_factory=list,
        description="Aktivitätspaare, die nicht dieselbe Ressource ausführen darf",
    )
    high_share: float = Field(0.05, ge=0, le=1)


class SegregationOfDutiesDetector(Detector):
    id = "segregation_of_duties"
    name = "Vier-Augen-Prinzip"
    category = "compliance"
    required_columns = {CASE, ACTIVITY, RESOURCE}
    config_model = SegregationConfig

    def detect(self, log: pd.DataFrame, config: SegregationConfig) -> list[Insight]:
        if not config.pairs:
            raise NotApplicable("Keine Aktivitätspaare konfiguriert.")

        total = log[CASE].nunique()
        events = log[[CASE, ACTIVITY, RESOURCE]].dropna()
        rule = f"hoch ab {pct(config.high_share)} betroffener Fälle, sonst mittel (Compliance)"

        insights = []
        for pair in config.pairs:
            first = events[events[ACTIVITY] == pair.first][[CASE, RESOURCE]].drop_duplicates()
            second = events[events[ACTIVITY] == pair.second][[CASE, RESOURCE]].drop_duplicates()
            both = first.merge(second, on=[CASE, RESOURCE])
            if both.empty:
                continue
            cases = both[CASE].unique()
            share = len(cases) / total
            insights.append(
                self.make_insight(
                    key=f"{pair.first}|{pair.second}",
                    severity="high" if share >= config.high_share else "medium",
                    title=f"Vier-Augen-Prinzip verletzt: „{pair.first}“ und „{pair.second}“",
                    summary=(
                        f"In {len(cases)} von {total} Fällen ({pct(share)}) hat dieselbe Person "
                        f"sowohl „{pair.first}“ als auch „{pair.second}“ ausgeführt."
                    ),
                    severity_rule=rule,
                    metrics={
                        "affected_cases": len(cases),
                        "involved_resources": int(both[RESOURCE].nunique()),
                    },
                    evidence={"first": pair.first, "second": pair.second},
                    affected_cases=cases,
                    total_cases=total,
                )
            )
        return insights

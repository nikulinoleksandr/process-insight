"""Engpässe: Übergänge A -> B, bei denen viel Wartezeit entsteht."""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE, TIMESTAMP
from app.core.insights.base import Detector, Insight, days, pct, severity_by_share
from app.core.process.transitions import transitions


class BottleneckConfig(BaseModel):
    min_case_share: float = Field(
        0.05, ge=0, le=1, description="Übergang muss mindestens so viele Fälle betreffen"
    )
    top_n: int = Field(3, ge=1, le=20, description="Wie viele Engpässe gemeldet werden")
    high_share: float = Field(0.25, ge=0, le=1, description="Anteil an der gesamten Wartezeit")
    medium_share: float = Field(0.10, ge=0, le=1)


class BottleneckDetector(Detector):
    id = "bottleneck"
    name = "Engpässe"
    category = "efficiency"
    required_columns = {CASE, ACTIVITY, TIMESTAMP}
    config_model = BottleneckConfig

    def detect(self, log: pd.DataFrame, config: BottleneckConfig) -> list[Insight]:
        total = log[CASE].nunique()
        tr = transitions(log)
        tr = tr.assign(wait_s=tr["wait"].dt.total_seconds())
        total_wait = tr["wait_s"].sum()
        if tr.empty or total_wait <= 0:
            return []

        stats = (
            tr.groupby(["source", "target"], sort=False)
            .agg(
                count=("case", "size"),
                cases=("case", "nunique"),
                median_wait=("wait_s", "median"),
                sum_wait=("wait_s", "sum"),
            )
            .reset_index()
        )
        stats = stats[stats["cases"] / total >= config.min_case_share]
        stats = stats.sort_values("sum_wait", ascending=False).head(config.top_n)

        rule = (
            f"hoch ab {pct(config.high_share)} Anteil an der gesamten Wartezeit, "
            f"mittel ab {pct(config.medium_share)}, sonst niedrig"
        )
        insights = []
        for row in stats.itertuples(index=False):
            share = row.sum_wait / total_wait
            cases = tr.loc[(tr["source"] == row.source) & (tr["target"] == row.target), "case"]
            insights.append(
                self.make_insight(
                    key=f"{row.source}->{row.target}",
                    severity=severity_by_share(share, config.high_share, config.medium_share),
                    title=f"Wartezeit zwischen „{row.source}“ und „{row.target}“",
                    summary=(
                        f"Zwischen „{row.source}“ und „{row.target}“ vergehen im Median "
                        f"{days(row.median_wait)}. Dieser Übergang verursacht {pct(share)} "
                        f"der gesamten Wartezeit im Prozess."
                    ),
                    severity_rule=rule,
                    metrics={
                        "median_wait_seconds": float(row.median_wait),
                        "total_wait_share": float(share),
                        "transition_count": int(row.count),
                    },
                    evidence={"source": str(row.source), "target": str(row.target)},
                    affected_cases=cases.unique(),
                    total_cases=total,
                )
            )
        return insights

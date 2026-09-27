"""Engpässe: Übergänge A -> B, bei denen viel Wartezeit entsteht.

Nicht gemeldet werden:
- Wiederholungen desselben Schritts (A -> A): das ist keine Wartezeit zwischen zwei
  Schritten, sondern der Abstand zwischen Wiederholungen (siehe Nacharbeit).
- Übergänge, bei denen fast nie gewartet wird (90 % der Fälle unter der Mindestwartezeit).
- Übergänge mit nur einem kleinen Anteil an der gesamten Wartezeit.
"""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE, TIMESTAMP
from app.core.insights.base import Detector, Insight, duration, pct, severity_by_share
from app.core.process.transitions import transitions


class BottleneckConfig(BaseModel):
    min_case_share: float = Field(
        0.05, ge=0, le=1, description="Übergang muss mindestens so viele Fälle betreffen"
    )
    top_n: int = Field(3, ge=1, le=20, description="Wie viele Engpässe gemeldet werden")
    min_wait_share: float = Field(
        0.05, ge=0, le=1, description="Mindestanteil an der gesamten Wartezeit"
    )
    min_wait_seconds: float = Field(
        3600, ge=0, description="Wartet höchstens jeder zehnte Fall länger, ist es kein Engpass"
    )
    high_share: float = Field(0.25, ge=0, le=1, description="Anteil an der gesamten Wartezeit")
    medium_share: float = Field(0.10, ge=0, le=1)
    ignore_transitions: list[list[str]] = Field(
        default_factory=list,
        description="Übergänge [von, nach], deren Wartezeit gewollt ist (z.B. gesetzliche Frist)",
    )


class BottleneckDetector(Detector):
    id = "bottleneck"
    name = "Engpässe"
    category = "efficiency"
    required_columns = {CASE, ACTIVITY, TIMESTAMP}
    config_model = BottleneckConfig

    def detect(self, log: pd.DataFrame, config: BottleneckConfig) -> list[Insight]:
        total = log[CASE].nunique()
        tr = transitions(log)
        tr = tr[tr["source"] != tr["target"]]
        if config.ignore_transitions:
            # Gewollte Wartezeiten zählen auch nicht zur Gesamtwartezeit, sonst würden sie
            # die Anteile aller anderen Übergänge künstlich klein machen.
            ignored = pd.MultiIndex.from_tuples([tuple(p) for p in config.ignore_transitions])
            pairs = pd.MultiIndex.from_arrays([tr["source"], tr["target"]])
            tr = tr[~pairs.isin(ignored)]
        tr = tr.assign(wait_s=tr["wait"].dt.total_seconds())
        total_wait = tr["wait_s"].sum()
        if tr.empty or total_wait <= 0:
            return []

        grouped = tr.groupby(["source", "target"], sort=False)["wait_s"]
        stats = pd.DataFrame(
            {
                "count": grouped.size(),
                "cases": tr.groupby(["source", "target"], sort=False)["case"].nunique(),
                "median_wait": grouped.median(),
                "p90_wait": grouped.quantile(0.9),
                "sum_wait": grouped.sum(),
            }
        ).reset_index()
        stats["share"] = stats["sum_wait"] / total_wait
        keep = (
            (stats["cases"] / total >= config.min_case_share)
            & (stats["share"] >= config.min_wait_share)
            & (stats["p90_wait"] >= config.min_wait_seconds)
        )
        stats = stats[keep].sort_values("sum_wait", ascending=False).head(config.top_n)

        rule = (
            f"hoch ab {pct(config.high_share)} Anteil an der gesamten Wartezeit, "
            f"mittel ab {pct(config.medium_share)}, sonst niedrig"
        )
        insights = []
        for row in stats.itertuples(index=False):
            cases = tr.loc[(tr["source"] == row.source) & (tr["target"] == row.target), "case"]
            insights.append(
                self.make_insight(
                    key=f"{row.source}->{row.target}",
                    severity=severity_by_share(row.share, config.high_share, config.medium_share),
                    title=f"Wartezeit zwischen „{row.source}“ und „{row.target}“",
                    summary=_summary(row),
                    severity_rule=rule,
                    metrics={
                        "median_wait_seconds": float(row.median_wait),
                        "p90_wait_seconds": float(row.p90_wait),
                        "total_wait_share": float(row.share),
                        "transition_count": int(row.count),
                    },
                    evidence={"source": str(row.source), "target": str(row.target)},
                    affected_cases=cases.unique(),
                    total_cases=total,
                )
            )
        return insights


def _summary(row) -> str:
    share = pct(row.share)
    between = f"Zwischen „{row.source}“ und „{row.target}“"
    # Geht es meistens schnell, aber manchmal sehr lange? Dann sagt der Median allein wenig.
    if row.median_wait < 0.1 * row.p90_wait:
        return (
            f"{between} geht es meist schnell weiter (Median {duration(row.median_wait)}), "
            f"aber jeder zehnte Fall wartet länger als {duration(row.p90_wait)}. Zusammen "
            f"macht dieser Übergang {share} der gesamten Wartezeit im Prozess aus."
        )
    return (
        f"{between} vergehen im Median {duration(row.median_wait)}, bei jedem zehnten Fall "
        f"mehr als {duration(row.p90_wait)}. Dieser Übergang verursacht {share} der gesamten "
        f"Wartezeit im Prozess."
    )

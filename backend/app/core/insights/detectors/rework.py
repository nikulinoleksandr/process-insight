"""Nacharbeit: Dieselbe Aktivität kommt innerhalb eines Falls mehrmals vor.

Nicht jede Wiederholung ist Nacharbeit. Manche Schritte sind dafür da, sich zu wiederholen,
z.B. Laborwerte im Krankenhaus oder Ratenzahlungen. Solche Schritte erkennen wir daran,
dass sie in den meisten Fällen, in denen sie vorkommen, mehrfach auftreten. Sie werden als
"wiederkehrender Schritt" mit niedrigem Schweregrad gemeldet statt als Nacharbeit.
"""

import pandas as pd
from pydantic import BaseModel, Field

from app.core.columns import ACTIVITY, CASE
from app.core.insights.base import Detector, Insight, pct, severity_by_share


class ReworkConfig(BaseModel):
    min_case_share: float = Field(0.02, ge=0, le=1, description="Mindestanteil betroffener Fälle")
    high_share: float = Field(0.20, ge=0, le=1)
    medium_share: float = Field(0.05, ge=0, le=1)
    routine_share: float = Field(
        0.5,
        gt=0,
        le=1,
        description=(
            "Wiederholt sich ein Schritt in mindestens diesem Anteil der Fälle, in denen er "
            "vorkommt, gilt er als planmäßig wiederkehrend statt als Nacharbeit"
        ),
    )
    routine_min_cases: int = Field(
        20, ge=1, description="Erst ab so vielen Fällen mit dem Schritt wird Routine erkannt"
    )
    routine_activities: list[str] = Field(
        default_factory=list,
        description="Schritte, die sich planmäßig wiederholen dürfen (werden nie gemeldet)",
    )


class ReworkDetector(Detector):
    id = "rework"
    name = "Nacharbeit"
    category = "quality"
    required_columns = {CASE, ACTIVITY}
    config_model = ReworkConfig

    def detect(self, log: pd.DataFrame, config: ReworkConfig) -> list[Insight]:
        total = log[CASE].nunique()
        counts = log.groupby([CASE, ACTIVITY], sort=False, observed=True).size()
        cases_with = counts.groupby(level=ACTIVITY, sort=False).size()
        repeated = counts[counts > 1]
        ignored = set(config.routine_activities)

        insights = []
        # Schritte, die immer in genau denselben Fällen wiederholt werden, gehören zusammen
        # (z.B. "Angebot erstellen", "Angebot senden"). Sie werden als ein Befund gemeldet.
        rework_groups: dict[tuple, list] = {}
        for activity, group in repeated.groupby(level=ACTIVITY, sort=False, observed=True):
            if activity in ignored:
                continue
            cases = group.index.get_level_values(CASE)
            share = len(cases) / total
            if share < config.min_case_share:
                continue
            n_with = int(cases_with[activity])
            repeat_rate = len(cases) / n_with
            if n_with >= config.routine_min_cases and repeat_rate >= config.routine_share:
                insights.append(self._routine(activity, group, cases, total, repeat_rate, config))
            else:
                key = tuple(sorted(map(str, cases)))
                rework_groups.setdefault(key, []).append((str(activity), group))
        for members in rework_groups.values():
            insights.append(self._rework(members, total, config))
        return insights

    def _rework(self, members: list, total: int, config: ReworkConfig) -> Insight:
        activities = [name for name, _ in members]
        group = members[0][1]
        cases = group.index.get_level_values(CASE)
        share = len(cases) / total
        extra = int(sum(int((g - 1).sum()) for _, g in members))
        names = _join([f"„{a}“" for a in activities])
        verb = "wird" if len(activities) == 1 else "werden gemeinsam"
        return self.make_insight(
            key="|".join(activities),
            severity=severity_by_share(share, config.high_share, config.medium_share),
            title=f"Nacharbeit bei {names}",
            summary=(
                f"In {len(cases)} von {total} Fällen ({pct(share)}) {verb} {names} "
                f"mehrfach ausgeführt, insgesamt {extra} zusätzliche "
                f"{'Ausführung' if extra == 1 else 'Ausführungen'}."
            ),
            severity_rule=(
                f"hoch ab {pct(config.high_share)} betroffener Fälle, "
                f"mittel ab {pct(config.medium_share)}, sonst niedrig"
            ),
            metrics={
                "affected_cases": len(cases),
                "extra_executions": extra,
                "max_executions_per_case": int(max(int(g.max()) for _, g in members)),
            },
            evidence={"activity": activities[0], "activities": activities, "kind": "rework"},
            affected_cases=cases,
            total_cases=total,
        )

    def _routine(self, activity, group, cases, total, repeat_rate, config) -> Insight:
        mean = float(group.mean())
        mean_text = f"{mean:.1f}".replace(".", ",")
        return self.make_insight(
            key=f"routine:{activity}",
            severity="low",
            title=f"„{activity}“ wiederholt sich fast immer",
            summary=(
                f"In {pct(repeat_rate)} der Fälle mit „{activity}“ kommt der Schritt mehrfach "
                f"vor, im Schnitt {mean_text}-mal. Das spricht für einen planmäßig "
                f"wiederkehrenden Schritt (z.B. regelmäßige Kontrolle) und nicht für Nacharbeit. "
                f"Ist das nicht so vorgesehen, lohnt ein genauer Blick."
            ),
            severity_rule=(
                f"immer niedrig: wiederholt sich in mindestens {pct(config.routine_share)} "
                f"der Fälle, in denen der Schritt vorkommt"
            ),
            metrics={
                "affected_cases": len(cases),
                "repeat_rate": float(repeat_rate),
                "mean_executions": mean,
                "max_executions_per_case": int(group.max()),
            },
            evidence={"activity": str(activity), "activities": [str(activity)], "kind": "routine"},
            affected_cases=cases,
            total_cases=total,
        )


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " und " + items[-1]

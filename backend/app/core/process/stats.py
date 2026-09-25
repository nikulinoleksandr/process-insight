"""Kennzahlen über ein ganzes Log."""

import pandas as pd
from pydantic import BaseModel

from app.core.columns import ACTIVITY, CASE, RESOURCE, TIMESTAMP
from app.core.process.variants import case_variants


class DurationStats(BaseModel):
    """Durchlaufzeiten in Sekunden."""

    mean: float
    median: float
    p90: float
    min: float
    max: float


class LogSummary(BaseModel):
    n_events: int
    n_cases: int
    n_activities: int
    n_variants: int
    n_resources: int | None
    has_resource: bool
    first_event: str
    last_event: str
    case_duration: DurationStats
    activity_counts: dict[str, int]
    activity_cases: dict[str, int]  # in wie vielen Fällen die Aktivität vorkommt


def case_durations(log: pd.DataFrame) -> pd.Series:
    """Durchlaufzeit pro Fall (spätester minus frühester Zeitstempel)."""
    grouped = log.groupby(CASE, sort=False)[TIMESTAMP]
    return grouped.max() - grouped.min()


def summarize(log: pd.DataFrame) -> LogSummary:
    seconds = case_durations(log).dt.total_seconds()
    has_resource = RESOURCE in log.columns and log[RESOURCE].notna().any()
    return LogSummary(
        n_events=len(log),
        n_cases=log[CASE].nunique(),
        n_activities=log[ACTIVITY].nunique(),
        n_variants=case_variants(log).nunique(),
        n_resources=int(log[RESOURCE].nunique()) if has_resource else None,
        has_resource=bool(has_resource),
        first_event=log[TIMESTAMP].min().isoformat(),
        last_event=log[TIMESTAMP].max().isoformat(),
        case_duration=DurationStats(
            mean=float(seconds.mean()),
            median=float(seconds.median()),
            p90=float(seconds.quantile(0.9)),
            min=float(seconds.min()),
            max=float(seconds.max()),
        ),
        activity_counts={str(k): int(v) for k, v in log[ACTIVITY].value_counts().items()},
        activity_cases={
            str(k): int(v) for k, v in log.groupby(ACTIVITY, sort=False)[CASE].nunique().items()
        },
    )

"""Varianten: die Reihenfolge der Aktivitäten eines Falls."""

import pandas as pd
from pydantic import BaseModel

from app.core.columns import ACTIVITY, CASE

SEPARATOR = " → "


class Variant(BaseModel):
    activities: list[str]
    case_count: int
    case_share: float


def case_variants(log: pd.DataFrame) -> pd.Series:
    """Pro Fall ein Text mit der Aktivitätsfolge, z.B. 'A → B → C'."""
    return log.groupby(CASE, sort=False)[ACTIVITY].agg(SEPARATOR.join)


def top_variants(log: pd.DataFrame, limit: int = 20) -> list[Variant]:
    per_case = case_variants(log)
    counts = per_case.value_counts()
    total = len(per_case)
    return [
        Variant(activities=v.split(SEPARATOR), case_count=int(c), case_share=c / total)
        for v, c in counts.head(limit).items()
    ]

"""Varianten: die Reihenfolge der Aktivitäten eines Falls."""

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.core.columns import ACTIVITY, CASE


class Variant(BaseModel):
    activities: list[str]
    case_count: int
    case_share: float


def case_variants(log: pd.DataFrame) -> pd.Series:
    """Pro Fall ein kompakter Schlüssel für die Aktivitätsfolge.

    Fälle mit derselben Folge haben denselben Schlüssel. Statt Texte zusammenzukleben
    (bei 150.000 Fällen mehrere Sekunden) wird jede Aktivität durch eine Zahl ersetzt und
    die Zahlenfolge als Bytes verwendet. Das Log muss nach Fall und Zeit sortiert sein.
    Lesbar machen: decode_variant(schlüssel, series.attrs["activities"]).
    """
    if log.empty:
        return pd.Series([], dtype=object)
    activity_codes, activities = pd.factorize(log[ACTIVITY])
    case_codes, _ = pd.factorize(log[CASE])
    boundaries = np.flatnonzero(np.diff(case_codes)) + 1
    parts = np.split(activity_codes.astype(np.int32), boundaries)
    starts = np.concatenate(([0], boundaries))
    keys = pd.Series(
        [part.tobytes() for part in parts],
        index=pd.Index(log[CASE].to_numpy()[starts], name=CASE),
        dtype=object,
    )
    keys.attrs["activities"] = [str(a) for a in activities]
    return keys


def decode_variant(key: bytes, activities: list[str]) -> list[str]:
    return [activities[i] for i in np.frombuffer(key, dtype=np.int32)]


def top_variants(log: pd.DataFrame, limit: int = 20) -> list[Variant]:
    per_case = case_variants(log)
    counts = per_case.value_counts()
    total = len(per_case)
    names = per_case.attrs.get("activities", [])
    return [
        Variant(activities=decode_variant(v, names), case_count=int(c), case_share=c / total)
        for v, c in counts.head(limit).items()
    ]

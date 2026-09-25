"""Direkte Übergänge A -> B innerhalb eines Falls.

Grundlage für Prozesslandkarte und Engpass-Erkennung.
"""

import pandas as pd

from app.core.columns import ACTIVITY, CASE, TIMESTAMP


def transitions(log: pd.DataFrame) -> pd.DataFrame:
    """Eine Zeile pro Übergang mit Spalten: case, source, target, wait (Timedelta).

    Das Log muss nach Fall und Zeit sortiert sein (macht normalize()).
    """
    nxt = log.groupby(CASE, sort=False)[[ACTIVITY, TIMESTAMP]].shift(-1)
    df = pd.DataFrame(
        {
            "case": log[CASE],
            "source": log[ACTIVITY],
            "target": nxt[ACTIVITY],
            "wait": nxt[TIMESTAMP] - log[TIMESTAMP],
        }
    )
    return df.dropna(subset=["target"]).reset_index(drop=True)

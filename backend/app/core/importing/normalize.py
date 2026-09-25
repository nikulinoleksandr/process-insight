"""Bringt ein eingelesenes Log in das einheitliche interne Format (siehe ARCHITEKTUR.md, 4.1)."""

from dataclasses import dataclass

import pandas as pd

from app.core.columns import ACTIVITY, CASE, REQUIRED_COLUMNS, RESOURCE, TIMESTAMP


class LogFormatError(ValueError):
    """Das Log ist nicht nutzbar, z.B. weil Pflichtspalten fehlen."""


@dataclass(frozen=True)
class ColumnMapping:
    """Welche Spalte der Quelldatei welche Bedeutung hat."""

    case: str
    activity: str
    timestamp: str
    resource: str | None = None


@dataclass(frozen=True)
class NormalizedLog:
    events: pd.DataFrame
    dropped_rows: int


def normalize(df: pd.DataFrame, mapping: ColumnMapping | None = None) -> NormalizedLog:
    """Benennt Spalten um, parst Zeitstempel nach UTC, entfernt unvollständige Zeilen, sortiert.

    Ohne mapping wird angenommen, dass die Spalten schon die Standardnamen tragen (XES).
    """
    df = df.copy()
    if mapping is not None:
        df = _apply_mapping(df, mapping)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise LogFormatError(f"Pflichtspalten fehlen: {', '.join(missing)}")

    df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP], utc=True, errors="coerce", format="mixed")
    df[CASE] = df[CASE].astype("string")
    df[ACTIVITY] = df[ACTIVITY].astype("string")
    if RESOURCE in df.columns:
        df[RESOURCE] = df[RESOURCE].astype("string")

    before = len(df)
    df = df.dropna(subset=list(REQUIRED_COLUMNS))
    dropped = before - len(df)
    if df.empty:
        raise LogFormatError("Das Log enthält keine gültigen Events.")

    df = df.sort_values([CASE, TIMESTAMP], kind="stable").reset_index(drop=True)
    return NormalizedLog(events=df, dropped_rows=dropped)


def _apply_mapping(df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    source_to_target = {
        mapping.case: CASE,
        mapping.activity: ACTIVITY,
        mapping.timestamp: TIMESTAMP,
    }
    if mapping.resource:
        source_to_target[mapping.resource] = RESOURCE

    unknown = [src for src in source_to_target if src not in df.columns]
    if unknown:
        raise LogFormatError(f"Spalten nicht in der Datei gefunden: {', '.join(unknown)}")
    if len(set(source_to_target)) != len(source_to_target):
        raise LogFormatError("Eine Spalte wurde mehreren Rollen zugeordnet.")

    # Vorhandene Spalten mit Zielnamen, die nicht gemeint sind, würden sonst kollidieren.
    targets = source_to_target.values()
    clashing = [t for t in targets if t in df.columns and t not in source_to_target]
    df = df.drop(columns=clashing)
    return df.rename(columns=source_to_target)

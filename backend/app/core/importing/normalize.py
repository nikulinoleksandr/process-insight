"""Bringt ein eingelesenes Log in das einheitliche interne Format (siehe ARCHITEKTUR.md, 4.1)."""

from dataclasses import dataclass

import pandas as pd

from app.core.columns import ACTIVITY, CASE, LIFECYCLE, REQUIRED_COLUMNS, RESOURCE, TIMESTAMP


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
    ignored_lifecycle_events: int = 0  # z.B. "start"-Events, wenn es auch "complete" gibt


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
    df, ignored = _keep_completed(df)
    if df.empty:
        raise LogFormatError("Das Log enthält keine gültigen Events.")

    df = df.sort_values([CASE, TIMESTAMP], kind="stable").reset_index(drop=True)
    return NormalizedLog(events=df, dropped_rows=dropped, ignored_lifecycle_events=ignored)


def _keep_completed(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Viele Logs (z.B. BPI 2012) haben pro Arbeitsschritt mehrere Events: "schedule",
    "start" und "complete". Für die Analyse zählt jeder Schritt einmal, sonst sähe jeder
    Schritt wie eine Wiederholung aus. Deshalb bleiben nur die "complete"-Events."""
    if LIFECYCLE not in df.columns:
        return df, 0
    state = df[LIFECYCLE].astype("string").str.strip().str.lower()
    is_complete = state == "complete"
    if not is_complete.any() or is_complete.fillna(True).all():
        return df, 0
    keep = is_complete.fillna(True)  # Events ohne Angabe behalten
    return df[keep.to_numpy()], int((~keep).sum())


_LIFECYCLE_NAMES = {"lifecycle:transition", "lifecycle", "transition"}


def _apply_mapping(df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    source_to_target = {
        mapping.case: CASE,
        mapping.activity: ACTIVITY,
        mapping.timestamp: TIMESTAMP,
    }
    if mapping.resource:
        source_to_target[mapping.resource] = RESOURCE
    # Eine Lifecycle-Spalte wird automatisch erkannt, sie muss nicht zugeordnet werden.
    lifecycle = next((c for c in df.columns if c.strip().lower() in _LIFECYCLE_NAMES), None)
    if lifecycle and lifecycle not in source_to_target:
        source_to_target[lifecycle] = LIFECYCLE

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

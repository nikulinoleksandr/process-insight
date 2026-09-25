"""Einlesen von CSV-Dateien inklusive Vorschlag für die Spaltenzuordnung."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.core.importing.normalize import ColumnMapping, LogFormatError, NormalizedLog, normalize

# Typische Spaltennamen, klein geschrieben. Die erste passende Spalte wird vorgeschlagen.
_HINTS = {
    "case": ["case:concept:name", "case_id", "caseid", "case", "fall", "fall_id", "order_id"],
    "activity": ["concept:name", "activity", "aktivität", "aktivitaet", "event", "task"],
    "timestamp": ["time:timestamp", "timestamp", "time", "zeitstempel", "zeit", "date", "datum"],
    "resource": ["org:resource", "resource", "ressource", "user", "bearbeiter", "person"],
}


@dataclass(frozen=True)
class CsvPreview:
    columns: list[str]
    rows: list[dict]
    suggested: dict[str, str | None]


def _read_raw(path: Path, nrows: int | None = None) -> pd.DataFrame:
    try:
        # sep=None lässt pandas das Trennzeichen (Komma, Semikolon, ...) selbst erkennen.
        return pd.read_csv(path, sep=None, engine="python", nrows=nrows, dtype=str)
    except Exception as exc:
        raise LogFormatError(f"CSV-Datei konnte nicht gelesen werden: {exc}") from exc


def preview_csv(path: Path, n: int = 5) -> CsvPreview:
    df = _read_raw(path, nrows=n)
    columns = list(df.columns)
    return CsvPreview(
        columns=columns,
        rows=df.fillna("").to_dict(orient="records"),
        suggested=suggest_mapping(columns),
    )


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    lowered = {c.lower().strip(): c for c in columns}
    suggestion: dict[str, str | None] = {}
    used: set[str] = set()
    for role, hints in _HINTS.items():
        match = next((lowered[h] for h in hints if h in lowered and lowered[h] not in used), None)
        suggestion[role] = match
        if match:
            used.add(match)
    return suggestion


def read_csv(path: Path, mapping: ColumnMapping) -> NormalizedLog:
    return normalize(_read_raw(path), mapping)

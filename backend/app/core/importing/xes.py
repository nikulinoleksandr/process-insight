"""Einlesen von XES-Dateien (XML-Standardformat für Event-Logs)."""

from pathlib import Path

import pm4py

from app.core.importing.normalize import LogFormatError, NormalizedLog, normalize


def read_xes(path: Path) -> NormalizedLog:
    try:
        df = pm4py.read_xes(str(path), return_legacy_log_object=False)
    except Exception as exc:  # PM4Py wirft je nach Fehler unterschiedliche Typen
        raise LogFormatError(f"XES-Datei konnte nicht gelesen werden: {exc}") from exc
    return normalize(df)

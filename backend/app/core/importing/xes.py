"""Einlesen von XES-Dateien (XML-Standardformat für Event-Logs)."""

import gzip
import logging
from pathlib import Path

import pm4py

from app.core.importing.normalize import LogFormatError, NormalizedLog, normalize

logger = logging.getLogger(__name__)

_HEAD_BYTES = 64 * 1024


def read_xes(path: Path) -> NormalizedLog:
    _reject_doctype(path)
    try:
        df = _read_fast(path)
    except BaseException as exc:  # PM4Py und rustxes werfen unterschiedliche Typen
        if isinstance(exc, KeyboardInterrupt | SystemExit):
            raise
        raise LogFormatError(f"XES-Datei konnte nicht gelesen werden: {exc}") from exc
    return normalize(df)


def _read_fast(path: Path):
    """rustxes (in Rust geschrieben) liest große Logs etwa 4-mal schneller als der
    Standard-Parser. Ist es nicht installiert oder scheitert es, nehmen wir den Standard."""
    try:
        return pm4py.read_xes(str(path), variant="rustxes", return_legacy_log_object=False)
    except BaseException as exc:  # rustxes meldet kaputte Dateien als "PanicException"
        if isinstance(exc, KeyboardInterrupt | SystemExit):
            raise
        logger.info("rustxes nicht nutzbar (%s), nehme Standard-Parser", type(exc).__name__)
        return pm4py.read_xes(str(path), variant="iterparse", return_legacy_log_object=False)


def _reject_doctype(path: Path) -> None:
    """XES braucht keine DTD. Eine DOCTYPE- oder ENTITY-Angabe ist ein Zeichen für einen
    Angriff (XXE: eine Datei, die den Server eigene Dateien einlesen lässt)."""
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    try:
        with opener(path, "rb") as fh:
            head = fh.read(_HEAD_BYTES).lower()
    except OSError as exc:
        raise LogFormatError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    if b"<!doctype" in head or b"<!entity" in head:
        raise LogFormatError("XES-Dateien mit DOCTYPE- oder ENTITY-Angaben werden abgelehnt.")

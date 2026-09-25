"""Anwendungsfälle rund um Event-Logs: hochladen, zuordnen, speichern, laden."""

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from app.core.importing.csv import CsvPreview, preview_csv, read_csv
from app.core.importing.normalize import ColumnMapping, LogFormatError, NormalizedLog
from app.core.importing.xes import read_xes
from app.core.process.stats import summarize
from app.services.errors import BadInputError, ConflictError, NotFoundError, TooLargeError
from app.storage.database import Database
from app.storage.files import FileStore

_CHUNK = 1024 * 1024


def detect_format(filename: str) -> tuple[str, str]:
    """Gibt (Format, Dateiendung) zurück oder wirft BadInputError."""
    name = filename.lower()
    if name.endswith(".xes.gz"):
        return "xes", ".xes.gz"
    if name.endswith(".xes"):
        return "xes", ".xes"
    if name.endswith(".csv"):
        return "csv", ".csv"
    raise BadInputError("Nur .xes, .xes.gz und .csv werden unterstützt.")


class LogService:
    def __init__(self, db: Database, files: FileStore, max_upload_mb: int, max_events: int):
        self.db = db
        self.files = files
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.max_events = max_events

    def create(
        self, filename: str, stream: BinaryIO, is_demo: bool = False
    ) -> tuple[dict, CsvPreview | None]:
        """Speichert eine hochgeladene Datei. XES wird sofort eingelesen, CSV braucht erst
        eine Spaltenzuordnung und bekommt deshalb eine Vorschau zurück."""
        fmt, suffix = detect_format(filename)
        log_id = str(uuid.uuid4())
        target = self.files.original_path(log_id, suffix)
        self._copy_limited(stream, target)

        self.db.insert_log(log_id, Path(filename).name, fmt, "processing", is_demo=is_demo)
        if fmt == "csv":
            try:
                preview = preview_csv(target)
            except LogFormatError as exc:
                self.db.update_log(log_id, status="failed")
                raise BadInputError(str(exc)) from exc
            self.db.update_log(log_id, status="needs_mapping")
            return self.get(log_id), preview

        self._ingest(log_id, lambda: read_xes(target))
        return self.get(log_id), None

    def apply_mapping(self, log_id: str, mapping: ColumnMapping) -> dict:
        record = self.get(log_id)
        if record["source_format"] != "csv":
            raise ConflictError("Eine Spaltenzuordnung ist nur für CSV-Dateien nötig.")
        original = self.files.find_original(log_id)
        self._ingest(log_id, lambda: read_csv(original, mapping), keep_on_error=True)
        return self.get(log_id)

    def get(self, log_id: str) -> dict:
        record = self.db.get_log(log_id)
        if record is None:
            raise NotFoundError(f"Log {log_id} nicht gefunden.")
        return record

    def events(self, log_id: str) -> pd.DataFrame:
        record = self.get(log_id)
        if record["status"] != "ready":
            raise ConflictError(f"Log ist noch nicht bereit (Status: {record['status']}).")
        return self.files.load_events(log_id)

    def demo(self) -> dict:
        record = self.db.find_demo_log()
        if record is None:
            raise NotFoundError("Kein Demo-Log vorhanden.")
        return record

    def ensure_demo(self, path: Path | None) -> dict | None:
        """Legt das Demo-Log einmalig an, damit Besucher sofort etwas ausprobieren können."""
        existing = self.db.find_demo_log()
        if existing or path is None or not path.exists():
            return existing
        with path.open("rb") as fh:
            record, _ = self.create(path.name, fh, is_demo=True)
        return record

    # --- intern ---------------------------------------------------------------

    def _copy_limited(self, stream: BinaryIO, target: Path) -> None:
        written = 0
        with target.open("wb") as out:
            while chunk := stream.read(_CHUNK):
                written += len(chunk)
                if written > self.max_bytes:
                    out.close()
                    shutil.rmtree(target.parent, ignore_errors=True)
                    raise TooLargeError(
                        f"Datei ist größer als {self.max_bytes // (1024 * 1024)} MB."
                    )
                out.write(chunk)

    def _ingest(self, log_id: str, reader, keep_on_error: bool = False) -> None:
        try:
            normalized: NormalizedLog = reader()
        except LogFormatError as exc:
            if not keep_on_error:
                self.db.update_log(log_id, status="failed")
            raise BadInputError(str(exc)) from exc

        events = normalized.events
        if len(events) > self.max_events:
            self.db.update_log(log_id, status="failed")
            raise TooLargeError(f"Log hat mehr als {self.max_events:,} Events.".replace(",", "."))

        self.files.save_events(log_id, events)
        summary = summarize(events)
        self.db.update_log(
            log_id,
            status="ready",
            n_events=summary.n_events,
            n_cases=summary.n_cases,
            n_activities=summary.n_activities,
            has_resource=int(summary.has_resource),
            dropped_rows=normalized.dropped_rows,
        )

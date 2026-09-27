"""Anwendungsfälle rund um Event-Logs: hochladen, zuordnen, speichern, laden."""

import hashlib
import shutil
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from app.core.importing.csv import CsvPreview, preview_csv, read_csv
from app.core.importing.normalize import ColumnMapping, LogFormatError, NormalizedLog
from app.core.importing.xes import read_xes
from app.core.process.stats import LogSummary, summarize
from app.services.errors import BadInputError, ConflictError, NotFoundError, TooLargeError
from app.storage.database import Database, now
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


class _LogCache:
    """Hält die zuletzt benutzten Logs im Arbeitsspeicher.

    Die Oberfläche fragt für ein Log viele Dinge nacheinander ab (Kennzahlen, Karte bei
    jeder Reglerbewegung, Analyse). Ohne Zwischenspeicher würde jedes Mal die Parquet-Datei
    neu gelesen. Neben den Events werden abgeleitete Werte (z.B. alle Kanten der
    Prozesslandkarte) mitgespeichert.
    """

    def __init__(self, max_logs: int):
        self.max_logs = max_logs
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, log_id: str, loader: Callable[[], pd.DataFrame]) -> dict[str, Any]:
        with self._lock:
            if log_id in self._items:
                self._items.move_to_end(log_id)
                return self._items[log_id]
        entry = {"events": loader(), "extras": {}}
        with self._lock:
            self._items[log_id] = entry
            self._items.move_to_end(log_id)
            while len(self._items) > self.max_logs:
                self._items.popitem(last=False)
        return entry

    def drop(self, log_id: str) -> None:
        with self._lock:
            self._items.pop(log_id, None)


class LogService:
    def __init__(
        self,
        db: Database,
        files: FileStore,
        max_upload_mb: int,
        max_events: int,
        cache_logs: int = 2,
    ):
        self.db = db
        self.files = files
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.max_events = max_events
        self.cache = _LogCache(cache_logs)
        self.on_new_log: Callable[[], None] | None = None  # z.B. Aufräumen anstoßen

    def create(
        self, filename: str, stream: BinaryIO, is_demo: bool = False
    ) -> tuple[dict, CsvPreview | None]:
        """Speichert eine hochgeladene Datei. XES wird sofort eingelesen, CSV braucht erst
        eine Spaltenzuordnung und bekommt deshalb eine Vorschau zurück.

        Wurde genau dieselbe Datei schon einmal hochgeladen, wird das vorhandene Log
        zurückgegeben statt eine zweite Kopie anzulegen.
        """
        fmt, suffix = detect_format(filename)
        log_id = str(uuid.uuid4())
        target = self.files.original_path(log_id, suffix)
        content_hash, size = self._copy_limited(stream, target)

        duplicate = self.db.find_by_hash(content_hash)
        if duplicate and bool(duplicate["is_demo"]) == is_demo:
            self.files.delete_log(log_id)
            self.db.touch_log(duplicate["id"])
            preview = None
            if duplicate["status"] == "needs_mapping":
                preview = preview_csv(self.files.find_original(duplicate["id"]))
            return self.get(duplicate["id"]), preview

        self.db.insert_log(log_id, Path(filename).name, fmt, "processing", is_demo=is_demo)
        self.db.update_log(log_id, content_hash=content_hash, last_accessed=now())
        if fmt == "csv":
            try:
                preview = preview_csv(target)
            except LogFormatError as exc:
                self._fail(log_id)
                raise BadInputError(str(exc)) from exc
            self.db.update_log(log_id, status="needs_mapping", size_bytes=size)
            return self.get(log_id), preview

        self._ingest(log_id, lambda: read_xes(target))
        return self.get(log_id), None

    def apply_mapping(self, log_id: str, mapping: ColumnMapping) -> dict:
        record = self.get(log_id)
        if record["source_format"] != "csv":
            raise ConflictError("Eine Spaltenzuordnung ist nur für CSV-Dateien nötig.")
        original = self.files.find_original(log_id)
        if original is None:
            raise ConflictError("Die Spalten dieses Logs sind bereits zugeordnet.")
        self._ingest(log_id, lambda: read_csv(original, mapping), keep_on_error=True)
        return self.get(log_id)

    def get(self, log_id: str) -> dict:
        record = self.db.get_log(log_id)
        if record is None:
            raise NotFoundError(f"Log {log_id} nicht gefunden.")
        return record

    def events(self, log_id: str) -> pd.DataFrame:
        return self._entry(log_id)["events"]

    def derived(self, log_id: str, key: str, compute: Callable[[pd.DataFrame], Any]) -> Any:
        """Ein aus dem Log berechneter Wert, der für dieses Log nur einmal berechnet wird."""
        entry = self._entry(log_id)
        extras = entry["extras"]
        if key not in extras:
            extras[key] = compute(entry["events"])
        return extras[key]

    def summary(self, log_id: str) -> LogSummary:
        """Kennzahlen; werden beim Import einmal berechnet und als Datei abgelegt."""
        self._require_ready(log_id)
        path = self.files.summary_path(log_id)
        if path.exists():
            return LogSummary.model_validate_json(path.read_text(encoding="utf-8"))
        summary = summarize(self.events(log_id))  # ältere Logs ohne gespeicherte Kennzahlen
        path.write_text(summary.model_dump_json(), encoding="utf-8")
        return summary

    def delete(self, log_id: str) -> None:
        self.cache.drop(log_id)
        for analysis_id in self.db.analysis_ids_for_log(log_id):
            self.files.result_path(analysis_id).unlink(missing_ok=True)
        self.db.delete_log(log_id)
        self.files.delete_log(log_id)

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

    def _require_ready(self, log_id: str) -> dict:
        record = self.get(log_id)
        if record["status"] != "ready":
            raise ConflictError(f"Log ist noch nicht bereit (Status: {record['status']}).")
        return record

    def _entry(self, log_id: str) -> dict[str, Any]:
        self._require_ready(log_id)
        self.db.touch_log(log_id)
        return self.cache.get(log_id, lambda: self.files.load_events(log_id))

    def _copy_limited(self, stream: BinaryIO, target: Path) -> tuple[str, int]:
        """Kopiert die Datei, bricht bei Übergröße ab und berechnet dabei den Fingerabdruck."""
        written = 0
        digest = hashlib.sha256()
        with target.open("wb") as out:
            while chunk := stream.read(_CHUNK):
                written += len(chunk)
                if written > self.max_bytes:
                    out.close()
                    shutil.rmtree(target.parent, ignore_errors=True)
                    raise TooLargeError(
                        f"Datei ist größer als {self.max_bytes // (1024 * 1024)} MB."
                    )
                digest.update(chunk)
                out.write(chunk)
        return digest.hexdigest(), written

    def _fail(self, log_id: str) -> None:
        self.db.update_log(log_id, status="failed")
        self.files.delete_original(log_id)

    def _ingest(self, log_id: str, reader, keep_on_error: bool = False) -> None:
        try:
            normalized: NormalizedLog = reader()
        except LogFormatError as exc:
            if not keep_on_error:
                self._fail(log_id)
            raise BadInputError(str(exc)) from exc

        events = normalized.events
        if len(events) > self.max_events:
            self._fail(log_id)
            raise TooLargeError(f"Log hat mehr als {self.max_events:,} Events.".replace(",", "."))

        self.files.save_events(log_id, events)
        summary = summarize(events)
        self.files.summary_path(log_id).write_text(summary.model_dump_json(), encoding="utf-8")
        self.files.delete_original(log_id)  # ab jetzt reicht die viel kleinere Parquet-Datei
        self.db.update_log(
            log_id,
            status="ready",
            n_events=summary.n_events,
            n_cases=summary.n_cases,
            n_activities=summary.n_activities,
            has_resource=int(summary.has_resource),
            dropped_rows=normalized.dropped_rows,
            ignored_lifecycle_events=normalized.ignored_lifecycle_events,
            size_bytes=self.files.log_size(log_id),
        )
        self.cache.drop(log_id)
        if self.on_new_log:
            self.on_new_log()

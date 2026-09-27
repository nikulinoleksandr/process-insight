"""Hält den Speicher klein: löscht alte Logs, Waisen und bei Bedarf die ältesten Logs.

Regeln (einstellbar in config.py):
- Logs, die länger als retention_days nicht benutzt wurden, werden gelöscht.
- Überschreitet der Speicher max_storage_mb, werden die am längsten unbenutzten Logs
  gelöscht, bis er wieder unter der Grenze liegt.
- Das Demo-Log bleibt immer erhalten.
- Dateien ohne Eintrag in der Datenbank ("Waisen") und abgebrochene Uploads werden entfernt.
- Doppelte Logs aus älteren Versionen (gleicher Dateiinhalt) werden zusammengeführt.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.log_service import LogService
from app.storage.database import Database
from app.storage.files import FileStore

logger = logging.getLogger(__name__)

STALE_UPLOAD = timedelta(hours=1)


@dataclass
class CleanupReport:
    deleted_logs: list[str] = field(default_factory=list)
    deleted_files: int = 0
    bytes_before: int = 0
    bytes_after: int = 0


class CleanupService:
    def __init__(
        self,
        db: Database,
        files: FileStore,
        logs: LogService,
        retention_days: float,
        max_storage_mb: int,
    ):
        self.db = db
        self.files = files
        self.logs = logs
        self.retention = timedelta(days=retention_days) if retention_days > 0 else None
        self.max_bytes = max_storage_mb * 1024 * 1024 if max_storage_mb > 0 else None
        self._lock = threading.Lock()

    def run(self, now: datetime | None = None) -> CleanupReport:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            report = CleanupReport(bytes_before=self.files.total_size())
            self._migrate_old_logs(report)
            self._remove_broken(report, now)
            self._remove_expired(report, now)
            self._enforce_limit(report)
            self._remove_orphans(report)
            report.bytes_after = self.files.total_size()
        if report.deleted_logs or report.deleted_files:
            logger.info(
                "Aufgeräumt: %d Logs, %d Dateien, %.1f MB -> %.1f MB",
                len(report.deleted_logs),
                report.deleted_files,
                report.bytes_before / 1e6,
                report.bytes_after / 1e6,
            )
        return report

    # --- einzelne Regeln ---------------------------------------------------------

    def _migrate_old_logs(self, report: CleanupReport) -> None:
        """Logs aus älteren Versionen: Fingerabdruck nachtragen, Duplikate entfernen,
        Originaldateien löschen, wenn das Log schon eingelesen ist."""
        newest_by_hash: dict[str, dict] = {}
        for record in self.db.list_logs():
            log_id = record["id"]
            original = self.files.find_original(log_id)
            if record["content_hash"] is None and original is not None:
                record["content_hash"] = _sha256(original)
                self.db.update_log(log_id, content_hash=record["content_hash"])
            if record["status"] == "ready" and original is not None:
                self.files.delete_original(log_id)
                report.deleted_files += 1
            if record["status"] == "ready" and record["size_bytes"] is None:
                self.db.update_log(log_id, size_bytes=self.files.log_size(log_id))
            key = record["content_hash"]
            if not key or record["status"] != "ready" or record["is_demo"]:
                continue
            kept = newest_by_hash.get(key)
            if kept is None:
                newest_by_hash[key] = record
                continue
            older = kept if _last_used(kept) < _last_used(record) else record
            newest_by_hash[key] = record if older is kept else kept
            self._delete(older["id"], report)

    def _remove_broken(self, report: CleanupReport, now: datetime) -> None:
        for record in self.db.list_logs():
            stale = now - _last_used(record) > STALE_UPLOAD
            if record["status"] == "failed" or (record["status"] == "processing" and stale):
                self._delete(record["id"], report)

    def _remove_expired(self, report: CleanupReport, now: datetime) -> None:
        if self.retention is None:
            return
        for record in self.db.list_logs():
            if not record["is_demo"] and now - _last_used(record) > self.retention:
                self._delete(record["id"], report)

    def _enforce_limit(self, report: CleanupReport) -> None:
        if self.max_bytes is None:
            return
        candidates = sorted((r for r in self.db.list_logs() if not r["is_demo"]), key=_last_used)
        total = self.files.total_size()
        for record in candidates:
            if total <= self.max_bytes:
                break
            size = self.files.log_size(record["id"])
            self._delete(record["id"], report)
            total -= size

    def _remove_orphans(self, report: CleanupReport) -> None:
        known_logs = {r["id"] for r in self.db.list_logs()}
        young = time.time() - STALE_UPLOAD.total_seconds()
        for log_id in self.files.existing_log_ids() - known_logs:
            # Ein Upload legt seinen Ordner an, bevor er in der Datenbank steht. Junge
            # Ordner könnten also gerade hochgeladen werden und bleiben unangetastet.
            if self.files.log_mtime(log_id) > young:
                continue
            self.files.delete_log(log_id)
            report.deleted_files += 1
        known_analyses = self.db.all_analysis_ids()
        for analysis_id in self.files.existing_result_ids() - known_analyses:
            self.files.result_path(analysis_id).unlink(missing_ok=True)
            report.deleted_files += 1
        if self.retention is not None:
            cutoff = time.time() - self.retention.total_seconds()
            for path in self.files.explanations_dir().glob("*.json"):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    report.deleted_files += 1

    def _delete(self, log_id: str, report: CleanupReport) -> None:
        self.logs.delete(log_id)
        report.deleted_logs.append(log_id)


def _last_used(record: dict) -> datetime:
    value = record.get("last_accessed") or record["uploaded_at"]
    return datetime.fromisoformat(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

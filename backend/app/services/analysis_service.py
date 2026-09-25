"""Anwendungsfälle rund um Analysen: starten, im Hintergrund ausführen, Ergebnis liefern."""

import hashlib
import json
import logging
import uuid
from typing import Any

from app.core.insights.engine import AnalysisResult, InvalidConfigError, run_analysis
from app.core.insights.engine import validate_config as _validate
from app.services.errors import BadInputError, ConflictError, NotFoundError
from app.services.log_service import LogService
from app.storage.database import Database, now
from app.storage.files import FileStore

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, db: Database, files: FileStore, logs: LogService):
        self.db = db
        self.files = files
        self.logs = logs

    def start(self, log_id: str, config: dict[str, Any] | None) -> tuple[dict, bool]:
        """Legt eine Analyse an. Gibt (Datensatz, muss_noch_laufen) zurück.

        Gibt es schon eine Analyse mit derselben Konfiguration, wird sie wiederverwendet.
        """
        record = self.logs.get(log_id)
        if record["status"] != "ready":
            raise ConflictError(f"Log ist noch nicht bereit (Status: {record['status']}).")
        try:
            validated = _validate(config)
        except InvalidConfigError as exc:
            raise BadInputError(str(exc)) from exc

        normalized = {k: v.model_dump(mode="json") for k, v in validated.items()}
        config_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
        existing = self.db.find_reusable_analysis(log_id, config_hash)
        if existing:
            return existing, False

        analysis_id = str(uuid.uuid4())
        self.db.insert_analysis(analysis_id, log_id, config_hash, normalized)
        return self.get(analysis_id), True

    def run(self, analysis_id: str) -> None:
        """Wird im Hintergrund ausgeführt."""
        record = self.get(analysis_id)
        self.db.update_analysis(analysis_id, status="running", started_at=now())
        try:
            events = self.logs.events(record["log_id"])
            result = run_analysis(events, json.loads(record["config_json"]))
            self.files.result_path(analysis_id).write_text(
                result.model_dump_json(), encoding="utf-8"
            )
            self.db.update_analysis(analysis_id, status="done", finished_at=now())
        except Exception as exc:
            logger.exception("Analyse %s fehlgeschlagen", analysis_id)
            self.db.update_analysis(
                analysis_id, status="failed", finished_at=now(), error_message=str(exc)
            )

    def get(self, analysis_id: str) -> dict:
        record = self.db.get_analysis(analysis_id)
        if record is None:
            raise NotFoundError(f"Analyse {analysis_id} nicht gefunden.")
        return record

    def result(self, analysis_id: str) -> AnalysisResult | None:
        record = self.get(analysis_id)
        if record["status"] != "done":
            return None
        text = self.files.result_path(analysis_id).read_text(encoding="utf-8")
        return AnalysisResult.model_validate_json(text)

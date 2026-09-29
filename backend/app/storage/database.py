"""Metadaten zu Logs und Analysen in einer kleinen SQLite-Datenbank."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_format TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    status TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    n_events INTEGER,
    n_cases INTEGER,
    n_activities INTEGER,
    has_resource INTEGER,
    dropped_rows INTEGER
);
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    log_id TEXT NOT NULL REFERENCES logs(id),
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_log ON analyses(log_id, config_hash);
"""


# Spalten, die nach der ersten Version dazugekommen sind. Bestehende Datenbanken werden
# beim Start automatisch ergänzt (einfache Migration ohne Zusatzwerkzeug).
_ADDED_LOG_COLUMNS = {
    "content_hash": "TEXT",
    "size_bytes": "INTEGER",
    "last_accessed": "TEXT",
    "ignored_lifecycle_events": "INTEGER",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(_SCHEMA)
            existing = {row["name"] for row in con.execute("PRAGMA table_info(logs)")}
            for column, sql_type in _ADDED_LOG_COLUMNS.items():
                if column not in existing:
                    con.execute(f"ALTER TABLE logs ADD COLUMN {column} {sql_type}")
            con.execute("CREATE INDEX IF NOT EXISTS idx_logs_hash ON logs(content_hash)")
            # Jobs, die bei einem Neustart noch liefen, können nicht mehr fertig werden.
            con.execute(
                "UPDATE analyses SET status='failed', error_message=? "
                "WHERE status IN ('pending', 'running')",
                ("Server wurde während der Analyse neu gestartet.",),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- Logs ---------------------------------------------------------------

    def insert_log(self, log_id: str, name: str, source_format: str, status: str, is_demo=False):
        with self.connect() as con:
            con.execute(
                "INSERT INTO logs (id, name, source_format, uploaded_at, status, is_demo) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, name, source_format, now(), status, int(is_demo)),
            )

    def update_log(self, log_id: str, **fields: Any) -> None:
        _update(self, "logs", log_id, fields)

    def get_log(self, log_id: str) -> dict | None:
        return _get(self, "logs", log_id)

    def find_by_hash(self, content_hash: str) -> dict | None:
        """Ein bereits hochgeladenes, nutzbares Log mit genau demselben Dateiinhalt."""
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM logs WHERE content_hash=? AND status IN ('ready', 'needs_mapping') "
                "ORDER BY uploaded_at DESC LIMIT 1",
                (content_hash,),
            ).fetchone()
        return dict(row) if row else None

    def touch_log(self, log_id: str) -> None:
        with self.connect() as con:
            con.execute("UPDATE logs SET last_accessed=? WHERE id=?", (now(), log_id))

    def list_logs(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM logs ORDER BY uploaded_at").fetchall()
        return [dict(r) for r in rows]

    def analysis_ids_for_log(self, log_id: str) -> list[str]:
        with self.connect() as con:
            rows = con.execute("SELECT id FROM analyses WHERE log_id=?", (log_id,)).fetchall()
        return [r["id"] for r in rows]

    def all_analysis_ids(self) -> set[str]:
        with self.connect() as con:
            return {r["id"] for r in con.execute("SELECT id FROM analyses")}

    def delete_log(self, log_id: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM analyses WHERE log_id=?", (log_id,))
            con.execute("DELETE FROM logs WHERE id=?", (log_id,))

    def find_demo_log(self) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM logs WHERE is_demo=1 AND status='ready' LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # --- Analysen -----------------------------------------------------------

    def insert_analysis(self, analysis_id: str, log_id: str, config_hash: str, config: dict):
        with self.connect() as con:
            con.execute(
                "INSERT INTO analyses (id, log_id, config_hash, config_json, status, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (analysis_id, log_id, config_hash, json.dumps(config), now()),
            )

    def update_analysis(self, analysis_id: str, **fields: Any) -> None:
        _update(self, "analyses", analysis_id, fields)

    def get_analysis(self, analysis_id: str) -> dict | None:
        return _get(self, "analyses", analysis_id)

    def find_reusable_analysis(self, log_id: str, config_hash: str) -> dict | None:
        """Eine fertige oder laufende Analyse mit gleicher Konfiguration, falls vorhanden."""
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM analyses WHERE log_id=? AND config_hash=? "
                "AND status IN ('pending', 'running', 'done') ORDER BY created_at DESC LIMIT 1",
                (log_id, config_hash),
            ).fetchone()
        return dict(row) if row else None


_ALLOWED = {
    "logs": {
        "status",
        "n_events",
        "n_cases",
        "n_activities",
        "has_resource",
        "dropped_rows",
        "content_hash",
        "size_bytes",
        "last_accessed",
        "ignored_lifecycle_events",
    },
    "analyses": {"status", "started_at", "finished_at", "error_message"},
}


def _update(db: Database, table: str, row_id: str, fields: dict[str, Any]) -> None:
    bad = set(fields) - _ALLOWED[table]
    if bad:
        raise ValueError(f"Unerlaubte Felder: {bad}")
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db.connect() as con:
        con.execute(f"UPDATE {table} SET {assignments} WHERE id=?", (*fields.values(), row_id))


def _get(db: Database, table: str, row_id: str) -> dict | None:
    with db.connect() as con:
        row = con.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    return dict(row) if row else None

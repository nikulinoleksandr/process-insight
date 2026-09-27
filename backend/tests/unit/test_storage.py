"""Speicher: Duplikate, Originaldateien, Aufbewahrung, Speichergrenze, Waisen."""

import io
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services.cleanup_service import CleanupService
from app.services.errors import BadInputError
from app.services.log_service import LogService
from app.storage.database import Database
from app.storage.files import FileStore
from tests.conftest import RUNNING_EXAMPLE

CSV = b"case;act;ts\n1;A;2024-01-01\n1;B;2024-01-02\n2;A;2024-01-01\n"


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "app.db")
    files = FileStore(tmp_path)
    logs = LogService(db, files, max_upload_mb=50, max_events=1_000_000)
    return db, files, logs


def upload(logs, name="log.xes", data=None):
    data = data if data is not None else RUNNING_EXAMPLE.read_bytes()
    record, _ = logs.create(name, io.BytesIO(data))
    return record


def cleanup(db, files, logs, days=7, mb=2000):
    return CleanupService(db, files, logs, retention_days=days, max_storage_mb=mb)


def test_original_is_deleted_after_import(store):
    db, files, logs = store
    record = upload(logs)
    assert files.find_original(record["id"]) is None
    assert files.events_path(record["id"]).exists()
    assert files.summary_path(record["id"]).exists()
    assert record["size_bytes"] > 0


def test_same_file_twice_is_stored_once(store):
    db, files, logs = store
    first = upload(logs, "a.xes")
    second = upload(logs, "kopie.xes")
    assert first["id"] == second["id"]
    assert len(db.list_logs()) == 1
    assert len(files.existing_log_ids()) == 1


def test_csv_original_kept_until_mapping(store):
    from app.core.importing.normalize import ColumnMapping

    db, files, logs = store
    record = upload(logs, "x.csv", CSV)
    assert files.find_original(record["id"]) is not None
    logs.apply_mapping(record["id"], ColumnMapping(case="case", activity="act", timestamp="ts"))
    assert files.find_original(record["id"]) is None


def test_expired_logs_are_deleted_but_demo_stays(store):
    db, files, logs = store
    old = upload(logs, "alt.xes")
    demo, _ = logs.create("demo.xes", io.BytesIO(RUNNING_EXAMPLE.read_bytes()), is_demo=True)
    long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    db.update_log(old["id"], last_accessed=long_ago)
    db.update_log(demo["id"], last_accessed=long_ago)

    report = cleanup(db, files, logs).run()
    assert report.deleted_logs == [old["id"]]
    assert db.get_log(demo["id"]) is not None
    assert old["id"] not in files.existing_log_ids()


def test_storage_limit_deletes_least_recently_used(store, tmp_path):
    db, files, logs = store
    a = upload(logs, "a.csv", CSV)
    b = upload(logs, "b.csv", CSV + b"3;A;2024-01-03\n")
    db.update_log(a["id"], last_accessed="2020-01-01T00:00:00+00:00")
    db.update_log(b["id"], last_accessed="2021-01-01T00:00:00+00:00")
    # Grenze so setzen, dass genau ein Log zu viel ist
    service = cleanup(db, files, logs, days=0, mb=0)
    service.max_bytes = files.total_size() - 1
    report = service.run()
    assert report.deleted_logs == [a["id"]]


def test_orphans_are_removed(store):
    db, files, logs = store
    orphan = files.log_dir("verwaist")
    (orphan / "events.parquet").write_bytes(b"x")
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    files.result_path("weg").write_text("{}")
    cleanup(db, files, logs).run()
    assert "verwaist" not in files.existing_log_ids()
    assert not files.result_path("weg").exists()


def test_fresh_upload_folder_is_not_treated_as_orphan(store):
    db, files, logs = store
    files.log_dir("wird-gerade-hochgeladen")
    cleanup(db, files, logs).run()
    assert "wird-gerade-hochgeladen" in files.existing_log_ids()


def test_duplicates_from_old_versions_are_merged(store):
    """Frühere Versionen haben Originale behalten und keine Fingerabdrücke gespeichert."""
    db, files, logs = store
    ids = []
    for name in ("a.xes", "b.xes"):
        record = upload(logs, name + ".tmp.xes", RUNNING_EXAMPLE.read_bytes() + name.encode())
        ids.append(record["id"])
        # Zustand wie in alter Version herstellen
        files.original_path(record["id"], ".xes").write_bytes(RUNNING_EXAMPLE.read_bytes())
        db.update_log(record["id"], content_hash=None)
    report = cleanup(db, files, logs).run()
    assert len(report.deleted_logs) == 1
    remaining = db.list_logs()
    assert len(remaining) == 1
    assert files.find_original(remaining[0]["id"]) is None


def test_failed_logs_are_removed(store):
    db, files, logs = store
    with pytest.raises(BadInputError):
        upload(logs, "kaputt.xes", b"<kein xml")
    cleanup(db, files, logs).run()
    assert db.list_logs() == []


def test_events_are_cached(store, monkeypatch):
    db, files, logs = store
    record = upload(logs)
    calls = []
    original = files.load_events
    monkeypatch.setattr(files, "load_events", lambda i: calls.append(i) or original(i))
    logs.events(record["id"])
    logs.events(record["id"])
    assert calls == [record["id"]]
    assert logs.derived(record["id"], "x", lambda ev: len(ev)) == 42

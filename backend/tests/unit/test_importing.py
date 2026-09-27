import pandas as pd
import pytest

from app.core.columns import ACTIVITY, CASE, TIMESTAMP
from app.core.importing.csv import read_csv, suggest_mapping
from app.core.importing.normalize import ColumnMapping, LogFormatError, normalize
from app.core.importing.xes import read_xes
from tests.conftest import RUNNING_EXAMPLE


def test_read_xes_running_example():
    result = read_xes(RUNNING_EXAMPLE)
    assert len(result.events) == 42
    assert result.events[CASE].nunique() == 6
    assert str(result.events[TIMESTAMP].dt.tz) == "UTC"


def test_normalize_drops_incomplete_rows_and_sorts():
    df = pd.DataFrame(
        {
            CASE: ["b", "a", "a", None],
            ACTIVITY: ["X", "B", "A", "Y"],
            TIMESTAMP: ["2024-01-02", "2024-01-03", "2024-01-01", "2024-01-01"],
        }
    )
    result = normalize(df)
    assert result.dropped_rows == 1
    assert list(result.events[ACTIVITY]) == ["A", "B", "X"]


def test_normalize_rejects_missing_columns():
    with pytest.raises(LogFormatError, match="Pflichtspalten"):
        normalize(pd.DataFrame({CASE: ["1"], ACTIVITY: ["A"]}))


def test_invalid_timestamps_are_dropped():
    df = pd.DataFrame({CASE: ["1", "1"], ACTIVITY: ["A", "B"], TIMESTAMP: ["2024-01-01", "kaputt"]})
    assert normalize(df).dropped_rows == 1


def test_suggest_mapping_recognises_common_names():
    suggestion = suggest_mapping(["Case ID", "Activity", "Timestamp", "User", "Betrag"])
    assert suggestion == {
        "case": None,
        "activity": "Activity",
        "timestamp": "Timestamp",
        "resource": "User",
    }
    assert suggest_mapping(["case_id", "Aktivität", "Zeit"])["case"] == "case_id"


def test_read_csv_with_semicolon_and_mapping(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("fall;schritt;wann\n1;A;2024-01-01 10:00\n1;B;2024-01-01 12:00\n")
    mapping = ColumnMapping(case="fall", activity="schritt", timestamp="wann")
    events = read_csv(path, mapping).events
    assert list(events.columns[:3]) == [CASE, ACTIVITY, TIMESTAMP]
    assert len(events) == 2


def test_mapping_with_unknown_column_fails(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("a,b,c\n1,A,2024-01-01\n")
    with pytest.raises(LogFormatError, match="nicht in der Datei"):
        read_csv(path, ColumnMapping(case="a", activity="b", timestamp="zeit"))


def test_lifecycle_keeps_only_complete_events():
    df = pd.DataFrame(
        {
            CASE: ["1"] * 4,
            ACTIVITY: ["A", "A", "B", "B"],
            TIMESTAMP: [
                "2024-01-01 10:00",
                "2024-01-01 11:00",
                "2024-01-01 12:00",
                "2024-01-01 13:00",
            ],
            "lifecycle:transition": ["start", "complete", "START", "COMPLETE"],
        }
    )
    result = normalize(df)
    assert list(result.events[ACTIVITY]) == ["A", "B"]
    assert result.ignored_lifecycle_events == 2


def test_lifecycle_column_in_csv_is_detected(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text(
        "id,step,time,lifecycle\n1,A,2024-01-01 10:00,start\n1,A,2024-01-01 11:00,complete\n"
    )
    events = read_csv(path, ColumnMapping(case="id", activity="step", timestamp="time")).events
    assert len(events) == 1


def test_xes_with_doctype_is_rejected(tmp_path):
    path = tmp_path / "evil.xes"
    path.write_text(
        '<?xml version="1.0"?><!DOCTYPE log [<!ENTITY x SYSTEM "file:///etc/passwd">]><log/>'
    )
    with pytest.raises(LogFormatError, match="DOCTYPE"):
        read_xes(path)

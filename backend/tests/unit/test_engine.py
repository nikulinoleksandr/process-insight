import pytest

from app.core.insights.base import Detector
from app.core.insights.detectors.rework import ReworkConfig
from app.core.insights.engine import InvalidConfigError, run_analysis, validate_config
from app.core.insights.registry import DETECTORS
from tests.conftest import make_log


class BrokenDetector(Detector):
    id = "broken"
    name = "Kaputt"
    category = "quality"
    required_columns = {"case:concept:name"}
    config_model = ReworkConfig

    def detect(self, log, config):
        raise RuntimeError("Absicht")


def test_all_detectors_run_on_log_without_resource():
    log = make_log([("1", "A", 0), ("1", "A", 1), ("2", "A", 0)])
    result = run_analysis(log)
    runs = {r.detector_id: r.status for r in result.detector_runs}
    assert runs["segregation_of_duties"] == "not_applicable"
    assert runs["rework"] == "ok"
    assert len(result.detector_runs) == len(DETECTORS)


def test_broken_detector_does_not_stop_analysis():
    log = make_log([("1", "A", 0), ("1", "A", 1)])
    detectors = [BrokenDetector(), DETECTORS[0]]
    result = run_analysis(log, detectors=detectors)
    statuses = [r.status for r in result.detector_runs]
    assert statuses == ["failed", "ok"]
    assert result.insights  # Nacharbeit wurde trotzdem gefunden


def test_insights_sorted_by_severity():
    log = make_log([("1", "A", 0), ("1", "A", 1), ("1", "B", 30), ("2", "A", 0), ("2", "B", 1)])
    order = {"high": 0, "medium": 1, "low": 2}
    ranks = [order[i.severity] for i in run_analysis(log).insights]
    assert ranks == sorted(ranks)


def test_invalid_config_is_rejected():
    with pytest.raises(InvalidConfigError):
        validate_config({"sla": {"max_days": -1}})
    with pytest.raises(InvalidConfigError):
        validate_config({"gibts_nicht": {}})

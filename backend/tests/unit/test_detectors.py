import pandas as pd
import pytest

from app.core.insights.base import NotApplicable
from app.core.insights.detectors.bottleneck import BottleneckConfig, BottleneckDetector
from app.core.insights.detectors.rare_variants import RareVariantsConfig, RareVariantsDetector
from app.core.insights.detectors.rework import ReworkConfig, ReworkDetector
from app.core.insights.detectors.segregation_of_duties import (
    SegregationConfig,
    SegregationOfDutiesDetector,
)
from app.core.insights.detectors.sla import SlaConfig, SlaDetector
from tests.conftest import make_log

# --- Nacharbeit ---------------------------------------------------------------


def test_rework_finds_repeated_activity():
    log = make_log(
        [
            ("1", "A", 0), ("1", "B", 1), ("1", "B", 2), ("1", "B", 3),
            ("2", "A", 0), ("2", "B", 1),
        ]
    )  # fmt: skip
    [insight] = ReworkDetector().detect(log, ReworkConfig())
    assert insight.evidence == {"activity": "B"}
    assert insight.affected_case_ids == ["1"]
    assert insight.affected_case_share == 0.5
    assert insight.metrics["extra_executions"] == 2
    assert insight.severity == "high"


def test_rework_ignores_clean_log():
    log = make_log([("1", "A", 0), ("1", "B", 1)])
    assert ReworkDetector().detect(log, ReworkConfig()) == []


def test_rework_on_running_example_matches_manual_count():
    from app.core.importing.xes import read_xes
    from tests.conftest import RUNNING_EXAMPLE

    log = read_xes(RUNNING_EXAMPLE).events
    by_activity = {
        i.evidence["activity"]: i.affected_case_ids
        for i in ReworkDetector().detect(log, ReworkConfig())
    }
    assert by_activity["check ticket"] == ["3", "5"]
    assert by_activity["reinitiate request"] == ["5"]


# --- Engpässe -----------------------------------------------------------------


def test_bottleneck_ranks_longest_waiting_transition_first():
    log = make_log(
        [
            ("1", "A", 0), ("1", "B", 1), ("1", "C", 11),
            ("2", "A", 0), ("2", "B", 1), ("2", "C", 9),
        ]
    )  # fmt: skip
    insights = BottleneckDetector().detect(log, BottleneckConfig())
    assert insights[0].evidence == {"source": "B", "target": "C"}
    assert insights[0].metrics["median_wait_seconds"] == 9 * 86400
    assert insights[0].severity == "high"


def test_bottleneck_respects_top_n():
    log = make_log([("1", "A", 0), ("1", "B", 1), ("1", "C", 3), ("1", "D", 6)])
    assert len(BottleneckDetector().detect(log, BottleneckConfig(top_n=2))) == 2


# --- Durchlaufzeiten ----------------------------------------------------------


def _durations_log(days_per_case: list[float]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(days_per_case):
        rows += [(str(i), "A", 0), (str(i), "B", d)]
    return make_log(rows)


def test_sla_fixed_threshold():
    log = _durations_log([1, 2, 3, 20])
    [insight] = SlaDetector().detect(log, SlaConfig(max_days=10))
    assert insight.affected_case_ids == ["3"]
    assert insight.affected_case_share == 0.25
    assert insight.severity == "high"


def test_sla_nothing_over_threshold():
    assert SlaDetector().detect(_durations_log([1, 2]), SlaConfig(max_days=10)) == []


def test_sla_percentile_mode_rates_by_ratio_to_median():
    log = _durations_log([1] * 9 + [30])
    [insight] = SlaDetector().detect(log, SlaConfig(percentile=0.8))
    assert insight.affected_case_ids == ["9"]
    assert insight.severity == "high"


def test_sla_config_validation():
    with pytest.raises(ValueError):
        SlaConfig(high_ratio=1.2, medium_ratio=2)


# --- Vier-Augen-Prinzip -------------------------------------------------------


def test_segregation_finds_same_person():
    log = make_log(
        [
            ("1", "Bestellen", 0, "Anna"), ("1", "Freigeben", 1, "Anna"),
            ("2", "Bestellen", 0, "Anna"), ("2", "Freigeben", 1, "Ben"),
        ]
    )  # fmt: skip
    config = SegregationConfig(pairs=[{"first": "Bestellen", "second": "Freigeben"}])
    [insight] = SegregationOfDutiesDetector().detect(log, config)
    assert insight.affected_case_ids == ["1"]
    assert insight.category == "compliance"


def test_segregation_without_pairs_is_not_applicable():
    log = make_log([("1", "A", 0, "Anna")])
    with pytest.raises(NotApplicable):
        SegregationOfDutiesDetector().detect(log, SegregationConfig())


# --- Seltene Varianten --------------------------------------------------------


def test_rare_variants():
    rows = []
    for i in range(18):
        rows += [(str(i), "A", 0), (str(i), "B", 1)]
    rows += [("x", "A", 0), ("x", "C", 1), ("y", "C", 0)]
    config = RareVariantsConfig(max_variant_share=0.1)
    [insight] = RareVariantsDetector().detect(make_log(rows), config)
    assert insight.affected_case_ids == ["x", "y"]
    assert insight.metrics["rare_variant_count"] == 2

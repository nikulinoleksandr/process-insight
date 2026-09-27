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
    rows = [("1", "A", 0), ("1", "B", 1), ("1", "B", 2), ("1", "B", 3)]
    for case in "234":
        rows += [(case, "A", 0), (case, "B", 1)]
    [insight] = ReworkDetector().detect(make_log(rows), ReworkConfig())
    assert insight.evidence == {"activity": "B", "activities": ["B"], "kind": "rework"}
    assert insight.affected_case_ids == ["1"]
    assert insight.affected_case_share == 0.25
    assert insight.metrics["extra_executions"] == 2
    assert insight.severity == "high"


def test_rework_treats_almost_always_repeated_step_as_routine():
    # Wie Laborwerte: In fast jedem Fall wird "Messen" mehrmals gemacht.
    rows = []
    for case in "1234":
        rows += [(case, "Aufnahme", 0), (case, "Messen", 1), (case, "Messen", 2)]
    rows += [("5", "Aufnahme", 0), ("5", "Messen", 1)]
    config = ReworkConfig(routine_min_cases=5)
    [insight] = ReworkDetector().detect(make_log(rows), config)
    assert insight.evidence["kind"] == "routine"
    assert insight.severity == "low"
    assert insight.metrics["repeat_rate"] == 0.8


def test_rework_ignores_configured_routine_activities():
    rows = [("1", "A", 0), ("1", "Zahlung", 1), ("1", "Zahlung", 2)]
    rows += [(c, "A", 0) for c in "234"]
    config = ReworkConfig(routine_activities=["Zahlung"])
    assert ReworkDetector().detect(make_log(rows), config) == []


def test_rework_ignores_clean_log():
    log = make_log([("1", "A", 0), ("1", "B", 1)])
    assert ReworkDetector().detect(log, ReworkConfig()) == []


def test_rework_on_running_example_matches_manual_count():
    from app.core.importing.xes import read_xes
    from tests.conftest import RUNNING_EXAMPLE

    log = read_xes(RUNNING_EXAMPLE).events
    by_activities = {
        tuple(i.evidence["activities"]): i.affected_case_ids
        for i in ReworkDetector().detect(log, ReworkConfig())
    }
    # "check ticket" und "decide" wiederholen sich in genau denselben Fällen -> ein Befund
    assert by_activities[("check ticket", "decide")] == ["3", "5"]
    assert by_activities[("examine casually", "reinitiate request")] == ["5"]


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
    assert insight.severity == "medium"


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


def test_rework_merges_steps_repeated_in_the_same_cases():
    rows = []
    for case in "12":
        rows += [(case, "Angebot erstellen", 0), (case, "Angebot senden", 1)]
        rows += [(case, "Angebot erstellen", 2), (case, "Angebot senden", 3)]
    rows += [(c, "Angebot erstellen", 0) for c in "3456789"]
    [insight] = ReworkDetector().detect(make_log(rows), ReworkConfig())
    assert insight.evidence["activities"] == ["Angebot erstellen", "Angebot senden"]
    assert insight.title == "Nacharbeit bei „Angebot erstellen“ und „Angebot senden“"
    assert insight.metrics["extra_executions"] == 4


def test_bottleneck_ignores_self_loops_and_near_zero_waits():
    rows = []
    for i in range(10):
        c = str(i)
        rows += [(c, "Messen", 0), (c, "Messen", 5)]  # Wiederholung, kein Übergang
        rows += [(c, "A", 6), (c, "B", 6 + 0.00001)]  # praktisch keine Wartezeit
        rows += [(c, "C", 20)]
    insights = BottleneckDetector().detect(make_log(rows), BottleneckConfig())
    pairs = [(i.evidence["source"], i.evidence["target"]) for i in insights]
    assert ("Messen", "Messen") not in pairs
    assert ("A", "B") not in pairs
    assert ("B", "C") in pairs


def test_bottleneck_respects_ignored_transitions():
    rows = []
    for i in range(10):
        rows += [(str(i), "A", 0), (str(i), "B", 30), (str(i), "C", 31)]
    config = BottleneckConfig(ignore_transitions=[["A", "B"]])
    pairs = [
        (i.evidence["source"], i.evidence["target"])
        for i in BottleneckDetector().detect(make_log(rows), config)
    ]
    assert ("A", "B") not in pairs


def test_rare_variants_reports_missing_standard_instead_of_alarm():
    # Jeder Fall verläuft anders: kein Standard, also kein Alarm.
    rows = []
    for i in range(30):
        rows += [(str(i), "Start", 0)] + [(str(i), f"Schritt {j}", j + 1) for j in range(i % 7)]
        rows += [(str(i), f"Ende {i}", 10)]
    [insight] = RareVariantsDetector().detect(make_log(rows), RareVariantsConfig())
    assert insight.evidence["kind"] == "no_standard"
    assert insight.severity == "low"


def test_sla_without_deadline_is_never_high():
    log = _durations_log([1] * 9 + [300])
    [insight] = SlaDetector().detect(log, SlaConfig(percentile=0.8))
    assert insight.severity == "medium"
    assert SlaDetector().detect(_durations_log([10, 10, 11, 12, 12]), SlaConfig()) == []


def test_rework_small_samples_are_not_called_routine():
    rows = [("1", "A", 0), ("1", "B", 1), ("1", "B", 2), ("2", "B", 0)]
    [insight] = ReworkDetector().detect(make_log(rows), ReworkConfig())
    assert insight.evidence["kind"] == "rework"

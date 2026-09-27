import json

from app.core.importing.xes import read_xes
from app.core.insights.engine import run_analysis
from app.llm.checks import unverified_numbers
from app.llm.payload import build_payload
from app.llm.prompts import build_user_prompt
from app.llm.schemas import Explanation
from tests.conftest import RUNNING_EXAMPLE, make_log


def _analysis():
    return run_analysis(read_xes(RUNNING_EXAMPLE).events)


def test_payload_contains_no_case_ids_or_people():
    log = make_log(
        [
            ("case-4711", "Bestellen", 0, "Anna Muster"),
            ("case-4711", "Freigeben", 1, "Anna Muster"),
            ("case-4712", "Bestellen", 0, "Ben"), ("case-4712", "Freigeben", 1, "Ben"),
        ]
    )  # fmt: skip
    config = {"segregation_of_duties": {"pairs": [{"first": "Bestellen", "second": "Freigeben"}]}}
    result = run_analysis(log, config)
    insight = next(i for i in result.insights if i.detector_id == "segregation_of_duties")
    text = json.dumps(build_payload(insight, result.log_summary), ensure_ascii=False)
    assert "case-4711" not in text
    assert "Anna" not in text and "Ben" not in text
    assert "Bestellen" in text


def test_payload_formats_metrics_readably():
    result = _analysis()
    insight = next(i for i in result.insights if i.detector_id == "bottleneck")
    metrics = build_payload(insight, result.log_summary)["befund"]["kennzahlen"]
    assert metrics["Wartezeit (Median)"].endswith("Tage")
    assert metrics["Anteil an der gesamten Wartezeit"].endswith("%")


def test_prompt_wraps_data_as_data():
    result = _analysis()
    prompt = build_user_prompt(build_payload(result.insights[0], result.log_summary))
    assert "<daten>" in prompt and "</daten>" in prompt


def _explanation(text: str) -> Explanation:
    return Explanation(headline="x", explanation=text, possible_causes=[], next_steps=[])


def test_number_check_accepts_measured_and_rounded_numbers():
    payload = {"kennzahlen": {"Anteil": "26,6 %", "Fälle": "1.234"}}
    ok = _explanation("Etwa 27 % bzw. 26,6 % der 1.234 Fälle, in 3 Schritten.")
    assert unverified_numbers(ok, payload) == []


def test_number_check_flags_invented_numbers():
    payload = {"kennzahlen": {"Anteil": "26,6 %"}}
    bad = _explanation("Das kostet jährlich 50.000 Euro und 45 % der Zeit.")
    assert unverified_numbers(bad, payload) == ["50.000", "45"]


def test_empty_api_key_means_no_ai(tmp_path):
    from app.config import Settings
    from app.main import build_explainer

    assert build_explainer(Settings(storage_dir=tmp_path, anthropic_api_key="  ")) is None
    assert build_explainer(Settings(storage_dir=tmp_path, anthropic_api_key=None)) is None
    explainer = build_explainer(Settings(storage_dir=tmp_path, anthropic_api_key="sk-test"))
    assert explainer is not None and explainer.model == "claude-haiku-4-5-20251001"

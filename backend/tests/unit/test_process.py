from app.core.importing.xes import read_xes
from app.core.process.models import render_model
from app.core.process.process_map import END, START, build_process_map
from app.core.process.stats import case_durations, summarize
from app.core.process.variants import top_variants
from tests.conftest import RUNNING_EXAMPLE, make_log


def edge_counts(pm):
    return {(e.source, e.target): e.count for e in pm.edges}


def test_process_map_counts_match_pm4py_on_running_example():
    import pm4py

    log = read_xes(RUNNING_EXAMPLE).events
    expected, starts, ends = pm4py.discover_dfg(log)
    counts = edge_counts(build_process_map(log))
    for (a, b), n in expected.items():
        assert counts[(a, b)] == n
    for a, n in starts.items():
        assert counts[(START, a)] == n
    for a, n in ends.items():
        assert counts[(a, END)] == n


def test_process_map_waiting_time_is_median():
    log = make_log([("1", "A", 0), ("1", "B", 1), ("2", "A", 0), ("2", "B", 3)])
    edge = next(e for e in build_process_map(log).edges if e.source == "A")
    assert edge.median_wait_seconds == 2 * 86400


def test_process_map_detail_hides_rare_paths_but_keeps_nodes_connected():
    rows = []
    for i in range(9):
        rows += [(str(i), "A", 0), (str(i), "B", 1)]
    rows += [("x", "A", 0), ("x", "C", 1)]
    pm = build_process_map(make_log(rows), detail=0.5)
    assert ("A", "C") not in edge_counts(pm)
    node_ids = {n.id for n in pm.nodes}
    for e in pm.edges:
        assert e.source in node_ids and e.target in node_ids


def test_summary_and_durations():
    log = make_log([("1", "A", 0), ("1", "B", 2), ("2", "A", 0), ("2", "B", 4)])
    summary = summarize(log)
    assert summary.n_cases == 2
    assert summary.n_variants == 1
    assert summary.case_duration.median == 3 * 86400
    assert list(case_durations(log).dt.days) == [2, 4]


def test_top_variants_sorted_by_frequency():
    log = make_log([("1", "A", 0), ("1", "B", 1), ("2", "A", 0), ("2", "B", 1), ("3", "B", 0)])
    variants = top_variants(log)
    assert variants[0].activities == ["A", "B"]
    assert variants[0].case_count == 2


def test_activity_counts_and_cases():
    """Wie oft eine Aktivität vorkommt und in wie vielen Fällen - das sind zwei Zahlen."""
    log = make_log([("1", "A", 0), ("1", "A", 1), ("1", "B", 2), ("2", "A", 0)])
    summary = summarize(log)
    assert summary.activity_counts == {"A": 3, "B": 1}
    assert summary.activity_cases == {"A": 2, "B": 1}


def test_render_model_returns_svg():
    log = read_xes(RUNNING_EXAMPLE).events
    for kind in ("bpmn", "petri"):
        svg = render_model(log, kind)
        assert "<svg" in svg
        assert "register request" in svg


def test_render_model_uses_project_colours():
    """Die Modelle sollen aussehen wie die Prozesslandkarte, nicht wie Graphviz-Standard."""
    log = read_xes(RUNNING_EXAMPLE).events
    for kind in ("bpmn", "petri"):
        svg = render_model(log, kind)
        assert "#eef2ff" in svg  # Aktivitäten in der Farbe der Landkarte
        assert "#94a3b8" in svg  # Kanten
        assert "Segoe UI" in svg
        assert 'fill="white"' not in svg  # keine Vorgabefarbe von pm4py mehr
        assert "Times" not in svg


def test_process_map_max_edges_keeps_the_most_frequent():
    """Die feste Obergrenze ist die wirksame Bremse bei dichten Logs."""
    rows = [("1", "A", 0), ("1", "B", 1), ("1", "C", 2), ("1", "D", 3)]
    rows += [(str(i), "A", 0) for i in range(2, 12)]
    rows += [(str(i), "B", 1) for i in range(2, 12)]
    full = build_process_map(make_log(rows))
    limited = build_process_map(make_log(rows), max_edges=2)
    assert len(limited.edges) == 2
    assert limited.total_edges == full.total_edges  # Gesamtzahl bleibt sichtbar
    strongest = max(e.count for e in full.edges)
    assert limited.edges[0].count == strongest
    # Knoten richten sich nach den übrigen Kanten
    assert set(n.id for n in limited.nodes) >= {START, END}


def test_process_map_focus_keeps_rare_edge_and_node():
    rows = []
    for i in range(20):
        rows += [(str(i), "A", 0), (str(i), "B", 1)]
    rows += [("x", "A", 0), ("x", "C", 1), ("x", "D", 2)]
    log = make_log(rows)
    limited = build_process_map(log, max_edges=3)
    assert ("C", "D") not in edge_counts(limited)

    focused = build_process_map(log, max_edges=3, focus_edges={("C", "D")}, focus_nodes={"C"})
    counts = edge_counts(focused)
    assert counts[("C", "D")] == 1
    assert ("A", "C") in counts  # stärkste eingehende Kante von C
    assert {"C", "D"} <= {n.id for n in focused.nodes}

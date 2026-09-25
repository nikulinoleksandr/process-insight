from tests.conftest import RUNNING_EXAMPLE


def upload(client, name, content):
    return client.post("/api/logs", files={"file": (name, content)})


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_demo_log_is_created_on_startup(client):
    demo = client.get("/api/demo").json()
    assert demo["status"] == "ready"
    assert demo["n_cases"] == 6
    assert demo["is_demo"] is True


def test_full_flow_with_xes(client):
    response = upload(client, "example.xes", RUNNING_EXAMPLE.read_bytes())
    assert response.status_code == 201
    log = response.json()
    assert log["status"] == "ready"
    assert log["n_events"] == 42

    pm = client.get(f"/api/logs/{log['id']}/process-map").json()
    assert any(e["source"] == "check ticket" and e["target"] == "decide" for e in pm["edges"])

    started = client.post(f"/api/logs/{log['id']}/analyses", json={})
    assert started.status_code == 202
    analysis = client.get(f"/api/analyses/{started.json()['id']}").json()
    assert analysis["status"] == "done"
    titles = [i["title"] for i in analysis["result"]["insights"]]
    assert "Nacharbeit bei „check ticket“" in titles

    insight = next(i for i in analysis["result"]["insights"] if i["detector_id"] == "rework")
    cases = client.get(
        f"/api/analyses/{analysis['id']}/insights/{insight['id']}/cases", params={"limit": 1}
    ).json()
    assert cases["total"] == insight["affected_case_count"]
    assert len(cases["cases"]) == 1


def test_same_config_reuses_analysis(client):
    log_id = client.get("/api/demo").json()["id"]
    first = client.post(f"/api/logs/{log_id}/analyses", json={"config": {}}).json()
    second = client.post(f"/api/logs/{log_id}/analyses").json()
    third = client.post(
        f"/api/logs/{log_id}/analyses", json={"config": {"sla": {"max_days": 5}}}
    ).json()
    assert first["id"] == second["id"]
    assert third["id"] != first["id"]


def test_csv_flow_needs_mapping(client):
    csv = b"order;step;when;who\n1;A;2024-01-01;Anna\n1;B;2024-01-02;Ben\n"
    log = upload(client, "orders.csv", csv).json()
    assert log["status"] == "needs_mapping"
    assert log["csv_preview"]["columns"] == ["order", "step", "when", "who"]

    blocked = client.post(f"/api/logs/{log['id']}/analyses")
    assert blocked.status_code == 409

    mapped = client.post(
        f"/api/logs/{log['id']}/mapping",
        json={"case": "order", "activity": "step", "timestamp": "when", "resource": "who"},
    ).json()
    assert mapped["status"] == "ready"
    assert mapped["has_resource"] is True


def test_bad_mapping_keeps_log_retryable(client):
    log = upload(client, "x.csv", b"a,b,c\n1,A,2024-01-01\n").json()
    bad = client.post(
        f"/api/logs/{log['id']}/mapping", json={"case": "a", "activity": "b", "timestamp": "z"}
    )
    assert bad.status_code == 422
    assert client.get(f"/api/logs/{log['id']}").json()["status"] == "needs_mapping"


def test_errors(client):
    assert upload(client, "bild.png", b"123").status_code == 422
    assert upload(client, "kaputt.xes", b"<kein xml").status_code == 422
    assert client.get("/api/logs/gibts-nicht").status_code == 404
    log_id = client.get("/api/demo").json()["id"]
    bad = client.post(f"/api/logs/{log_id}/analyses", json={"config": {"sla": {"max_days": 0}}})
    assert bad.status_code == 422


def test_upload_limit(small_upload_client):
    assert upload(small_upload_client, "a.xes", b"x" * 10).status_code == 413


def test_detectors_endpoint(client):
    ids = [d["id"] for d in client.get("/api/detectors").json()]
    assert ids == ["rework", "bottleneck", "sla", "segregation_of_duties", "rare_variants"]


def test_process_map_detail_parameter(client):
    """Der Detailgrad-Regler der Oberflaeche blendet seltene Pfade aus."""
    log_id = client.get("/api/demo").json()["id"]
    full = client.get(f"/api/logs/{log_id}/process-map").json()
    reduced = client.get(f"/api/logs/{log_id}/process-map", params={"detail": 0.5}).json()
    assert len(reduced["edges"]) < len(full["edges"])
    assert reduced["total_edges"] == full["total_edges"]
    assert client.get(f"/api/logs/{log_id}/process-map", params={"detail": 2}).status_code == 422


def test_veraltetes_ergebnis_wird_neu_gerechnet(client, tmp_path):
    """Ein gespeichertes Ergebnis aus einer älteren Schema-Version darf nicht abstürzen.

    Passiert, sobald LogSummary oder Insight ein Pflichtfeld dazubekommen: Die JSON-Datei
    auf der Platte kennt es nicht. Statt HTTP 500 soll die Analyse neu laufen.
    """
    import json
    from pathlib import Path

    log_id = client.get("/api/demo").json()["id"]
    first = client.post(f"/api/logs/{log_id}/analyses", json={"config": {}}).json()
    assert client.get(f"/api/analyses/{first['id']}").json()["status"] == "done"

    # Ergebnisdatei so verfälschen, wie es eine Schema-Erweiterung tun würde
    result_file = next(Path(tmp_path).rglob(f"{first['id']}.json"))
    stored = json.loads(result_file.read_text(encoding="utf-8"))
    del stored["log_summary"]["activity_cases"]
    result_file.write_text(json.dumps(stored), encoding="utf-8")

    again = client.post(f"/api/logs/{log_id}/analyses", json={"config": {}})
    assert again.status_code == 202
    final = client.get(f"/api/analyses/{again.json()['id']}").json()
    assert final["status"] == "done"
    assert final["result"]["log_summary"]["activity_cases"]


def test_model_endpoint_liefert_svg(client):
    """Der Umschalter der Oberfläche holt BPMN und Petri-Netz als fertiges Bild."""
    log_id = client.get("/api/demo").json()["id"]
    for kind in ("bpmn", "petri"):
        response = client.get(f"/api/logs/{log_id}/model/{kind}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in response.text
    assert client.get(f"/api/logs/{log_id}/model/quatsch").status_code == 422


def test_startseite_liefert_oberflaeche(client):
    """Unter "/" kommt die Oberflaeche, die API bleibt unter "/api" erreichbar."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Process Insight" in response.text
    assert client.get("/api/health").status_code == 200

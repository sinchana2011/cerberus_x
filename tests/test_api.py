"""Integration tests for the CERBERUS-X FastAPI REST endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import BackendSettings
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _make_client(tmp_path: Path) -> TestClient:
    settings = BackendSettings(
        db_path=tmp_path / "api_test.db",
        upload_dir=tmp_path / "uploads",
    )
    return TestClient(create_app(settings))


def _upload_demo_bundle(client: TestClient) -> str:
    demo_dir = ROOT / "demo_data"
    filenames = [
        "case1_quantity_conflict.csv",
        "case2_order_vs_dispatch.txt",
        "case3_leadership.txt",
        "case4_hidden_instruction.pdf",
        "case5_timeline.txt",
    ]
    files = [
        ("files", (name, (demo_dir / name).read_bytes(), "application/octet-stream"))
        for name in filenames
    ]
    resp = client.post("/api/upload", files=files)
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["analysis_id"].startswith("anl_")
    assert payload["counts"]["documents"] == 5
    return payload["analysis_id"]


def test_health_and_cors_for_vite_origin(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    preflight = client.options(
        "/api/upload",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_list_analyses_returns_sqlite_history_and_aggregates(tmp_path):
    client = _make_client(tmp_path)

    empty = client.get("/api/analyses")
    assert empty.status_code == 200
    assert empty.json()["total_investigations"] == 0
    assert empty.json()["aggregate_counts"]["documents"] == 0

    first_id = _upload_demo_bundle(client)
    single_csv = (ROOT / "demo_data" / "case1_quantity_conflict.csv").read_bytes()
    second = client.post(
        "/api/upload",
        files=[("files", ("case1_quantity_conflict.csv", single_csv, "text/csv"))],
    )
    assert second.status_code == 201
    second_id = second.json()["analysis_id"]

    listed = client.get("/api/analyses")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total_investigations"] == 2
    assert body["aggregate_counts"]["documents"] == 6
    returned_ids = {item["analysis_id"] for item in body["investigations"]}
    assert returned_ids == {first_id, second_id}


def test_upload_validation_rejects_empty_and_unsupported_files(tmp_path):
    client = _make_client(tmp_path)

    empty_resp = client.post(
        "/api/upload",
        files=[("files", ("empty.txt", b"", "text/plain"))],
    )
    assert empty_resp.status_code == 400

    bad_ext = client.post(
        "/api/upload",
        files=[("files", ("archive.docx", b"PK\x03\x04", "application/octet-stream"))],
    )
    assert bad_ext.status_code == 400


def test_all_analysis_endpoints_end_to_end(tmp_path):
    client = _make_client(tmp_path)
    analysis_id = _upload_demo_bundle(client)

    # 1. GET /api/analysis/{analysis_id}
    detail = client.get(f"/api/analysis/{analysis_id}")
    assert detail.status_code == 200
    detail_json = detail.json()
    assert detail_json["analysis_id"] == analysis_id
    assert detail_json["counts"]["documents"] == 5
    assert len(detail_json["entities"]) >= 4
    assert len(detail_json["claims"]) >= 8

    # 2. GET /api/analysis/{analysis_id}/graph (React Flow structure)
    graph = client.get(f"/api/analysis/{analysis_id}/graph")
    assert graph.status_code == 200
    graph_json = graph.json()
    assert graph_json["statistics"]["documents"] == 5
    assert len(graph_json["nodes"]) == graph_json["statistics"]["nodes"]
    assert len(graph_json["edges"]) == graph_json["statistics"]["edges"]
    sample_node = graph_json["nodes"][0]
    assert {"id", "type", "position", "data"}.issubset(sample_node.keys())
    assert {"x", "y"}.issubset(sample_node["position"].keys())

    # 3. GET /api/analysis/{analysis_id}/conflicts
    conflicts = client.get(f"/api/analysis/{analysis_id}/conflicts")
    assert conflicts.status_code == 200
    conf_json = conflicts.json()
    assert conf_json["total"] >= 4
    assert conf_json["real_problem_count"] >= 3
    real_only = client.get(
        f"/api/analysis/{analysis_id}/conflicts",
        params={"only_real_problems": "true"},
    )
    assert real_only.status_code == 200
    assert all(c["is_real_problem"] for c in real_only.json()["conflicts"])

    # 4. GET /api/analysis/{analysis_id}/digital-twin
    twin = client.get(f"/api/analysis/{analysis_id}/digital-twin")
    assert twin.status_code == 200
    twin_json = twin.json()
    assert twin_json["summary"]["total_states"] > 0
    assert len(twin_json["entities"]) >= 4
    first_eid = twin_json["entities"][0]["entity_id"]
    twin_filtered = client.get(
        f"/api/analysis/{analysis_id}/digital-twin",
        params={"entity_id": first_eid},
    )
    assert twin_filtered.status_code == 200
    assert all(s["entity_id"] == first_eid for s in twin_filtered.json()["states"])

    # 5. POST /api/analysis/{analysis_id}/ask
    ask_conf = client.post(
        f"/api/analysis/{analysis_id}/ask",
        json={"question": "How many units of Shipment SH-1042 were dispatched?"},
    )
    assert ask_conf.status_code == 200
    ask_json = ask_conf.json()
    assert ask_json["status"] == "conflicting"
    assert "85" in ask_json["answer_text"] and "100" in ask_json["answer_text"]
    assert len(ask_json["citations"]) >= 1

    ask_blank = client.post(
        f"/api/analysis/{analysis_id}/ask",
        json={"question": "   "},
    )
    assert ask_blank.status_code == 422

    # 6. GET /api/analysis/{analysis_id}/forensics
    forensics = client.get(f"/api/analysis/{analysis_id}/forensics")
    assert forensics.status_code == 200
    for_json = forensics.json()
    assert for_json["total_documents"] == 5
    assert for_json["suspicious_documents"] == 1
    assert for_json["total_flags"] >= 2
    pdf_doc = next(
        d for d in for_json["documents"] if d["filename"] == "case4_hidden_instruction.pdf"
    )
    assert pdf_doc["is_suspicious"] is True
    assert pdf_doc["reliability"] < 0.5


def test_not_found_returns_404_across_endpoints(tmp_path):
    client = _make_client(tmp_path)
    missing = "anl_does_not_exist"
    assert client.get(f"/api/analysis/{missing}").status_code == 404
    assert client.get(f"/api/analysis/{missing}/graph").status_code == 404
    assert client.get(f"/api/analysis/{missing}/conflicts").status_code == 404
    assert client.get(f"/api/analysis/{missing}/digital-twin").status_code == 404
    assert client.get(f"/api/analysis/{missing}/forensics").status_code == 404
    assert (
        client.post(f"/api/analysis/{missing}/ask", json={"question": "Who is CEO?"}).status_code
        == 404
    )
    assert client.post(f"/api/analysis/{missing}/brief").status_code == 404
    assert client.delete(f"/api/analysis/{missing}").status_code == 404


def test_demo_endpoint_delete_and_ollama_fallback_and_synthesis(tmp_path, monkeypatch):
    import core.llm as llm_mod

    monkeypatch.setattr(
        llm_mod,
        "ollama_status",
        lambda **_: llm_mod.OllamaStatus(
            available=False,
            base_url="http://127.0.0.1:11434",
            model="llama3.2:3b",
            model_installed=False,
            models=[],
            message="Ollama daemon offline in test",
        ),
    )

    client = _make_client(tmp_path)
    health = client.get("/api/health").json()
    assert health["ollama_available"] is False
    assert health["ollama_model"] == "llama3.2:3b"
    assert ".pdf" in health["supported_extensions"]

    demo_resp = client.post("/api/demo")
    assert demo_resp.status_code == 201, demo_resp.text
    analysis_id = demo_resp.json()["analysis_id"]
    assert demo_resp.json()["counts"]["documents"] >= 5

    # Ask with use_llm=True while Ollama is offline -> deterministic fallback
    monkeypatch.setattr(
        llm_mod,
        "_call_ollama_generate",
        lambda *a, **kw: (None, "Ollama offline; using deterministic reasoning."),
    )
    ask_offline = client.post(
        f"/api/analysis/{analysis_id}/ask",
        json={"question": "Who is the CEO of Northwind Logistics?", "use_llm": True},
    )
    assert ask_offline.status_code == 200
    body_off = ask_offline.json()
    assert body_off["used_llm"] is False
    assert "Priya Nair" in body_off["answer_text"]
    assert any("deterministic" in n.lower() for n in body_off["notes"])

    # Ask with use_llm=True while Ollama is online
    monkeypatch.setattr(
        llm_mod,
        "_call_ollama_generate",
        lambda *a, **kw: ("Priya Nair is the latest recorded CEO of Northwind Logistics (case3_leadership.txt).", None),
    )
    ask_online = client.post(
        f"/api/analysis/{analysis_id}/ask",
        json={"question": "Who is the CEO of Northwind Logistics?", "use_llm": True},
    )
    assert ask_online.status_code == 200
    body_on = ask_online.json()
    assert body_on["used_llm"] is True
    assert body_on["model"] == "llama3.2:3b"
    assert "Priya Nair" in body_on["answer_text"]

    # Executive brief endpoint
    brief = client.post(f"/api/analysis/{analysis_id}/brief")
    assert brief.status_code == 200
    assert brief.json()["used_llm"] is True
    assert len(brief.json()["highlights"]) >= 3

    # Delete analysis
    deleted = client.delete(f"/api/analysis/{analysis_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/analysis/{analysis_id}").status_code == 404

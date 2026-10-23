"""Benchmark, report, artifact-security and overview tests."""
from __future__ import annotations

import os


def _run_demo(client, auth_headers, name: str) -> str:
    from tests.helpers import run_demo

    return run_demo(client, auth_headers, name)

def test_benchmark_on_demo_models(client, auth_headers):
    _run_demo(client, auth_headers, "bench-demo-source")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    assert models
    teacher = next(m for m in models if "teacher" in m["name"])
    r = client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
        "model_id": teacher["id"], "task": "synthetic_classification", "seed": 11, "n_repeats": 3,
    })
    assert r.status_code == 201, r.text
    results = r.json()["results"]
    assert results["note"] == "measured on host CPU; confidence intervals from bootstrap over repeats"
    assert results["accuracy_ci95"] is not None and results["n_repeats"] == 3
    assert 0 <= results["mean_accuracy"] <= 1


def test_benchmark_fabricated_task_rejected(client, auth_headers):
    _run_demo(client, auth_headers, "bench-fabricated")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    teacher = models[0]["id"]
    r = client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
        "model_id": teacher, "task": "question_answering",
    })
    assert r.status_code == 409
    assert "no fake scores" in r.json()["detail"].lower()


def test_benchmark_on_quantized_artifact_dequantizes(client, auth_headers):
    """int8-quantized artifacts must still be evaluable (dequantized forward path),
    not crash with a 500 KeyError (regression for the qW{i} artifact schema)."""
    from tests.helpers import run_demo

    run_demo(client, auth_headers, "quant-bench-demo")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    teacher = next(m for m in models if "teacher" in m["name"])
    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "weight_quantization", "name": "quant for bench",
        "model_id": teacher["id"], "config": {"bits": 8}, "run_immediately": False,
    })
    assert r.status_code == 201, r.text
    q_exp = r.json()["id"]
    assert client.post(f"/api/v1/experiments/{q_exp}/run_sync", headers=auth_headers).status_code == 200
    qmodel_id = client.get(f"/api/v1/experiments/{q_exp}", headers=auth_headers).json()[
        "result_summary"]["quantized_model_id"]

    rb = client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
        "model_id": qmodel_id, "task": "synthetic_classification", "seed": 11, "n_repeats": 3,
    })
    assert rb.status_code == 201, rb.text
    res = rb.json()["results"]
    assert 0 <= res["mean_accuracy"] <= 1
    # dequantized teacher must stay within a sane margin of its fp32 accuracy
    rt = client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
        "model_id": teacher["id"], "task": "synthetic_classification", "seed": 11, "n_repeats": 3,
    })
    assert rt.status_code == 201
    delta = abs(res["mean_accuracy"] - rt.json()["results"]["mean_accuracy"])
    assert delta < 0.05, f"dequantized accuracy diverged: {delta}"


def test_benchmark_compare_pareto(client, auth_headers):
    _run_demo(client, auth_headers, "bench-compare-demo")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    for m in models:
        client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
            "model_id": m["id"], "task": "synthetic_classification", "seed": 13, "n_repeats": 2,
        })
    r = client.get("/api/v1/benchmarks/compare", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tradeoffs"] and any(t.get("on_pareto_front") for t in body["tradeoffs"])


def test_report_generation_markdown_html(client, auth_headers):
    exp_id = _run_demo(client, auth_headers, "report-demo")
    for fmt, ctype in (("markdown", "text/markdown"), ("html", "text/html")):
        r = client.post("/api/v1/reports/generate", headers=auth_headers, json={
            "experiment_id": exp_id, "format": fmt,
        })
        assert r.status_code == 201, r.text
        art_id = r.json()["artifact_id"]
        dl = client.get(f"/api/v1/artifacts/{art_id}/download", headers=auth_headers)
        assert dl.status_code == 200
        content = dl.content.decode()
        if fmt == "markdown":
            assert "## Results and uncertainty" in content
            assert "measured values" in content  # honesty statement present
            assert "## Reproducibility instructions" in content
        else:
            assert "<h2>" in content
    # PDF requires reportlab (installed in full env) but keep graceful either way
    r = client.post("/api/v1/reports/generate", headers=auth_headers, json={"experiment_id": exp_id, "format": "pdf"})
    assert r.status_code in (201, 409)


def test_artifact_access_control(client, auth_headers):
    exp_id = _run_demo(client, auth_headers, "acl-demo")
    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    art = next(a for a in r.json()["artifacts"] if a["kind"] == "model")
    dl = client.get(f"/api/v1/artifacts/{art['id']}/download", headers=auth_headers)
    assert dl.status_code == 200
    # integrity: advertised sha256 matches recomputed content hash
    import hashlib

    assert art["sha256"].lower() == hashlib.sha256(dl.content).hexdigest()
    assert dl.headers.get("X-Artifact-SHA256") == art["sha256"]
    # non-member user is denied (403 pre-workspace or 404 no-existence-leak)
    from tests.helpers import make_viewer

    _token, v_headers = make_viewer(client)
    dl = client.get(f"/api/v1/artifacts/{art['id']}/download", headers=v_headers)
    assert dl.status_code in (403, 404)


def test_artifact_integrity_failure_detected(client, auth_headers):
    from app.database import SessionLocal
    from app.models import Artifact
    from app.services.artifacts import read_bytes

    exp_id = _run_demo(client, auth_headers, "integrity-demo")
    with SessionLocal() as db:
        art = db.query(Artifact).filter_by(experiment_id=exp_id, kind="model").first()
        rel = art.uri.removeprefix("local://")
        path = os.path.join(os.environ["DATA_DIR"], rel)
    # Tamper with the artifact bytes
    with open(path, "ab") as f:
        f.write(b"tampered")
    try:
        import pytest

        with pytest.raises(ValueError):
            read_bytes(art.uri)
    finally:
        pass


def test_overview_from_real_data(client, auth_headers):
    r = client.get("/api/v1/overview", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    totals = body["totals"]
    assert totals["methods_available"] >= 8
    if totals["experiments_completed"] > 0:
        assert body["averages"]["compression_ratio"] is not None
        assert body["averages"]["task_retention"] is not None
    else:
        assert body["empty_state_hint"].startswith("No experiments yet")


def test_knowledge_graph_built(client, auth_headers):
    _run_demo(client, auth_headers, "graph-demo")
    r = client.get("/api/v1/graph", headers=auth_headers)
    assert r.status_code == 200
    g = r.json()
    kinds = {n["kind"] for n in g["nodes"]}
    assert "experiment" in kinds and "model" in kinds
    edges = g["edges"]
    assert any(e["established"] for e in edges)
    note_established = any("user" in e["evidence"] or e["established"] for e in edges)
    assert note_established


def test_research_entries_seeded_and_filtered(client, auth_headers):
    r = client.get("/api/v1/research/entries", headers=auth_headers)
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 10
    assert all("question" in e for e in entries)
    r = client.get("/api/v1/research/entries?field=compression", headers=auth_headers)
    assert all(e["research_field"] == "compression" for e in r.json())
    r2 = client.get("/api/v1/research/entries?evidence=established", headers=auth_headers)
    assert all(e["evidence_quality"] == "established" for e in r2.json())


def test_hypothesis_lifecycle(client, auth_headers):
    r = client.post("/api/v1/hypotheses", headers=auth_headers, json={
        "statement": "Can a shared low-rank representation reduce redundant computation across two modules without materially reducing task accuracy?",
        "success_criteria": "retention >= 0.95",
        "failure_criteria": "retention < 0.90 or instable across seeds",
    })
    assert r.status_code == 201
    h_id = r.json()["id"]
    r = client.get(f"/api/v1/hypotheses/{h_id}", headers=auth_headers)
    assert r.json()["evidence_level"] == "idea_only"
    # approve
    r = client.patch(f"/api/v1/hypotheses/{h_id}", headers=auth_headers, json={"status": "approved"})
    assert r.status_code == 200
    # invalid evidence level rejected
    r = client.patch(f"/api/v1/hypotheses/{h_id}", headers=auth_headers, json={"evidence_level": "magic"})
    assert r.status_code == 422
    # link an experiment: evidence stays manual until runs exist
    exp = client.post("/api/v1/experiments", headers=auth_headers, json={
        "name": "hyp-linked demo", "kind": "distillation_demo", "hypothesis_id": h_id, "run_now": False,
    })
    exp_id = exp.json()["id"]
    client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers)
    r = client.get("/api/v1/hypotheses", headers=auth_headers)
    h = next(x for x in r.json() if x["id"] == h_id)
    assert h["experiments"] and h["experiments"][0]["status"] == "completed"


def test_assistant_offline_honest(client, auth_headers):
    r = client.get("/api/v1/assistant/status", headers=auth_headers)
    assert r.status_code == 200
    st = r.json()
    assert st["mode"] == "offline_rules" or st["configured"]
    r = client.post("/api/v1/assistant/chat", headers=auth_headers, json={"message": "did it work? what were the results?"})
    assert r.status_code == 200
    content = r.json()["content"]
    assert ("No experiments exist yet" in content) or ("database records" in content)


def test_rate_middleware_blocks_under_burst(client):
    from app.main import RateLimitMiddleware
    import asyncio

    downstream_calls: list[str] = []

    async def passthrough(scope, receive, send):
        downstream_calls.append("call")

    lim = RateLimitMiddleware(app=passthrough, per_minute=2)
    scope = {"type": "http", "client": ("10.0.0.7", 1, "")}

    async def ride():
        events: list = []

        async def collector(message):
            events.append(message)

        await lim(scope, {"type": "http"}, collector)
        return events

    # 2 allowed calls reach downstream
    asyncio.run(ride())
    asyncio.run(ride())
    assert len(downstream_calls) == 2
    # 3rd call must be short-circuited with a 429 (downstream untouched, 429 status sent)
    events = asyncio.run(ride())
    assert len(downstream_calls) == 2  # unchanged
    assert any(e.get("status") == 429 for e in events if e["type"] == "http.response.start")

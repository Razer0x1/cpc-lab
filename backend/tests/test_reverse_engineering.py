"""Reverse-engineering (black-box surrogate) engine tests: real extraction runs."""
from __future__ import annotations

from tests.helpers import run_demo


def _setup_teacher(client, auth_headers, name: str) -> tuple[str, dict]:
    """Distill the demo, register artifacts, return (teacher model id, row)."""
    run_demo(client, auth_headers, name)
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    teacher = next(m for m in models if "teacher" in m["name"] and "quantized" not in m["name"]
                    and m["artifact_uri"])
    return teacher["id"], teacher


def test_registry_lists_reverse_engineering_as_runnable(client):
    methods = {m["key"]: m for m in client.get("/api/v1/workbench/methods").json()}
    m = methods["reverse_engineering"]
    assert m["runnable_now"] is True
    assert "Ethics" in " ".join(m["limitations"]) or any("ToS" in l for l in m["limitations"])


def test_reverse_engineering_run_end_to_end(client, auth_headers):
    teacher_id, teacher = _setup_teacher(client, auth_headers, "re-demo-source")

    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "reverse_engineering", "name": "blackbox extraction demo",
        "model_id": teacher_id, "config": {"surrogate_hidden": [8], "query_budget": 2000},
        "run_immediately": False,
    })
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]
    assert r.json()["kind"] == "reverse_engineering_extract"

    r = client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] in ("successful", "unsuccessful", "inconclusive")

    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    body = r.json()
    assert body["status"] == "completed"
    s = body["result_summary"]
    assert s["measured_only"] is True
    assert s["access_mode"] == "blackbox-forward-only"
    assert s["query_budget"] == 2000
    # measured fidelity + compression numbers exist and are sane
    assert 0.0 <= s["agreement_heldout"] <= 1.0
    assert 0.0 <= s["agreement_task"] <= 1.0
    assert s["params_surrogate"] < s["params_target"]
    assert s["artifact_bytes_surrogate"] < s["artifact_bytes_target"]
    assert s["compression_ratio_artifact"] and s["compression_ratio_artifact"] > 1.0
    # effective config snapshotted for reproducibility
    assert body["config"]["model_id"] == teacher_id
    assert body["config"]["access_mode"] == "blackbox-forward-only"
    # extracted surrogate got registered as a benchmarkable model
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    assert any(("reversed surrogate" in m["name"]) and m["artifact_uri"] for m in models)


def test_surrogate_benchmark_resolves_artifact_bytes_and_role(client, auth_headers):
    """Pareto/tradeoff data must resolve artifact size + role for black-box
    extraction outputs (regression: surrogate excluded as artifact_bytes=None/unknown)."""
    from tests.helpers import run_demo

    run_demo(client, auth_headers, "surrogate-pareto-source")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    teacher = next(m for m in models if "teacher" in m["name"] and m["artifact_uri"])
    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "reverse_engineering", "name": "re pareto demo",
        "model_id": teacher["id"], "config": {"query_budget": 2000}, "run_immediately": False,
    })
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]
    assert client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers).status_code == 200
    surrogate_id = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers).json()[
        "result_summary"]["surrogate_model_id"]

    r = client.post("/api/v1/benchmarks/run", headers=auth_headers, json={
        "model_id": surrogate_id, "task": "synthetic_classification", "seed": 13, "n_repeats": 3,
    })
    assert r.status_code == 201, r.text

    c = client.get("/api/v1/benchmarks/compare", headers=auth_headers).json()
    rows = {t["model_id"]: t for t in c["tradeoffs"]}
    row = rows[surrogate_id]
    assert row["artifact_bytes"] is not None and row["artifact_bytes"] > 0
    assert row["role"] == "compressed"
    assert isinstance(row["on_pareto_front"], bool)
    assert row["quality"] is not None


def test_reverse_engineering_config_validation(client, auth_headers):
    teacher_id, _ = _setup_teacher(client, auth_headers, "re-validation-source")
    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "reverse_engineering", "name": "bad config run",
        "model_id": teacher_id,
        "config": {"temperature": 99, "query_budget": 10, "surrogate_hidden": []},
        "run_immediately": False,
    })
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["validation_errors"]
    assert any("temperature" in e for e in errors)
    assert any("query_budget" in e for e in errors)
    assert any("surrogate_hidden" in e for e in errors)


def test_reverse_engineering_requires_target_model(client, auth_headers):
    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "reverse_engineering", "name": "missing model run",
        "run_immediately": False,
    })
    assert r.status_code == 422
    assert "model_id required" in r.json()["detail"]

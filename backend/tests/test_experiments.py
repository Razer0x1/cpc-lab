"""Experiment lifecycle tests: end-to-end real demo, cancel, retry-after-failure, logs, artifacts."""
from __future__ import annotations

from tests.helpers import run_demo


def test_create_and_run_distillation_demo(client, auth_headers):
    r = client.post("/api/v1/experiments", headers=auth_headers, json={
        "name": "Demo distillation run",
        "kind": "distillation_demo",
        "seed": 7,
        "budgets": {"max_seconds": 60},
        "run_now": False,
    })
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]

    r = client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] in ("successful", "unsuccessful", "inconclusive")

    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    body = r.json()
    assert body["status"] == "completed"
    assert body["log_count"] > 0
    # effective config (kind defaults + overrides) is snapshotted for reproducibility
    assert body["config"].get("kd_alpha") == 0.7
    assert body["config"].get("teacher_hidden") == [64, 64]
    summary = body["result_summary"]
    assert summary["measured_only"] is True
    # measured metric sanity
    assert 0 <= summary["accuracy_baseline"] <= 1
    assert 0 <= summary["accuracy_compressed"] <= 1
    ratio = summary["compression_ratio_artifact"]
    retention = summary["task_retention"]
    assert ratio is not None and ratio > 1, "teacher artifact must be larger than student artifact"
    assert retention is not None and 0 < retention <= 2
    # metrics rows staged baseline/compressed/measured
    names = {m["name"] + ":" + m["stage"] for m in body["metrics"]}
    assert "accuracy:baseline" in names and "accuracy:compressed" in names
    assert "compression_ratio:measured" in names
    # artifacts exist
    assert any(a["kind"] == "model" for a in body["artifacts"])


def test_logs_present_and_sequential(client, auth_headers):
    exp_id = run_demo(client, auth_headers, "logs demo")
    r = client.get(f"/api/v1/experiments/{exp_id}/logs", headers=auth_headers)
    logs = r.json()["logs"]
    assert logs and logs[0]["seq"] == 0
    seqs = [ln["seq"] for ln in logs]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))


def test_unknown_kind_rejected(client, auth_headers):
    r = client.post("/api/v1/experiments", headers=auth_headers, json={
        "name": "bad run", "kind": "definitely_not_registered",
    })
    assert r.status_code == 422


def test_duplicate_name_rejected(client, auth_headers):
    r = client.post("/api/v1/experiments", headers=auth_headers, json={"name": "dup-test", "kind": "distillation_demo", "run_now": False})
    assert r.status_code == 201
    r = client.post("/api/v1/experiments", headers=auth_headers, json={"name": "dup-test", "kind": "distillation_demo", "run_now": False})
    assert r.status_code == 409


def test_gpu_kinds_disabled_without_engine(client, auth_headers):
    r = client.post("/api/v1/experiments", headers=auth_headers, json={
        "name": "gpu kind", "kind": "benchmark_synthetic_classification",
    })
    assert r.status_code == 409
    assert "ENGINE_TORCH" in r.json()["detail"]


def test_cancel_queued_experiment(client, auth_headers):
    r = client.post("/api/v1/experiments", headers=auth_headers, json={"name": "cancel me", "kind": "distillation_demo", "run_now": False})
    exp_id = r.json()["id"]
    r = client.post(f"/api/v1/experiments/{exp_id}/cancel", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r.json()["status"] == "cancelled"


def test_cancel_completed_conflict(client, auth_headers):
    exp_id = run_demo(client, auth_headers, "cancel-conflict demo")
    r = client.post(f"/api/v1/experiments/{exp_id}/cancel", headers=auth_headers)
    assert r.status_code == 409


def test_failed_run_and_retry(client, auth_headers):
    # quantization without model_id fails fast -> failed state -> retry resets, still fails
    exp_r = client.post("/api/v1/experiments", headers=auth_headers, json={
        "name": "quant-no-target", "kind": "quantization_int8_eval", "run_now": False,
    })
    exp_id = exp_r.json()["id"]
    r = client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers)
    assert r.status_code == 200 and r.json()["verdict"] is None
    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r.json()["status"] == "failed"
    assert "model_id is required" in (r.json()["error"] or "")

    # valid demo provides a model; retry then fixed run still reports missing config until updated
    run_demo(client, auth_headers, "demo for quant")
    r = client.post(f"/api/v1/experiments/{exp_id}/retry", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "created"
    r = client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=auth_headers)
    assert r.status_code == 200 and r.json()["verdict"] is None
    r = client.get(f"/api/v1/experiments/{exp_id}", headers=auth_headers)
    assert r.json()["status"] == "failed"


def test_quantization_run_success_criteria(client, auth_headers):
    run_demo(client, auth_headers, "demo2")
    models = client.get("/api/v1/workbench/models", headers=auth_headers).json()
    teacher = next(m for m in models if "teacher" in m["name"])

    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "weight_quantization", "name": "quant teacher int8",
        "model_id": teacher["id"], "config": {"bits": 8}, "run_immediately": False,
    })
    assert r.status_code == 201, r.text
    q_id = r.json()["id"]
    r = client.post(f"/api/v1/experiments/{q_id}/run_sync", headers=auth_headers)
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/experiments/{q_id}", headers=auth_headers)
    s = r.json()["result_summary"]
    assert s["accuracy_quantized"] is not None
    assert s["measured_only"] is True
    # effective config includes the resolved bits + target model
    cfg = r.json()["config"]
    assert cfg.get("bits") == 8
    assert cfg.get("model_id") == teacher["id"]
    measured, theoretical = s["compression_ratio_measured"], s["compression_ratio_theoretical"]
    assert theoretical == 4.0 and measured is not None


def test_workbench_planned_method_rejected(client, auth_headers):
    r = client.post("/api/v1/workbench/runs", headers=auth_headers, json={
        "method_key": "pruning_unstructured", "name": "planned method run",
    })
    assert r.status_code == 409
    assert "planned" in r.json()["detail"]


def test_experiment_workspace_isolation(client, auth_headers):
    from tests.helpers import make_viewer

    _token, v_headers = make_viewer(client)
    # viewer has their own personal workspace: empty list, not the admin's data
    r = client.get("/api/v1/experiments", headers=v_headers)
    assert r.status_code == 200
    assert r.json() == []
    # admin experiments are not listable under a forged workspace header
    r = client.get("/api/v1/experiments", headers={**auth_headers, "X-Workspace-ID": "ffff"})
    assert r.status_code == 403

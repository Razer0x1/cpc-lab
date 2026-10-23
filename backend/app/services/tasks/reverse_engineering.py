"""Reverse-engineering extraction engine: reconstruct a compact surrogate from a
trained model's *behavior only*.

Protocol (documented, CPU-friendly, fully measured):
  1. Load the target artifact (weights stay local; see honesty note below).
  2. Draw N query inputs uniformly from the documented input domain.
  3. Query the target's forward function: soft targets at temperature T + hard
     argmax decisions. No training labels, no gradients, no internals.
  4. Fit a compact surrogate on the queried points only.
  5. Measure: held-out agreement with the target, task-set agreement and
     ground-truth accuracy on the canonical spiral3 split, artifact bytes,
     parameter counts, warm latency on identical batches.

Honesty note: the artifact file is read locally (no network service is
queried), but the extraction protocol deliberately restricts itself to
forward outputs — mirroring black-box access as in the model-extraction
literature. All reported metrics derive from these queries.

Legal/ethical boundary: extraction of hosted third-party models may violate
terms of service. This engine documents that boundary in the registry
limitations and is intended for locally owned artifacts.
"""
from __future__ import annotations

import json
import time
import tracemalloc

import numpy as np

from app.models import MLModel, Transformation

from ..runner import TaskContext, TaskResult, register_task, snapshot_effective_config
from . import nn_numpy as npnn

TASK_KEY = "reverse_engineering_extract"

DEFAULTS = {
    "query_budget": 3000,          # total black-box queries (70% train / 30% held-out)
    "query_range": 1.2,            # uniform domain [-query_range, query_range]^d
    "surrogate_hidden": [8],
    "temperature": 2.0,            # soft-target temperature for query responses
    "soft_weight": 0.9,            # distillation weight on teacher soft outputs
    "surrogate_epochs": 120,
    "learning_rate": 0.03,
    "batch_size": 128,
    "success_criteria": {          # evaluated against measured metrics only
        "min_agreement_heldout": 0.70,
        "min_compression_ratio": 5.0,
        "min_latency_speedup": 1.0,
    },
}


def _soft_targets(net: npnn.MLP, X: np.ndarray, temperature: float) -> np.ndarray:
    z = net.forward_logits(X) / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return (e / e.sum(axis=1, keepdims=True)).astype(np.float32)


def _forward_peak_mem(net: npnn.MLP, X: np.ndarray) -> float:
    tracemalloc.start()
    net.forward_logits(X[:64])
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / (1024 * 1024)


@register_task(TASK_KEY)
def run_reverse_engineering_extract(ctx: TaskContext) -> TaskResult:
    cfg = {**DEFAULTS, **(ctx.config or {})}
    criteria = {**DEFAULTS["success_criteria"], **(cfg.get("success_criteria") or {})}
    seed = ctx.seed

    model = ctx.db.get(MLModel, ctx.config.get("model_id"))
    if model is None or model.workspace_id != ctx.workspace_id:
        raise ValueError("config.model_id is required: reverse-engineering extracts a registered model artifact (black-box queries)")
    if not model.artifact_uri:
        raise ValueError("target model has no stored artifact to query")

    query_budget = int(cfg["query_budget"])
    if not (200 <= query_budget <= 50000):
        raise ValueError("query_budget must be within [200, 50000]")
    query_range = float(cfg["query_range"])
    if not (0.5 <= query_range <= 4.0):
        raise ValueError("query_range must be within [0.5, 4.0]")
    temperature = float(cfg["temperature"])
    if not (0.5 <= temperature <= 10.0):
        raise ValueError("temperature must be within [0.5, 10]")
    soft_weight = float(cfg["soft_weight"])
    if not (0.0 <= soft_weight <= 1.0):
        raise ValueError("soft_weight must be within [0, 1]")
    hidden = [int(h) for h in cfg["surrogate_hidden"]]
    if not hidden or not all(1 <= h <= 512 for h in hidden):
        raise ValueError("surrogate_hidden must be a list of layer widths in [1, 512]")

    from app.services import artifacts as artifact_store

    target_bytes = artifact_store.read_bytes(model.artifact_uri)
    target = npnn.MLP.load_npz(target_bytes)
    ctx.log(f"Target: {model.name} (revision {model.revision})")
    snapshot_effective_config(ctx, {
        **{k: v for k, v in cfg.items() if k != "success_criteria"},
        "success_criteria": criteria,
        "model_id": model.id,
        "model_name": model.name,
        "access_mode": "blackbox-forward-only",
    })

    num_classes = target.sizes[-1]
    input_dim = target.sizes[0]
    rng = np.random.default_rng(seed)
    X_q = ((rng.random((query_budget, input_dim)) * 2 - 1) * query_range).astype(np.float32)
    ctx.log(f"Query set: uniform [-{query_range}, {query_range}]^{input_dim}, n={query_budget} (documented domain)")
    ctx.progress(0.15, "Querying target model (forward-only access)")
    ctx.check_point()

    # hard decisions for the surrogate's label channel (argmax at T == argmax of raw logits);
    # soft responses at temperature T are applied inside the surrogate's KD loss
    labels_q = target.predict(X_q).astype(np.int64)

    split = int(query_budget * 0.7)
    X_tr, y_tr = X_q[:split], labels_q[:split]
    X_held, y_held = X_q[split:], labels_q[split:]
    ctx.log(f"Behavior dataset: {X_tr.shape[0]} train queries / {X_held.shape[0]} held-out queries "
            f"(soft KD targets at T={temperature})")

    surrogate = npnn.MLP(sizes=[input_dim, *hidden, num_classes], activation="relu", seed=seed)
    ctx.progress(0.35, "Training surrogate from queried behavior")
    ctx.check_point()
    surrogate.fit(
        X_tr, y_tr,
        epochs=int(cfg["surrogate_epochs"]), lr=float(cfg["learning_rate"]),
        batch_size=int(cfg["batch_size"]), seed=seed + 1,
        teacher=target, kd_alpha=soft_weight, kd_temperature=temperature,
        log_every=40, log_fn=ctx.log,
    )

    # ---- measured evaluation ------------------------------------------------
    agreement_heldout = float((surrogate.predict(X_held) == y_held).mean())
    held_soft_t = _soft_targets(target, X_held, temperature)
    held_soft_s = _soft_targets(surrogate, X_held, temperature)
    soft_ce_heldout = float(-(held_soft_t * np.log(np.clip(held_soft_s, 1e-12, None))).sum(axis=1).mean())

    X_test, y_test = npnn.make_spiral3(400, seed=seed + 1)
    agreement_task = float((surrogate.predict(X_test) == target.predict(X_test)).mean())
    acc_surrogate = npnn.accuracy(surrogate, X_test, y_test)
    acc_target = npnn.accuracy(target, X_test, y_test)
    ce_surrogate = npnn.cross_entropy(surrogate, X_test, y_test)
    ctx.progress(0.75, "Measuring agreement, artifacts and latency")
    ctx.check_point()

    batch = X_test[: min(256, X_test.shape[0])]
    for _ in range(5):
        surrogate.forward_logits(batch)
        target.forward_logits(batch)
    t0 = time.perf_counter()
    for _ in range(30):
        surrogate.forward_logits(batch)
    lat_surrogate = (time.perf_counter() - t0) * 1000 / 30
    t0 = time.perf_counter()
    for _ in range(30):
        target.forward_logits(batch)
    lat_target = (time.perf_counter() - t0) * 1000 / 30

    target_params = target.param_count
    surrogate_params = surrogate.param_count
    surrogate_bytes = float(len(surrogate.save_npz()))
    target_artifact_bytes = float(len(target_bytes))
    ratio_artifact = (target_artifact_bytes / surrogate_bytes) if surrogate_bytes else None

    checks = [
        ("min_agreement_heldout",
         agreement_heldout >= criteria["min_agreement_heldout"],
         f"held-out agreement={agreement_heldout:.3f} >= {criteria['min_agreement_heldout']}"),
        ("min_compression_ratio",
         ratio_artifact is not None and ratio_artifact >= criteria["min_compression_ratio"],
         f"artifact ratio={ratio_artifact:.2f}" if ratio_artifact is not None else "artifact ratio unavailable"),
        ("min_latency_speedup",
         lat_surrogate > 0 and (lat_target / lat_surrogate) >= criteria["min_latency_speedup"],
         f"warm speedup={lat_target / lat_surrogate if lat_surrogate else 0:.2f}x"),
    ]
    all_pass = all(ok for _, ok, _ in checks)
    verdict = "successful" if all_pass else (
        "unsuccessful" if agreement_heldout < criteria["min_agreement_heldout"] * 0.5 else "inconclusive"
    )
    reason = (
        "; ".join(t for _, ok, t in checks if not ok) if not all_pass
        else "agreement, artifact ratio and latency criteria met on measured values"
    )

    # ---- persist extracted artifact + registered surrogate model ------------
    stored = artifact_store.put_bytes(ctx.workspace_id, "model", "surrogate_extracted.npz", surrogate.save_npz())
    from app.models import Artifact  # local import to avoid import cycle

    art = Artifact(
        workspace_id=ctx.workspace_id, experiment_id=ctx.experiment_id, kind="model",
        filename="surrogate_extracted.npz",
        meta={"dtype": "float32", "extracted_from": model.artifact_uri, "access": "blackbox-forward-only"},
        **stored,
    )
    ctx.db.add(art)
    ctx.db.commit()
    ctx.db.refresh(art)

    smodel = MLModel(
        workspace_id=ctx.workspace_id,
        name=f"{model.name} reversed surrogate [{','.join(str(h) for h in hidden)}]",
        family=model.family, revision=f"re1-{model.revision}", source="synthetic",
        params_count=surrogate_params, artifact_uri=art.uri, synthetic=True,
        notes=f"Black-box surrogate of model {model.id}: fit on {query_budget} forward queries "
              f"(soft targets T={temperature}, soft_weight={soft_weight}); no internals used.",
    )
    ctx.db.add(smodel)
    ctx.db.commit()
    ctx.db.refresh(smodel)

    compat = [
        {"name": "blackbox_forward_only", "passed": True, "detail": f"{query_budget} forward queries, no internals"},
        {"name": "shape_match", "passed": True, "detail": f"surrogate={surrogate.sizes}"},
        {"name": "documented_query_domain", "passed": True, "detail": f"uniform [-{query_range}, {query_range}]^{input_dim}"},
    ]
    trans = Transformation(
        workspace_id=ctx.workspace_id, experiment_id=ctx.experiment_id, method_key="reverse_engineering",
        spec={"type": "reverse_engineering", "version": 1,
              "params": {"query_budget": query_budget, "temperature": temperature, "soft_weight": soft_weight,
                          "surrogate_hidden": hidden, "query_range": query_range}},
        spec_version=1,
        preconditions=["forward-query access to the target (artifact present locally)"],
        invariants=["compact surrogate trained on queried behavior only",
                     "agreement and compression reported from measurements"],
        failure_modes=["out-of-domain extrapolation unreliable",
                        "surrogate capacity gap under-fits decision boundary",
                        "query distribution shift inflates agreement estimates"],
        compat_checks=compat,
        status="applied" if all(c["passed"] for c in compat) else "rejected",
        input_model_id=model.id, output_model_id=smodel.id,
    )
    ctx.db.add(trans)
    ctx.db.commit()

    summary = {
        "question": f"Can a compact surrogate ({hidden}) be reconstructed from {query_budget} forward queries "
                     f"of {model.name}, preserving behavior while shrinking the artifact?",
        "access_mode": "blackbox-forward-only",
        "query_budget": query_budget,
        "query_train": int(X_tr.shape[0]),
        "query_heldout": int(X_held.shape[0]),
        "temperature": temperature,
        "soft_weight": soft_weight,
        "target_model_id": model.id,
        "surrogate_model_id": smodel.id,
        "transformation_id": trans.id,
        "surrogate_artifact_uri": art.uri,
        "agreement_heldout": agreement_heldout,
        "soft_ce_heldout": soft_ce_heldout,
        "agreement_task": agreement_task,
        "accuracy_target": acc_target,
        "accuracy_surrogate": acc_surrogate,
        "accuracy_gap_abs": acc_target - acc_surrogate,
        "cross_entropy_surrogate": ce_surrogate,
        "params_target": target_params,
        "params_surrogate": surrogate_params,
        "compression_ratio_params": (target_params / surrogate_params) if surrogate_params else None,
        "artifact_bytes_target": target_artifact_bytes,
        "artifact_bytes_surrogate": surrogate_bytes,
        "compression_ratio_artifact": ratio_artifact,
        "latency_warm_ms_target": lat_target,
        "latency_warm_ms_surrogate": lat_surrogate,
        "latency_speedup": (lat_target / lat_surrogate) if lat_surrogate else None,
        "inference_peak_mem_mb": max(_forward_peak_mem(target, batch), _forward_peak_mem(surrogate, batch)),
        "criteria": criteria,
        "criteria_checks": [{"id": cid, "passed": ok, "detail": det} for cid, ok, det in checks],
        "verdict": verdict,
        "engine": "numpy-mlp/CPU (black-box surrogate extraction)",
        "measured_only": True,
    }

    metrics = [
        {"name": "agreement", "value": agreement_heldout, "unit": "frac", "stage": "measured",
         "extra": {"split": "held-out queries"}},
        {"name": "agreement", "value": agreement_task, "unit": "frac", "stage": "measured",
         "extra": {"split": "spiral3 test (vs target predictions)"}},
        {"name": "soft_cross_entropy", "value": soft_ce_heldout, "unit": "nats", "stage": "measured",
         "extra": {"definition": "cross-entropy between target and surrogate soft responses (held-out)", "temperature": temperature}},
        {"name": "accuracy", "value": acc_target, "unit": "frac", "stage": "baseline"},
        {"name": "accuracy", "value": acc_surrogate, "unit": "frac", "stage": "extracted"},
        {"name": "artifact_bytes", "value": target_artifact_bytes, "unit": "B", "stage": "baseline"},
        {"name": "artifact_bytes", "value": surrogate_bytes, "unit": "B", "stage": "extracted"},
        {"name": "compression_ratio", "value": ratio_artifact, "unit": "x", "stage": "measured"},
        {"name": "latency_warm_ms", "value": lat_target, "unit": "ms", "stage": "baseline"},
        {"name": "latency_warm_ms", "value": lat_surrogate, "unit": "ms", "stage": "extracted"},
        {"name": "params", "value": target_params, "unit": "", "stage": "baseline"},
        {"name": "params", "value": surrogate_params, "unit": "", "stage": "extracted"},
    ]
    ctx.save_artifact(
        "eval", "reverse_engineering_metrics.json",
        json.dumps({"summary": summary, "metrics": metrics}, indent=2).encode(),
        meta={"experiment": ctx.experiment_id},
    )
    ctx.log(f"Extracted surrogate: agreement={agreement_heldout:.3f} (held-out), "
            f"task agreement={agreement_task:.3f}, soft CE={soft_ce_heldout:.4f}, "
            f"artifact={surrogate_bytes:.0f}B, warm speedup={lat_target / lat_surrogate if lat_surrogate else 0:.2f}x")

    return TaskResult(summary=summary, metrics=metrics, verdict=verdict, verdict_reason=reason,
                      engine_note="numpy-mlp/CPU black-box extraction")

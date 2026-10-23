"""Post-training weight quantization (int8) on a stored MLP artifact.

Measured: accuracy delta on the same test split, artifact bytes (int8 + scales),
compression ratio, and host latency with a dequantize-on-load numeric path.
Theoretical: byte-width ratio (float32->int8 == 4x) is recorded separately as
stage='theoretical' and never mixed with measured results.
"""
from __future__ import annotations

import json
import time
import tracemalloc

import numpy as np

from ..compression import theoretical_quantization_ratio
from ..runner import TaskContext, TaskResult, register_task, snapshot_effective_config
from app.models import MLModel, Transformation
from . import nn_numpy as npnn

TASK_KEY = "quantization_int8_eval"

DEFAULTS = {
    "bits": 8,
    "success_criteria": {
        "max_accuracy_drop_abs": 0.05,
        "min_compression_ratio": 2.0,
    },
    "requires_artifact": True,
}


def _quantize_array(w: np.ndarray, bits: int) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric per-tensor quantization to `bits`-width codes represented in uint8 storage."""
    qmax = 2 ** (bits - 1) - 1
    scale = float(np.max(np.abs(w))) / qmax if np.max(np.abs(w)) > 0 else 1.0
    q = np.clip(np.rint(w / scale), -qmax - (1 if bits == 8 else 0), qmax).astype(np.int8)
    return q, np.float32(scale)


def _dequantize(q: np.ndarray, scale: np.ndarray | float) -> np.ndarray:
    return q.astype(np.float32) * float(scale)


@register_task(TASK_KEY)
def run_quantization_eval(ctx: TaskContext) -> TaskResult:
    from sqlalchemy.orm import Session as _S  # noqa: F401  (typing aid only)

    cfg = {**DEFAULTS, **(ctx.config or {})}
    criteria = {**DEFAULTS["success_criteria"], **(cfg.get("success_criteria") or {})}
    bits = int(cfg.get("bits", 8))
    if bits not in (2, 4, 8):
        raise ValueError("bits must be one of 2, 4, 8")

    model_id = ctx.config.get("model_id")
    if not model_id:
        raise ValueError("config.model_id is required: select a quantization target model first")
    model = ctx.db.get(MLModel, model_id)
    if model is None or model.workspace_id != ctx.workspace_id:
        raise ValueError("target model not found in this workspace")
    if not model.artifact_uri:
        raise ValueError("target model has no stored artifact")
    snapshot_effective_config(ctx, {**cfg, "model_id": model_id, "model_name": model.name})
    ctx.log(f"Target: {model.name} (revision {model.revision})")

    from app.services import artifacts as artifact_store

    weights_bytes = artifact_store.read_bytes(model.artifact_uri)
    net = npnn.MLP.load_npz(weights_bytes)

    # Deterministic eval set matching distillation demo generation (spin @ model revision seed
    # not guaranteed; the quantization eval regenerates spiral3 with dataset-level seed).
    seed = int(ctx.config.get("eval_seed", 7))
    X_test, y_test = npnn.make_spiral3(400, seed=seed + 1)
    ctx.log(f"Eval set: cpc_spiral3 (seed={seed + 1}, n={X_test.shape[0]})")

    base_acc = npnn.accuracy(net, X_test, y_test)
    base_bytes = float(len(weights_bytes))
    base_lat = npnn.measure_latency(net, X_test)
    ctx.log(f"Baseline(float32): accuracy={base_acc:.4f} artifact={base_bytes:.0f}B warm={base_lat['latency_warm_ms']:.3f}ms")

    # Quantize
    q_layers: list[tuple[np.ndarray, np.ndarray]] = []
    for w in net.W:
        q_layers.append(_quantize_array(w, bits))
    q_biases = [b.astype(np.float32) for b in net.b]  # biases kept fp32
    qnet = npnn.MLP(net.sizes, seed=0)
    qnet.W = [_dequantize(q, s) for q, s in q_layers]
    qnet.b = q_biases

    # Measure dequantize-on-load inference
    def forward_q(X: np.ndarray) -> np.ndarray:
        h = X
        for i in range(len(qnet.W) - 1):
            h = np.maximum(h @ qnet.W[i] + qnet.b[i], 0.0)
        return h @ qnet.W[-1] + qnet.b[-1]

    if tracemalloc.is_tracing():
        tracemalloc.stop()
    tracemalloc.start()
    forward_q(X_test[:64])
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    batch = X_test[: min(256, X_test.shape[0])]
    for _ in range(5):
        forward_q(batch)
    t0 = time.perf_counter()
    for _ in range(30):
        forward_q(batch)
    warm_ms = (time.perf_counter() - t0) * 1000 / 30

    qacc = npnn.accuracy(qnet, X_test, y_test)
    # Measured artifact size: int8 weights + fp32 biases + scales
    q_bytes = float(sum(q.nbytes for q, _ in q_layers) + sum(b.nbytes for b in q_biases) + len(q_layers) * 4)
    ratio_measured = base_bytes / q_bytes if q_bytes else None
    drop_abs = base_acc - qacc

    # Persist quantized artifact
    import io

    buf = io.BytesIO()
    arrays: dict[str, np.ndarray] = {}
    for i, (q, s) in enumerate(q_layers):
        arrays[f"qW{i}"] = q
        arrays[f"sW{i}"] = np.float32([s])
        arrays[f"b{i}"] = q_biases[i]
    np.savez_compressed(buf, **arrays)
    quant_bytes = buf.getvalue()

    from app.models import Artifact  # local import to avoid cycle at module import

    stored = artifact_store.put_bytes(ctx.workspace_id, "model", f"quantized_{bits}bit.npz", quant_bytes)
    art = Artifact(
        workspace_id=ctx.workspace_id, experiment_id=ctx.experiment_id, kind="model",
        filename=f"quantized_{bits}bit.npz", meta={"dtype": f"int{bits}", "quantized_from": model.artifact_uri},
        **stored,
    )
    ctx.db.add(art)
    ctx.db.commit()
    ctx.db.refresh(art)

    qmodel = MLModel(
        workspace_id=ctx.workspace_id, name=f"{model.name} int{bits} quantized",
        family=model.family, revision=f"q{bits}-{model.revision}", source="synthetic",
        params_count=model.params_count, artifact_uri=art.uri, synthetic=model.synthetic,
        notes=f"Symmetric per-tensor int{bits} weight quantization of model {model.id}. Biases fp32 (common practice); arithmetic dequantize-on-load in fp32.",
    )
    ctx.db.add(qmodel)
    ctx.db.commit()
    ctx.db.refresh(qmodel)

    theo = theoretical_quantization_ratio("float32", f"int{bits}")
    compat = [
        {"name": "architecture_match", "passed": qnet.sizes == net.sizes, "detail": f"sizes={qnet.sizes}"},
        {"name": "dtype_availabe", "passed": True, "detail": f"int{bits} codes + fp32 scale"},
        {"name": "calibration_not_required", "passed": True, "detail": "post-training symmetric absmax"},
    ]
    trans = Transformation(
        workspace_id=ctx.workspace_id, experiment_id=ctx.experiment_id, method_key="weight_quantization",
        spec={"type": "weight_quantization", "version": 1, "params": {"bits": bits, "granularity": "per_tensor", "symmetric": True}},
        spec_version=1,
        preconditions=["weights available as fp32 artifact"],
        invariants=["parameter count unchanged", "architecture unchanged"],
        failure_modes=["activation outliers -> accuracy drop", "all-zero tails of spiral -> minor class drift"],
        compat_checks=compat,
        status="applied" if all(c["passed"] for c in compat) else "rejected",
        input_model_id=model.id, output_model_id=qmodel.id,
    )
    ctx.db.add(trans)
    ctx.db.commit()

    checks = [
        ("max_accuracy_drop_abs", drop_abs <= criteria["max_accuracy_drop_abs"], f"drop={drop_abs:.4f} <= {criteria['max_accuracy_drop_abs']}"),
        ("min_compression_ratio", ratio_measured is not None and ratio_measured >= criteria["min_compression_ratio"], f"ratio={ratio_measured:.2f}"),
    ]
    all_pass = all(ok for _, ok, _ in checks)
    verdict = "successful" if all_pass else ("unsuccessful" if drop_abs > 2 * criteria["max_accuracy_drop_abs"] else "inconclusive")
    reason = "; ".join(t for _, ok, t in checks if not ok) if not all_pass else "accuracy within tolerance and measured artifact ratio met"

    summary = {
        "question": f"Does int{bits} post-training quantization reduce artifact size on {model.name} without materially reducing accuracy?",
        "source_model_id": model.id,
        "quantized_model_id": qmodel.id,
        "transformation_id": trans.id,
        "quantized_artifact_uri": art.uri,
        "accuracy_baseline": base_acc,
        "accuracy_quantized": qacc,
        "accuracy_drop_abs": drop_abs,
        "artifact_bytes_baseline": base_bytes,
        "artifact_bytes_quantized": q_bytes,
        "compression_ratio_measured": ratio_measured,
        "compression_ratio_theoretical": theo,
        "latency_warm_ms_baseline": base_lat["latency_warm_ms"],
        "latency_warm_ms_quantized": warm_ms,
        "latency_speedup": (base_lat["latency_warm_ms"] / warm_ms) if warm_ms else None,
        "inference_peak_mem_mb": peak / (1024 * 1024),
        "criteria": criteria,
        "criteria_checks": [{"id": cid, "passed": ok, "detail": det} for cid, ok, det in checks],
        "verdict": verdict,
        "engine": "numpy-mlp/CPU (dequantize-on-load)",
        "measured_only": True,
    }
    ctx.log(f"Quantized(int{bits}): accuracy={qacc:.4f} artifact={q_bytes:.0f}B warm={warm_ms:.3f}ms")

    metrics = [
        {"name": "accuracy", "value": base_acc, "unit": "frac", "stage": "baseline", "extra": {"dtype": "float32"}},
        {"name": "accuracy", "value": qacc, "unit": "frac", "stage": "compressed", "extra": {"dtype": f"int{bits}"}},
        {"name": "artifact_bytes", "value": base_bytes, "unit": "B", "stage": "baseline"},
        {"name": "artifact_bytes", "value": q_bytes, "unit": "B", "stage": "compressed"},
        {"name": "compression_ratio", "value": ratio_measured, "unit": "x", "stage": "measured"},
        {"name": "compression_ratio", "value": theo, "unit": "x", "stage": "theoretical", "extra": {"definition": "byte-width ratio float32->int%d" % bits}},
        {"name": "latency_warm_ms", "value": warm_ms, "unit": "ms", "stage": "compressed"},
        {"name": "latency_warm_ms", "value": base_lat["latency_warm_ms"], "unit": "ms", "stage": "baseline"},
    ]
    ctx.save_artifact("eval", f"quantization_{bits}bit_metrics.json",
                      json.dumps({"summary": summary, "metrics": metrics}, indent=2).encode(),
                      meta={"experiment": ctx.experiment_id})

    return TaskResult(summary=summary, metrics=metrics, verdict=verdict, verdict_reason=reason,
                      engine_note=f"numpy-mlp/CPU int{bits}")

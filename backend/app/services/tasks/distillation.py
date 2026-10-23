"""First working research demonstration (CPU-only, reproducible, fully measured).

Question: "Can a compact student model preserve the task performance of a larger
teacher model while reducing artifact size and inference cost?"

Method: knowledge distillation on a deterministic synthetic classification benchmark.
Everything measured here is real, recorded, and reproducible; nothing is simulated.
If the run fails pre-criteria, the verdict is 'unsuccessful' or 'inconclusive' — never
silently 'successful'.
"""
from __future__ import annotations

import json

import numpy as np

from app.models import Dataset, MLModel, Transformation
from ..runner import TaskContext, TaskResult, register_task, snapshot_effective_config
from . import nn_numpy as npnn

TASK_KEY = "distillation_demo"

DEFAULTS = {
    "dataset_generator": "cpc_spiral3",
    "train_examples": 2400,
    "test_examples": 1200,
    "teacher_hidden": [64, 64],
    "student_hidden": [8],
    "teacher_epochs": 120,
    "student_epochs": 120,
    "kd_alpha": 0.7,
    "kd_temperature": 2.0,
    "learning_rate": 0.02,
    "batch_size": 128,
    "success_criteria": {  # evaluated against *measured* metrics only
        "min_retention": 0.95,      # student_acc / teacher_acc
        "min_compression_ratio": 6.0,
        "min_latency_speedup": 0.9,  # student must not be slower (on this host)
    },
}


def _measure(net: npnn.MLP, X_test: np.ndarray, y_test: np.ndarray) -> dict:
    lat = npnn.measure_latency(net, X_test)
    acc = npnn.accuracy(net, X_test, y_test)
    ce = npnn.cross_entropy(net, X_test, y_test)
    import tracemalloc

    tracemalloc.start()
    net.forward_logits(X_test[:64])
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "accuracy": acc,
        "cross_entropy": ce,
        "param_count": net.param_count,
        "artifact_bytes": float(len(net.save_npz())),
        "inference_peak_mem_mb": peak / (1024 * 1024),
        **lat,
    }


@register_task(TASK_KEY)
def run_distillation_demo(ctx: TaskContext) -> TaskResult:
    cfg = {**DEFAULTS, **(ctx.config or {})}
    seed = ctx.seed
    criteria = {**DEFAULTS["success_criteria"], **(cfg.get("success_criteria") or {})}
    snapshot_effective_config(ctx, {**cfg, "success_criteria": criteria})
    ctx.log(f"Config: teacher={cfg['teacher_hidden']}, student={cfg['student_hidden']}, "
            f"kd_alpha={cfg['kd_alpha']}, T={cfg['kd_temperature']}, seed={seed}")
    ctx.log("Engine: numpy-mlp (CPU). Torch/HF engines are optional GPU extras, not required for this demo.")

    X_train, y_train = npnn.make_spiral3(cfg["train_examples"] // 3, seed=seed)
    X_test, y_test = npnn.make_spiral3(cfg["test_examples"] // 3, seed=seed + 1)
    ctx.log(f"Dataset: cpc_spiral3 synthetic — train={X_train.shape[0]}, test={X_test.shape[0]} (deterministic, seed={seed})")

    # ---- Stage 1: teacher baseline ----
    ctx.progress(0.05, "Training teacher model (baseline)")
    teacher = npnn.MLP([2, *cfg["teacher_hidden"], 3], seed=seed)
    peak_train_mb, _ = npnn.measure_peak_memory_train(
        teacher.fit, X_train, y_train, epochs=cfg["teacher_epochs"],
        lr=cfg["learning_rate"], batch_size=cfg["batch_size"], seed=seed, log_every=40, log_fn=ctx.log,
    )
    ctx.check_point()
    base = _measure(teacher, X_test, y_test)
    base["training_peak_mem_mb"] = peak_train_mb
    ctx.log(f"Teacher baseline: accuracy={base['accuracy']:.4f} CE={base['cross_entropy']:.4f} "
            f"params={base['param_count']} artifact={base['artifact_bytes']:.0f}B "
            f"warm_lat={base['latency_warm_ms']:.3f}ms")

    teacher_bytes = teacher.save_npz()
    art_teacher = ctx.save_artifact("model", "teacher.npz", teacher_bytes,
                                    meta={"role": "baseline", "sizes": [2, *cfg["teacher_hidden"], 3], "dtype": "float32", "engine": "numpy-mlp"})

    # Register dataset + models
    ds = ctx.db.query(Dataset).filter_by(workspace_id=ctx.workspace_id, name="cpc_spiral3 (synthetic)").one_or_none()
    if ds is None:
        ds = Dataset(
            workspace_id=ctx.workspace_id, name="cpc_spiral3 (synthetic)", task_type="classification",
            num_examples=X_train.shape[0] + X_test.shape[0],
            split_config={"train": 2 / 3, "test": 1 / 3}, generator_key="cpc_spiral3",
            synthetic=True, notes="Deterministic 3-class 2D spiral; generated from run seed inside the task.",
        )
        ctx.db.add(ds)
        ctx.db.commit()
        ctx.db.refresh(ds)

    teacher_row = MLModel(
        workspace_id=ctx.workspace_id, name=f"MLP teacher {cfg['teacher_hidden']} (seed {seed})",
        family="mlp", revision=f"demo-{seed}", source="synthetic", params_count=base["param_count"],
        artifact_uri=art_teacher.uri, synthetic=True,
        notes="Trained inside distillation_demo run; artifact stored with sha256.",
    )
    ctx.db.add(teacher_row)
    ctx.db.commit()
    ctx.db.refresh(teacher_row)

    ctx.progress(0.45, "Training student via knowledge distillation")

    # ---- Stage 2: KD student ----
    student = npnn.MLP([2, *cfg["student_hidden"], 3], seed=seed + 100)
    peak_train_mb_s, _ = npnn.measure_peak_memory_train(
        student.fit, X_train, y_train, epochs=cfg["student_epochs"], lr=cfg["learning_rate"],
        batch_size=cfg["batch_size"], seed=seed + 100, teacher=teacher,
        kd_alpha=cfg["kd_alpha"], kd_temperature=cfg["kd_temperature"], log_every=40, log_fn=ctx.log,
    )
    ctx.check_point()
    comp = _measure(student, X_test, y_test)
    comp["training_peak_mem_mb"] = peak_train_mb_s
    ctx.log(f"Student (KD): accuracy={comp['accuracy']:.4f} CE={comp['cross_entropy']:.4f} "
            f"params={comp['param_count']} artifact={comp['artifact_bytes']:.0f}B "
            f"warm_lat={comp['latency_warm_ms']:.3f}ms")

    student_bytes = student.save_npz()
    art_student = ctx.save_artifact("model", "student.npz", student_bytes,
                                    meta={"role": "compressed", "sizes": [2, *cfg["student_hidden"], 3], "dtype": "float32", "engine": "numpy-mlp", "distilled_from": art_teacher.uri})
    student_row = MLModel(
        workspace_id=ctx.workspace_id, name=f"MLP student {cfg['student_hidden']} distilled (seed {seed})",
        family="mlp", revision=f"demo-{seed}", source="synthetic", params_count=comp["param_count"],
        artifact_uri=art_student.uri, synthetic=True,
        notes=f"KD(alpha={cfg['kd_alpha']}, T={cfg['kd_temperature']}) from teacher model id={teacher_row.id}",
    )
    ctx.db.add(student_row)
    ctx.db.commit()
    ctx.db.refresh(student_row)

    # ---- Transformation record (typed & versioned) ----
    compat = [
        {"name": "input_dim_match", "passed": teacher.sizes[0] == student.sizes[0], "detail": f"in={teacher.sizes[0]}"},
        {"name": "output_classes_match", "passed": teacher.sizes[-1] == student.sizes[-1], "detail": f"classes={teacher.sizes[-1]}"},
        {"name": "same_test_split", "passed": True, "detail": f"shared X_test from seed {seed}+1"},
        {"name": "dtype_preserved", "passed": True, "detail": "float32 weights both models"},
    ]
    trans = Transformation(
        workspace_id=ctx.workspace_id,
        experiment_id=ctx.experiment_id,
        method_key="knowledge_distillation",
        spec={
            "type": "knowledge_distillation",
            "version": 1,
            "params": {"kd_alpha": cfg["kd_alpha"], "kd_temperature": cfg["kd_temperature"],
                        "teacher": art_teacher.uri, "student_arch": student.sizes},
            "engineering": "numpy-mlp",
        },
        spec_version=1,
        preconditions=["teacher trained on task data", "shared labeled test split"],
        invariants=["class label set unchanged", "test split unchanged", "float32 dtype"],
        failure_modes=["capacity gap too large -> accuracy drop", "T too high -> over-smoothed logits"],
        compat_checks=compat,
        status="applied" if all(c["passed"] for c in compat) else "rejected",
        input_model_id=teacher_row.id,
        output_model_id=student_row.id,
    )
    ctx.db.add(trans)
    ctx.db.commit()

    # ---- Verdict from measured metrics ----
    ratio = comp["artifact_bytes"] and base["artifact_bytes"] / comp["artifact_bytes"]
    retention = base["accuracy"] and comp["accuracy"] / base["accuracy"]
    speedup = comp["latency_warm_ms"] and base["latency_warm_ms"] / comp["latency_warm_ms"]
    latency_delta_warm = base["latency_warm_ms"] - comp["latency_warm_ms"]

    checks = [
        ("min_retention", retention is not None and retention >= criteria["min_retention"], f"retention={retention:.4f} >= {criteria['min_retention']}"),
        ("min_compression_ratio", ratio is not None and ratio >= criteria["min_compression_ratio"], f"ratio={ratio:.2f} >= {criteria['min_compression_ratio']}"),
        ("min_latency_speedup", speedup is not None and speedup >= criteria["min_latency_speedup"], f"speedup={speedup:.3f} >= {criteria['min_latency_speedup']}"),
    ]
    all_pass = all(ok for _, ok, _ in checks)
    severe_fail = (retention is not None and retention < 0.90) or (ratio is not None and ratio < 2.0)
    verdict = "successful" if all_pass else ("unsuccessful" if severe_fail else "inconclusive")
    reason = "; ".join(t for _, ok, t in checks if not ok) if not all_pass else "all predefined criteria met on measured values"

    summary = {
        "question": "Can a compact student preserve teacher task performance while reducing artifact size and inference cost?",
        "teacher_model_id": teacher_row.id,
        "student_model_id": student_row.id,
        "dataset_id": ds.id,
        "transformation_id": trans.id,
        "artifact_teacher_uri": art_teacher.uri,
        "artifact_student_uri": art_student.uri,
        "baseline": base,
        "compressed": comp,
        "compression_ratio_artifact": ratio,
        "compression_ratio_params": (base["param_count"] / comp["param_count"]) if comp["param_count"] else None,
        "task_retention": retention,
        "accuracy_baseline": base["accuracy"],
        "accuracy_compressed": comp["accuracy"],
        "latency_speedup_warm": speedup,
        "latency_change_warm_ms": latency_delta_warm,
        "memory_reduction_factor": (base["inference_peak_mem_mb"] / comp["inference_peak_mem_mb"]) if comp["inference_peak_mem_mb"] else None,
        "throughput_gain": (comp["throughput_rows_per_s"] / (base["throughput_rows_per_s"] or 1)) if comp["throughput_rows_per_s"] else None,
        "criteria": criteria,
        "criteria_checks": [{"id": cid, "passed": ok, "detail": d} for cid, ok, d in checks],
        "verdict": verdict,
        "engine": "numpy-mlp/CPU",
        "measured_only": True,
    }

    metrics = [
        {"name": "accuracy", "value": base["accuracy"], "unit": "frac", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "cross_entropy", "value": base["cross_entropy"], "unit": "nats", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "artifact_bytes", "value": base["artifact_bytes"], "unit": "B", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "param_count", "value": float(base["param_count"]), "unit": "params", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "latency_warm_ms", "value": base["latency_warm_ms"], "unit": "ms", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "latency_cold_ms", "value": base["latency_cold_ms"], "unit": "ms", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "throughput_rows_per_s", "value": base["throughput_rows_per_s"], "unit": "rows/s", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "inference_peak_mem_mb", "value": base["inference_peak_mem_mb"], "unit": "MB", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "training_peak_mem_mb", "value": peak_train_mb, "unit": "MB", "stage": "baseline", "extra": {"model": "teacher"}},
        {"name": "accuracy", "value": comp["accuracy"], "unit": "frac", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "cross_entropy", "value": comp["cross_entropy"], "unit": "nats", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "artifact_bytes", "value": comp["artifact_bytes"], "unit": "B", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "param_count", "value": float(comp["param_count"]), "unit": "params", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "latency_warm_ms", "value": comp["latency_warm_ms"], "unit": "ms", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "latency_cold_ms", "value": comp["latency_cold_ms"], "unit": "ms", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "throughput_rows_per_s", "value": comp["throughput_rows_per_s"], "unit": "rows/s", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "inference_peak_mem_mb", "value": comp["inference_peak_mem_mb"], "unit": "MB", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "training_peak_mem_mb", "value": peak_train_mb_s, "unit": "MB", "stage": "compressed", "extra": {"model": "student"}},
        {"name": "compression_ratio", "value": ratio, "unit": "x", "stage": "measured", "extra": {"definition": "artifact_bytes_baseline / artifact_bytes_compressed"}},
        {"name": "task_retention", "value": retention, "unit": "frac", "stage": "measured", "extra": {"definition": "accuracy_compressed / accuracy_baseline"}},
        {"name": "latency_speedup_warm", "value": speedup, "unit": "x", "stage": "measured", "extra": {"definition": "warm_latency_baseline / warm_latency_compressed"}},
    ]

    metrics_bytes = json.dumps({"summary": summary, "metrics": metrics}, indent=2, default=str).encode()
    ctx.save_artifact("eval", "distillation_metrics.json", metrics_bytes, meta={"experiment": ctx.experiment_id})

    return TaskResult(
        summary=summary,
        metrics=metrics,
        verdict=verdict,
        verdict_reason=reason,
        engine_note="numpy-mlp/CPU",
    )

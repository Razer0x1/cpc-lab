"""Benchmark evaluation task: run a registered MLP artifact on the synthetic
classification benchmark with bootstrap confidence intervals.

This is a REAL evaluation of stored artifacts (not simulated). Text tasks (QA,
summarization, perplexity, code generation) require the optional HF engine and real
model registrations; the API returns a clear 'not executed' error rather than fake scores.
"""
from __future__ import annotations

import json
import time

import numpy as np

from ..metrics_math import bootstrap_ci
from app.models import BenchmarkRun
from ..runner import TaskContext, TaskResult, register_task
from . import nn_numpy as npnn

TASK_KEY = "benchmark_synthetic_classification"

DEFAULTS = {"eval_seed": 11, "n_repeats": 3}


@register_task(TASK_KEY)
def run_benchmark(ctx: TaskContext) -> TaskResult:
    raise RuntimeError("Use POST /benchmarks/run — benchmark execution is synchronous and returns the result directly")


def evaluate_model_artifact(
    artifact_bytes: bytes,
    task_cfg: dict,
    *,
    eval_seed: int,
    n_repeats: int,
    model_label: str,
    dataset_generator: str = "cpc_spiral3",
) -> dict:
    """Evaluate a stored npz MLP artifact. Returns measured metrics + CI. Pure function."""
    if dataset_generator != "cpc_spiral3":
        raise ValueError(f"Unsupported benchmark dataset generator: {dataset_generator}")
    net = npnn.MLP.load_npz(artifact_bytes)
    X_test, y_test = npnn.make_spiral3(400, seed=eval_seed + 1)
    accs, ces, lats = [], [], []
    details = []
    for rep in range(n_repeats):
        acc = npnn.accuracy(net, X_test, y_test)
        ce = npnn.cross_entropy(net, X_test, y_test)
        lat = npnn.measure_latency(net, X_test, warmup=3, repeats=10)
        accs.append(acc)
        ces.append(ce)
        lats.append(lat["latency_warm_ms"])
        details.append({"repeat": rep, "accuracy": acc, "cross_entropy": ce, "latency_warm_ms": lat["latency_warm_ms"]})
    acc_ci = bootstrap_ci(accs, seed=eval_seed)
    ce_ci = bootstrap_ci(ces, seed=eval_seed)
    batch = X_test[: min(256, X_test.shape[0])]
    for _ in range(3):
        net.forward_logits(batch)
    t0 = time.perf_counter()
    for _ in range(20):
        net.forward_logits(batch)
    warm_ms = (time.perf_counter() - t0) * 1000 / 20
    return {
        "model_label": model_label,
        "task": task_cfg.get("task", "synthetic_classification"),
        "dataset_generator": dataset_generator,
        "primary_metric": "accuracy",
        "value": accs[0],
        "mean_accuracy": float(np.mean(accs)),
        "accuracy_ci95": list(acc_ci) if acc_ci else None,
        "mean_cross_entropy": float(np.mean(ces)),
        "cross_entropy_ci95": list(ce_ci) if ce_ci else None,
        "latency_warm_ms": warm_ms,
        "n_repeats": n_repeats,
        "per_repeat": details,
        "throughput_rows_per_s": batch.shape[0] / (warm_ms / 1000),
        "eval_seed": eval_seed,
        "note": "measured on host CPU; confidence intervals from bootstrap over repeats",
    }


def finalize_benchmark_run(bench: BenchmarkRun, result: dict, db) -> BenchmarkRun:  # noqa: ANN001
    bench.status = "completed"
    bench.result = result
    return bench

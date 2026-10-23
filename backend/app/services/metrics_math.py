"""Metric math: retention, deltas, bootstrap CIs, Pareto frontier, aggregation."""
from __future__ import annotations

from math import isfinite
from statistics import mean, stdev
from typing import Sequence


def retained_fraction(baseline: float | None, optimized: float | None) -> float | None:
    """fraction of baseline task performance preserved by the optimized system [0..inf)."""
    if baseline is None or optimized is None or baseline == 0:
        return None
    return optimized / baseline


def relative_change_pct(baseline: float | None, optimized: float | None) -> float | None:
    if baseline in (None, 0) or optimized is None:
        return None
    return (optimized - baseline) / baseline * 100.0


def bootstrap_ci(
    values: Sequence[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float] | None:
    """Deterministic bootstrap CI of the mean (numpy-normal state, seeded). Works for n>=2."""
    import numpy as np

    arr = np.asarray([v for v in values if v is not None and isfinite(v)], dtype=float)
    if arr.size == 0:
        return None
    if arr.size == 1:
        return (float(arr[0]), float(arr[0]))
    rng = np.random.default_rng(seed)
    n = arr.size
    idx = rng.integers(0, n, size=(n_boot, n))
    means = arr[idx].mean(axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return (lo, hi)


def describe(values: Sequence[float]) -> dict:
    clean = [v for v in values if v is not None and isfinite(v)]
    if not clean:
        return {"n": 0}
    out: dict = {"n": len(clean), "mean": mean(clean)}
    if len(clean) >= 2:
        out["std"] = stdev(clean)
        out["min"] = min(clean)
        out["max"] = max(clean)
    ci = bootstrap_ci(clean)
    if ci:
        out["ci95_lo"], out["ci95_hi"] = ci
    return out


def pareto_frontier(
    points: Sequence[dict],
    quality_key: str = "quality",
    min_keys: tuple[str, ...] = ("artifact_bytes", "latency_ms"),
) -> list[int]:
    """Indices of non-dominated points.

    A point A dominates B if A.q >= B.q, every key in min_keys of A <= B's, and A strictly
    better in at least one. Points with missing values are ignored.
    """
    def ok(p) -> bool:
        return all(p.get(quality_key) is not None for k in min_keys if p.get(k) is not None)

    usable = [(i, p) for i, p in enumerate(points) if ok(p)]
    front: list[int] = []
    for i, p in usable:
        dominated = False
        for _j, q in usable:
            if q is p:
                continue
            ge = q[quality_key] >= p[quality_key] and all(
                (q[k] is not None and p.get(k) is not None and q[k] <= p[k]) or (p.get(k) is None)
                for k in min_keys
            )
            strict = q[quality_key] > p[quality_key] or any(
                q.get(k) is not None and p.get(k) is not None and q[k] < p[k] for k in min_keys
            )
            if ge and strict:
                dominated = True
                break
        if not dominated:
            front.append(i)
    return front

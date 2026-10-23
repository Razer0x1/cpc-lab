"""Compression math tests: consistent ratio definition, theoretical estimators, validation."""
from __future__ import annotations

import pytest

from app.services.compression import (
    artifact_size_bytes,
    compression_ratio,
    theoretical_quantization_ratio,
    validate_config,
)
from app.services.metrics_math import bootstrap_ci, describe, pareto_frontier, retained_fraction, relative_change_pct


def test_compression_ratio_definition():
    # ratio = original / compressed (>= 1 means smaller artifact)
    assert compression_ratio(8000, 2000) == 4.0
    assert compression_ratio(0, 2000) is None
    assert compression_ratio(8000, 0) is None
    with pytest.raises(ValueError, match="Unknown dtype"):
        artifact_size_bytes(10, "quantum8")


def test_artifact_sizes():
    assert artifact_size_bytes(1000, "float32") == 4000
    assert artifact_size_bytes(1000, "int8") == 1000
    assert artifact_size_bytes(1000, "int4") == 500


def test_theoretical_quantization():
    assert theoretical_quantization_ratio("float32", "int8") == 4.0
    assert theoretical_quantization_ratio("float32", "int4") == 8.0
    assert theoretical_quantization_ratio("float32", "float16") == 2.0


def test_validate_config_kd():
    assert validate_config("knowledge_distillation", {"temperature": -1}) != []
    assert validate_config("knowledge_distillation", {"alpha": 1.5}) != []
    assert validate_config("knowledge_distillation", {"temperature": 2.0, "alpha": 0.5}) == []


def test_validate_config_quantization_and_pruning():
    assert validate_config("weight_quantization", {"bits": 3}) != []
    assert validate_config("weight_quantization", {"bits": 8}) == []
    assert validate_config("pruning_structured", {"sparsity": 1.0}) != []
    assert validate_config("pruning_structured", {"sparsity": 0.5}) == []


def test_retention_and_change():
    assert retained_fraction(0.95, 0.90) == pytest.approx(0.947368, abs=1e-5)
    assert retained_fraction(0, 5) is None
    assert relative_change_pct(1000, 500) == -50.0


def test_bootstrap_ci_sane():
    values = [0.9, 0.9, 0.9, 0.8, 0.95, 0.92]
    lo, hi = bootstrap_ci(values, seed=3)
    assert 0.7 <= lo <= 0.95 and 0.8 <= hi <= 1.0 and lo <= hi


def test_bootstrap_ci_single_and_none():
    assert bootstrap_ci([]) is None
    assert bootstrap_ci([0.42]) == (0.42, 0.42)


def test_describe():
    d = describe([1, 2, 3, 4, 5])
    assert d["n"] == 5 and d["mean"] == 3 and d["min"] == 1


def test_pareto_frontier():
    points = [
        {"quality": 0.90, "artifact_bytes": 10000, "latency_ms": 10.0},  # baseline: dominates nothing, on front
        {"quality": 0.90, "artifact_bytes": 2000, "latency_ms": 8.0},    # better everywhere; dominates [0]
        {"quality": 0.60, "artifact_bytes": 1000, "latency_ms": 5.0},    # lower quality; on front (smaller/faster)
    ]
    front = pareto_frontier(points)
    assert 1 in front and 2 in front and 0 not in front


def test_pareto_handles_missing():
    points = [
        {"quality": None, "artifact_bytes": 10, "latency_ms": 1},
        {"quality": 0.9, "artifact_bytes": 20, "latency_ms": 2},
    ]
    assert pareto_frontier(points) == [1]

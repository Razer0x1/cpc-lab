"""Compression math: consistent, explicitly sourced.

The platform defines compression ratio as:
    compression_ratio = original_artifact_size_bytes / compressed_artifact_size_bytes
Theoretical estimates are labeled `theoretical` and never mixed into measured results.
"""
from __future__ import annotations

from dataclasses import dataclass

DTYPE_BYTES = {
    "float64": 8,
    "float32": 4,
    "float16": 2,
    "bf16": 2,
    "int8": 1,
    "int4": 0.5,
    "binary": 0.125,
}


def artifact_size_bytes(param_count: int, dtype: str, per_param_overhead_bytes: float = 0.0) -> float:
    if dtype not in DTYPE_BYTES:
        raise ValueError(f"Unknown dtype: {dtype}")
    return param_count * (DTYPE_BYTES[dtype] + per_param_overhead_bytes)


def compression_ratio(original_bytes: float, compressed_bytes: float) -> float | None:
    """original artifact size / compressed artifact size (>=1 means smaller artifact)."""
    if compressed_bytes <= 0 or original_bytes <= 0:
        return None
    return original_bytes / compressed_bytes


@dataclass(frozen=True)
class Taxonomy:
    """Known compression/optimization method families and their typical effect direction."""
    QUANTIZATION = "quantization"
    PRUNING_UNSTRUCTURED = "pruning_unstructured"
    PRUNING_STRUCTURED = "pruning_structured"
    DISTILLATION = "distillation"
    LOW_RANK = "low_rank_factorization"
    PARAMETER_SHARING = "parameter_sharing"
    CACHE_OPTIMIZATION = "activation_cache_optimization"
    ARCH_SIMPLIFICATION = "architecture_simplification"
    HYBRID = "hybrid"
    REVERSE_ENGINEERING = "reverse_engineering"


METHOD_CATEGORIES = [
    Taxonomy.QUANTIZATION,
    Taxonomy.PRUNING_UNSTRUCTURED,
    Taxonomy.PRUNING_STRUCTURED,
    Taxonomy.DISTILLATION,
    Taxonomy.LOW_RANK,
    Taxonomy.PARAMETER_SHARING,
    Taxonomy.CACHE_OPTIMIZATION,
    Taxonomy.ARCH_SIMPLIFICATION,
    Taxonomy.HYBRID,
    Taxonomy.REVERSE_ENGINEERING,
]


def theoretical_quantization_ratio(source_dtype: str, target_dtype: str) -> float | None:
    """Artifact-size ratio implied purely by precision change (theoretical, no eval claims)."""
    sb = DTYPE_BYTES.get(source_dtype)
    tb = DTYPE_BYTES.get(target_dtype)
    if not sb or not tb or tb == 0:
        return None
    return sb / tb


def validate_config(method_key: str, cfg: dict) -> list[str]:
    """Runtime validation rules for each method's user-supplied config. Returns error strings."""
    errors: list[str] = []
    if method_key == "knowledge_distillation":
        T = cfg.get("temperature", 2.0)
        alpha = cfg.get("alpha", 0.5)
        if not isinstance(T, (int, float)) or T <= 0:
            errors.append("temperature must be a positive number")
        if not isinstance(alpha, (int, float)) or not (0.0 <= alpha <= 1.0):
            errors.append("alpha (distillation weight) must be within [0, 1]")
    if method_key == "low_rank_factorization":
        for k in ("student_hidden",):
            v = cfg.get(k)
            if not isinstance(v, int) or v < 1:
                errors.append(f"{k} must be a positive integer")
    if method_key in ("weight_quantization", "activation_quantization"):
        bits = cfg.get("bits", 8)
        if bits not in (2, 4, 8):
            errors.append("bits must be one of 2, 4, 8")
    if method_key in ("pruning_structured", "pruning_unstructured"):
        sparsity = cfg.get("sparsity", 0.0)
        if not isinstance(sparsity, (int, float)) or not (0.0 <= sparsity < 1.0):
            errors.append("sparsity must be within [0, 1)")
    if method_key == "reverse_engineering":
        T = cfg.get("temperature", 2.0)
        if not isinstance(T, (int, float)) or not (0.5 <= T <= 10):
            errors.append("temperature must be within [0.5, 10]")
        sw = cfg.get("soft_weight", 0.9)
        if not isinstance(sw, (int, float)) or not (0.0 <= sw <= 1.0):
            errors.append("soft_weight must be within [0, 1]")
        qb = cfg.get("query_budget", 3000)
        if not isinstance(qb, int) or not (200 <= qb <= 50000):
            errors.append("query_budget must be an integer within [200, 50000]")
        qr = cfg.get("query_range", 1.2)
        if not isinstance(qr, (int, float)) or not (0.5 <= qr <= 4.0):
            errors.append("query_range must be within [0.5, 4.0]")
        hidden = cfg.get("surrogate_hidden", [8])
        if (
            not isinstance(hidden, list)
            or not hidden
            or not all(isinstance(h, int) and 1 <= h <= 512 for h in hidden)
        ):
            errors.append("surrogate_hidden must be a list of layer widths (positive integers <= 512)")
    return errors

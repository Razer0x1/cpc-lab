"""Benchmark Center: baseline-vs-compressed evaluation with CIs and Pareto analysis."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Artifact, BenchmarkRun, Dataset, Experiment, MLModel
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access
from ..services.metrics_math import bootstrap_ci, describe, pareto_frontier

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmark center"])

SUPPORTED_TASKS = {
    "synthetic_classification": "CPU demo task — evaluates registered MLP artifacts (real measured scores)",
    # Documented-but-not-enabled tasks require real HF model registrations + optional GPU engine:
    "text_classification": "requires HF engine + registered text model",
    "perplexity": "requires HF engine + registered LM",
    "question_answering": "requires HF engine + registered QA data",
    "summarization": "requires HF engine + registered summarization data",
    "embedding_similarity": "requires embedding model registration",
}


@router.get("/tasks")
def tasks():
    return [{"key": k, "note": v} for k, v in SUPPORTED_TASKS.items()]


class BenchmarkIn(BaseModel):
    model_id: str
    dataset_id: str | None = None
    task: str = Field(default="synthetic_classification")
    seed: int = 11
    n_repeats: int = Field(default=3, ge=1, le=10)
    experiment_id: str | None = None


@router.post("/run", status_code=201)
def run_benchmark(body: BenchmarkIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    if body.task not in SUPPORTED_TASKS:
        raise HTTPException(status_code=422, detail=f"Unknown task. Supported: {list(SUPPORTED_TASKS)}")
    if body.task != "synthetic_classification":
        raise HTTPException(
            status_code=409,
            detail=f"Task '{body.task}' is documented but requires the optional HF engine + registered models. "
                    "No fake scores are produced. CPU-available task: synthetic_classification.",
        )
    model = db.get(MLModel, body.model_id)
    if model is None or model.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Model not found")
    if not model.artifact_uri:
        raise HTTPException(status_code=422, detail="Model has no stored artifact to evaluate")
    dataset = db.get(Dataset, body.dataset_id) if body.dataset_id else None
    generator = (dataset.generator_key if dataset else "") or "cpc_spiral3"

    bench = BenchmarkRun(
        workspace_id=ctx.workspace.id, experiment_id=body.experiment_id,
        model_id=model.id, dataset_id=dataset.id if dataset else None,
        task=body.task, config_json={"n_repeats": body.n_repeats, "generator": generator},
        seed=body.seed, status="running", primary_metric="accuracy",
    )
    db.add(bench)
    db.commit()
    db.refresh(bench)

    from ..services import artifacts as artifact_store
    from ..services.tasks.bench_eval import evaluate_model_artifact

    try:
        weights = artifact_store.read_bytes(model.artifact_uri)
        result = evaluate_model_artifact(
            weights, {"task": body.task}, eval_seed=body.seed, n_repeats=body.n_repeats, model_label=model.name,
            dataset_generator=generator,
        )
    except Exception as e:
        bench.status = "failed"
        bench.error = str(e)[:2000]
        db.commit()
        raise HTTPException(status_code=500, detail=f"Benchmark execution failed: {type(e).__name__}: {e}")

    bench.status = "completed"
    bench.result = result
    db.commit()
    audit(db, "benchmark.complete", user=ctx.user, workspace_id=ctx.workspace.id, object_type="benchmark_run", object_id=bench.id,
          detail={"task": body.task, "model": model.name})
    db.commit()
    return {
        "id": bench.id, "status": "completed", "task": body.task,
        "model": {"id": model.id, "name": model.name},
        "results": result,
    }


@router.get("/runs")
def list_runs(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    runs = db.query(BenchmarkRun).filter_by(workspace_id=ctx.workspace.id).order_by(BenchmarkRun.created_at.desc()).all()
    models = {m.id: m for m in db.query(MLModel).filter_by(workspace_id=ctx.workspace.id).all()}
    return [
        {
            "id": b.id, "task": b.task, "status": b.status, "seed": b.seed,
            "model_id": b.model_id, "model_name": (models.get(b.model_id) or None) and models[b.model_id].name,
            "primary_metric": b.primary_metric,
            "value": (b.result or {}).get("value"), "ci95": (b.result or {}).get("accuracy_ci95"),
            "mean_accuracy": (b.result or {}).get("mean_accuracy"),
            "latency_warm_ms": (b.result or {}).get("latency_warm_ms"),
            "n_repeats": (b.result or {}).get("n_repeats"),
            "created_at": b.created_at.isoformat(),
        }
        for b in runs
    ]


@router.get("/compare")
def compare(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Baseline-vs-optimized comparison + trade-off plot data + Pareto frontier."""
    runs = (
        db.query(BenchmarkRun)
        .filter_by(workspace_id=ctx.workspace.id, status="completed")
        .order_by(BenchmarkRun.created_at.desc())
        .limit(50)
        .all()
    )
    models = {m.id: m for m in db.query(MLModel).filter_by(workspace_id=ctx.workspace.id).all()}
    experiments = {e.id: e for e in db.query(Experiment).filter_by(workspace_id=ctx.workspace.id, status="completed").all()}

    points = []
    comparisons = []
    for b in runs:
        m = models.get(b.model_id)
        r = b.result or {}
        # find experiment summary to tie role baseline/compressed
        role = "unknown"
        for e in experiments.values():
            s = e.result_summary or {}
            if s.get("teacher_model_id") == b.model_id:
                role = "baseline"
                break
            if s.get("student_model_id") == b.model_id or s.get("quantized_model_id") == b.model_id:
                role = "compressed"
                break
        # artifact bytes from measured metrics stored in experiment summaries when available
        artifact_bytes = None
        for e in experiments.values():
            s = e.result_summary or {}
            if s.get("teacher_model_id") == b.model_id:
                artifact_bytes = (s.get("baseline") or {}).get("artifact_bytes")
            if s.get("student_model_id") == b.model_id:
                artifact_bytes = (s.get("compressed") or {}).get("artifact_bytes")
        points.append({
            "benchmark_id": b.id, "model_id": b.model_id,
            "model_name": m.name if m else b.model_id,
            "quality": r.get("mean_accuracy"), "artifact_bytes": artifact_bytes,
            "latency_ms": r.get("latency_warm_ms"), "role": role,
        })
        comparisons.append({
            "id": b.id, "task": b.task, "model_id": b.model_id, "role": role,
            "model_name": m.name if m else b.model_id,
            "accuracy": r.get("mean_accuracy"), "accuracy_ci95": r.get("accuracy_ci95"),
            "cross_entropy": r.get("mean_cross_entropy"), "latency_warm_ms": r.get("latency_warm_ms"),
            "n_repeats": r.get("n_repeats"),
        })
    front = pareto_frontier(points)
    for i, p in enumerate(points):
        p["on_pareto_front"] = i in front
    multi_metric = describe([r.get("mean_accuracy") for r in comparisons if r.get("accuracy") is not None])
    return {
        "comparisons": comparisons,
        "tradeoffs": points,
        "multi_run_summary": multi_metric,
        "note": "Pareto frontier = accuracy vs (artifact size, latency); missing values excluded.",
    }



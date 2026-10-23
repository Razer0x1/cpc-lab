"""Experiment Lab: asynchronous experiment manager (queue/pause/cancel/retry/logs/artifacts)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import Artifact, Experiment, ExperimentLog, ExperimentRun, Metric
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access
from ..services.runner import execute_experiment_sync, job_manager, known_kinds
from ..config import get_settings

router = APIRouter(prefix="/api/v1/experiments", tags=["experiment lab"])


class ExperimentIn(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    kind: str = Field(min_length=2, max_length=40)
    config: dict = {}
    hypothesis_id: str | None = None
    project_id: str | None = None
    baseline_model_id: str | None = None
    dataset_id: str | None = None
    seed: int = 7
    budgets: dict = Field(default={"max_seconds": 60, "max_ram_mb": 512})
    run_now: bool = True


@router.get("/kinds")
def kinds():
    return [{"key": k} for k in known_kinds()]


@router.post("", status_code=201)
def create_experiment(
    body: ExperimentIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)
):
    require_write_access(ctx.user)
    if body.kind not in known_kinds():
        raise HTTPException(status_code=422, detail=f"Unknown experiment kind. Available: {known_kinds()}")
    settings = get_settings()
    if body.kind not in ("distillation_demo", "quantization_int8_eval"):
        # GPU-intensive kinds must be explicitly configured (not enabled by default)
        if not settings.engine_torch:
            raise HTTPException(status_code=409, detail=f"Kind '{body.kind}' requires ENGINE_TORCH=true and GPU extras installed")
    duplicate = db.query(Experiment).filter_by(workspace_id=ctx.workspace.id, name=body.name).one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Experiment name already exists in workspace")
    exp = Experiment(
        workspace_id=ctx.workspace.id, name=body.name, kind=body.kind,
        config_json=body.config, hypothesis_id=body.hypothesis_id, project_id=body.project_id,
        baseline_model_id=body.baseline_model_id, dataset_id=body.dataset_id,
        seed=body.seed, budgets=body.budgets, runner_kind=settings.job_backend, created_by=ctx.user.id,
        status="created" if not body.run_now else "queued",
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    audit(db, "experiment.create", user=ctx.user, workspace_id=ctx.workspace.id, object_type="experiment", object_id=exp.id)
    db.commit()
    if body.run_now:
        job_manager.submit(exp.id)
    return {"id": exp.id, "status": exp.status}


@router.get("")
def list_experiments(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = db.query(Experiment).filter_by(workspace_id=ctx.workspace.id).order_by(Experiment.created_at.desc()).all()
    return [_experiment_row(e) for e in items]


def _experiment_row(e: Experiment) -> dict:
    return {
        "id": e.id, "name": e.name, "kind": e.kind, "status": e.status,
        "progress": e.progress, "seed": e.seed, "hypothesis_id": e.hypothesis_id,
        "verdict": e.success_verdict, "error": e.error,
        "config": e.config_json, "config_version": e.config_version, "budgets": e.budgets,
        "runner": e.runner_kind, "engine_note": e.engine_note,
        "result_summary": e.result_summary, "created_at": e.created_at.isoformat(),
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "finished_at": e.finished_at.isoformat() if e.finished_at else None,
    }


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    runs = db.query(ExperimentRun).filter_by(experiment_id=e.id).order_by(ExperimentRun.seq).all()
    metrics = db.query(Metric).filter_by(experiment_id=e.id).order_by(Metric.name).all()
    arts = db.query(Artifact).filter_by(experiment_id=e.id).all()
    logs_n = db.query(ExperimentLog).filter_by(experiment_id=e.id).count()
    return {
        **_experiment_row(e),
        "runs": [{"id": r.id, "seq": r.seq, "seed": r.seed, "status": r.status,
                  "started_at": r.started_at.isoformat() if r.started_at else None,
                  "finished_at": r.finished_at.isoformat() if r.finished_at else None} for r in runs],
        "metrics": [{"name": m.name, "value": m.value, "unit": m.unit, "stage": m.stage,
                      "seed": m.seed, "extra": m.extra} for m in metrics],
        "artifacts": [{"id": a.id, "kind": a.kind, "filename": a.filename, "sha256": a.sha256,
                        "size_bytes": a.size_bytes} for a in arts],
        "log_count": logs_n,
    }


@router.post("/{experiment_id}/cancel")
def cancel_experiment(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Experiment already {e.status}")
    job_manager.cancel(e.id)
    if e.status in ("queued", "created"):
        e.status = "cancelled"
        db.commit()
    audit(db, "experiment.cancel", user=ctx.user, workspace_id=ctx.workspace.id, object_type="experiment", object_id=e.id)
    db.commit()
    return {"ok": True, "status": e.status}


@router.post("/{experiment_id}/pause")
def pause_experiment(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"Cannot pause a {e.status} experiment")
    job_manager.pause(e.id)
    db.commit()
    return {"ok": True, "status": e.status}


@router.post("/{experiment_id}/resume")
def resume_experiment(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status != "paused":
        raise HTTPException(status_code=409, detail="Experiment is not paused")
    # Demo tasks restart from the beginning on resume (deterministic); documented behavior.
    e.status = "queued"
    db.commit()
    job_manager.resume(e.id)
    return {"ok": True, "status": e.status}


@router.post("/{experiment_id}/retry")
def retry_experiment(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Reset a failed/cancelled/paused experiment for resubmission (no auto-start)."""
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status not in ("failed", "cancelled", "paused"):
        raise HTTPException(status_code=409, detail=f"Retry applies to failed/cancelled/paused (got {e.status})")
    e.status = "created"
    e.error = None
    e.progress = 0.0
    e.success_verdict = None
    e.result_summary = {}
    db.commit()
    audit(db, "experiment.retry", user=ctx.user, workspace_id=ctx.workspace.id, object_type="experiment", object_id=e.id)
    db.commit()
    return {"ok": True, "status": e.status}


@router.post("/{experiment_id}/run")
def run_now(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="Already queued or running")
    e.status = "queued"
    e.error = None
    e.progress = 0.0
    db.commit()
    job_manager.submit(e.id)
    return {"ok": True, "status": e.status}


@router.post("/{experiment_id}/run_sync")
def run_sync(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Deterministic in-request execution (dev/tests). Production uses queued runner."""
    require_write_access(ctx.user)
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if e.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail="Already queued or running")
    db.close()
    execute_experiment_sync(experiment_id)
    session = SessionLocal()
    try:
        e2 = session.get(Experiment, experiment_id)
        return {"ok": True, "status": e2.status, "verdict": e2.success_verdict}
    finally:
        session.close()


@router.get("/{experiment_id}/logs")
def get_logs(experiment_id: str, after_seq: int = -1, limit: int = 200,
             ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    q = db.query(ExperimentLog).filter_by(experiment_id=e.id).order_by(ExperimentLog.seq.desc())
    if after_seq >= 0:
        q = q.filter(ExperimentLog.seq > after_seq)
    rows = q.limit(limit).all()
    rows = list(reversed(rows))
    next_seq = rows[-1].seq if rows else after_seq
    return {
        "logs": [{"seq": r.seq, "ts": r.ts.isoformat(), "level": r.level, "message": r.message} for r in rows],
        "next_seq": next_seq,
        "experiment_status": e.status,
    }


@router.get("/{experiment_id}/logs/stream")
def stream_logs(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """SSE log stream (streaming-by-polling with a cursor; survives restarts/retries)."""
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    exp_id = e.id

    def gen():
        import json
        import time
        cursor = -1
        deadline = time.time() + 300
        while time.time() < deadline:
            db2 = SessionLocal()
            try:
                rows = db2.query(ExperimentLog).filter(ExperimentLog.experiment_id == exp_id, ExperimentLog.seq > cursor).order_by(ExperimentLog.seq).all()
                exp = db2.get(Experiment, exp_id)
                for r in rows:
                    cursor = r.seq
                    yield f"data: {json.dumps({'seq': r.seq, 'ts': r.ts.isoformat(), 'level': r.level, 'message': r.message})}\n\n"
                if exp and exp.status in ("completed", "failed", "cancelled"):
                    yield "event: end\ndata: {}\n\n"
                    return
            finally:
                db2.close()
            time.sleep(0.6)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/{experiment_id}/compare")
def compare_versions(experiment_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Compare this experiment against the other completed experiments in the workspace."""
    e = db.get(Experiment, experiment_id)
    if e is None or e.workspace_id != ctx.workspace.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    peers = db.query(Experiment).filter_by(workspace_id=ctx.workspace.id, status="completed").all()
    rows = []
    for p in peers:
        s = p.result_summary or {}
        rows.append({
            "id": p.id, "name": p.name, "kind": p.kind, "verdict": p.success_verdict,
            "retention": s.get("task_retention"), "ratio": s.get("compression_ratio_artifact"),
            "accuracy_baseline": s.get("accuracy_baseline"), "accuracy_compressed": s.get("accuracy_compressed"),
            "latency_speedup": s.get("latency_speedup_warm"),
            "is_current": p.id == e.id,
        })
    return {"comparison": rows}



"""Compression Workbench: method registry, config validation, compression runs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CompressionMethod, Experiment, MLModel
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access
from ..services.compression import validate_config
from ..services.runner import known_kinds

router = APIRouter(prefix="/api/v1/workbench", tags=["compression workbench"])


@router.get("/methods")
def list_methods(db: Session = Depends(get_db)):
    methods = db.query(CompressionMethod).order_by(CompressionMethod.key).all()
    kinds = known_kinds()
    runnable_kinds = ("distillation_demo", "quantization_int8_eval", "reverse_engineering_extract")
    out = []
    for m in methods:
        runnable = m.engine == "builtin_numpy" and any(
            k in kinds for k in runnable_kinds
        ) and (m.key in ("knowledge_distillation", "weight_quantization", "hybrid_combination", "reverse_engineering"))
        out.append({
            "id": m.id, "key": m.key, "name": m.name, "category": m.category,
            "description": m.description, "config_schema": m.config_schema,
            "prereqs": m.prereqs, "supported_models": m.supported_models,
            "limitations": m.limitations, "engine": m.engine,
            "runnable_now": runnable,
            "runnable_note": (
                "engine ready (CPU demo)" if runnable
                else "engine planned — configuration validated, runner task not yet implemented in this milestone"
            ),
        })
    return out

class CompressionRunIn(BaseModel):
    method_key: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=3, max_length=300)
    config: dict = {}
    model_id: str | None = None  # required for quantization (existing artifact target)
    hypothesis_id: str | None = None
    seed: int = 7
    run_immediately: bool = True


@router.post("/runs", status_code=201)
def create_run(body: CompressionRunIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Create a compression experiment from a workbench method + validated config."""
    require_write_access(ctx.user)
    method = db.query(CompressionMethod).filter_by(key=body.method_key).one_or_none()
    if method is None:
        raise HTTPException(status_code=404, detail="Method not found")
    if method.engine == "planned_documented":
        raise HTTPException(
            status_code=409,
            detail=f"Runner engine for '{method.key}' is planned, not implemented in this milestone. "
                    "Runnable methods: knowledge_distillation (distillation_demo), weight_quantization, "
                    "reverse_engineering, hybrid chains.",
        )
    errors = validate_config(body.method_key, body.config)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    # Map method -> runner task kind and merge config
    if body.method_key == "knowledge_distillation":
        kind = "distillation_demo"
        cfg = {**body.config}
    elif body.method_key == "weight_quantization":
        kind = "quantization_int8_eval"
        if not body.model_id:
            raise HTTPException(status_code=422, detail="model_id required: quantization targets an existing registered model artifact")
        target = db.get(MLModel, body.model_id)
        if target is None or target.workspace_id != ctx.workspace.id:
            raise HTTPException(status_code=404, detail="Target model not found in workspace")
        if not target.artifact_uri:
            raise HTTPException(status_code=422, detail="Target model has no stored artifact to quantize")
        cfg = {**body.config, "model_id": body.model_id}
    elif body.method_key == "hybrid_combination":
        kind = "distillation_demo"  # demo chain: distill now; quantize stage run separately
        cfg = {**body.config}
    elif body.method_key == "reverse_engineering":
        kind = "reverse_engineering_extract"
        if not body.model_id:
            raise HTTPException(
                status_code=422,
                detail="model_id required: reverse engineering extracts a registered model artifact via forward queries",
            )
        target = db.get(MLModel, body.model_id)
        if target is None or target.workspace_id != ctx.workspace.id:
            raise HTTPException(status_code=404, detail="Target model not found in workspace")
        if not target.artifact_uri:
            raise HTTPException(status_code=422, detail="Target model has no stored artifact to query")
        cfg = {**body.config, "model_id": body.model_id}
    else:
        raise HTTPException(status_code=409, detail=f"No engine mapped for method {body.method_key}")

    existing = db.query(Experiment).filter_by(workspace_id=ctx.workspace.id, name=body.name).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An experiment with this name already exists")

    exp = Experiment(
        workspace_id=ctx.workspace.id,
        hypothesis_id=body.hypothesis_id,
        name=body.name,
        kind=kind,
        status="created" if not body.run_immediately else "queued",
        config_json=cfg,
        seed=body.seed,
        runner_kind="thread",
        created_by=ctx.user.id,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    audit(db, "workbench.run_created", user=ctx.user, workspace_id=ctx.workspace.id, object_type="experiment", object_id=exp.id,
          detail={"method_key": body.method_key, "kind": kind})
    db.commit()
    if body.run_immediately:
        from ..services.runner import job_manager
        job_manager.submit(exp.id)
    return {"id": exp.id, "kind": kind, "status": exp.status}


@router.get("/models")
def list_models(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    """Registered models (targets for quantization/eval). Populated after demo runs."""
    models = db.query(MLModel).filter_by(workspace_id=ctx.workspace.id).order_by(MLModel.created_at.desc()).all()
    return [
        {"id": m.id, "name": m.name, "family": m.family, "revision": m.revision, "source": m.source,
         "params_count": m.params_count, "artifact_uri": m.artifact_uri, "synthetic": m.synthetic, "notes": m.notes}
        for m in models
    ]



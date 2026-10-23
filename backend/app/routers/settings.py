"""Settings: compute resources, provider config, workspace privileged info."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ComputeResource
from ..security import WorkspaceCtx, get_ws_ctx 
from ..services.assistant import provider_status

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/compute")
def compute(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = db.query(ComputeResource).filter_by(workspace_id=ctx.workspace.id).all()
    return [
        {"id": c.id, "name": c.name, "kind": c.kind, "status": c.status,
         "limits": c.limits, "utilization": c.utilization, "updated_at": c.updated_at.isoformat()}
        for c in items
    ]


@router.get("/assistant")
def assistant_config():
    return provider_status()


@router.get("/environment")
def environment(ctx: WorkspaceCtx = Depends(get_ws_ctx)):
    """Non-secret environment facts useful for debugging deployments."""
    from ..config import get_settings

    s = get_settings()
    return {
        "env": s.env,
        "database": ("sqlite" if s.is_sqlite else s.database_url.split("@")[-1].split("/")[0]),
        "storage_backend": s.storage_backend,
        "job_backend": s.job_backend,
        "engine_torch": s.engine_torch,
        "assistant_provider": s.assistant_provider or "(offline mode)",
        "rate_limit_per_minute": s.rate_limit_per_minute,
    }





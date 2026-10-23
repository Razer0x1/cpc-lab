"""Artifact download & integrity endpoints (workspace-authorized)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Artifact
from ..security import WorkspaceCtx, audit, get_ws_ctx 
from ..services import artifacts as artifact_store

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("")
def list_artifacts(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    items = (
        db.query(Artifact).filter_by(workspace_id=ctx.workspace.id)
        .order_by(Artifact.created_at.desc()).limit(200).all()
    )
    return [
        {"id": a.id, "kind": a.kind, "filename": a.filename, "size_bytes": a.size_bytes,
         "sha256": a.sha256, "experiment_id": a.experiment_id, "created_at": a.created_at.isoformat()}
        for a in items
    ]


@router.get("/{artifact_id}/download")
def download_artifact(artifact_id: str, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    art = db.get(Artifact, artifact_id)
    if art is None or art.workspace_id != ctx.workspace.id:
        # Do not leak existence to other workspaces
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        data = artifact_store.read_bytes(art.uri)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Artifact path invalid")
    except ValueError as e:
        # integrity failure or unreadable
        audit(db, "artifact.integrity_failure", user=ctx.user, workspace_id=ctx.workspace.id,
              object_type="artifact", object_id=art.id, detail={"error": str(e)})
        db.commit()
        raise HTTPException(status_code=409, detail=f"Artifact integrity check failed: {e}")
    audit(db, "artifact.download", user=ctx.user, workspace_id=ctx.workspace.id, object_type="artifact", object_id=art.id)
    db.commit()
    fname = art.filename or "artifact"
    if art.kind == "model":
        fname = fname if fname.endswith(".npz") else f"{fname}.npz"
    return Response(
        content=data,
        media_type=art.content_type,
        headers={"Content-Disposition": f"attachment; filename={fname}", "X-Artifact-SHA256": art.sha256},
    )





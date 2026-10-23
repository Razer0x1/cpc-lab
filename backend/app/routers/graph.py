"""Knowledge Graph endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import WorkspaceCtx, get_ws_ctx 
from ..services.graph import build_graph

router = APIRouter(prefix="/api/v1/graph", tags=["knowledge graph"])


@router.get("")
def get_graph(
    kinds: str | None = Query(default=None, description="Comma-separated node kinds to include"),
    ctx: WorkspaceCtx = Depends(get_ws_ctx),
    db: Session = Depends(get_db),
):
    data = build_graph(db, ctx.workspace.id)
    if kinds:
        keep = {k.strip() for k in kinds.split(",")}
        data["nodes"] = [n for n in data["nodes"] if n["kind"] in keep]
        keep_ids = {n["id"] for n in data["nodes"]}
        data["edges"] = [e for e in data["edges"] if e["source"] in keep_ids and e["target"] in keep_ids]
    return data





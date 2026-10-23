"""Overview dashboard endpoint (database-backed metrics only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import WorkspaceCtx, get_ws_ctx 
from ..services import overview as overview_service

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("")
def get_overview(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    return overview_service.compute_overview(db, ctx.workspace.id)





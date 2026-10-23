"""AI research assistant endpoints (provider-independent, offline-capable)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import WorkspaceCtx, audit, get_ws_ctx, require_write_access
from ..services import assistant as assistant_service

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.get("/status")
def status():
    """Provider connection status + configuration guidance (no secrets returned)."""
    return assistant_service.provider_status()


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


@router.post("/chat")
def chat(body: ChatIn, ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    result = assistant_service.chat(db, ctx.workspace.id, ctx.user.id, body.message)
    audit(db, "assistant.chat", user=ctx.user, workspace_id=ctx.workspace.id, detail={"mode": result["meta"].get("mode")})
    db.commit()
    return result


@router.get("/conversations")
def conversations(ctx: WorkspaceCtx = Depends(get_ws_ctx), db: Session = Depends(get_db)):
    from ..models import AssistantConversation

    items = (
        db.query(AssistantConversation)
        .filter_by(workspace_id=ctx.workspace.id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(30)
        .all()
    )
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat(), "messages": c.messages} for c in items]



"""Auth endpoints: login, me, workspace context."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Workspace, WorkspaceMember
from ..security import (
    WorkspaceCtx, audit, create_access_token, get_current_user, get_ws_ctx, hash_password,
)
from ..config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=200)


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.lower()).one_or_none()
    from ..security import verify_password

    if user is None or not verify_password(body.password, user.hashed_password):
        audit(db, "auth.login_failed", object_type="user", detail={"email": body.email}, ip=request.client.host if request.client else "")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user)
    audit(db, "auth.login", user=user, ip=request.client.host if request.client else "")
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "is_admin": user.is_admin},
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Open registration (demo/dev): creates the account plus a personal workspace."""
    import re as _re

    settings = get_settings()
    if settings.env == "production" and not settings.allow_public_registration:
        raise HTTPException(status_code=403, detail="Public registration disabled in production")

    existing = db.query(User).filter_by(email=body.email.lower()).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email.lower(), hashed_password=hash_password(body.password), display_name=body.display_name)
    db.add(user)
    db.flush()

    # Self-serve onboarding: every new account owns a personal workspace immediately.
    base_slug = _re.sub(r"[^a-z0-9]+", "-", body.email.lower().split("@")[0]).strip("-") or "workspace"
    slug = base_slug
    n = 1
    while db.query(Workspace).filter_by(slug=slug).one_or_none() is not None:
        n += 1
        slug = f"{base_slug}-{n}"
    display = user.display_name or user.email
    ws = Workspace(name=f"Personal — {display}", slug=slug)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin"))

    audit(db, "auth.register", user=user, workspace_id=ws.id, object_type="user", object_id=user.id,
          detail={"email": user.email})
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "workspace_id": ws.id}


@router.get("/me")
def me(
    ctx: WorkspaceCtx = Depends(get_ws_ctx),
    user: User = Depends(get_current_user),
):
    return {
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "is_admin": user.is_admin},
        "workspace": {"id": ctx.workspace.id, "name": ctx.workspace.name, "slug": ctx.workspace.slug},
        "role": ctx.role,
    }


@router.get("/workspaces")
def workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    )
    return [{"id": ws.id, "name": ws.name, "slug": ws.slug, "role": role} for ws, role in rows]




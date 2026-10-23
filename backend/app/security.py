"""Authentication, workspace authorization, audit logging, password hashing (stdlib pbkdf2)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AuditEvent, User, Workspace, WorkspaceMember

settings = get_settings()
PBKDF2_ITERATIONS = 240_000
_ROLE_RANK = {"viewer": 0, "member": 1, "owner": 2}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, dk_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "admin": user.is_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(auth.removeprefix("Bearer ").strip())
    user = db.get(User, claims.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def require_write_access(user: User) -> None:
    if getattr(user, "_is_workspace_viewer", False):
        raise HTTPException(status_code=403, detail="Viewer role has read-only access")


class WorkspaceCtx:
    """Resolved workspace context with role, used by all workspace-scoped routers."""

    def __init__(self, workspace: Workspace, user: User, role: str) -> None:
        self.workspace = workspace
        self.user = user
        self.role = role
        user._is_workspace_viewer = role == "viewer"


def resolve_workspace(request: Request, user: User, db: Session) -> WorkspaceCtx:
    ws_id = request.headers.get("X-Workspace-ID") or ""
    memberships: dict[str, str] = {}
    for m, ws in (
        db.query(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    ):
        memberships[m.workspace_id] = m.role
    if ws_id:
        if ws_id not in memberships:
            raise HTTPException(status_code=403, detail="No access to requested workspace")
        role = memberships[ws_id]
    else:
        if not memberships:
            raise HTTPException(status_code=403, detail="User has no workspaces")
        ws_id, role = next(iter(memberships.items()))
    if not ws_id:
        raise HTTPException(status_code=403, detail="User has no workspaces")
    ws = db.get(Workspace, ws_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceCtx(ws, user, role)


def get_ws_ctx(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WorkspaceCtx:
    return resolve_workspace(request, user, db)


def audit(
    db: Session, action: str, *, user: User | None = None, workspace_id: str | None = None,
    object_type: str = "", object_id: str | None = None, detail: dict | None = None, ip: str = ""
) -> None:
    db.add(
        AuditEvent(
            workspace_id=workspace_id,
            user_id=user.id if user else None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            detail=detail or {},
            ip=ip,
        )
    )


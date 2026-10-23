"""Shared test helpers (import-safe; no cleanup side effects)."""
from __future__ import annotations

import time


def make_viewer(client) -> tuple[str, dict]:
    """Register a second user (own personal workspace) for isolation tests.

    Since self-serve registration provisions a personal workspace, this user
    can use the app, but cannot see the admin workspace's data.
    """
    email = f"viewer-{int(time.time() * 1000000)}@test.lab"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "viewer-pass-1"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "viewer-pass-1"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def make_workspaceless_user(client) -> tuple[str, dict]:
    """User with zero memberships (created directly in the DB — the register
    endpoint self-provisions a workspace, so this account mirrors legacy/migrated
    users and exercises the central "no workspace" 403 path)."""
    import uuid

    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    email = f"nowsh-{uuid.uuid4().hex[:10]}@test.lab"
    with SessionLocal() as db:
        db.add(User(email=email, hashed_password=hash_password("lonely-pass-1"), display_name="No WS"))
        db.commit()
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "lonely-pass-1"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def run_demo(client, headers, name: str) -> str:
    """Create and synchronously execute a distillation demo. Returns experiment id."""
    r = client.post("/api/v1/experiments", headers=headers, json={"name": name, "kind": "distillation_demo", "run_now": False})
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]
    r = client.post(f"/api/v1/experiments/{exp_id}/run_sync", headers=headers)
    assert r.status_code == 200, r.text
    return exp_id

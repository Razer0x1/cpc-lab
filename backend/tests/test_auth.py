"""Auth + authorization tests."""
from __future__ import annotations


def test_login_success(client, admin_token):
    assert admin_token


def test_login_bad_password(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@test.lab", "password": "wrong-password"})
    assert r.status_code == 401


def test_login_validation(client):
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422


def test_protected_route_requires_token(client):
    r = client.get("/api/v1/overview")
    assert r.status_code == 401


def test_me_returns_workspace(client, auth_headers):
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "admin@test.lab"
    assert body["workspace"]["slug"] == "main"
    assert body["role"] == "owner"


def test_workspaceless_user_gets_403_on_workspace_routes(client):
    """Legacy/migrated users with no memberships are explicitly denied."""
    from tests.helpers import make_workspaceless_user

    _token, headers = make_workspaceless_user(client)
    r = client.get("/api/v1/overview", headers=headers)
    assert r.status_code == 403
    assert "no workspace" in r.json()["detail"].lower()


def test_registered_users_are_isolated_by_personal_workspace(client, auth_headers):
    from tests.helpers import make_viewer

    # A registered user has their own workspace and sees an empty experiment list,
    # never the admin workspace's data.
    _token, v_headers = make_viewer(client)
    r = client.get("/api/v1/experiments", headers=v_headers)
    assert r.status_code == 200
    assert r.json() == []  # isolation: admin's experiments are not visible
    # admin experiments are not listable under a forged workspace header either
    r = client.get("/api/v1/experiments", headers={**auth_headers, "X-Workspace-ID": "ffff"})
    assert r.status_code == 403


def test_register_creates_personal_workspace_then_login(client):
    """Self-serve registration: account + personal workspace, then login works."""
    import uuid

    email = f"reg-{uuid.uuid4().hex[:10]}@test.lab"
    password = "register-pass-8"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Reg Tester"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert body["id"] and body["workspace_id"]

    r2 = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]

    r3 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200, r3.text
    me = r3.json()
    assert me["workspace"]["id"] == body["workspace_id"]
    assert me["workspace"]["name"].startswith("Personal")
    assert me["role"] == "admin"

    r4 = client.get(
        "/api/v1/auth/workspaces", headers={"Authorization": f"Bearer {token}"}
    )
    assert r4.status_code == 200
    assert {ws["id"] for ws in r4.json()} == {body["workspace_id"]}


def test_register_duplicate_email_conflict(client):
    import uuid

    email = f"dup-{uuid.uuid4().hex[:10]}@test.lab"
    payload = {"email": email, "password": "register-pass-8", "display_name": "Dup"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_register_slug_collision_gets_suffix(client):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    a = f"coll-{suffix}@test.lab"
    b = f"coll.{suffix}@test.lab"  # same local-part slug after slug-ing
    pa, pb = "register-pass-8", "register-pass-9"
    r1 = client.post("/api/v1/auth/register", json={"email": a, "password": pa})
    r2 = client.post("/api/v1/auth/register", json={"email": b, "password": pb})
    assert r1.status_code == 201 and r2.status_code == 201
    ws_a = client.post(
        "/api/v1/auth/login", json={"email": a, "password": pa}
    ).json()["access_token"]
    ws_b = client.post(
        "/api/v1/auth/login", json={"email": b, "password": pb}
    ).json()["access_token"]
    me_a = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ws_a}"}).json()
    me_b = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ws_b}"}).json()
    assert me_a["workspace"]["slug"] != me_b["workspace"]["slug"]

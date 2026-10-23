"""Pytest configuration: isolated per-run SQLite database + TestClient + auth helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEST_DATA_DIR = BACKEND_DIR / ".test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)
TEST_DB = TEST_DATA_DIR / "test_cpc.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ADMIN_EMAIL"] = "admin@test.lab"
os.environ["ADMIN_PASSWORD"] = "test-admin-pass"
os.environ["JWT_EXPIRES_MINUTES"] = "60"
os.environ["ENV"] = "test"
os.environ["ENGINE_TORCH"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

try:  # remove stale db from a previous run (engine may still be open in another session)
    for f in (TEST_DB, TEST_DATA_DIR / "test_cpc.db-wal", TEST_DATA_DIR / "test_cpc.db-shm"):
        if f.exists():
            f.unlink(missing_ok=True)
except PermissionError:
    pass


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@test.lab", "password": "test-admin-pass"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

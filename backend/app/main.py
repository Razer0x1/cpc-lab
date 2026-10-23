"""CPC Lab API assembly: middleware, routers, startup seeding.

Security: JWT auth, workspace authorization, per-IP rate limiting, audit logging,
request validation via Pydantic, path-safe artifact storage.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import (
    assistant, artifacts, auth, benchmarks, experiments, graph, hypotheses,
    overview, papers, reports, research, settings as settings_router, workbench,
)
from .services.runner import known_kinds
from .services import tasks as _register_tasks  # noqa: F401  (registers experiment runners)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (dev fallback) and seed idempotently. Production uses Alembic migrations.
    if settings.is_sqlite:
        Base.metadata.create_all(bind=engine)
    from .seed import seed_db

    with SessionLocal() as db:
        seed_db(db)
        db.commit()
    yield


class RateLimitMiddleware:
    """Per-IP sliding-window ASGI limiter (single-process; gateway rate limiting for HA)."""

    def __init__(self, app, per_minute: int) -> None:
        self.app = app
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=per_minute * 2))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        client_ip = (scope.get("client") or ("unknown",))[0]
        now = time.monotonic()
        q = self.hits[client_ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            resp = JSONResponse({"detail": "Rate limit exceeded; retry later"}, status_code=429,
                                headers={"Retry-After": "60"})
            await resp(scope, receive, send)
            return
        q.append(now)
        await self.app(scope, receive, send)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Cross-Paradigm Compression research platform API",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Workspace-ID", "Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def audit_write_requests(request: Request, call_next):
    started = time.time()
    response = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        try:
            from .models import AuditEvent

            with SessionLocal() as db:
                db.add(
                    AuditEvent(
                        action=f"http.{request.method.lower()}",
                        object_type="http", object_id=request.url.path,
                        detail={"status": response.status_code, "ms": round((time.time() - started) * 1000, 1)},
                        ip=(request.client.host if request.client else ""),
                    )
                )
                db.commit()
        except Exception:
            pass
    return response


@app.get("/health")
def health():
    from sqlalchemy import text

    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "kinds": known_kinds()}


for r in (auth.router, overview.router, research.router, hypotheses.router, workbench.router,
          experiments.router, benchmarks.router, graph.router, papers.router, reports.router,
          assistant.router, settings_router.router, artifacts.router):
    app.include_router(r)

# Deployment Guide

## 1. Local development

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt -r requirements-extras.txt
alembic upgrade head              # or: let startup create dev tables
uvicorn app.main:app --reload --port 8000

# frontend
cd ../frontend
npm install
npm run dev
```

Default admin (seeded on startup, idempotent): `ADMIN_EMAIL` / `ADMIN_PASSWORD`
(defaults `admin@cpc.lab` / `change-me-admin`). Public registration is enabled in dev and
gated off in production without `ALLOW_PUBLIC_REGISTRATION`.

## 2. Docker Compose (production-shaped)

```bash
cp .env.example .env    # set JWT_SECRET + ADMIN_PASSWORD + POSTGRES_PASSWORD
docker compose up --build
```

Services:

| Service | Image | Purpose |
|---|---|---|
| `api` | built from `backend/Dockerfile` | Alembic migrations on boot → uvicorn on :8000 |
| `worker` | same image | `celery -A app.worker worker --concurrency 2` (Redis broker) |
| `postgres` | postgres:16-alpine | default strong store for compose deployment |
| `redis` | redis:7-alpine | Celery broker/results |
| `frontend` | built from `frontend/Dockerfile` | Next.js standalone on :3000 |

Notes:
- `NEXT_PUBLIC_API_URL` is a **build arg** — it is baked into the browser bundle. Set it to the
  address the *user's browser* uses to reach the API (e.g. `http://localhost:8000` locally or
  `https://api.your-domain.com` publicly).
- Correspondingly set `CORS_ORIGINS` to the frontend's public origin(s).
- Artifacts persist in the `cpc_data` volume (`DATA_DIR=/app/data`); Postgres data in `pg_data`.

## 3. Migrations

```bash
alembic upgrade head      # apply
alembic downgrade base    # roll back
# after model changes:
alembic revision --autogenerate -m "describe change"
```

Startup also creates tables as a dev fallback; production deployments should rely on Alembic.

## 4. Job backends

- `JOB_BACKEND=thread` (default): in-process ThreadPool; ideal for single-host CPU demos and tests.
- `JOB_BACKEND=celery`: experiments are enqueued (`cpc.run_experiment`) to the `worker` service via Redis.
  The docker-compose deployment configures this automatically.

## 5. Storage backends

- `STORAGE_BACKEND=local`: content-addressed directory under `DATA_DIR/artifacts/<ws>/<kind>/<sha>__<name>`.
- `STORAGE_BACKEND=s3`: set `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`.
  (Credentials read from the standard AWS env chain.) SHA-256 integrity is verified on download in both modes.

## 6. GPU extras (optional)

`backend/requirements-gpu.txt` carries the torch/transformers/peft/onnx runtime stack. It is
**not installed by default**; CPU demo engines run the full workflow without it. Enable with
`ENGINE_TORCH=true` only after installing the extras — GPU-heavy experiment kinds refuse to
start otherwise (explicit 409 with instructions).

## 7. Security checklist for production

- [ ] `JWT_SECRET` is long and random; cookies/tokens expire per `JWT_EXPIRES_MINUTES`.
- [ ] `ADMIN_PASSWORD` changed from the seeded default.
- [ ] `ALLOW_PUBLIC_REGISTRATION` reviewed (registration closed unless intentional).
- [ ] `CORS_ORIGINS` restricted to real frontend origins.
- [ ] TLS terminates at a reverse proxy (Caddy/nginx) if exposed beyond localhost.
- [ ] Postgres volume + artifact volume backups scheduled.
- [ ] `RATE_LIMIT_PER_MINUTE` tuned for deployment size.

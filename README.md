# CPC Lab — Cross-Paradigm Compression Lab

**CPC Lab** is a full-stack research platform for cross-paradigm neural-network compression.
It turns research questions into falsifiable hypotheses, links them to literature with verified
provenance, executes **real, measured, reproducible experiments** (CPU-friendly by default),
evaluates them statistically, and exports scientific reports.

> **Scientific policy:** every number the platform shows is computed from the database,
> every metric is measured by executed code, and anything that is only *planned* is clearly
> labeled as such (or refuses to run with an explicit error) — the platform never fabricates
> research results, benchmark scores, or API responses.

![status](https://img.shields.io/badge/tests-50%2F50%20passing-emerald) ![python](https://img.shields.io/badge/python-3.13-skyblue) ![next](https://img.shields.io/badge/next-14.2-blue)

---

## What works end-to-end (implemented, verified by tests)

| Area | What actually runs |
|---|---|
| **Research Explorer** | Curated cross-paradigm catalog (seeded: 10 research entries, 10 methods, 11 real papers), filtering, user-added entries, one-click hypothesis drafting. |
| **Hypothesis Studio** | Full lifecycle: draft → approve/reject → evidence levels (`idea_only` → `independently_reproduced`). Evidence level never rises from paper searches. |
| **Experiment Lab** | Real async job execution (in-process thread runner; Celery+Redis optional). Real flagship demo: **teacher→student knowledge distillation** (teacher MLP `[2,64,64,3]` → student `[2,8,3]`) on the synthetic `cpc_spiral3` dataset, written in pure NumPy — accuracy/CE metrics, artifact bytes, warm/cold latency, throughput, tracemalloc peak memory are **measured**, not assumed. Also: **int8 quantization + evaluation** of registered artifacts, and **black-box reverse engineering** (compact surrogate extracted from the target's forward queries only, with held-out agreement, soft-fidelity CE, artifact and latency measurements). Logs (cursor-polled streaming + SSE endpoint), pause/resume/cancel/retry lifecycle. |
| **Compression Workbench** | Method registry with **validated** config schemas. Methods with an implemented engine (distillation, weight quantization, reverse-engineering extraction, hybrid chains) run for real; planned engines (pruning, low-rank, caching, LLM/4-bit…) are explicitly marked *planned — not implemented* and reject runs with 409 instead of faking results. |
| **Benchmark Center** | Baseline-vs-compressed evaluation on registered artifacts with **bootstrap 95% CIs**, multi-repeat measurements, and a measured **Pareto frontier** (accuracy vs artifact bytes vs latency). |
| **Knowledge Graph** | Provenance graph (hypotheses ⇄ experiments ⇄ papers ⇄ models ⇄ methods) with distinguished *verified* (user-established) vs *structural* relations, rendered interactively. |
| **Paper Library** | Live scholarly metadata search (OpenAlex, arXiv, Crossref — no API keys), ingestion deduplication, and user-verified source linking. Failures (offline/rate limit) surface as explicit errors — never as fake results. |
| **Reports** | Scientific reports (Markdown/HTML/PDF) generated from runs: objective, hypothesis, setup, **documented limitations**, measured results, reproducibility steps, references. |
| **Accounts** | Seeded admin (`ADMIN_EMAIL`/`ADMIN_PASSWORD`) **plus self-serve registration**: `POST /api/v1/auth/register` (open in dev; gated by `ALLOW_PUBLIC_REGISTRATION=false` in production) creates the account **and provisions a personal workspace** (owner role), so a new user can register a model and run experiments immediately. Registration is also available in the UI at `/register` (linked from the login page). |
| **Offline & realtime** | The workspace UI keeps working when the API is unreachable: last-known GET responses are cached locally and served (clearly labeled by an offline banner), writes fail honestly, and the banner clears automatically when the backend is reachable again — no fabricated data ever appears while offline. "Realtime" is cursor-polled live logs (fast cadence while running) plus 4–10 s page polling; an SSE logs endpoint exists for stream consumers. |
| **Integrity** | Artifacts are content-addressed local storage (S3 optional) with **SHA-256 verification on every download**. |

**Not implemented (honestly labeled in the UI):** GPU/torch engines, HF-model task benchmarks
(text classification / QA / summarization…), pruning/LTT/4-bit engines. They either require
`ENGINE_TORCH=true` with the optional GPU extras, or are the next milestone.

## The research engine (six stages)

```
Research question → Hypothesis (falsifiable, evidence-classified)
   → Method + validated config → Experiment (seeded, queued, measured)
      → Benchmarks (CIs, Pareto) → Report (MD/HTML/PDF + repro steps)
```

Every stage is coupled: entries **draft** hypotheses, hypotheses **link** to experiments,
experiments register **models**, benchmarks **evaluate** those models, reports **cite** the
links the user verified in the Paper Library.

---

## Architecture

```
openproject/
├── backend/               FastAPI + SQLAlchemy 2 + Alembic + NumPy engine
│   ├── app/
│   │   ├── main.py        app assembly, CORS, rate limiting, startup seeding
│   │   ├── config.py      12-factor env config
│   │   ├── models.py      20 tables (users, workspaces, research, experiments, …)
│   │   ├── security.py    PBKDF2 hashes, JWT, workspace context, audit events
│   │   ├── routers/       13 routers, 55 routes (see docs/api-reference.md)
│   │   ├── services/      runner, distillation/quantization/bench engines,
│   │   │                  artifact store (SHA-256), papers search, reports, graph
│   │   └── worker.py      optional Celery worker (Redis broker)
│   ├── alembic/           migrations (upgrade/downgrade verified)
│   ├── tests/             50 tests incl. full real-demo lifecycle, quantized-artifact
│   │                      benchmarking, black-box reverse-engineering extraction and
│   │                      measured Pareto data resolution for extraction outputs
│   ├── tools/make_figures.py  deterministic SVG figures from the live DB
│   │                          (measured Pareto chart, provenance graph → docs/figures/)
│   ├── requirements.txt   pinned runtime deps
│   ├── requirements-extras.txt   celery, redis, boto3, reportlab, psycopg2 …
│   └── requirements-gpu.txt      optional torch/HF stack (NOT installed by default)
└── frontend/              Next.js 14 (App Router) + React 18 + Tailwind 3
    ├── src/app/(app)/     Overview, Explorer, Hypotheses, Workbench, Experiment Lab,
    │                      Benchmarks, Graph, Papers, Reports, Settings
    ├── src/app/login/     auth page (JWT in localStorage, workspace header)
    ├── src/app/register/  self-serve registration (auto-provisions a personal workspace)
    └── src/lib/api.ts     typed fetch client (auth + workspace headers, 401 handling,
                           offline detection + labeled local GET cache when unreachable)
```

**Backend runtime:** SQLite by default (`DATABASE_URL` env switches to Postgres/psycopg2), thread
job runner by default (`JOB_BACKEND=celery` + Redis for production), local artifact store by
default (`STORAGE_BACKEND=s3` optional).

## Quickstart (local dev)

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt -r requirements-extras.txt

# admin seed credentials via env (defaults: admin@cpc.lab / change-me-admin)
copy ..\.env.example .env        # optional
alembic upgrade head             # create schema (or let startup create it for dev)

uvicorn app.main:app --reload --port 8000
```

API is at `http://localhost:8000` — docs (`/docs`), `/health`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev     # http://localhost:3000
```

Sign in with the seeded admin (`ADMIN_EMAIL` / `ADMIN_PASSWORD`; defaults
`admin@cpc.lab` / `change-me-admin`), or create your own account via
**Create an account** on the login page (`/register`) — new users get a personal
workspace automatically. The UI ships dark-first with the CPC Lab brand.

### 3. First research session (all real)

1. **Experiment Lab** → create *"KD spiral demo"*, kind `distillation_demo`, seed 7, Run synchronously.
   → completes in seconds with measured metrics + `teacher.npz` / `student.npz` artifacts.
2. **Workbench** → pick *Weight Quantization* → select the registered teacher model → run.
3. **Benchmark Center** → evaluate teacher & student; the comparison table shows **95% CIs** and the trade-off plot marks the **Pareto frontier**.
4. **Reports** → generate Markdown/HTML/PDF from the experiment (limitations + repro steps included).
5. **Knowledge Graph** → see hypothesis ⇄ experiment ⇄ paper ⇄ model provenance.

## Docker (production-shaped)

```bash
cp .env.example .env      # set JWT_SECRET, ADMIN_PASSWORD first!
docker compose up --build
# frontend http://localhost:3000  |  api http://localhost:8000  |  celery worker + postgres + redis
```

- The `api` container runs `alembic upgrade head` on boot, then uvicorn.
- The `worker` container runs `celery -A app.worker worker` (Redis broker).
- Artifacts persist in the `cpc_data` volume; Postgres in `pg_data`.

## Environment variables (backend)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/cpc.db` | SQLAlchemy connection (Postgres: `postgresql+psycopg2://…`) |
| `JWT_SECRET` | `dev-only-secret-change-me` | **must change in production** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@cpc.lab` / `change-me-admin` | seeded admin credentials |
| `DATA_DIR` | `./data` | root for DB + artifact store |
| `STORAGE_BACKEND` | `local` | or `s3` (+ `S3_*`) |
| `JOB_BACKEND` | `thread` | or `celery` (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`) |
| `ENGINE_TORCH` | `false` | GPU/torch engine gate (optional extras) |
| `CORS_ORIGINS` | localhost:3000 | comma-separated allowed origins |
| `RATE_LIMIT_PER_MINUTE` | `120` | auth'd endpoints rate limit |
| `SCHOLAR_CONTACT_EMAIL` | *(empty)* | OpenAlex/Crossref politeness email |
| `ASSISTANT_*` | *(empty)* | optional LLM provider (offline rules mode otherwise) |

Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`), optional dev proxy `API_PROXY_TARGET`.

## Tests

```bash
cd backend && .venv\Scripts\python.exe -m pytest tests -q   # 50 passed
cd frontend && npm run build                                # type-checked build
```

The experiment tests run the **actual** NumPy distillation, quantization and black-box
reverse-engineering engines and assert measured metric sanity (e.g. student artifact is
genuinely smaller than the teacher artifact; surrogate extraction fidelity is bounded).

## Figures (rendered from the live database)

- [`docs/figures/pareto-measured.svg`](docs/figures/pareto-measured.svg) — measured accuracy ↔ artifact-size Pareto chart (all completed benchmark runs)
- [`docs/figures/provenance-graph.svg`](docs/figures/provenance-graph.svg) — knowledge-graph export (nodes/edges rebuilt from DB)

Both regenerate deterministically: `cd backend && .venv\Scripts\python.exe tools\make_figures.py`

## Docs

- [`docs/api-reference.md`](docs/api-reference.md) — full route surface with auth + workspace rules
- [`docs/research-methodology.md`](docs/research-methodology.md) — evidence policy, measurement rules, reproducibility contract
- [`docs/deployment.md`](docs/deployment.md) — env vars, migrations, storage backends, workers, security checklist

## Deploying (GitHub → Render API + Vercel frontend)

The stack is split deliberately: **Vercel hosts the Next.js frontend** (its natural home);
the **FastAPI engine must run on a long-running container host** because it needs background
threads (experiment runner), a persistent SQLite artifact store, and SSE/polling — serverless
platforms like Vercel cannot provide those.

1. **Push to GitHub** — `git remote add origin https://github.com/<you>/cpc-lab.git && git push -u origin main`
2. **API on Render** (or Railway/Fly/VPS): render.com → *New + → Blueprint* → pick the repo
   → `render.yaml` provisions the Docker backend + 1 GB persistent disk (`/data`) + generated
   `JWT_SECRET`/admin password. Note the service URL, e.g. `https://cpc-lab-api.onrender.com`.
   Set `CORS_ORIGINS` to your Vercel URL once known.
3. **Frontend on Vercel**: vercel.com → Add New → Project → import the repo →
   **Root Directory: `frontend`** → Environment variable
   `NEXT_PUBLIC_API_URL=https://cpc-lab-api.onrender.com` → Deploy.
4. Update `CORS_ORIGINS` on Render with the final `https://<project>.vercel.app` and redeploy.

## Security model

PBKDF2-SHA256 password hashing · HS256 JWT (`JWT_EXPIRES_MINUTES`, default 12 h) ·
workspace-scoped every query (`create_tables`-free; FK + `X-Workspace-ID` header context) ·
role gates (`admin`/`member`/`viewer` — viewers are read-only) · rate limiting · audit events ·
artifact integrity (SHA-256) on every download · no secrets returned by any endpoint.

---

**Logo:** the CPC Lab mark is the provided brand logo, recreated as an inline SVG
(`frontend/src/components/brand.tsx`, `frontend/public/logo.svg`, `logo-mark.svg`).

**Footer:** the app shell carries the required notice — *© 2026 Razer0x1 — All rights reserved.*

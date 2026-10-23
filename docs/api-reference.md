# API Reference

Base URL: `http://localhost:8000` — all routes below are under `/api/v1` (except `/health`).
Auth: `Authorization: Bearer <JWT>` from `POST /api/v1/auth/login`.
Workspace context comes from the `X-Workspace-ID` header; every query is workspace-scoped.
Roles: `admin` > `member` (write) > `viewer` (read-only).

## Auth — `/api/v1/auth`
| Method | Path | Notes |
|---|---|---|
| POST | `/login` | `{email, password}` → `{access_token, user}` (401 on bad creds; audited) |
| POST | `/register` | `{email, password, display_name?}` → `201 {id, email, workspace_id}`: creates the account **and provisions a personal workspace** (admin/owner role) so the user can work immediately. Open in dev; 403 in production unless `ALLOW_PUBLIC_REGISTRATION=true`. `409` on duplicate e-mail. |
| GET | `/me` | `{user, workspace, role}` |
| GET | `/workspaces` | memberships of current user |

## Overview — `/api/v1/overview`
| GET | `` | dashboard aggregates (database-computed; `None` = no measured data) |

## Research Explorer — `/api/v1/research`
| GET | `/entries` | filters: `field, architecture, technique, evidence, resource, year_from, q` |
| POST | `/entries` | create research entry (question ≥ 1 char) |
| POST | `/entries/{id}/hypothesis` | draft a structured hypothesis from an entry |

## Hypothesis Studio — `/api/v1/hypotheses`
| GET | `` | list with linked experiments |
| POST | `` | create (evidence_level starts `idea_only`) |
| GET/PATCH | `/{id}` | patch: statement fields, status (`draft/approved/rejected`), `evidence_level` |
| POST | `/{id}/link-paper` | user-verified provenance link |

## Compression Workbench — `/api/v1/workbench`
| GET | `/methods` | registry incl. `runnable_now` + honest `runnable_note` (runnable engines: `knowledge_distillation`, `weight_quantization`, `reverse_engineering`, `hybrid_combination`) |
| POST | `/runs` | validate config → create mapped experiment (`409` for planned engines, `422` on schema violations). `reverse_engineering` requires `model_id` (black-box queries against a registered artifact; extracts a compact surrogate and measures held-out agreement + compression) |
| GET | `/models` | registered models (targets for quantize/eval) |

## Experiment Lab — `/api/v1/experiments`
| GET | `/kinds` | registered runner task kinds |
| POST | `` | create (`run_now=false` → status `created`, never auto-starts) |
| GET | `` | list |
| GET | `/{id}` | detail: runs, metrics, artifacts, log_count |
| POST | `/{id}/run` | queue to runner (created/cancelled/failed/paused → queued) |
| POST | `/{id}/run_sync` | deterministic in-request execution (dev/tests) |
| POST | `/{id}/cancel` `/{id}/pause` `/{id}/resume` `/{id}/retry` | lifecycle (retry resets to `created`, no auto-start) |
| GET | `/{id}/logs` | cursor-poll, `?after_seq=` |
| GET | `/{id}/logs/stream` | SSE stream (5 min window) |
| GET | `/{id}/compare` | vs other completed experiments |

## Benchmark Center — `/api/v1/benchmarks`
| GET | `/tasks` | task registry with honest capability notes |
| POST | `/run` | measured evaluation w/ bootstrap CIs (`409` for tasks that need the HF engine) |
| GET | `/runs` | history |
| GET | `/compare` | comparisons + trade-off points + Pareto frontier |

## Paper Library — `/api/v1/papers`
| GET | `/search?q=…&sources=openalex,arxiv,crossref&limit=` | cached (30 min), rate limited; errors → `{errors}` |
| POST | `` | ingest (dedupe by `source+external_id`) |
| GET | `` | library |
| POST / DELETE | `/{id}/link` `/{id}/link/{ref_id}` | provenance links (verified actions) |

## Reports — `/api/v1/reports`
| POST | `/generate` | `{experiment_id, format: markdown/html/pdf, title?}` → artifact + report row |
| GET | `` | list |
| GET | `/{id}/download` | file stream + `X-Artifact-SHA256` |

## Artifacts — `/api/v1/artifacts`
| GET | `` | list (metadata only) |
| GET | `/{id}/download` | SHA-256 verified; `409` on integrity failure; no cross-workspace leaks |

## Knowledge Graph — `/api/v1/graph`
| GET | `` | `{nodes[], edges[]}`; `?kinds=hypothesis,experiment` filter. Edge `established: verified` |

## Settings — `/api/v1/settings`
| GET | `/compute` | compute resources |
| GET | `/assistant` | provider status (no secrets) |
| GET | `/environment` | non-secret deployment facts |

## Assistant — `/api/v1/assistant`
| GET | `/status` | provider/offline mode + setup help |
| POST | `/chat` | `{message, conversation_id?}` → `{content, meta, conversation_id}` |
| GET | `/conversations` | latest 30 conversations |

## Misc
| GET | `/health` | liveness |

# DOCS.md

## Project Overview

repo-radar is a multi-agent code auditing service.
A user submits a public Git repository.
The system clones it, dispatches specialised auditor agents in parallel, and returns structured typed findings plus a diff against the previous run of the same repository.

The product is the agent pipeline, not the report.
What makes it worth building is that the pipeline is evaluated, budgeted, and regression-proof: every auditor is measured against golden fixtures in CI, and every run has a hard cost ceiling.

Audience: developers and hiring teams who want a repeatable read on a repository's health over time, rather than a one-off score with no baseline.

## Core Features

- Submit a public Git repository for audit
- Parallel specialised auditors (dead code, security, test quality) sharing one run
- Findings returned through tool schemas as typed objects, never parsed from prose
- Per-run cost ceiling, checked before each call rather than after, so concurrent auditors cannot all slip through
- Evaluation harness: golden fixture repositories with planted defects, precision and recall asserted in CI
- Record and replay cassettes so agent tests run offline, free, and deterministic
- Live run progress over WebSocket
- Run history with a diff classifying each finding as new, fixed, or persisting
- Bring your own key: the visitor supplies their own model credentials, session scoped, never persisted

## Tech Stack

- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS. shadcn/ui is added in Phase 6, when there are components that need it.
- Backend: FastAPI, Python 3.11, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL
- Tooling: uv (Python environments, with `uv.lock` committed for reproducible installs), ruff (lint and format), mypy strict, pytest
- Auth: none in Phase 0. Bring your own key arrives in Phase 4.
- Deployment: not decided. Phase 7.

No Redis.
Background work runs through FastAPI BackgroundTasks and run state lives in Postgres.
Redis plus arq is reconsidered at Phase 5, only if concurrent runs measurably outgrow a single process.

## Folder Conventions

```
frontend/src/app/               Next.js App Router pages
frontend/src/components/ui/     shadcn base components (never edit by hand)
frontend/src/components/        custom app components
frontend/src/lib/               api client, shared helpers
frontend/src/types/             types mirroring backend response schemas

backend/app/routers/            FastAPI route handlers (thin: no business logic)
backend/app/schemas/            Pydantic request and response schemas
backend/app/auditors/           one module per auditor: prompt and tool description
backend/app/llm/                provider-agnostic client, cassettes, cost accounting
backend/app/orchestrator.py     fans auditors out, merges outcomes
backend/app/budget.py           per-run spending ceiling
backend/app/cloner.py           safe clone of an untrusted repository URL
backend/app/evaluation.py       precision and recall against golden fixtures
backend/tests/fixtures/         fixture repositories with planted defects
backend/tests/cassettes/        recorded model replies (generated, not hand written)
backend/tests/eval/             the regression gate for prompt changes

Not created yet, deliberately. Each arrives with the phase that needs it, so
nothing sits in the tree unwired:

backend/app/services/           business logic                        (Phase 4)
backend/app/repositories/       database query layer                  (Phase 4)
backend/app/models/             SQLAlchemy ORM models                 (Phase 4)
backend/alembic/                migrations                            (Phase 4)
```

## API Base URL

- Development: http://localhost:8001
- Production: not deployed yet

All routes live under the `/api/v1` prefix.
The unprefixed path must 404, so no client can depend on an unversioned URL.

## Environment Variables

Copy `.env.example` to `backend/.env`.
Every variable has a development default, so a fresh clone runs without configuration.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | backend | Postgres connection string. Matches docker-compose.yml. |
| `DEBUG` | backend | Echoes SQL when true. Off in production. |
| `ALLOWED_ORIGINS` | backend | CORS allowlist. |
| `NEXT_PUBLIC_API_URL` | frontend | Backend base URL. Goes in `frontend/.env.local`. |
| `LLM_MODEL` | backend | Model to call, and part of the cassette key. |
| `LLM_CASSETTE_MODE` | backend | `replay` (default, no key needed) or `record`. |
| `GEMINI_API_KEY` | backend | Only needed to record cassettes. |

No model API key is stored server side.
Keys arrive per session through the bring your own key path in Phase 4.

## Running Locally

```bash
docker compose up -d                       # Postgres

cd backend
uv sync --extra dev                        # installs exactly what uv.lock pins
.venv/bin/uvicorn app.main:app --reload --port 8001  # http://localhost:8001

cd ../frontend
npm install
npm run dev                                # http://localhost:3000
```

## Verification

Every check below must pass before a change is merged.
CI runs exactly these commands.

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q

cd frontend
npm run lint
npm run typecheck
npm run build
```

Backend tests call the app in process through ASGITransport.
They open no sockets and need no database, which is why CI runs them without a Postgres service.

## Build Order

See `secure/ROADMAP.md` for the eight phases, the files each produces, and the condition that proves each is finished.

| Phase | State | Note |
| --- | --- | --- |
| 0 Foundation | done | Both sides build and test on a clean clone. |
| 1 LLM client and cassettes | done | Replay is the default, so no key is needed to run anything. |
| 2 First auditor | **machinery done, not measured** | The evaluation skips until cassettes are recorded. |
| 3 Orchestrator and budget | **machinery done, not measured** | Same reason. Three auditors, concurrent, one shared ceiling. |
| 4 API and BYOK | done | Runs execute in the background; the caller's own key, never stored. |
| 5 History and diff | done | A run is compared against the previous completed run of the same repository. |
| 6 Frontend | next | |

**Redis checkpoint, decided at Phase 5: still not needed.** Background work runs
through FastAPI BackgroundTasks and run state lives in Postgres.
Nothing so far has needed a job queue or a shared cache.
Revisit when concurrent runs measurably outgrow a single process, and add `arq` then, with the measurement that justified it.

Phases 2 and 3 are not finished until this runs and the evaluations stop skipping:

```bash
cd backend
GEMINI_API_KEY=... .venv/bin/python scripts/record_cassettes.py
.venv/bin/pytest tests/eval -v
```

Six calls on a free tier. Until then the auditors' prompts are unmeasured: everything around the model is tested, the model's own detection quality is not.

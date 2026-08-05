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
- Per-run token and cost budget with a hard cap and early abort
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
backend/app/services/           business logic
backend/app/repositories/       database query layer
backend/app/models/             SQLAlchemy ORM models
backend/app/schemas/            Pydantic request and response schemas
backend/app/auditors/           one module per auditor: prompt, tool schema, fixtures
backend/app/llm/                provider-agnostic client and cassette layer
backend/tests/                  tests, fixtures, cassettes
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
Phase 0 is complete.

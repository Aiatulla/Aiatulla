# Contributing

Thanks for looking. This document covers how to run the project, what a change
has to satisfy, and the few rules that are specific enough to be worth stating.

## Setup

```bash
docker compose up -d                    # Postgres
cd backend && uv sync --extra dev
.venv/bin/alembic upgrade head
cd ../frontend && npm install
```

**You do not need an API key.** Tests replay recorded model responses, so the
whole suite runs offline and free. A key is only needed to re-record cassettes or
to run a real audit.

## Definition of done

CI runs exactly these. Run them before opening a pull request.

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app                          # strict
.venv/bin/pytest -q --cov=app               # 90% minimum

cd ../frontend
npm run lint && npm run typecheck && npm run test && npm run build
```

**Zero skipped tests is the bar.** A skipped evaluation is not a passing
evaluation. If `tests/eval/` starts skipping, a prompt or tool schema changed and
the cassettes need re-recording.

## Rules worth stating

Most conventions are visible in the code. These are the ones that are not.

**Never make a run look cleaner than it was.** A run where every auditor failed is
`FAILED`, not `COMPLETED` with an empty list. An empty findings list must never
render as "nothing found" unless auditors actually ran. This has gone wrong twice,
in two different layers.

**Money is `Decimal`.** Costs are summed across thousands of calls and compared
against a ceiling.

**An unpriced model raises.** Do not add a zero-cost fallback; it would let a run
bypass its budget silently.

**The repository URL is untrusted input.** Do not relax anything in `cloner.py`
without reading the test that covers it. Each limit names the attack it blocks.

**The API key belongs to the caller.** It must never reach the database, a log
line, an error message, or a response.

**Fixtures contain deliberately bad code.** `tests/fixtures/` is input data for
the auditors, not tests. It is excluded from lint and from collection. Do not fix
it.

## Adding an auditor

An auditor is not finished until it is measured.

1. A module in `backend/app/auditors/` — a name, a system prompt, a tool description
2. A fixture repository under `tests/fixtures/`, containing **correct code as well
   as planted defects**. Without the correct code, precision is meaningless: an
   auditor flagging every line would score perfectly.
3. Expectations in that fixture's `golden.json`, with a `why_planted` note each
4. A case in `CASES` in `tests/eval/test_auditor_eval.py`
5. Recorded cassettes

See [docs/EVALUATION.md](docs/EVALUATION.md).

## Adding a provider

A file in `backend/app/llm/providers/` satisfying `LLMClient`, a prefix in
`_KEY_PREFIXES`, a default model, and prices in `usage.py`. Copy an existing
adapter — the three deliberately do not share a base class, because their wire
formats disagree on every detail that matters.

## Commits and pull requests

[Conventional Commits](https://www.conventionalcommits.org/), one logical change
per commit. Explain **why** in the body; the diff already says what.

```
fix(budget): price a call before making it, not after

The ceiling never fired. Every auditor makes one call, and all of them
were admitted before any had reported a cost.
```

A pull request should say what changed, why, and how to check it. If you changed
a prompt, include the before and after precision and recall.

## Reporting a bug

Include the repository URL you audited if it is public, the run status and error,
and which provider and model. Never paste an API key — if one has appeared
anywhere, rotate it first.

## Security

Do not open a public issue for an exploitable vulnerability. See
[SECURITY.md](SECURITY.md).

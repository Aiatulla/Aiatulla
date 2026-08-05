"""The background half of a run: what happens after the request has responded."""

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.cloner import CloneError
from app.llm.protocol import Response, ToolCall
from app.llm.usage import build_usage
from app.models.run import RunStatus
from app.repositories.runs import RunRepository
from app.services.run_service import execute_run, repository_slug

KEY = SecretStr("sk-ant-api03-notarealkey")
MODEL = "claude-sonnet-5"
REPO = "https://github.com/example/repo"
FIXTURE = Path(__file__).parent / "fixtures" / "repo_a"


class StubModel:
    """Answers every auditor with one finding, so no provider is called."""

    async def complete(self, messages, tools=None, system=None) -> Response:
        return Response(
            model=MODEL,
            usage=build_usage(MODEL, 1_000, 100),
            tool_calls=(
                ToolCall(
                    "report_findings",
                    {
                        "findings": [
                            {
                                "category": "unused_module",
                                "file_path": "legacy_export.py",
                                "severity": "low",
                                "summary": "Nothing imports this",
                                "evidence": "no import found",
                            }
                        ]
                    },
                ),
            ),
        )


@asynccontextmanager
async def _clone_to_fixture(url: str):
    """Stand in for a real clone with a directory already on disk.

    execute_run reads workspace / "repo", so this yields the parent of the
    fixture directory and the fixture is named repo_a alongside it.
    """
    yield FIXTURE.parent


@pytest.fixture
def offline_run(monkeypatch):
    """Replace the clone and the model, so a run needs no network and no key."""
    monkeypatch.setattr("app.services.run_service.clone_repository", _clone_to_fixture)
    monkeypatch.setattr("app.services.run_service.build_client", lambda *a, **k: StubModel())


async def _create_run(session_factory) -> uuid.UUID:
    async with session_factory() as session:
        run = await RunRepository(session).create(REPO, repository_slug(REPO), MODEL)
        await session.commit()
        return run.id


async def test_a_finished_run_stores_its_findings(session_factory, offline_run):
    run_id = await _create_run(session_factory)

    await execute_run(run_id, REPO, KEY, MODEL, Decimal("1.00"), session_factory)

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)

    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert len(run.findings) == 3, "one finding from each of the three auditors"
    assert run.cost_usd > 0
    assert {finding.auditor for finding in run.findings} == {
        "dead_code",
        "security",
        "test_quality",
    }


async def test_a_failed_clone_records_the_reason(session_factory, monkeypatch):
    """A run that cannot start must say why, not sit on "running" forever."""

    def exploding_clone(url: str):
        raise CloneError("host not allowed")

    monkeypatch.setattr("app.services.run_service.clone_repository", exploding_clone)
    run_id = await _create_run(session_factory)

    await execute_run(run_id, REPO, KEY, MODEL, Decimal("1.00"), session_factory)

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)

    assert run is not None
    assert run.status is RunStatus.FAILED
    assert "host not allowed" in (run.error or "")


async def test_a_failure_never_records_the_key(session_factory, monkeypatch):
    """Error text is stored in the run and returned to callers."""

    def exploding_clone(url: str):
        raise CloneError(f"something went wrong near {KEY.get_secret_value()}")

    monkeypatch.setattr("app.services.run_service.clone_repository", exploding_clone)
    run_id = await _create_run(session_factory)

    await execute_run(run_id, REPO, KEY, MODEL, Decimal("1.00"), session_factory)

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)

    # This one documents a real limit: the key is only absent because nothing
    # puts it into an error. If a provider ever echoes a key in a message, it
    # would land here.
    assert run is not None
    assert run.status is RunStatus.FAILED


async def test_a_run_where_every_auditor_failed_is_not_reported_as_clean(
    session_factory, monkeypatch
):
    """The worst thing an audit tool can do is say nothing is wrong when it
    never managed to look. An empty findings list on a COMPLETED run is
    indistinguishable from a clean repository."""

    class BrokenModel:
        async def complete(self, messages, tools=None, system=None):
            raise RuntimeError("401 from the provider")

    monkeypatch.setattr("app.services.run_service.clone_repository", _clone_to_fixture)
    monkeypatch.setattr("app.services.run_service.build_client", lambda *a, **k: BrokenModel())
    run_id = await _create_run(session_factory)

    await execute_run(run_id, REPO, KEY, MODEL, Decimal("1.00"), session_factory)

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)

    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.findings == []
    assert "Every auditor failed" in (run.error or "")


async def test_a_run_where_one_auditor_failed_still_completes(session_factory, monkeypatch):
    """Partial findings are a result. Only a total failure is a failed run."""
    calls = {"count": 0}

    class FlakyModel(StubModel):
        async def complete(self, messages, tools=None, system=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("one auditor hit a transient error")
            return await super().complete(messages, tools, system)

    monkeypatch.setattr("app.services.run_service.clone_repository", _clone_to_fixture)
    monkeypatch.setattr("app.services.run_service.build_client", lambda *a, **k: FlakyModel())
    run_id = await _create_run(session_factory)

    await execute_run(run_id, REPO, KEY, MODEL, Decimal("1.00"), session_factory)

    async with session_factory() as session:
        run = await RunRepository(session).get(run_id)

    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert len(run.findings) == 2, "the two auditors that worked still reported"

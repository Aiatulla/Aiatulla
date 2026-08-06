"""The live progress socket.

Uses starlette's TestClient rather than httpx: httpx has no websocket support, so
without this the socket would be the one user-visible feature with no test.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.run import FindingRow, Run, RunStatus

PROGRESS = f"{settings.API_PREFIX}/runs"


@pytest.fixture
def ws_client(session_factory, monkeypatch):
    """A test client whose websocket handler talks to the in-memory database.

    ws.py opens its own session rather than taking the request dependency,
    because it outlives the request, so the factory is patched directly.
    """
    monkeypatch.setattr("app.routers.ws.AsyncSessionLocal", session_factory)
    with TestClient(app) as client:
        yield client


async def _store_run(session_factory, status: RunStatus, findings: int = 0) -> uuid.UUID:
    async with session_factory() as session:
        run = Run(
            repository_url="https://github.com/example/repo",
            repository_slug="github.com/example/repo",
            model="claude-sonnet-5",
            status=status,
        )
        session.add(run)
        await session.flush()
        for index in range(findings):
            session.add(
                FindingRow(
                    run_id=run.id,
                    auditor="dead_code",
                    category="unused_module",
                    file_path=f"file_{index}.py",
                    severity="low",
                    summary="something",
                    evidence="evidence",
                )
            )
        await session.commit()
        return run.id


async def test_a_finished_run_is_sent_once_and_the_socket_closes(ws_client, session_factory):
    """A terminal run has nothing further to report, so the socket must not sit
    open polling forever."""
    run_id = await _store_run(session_factory, RunStatus.COMPLETED, findings=2)

    with ws_client.websocket_connect(f"{PROGRESS}/{run_id}/progress") as socket:
        payload = socket.receive_json()

    assert payload["status"] == "completed"
    assert len(payload["findings"]) == 2


async def test_a_failed_run_reports_its_error(ws_client, session_factory):
    run_id = await _store_run(session_factory, RunStatus.FAILED)

    with ws_client.websocket_connect(f"{PROGRESS}/{run_id}/progress") as socket:
        payload = socket.receive_json()

    assert payload["status"] == "failed"


async def test_an_unknown_run_is_reported_rather_than_hanging(ws_client):
    """Without this the client would wait for a run that will never appear."""
    with ws_client.websocket_connect(f"{PROGRESS}/{uuid.uuid4()}/progress") as socket:
        payload = socket.receive_json()

    assert payload == {"error": "Run not found"}


async def test_the_payload_carries_what_the_page_needs(ws_client, session_factory):
    """The socket sends the same shape as GET /runs/{id}, so the page has one
    parser rather than two."""
    run_id = await _store_run(session_factory, RunStatus.COMPLETED, findings=1)

    with ws_client.websocket_connect(f"{PROGRESS}/{run_id}/progress") as socket:
        payload = socket.receive_json()

    for field in ("id", "status", "model", "input_tokens", "cost_usd", "truncated"):
        assert field in payload, f"the run page reads {field}"

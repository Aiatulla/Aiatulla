import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """An HTTP client wired straight to the app, with no network or running server.

    ASGITransport calls the app in-process, which keeps tests fast and lets CI
    run them without starting uvicorn or Postgres.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_transport(monkeypatch):
    """Route every httpx.AsyncClient through a canned response.

    Shared by all provider adapter tests. It exercises our translation to and
    from each provider's wire format without a network call or an API key, and
    hands back the captured requests so a test can assert what was sent.
    """

    def install(payload: dict, status: int = 200) -> list[httpx.Request]:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(status, json=payload)

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        return captured

    return install

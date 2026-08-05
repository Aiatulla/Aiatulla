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

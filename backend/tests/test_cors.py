import pytest

from app.config import settings


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000", "http://localhost:8080"],
)
async def test_allowed_origin_receives_cors_header(client, origin):
    """A browser on an allowed origin must get the header back, or the call is blocked."""
    response = await client.get(f"{settings.API_PREFIX}/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


async def test_unknown_origin_is_not_allowed(client):
    """Without this, a wildcard or misconfiguration would let any site call the API."""
    response = await client.get(
        f"{settings.API_PREFIX}/health",
        headers={"Origin": "http://evil.example.com"},
    )

    assert "access-control-allow-origin" not in response.headers

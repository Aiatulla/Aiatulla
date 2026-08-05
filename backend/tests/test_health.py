from app.config import settings


async def test_health_returns_ok(client):
    response = await client.get(f"{settings.API_PREFIX}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.VERSION}


async def test_health_is_versioned(client):
    """The unprefixed path must 404, so clients cannot depend on an unversioned URL."""
    response = await client.get("/health")

    assert response.status_code == 404

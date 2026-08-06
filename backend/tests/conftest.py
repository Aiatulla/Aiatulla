import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.base import Base
from app.rate_limit import reset_rate_limits

# SQLite in memory, not Postgres. The models use SQLAlchemy's dialect-neutral
# types, so the schema is the same one Alembic creates, and CI needs no database
# service. Anything genuinely Postgres-specific would have to be tested against
# Postgres instead.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Start every test with an empty rate limiter.

    It is module-level state shared by the process, so without this the suite
    trips its own limit part way through and later tests fail for a reason that
    has nothing to do with what they are testing.
    """
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture
async def session_factory():
    """A fresh, empty database per test.

    A single connection is held for the whole test, because an in-memory SQLite
    database disappears when its last connection closes.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=None)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    await engine.dispose()


@pytest.fixture
async def client(session_factory):
    """An HTTP client wired straight to the app, with no network or running server.

    ASGITransport calls the app in-process, which keeps tests fast and lets CI
    run them without starting uvicorn or Postgres.
    """

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


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

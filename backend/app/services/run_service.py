import uuid
from decimal import Decimal
from urllib.parse import urlparse

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auditors.base import Auditor
from app.auditors.dead_code import DeadCodeAuditor
from app.auditors.security import SecurityAuditor
from app.auditors.test_quality import TestQualityAuditor
from app.cloner import clone_repository
from app.llm.providers import DEFAULT_MODELS, build_client, provider_for_key
from app.orchestrator import run_audit
from app.repositories.runs import RunRepository

ALL_AUDITORS: list[Auditor] = [DeadCodeAuditor(), SecurityAuditor(), TestQualityAuditor()]


def repository_slug(url: str) -> str:
    """Reduce a URL to a stable "host/owner/name", so runs of the same repository group together.

    Without this, "…/repo" and "…/repo.git" would look like two different
    repositories and never be compared against each other.
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/").removesuffix(".git")
    return f"{parsed.hostname}/{path}".lower()


def default_model_for(api_key: str) -> str:
    return DEFAULT_MODELS[provider_for_key(api_key)]


async def execute_run(
    run_id: uuid.UUID,
    repository_url: str,
    api_key: SecretStr,
    model: str,
    max_usd: Decimal,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Clone a repository, audit it, and record what happened.

    Runs in the background after the request has already responded, so it opens
    its own session: the request's session is closed by then.

    The key is a parameter held in memory for the length of this call. It is
    never written to the database and never logged.

    Every failure is caught and recorded against the run. An exception escaping
    here would vanish into the background task and leave the run stuck on
    "running" forever, with nothing to tell the caller why.
    """
    async with session_factory() as session:
        repository = RunRepository(session)
        await repository.mark_running(run_id)
        await session.commit()

    try:
        client = build_client(api_key.get_secret_value(), model=model)

        async with clone_repository(repository_url) as workspace:
            result = await run_audit(
                client=client,
                repository=workspace / "repo",
                auditors=ALL_AUDITORS,
                max_usd=max_usd,
                model=model,
            )

        async with session_factory() as session:
            await RunRepository(session).save_result(run_id, result)
            await session.commit()

    except Exception as exc:
        # Broad on purpose: a clone, a network call and a model reply can all
        # fail in ways there is no useful list of. The run must not be left
        # looking like it is still going.
        async with session_factory() as session:
            await RunRepository(session).mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            await session.commit()

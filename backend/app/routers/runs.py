import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.byok import require_api_key
from app.cloner import CloneError, validate_repo_url
from app.database import AsyncSessionLocal, get_db
from app.repositories.runs import RunRepository
from app.schemas.run import CreateRunRequest, RunResponse, RunSummary
from app.services.run_service import default_model_for, execute_run, repository_slug

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    api_key: Annotated[SecretStr, Depends(require_api_key)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RunResponse:
    """Start an audit and return immediately.

    202, not 201: the run has been accepted, not finished. Auditing takes far
    longer than a request should, so the work continues in the background and the
    caller polls the run or watches the websocket.
    """
    try:
        validate_repo_url(body.repository_url)
    except CloneError as exc:
        # Rejected here rather than inside the background task, so a bad URL is
        # an error the caller sees rather than a run that quietly fails later.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    model = body.model or default_model_for(api_key.get_secret_value())

    repository = RunRepository(session)
    run = await repository.create(
        repository_url=body.repository_url,
        repository_slug=repository_slug(body.repository_url),
        model=model,
    )
    await session.commit()

    background_tasks.add_task(
        execute_run,
        run_id=run.id,
        repository_url=body.repository_url,
        api_key=api_key,
        model=model,
        max_usd=body.max_usd,
        session_factory=AsyncSessionLocal,
    )

    return RunResponse.model_validate(run)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RunResponse:
    """Fetch one run and its findings. No key needed: a run holds no secrets."""
    run = await RunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return RunResponse.model_validate(run)


@router.get("", response_model=list[RunSummary])
async def list_runs(session: Annotated[AsyncSession, Depends(get_db)]) -> list[RunSummary]:
    """Most recent runs, without findings."""
    runs = await RunRepository(session).list_recent()
    return [RunSummary.model_validate(run) for run in runs]

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.runs import RunRepository
from app.schemas.diff import DiffEntryResponse, RunDiffResponse
from app.schemas.run import RunSummary
from app.services.diff_service import diff_against_nothing, diff_findings

router = APIRouter(tags=["history"])


@router.get("/runs/{run_id}/diff", response_model=RunDiffResponse)
async def get_run_diff(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RunDiffResponse:
    """Compare a run against the previous completed run of the same repository.

    This is the question a one-off score cannot answer: not "how bad is this
    repository" but "what changed since last time".
    """
    repository = RunRepository(session)

    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    previous = await repository.find_previous_completed(run)

    # A first run is described rather than refused: every finding is new, because
    # there is no baseline yet.
    diff = (
        diff_findings(list(previous.findings), list(run.findings))
        if previous is not None
        else diff_against_nothing(list(run.findings))
    )

    return RunDiffResponse(
        run_id=run.id,
        previous_run_id=previous.id if previous else None,
        is_first_run=previous is None,
        counts={
            "new": len(diff.new),
            "fixed": len(diff.fixed),
            "persisting": len(diff.persisting),
        },
        entries=[DiffEntryResponse.model_validate(entry) for entry in diff.entries],
    )


@router.get("/repos/{slug:path}/history", response_model=list[RunSummary])
async def get_repository_history(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RunSummary]:
    """Every run of one repository, newest first.

    The slug takes a :path converter because it contains slashes, as in
    github.com/psf/requests.
    """
    runs = await RunRepository(session).list_for_repository(slug.lower())
    return [RunSummary.model_validate(run) for run in runs]

import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.finding import Severity
from app.services.diff_service import Change


class DiffEntryResponse(BaseModel):
    """One finding and how it compares to the previous run."""

    model_config = ConfigDict(from_attributes=True)

    change: Change
    auditor: str
    category: str
    file_path: str
    severity: Severity
    summary: str


class RunDiffResponse(BaseModel):
    """What changed between a run and the previous run of the same repository."""

    run_id: uuid.UUID
    previous_run_id: uuid.UUID | None
    is_first_run: bool
    counts: dict[str, int]
    entries: list[DiffEntryResponse]

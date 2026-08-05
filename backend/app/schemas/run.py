import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.run import RunStatus
from app.schemas.finding import Severity


class CreateRunRequest(BaseModel):
    """Body of POST /runs. The API key is a header, never part of the body.

    A body is logged far more casually than a header, and request bodies end up
    in error reports and traces.
    """

    repository_url: str = Field(
        description="HTTPS URL of a public repository on an allowed host",
        examples=["https://github.com/psf/requests"],
    )
    model: str | None = Field(
        default=None,
        description="Model to use. Defaults to a cheap model for the key's provider.",
    )
    max_usd: Decimal = Field(
        default=Decimal("0.50"),
        gt=0,
        le=Decimal("10.00"),
        description="Spending ceiling for this run.",
    )


class FindingResponse(BaseModel):
    """One finding, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    auditor: str
    category: str
    file_path: str
    line: int | None
    severity: Severity
    summary: str
    evidence: str


class RunResponse(BaseModel):
    """A run and everything known about it so far."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_url: str
    status: RunStatus
    error: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    truncated: bool
    created_at: datetime
    findings: list[FindingResponse]


class RunSummary(BaseModel):
    """A run without its findings, for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_url: str
    status: RunStatus
    cost_usd: Decimal
    truncated: bool
    created_at: datetime

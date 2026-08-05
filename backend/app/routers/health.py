from fastapi import APIRouter

from app.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is up.

    This deliberately does not check the database. A liveness probe should fail
    only when the process itself is broken, otherwise a brief database blip
    causes the orchestrator to restart a backend that was working fine.
    A separate readiness probe arrives in Phase 2, when there is a database to check.
    """
    return HealthResponse(status="ok", version=settings.VERSION)

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import AsyncSessionLocal
from app.models.run import RunStatus
from app.repositories.runs import RunRepository
from app.schemas.run import RunResponse

router = APIRouter(tags=["runs"])

POLL_SECONDS = 1.0
TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED}


@router.websocket("/runs/{run_id}/progress")
async def run_progress(websocket: WebSocket, run_id: uuid.UUID) -> None:
    """Stream a run's state until it finishes.

    The run is polled from the database rather than pushed from the task that
    executes it. Polling survives the socket and the run being handled by
    different worker processes, which an in-memory subscription would not.

    ponytail: a one second poll, not a subscription. Fine for a run that takes
    tens of seconds. If runs get short or sockets get numerous, move to
    NOTIFY/LISTEN or a broker.
    """
    await websocket.accept()

    try:
        while True:
            async with AsyncSessionLocal() as session:
                run = await RunRepository(session).get(run_id)

            if run is None:
                await websocket.send_json({"error": "Run not found"})
                return

            await websocket.send_json(RunResponse.model_validate(run).model_dump(mode="json"))

            if run.status in TERMINAL_STATUSES:
                return

            await asyncio.sleep(POLL_SECONDS)

    except WebSocketDisconnect:
        # The client closing is ordinary, not an error worth logging.
        return

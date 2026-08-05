import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.models.run import FindingRow, Run, RunStatus
from app.orchestrator import AuditorStatus, RunResult

OK = AuditorStatus.OK


class RunRepository:
    """Every database query about runs lives here.

    Keeping queries out of the service and the routers means the shape of a query
    can change without touching the code that decides what to do with the result.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, repository_url: str, repository_slug: str, model: str) -> Run:
        run = Run(
            repository_url=repository_url,
            repository_slug=repository_slug,
            model=model,
            status=RunStatus.PENDING,
        )
        self._session.add(run)
        await self._session.flush()
        # Mark the empty findings collection as already loaded. A plain
        # assignment would first read the existing rows to work out the change,
        # and that read happens from synchronous code, which raises
        # MissingGreenlet under asyncio. A brand new run has no findings, so
        # there is nothing to read.
        set_committed_value(run, "findings", [])
        return run

    async def get(self, run_id: uuid.UUID) -> Run | None:
        return await self._session.get(Run, run_id)

    async def list_recent(self, limit: int = 50) -> list[Run]:
        result = await self._session.execute(
            select(Run).order_by(Run.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def mark_running(self, run_id: uuid.UUID) -> None:
        run = await self._session.get(Run, run_id)
        if run is not None:
            run.status = RunStatus.RUNNING

    async def save_result(self, run_id: uuid.UUID, result: RunResult) -> None:
        """Store what a finished run produced.

        A run where some auditors failed is still completed: partial findings are
        a result, and the failures are visible per auditor.

        A run where *every* auditor failed is not. Reporting it as completed with
        an empty findings list is indistinguishable from a clean repository,
        which is the worst thing an audit tool can do: say nothing is wrong when
        it never managed to look.
        """
        run = await self._session.get(Run, run_id)
        if run is None:
            return

        failures = [outcome for outcome in result.outcomes if outcome.status is not OK]
        if len(failures) == len(result.outcomes):
            run.status = RunStatus.FAILED
            run.error = "Every auditor failed: " + "; ".join(
                f"{outcome.auditor}: {outcome.error}" for outcome in failures
            )
        else:
            run.status = RunStatus.COMPLETED

        run.input_tokens = result.usage.input_tokens
        run.output_tokens = result.usage.output_tokens
        run.cost_usd = result.usage.cost_usd
        run.truncated = result.truncated

        for outcome in result.outcomes:
            for finding in outcome.findings:
                self._session.add(
                    FindingRow(
                        run_id=run.id,
                        auditor=outcome.auditor,
                        category=finding.category,
                        file_path=finding.file_path,
                        line=finding.line,
                        severity=finding.severity,
                        summary=finding.summary,
                        evidence=finding.evidence,
                    )
                )

    async def mark_failed(self, run_id: uuid.UUID, error: str) -> None:
        run = await self._session.get(Run, run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.error = error

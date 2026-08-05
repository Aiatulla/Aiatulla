import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from app.auditors.base import Auditor
from app.budget import BudgetExceededError, BudgetGuard
from app.llm.protocol import LLMClient
from app.llm.usage import Usage
from app.schemas.finding import Finding


class AuditorStatus(StrEnum):
    """How one auditor ended."""

    OK = "ok"
    FAILED = "failed"
    OVER_BUDGET = "over_budget"


@dataclass(frozen=True)
class AuditorOutcome:
    """What one auditor produced, and whether it got to finish.

    Findings alone would lose the fact that an auditor died. A run that reports
    two clean auditors and silently drops a third is worse than one that says so.
    """

    auditor: str
    status: AuditorStatus
    findings: tuple[Finding, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    """The result of auditing one repository with several auditors."""

    outcomes: tuple[AuditorOutcome, ...]
    usage: Usage
    truncated: bool = field(default=False)

    @property
    def findings(self) -> list[Finding]:
        """Every finding from every auditor that completed."""
        return [finding for outcome in self.outcomes for finding in outcome.findings]

    @property
    def is_complete(self) -> bool:
        """True when every auditor finished normally."""
        return all(outcome.status is AuditorStatus.OK for outcome in self.outcomes)


async def run_audit(
    client: LLMClient,
    repository: Path,
    auditors: list[Auditor],
    max_usd: Decimal,
    model: str = "gemini-2.0-flash",
) -> RunResult:
    """Run every auditor over one repository and merge what they find.

    Auditors are independent, so they run concurrently and share one budget.

    One auditor failing does not fail the run. A partial result naming what broke
    is more useful than nothing at all, and a single unparseable model reply
    should not discard the work the others already did.
    """
    guard = BudgetGuard(client, model=model, max_usd=max_usd)

    outcomes = await asyncio.gather(*(_run_one(guard, repository, auditor) for auditor in auditors))

    return RunResult(
        outcomes=tuple(outcomes),
        usage=guard.spent,
        truncated=any(outcome.status is AuditorStatus.OVER_BUDGET for outcome in outcomes),
    )


async def _run_one(guard: BudgetGuard, repository: Path, auditor: Auditor) -> AuditorOutcome:
    """Run one auditor, converting any failure into a recorded outcome.

    Exceptions are caught here rather than by gather(return_exceptions=True) so
    that the reason survives as a readable string instead of an exception object
    the caller has to unpack.
    """
    try:
        findings = await auditor.run(guard, repository)
    except BudgetExceededError as exc:
        return AuditorOutcome(auditor.name, AuditorStatus.OVER_BUDGET, error=str(exc))
    except Exception as exc:
        # Deliberately broad: an auditor is a prompt plus a model reply, and there
        # is no useful list of everything that can go wrong with one. Whatever
        # happened, the other auditors' work is still worth returning.
        return AuditorOutcome(
            auditor.name, AuditorStatus.FAILED, error=f"{type(exc).__name__}: {exc}"
        )

    return AuditorOutcome(auditor.name, AuditorStatus.OK, findings=tuple(findings))

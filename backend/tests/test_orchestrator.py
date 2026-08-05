import asyncio
from decimal import Decimal
from pathlib import Path

from app.auditors.base import Auditor, AuditorError
from app.llm.protocol import Response, ToolCall
from app.llm.usage import build_usage
from app.orchestrator import AuditorStatus, run_audit

FIXTURE = Path(__file__).parent / "fixtures" / "repo_a"
MODEL = "gemini-2.0-flash"


class FakeAuditor(Auditor):
    """An auditor whose behaviour the test dictates, so no model is involved."""

    def __init__(
        self,
        name: str,
        findings: list[dict] | None = None,
        fails: bool = False,
        calls: int = 1,
    ) -> None:
        self._name = name
        self._findings = findings or []
        self._fails = fails
        self._calls = calls
        self.started = asyncio.Event()

    @property
    def name(self) -> str:
        return self._name

    @property
    def system_prompt(self) -> str:
        return f"prompt for {self._name}"

    @property
    def tool_description(self) -> str:
        return "findings"

    async def run(self, client, repository):  # type: ignore[override]
        self.started.set()
        # Still spends budget, so budget tests behave as they would in a real run.
        for _ in range(self._calls):
            await client.complete(messages=[], tools=[self.tool], system=self.system_prompt)
        if self._fails:
            raise AuditorError(f"{self._name} could not parse the reply")
        return [self._finding(item) for item in self._findings]

    def _finding(self, item: dict):
        from app.schemas.finding import Finding

        return Finding.model_validate(item)


class SlowClient:
    """Sleeps before replying, so concurrency is observable in wall clock time."""

    def __init__(self, delay: float = 0.05, cost_tokens: int = 1_000) -> None:
        self._delay = delay
        self._cost_tokens = cost_tokens
        self.calls = 0

    async def complete(self, messages=None, tools=None, system=None) -> Response:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return Response(
            model=MODEL,
            usage=build_usage(MODEL, self._cost_tokens, 0),
            tool_calls=(ToolCall(name="report_findings", arguments={"findings": []}),),
        )


def _finding(category: str, file_path: str) -> dict:
    return {
        "category": category,
        "file_path": file_path,
        "severity": "low",
        "summary": "something",
        "evidence": "evidence",
    }


async def test_findings_from_every_auditor_are_merged():
    auditors = [
        FakeAuditor("dead_code", [_finding("unused_module", "a.py")]),
        FakeAuditor("security", [_finding("hardcoded_credential", "config.py")]),
    ]

    result = await run_audit(SlowClient(), FIXTURE, auditors, max_usd=Decimal("1.00"))

    assert result.is_complete
    assert {finding.category for finding in result.findings} == {
        "unused_module",
        "hardcoded_credential",
    }


async def test_auditors_run_concurrently_not_one_after_another():
    """Three auditors at 50ms each finish in about 50ms if parallel, 150ms if not."""
    auditors = [FakeAuditor(f"auditor_{index}") for index in range(3)]

    started = asyncio.get_running_loop().time()
    await run_audit(SlowClient(delay=0.05), FIXTURE, auditors, max_usd=Decimal("1.00"))
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.12, f"auditors appear to be running sequentially ({elapsed:.3f}s)"


async def test_one_failing_auditor_does_not_lose_the_others_work():
    auditors = [
        FakeAuditor("dead_code", [_finding("unused_module", "a.py")]),
        FakeAuditor("security", fails=True),
        FakeAuditor("test_quality", [_finding("assertion_free_test", "t.py")]),
    ]

    result = await run_audit(SlowClient(), FIXTURE, auditors, max_usd=Decimal("1.00"))

    assert len(result.findings) == 2
    assert not result.is_complete

    failed = next(o for o in result.outcomes if o.auditor == "security")
    assert failed.status is AuditorStatus.FAILED
    assert "could not parse" in (failed.error or ""), "the reason must survive as readable text"


async def test_a_tiny_budget_truncates_the_run():
    """A run that ran out of money must say so, not look like a clean result.

    Each auditor makes two calls. The first wave is admitted, because concurrent
    callers are all checked before any of them has reported a cost. That wave
    blows the ceiling, so the second wave is refused and the run is truncated.
    """
    auditors = [FakeAuditor(f"auditor_{index}", calls=2) for index in range(3)]
    client = SlowClient(delay=0.0, cost_tokens=1_000_000)  # $0.10 per call

    result = await run_audit(client, FIXTURE, auditors, max_usd=Decimal("0.05"))

    assert result.truncated
    assert client.calls == 3, "the second wave must never reach the provider"

    over_budget = [o for o in result.outcomes if o.status is AuditorStatus.OVER_BUDGET]
    assert len(over_budget) == 3, "every auditor should have been stopped mid-run"


async def test_usage_totals_every_auditor():
    auditors = [FakeAuditor(f"auditor_{index}") for index in range(3)]

    result = await run_audit(SlowClient(cost_tokens=1_000), FIXTURE, auditors, Decimal("1.00"))

    assert result.usage.input_tokens == 3_000


async def test_a_clean_run_is_not_marked_truncated():
    result = await run_audit(SlowClient(), FIXTURE, [FakeAuditor("dead_code")], Decimal("1.00"))

    assert not result.truncated
    assert result.is_complete

from decimal import Decimal

from app.llm.protocol import LLMClient, Message, Response, Tool
from app.llm.usage import Usage


class BudgetExceededError(RuntimeError):
    """Raised when a run has spent its allowance and tries to make another call."""


class BudgetGuard:
    """Wraps a client and refuses to keep spending past a ceiling.

    This is an LLMClient itself, so it composes with the cassette layer and any
    provider without either of them knowing it exists.

    A cost is only known after a call returns, so the check happens before
    starting the next one. The ceiling is therefore a floor on when to stop, not
    a hard cap on the total.

    How far it can overshoot: every call already in flight was admitted before
    any of them had recorded a cost, so a run can exceed the ceiling by one call
    per concurrent auditor. With three auditors that is three calls, which is
    bounded and predictable, but it is not one call.

    ponytail: reserving an estimated cost per in-flight call would tighten this,
    at the price of an estimate that is wrong in both directions. Worth doing
    when auditors start making many calls each rather than one.
    """

    def __init__(self, inner: LLMClient, max_usd: Decimal) -> None:
        if max_usd <= 0:
            raise ValueError("A budget ceiling must be positive")

        self._inner = inner
        self._max_usd = max_usd
        self._spent = Usage(model="", input_tokens=0, output_tokens=0, cost_usd=Decimal(0))

    @property
    def spent(self) -> Usage:
        """What this run has used so far, across every auditor sharing the guard."""
        return self._spent

    @property
    def remaining_usd(self) -> Decimal:
        return max(Decimal(0), self._max_usd - self._spent.cost_usd)

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        if self._spent.cost_usd >= self._max_usd:
            raise BudgetExceededError(
                f"Run has spent ${self._spent.cost_usd} of its ${self._max_usd} budget"
            )

        response = await self._inner.complete(messages=messages, tools=tools, system=system)

        # Auditors run concurrently and share this guard. asyncio does not
        # interleave between await points on a single thread, so this read and
        # write cannot be split by another auditor.
        self._spent = self._spent + response.usage
        return response

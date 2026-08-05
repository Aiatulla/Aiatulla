import asyncio
from decimal import Decimal

import pytest

from app.budget import BudgetExceededError, BudgetGuard
from app.llm.protocol import Message, Response
from app.llm.usage import build_usage

MODEL = "gemini-2.0-flash"
MESSAGES = [Message(role="user", content="hello")]


class CountingClient:
    """Charges a fixed amount per call and counts how many it served."""

    def __init__(self, input_tokens: int = 1_000_000, output_tokens: int = 0) -> None:
        self.calls = 0
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    async def complete(self, messages, tools=None, system=None) -> Response:
        self.calls += 1
        # A real provider call always yields to the event loop. Without this the
        # coroutine would run start to finish without giving concurrent callers a
        # chance to interleave, and concurrency tests would pass for the wrong reason.
        await asyncio.sleep(0)
        return Response(
            model=MODEL,
            usage=build_usage(MODEL, self._input_tokens, self._output_tokens),
        )


async def test_calls_within_budget_go_through():
    # $0.10 per call at 1M input tokens.
    inner = CountingClient()
    guard = BudgetGuard(inner, max_usd=Decimal("1.00"))

    await guard.complete(MESSAGES)

    assert inner.calls == 1
    assert guard.spent.cost_usd == Decimal("0.10")


async def test_spending_accumulates_across_calls():
    guard = BudgetGuard(CountingClient(), max_usd=Decimal("1.00"))

    for _ in range(3):
        await guard.complete(MESSAGES)

    assert guard.spent.cost_usd == Decimal("0.30")
    assert guard.spent.input_tokens == 3_000_000


async def test_call_is_refused_once_the_ceiling_is_reached():
    """The whole point: a run cannot keep spending after its allowance is gone."""
    inner = CountingClient()
    guard = BudgetGuard(inner, max_usd=Decimal("0.05"))

    await guard.complete(MESSAGES)  # spends 0.10, which is already past 0.05

    with pytest.raises(BudgetExceededError, match=r"0\.05"):
        await guard.complete(MESSAGES)

    assert inner.calls == 1, "the refused call must never reach the provider"


async def test_a_call_is_admitted_while_budget_remains():
    """The check is on money already spent, not on what a call might cost."""
    inner = CountingClient()
    guard = BudgetGuard(inner, max_usd=Decimal("0.15"))

    await guard.complete(MESSAGES)  # 0.10 spent, still below 0.15
    await guard.complete(MESSAGES)  # admitted, takes the total to 0.20

    assert inner.calls == 2
    assert guard.spent.cost_usd == Decimal("0.20")


async def test_concurrent_calls_overshoot_by_one_call_each():
    """Documented limit, pinned down so it cannot drift unnoticed.

    Calls already in flight were all admitted before any recorded a cost, so a
    ceiling can be passed by one call per concurrent caller.
    """
    inner = CountingClient()
    guard = BudgetGuard(inner, max_usd=Decimal("0.05"))

    await asyncio.gather(*(guard.complete(MESSAGES) for _ in range(3)))

    assert inner.calls == 3, "all three were admitted before any had reported spending"
    assert guard.spent.cost_usd == Decimal("0.30")

    # The next wave is refused, which is the guarantee that actually holds.
    with pytest.raises(BudgetExceededError):
        await guard.complete(MESSAGES)


async def test_remaining_never_goes_negative():
    guard = BudgetGuard(CountingClient(), max_usd=Decimal("0.05"))

    await guard.complete(MESSAGES)

    assert guard.remaining_usd == Decimal(0)


def test_a_ceiling_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        BudgetGuard(CountingClient(), max_usd=Decimal(0))

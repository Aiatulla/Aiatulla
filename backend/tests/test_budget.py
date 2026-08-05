import asyncio
from decimal import Decimal

import pytest

from app.budget import (
    ASSUMED_OUTPUT_TOKENS,
    BudgetExceededError,
    BudgetGuard,
    estimate_prompt_tokens,
)
from app.llm.protocol import Message, Response, Tool
from app.llm.usage import build_usage

MODEL = "gemini-2.0-flash"

# 4000 characters is 1000 estimated input tokens, which at $0.10 per million plus
# the assumed 4000 output tokens at $0.40 per million reserves $0.0017 per call.
MESSAGES = [Message(role="user", content="x" * 4_000)]
RESERVATION_PER_CALL = Decimal("0.0017")


class CountingClient:
    """Charges a fixed amount per call and counts how many it served."""

    def __init__(self, input_tokens: int = 1_000, output_tokens: int = 100) -> None:
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


def test_estimate_counts_the_prompt():
    tokens = estimate_prompt_tokens([Message(role="user", content="x" * 400)], None, None)

    assert tokens == 100


def test_estimate_counts_the_system_prompt_and_tool_schemas():
    """A large tool schema is sent on every call and is not free."""
    tool = Tool(name="report", description="d" * 100, parameters={"type": "object"})

    bare = estimate_prompt_tokens([Message(role="user", content="x" * 400)], None, None)
    full = estimate_prompt_tokens([Message(role="user", content="x" * 400)], [tool], "s" * 200)

    assert full > bare


async def test_calls_within_budget_go_through():
    inner = CountingClient()
    guard = BudgetGuard(inner, model=MODEL, max_usd=Decimal("1.00"))

    await guard.complete(MESSAGES)

    assert inner.calls == 1
    assert guard.spent.cost_usd > 0


async def test_spending_accumulates_across_calls():
    guard = BudgetGuard(CountingClient(), model=MODEL, max_usd=Decimal("1.00"))

    for _ in range(3):
        await guard.complete(MESSAGES)

    assert guard.spent.input_tokens == 3_000


async def test_a_call_that_would_breach_the_ceiling_is_refused():
    """The reservation is checked before the call, so nothing is spent to learn this."""
    inner = CountingClient()
    guard = BudgetGuard(inner, model=MODEL, max_usd=RESERVATION_PER_CALL / 2)

    with pytest.raises(BudgetExceededError, match="would exceed"):
        await guard.complete(MESSAGES)

    assert inner.calls == 0, "the refused call must never reach the provider"


async def test_concurrent_calls_cannot_all_slip_through():
    """The reason reservations exist.

    Checking only money already spent would admit every concurrent caller, since
    none of them has reported a cost yet. Reserving up front is what stops that.
    """
    inner = CountingClient()
    # Room for one reservation, not three.
    guard = BudgetGuard(inner, model=MODEL, max_usd=RESERVATION_PER_CALL * Decimal("1.5"))

    results = await asyncio.gather(
        *(guard.complete(MESSAGES) for _ in range(3)), return_exceptions=True
    )

    admitted = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, BudgetExceededError)]

    assert len(admitted) == 1, "only one call fits the ceiling"
    assert len(refused) == 2
    assert inner.calls == 1, "refused calls must never reach the provider"


async def test_a_reservation_is_released_after_the_call():
    """Otherwise a long run would strangle itself as reservations piled up."""
    guard = BudgetGuard(CountingClient(), model=MODEL, max_usd=Decimal("1.00"))

    for _ in range(5):
        await guard.complete(MESSAGES)

    # Five small calls against a large ceiling must all succeed.
    assert guard.spent.input_tokens == 5_000


async def test_a_reservation_is_released_when_the_call_fails():
    """One provider error must not shrink the budget for everything after it."""

    class FailingClient:
        async def complete(self, messages, tools=None, system=None):
            await asyncio.sleep(0)
            raise RuntimeError("provider is down")

    guard = BudgetGuard(FailingClient(), model=MODEL, max_usd=Decimal("1.00"))

    with pytest.raises(RuntimeError, match="provider is down"):
        await guard.complete(MESSAGES)

    assert guard.remaining_usd == Decimal("1.00"), "the reservation should have been released"


async def test_remaining_accounts_for_spending():
    guard = BudgetGuard(CountingClient(), model=MODEL, max_usd=Decimal("1.00"))

    await guard.complete(MESSAGES)

    assert guard.remaining_usd < Decimal("1.00")
    assert guard.remaining_usd > Decimal("0.99")


def test_assumed_output_is_generous_rather_than_optimistic():
    """Under-reserving lets a run past its ceiling. Over-reserving only stops it early."""
    assert ASSUMED_OUTPUT_TOKENS >= 1_000


def test_a_ceiling_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        BudgetGuard(CountingClient(), model=MODEL, max_usd=Decimal(0))

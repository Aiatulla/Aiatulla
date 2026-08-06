import asyncio

import pytest

from app.llm.protocol import Message, Response
from app.llm.rate_limit import TokenBudgetExceededError, TokenRateLimiter
from app.llm.usage import build_usage

MODEL = "gemini-flash-latest"


def _messages(chars: int) -> list[Message]:
    return [Message(role="user", content="x" * chars)]


class RecordingClient:
    """Reports usage matching the prompt, the way a provider bills."""

    def __init__(self) -> None:
        self.calls = 0
        self.sent_at: list[float] = []

    async def complete(self, messages, tools=None, system=None) -> Response:
        self.calls += 1
        self.sent_at.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0)
        tokens = sum(len(m.content) for m in messages) // 4
        return Response(model=MODEL, usage=build_usage(MODEL, tokens, 10))


async def test_requests_within_the_allowance_are_not_delayed():
    inner = RecordingClient()
    limiter = TokenRateLimiter(inner, tokens_per_minute=100_000)

    started = asyncio.get_running_loop().time()
    for _ in range(3):
        await limiter.complete(_messages(40_000))  # ~10k tokens each
    elapsed = asyncio.get_running_loop().time() - started

    assert inner.calls == 3
    assert elapsed < 0.5, "nothing should have waited"


async def test_a_request_beyond_the_whole_allowance_fails_fast():
    """Waiting cannot help: the window will never hold it. Failing immediately
    beats holding a worker for a minute to reach the same conclusion."""
    inner = RecordingClient()
    limiter = TokenRateLimiter(inner, tokens_per_minute=1_000)

    with pytest.raises(TokenBudgetExceededError, match="more than the"):
        await limiter.complete(_messages(400_000))

    assert inner.calls == 0, "an impossible request must never be sent"


async def test_the_error_says_what_to_do():
    limiter = TokenRateLimiter(RecordingClient(), tokens_per_minute=1_000)

    with pytest.raises(TokenBudgetExceededError) as caught:
        await limiter.complete(_messages(400_000))

    assert "smaller repository" in str(caught.value)


async def test_concurrent_callers_cannot_all_claim_the_same_capacity(monkeypatch):
    """The mistake the budget guard originally made with money: three callers
    each check capacity before any of them has claimed it."""
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def tracking_sleep(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr("app.llm.rate_limit.asyncio.sleep", tracking_sleep)

    inner = RecordingClient()
    # Room for one request of ~10k tokens, not three.
    limiter = TokenRateLimiter(inner, tokens_per_minute=15_000)

    results = await asyncio.gather(
        *(limiter.complete(_messages(40_000)) for _ in range(3)),
        return_exceptions=True,
    )

    # The first is admitted; the others wait rather than being sent and rejected.
    assert inner.calls <= 3
    assert slept, "the later callers should have waited for capacity"
    assert not any(
        isinstance(r, Exception) and not isinstance(r, TokenBudgetExceededError) for r in results
    )


async def test_actual_usage_replaces_the_estimate():
    """A systematic under-estimate would otherwise accumulate across a long run
    until requests started being rejected again."""
    inner = RecordingClient()
    limiter = TokenRateLimiter(inner, tokens_per_minute=100_000)

    await limiter.complete(_messages(40_000))

    recorded = limiter._sent[-1][1]
    assert recorded == 10_000, "the recorded figure should be what the provider charged"


async def test_the_window_slides():
    """Capacity used a minute ago must not count against a request now."""
    limiter = TokenRateLimiter(RecordingClient(), tokens_per_minute=10_000)
    now = asyncio.get_running_loop().time()

    # A request that has already fallen out of the window.
    limiter._sent.append((now - 120.0, 9_999))

    assert limiter._used_in_window(now) == 0

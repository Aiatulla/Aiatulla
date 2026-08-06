import asyncio
import time
from collections import deque

from app.budget import estimate_prompt_tokens
from app.llm.protocol import LLMClient, Message, Response, Tool

# Google's smallest free tier allows this many input tokens per minute. Paid
# tiers are far higher, so this is the conservative floor rather than a fact
# about every account.
FREE_TIER_INPUT_TOKENS_PER_MINUTE = 250_000
WINDOW_SECONDS = 60.0

# Never wait longer than this for capacity. Beyond it the quota is a daily one,
# or the prompt is simply too large for the tier, and waiting only defers the
# error while holding a worker.
MAX_WAIT_SECONDS = 90.0


class TokenBudgetExceededError(RuntimeError):
    """Raised when a single request cannot fit the per-minute allowance at all."""


class TokenRateLimiter:
    """Paces requests so they stay inside a provider's tokens-per-minute quota.

    This is an LLMClient, so it composes with the cassette layer, the budget
    guard and any provider without any of them knowing it exists.

    It exists because retrying a quota error is actively harmful. A rejected
    request still had to be sent, so retrying a large prompt after a short delay
    spends more of the allowance that was already exhausted. Three auditors
    retrying four times each turned one over-quota run into twelve. Waiting for
    capacity before sending is the only version of this that converges.
    """

    def __init__(
        self,
        inner: LLMClient,
        tokens_per_minute: int = FREE_TIER_INPUT_TOKENS_PER_MINUTE,
    ) -> None:
        self._inner = inner
        self._limit = tokens_per_minute
        self._sent: deque[tuple[float, int]] = deque()
        # Auditors run concurrently and share the allowance. Without a lock they
        # would each check capacity before any of them had claimed it, which is
        # the same mistake the budget guard originally made with money.
        self._lock = asyncio.Lock()

    def _used_in_window(self, now: float) -> int:
        cutoff = now - WINDOW_SECONDS
        while self._sent and self._sent[0][0] <= cutoff:
            self._sent.popleft()
        return sum(tokens for _, tokens in self._sent)

    async def _claim(self, tokens: int) -> None:
        """Wait until this many tokens fit, then record them as spent."""
        if tokens > self._limit:
            raise TokenBudgetExceededError(
                f"A single request needs about {tokens:,} input tokens, more than the "
                f"{self._limit:,} per minute this tier allows. Audit a smaller "
                f"repository, or use a key with a higher quota."
            )

        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                if self._used_in_window(now) + tokens <= self._limit:
                    self._sent.append((now, tokens))
                    return
                # Sleep until the oldest request leaves the window, so capacity
                # is rechecked exactly when more becomes available.
                oldest = self._sent[0][0]
                sleep_for = max(0.1, oldest + WINDOW_SECONDS - now)

            if waited + sleep_for > MAX_WAIT_SECONDS:
                raise TokenBudgetExceededError(
                    f"Waited {waited:.0f}s for quota and still cannot send "
                    f"{tokens:,} input tokens. The allowance is likely a daily one."
                )

            await asyncio.sleep(sleep_for)
            waited += sleep_for

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        await self._claim(estimate_prompt_tokens(messages, tools, system))

        response = await self._inner.complete(messages=messages, tools=tools, system=system)

        # Replace the estimate with what was actually charged, so a systematic
        # under-estimate does not accumulate across a long run.
        async with self._lock:
            if self._sent:
                timestamp, _ = self._sent.pop()
                self._sent.append((timestamp, response.usage.input_tokens))

        return response

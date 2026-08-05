import json
from decimal import Decimal

from app.llm.protocol import LLMClient, Message, Response, Tool
from app.llm.usage import Usage, estimate_cost

# Rough conversion used to price a call before making it. Four characters per
# token is the usual approximation for English text and code.
CHARS_PER_TOKEN = 4

# What one reply is assumed to cost before it arrives. A findings array is small,
# so this is deliberately generous: under-reserving lets a run past its ceiling,
# while over-reserving only makes the guard stop slightly early.
ASSUMED_OUTPUT_TOKENS = 4_000


class BudgetExceededError(RuntimeError):
    """Raised when a call would take a run past its spending ceiling."""


def estimate_prompt_tokens(
    messages: list[Message],
    tools: list[Tool] | None,
    system: str | None,
) -> int:
    """Approximate how many input tokens a request will use.

    Counts the tool schemas as well as the prompt, since a large schema is sent
    on every call and is not free.
    """
    characters = sum(len(message.content) for message in messages)
    characters += len(system or "")
    characters += sum(
        len(tool.name) + len(tool.description) + len(json.dumps(tool.parameters))
        for tool in tools or []
    )
    return characters // CHARS_PER_TOKEN


class BudgetGuard:
    """Wraps a client and refuses calls that would take a run past a ceiling.

    This is an LLMClient itself, so it composes with the cassette layer and any
    provider without either of them knowing it exists.

    A call is priced before it is made, from the size of the prompt and the tool
    schemas, and that estimate is held as a reservation until the reply arrives.
    Reserving is what makes the ceiling hold under concurrency: auditors run at
    the same time, and checking only against money already spent would admit all
    of them before any had reported a cost.

    The ceiling is enforced against estimates, so the actual total can differ by
    the estimation error. Input is estimated closely because we build the prompt;
    output is assumed generous. Actual usage replaces the estimate once known, so
    the error does not accumulate across calls.
    """

    def __init__(self, inner: LLMClient, model: str, max_usd: Decimal) -> None:
        if max_usd <= 0:
            raise ValueError("A budget ceiling must be positive")

        self._inner = inner
        self._model = model
        self._max_usd = max_usd
        self._spent = Usage(model=model, input_tokens=0, output_tokens=0, cost_usd=Decimal(0))
        self._reserved = Decimal(0)

    @property
    def spent(self) -> Usage:
        """What this run has used so far, across every auditor sharing the guard."""
        return self._spent

    @property
    def remaining_usd(self) -> Decimal:
        """Ceiling minus what is spent and what is currently reserved."""
        return max(Decimal(0), self._max_usd - self._spent.cost_usd - self._reserved)

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        reservation = estimate_cost(
            model=self._model,
            input_tokens=estimate_prompt_tokens(messages, tools, system),
            output_tokens=ASSUMED_OUTPUT_TOKENS,
        )

        if self._spent.cost_usd + self._reserved + reservation > self._max_usd:
            raise BudgetExceededError(
                f"A call estimated at ${reservation} would exceed the ${self._max_usd} "
                f"budget: ${self._spent.cost_usd} spent, ${self._reserved} reserved"
            )

        # Auditors run concurrently and share this guard. asyncio does not
        # interleave between await points on a single thread, so reserving here
        # is seen by every other auditor before any of them can be admitted.
        self._reserved += reservation
        try:
            response = await self._inner.complete(messages=messages, tools=tools, system=system)
        finally:
            # Released even on failure, otherwise one error would shrink the
            # budget for every call that follows.
            self._reserved -= reservation

        self._spent = self._spent + response.usage
        return response

from dataclasses import dataclass
from decimal import Decimal

# Price per one million tokens, in US dollars.
#
# These are hardcoded on purpose: a run must be able to price itself without a
# network call. They drift, so treat them as an estimate and re-check against the
# provider's pricing page when adding a model.
#
# Decimal, not float, because these values are summed across thousands of calls
# and compared against a budget ceiling. Float rounding would make the ceiling
# quietly wrong.
_PRICE_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # model: (input, output)
    #
    # VERIFY BEFORE RELYING ON THESE FOR REAL SPEND. They are working values, not
    # quoted from a price sheet at the time of writing. A wrong price makes the
    # budget ceiling wrong in the same direction.
    # The -latest aliases resolve to whatever the caller's tier can actually
    # serve. Pinned names like gemini-2.5-flash appear in ListModels but return
    # 404 on a free-tier key, so an alias is the reliable default.
    #
    # Priced at the higher 2.5-class rate rather than the 2.0 rate: an alias can
    # move to a dearer model without warning, and over-estimating only stops a
    # run early while under-estimating lets it past its ceiling.
    "gemini-flash-latest": (Decimal("0.30"), Decimal("2.50")),
    "gemini-flash-lite-latest": (Decimal("0.10"), Decimal("0.40")),
    "gemini-2.0-flash": (Decimal("0.10"), Decimal("0.40")),
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "claude-haiku-4-5-20251001": (Decimal("1.00"), Decimal("5.00")),
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-opus-5": (Decimal("15.00"), Decimal("75.00")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}

_ONE_MILLION = Decimal(1_000_000)


class UnknownModelError(ValueError):
    """Raised when a model has no entry in the price table.

    This is deliberately fatal. Returning a zero cost for an unpriced model would
    let a run bypass its budget ceiling without anyone noticing.
    """


@dataclass(frozen=True)
class Usage:
    """Token counts and estimated cost for a single model call."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal

    def __add__(self, other: "Usage") -> "Usage":
        """Combine two usages so a run can total the calls it made.

        The model of the left operand wins, since the sum spans several models
        and no single name describes it.
        """
        return Usage(
            model=self.model,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Price a single call.

    :raises UnknownModelError: when the model is missing from the price table.
    """
    try:
        input_price, output_price = _PRICE_PER_MILLION[model]
    except KeyError as exc:
        known = ", ".join(sorted(_PRICE_PER_MILLION))
        raise UnknownModelError(f"No price for model {model!r}. Known models: {known}") from exc

    return (
        input_price * Decimal(input_tokens) + output_price * Decimal(output_tokens)
    ) / _ONE_MILLION


def build_usage(model: str, input_tokens: int, output_tokens: int) -> Usage:
    """Create a Usage with its cost already calculated."""
    return Usage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost(model, input_tokens, output_tokens),
    )

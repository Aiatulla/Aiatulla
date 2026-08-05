from decimal import Decimal

import pytest

from app.llm.usage import UnknownModelError, Usage, build_usage, estimate_cost


def test_cost_is_priced_per_million_tokens():
    # gemini-2.0-flash: $0.10 per 1M input, $0.40 per 1M output.
    cost = estimate_cost("gemini-2.0-flash", input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost == Decimal("0.50")


def test_small_call_keeps_full_precision():
    """A float would round this away, and thousands of them decide a budget."""
    cost = estimate_cost("gemini-2.0-flash", input_tokens=1, output_tokens=1)

    assert cost == Decimal("0.0000005")
    assert isinstance(cost, Decimal)


def test_unknown_model_raises_rather_than_costing_nothing():
    """Silently pricing an unknown model at zero would let a run skip its budget."""
    with pytest.raises(UnknownModelError, match="gpt-9"):
        estimate_cost("gpt-9", input_tokens=100, output_tokens=100)


def test_usages_add_up_across_calls():
    first = build_usage("gemini-2.0-flash", input_tokens=1_000, output_tokens=500)
    second = build_usage("gemini-2.0-flash", input_tokens=2_000, output_tokens=250)

    total = first + second

    assert total == Usage(
        model="gemini-2.0-flash",
        input_tokens=3_000,
        output_tokens=750,
        cost_usd=first.cost_usd + second.cost_usd,
    )

import pytest

from app.llm.providers import (
    DEFAULT_MODELS,
    Provider,
    UnknownProviderError,
    build_client,
    provider_for_key,
)
from app.llm.providers.anthropic import AnthropicClient
from app.llm.providers.gemini import GeminiClient
from app.llm.providers.openai import OpenAIClient
from app.llm.usage import _PRICE_PER_MILLION

ANTHROPIC_KEY = "sk-ant-api03-notarealkey"
GEMINI_KEY = "AIzaSyNotARealKey"
OPENAI_KEY = "sk-projNotARealKey"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (ANTHROPIC_KEY, Provider.ANTHROPIC),
        (GEMINI_KEY, Provider.GEMINI),
        (OPENAI_KEY, Provider.OPENAI),
    ],
    ids=["anthropic", "gemini", "openai"],
)
def test_provider_is_read_from_the_key(key, expected):
    assert provider_for_key(key) is expected


def test_an_anthropic_key_is_not_mistaken_for_openai():
    """Both start with "sk-", so prefix order decides this.

    Getting it wrong would send an Anthropic key to OpenAI, handing someone's
    credential to a vendor they never chose.
    """
    assert provider_for_key("sk-ant-api03-x") is Provider.ANTHROPIC
    assert provider_for_key("sk-anything-else") is Provider.OPENAI


def test_an_unrecognised_key_raises_rather_than_guessing():
    with pytest.raises(UnknownProviderError):
        provider_for_key("not-a-key-we-know")


def test_the_error_never_repeats_the_key():
    """An error message ends up in logs and in responses to the caller."""
    secret = "totally-unknown-but-still-secret"

    with pytest.raises(UnknownProviderError) as caught:
        provider_for_key(secret)

    assert secret not in str(caught.value)


@pytest.mark.parametrize(
    ("key", "expected_type"),
    [
        (ANTHROPIC_KEY, AnthropicClient),
        (GEMINI_KEY, GeminiClient),
        (OPENAI_KEY, OpenAIClient),
    ],
    ids=["anthropic", "gemini", "openai"],
)
def test_build_client_returns_the_matching_adapter(key, expected_type):
    assert isinstance(build_client(key), expected_type)


def test_an_explicit_model_overrides_the_default():
    client = build_client(ANTHROPIC_KEY, model="claude-opus-5")

    assert client._model == "claude-opus-5"


def test_every_default_model_has_a_price():
    """A model with no price raises at call time, which would fail a real run
    only after the user had already handed over a key."""
    for provider, model in DEFAULT_MODELS.items():
        assert model in _PRICE_PER_MILLION, f"{provider} default {model} has no price"

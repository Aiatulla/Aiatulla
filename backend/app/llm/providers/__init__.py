from enum import StrEnum

from app.llm.protocol import LLMClient
from app.llm.providers.anthropic import AnthropicClient
from app.llm.providers.gemini import GeminiClient
from app.llm.providers.openai import OpenAIClient


class Provider(StrEnum):
    """A model vendor this application can talk to."""

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"


class UnknownProviderError(ValueError):
    """Raised when a key does not match any provider we can talk to."""


# Order matters: an Anthropic key also starts with "sk-", so it must be tested
# before OpenAI or every Anthropic key would be sent to the wrong vendor.
_KEY_PREFIXES: tuple[tuple[str, Provider], ...] = (
    ("sk-ant-", Provider.ANTHROPIC),
    ("AIza", Provider.GEMINI),
    ("sk-", Provider.OPENAI),
)

DEFAULT_MODELS: dict[Provider, str] = {
    Provider.ANTHROPIC: "claude-sonnet-5",
    Provider.GEMINI: "gemini-2.0-flash",
    Provider.OPENAI: "gpt-4o-mini",
}


def provider_for_key(api_key: str) -> Provider:
    """Work out which vendor a key belongs to from its prefix.

    Users bring their own keys, so the vendor cannot be configured ahead of time.
    Asking someone to name their provider as well as paste a key is a question
    the key already answers.

    :raises UnknownProviderError: when no prefix matches. Guessing would send the
        key to the wrong vendor, which leaks it to a third party.
    """
    for prefix, provider in _KEY_PREFIXES:
        if api_key.startswith(prefix):
            return provider

    # The key itself is never included in the message.
    raise UnknownProviderError(
        "Key does not match a known provider. Expected an Anthropic, Gemini or OpenAI key."
    )


def build_client(api_key: str, model: str | None = None) -> LLMClient:
    """Create the right client for a key, defaulting to that vendor's cheap model.

    A match rather than a lookup table: the three constructors are the only place
    the concrete classes are named, and mypy can check every branch returns a
    client that satisfies the protocol.
    """
    provider = provider_for_key(api_key)
    resolved_model = model or DEFAULT_MODELS[provider]

    match provider:
        case Provider.ANTHROPIC:
            return AnthropicClient(api_key=api_key, model=resolved_model)
        case Provider.GEMINI:
            return GeminiClient(api_key=api_key, model=resolved_model)
        case Provider.OPENAI:
            return OpenAIClient(api_key=api_key, model=resolved_model)

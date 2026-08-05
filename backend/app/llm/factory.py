from app.config import settings
from app.llm.cassette import CassetteClient, CassetteMode
from app.llm.protocol import LLMClient
from app.llm.providers.gemini import GeminiClient


class MissingApiKeyError(RuntimeError):
    """Raised when recording is requested without a provider key."""


def build_llm_client() -> LLMClient:
    """Return the client the application should use, based on configuration.

    Everything above this point depends on the LLMClient protocol, so swapping a
    provider or turning recording on is a configuration change, not a code change.

    Replay is the default. That is what makes the test suite free, offline and
    deterministic, and it means a clone with no API key still runs everything.
    """
    if settings.LLM_CASSETTE_MODE is CassetteMode.REPLAY:
        return CassetteClient(
            cassette_dir=settings.LLM_CASSETTE_DIR,
            model=settings.LLM_MODEL,
            mode=CassetteMode.REPLAY,
        )

    if settings.GEMINI_API_KEY is None:
        raise MissingApiKeyError(
            "Recording calls the real provider, so GEMINI_API_KEY must be set. "
            "Leave LLM_CASSETTE_MODE as replay to run without a key."
        )

    return CassetteClient(
        cassette_dir=settings.LLM_CASSETTE_DIR,
        model=settings.LLM_MODEL,
        mode=CassetteMode.RECORD,
        # Unwrapped only here, at the point it is handed to the provider.
        inner=GeminiClient(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            model=settings.LLM_MODEL,
        ),
    )

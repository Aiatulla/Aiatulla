import pytest

from app.config import settings
from app.llm.cassette import CassetteClient, CassetteMode
from app.llm.factory import MissingApiKeyError, build_llm_client


def test_default_mode_needs_no_api_key(monkeypatch):
    """A fresh clone with no credentials must still be able to run everything."""
    monkeypatch.setattr(settings, "LLM_CASSETTE_MODE", CassetteMode.REPLAY)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)

    client = build_llm_client()

    assert isinstance(client, CassetteClient)


def test_recording_without_a_key_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CASSETTE_MODE", CassetteMode.RECORD)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)

    with pytest.raises(MissingApiKeyError, match="GEMINI_API_KEY"):
        build_llm_client()


def test_recording_wraps_the_real_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CASSETTE_MODE", CassetteMode.RECORD)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    client = build_llm_client()

    assert isinstance(client, CassetteClient)

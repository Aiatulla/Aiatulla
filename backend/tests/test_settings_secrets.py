"""A key that leaks into a log is as compromised as one committed to the repo.

These assert the mechanism, not the intention: the guarantee is that printing
settings anywhere cannot reveal the key.
"""

import pytest
from pydantic import SecretStr

from app.config import Settings

LEAKED = "AIzaSyDUMMY-not-a-real-key-000000000000000"


@pytest.fixture
def settings_with_key() -> Settings:
    return Settings(GEMINI_API_KEY=SecretStr(LEAKED))


def test_repr_does_not_reveal_the_key(settings_with_key):
    assert LEAKED not in repr(settings_with_key)


def test_str_does_not_reveal_the_key(settings_with_key):
    """This is the one that catches an f-string in a log line."""
    assert LEAKED not in str(settings_with_key)


def test_model_dump_does_not_reveal_the_key(settings_with_key):
    """Covers the accidental `logger.info(settings.model_dump())`."""
    assert LEAKED not in str(settings_with_key.model_dump())


def test_the_key_is_still_readable_when_deliberately_unwrapped(settings_with_key):
    """Hiding it everywhere would be useless if the provider could not read it."""
    assert settings_with_key.GEMINI_API_KEY is not None
    assert settings_with_key.GEMINI_API_KEY.get_secret_value() == LEAKED


def test_no_key_configured_by_default():
    """A clone with no .env must not carry a credential from anywhere."""
    assert Settings(_env_file=None).GEMINI_API_KEY is None

"""Bring your own key: the credential belongs to the caller.

These assert the two things that matter about someone else's key: that it is
checked before any work starts, and that it never comes back out anywhere.
"""

import pytest

from app.auth.byok import HEADER_NAME
from app.config import settings

ANTHROPIC_KEY = "sk-ant-api03-notarealkey"
RUNS = f"{settings.API_PREFIX}/runs"
BODY = {"repository_url": "https://github.com/example/repo"}


@pytest.fixture(autouse=True)
def no_background_work(monkeypatch):
    """Stop the audit itself from running.

    These tests cover the request path. The background task is covered
    separately, and letting it fire here would clone a repository and call a
    model with a key that is not real.
    """

    async def do_nothing(**kwargs):
        return None

    monkeypatch.setattr("app.routers.runs.execute_run", do_nothing)


async def test_a_run_cannot_start_without_a_key(client):
    response = await client.post(RUNS, json=BODY)

    assert response.status_code == 401
    assert HEADER_NAME in response.json()["detail"]


async def test_an_unrecognised_key_is_rejected_before_any_work(client):
    """Checked up front, so a bad key fails immediately rather than after a clone."""
    response = await client.post(RUNS, json=BODY, headers={HEADER_NAME: "nonsense"})

    assert response.status_code == 400


async def test_the_rejection_message_never_repeats_the_key(client):
    """Error text reaches logs, error trackers and the caller's console."""
    secret = "definitely-not-a-known-prefix-but-still-secret"

    response = await client.post(RUNS, json=BODY, headers={HEADER_NAME: secret})

    assert secret not in response.text


async def test_the_key_is_never_returned_in_the_run(client):
    response = await client.post(RUNS, json=BODY, headers={HEADER_NAME: ANTHROPIC_KEY})

    assert response.status_code == 202
    assert ANTHROPIC_KEY not in response.text


async def test_the_key_is_never_stored(client, session_factory):
    """The strongest form of this: search the whole database for the key.

    Asserting on a column would only prove the column we thought of is clean.
    """
    from sqlalchemy import text

    await client.post(RUNS, json=BODY, headers={HEADER_NAME: ANTHROPIC_KEY})

    async with session_factory() as session:
        for table in ("runs", "findings"):
            rows = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().all()
            for row in rows:
                assert ANTHROPIC_KEY not in str(dict(row)), f"key found in {table}"


async def test_the_key_is_never_logged(client, caplog):
    """Fails if anyone adds a log line that includes the key."""
    import logging

    with caplog.at_level(logging.DEBUG):
        await client.post(RUNS, json=BODY, headers={HEADER_NAME: ANTHROPIC_KEY})

    assert ANTHROPIC_KEY not in caplog.text


@pytest.mark.parametrize(
    "key",
    ["sk-ant-api03-x", "AIzaSyNotARealKey", "sk-projNotARealKey"],
    ids=["anthropic", "gemini", "openai"],
)
async def test_any_supported_provider_key_is_accepted(client, key):
    response = await client.post(RUNS, json=BODY, headers={HEADER_NAME: key})

    assert response.status_code == 202

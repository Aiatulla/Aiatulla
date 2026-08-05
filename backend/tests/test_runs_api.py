import uuid

import pytest

from app.auth.byok import HEADER_NAME
from app.config import settings
from app.services.run_service import repository_slug

KEY = "sk-ant-api03-notarealkey"
RUNS = f"{settings.API_PREFIX}/runs"
HEADERS = {HEADER_NAME: KEY}
REPO = "https://github.com/example/repo"


@pytest.fixture(autouse=True)
def no_background_work(monkeypatch):
    """Stop the audit itself from running.

    These tests are about the HTTP surface. Letting the background task fire
    would try to clone a repository and call a model.
    """

    async def do_nothing(**kwargs):
        return None

    monkeypatch.setattr("app.routers.runs.execute_run", do_nothing)


async def test_creating_a_run_returns_202_not_201(client):
    """202 means accepted, not finished. The audit has not run yet."""
    response = await client.post(RUNS, json={"repository_url": REPO}, headers=HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "pending"


async def test_a_created_run_can_be_fetched(client):
    created = await client.post(RUNS, json={"repository_url": REPO}, headers=HEADERS)
    run_id = created.json()["id"]

    fetched = await client.get(f"{RUNS}/{run_id}")

    assert fetched.status_code == 200
    assert fetched.json()["repository_url"] == REPO


async def test_fetching_a_run_needs_no_key(client):
    """A run holds no secrets, so reading one does not need a credential."""
    created = await client.post(RUNS, json={"repository_url": REPO}, headers=HEADERS)

    fetched = await client.get(f"{RUNS}/{created.json()['id']}")

    assert fetched.status_code == 200


async def test_an_unknown_run_is_404(client):
    response = await client.get(f"{RUNS}/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://github.com/a/b",
        "https://169.254.169.254/latest/meta-data",
        "https://user:token@github.com/a/b",
    ],
    ids=["local_file", "plain_http", "metadata_endpoint", "embedded_credentials"],
)
async def test_a_dangerous_url_is_rejected_at_the_api(client, url):
    """Rejected here rather than in the background, so the caller is told."""
    response = await client.post(RUNS, json={"repository_url": url}, headers=HEADERS)

    assert response.status_code == 400


async def test_the_budget_ceiling_is_bounded(client):
    """Without an upper bound, a caller could ask for an unlimited run."""
    response = await client.post(
        RUNS, json={"repository_url": REPO, "max_usd": "1000"}, headers=HEADERS
    )

    assert response.status_code == 422


async def test_a_non_positive_budget_is_rejected(client):
    response = await client.post(
        RUNS, json={"repository_url": REPO, "max_usd": "0"}, headers=HEADERS
    )

    assert response.status_code == 422


async def test_listing_runs_returns_the_most_recent(client):
    for index in range(3):
        await client.post(RUNS, json={"repository_url": f"{REPO}-{index}"}, headers=HEADERS)

    response = await client.get(RUNS)

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_the_model_defaults_to_the_providers_cheap_one(client):
    response = await client.post(RUNS, json={"repository_url": REPO}, headers=HEADERS)

    assert response.json()["model"] == "claude-sonnet-5"


async def test_an_explicit_model_is_used(client):
    response = await client.post(
        RUNS, json={"repository_url": REPO, "model": "claude-opus-5"}, headers=HEADERS
    )

    assert response.json()["model"] == "claude-opus-5"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/PSF/Requests", "github.com/psf/requests"),
        ("https://github.com/psf/requests.git", "github.com/psf/requests"),
        ("https://github.com/psf/requests/", "github.com/psf/requests"),
    ],
    ids=["case", "git_suffix", "trailing_slash"],
)
def test_urls_for_the_same_repository_share_a_slug(url, expected):
    """Phase 5 diffs a run against the previous run of the same repository.
    Without this, one repository written three ways would never be compared."""
    assert repository_slug(url) == expected

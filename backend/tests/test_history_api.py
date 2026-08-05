import pytest

from app.config import settings
from app.models.run import FindingRow, Run, RunStatus
from app.services.run_service import repository_slug

REPO = "https://github.com/example/repo"
SLUG = repository_slug(REPO)
API = settings.API_PREFIX


async def _store_run(session_factory, findings: list[tuple[str, str]], status=RunStatus.COMPLETED):
    """Write a finished run straight to the database, skipping the audit."""
    async with session_factory() as session:
        run = Run(
            repository_url=REPO,
            repository_slug=SLUG,
            model="claude-sonnet-5",
            status=status,
        )
        session.add(run)
        await session.flush()

        for category, file_path in findings:
            session.add(
                FindingRow(
                    run_id=run.id,
                    auditor="dead_code",
                    category=category,
                    file_path=file_path,
                    severity="low",
                    summary="something",
                    evidence="evidence",
                )
            )
        await session.commit()
        return run.id


async def test_a_first_run_is_reported_as_a_first_run(client, session_factory):
    run_id = await _store_run(session_factory, [("unused_module", "a.py")])

    response = await client.get(f"{API}/runs/{run_id}/diff")

    assert response.status_code == 200
    body = response.json()
    assert body["is_first_run"] is True
    assert body["previous_run_id"] is None
    assert body["counts"] == {"new": 1, "fixed": 0, "persisting": 0}


async def test_a_second_run_is_compared_against_the_first(client, session_factory):
    """The whole point of the phase: two runs of one repository produce a diff."""
    first = await _store_run(
        session_factory, [("unused_module", "gone.py"), ("unused_module", "stays.py")]
    )
    second = await _store_run(
        session_factory, [("unused_module", "stays.py"), ("unused_module", "new.py")]
    )

    response = await client.get(f"{API}/runs/{second}/diff")

    body = response.json()
    assert body["is_first_run"] is False
    assert body["previous_run_id"] == str(first)
    assert body["counts"] == {"new": 1, "fixed": 1, "persisting": 1}


async def test_a_failed_run_is_not_used_as_a_baseline(client, session_factory):
    """A failed run has no findings. Diffing against it would report every
    finding as new and hide a real regression behind a broken predecessor."""
    good = await _store_run(session_factory, [("unused_module", "a.py")])
    await _store_run(session_factory, [], status=RunStatus.FAILED)
    latest = await _store_run(session_factory, [("unused_module", "a.py")])

    body = (await client.get(f"{API}/runs/{latest}/diff")).json()

    assert body["previous_run_id"] == str(good)
    assert body["counts"]["persisting"] == 1


async def test_a_run_is_never_compared_against_a_different_repository(client, session_factory):
    async with session_factory() as session:
        other = Run(
            repository_url="https://github.com/other/project",
            repository_slug="github.com/other/project",
            model="claude-sonnet-5",
            status=RunStatus.COMPLETED,
        )
        session.add(other)
        await session.commit()

    run_id = await _store_run(session_factory, [("unused_module", "a.py")])

    body = (await client.get(f"{API}/runs/{run_id}/diff")).json()

    assert body["is_first_run"] is True


async def test_history_lists_every_run_of_one_repository(client, session_factory):
    for _ in range(3):
        await _store_run(session_factory, [])

    response = await client.get(f"{API}/repos/{SLUG}/history")

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_history_of_an_unknown_repository_is_empty_not_an_error(client):
    """Nothing has been audited yet is a valid answer, not a failure."""
    response = await client.get(f"{API}/repos/github.com/nobody/nothing/history")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("path", ["github.com/Example/Repo", "GITHUB.COM/EXAMPLE/REPO"])
async def test_history_lookup_is_case_insensitive(client, session_factory, path):
    await _store_run(session_factory, [])

    response = await client.get(f"{API}/repos/{path}/history")

    assert len(response.json()) == 1


async def test_the_diff_of_an_unknown_run_is_404(client):
    import uuid

    response = await client.get(f"{API}/runs/{uuid.uuid4()}/diff")

    assert response.status_code == 404

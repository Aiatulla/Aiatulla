"""Does the dead_code auditor still detect what it is supposed to detect?

This is the regression gate for prompt changes. It replays recorded cassettes, so
it costs nothing, needs no API key and cannot flake on model non-determinism.
"""

from pathlib import Path

import pytest

from app.auditors.dead_code import DeadCodeAuditor
from app.evaluation import evaluate, load_expected
from app.llm.cassette import CassetteClient, CassetteMissError, CassetteMode

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
CASSETTE_DIR = BACKEND_ROOT / "tests" / "cassettes"
FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures"
MODEL = "gemini-2.0-flash"

# Committed thresholds. Lower them only with a reason in the commit message: this
# is the number that says whether a prompt edit made the auditor worse.
MIN_RECALL = 1.0
MIN_PRECISION = 0.5


async def test_dead_code_auditor_finds_planted_defects():
    auditor = DeadCodeAuditor()
    fixture = FIXTURE_DIR / "repo_a"
    client = CassetteClient(CASSETTE_DIR, MODEL, mode=CassetteMode.REPLAY)

    try:
        findings = await auditor.run(client, fixture)
    except CassetteMissError as exc:
        pytest.skip(
            f"No cassette recorded for this prompt. "
            f"Run scripts/record_cassettes.py with a real key. ({exc})"
        )

    result = evaluate(load_expected(fixture / "golden.json"), findings)

    assert result.recall >= MIN_RECALL, f"dead_code lost detections: {result.summary()}"
    assert result.precision >= MIN_PRECISION, f"dead_code got noisier: {result.summary()}"


async def test_live_code_is_not_reported_as_dead():
    """Precision has a floor for a reason: flagging the live path is the failure
    that would make the whole tool untrustworthy."""
    auditor = DeadCodeAuditor()
    fixture = FIXTURE_DIR / "repo_a"
    client = CassetteClient(CASSETTE_DIR, MODEL, mode=CassetteMode.REPLAY)

    try:
        findings = await auditor.run(client, fixture)
    except CassetteMissError:
        pytest.skip("No cassette recorded for this prompt.")

    reported_files = {finding.file_path for finding in findings}

    assert "main.py" not in reported_files
    assert "storage.py" not in reported_files

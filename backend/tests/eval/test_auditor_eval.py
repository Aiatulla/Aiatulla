"""Do the auditors still detect what they are supposed to detect?

This is the regression gate for prompt changes. It replays recorded cassettes, so
it costs nothing, needs no API key and cannot flake on model non-determinism.

Each auditor and fixture pair is scored separately: an auditor that improved must
not be able to hide another that got worse.
"""

from pathlib import Path

import pytest

from app.auditors.base import Auditor
from app.auditors.dead_code import DeadCodeAuditor
from app.auditors.security import SecurityAuditor
from app.auditors.test_quality import TestQualityAuditor
from app.evaluation import evaluate, load_expected
from app.llm.cassette import CassetteClient, CassetteMissError, CassetteMode

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
CASSETTE_DIR = BACKEND_ROOT / "tests" / "cassettes"
FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures"
MODEL = "gemini-2.0-flash"

# Committed thresholds, per auditor and fixture. Lowering one needs a reason in
# the commit message: this number is what says whether an edit made it worse.
#
# Recall is held at 1.0 because every planted defect is unambiguous. Precision
# allows some noise, since a model reasonably notices real problems that were not
# the ones planted.
CASES: list[tuple[Auditor, str, float, float]] = [
    (DeadCodeAuditor(), "repo_a", 1.0, 0.5),
    (SecurityAuditor(), "repo_b", 1.0, 0.5),
    (TestQualityAuditor(), "repo_b", 1.0, 0.5),
]


# pytest passes each parameter separately to an ids function, so the readable
# name is built here from the cases themselves.
CASE_IDS = [f"{auditor.name}-{fixture}" for auditor, fixture, _, _ in CASES]


async def _findings_or_skip(auditor: Auditor, fixture: Path):
    client = CassetteClient(CASSETTE_DIR, MODEL, mode=CassetteMode.REPLAY)
    try:
        return await auditor.run(client, fixture)
    except CassetteMissError as exc:
        pytest.skip(
            f"No cassette for {auditor.name}. "
            f"Run scripts/record_cassettes.py with a real key. ({exc})"
        )


@pytest.mark.parametrize(("auditor", "fixture", "min_recall", "min_precision"), CASES, ids=CASE_IDS)
async def test_auditor_meets_its_thresholds(auditor, fixture, min_recall, min_precision):
    fixture_path = FIXTURE_DIR / fixture
    findings = await _findings_or_skip(auditor, fixture_path)

    expected = load_expected(fixture_path / "golden.json", auditor.name)
    result = evaluate(expected, findings)

    assert result.recall >= min_recall, f"{auditor.name} lost detections: {result.summary()}"
    assert result.precision >= min_precision, f"{auditor.name} got noisier: {result.summary()}"


@pytest.mark.parametrize(
    ("auditor", "fixture", "protected"),
    [
        (DeadCodeAuditor(), "repo_a", ["main.py", "storage.py"]),
        (SecurityAuditor(), "repo_b", []),
    ],
    ids=["dead_code-live-path", "security-placeholders"],
)
async def test_known_good_code_is_not_reported(auditor, fixture, protected):
    """Flagging correct code is the failure that makes the whole tool untrustworthy.

    Precision alone would let this through if the auditor also found enough real
    defects, so the specific files are named here.
    """
    fixture_path = FIXTURE_DIR / fixture
    findings = await _findings_or_skip(auditor, fixture_path)

    reported = {finding.file_path for finding in findings}

    for path in protected:
        assert path not in reported, f"{auditor.name} reported the live path {path}"

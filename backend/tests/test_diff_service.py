"""Comparing a run against the previous one.

Every audit that scanned this profile said the same thing: no comparable
previous result was available, so its score was a baseline and nothing more.
This is the part that answers that.
"""

from app.models.run import FindingRow
from app.services.diff_service import (
    Change,
    diff_against_nothing,
    diff_findings,
    identity_of,
)


def _finding(
    category: str,
    file_path: str,
    auditor: str = "dead_code",
    line: int | None = None,
    summary: str = "something",
) -> FindingRow:
    return FindingRow(
        auditor=auditor,
        category=category,
        file_path=file_path,
        line=line,
        severity="low",
        summary=summary,
        evidence="evidence",
    )


def test_a_finding_present_in_both_runs_is_persisting():
    previous = [_finding("unused_module", "legacy.py")]
    current = [_finding("unused_module", "legacy.py")]

    diff = diff_findings(previous, current)

    assert len(diff.persisting) == 1
    assert not diff.new
    assert not diff.fixed


def test_a_finding_only_in_the_new_run_is_new():
    diff = diff_findings([], [_finding("unused_module", "legacy.py")])

    assert len(diff.new) == 1
    assert diff.new[0].change is Change.NEW


def test_a_finding_only_in_the_old_run_is_fixed():
    diff = diff_findings([_finding("unused_module", "legacy.py")], [])

    assert len(diff.fixed) == 1
    assert diff.fixed[0].file_path == "legacy.py"


def test_a_moved_defect_is_persisting_not_fixed_and_new():
    """Adding an import above a defect shifts every line below it. A diff keyed
    on line numbers would report churn on every run."""
    previous = [_finding("unused_module", "legacy.py", line=10)]
    current = [_finding("unused_module", "legacy.py", line=42)]

    diff = diff_findings(previous, current)

    assert len(diff.persisting) == 1
    assert not diff.fixed
    assert not diff.new


def test_rephrasing_does_not_look_like_a_change():
    """A model words the same defect differently every run. Comparing summaries
    would report changes that never happened."""
    previous = [_finding("unused_module", "legacy.py", summary="Nothing imports this module")]
    current = [_finding("unused_module", "legacy.py", summary="This file is unreachable")]

    diff = diff_findings(previous, current)

    assert len(diff.persisting) == 1


def test_the_same_category_in_a_different_file_is_a_different_finding():
    previous = [_finding("unused_module", "a.py")]
    current = [_finding("unused_module", "b.py")]

    diff = diff_findings(previous, current)

    assert len(diff.new) == 1
    assert len(diff.fixed) == 1


def test_the_same_file_from_a_different_auditor_is_a_different_finding():
    previous = [_finding("hardcoded_credential", "config.py", auditor="security")]
    current = [_finding("hardcoded_credential", "config.py", auditor="dead_code")]

    diff = diff_findings(previous, current)

    assert len(diff.new) == 1
    assert len(diff.fixed) == 1


def test_a_mixed_run_reports_all_three_states():
    previous = [
        _finding("unused_module", "gone.py"),
        _finding("unused_module", "stays.py"),
    ]
    current = [
        _finding("unused_module", "stays.py"),
        _finding("unused_module", "appeared.py"),
    ]

    diff = diff_findings(previous, current)

    assert [entry.file_path for entry in diff.fixed] == ["gone.py"]
    assert [entry.file_path for entry in diff.persisting] == ["stays.py"]
    assert [entry.file_path for entry in diff.new] == ["appeared.py"]


def test_a_run_with_no_changes_says_so():
    findings = [_finding("unused_module", "legacy.py")]

    assert diff_findings(findings, findings).is_unchanged


def test_a_run_that_fixed_something_is_not_unchanged():
    assert not diff_findings([_finding("unused_module", "legacy.py")], []).is_unchanged


def test_a_first_run_reports_everything_as_new():
    """Describing a first run beats refusing to answer. It is the honest
    description, and it is what a one-off score cannot give."""
    diff = diff_against_nothing(
        [_finding("unused_module", "a.py"), _finding("dead_asset", "b.svg")]
    )

    assert len(diff.new) == 2
    assert not diff.fixed
    assert not diff.persisting


def test_identity_ignores_line_and_wording():
    a = _finding("unused_module", "legacy.py", line=1, summary="one wording")
    b = _finding("unused_module", "legacy.py", line=99, summary="another wording")

    assert identity_of(a) == identity_of(b)

import json

from app.evaluation import ExpectedFinding, evaluate, load_expected
from app.schemas.finding import Finding, Severity


def _finding(category: str, file_path: str, summary: str = "something") -> Finding:
    return Finding(
        category=category,
        file_path=file_path,
        severity=Severity.LOW,
        summary=summary,
        evidence="evidence",
    )


def test_perfect_detection_scores_one():
    expected = [ExpectedFinding("unused_module", "legacy.py")]
    actual = [_finding("unused_module", "legacy.py")]

    result = evaluate(expected, actual)

    assert result.recall == 1.0
    assert result.precision == 1.0


def test_wording_does_not_affect_matching():
    """The model rephrases every re-recording. Scoring prose would measure the wrong thing."""
    expected = [ExpectedFinding("unused_module", "legacy.py")]

    result = evaluate(expected, [_finding("unused_module", "legacy.py", "totally different words")])

    assert result.recall == 1.0


def test_missed_defect_lowers_recall_only():
    expected = [ExpectedFinding("unused_module", "a.py"), ExpectedFinding("dead_asset", "b.svg")]
    actual = [_finding("unused_module", "a.py")]

    result = evaluate(expected, actual)

    assert result.recall == 0.5
    assert result.precision == 1.0


def test_false_positive_lowers_precision_only():
    expected = [ExpectedFinding("unused_module", "a.py")]
    actual = [_finding("unused_module", "a.py"), _finding("unused_module", "main.py")]

    result = evaluate(expected, actual)

    assert result.recall == 1.0
    assert result.precision == 0.5


def test_duplicate_reports_cannot_inflate_recall():
    """Each expectation consumes one finding, so repeating a defect is not free."""
    expected = [ExpectedFinding("unused_module", "a.py")]
    actual = [_finding("unused_module", "a.py"), _finding("unused_module", "a.py")]

    result = evaluate(expected, actual)

    assert result.recall == 1.0
    assert result.precision == 0.5
    assert len(result.spurious) == 1


def test_reporting_nothing_is_precise_but_not_recalled():
    """An auditor that says nothing makes no false claims. Recall is what catches it."""
    result = evaluate([ExpectedFinding("unused_module", "a.py")], [])

    assert result.precision == 1.0
    assert result.recall == 0.0


def test_summary_names_what_went_wrong():
    result = evaluate([ExpectedFinding("unused_module", "a.py")], [_finding("other", "b.py")])

    summary = result.summary()

    assert "unused_module" in summary
    assert "b.py" in summary


def test_load_expected_reads_golden_file(tmp_path):
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps({"expected_findings": [{"category": "unused_module", "file_path": "x.py"}]})
    )

    assert load_expected(golden) == [ExpectedFinding("unused_module", "x.py")]

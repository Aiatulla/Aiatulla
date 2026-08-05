from pathlib import Path

import pytest

from app.auditors.base import AuditorError, render_repository
from app.auditors.dead_code import DeadCodeAuditor
from app.llm.protocol import Response, ToolCall
from app.llm.usage import build_usage
from app.schemas.finding import Severity

FIXTURE = Path(__file__).parent / "fixtures" / "repo_a"
MODEL = "gemini-2.0-flash"


def _response(*tool_calls: ToolCall, text: str | None = None) -> Response:
    return Response(
        model=MODEL,
        usage=build_usage(MODEL, input_tokens=10, output_tokens=10),
        text=text,
        tool_calls=tool_calls,
    )


def _call(*findings: dict) -> ToolCall:
    return ToolCall(name="report_findings", arguments={"findings": list(findings)})


def test_valid_tool_call_becomes_findings():
    auditor = DeadCodeAuditor()
    response = _response(
        _call(
            {
                "category": "unused_module",
                "file_path": "legacy_export.py",
                "severity": "low",
                "summary": "Nothing imports this module",
                "evidence": "No import of legacy_export anywhere in the tree",
            }
        )
    )

    findings = auditor.parse(response)

    assert len(findings) == 1
    assert findings[0].category == "unused_module"
    assert findings[0].severity is Severity.LOW


def test_prose_reply_is_an_error_not_an_empty_result():
    """An empty list would be indistinguishable from an auditor that found nothing."""
    auditor = DeadCodeAuditor()

    with pytest.raises(AuditorError, match="no tool call"):
        auditor.parse(_response(text="I think legacy_export.py might be unused."))


def test_finding_that_fails_validation_is_an_error():
    auditor = DeadCodeAuditor()
    response = _response(_call({"category": "unused_module", "severity": "catastrophic"}))

    with pytest.raises(AuditorError, match="failed validation"):
        auditor.parse(response)


def test_empty_findings_array_is_valid():
    """A clean repository is a legitimate answer, unlike a prose reply."""
    assert DeadCodeAuditor().parse(_response(_call())) == []


def test_rendered_repository_is_deterministic():
    """The cassette key hashes this text. An unsorted walk would change the key
    per machine and every cassette would miss."""
    assert render_repository(FIXTURE) == render_repository(FIXTURE)


def test_rendered_repository_contains_the_source_files():
    rendered = render_repository(FIXTURE)

    assert "legacy_export.py" in rendered
    assert "def export_to_csv" in rendered


def test_rendered_repository_skips_ignored_directories(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')")
    junk = tmp_path / "node_modules" / "left-pad"
    junk.mkdir(parents=True)
    (junk / "index.js").write_text("module.exports = 1")

    rendered = render_repository(tmp_path)

    assert "app.py" in rendered
    assert "left-pad" not in rendered


def test_tool_schema_has_no_refs():
    """Provider function calling rejects $ref and $defs, which Pydantic emits for enums."""
    schema = DeadCodeAuditor().tool.parameters
    serialised = str(schema)

    assert "$ref" not in serialised
    assert "$defs" not in serialised
    assert "critical" in serialised, "the severity enum must survive inlining"

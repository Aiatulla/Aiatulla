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


def test_lock_files_and_images_are_not_sent(tmp_path):
    """package-lock.json is 223KB of dependency hashes and an SVG is coordinates.
    Neither tells a model anything about code quality, and both crowd out source."""
    (tmp_path / "app.py").write_text("print('hi')")
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}')
    (tmp_path / "logo.svg").write_text("<svg><path d='M0 0'/></svg>")
    (tmp_path / "uv.lock").write_text("version = 1")

    rendered = render_repository(tmp_path)

    assert "app.py" in rendered
    assert "package-lock.json" not in rendered
    assert "logo.svg" not in rendered
    assert "uv.lock" not in rendered


def test_tool_caches_are_not_sent(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    cache = tmp_path / ".mypy_cache" / "3.11"
    cache.mkdir(parents=True)
    (cache / "cache.db").write_text("binary-ish junk" * 100)

    rendered = render_repository(tmp_path)

    assert "app.py" in rendered
    assert "cache.db" not in rendered


def test_an_oversized_repository_is_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr("app.auditors.base.MAX_PROMPT_BYTES", 2_000)
    for index in range(20):
        (tmp_path / f"file_{index}.py").write_text("x = 1\n" * 100)

    rendered = render_repository(tmp_path)

    assert len(rendered) <= 2_000 + 1_000, "the note itself is allowed to exceed slightly"


def test_truncation_is_declared_in_the_prompt(tmp_path, monkeypatch):
    """An auditor that silently saw half a repository would report on half a
    repository while looking exactly like one that had seen all of it."""
    monkeypatch.setattr("app.auditors.base.MAX_PROMPT_BYTES", 2_000)
    for index in range(20):
        (tmp_path / f"file_{index}.py").write_text("x = 1\n" * 100)

    rendered = render_repository(tmp_path)

    assert "exceeds the size that fits in one request" in rendered
    assert "Do not draw conclusions about files you were not shown" in rendered


def test_a_small_repository_is_not_declared_truncated(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")

    assert "exceeds the size" not in render_repository(tmp_path)


def test_small_files_are_kept_when_the_budget_is_tight(tmp_path, monkeypatch):
    """Large files first would eat the budget and hide dozens of small ones, and
    small source files are where most findings are."""
    monkeypatch.setattr("app.auditors.base.MAX_PROMPT_BYTES", 3_000)
    (tmp_path / "huge.py").write_text("# padding\n" * 500)
    for index in range(5):
        (tmp_path / f"small_{index}.py").write_text(f"value = {index}")

    rendered = render_repository(tmp_path)

    for index in range(5):
        assert f"small_{index}.py ---" in rendered, "small files should survive"

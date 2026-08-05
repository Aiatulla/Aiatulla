"""End to end over the machinery, with the model itself stubbed out.

The evaluation in tests/eval/ measures how well the model detects things. This
measures that everything around the model is wired together: rendering the
repository, building the tool schema, validating the reply, and scoring it.
"""

from pathlib import Path

import pytest

from app.auditors.dead_code import DeadCodeAuditor
from app.cloner import CloneError, clone_repository
from app.evaluation import evaluate, load_expected
from app.llm.protocol import Response, ToolCall
from app.llm.usage import build_usage

FIXTURE = Path(__file__).parent / "fixtures" / "repo_a"
MODEL = "gemini-2.0-flash"


class StubClient:
    """Returns a fixed reply, so the pipeline can be tested without a model."""

    def __init__(self, findings: list[dict]) -> None:
        self._findings = findings
        self.received_system: str | None = None
        self.received_tools: list | None = None

    async def complete(self, messages, tools=None, system=None) -> Response:
        self.received_system = system
        self.received_tools = tools
        return Response(
            model=MODEL,
            usage=build_usage(MODEL, input_tokens=100, output_tokens=50),
            tool_calls=(ToolCall(name="report_findings", arguments={"findings": self._findings}),),
        )


async def test_a_perfect_auditor_scores_perfectly_on_the_fixture():
    """Proves golden.json, the Finding schema and the scorer agree with each other.

    If this fails, the fixture is wrong rather than the model.
    """
    client = StubClient(
        [
            {
                "category": "unused_module",
                "file_path": "legacy_export.py",
                "severity": "low",
                "summary": "Nothing imports this module",
                "evidence": "No import of legacy_export in the tree",
            },
            {
                "category": "commented_out_code",
                "file_path": "formatting.py",
                "severity": "info",
                "summary": "Two implementations are disabled by comments",
                "evidence": "strikethrough and underline are commented out",
            },
        ]
    )

    findings = await DeadCodeAuditor().run(client, FIXTURE)
    result = evaluate(load_expected(FIXTURE / "golden.json", "dead_code"), findings)

    assert result.recall == 1.0, result.summary()
    assert result.precision == 1.0, result.summary()


async def test_auditor_sends_its_prompt_and_tool_to_the_model():
    client = StubClient([])

    await DeadCodeAuditor().run(client, FIXTURE)

    assert client.received_system is not None
    assert "dead code" in client.received_system
    assert client.received_tools is not None
    assert client.received_tools[0].name == "report_findings"


async def test_workspace_is_removed_when_the_clone_fails(monkeypatch):
    """A failed audit must not leave the disk filling up behind it."""
    created: list[Path] = []

    async def fail_after_creating_workspace(url: str, destination: Path) -> None:
        created.append(destination)
        raise CloneError("simulated git failure")

    monkeypatch.setattr("app.cloner._run_git_clone", fail_after_creating_workspace)

    with pytest.raises(CloneError, match="simulated"):
        async with clone_repository("https://github.com/example/repo"):
            pass

    assert created, "the workspace should have been created before the failure"
    assert not created[0].exists(), "the workspace must be cleaned up on failure"


async def test_rejected_url_never_reaches_git(monkeypatch):
    async def should_not_run(url: str, destination: Path) -> None:
        raise AssertionError("git must not be invoked for a rejected URL")

    monkeypatch.setattr("app.cloner._run_git_clone", should_not_run)

    with pytest.raises(CloneError, match="scheme"):
        async with clone_repository("file:///etc/passwd"):
            pass

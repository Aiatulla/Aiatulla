from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from app.llm.protocol import LLMClient, Message, Response, Tool
from app.schemas.finding import Finding, findings_tool_schema

# Files an auditor never reads. Reading them wastes tokens and, for lock files,
# floods the prompt with content that tells the model nothing about the code.
IGNORED_DIRECTORIES = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".next"})
IGNORED_SUFFIXES = frozenset({".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"})

MAX_FILE_BYTES = 50_000


class AuditorError(RuntimeError):
    """Raised when an auditor cannot produce findings from a model reply."""


class Auditor(ABC):
    """One specialised reviewer.

    A subclass supplies three things: a name, a system prompt, and a description
    of what its tool collects. Everything else, including reading the repository
    and validating the reply, is shared.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, used in results and evaluation fixtures."""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Instructions describing what this auditor looks for."""

    @property
    @abstractmethod
    def tool_description(self) -> str:
        """What the findings array should contain, shown to the model."""

    @property
    def tool(self) -> Tool:
        return Tool(
            name="report_findings",
            description=self.tool_description,
            parameters=findings_tool_schema("report_findings", self.tool_description),
        )

    async def run(self, client: LLMClient, repository: Path) -> list[Finding]:
        """Audit a checked-out repository and return validated findings."""
        response = await client.complete(
            messages=[Message(role="user", content=render_repository(repository))],
            tools=[self.tool],
            system=self.system_prompt,
        )
        return self.parse(response)

    def parse(self, response: Response) -> list[Finding]:
        """Validate the model's tool call into Findings.

        :raises AuditorError: when the model answered in prose or produced a
            payload that does not match the schema. Both are failures worth
            surfacing: returning an empty list would be indistinguishable from an
            auditor that legitimately found nothing.
        """
        if not response.tool_calls:
            raise AuditorError(f"{self.name} returned no tool call. Text was: {response.text!r}")

        raw_findings = response.tool_calls[0].arguments.get("findings")
        if raw_findings is None:
            raise AuditorError(f"{self.name} tool call had no findings key")

        try:
            return [Finding.model_validate(item) for item in raw_findings]
        except ValidationError as exc:
            raise AuditorError(
                f"{self.name} produced a finding that failed validation: {exc}"
            ) from exc


def render_repository(root: Path) -> str:
    """Flatten a repository into one prompt-ready string.

    Deterministic ordering matters more than it looks: the cassette key hashes
    this text, so an unsorted walk would produce a different key on every machine
    and every cassette would miss.
    """
    sections = [f"Repository tree:\n{_render_tree(root)}\n"]

    for path in sorted(_readable_files(root)):
        relative = path.relative_to(root)
        content = path.read_text(errors="replace")[:MAX_FILE_BYTES]
        sections.append(f"--- {relative} ---\n{content}")

    return "\n".join(sections)


def _readable_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not _is_ignored(path.relative_to(root))
        and path.suffix not in IGNORED_SUFFIXES
    ]


def _render_tree(root: Path) -> str:
    paths = sorted(str(path.relative_to(root)) for path in _readable_files(root))
    return "\n".join(paths)


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in relative.parts)

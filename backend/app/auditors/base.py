from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from app.llm.protocol import LLMClient, Message, Response, Tool
from app.schemas.finding import Finding, findings_tool_schema

# Files an auditor never reads. Reading them wastes tokens and, for lock files,
# floods the prompt with content that tells the model nothing about the code.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".next",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "vendor",
    }
)
IGNORED_SUFFIXES = frozenset(
    {
        ".lock",
        # Vector images are enormous and are coordinates, not code. One profile
        # SVG contributed 50,000 bytes of path data to every prompt.
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".webp",
        ".pdf",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".map",
        ".min.js",
        ".csv",
        ".parquet",
    }
)
# Lock files that do not end in .lock. package-lock.json alone is 223KB of
# dependency hashes.
IGNORED_NAMES = frozenset(
    {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "Gemfile.lock"}
)

MAX_FILE_BYTES = 50_000

# Ceiling on the whole prompt.
#
# Derived from the limit rather than picked. Three auditors run within the same
# minute, the smallest free tier allows 250,000 input tokens per minute, and
# cassettes measured the real ratio at 3.84 characters per token.
#
# Sizing exactly to the limit still failed in practice: a run does not start with
# an empty allowance, because earlier attempts and other work already consumed
# part of the window. Three auditors at this size is roughly 117,000 tokens,
# leaving half the free-tier minute spare.
#
# Raise it on a paid tier, where per-minute limits are far higher. Truncation is
# disclosed in the prompt either way, so a smaller value costs coverage rather
# than correctness.
MAX_PROMPT_BYTES = 150_000


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

    A repository larger than MAX_PROMPT_BYTES is cut short, and the prompt says
    so in the text the model reads. An auditor that silently saw half a
    repository would report on half a repository while looking exactly like one
    that had seen all of it.
    """
    tree = _render_tree(root)
    sections = [f"Repository tree:\n{tree}\n"]
    budget = MAX_PROMPT_BYTES - len(sections[0])

    included: list[Path] = []
    skipped: list[Path] = []

    # Smallest first. A handful of large files would otherwise consume the whole
    # budget and hide dozens of small ones, and small source files are where
    # most findings are.
    for path in sorted(_readable_files(root), key=lambda p: (p.stat().st_size, str(p))):
        relative = path.relative_to(root)
        content = path.read_text(errors="replace")[:MAX_FILE_BYTES]
        section = f"--- {relative} ---\n{content}"

        if len(section) > budget:
            skipped.append(relative)
            continue

        budget -= len(section)
        included.append(relative)
        sections.append(section)

    if skipped:
        # Stated to the model, not just logged, so it does not report confidently
        # on files it was never shown.
        sections.insert(
            1,
            f"NOTE: this repository exceeds the size that fits in one request. "
            f"{len(skipped)} of {len(included) + len(skipped)} files were not "
            f"included: {', '.join(str(p) for p in sorted(skipped)[:20])}"
            f"{' and others' if len(skipped) > 20 else ''}. "
            f"Do not draw conclusions about files you were not shown.\n",
        )

    # Deterministic despite the size-ordered walk: the sections were appended in
    # a stable order, so the same repository renders to the same text every time.
    return "\n".join(sections)


def _readable_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not _is_ignored(path.relative_to(root))
        and path.suffix not in IGNORED_SUFFIXES
        and path.name not in IGNORED_NAMES
    ]


def _render_tree(root: Path) -> str:
    paths = sorted(str(path.relative_to(root)) for path in _readable_files(root))
    return "\n".join(paths)


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in relative.parts)

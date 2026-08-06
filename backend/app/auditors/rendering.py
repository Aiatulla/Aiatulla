from pathlib import Path

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
    sections = [f"Repository tree:\n{render_tree(root)}\n"]
    budget = MAX_PROMPT_BYTES - len(sections[0])

    included: list[Path] = []
    skipped: list[Path] = []

    # Smallest first. A handful of large files would otherwise consume the whole
    # budget and hide dozens of small ones, and small source files are where
    # most findings are.
    for path in sorted(readable_files(root), key=lambda p: (p.stat().st_size, str(p))):
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
        sections.insert(1, _truncation_note(included, skipped))

    return "\n".join(sections)


def _truncation_note(included: list[Path], skipped: list[Path]) -> str:
    listed = ", ".join(str(p) for p in sorted(skipped)[:20])
    suffix = " and others" if len(skipped) > 20 else ""
    return (
        f"NOTE: this repository exceeds the size that fits in one request. "
        f"{len(skipped)} of {len(included) + len(skipped)} files were not "
        f"included: {listed}{suffix}. "
        f"Do not draw conclusions about files you were not shown.\n"
    )


def readable_files(root: Path) -> list[Path]:
    """Every file worth showing a model, excluding noise and generated content."""
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not _is_ignored(path.relative_to(root))
        and path.suffix not in IGNORED_SUFFIXES
        and path.name not in IGNORED_NAMES
    ]


def render_tree(root: Path) -> str:
    return "\n".join(sorted(str(path.relative_to(root)) for path in readable_files(root)))


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in relative.parts)

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

# A repository URL comes from whoever calls the API, so it is untrusted input and
# every limit below exists to stop a hostile or careless one.
ALLOWED_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org"})
CLONE_TIMEOUT_SECONDS = 60.0
MAX_REPO_BYTES = 100 * 1024 * 1024


class CloneError(RuntimeError):
    """Raised when a repository cannot be cloned safely."""


def validate_repo_url(url: str) -> str:
    """Check a repository URL before it reaches git.

    :raises CloneError: when the URL could reach somewhere it should not.
    """
    parsed = urlparse(url)

    # Only https. file:// would read the server's own disk, ssh:// and git://
    # would use the server's credentials or skip host verification.
    if parsed.scheme != "https":
        raise CloneError(f"Only https URLs are allowed, got {parsed.scheme or 'no'} scheme")

    # Credentials in the URL would be logged and could be someone else's.
    if "@" in parsed.netloc:
        raise CloneError("URLs with embedded credentials are not allowed")

    if parsed.hostname not in ALLOWED_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_HOSTS))
        raise CloneError(f"Host {parsed.hostname!r} is not allowed. Allowed hosts: {allowed}")

    return url


def directory_size_bytes(path: Path) -> int:
    """Total size of every real file below path.

    Symlinks are skipped entirely rather than measured. A cloned repository can
    contain them, and following one would both mis-count the size and read a file
    outside the workspace.
    """
    return sum(
        item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink()
    )


@asynccontextmanager
async def clone_repository(url: str) -> AsyncIterator[Path]:
    """Clone a repository into a temporary directory for the duration of the block.

    The directory is removed on the way out whether the body succeeded or raised,
    so a failed audit cannot leave the disk filling up behind it.

    :raises CloneError: on a rejected URL, a timeout, a git failure or an
        oversized repository.
    """
    validate_repo_url(url)
    workspace = Path(tempfile.mkdtemp(prefix="repo-radar-"))

    try:
        await _run_git_clone(url, workspace)
        _enforce_size_limit(workspace)
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


async def _run_git_clone(url: str, destination: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        # One commit of one branch: an audit reads the current tree, and full
        # history on a large repository is slow and can be enormous.
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        # Submodules would fetch further URLs that never passed the host check.
        "--recurse-submodules=no",
        url,
        str(destination / "repo"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Stops git prompting for credentials on a private repository and hanging
        # until the timeout instead of failing straight away.
        env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=CLONE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise CloneError(f"Clone timed out after {CLONE_TIMEOUT_SECONDS} seconds") from exc

    if process.returncode != 0:
        raise CloneError(f"git clone failed: {stderr.decode(errors='replace').strip()}")


def _enforce_size_limit(workspace: Path) -> None:
    size = directory_size_bytes(workspace)
    if size > MAX_REPO_BYTES:
        raise CloneError(f"Repository is {size} bytes, over the {MAX_REPO_BYTES} byte limit")

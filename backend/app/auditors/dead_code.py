from app.auditors.base import Auditor

SYSTEM_PROMPT = """\
You audit a repository for dead code: code and assets that are present but not \
reachable from anything the project actually runs.

Report only these categories:
- unused_module: a source file that nothing imports, references or executes
- unused_declaration: an exported function, class or constant with no reader
- unreferenced_asset: a committed file nothing links to or loads
- commented_out_code: a block of real code disabled by comments, left in place

Rules you must follow:
- Report a finding only when you can point at evidence in the files you were \
given. If reachability is uncertain, do not report it.
- An entry point is not dead. Treat main modules, CLI entry points, test files, \
configuration and package metadata as reachable by definition.
- Something referenced only from a comment is still unreferenced.
- Severity is low or info for dead code. It slows readers down, it does not \
break anything at runtime.
- Report nothing rather than pad the list. A false finding costs a reader more \
than a missed one.
"""


class DeadCodeAuditor(Auditor):
    """Finds code and assets that nothing reaches."""

    @property
    def name(self) -> str:
        return "dead_code"

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tool_description(self) -> str:
        return (
            "Every piece of dead code found in the repository. "
            "An empty array is a valid answer when the repository has none."
        )

from dataclasses import dataclass
from enum import StrEnum

from app.models.run import FindingRow


class Change(StrEnum):
    """How a finding compares to the previous run of the same repository."""

    NEW = "new"
    """Not present last time. Something got worse, or the auditor got better."""

    FIXED = "fixed"
    """Present last time, gone now."""

    PERSISTING = "persisting"
    """Present in both runs, and still unaddressed."""


# What makes two findings across two runs "the same finding".
#
# Line numbers are excluded on purpose: adding an import above a defect shifts
# every line below it, and a diff that called that "fixed plus new" would be
# noise on every run.
#
# Wording is excluded for the same reason the evaluation ignores it. A model
# rephrases the same defect every time it runs, so comparing summaries would
# report churn that never happened.
#
# ponytail: two findings of the same category in the same file therefore count
# as one. Acceptable while categories are file-level. If a category ever fires
# several times per file, add a normalised code snippet to the identity.
FindingIdentity = tuple[str, str, str]


def identity_of(finding: FindingRow) -> FindingIdentity:
    return (finding.auditor, finding.category, finding.file_path)


@dataclass(frozen=True)
class DiffEntry:
    """One finding, and what changed about it."""

    change: Change
    auditor: str
    category: str
    file_path: str
    severity: str
    summary: str

    @classmethod
    def from_finding(cls, finding: FindingRow, change: Change) -> "DiffEntry":
        return cls(
            change=change,
            auditor=finding.auditor,
            category=finding.category,
            file_path=finding.file_path,
            severity=finding.severity,
            summary=finding.summary,
        )


@dataclass(frozen=True)
class RunDiff:
    """What changed between two runs of the same repository."""

    entries: tuple[DiffEntry, ...]

    @property
    def new(self) -> tuple[DiffEntry, ...]:
        return tuple(entry for entry in self.entries if entry.change is Change.NEW)

    @property
    def fixed(self) -> tuple[DiffEntry, ...]:
        return tuple(entry for entry in self.entries if entry.change is Change.FIXED)

    @property
    def persisting(self) -> tuple[DiffEntry, ...]:
        return tuple(entry for entry in self.entries if entry.change is Change.PERSISTING)

    @property
    def is_unchanged(self) -> bool:
        return not self.new and not self.fixed


def diff_findings(
    previous: list[FindingRow],
    current: list[FindingRow],
) -> RunDiff:
    """Compare two runs' findings.

    A fixed finding is described using the previous run's row, because it does
    not exist in the current one. Everything else uses the current row, so a
    reader sees the latest wording.
    """
    previous_by_identity = {identity_of(finding): finding for finding in previous}
    current_by_identity = {identity_of(finding): finding for finding in current}

    entries = [
        DiffEntry.from_finding(
            finding,
            Change.PERSISTING if identity in previous_by_identity else Change.NEW,
        )
        for identity, finding in current_by_identity.items()
    ]

    entries += [
        DiffEntry.from_finding(finding, Change.FIXED)
        for identity, finding in previous_by_identity.items()
        if identity not in current_by_identity
    ]

    return RunDiff(entries=tuple(entries))


def diff_against_nothing(current: list[FindingRow]) -> RunDiff:
    """Describe the first ever run of a repository.

    Every finding is new, because there is no baseline. Saying that plainly is
    better than refusing to answer: it is the honest description of a first run,
    and it is what every audit that scanned this profile could not produce.
    """
    return RunDiff(
        entries=tuple(DiffEntry.from_finding(finding, Change.NEW) for finding in current)
    )

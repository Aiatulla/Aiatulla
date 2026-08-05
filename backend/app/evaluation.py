import json
from dataclasses import dataclass
from pathlib import Path

from app.schemas.finding import Finding


@dataclass(frozen=True)
class ExpectedFinding:
    """A defect deliberately planted in a fixture repository.

    Matching is on category and file, not on wording. The model will phrase the
    same defect differently every time it is re-recorded, and an evaluation that
    broke on rephrasing would measure prose, not detection.
    """

    category: str
    file_path: str

    def matches(self, finding: Finding) -> bool:
        return finding.category == self.category and finding.file_path == self.file_path


@dataclass(frozen=True)
class EvalResult:
    """How one auditor scored against one fixture repository."""

    matched: tuple[ExpectedFinding, ...]
    missed: tuple[ExpectedFinding, ...]
    spurious: tuple[Finding, ...]

    @property
    def recall(self) -> float:
        """Share of planted defects that were found.

        A perfect score on an empty expectation set: nothing was there to miss.
        """
        expected_count = len(self.matched) + len(self.missed)
        if expected_count == 0:
            return 1.0
        return len(self.matched) / expected_count

    @property
    def precision(self) -> float:
        """Share of reported findings that were real.

        An auditor that reports nothing is precise by default. That is the honest
        reading: it made no false claims. Recall is what catches it saying nothing.
        """
        reported_count = len(self.matched) + len(self.spurious)
        if reported_count == 0:
            return 1.0
        return len(self.matched) / reported_count

    def summary(self) -> str:
        """One line for an assertion message, so a failure says what went wrong."""
        return (
            f"precision={self.precision:.2f} recall={self.recall:.2f} "
            f"matched={len(self.matched)} missed={[m.category for m in self.missed]} "
            f"spurious={[(s.category, s.file_path) for s in self.spurious]}"
        )


def load_expected(golden_path: Path, auditor: str) -> list[ExpectedFinding]:
    """Read the defects planted for one auditor in a fixture repository.

    Expectations are keyed by auditor because a fixture usually carries defects
    for several of them, and each must be scored only on the ones it owns.

    An auditor with no entry expects nothing. That is a real case worth
    supporting: it asserts the auditor stays quiet on a repository that has
    nothing for it, which is how false positives get caught.
    """
    raw = json.loads(golden_path.read_text())
    return [
        ExpectedFinding(category=item["category"], file_path=item["file_path"])
        for item in raw["expected_findings"].get(auditor, [])
    ]


def evaluate(expected: list[ExpectedFinding], actual: list[Finding]) -> EvalResult:
    """Score findings against the defects that were planted.

    Each expectation consumes at most one finding, so an auditor cannot inflate
    recall by reporting the same defect several times.
    """
    unclaimed = list(actual)
    matched: list[ExpectedFinding] = []
    missed: list[ExpectedFinding] = []

    for expectation in expected:
        hit = next((finding for finding in unclaimed if expectation.matches(finding)), None)
        if hit is None:
            missed.append(expectation)
        else:
            matched.append(expectation)
            unclaimed.remove(hit)

    return EvalResult(matched=tuple(matched), missed=tuple(missed), spurious=tuple(unclaimed))

from app.auditors.base import Auditor

SYSTEM_PROMPT = """\
You audit a repository's tests for whether they would actually catch a \
regression.

Report only these categories:
- assertion_free_test: a test that runs code but asserts nothing, so it passes \
whatever the code does
- disabled_test: a test committed as skipped, xfail or commented out, with no \
reason given
- tautological_assertion: an assertion that cannot fail, such as comparing a \
value to itself or asserting a literal
- untested_critical_path: a module carrying money, authentication or data \
deletion logic with no test referencing it

Rules you must follow:
- Judge whether the test would fail if the code under it broke. That is the \
only question that matters.
- A test with few assertions is not automatically weak. A single precise \
assertion can be stronger than ten vague ones.
- A skipped test with a written reason is a decision, not a defect.
- Do not report missing tests for trivial code such as plain data holders or \
one-line accessors.
- Report nothing rather than pad the list.
"""


class TestQualityAuditor(Auditor):
    """Finds tests that would not catch a regression."""

    @property
    def name(self) -> str:
        return "test_quality"

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tool_description(self) -> str:
        return (
            "Every test quality defect found in the repository. "
            "An empty array is a valid answer when the tests are sound."
        )

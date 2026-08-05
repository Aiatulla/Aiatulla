"""Record evaluation cassettes against a real provider.

Run by hand, rarely. Everything else replays what this writes, which is what keeps
the test suite free, offline and deterministic.

    GEMINI_API_KEY=... python scripts/record_cassettes.py

Re-record when a prompt, tool schema or model changes: the cassette key covers all
three, so the evaluation will fail with a miss rather than replay a stale answer.
"""

import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.auditors.base import Auditor  # noqa: E402
from app.auditors.dead_code import DeadCodeAuditor  # noqa: E402
from app.auditors.security import SecurityAuditor  # noqa: E402
from app.auditors.test_quality import TestQualityAuditor  # noqa: E402
from app.llm.cassette import CassetteClient, CassetteMode  # noqa: E402
from app.llm.providers.gemini import GeminiClient  # noqa: E402

MODEL = "gemini-2.0-flash"
CASSETTE_DIR = BACKEND_ROOT / "tests" / "cassettes"
FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures"

AUDITORS: list[Auditor] = [DeadCodeAuditor(), SecurityAuditor(), TestQualityAuditor()]
FIXTURES = ["repo_a", "repo_b"]


async def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is not set. Recording calls the real provider.")
        return 1

    client = CassetteClient(
        cassette_dir=CASSETTE_DIR,
        model=MODEL,
        mode=CassetteMode.RECORD,
        inner=GeminiClient(api_key=api_key, model=MODEL),
    )

    for auditor in AUDITORS:
        for fixture in FIXTURES:
            findings = await auditor.run(client, FIXTURE_DIR / fixture)
            print(f"{auditor.name} on {fixture}: recorded {len(findings)} findings")

    print(f"\nCassettes written to {CASSETTE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

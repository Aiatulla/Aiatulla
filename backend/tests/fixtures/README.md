# Evaluation fixtures

Each directory here is a small repository with defects planted on purpose, plus a
`golden.json` naming what an auditor is expected to find in it.

## How scoring works

`app/evaluation.py` matches a finding to an expectation on **category and file
path only**, never on wording. The model rephrases the same defect every time the
cassettes are re-recorded, so an evaluation that compared sentences would measure
prose rather than detection.

- **Recall** answers: did it find the planted defects?
- **Precision** answers: was what it reported real?

Both are asserted against a committed threshold in `tests/eval/`. A prompt change
that degrades either one fails the build.

## Adding a fixture

1. Create a directory with a believable small project. It must have a genuine live
   path, otherwise precision is meaningless: everything in it would be dead.
2. Plant defects that a careful reviewer would agree on. Ambiguous ones make the
   threshold noisy and the suite flaky.
3. Write `golden.json` with a `why_planted` note for each expectation, so a future
   reader can tell a real regression from a fixture that was always wrong.
4. Record cassettes: see `scripts/record_cassettes.py`.

## Cassettes

The evaluation runs entirely from recorded cassettes, so it costs nothing, needs
no API key, and cannot flake on model non-determinism.

`tests/cassettes/` is generated, not written by hand. If a prompt, tool schema or
model changes, the cassette key changes and the test fails with a miss rather than
replaying an answer to the previous question. Re-record when that happens.

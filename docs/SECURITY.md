# Security

repo-radar takes two things from strangers: a repository URL and an API key. This
document describes what is done about each.

## Reporting a vulnerability

Open a GitHub issue for anything already public. For something exploitable, email
the maintainer rather than filing publicly, and allow time for a fix before
disclosure.

## The two trust boundaries

### 1. The repository URL

Anyone can submit any URL, so `backend/app/cloner.py` treats it as hostile.

| Limit | What it stops |
| --- | --- |
| https only | `file://` reads the server's own disk; `ssh://` uses the server's keys; `git://` skips host verification |
| Host allowlist | Arbitrary internal hosts, and `169.254.169.254`, the cloud metadata endpoint |
| No credentials in the URL | `https://user:token@host/...` would be written to logs |
| `--recurse-submodules=no` | Submodules fetch further URLs that never passed the host check |
| `GIT_TERMINAL_PROMPT=0` | A private repository hanging on a credential prompt until timeout |
| 60 second timeout | A slow or endless clone holding a worker |
| 100 MB cap | Filling the disk |
| Symlinks skipped when measuring | Following one would mis-count size and read outside the workspace |
| Cleanup in `finally` | A failed audit leaving the disk filling up |

Each has a test in `backend/tests/test_cloner.py`, named for the attack it blocks.

The URL is validated at the API boundary as well as in the cloner, so a bad URL
is an error the caller sees rather than a run that fails quietly later.

### 2. The API key

The key belongs to the caller. It is used for one run and never retained.

- Arrives in the `X-LLM-Key` **header**, not the body. Bodies are logged far more
  casually and appear in error reports and traces.
- Validated at the edge, so a bad key fails before a repository is cloned.
- Held as `SecretStr`, which renders as `**********` in a repr, an f-string, a
  `model_dump()` or a traceback. Unwrapped only where it is handed to the provider.
- Passed to providers as a **header**, never a query parameter, because URLs reach
  server logs, proxy logs and error traces.
- **No database column exists for it**, anywhere.
- Never included in an error message. `provider_for_key` rejects unknown keys
  without repeating the value.

Asserted by `tests/test_byok.py` and `tests/test_settings_secrets.py`, including a
test that searches every table for the key and one that scans captured log output.

## What is deliberately not protected

Stated plainly rather than left to be discovered.

- **No rate limiting.** Anyone reaching the API can start runs. The cloner's caps
  bound the damage per run, but not the number of runs. **This must be added
  before any public deployment.**
- **No authentication.** There are no accounts. Runs are readable by anyone with
  the run id, which is a UUID but not a secret.
- **No tenant isolation.** Every run is visible in the run list.
- **Model output is trusted as data.** A repository containing text that tries to
  instruct the model could influence what it reports. Findings are constrained by
  a tool schema, so the damage is limited to a misleading finding rather than code
  execution, but prompt injection is not otherwise defended against.
- **Cloned code is never executed.** It is read as text and sent to the model.
  There is no build step, no dependency install, and no test run.

## Secrets in this repository

`backend/tests/fixtures/` contains code with deliberately planted credentials.
They are fake, they open nothing, and they exist so the `security` auditor has
something to find.

They are written as low-entropy dictionary words on purpose. A realistic-looking
key would be flagged by secret scanners and blocked by GitHub push protection —
a fixture written to be found by our auditor should not trip everyone else's.

Real configuration lives in `backend/.env`, which is gitignored. `.env.example`
lists variable names with blank or throwaway local-development values.

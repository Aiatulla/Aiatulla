# Changelog

Notable changes to repo-radar. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-06

First release. The audit pipeline works end to end and every auditor is measured.

### Added

- **Multi-agent auditing.** Three auditors — `dead_code`, `security`,
  `test_quality` — run concurrently over one repository and report through typed
  tool schemas rather than prose.
- **Evaluation harness.** Fixture repositories with deliberately planted defects
  and golden expectations. Precision and recall are asserted per auditor in CI, so
  a prompt edit that detects less fails the build. Current: 1.00 on both, for all
  three auditors.
- **Record and replay cassettes.** Real model responses recorded once and replayed
  thereafter, so the test suite runs offline, costs nothing, and cannot flake on
  model non-determinism.
- **Three providers.** Anthropic, Gemini and OpenAI behind one interface, selected
  from the shape of the caller's key.
- **Per-run cost ceiling.** Every call is priced from its prompt before it is sent
  and charged against a reservation, so concurrent auditors cannot collectively
  exceed the limit.
- **Token rate limiting.** Requests are paced inside the provider's
  tokens-per-minute allowance rather than being sent, rejected and retried.
- **Bring your own key.** The caller's credential arrives per request in a header,
  is never persisted, logged or returned, and is validated before any work starts.
- **Run history and diffs.** Every run is stored and compared against the previous
  completed run of the same repository: new, fixed, or still there.
- **Live progress** over WebSocket, with a polling fallback.
- **Web interface.** Submit a repository, watch a run, read findings, see what
  changed.
- **Containerised.** Both services build as non-root images; migrations run on
  boot.

### Security

- Repository URLs are treated as untrusted input: https only, host allowlist
  which also blocks the cloud metadata endpoint, no embedded credentials, no
  submodule recursion, timeout, size cap, and guaranteed cleanup.
- Rate limiting on run creation.
- API keys held as `SecretStr` so they cannot leak through a repr, an f-string, a
  `model_dump()` or a traceback.

### Known limitations

Recorded in the README rather than discovered later: no authentication, a
per-process rate limiter, a hardcoded price table that will drift, an evaluation
corpus of two fixtures, and no deployment.

[0.1.0]: https://github.com/Aiatulla/repo-radar/releases/tag/v0.1.0

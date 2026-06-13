---
name: registering-review-agent-gate-completeness
description: "Registering a new review agent must pass the FULL tests/review/ suite (esp. test_context_policy tier classification), not just test_registry/test_evals; and don't pipe pytest through `| tail` when checking exit codes."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d223e8a5-1474-42c2-8088-d811bc966678
---

When adding a new review agent to `src/framework_cli/review/registry.py`, there are MORE gates than `test_registry.py` + `test_evals.py`:

- `tests/review/test_context_policy.py::test_every_agent_has_an_explicit_context_strategy` enumerates `agent_names()` and asserts each is in a hardcoded `bundle` or `agentic` set — a new agent must be added to the right set or this fails.
- `tests/review/test_registry.py` has hardcoded `_EXPECTED_PR` (file-trigger + always agents) and `_EXPECTED_PUSH`; a new file-trigger agent joins `_EXPECTED_PR`.
- `tests/review/test_evals.py::test_every_registered_agent_has_fixtures` needs ≥1 bad + ≥1 good fixture.

**Why:** in Plan 17 a per-task run of only `test_registry.py + test_evals.py` (59 passed) missed the `test_context_policy` classification failure; the branch-end Opus review caught it. **How to apply:** when registering an agent, run the WHOLE `tests/review/` dir, not a subset.

Second lesson, same incident: a "full gate" run as `uv run pytest -q ... | tail` reported a background exit code of 0 even though pytest had `1 failed, 737 passed` — **the pipe makes the shell exit code = `tail`'s (0), masking the pytest failure.** When you need the real result, redirect to a file and capture `$?` of pytest directly (`pytest ... > log 2>&1; echo $?`), or read the summary line, never trust an exit code from a `pytest | tail` pipeline. Related: [[release-readiness-needs-render-not-local-gate]], [[gate-cadence-framework-slices]].

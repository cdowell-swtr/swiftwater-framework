---
name: audit-prepare-snapshot-stderr-breaks-cli-runner-output
description: "audit-prepare logs per-agent \"running in snapshot mode\" to stderr; CliRunner's result.output is stdout+stderr combined, so JSON-parsing it breaks. Use result.stdout (+ --snapshot or monkeypatch _default_scorecards_root) in tests."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0576f127-c936-4be4-8ea0-a38356f39443
---

When writing/updating tests that invoke `audit-prepare`: `audit-prepare` writes one `"running in snapshot mode"` line to stderr for every agent that falls back to snapshot (no prior baseline, or `--snapshot` forced). Typer's `CliRunner` `result.output` is stdout+stderr combined — any stderr line poisons a `json.loads(result.output)` call.

**Why:** The snapshot-fallback logging was added in the audit-semantics branch (Task 4). Multiple existing tests (`test_audit_prepare_detects_framework_target`, `test_audit_prepare_explicit_target_override`, `test_audit_prepare_tolerates_pyproject_formatting_variations`, the two `test_audit_prepare_split_to_*` tests) silently kept passing in CI because their staged hash had `security` in the prior baseline → delta mode → no fallback log. The tests only started failing when `FRAMEWORK_AGENTS` was temporarily expanded to 9, exposing the latent flake. The test-quality reviewer in the gate also flagged `test_audit_prepare_explicit_target_override` as tautological for a related reason.

**How to apply:** In `test_audit_prepare_*` tests:
1. Use `result.stdout` (not `result.output`) when parsing JSON.
2. Either pass `--snapshot` (skips the per-agent fallback logging entirely) or `monkeypatch.setattr(cli_mod, "_default_scorecards_root", lambda: tmp_path)` (no baselines in tmp_path → all snapshot, but still stderr-noisy).
3. For tests asserting `--target` override behavior, monkeypatch `_detect_audit_target` so the override is observable (otherwise auto-detect coincidentally produces the same value and the test is tautological).

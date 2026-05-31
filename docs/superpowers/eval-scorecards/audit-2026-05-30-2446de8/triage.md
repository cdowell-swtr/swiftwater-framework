# Triage — framework audit 2026-05-30-2446de8

**Audit run:** see [`audit-report.md`](./audit-report.md) (raw findings) and [`meta.json`](./meta.json) (run metadata).

**Roster (6 active for `target=framework`):** application-logic, architecture, dependency, documentation, security, test-quality.

**Skipped agents (registry inactive for framework target):** accessibility, api-design, compliance, contracts, data-integrity, data-lineage, observability (and -db/-infra), performance, privacy, usability. The plan originally specified 9 agents but `audit-prepare --target framework` only allowed 6 — the registry's per-target activation rule excluded api-design, contracts, performance.

**Review surface caveat:** the audit-prepare path reuses `pr_diff()` = `git diff HEAD~1...HEAD`, so the run reviewed the just-committed audit-split-manifest commit, not the entire `src/framework_cli/` tree. The findings below are mostly self-referential to that diff. For a future broader baseline against the whole framework source, `_emit_audit_prep` would need its own diff source (e.g. `git diff <empty-tree>...HEAD` for the full tree, or a non-diff-based snapshot — out of scope here).

## Decisions

| # | Agent | Severity | File:line | Summary | Decision | Rationale | Fixed-in |
|---|---|---|---|---|---|---|---|
| 1 | review-application-logic | medium | `.claude/workflows/reviewers-audit.js:132` | Empty-items path silently returns `{results: [], meta}` instead of erroring like the old code | defer | Real concern but minor — the noop path *should* exist when `audit-prepare` validly produces zero items (e.g. unknown-agents filter that consumes the whole roster). Add a `log()` line as a future polish. | — |
| 2 | review-application-logic | low | `.claude/workflows/reviewers-audit.js:130` | `!Array.isArray(items)` guard dropped from validation | defer | The INDEX_SCHEMA already enforces array. Cheap to add as defense-in-depth in a follow-up. | — |
| 3 | review-application-logic | low | `src/framework_cli/cli.py:268` | `shutil.rmtree(split_dir)` raises if a stale FILE is at the path | defer | Real edge case but `/tmp/reviewers-audit-prep-split` is a fixed path under our control; unlikely to collide with a file in normal use. Future polish. | — |
| 4 | review-documentation | low | `src/framework_cli/cli.py:666` | `audit-prepare` command docstring doesn't mention the `--split-to` side effect | fix-now | One-line docstring update; trivially correct. | — |
| 5 | review-documentation | info | `src/framework_cli/cli.py:1052` | `_emit_audit_prep` helper has no function-level docstring describing the dual-output contract | fix-now | Same trivial doc update; pair with #4. | — |
| 6 | review-security | low | `src/framework_cli/cli.py:268` | TOCTOU between `exists()` check and `rmtree`/`mkdir` on a predictable `/tmp` path; symlink coercion risk on multi-user hosts | defer | Real on a hardened multi-user host; not a concern in the single-user dev environment where this command runs. Worth fixing in a security-hardening pass alongside #3 (tempfile.mkdtemp would solve both). | — |
| 7 | review-security | low | `src/framework_cli/cli.py:271` | `items_dir.mkdir(exist_ok=True)` uses umask before chmod 0o700 → brief world-listable window | defer | Same single-user-dev rationale as #6. Switching to `Path.mkdir(mode=0o700)` semantics or `tempfile.mkdtemp` would close it. | — |
| 8 | review-test-quality | medium | `tests/test_cli.py:549` | New split-to test doesn't assert file permissions (0o700/0o600) the production code sets | fix-now | Real — the chmods are load-bearing (per-item files carry the diff). Regression guard worth one new test. | — |
| 9 | review-test-quality | medium | `tests/test_cli.py:511` | Test only exercises fresh-dir path; idempotency-against-pre-populated case isn't covered | fix-now | Real — the `if split_dir.exists(): shutil.rmtree(split_dir)` line is unobserved. One small test addition. | — |
| 10 | review-test-quality | low | `tests/test_cli.py:540` | Test only exercises 1 agent — multi-item `f"item-{i:04d}.json"` padding for `i>=10` isn't covered | defer | Audit roster on this codebase is bounded; padding bug would surface immediately. Defer to a future "comprehensive tests" pass if ever justified. | — |

## Decision summary

| Decision | Count |
|---|---|
| fix-now | 4 |
| defer | 6 |
| false-positive | 0 |

## Fix-now items

The 4 `fix-now` items are small documentation + test polish landing in a follow-up commit on this branch (or a quick follow-up plan). They are:
- **#4 + #5** — `audit-prepare`'s command docstring + the `_emit_audit_prep` helper docstring expand to describe the `--split-to` side effect.
- **#8 + #9** — new `tests/test_cli.py` cases: assert permissions on split-manifest outputs (0o700 dirs, 0o600 files); assert idempotency against a pre-populated split dir.

## Defer items

The 6 `defer` items are noted here so they aren't lost. They form a coherent **"audit-prepare hardening" follow-up slice**: switch `/tmp/reviewers-audit-prep-split` to a `tempfile.mkdtemp`-style ephemeral path (closes the TOCTOU + umask + non-dir collision concerns at once), and add the workflow-level `Array.isArray(items)` and empty-items-`log()` guards. Total maybe ~30 lines + 3-4 tests. Defer to a small follow-up plan.

## Notes for future audits

- The `audit-prepare` review surface is `HEAD~1...HEAD` — not the whole framework. To audit the entire `src/framework_cli/` tree, `_emit_audit_prep` would need a different diff source. Worth a design question on a future plan: is "audit" meant to be diff-based or snapshot-based?
- 3 framework-relevant agents (api-design, contracts, performance) are currently inactive for `target=framework`. Worth revisiting the registry's active-agents-per-target rule — those reviewers would have legitimate things to say about CLI surface, module contracts, and subprocess timeouts.

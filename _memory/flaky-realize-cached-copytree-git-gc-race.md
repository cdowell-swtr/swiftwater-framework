---
name: flaky-realize-cached-copytree-git-gc-race
description: The flaky test_realize_cached_reuses_base_render failure is a copytree-vs-git-auto-GC race; fix is disabling auto-gc on the base repo.
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: f1b70b94-559d-4a71-b5cd-a53c1296c731
---

**Symptom:** `test_realize_cached_reuses_base_render` (and potentially other `realize_cached`/`realize_fixture` users) intermittently fails with `shutil.Error: [Errno 2] No such file or directory: …/.git/objects/<xx>` — vanished loose objects mid-copy. Hit once on PR #13's `gate` job (`pytest -q --ignore=tests/acceptance`); **transient, clears on rerun**, unrelated to whatever change is in flight.

**Cause:** `evals.realize_cached` does `shutil.copytree(base, work)` over a base project that contains a **live `.git`** dir. Git's background auto-GC can repack loose objects mid-copy, so `shutil` then fails on a path that disappeared.

**Fix (cheap, safe, standalone):** immediately after `git init` in **both** `realize_cached` and `realize_fixture`, set `git config gc.auto 0` (and `maintenance.auto false`) on the base repo so no background repack can race the copy. Not blocking; good fit to fold into Plan 23 (eval/reviewer tooling) or do as a one-off.

(Preserved 2026-06-12 from the abandoned `plan21-reviewer-rework` branch before it was deleted; master's meta-plan kept only a one-line pointer to this under Plan 23.)

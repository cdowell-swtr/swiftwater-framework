---
name: flaky-realize-cached-copytree-git-gc-race
description: The flaky realize_cached copytree failure is a loose-object-vs-GC race; FIXED durably in FWK33 by packing each cached base (gc.auto 0 alone was insufficient).
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: f1b70b94-559d-4a71-b5cd-a53c1296c731
---

**Symptom:** `realize_cached` users (`test_realize_cached_reuses_base_render`; `test_realize_cached_builds_framework_shaped_base_for_coverage_gap`) intermittently fail with `shutil.Error: [Errno 2] No such file or directory: …/.git/objects/<xx>` — vanished loose objects mid-copy. Seen on PR #13's `gate` and again on the v0.2.11 release run's `gate`; transient, clears on rerun, unrelated to the change in flight.

**Cause:** `evals.realize_cached` does `shutil.copytree(base, work)` over a base repo whose `.git` holds **loose objects** (~342 after a fresh `init`+`commit`). Git packing/pruning a loose object mid-copy makes `shutil` fail on the vanished path.

**RESOLVED — FWK33 (2026-06-16, PR #47).** The earlier guess — `git config gc.auto 0` after `git init` — was applied to `_framework_base` yet it **still raced** there, so gc.auto 0 alone is INSUFFICIENT (the loose objects are still present to race). The durable fix is to leave **no loose objects** in the copytree source: `_freeze_git_base(repo)` = `git config gc.auto 0` + `git repack -adq`, called after each cached base's commit (both the framework-shaped `_framework_base` and the rendered base in `realize_cached`). Deterministic guard `test_framework_base_is_packed_with_no_loose_objects` asserts `git count-objects` loose count == 0. If this class ever recurs, check any NEW cached-base/copytree-of-.git site calls `_freeze_git_base` (or packs) before being copied.

(Originally preserved 2026-06-12 from the abandoned `plan21-reviewer-rework` branch; updated 2026-06-16 when FWK33 shipped the durable fix.)

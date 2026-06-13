---
name: ruff-format-check-after-inline-edits
description: "After hand/polish edits to Python, run `ruff format --check` (not just `ruff check`) before committing"
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6b601497-74e6-4625-81ec-331bcfdd5d64
---

When I make inline Python edits directly (especially controller "polish" edits between subagent tasks), run `uv run ruff format --check .` on the touched files before committing — not just `uv run ruff check`.

**Why:** Over-length lines (long subprocess arg lists, long `assert ...,(msg)` lines, wrapped calls) that I write by hand pass `ruff check` but fail `ruff format --check` against the lock-pinned ruff. This is the repo's recurring "format-cleanliness regression" class. Twice in the 8f-w / Plan 9 sessions a final whole-branch review (or the implementer) had to catch + fix format drift that my own polish edits introduced; CI would otherwise fail the gate.

**How to apply:** After any inline Edit to `*.py`, run `uv run ruff format <files>` (or `--check` then fix) and re-stage before the commit. Subagent implementers already do this per task; the gap is my own between-task edits. Related: [[commit-gate-hook-timing]].

**Run it repo-wide before pushing, NOT just on the rendered project (Plan 16 / v0.1.8 relapse):** during the v0.1.8 release push the framework `ci` workflow failed on `ruff format --check .` because a SUBAGENT's added render-assertions in `tests/test_copier_runner.py` had an over-length `assert` line — `ruff check` passed, `ruff format` didn't. I'd only run `ruff format --check` on the *rendered* project (per [[release-readiness-needs-render-not-local-gate]]), not on the framework repo itself. So: before any push/release, run `uv run ruff format --check .` on the **framework repo** (subagent edits count, not only my own); the release `ci` job enforces it and a slip fails the release push.

---
name: template-audit-uv-run-project-gotcha
description: "Inside a rendered project dir, use `uv run --project \"$FW_ROOT\" framework …` — a bare `uv run framework` resolves to the rendered project's venv and fails."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: f8907a45-ce5e-4aeb-8200-b311b671859b
---

When a flow needs cwd = a rendered/generated project (so `framework audit-prepare`'s `read_batteries(Path("."))` and `--target` auto-detection see *that* project's `.copier-answers.yml` and all-batteries roster) but must run the **framework's own** CLI, a bare `uv run framework …` fails with `error: Failed to spawn: framework / No such file or directory`. Reason: `uv run` resolves the binary from the *current dir's* project venv, and a rendered project installs its own package (`demo`), not `framework-cli`.

**Fix:** `uv run --project "$FW_ROOT" framework …` — keeps cwd at the render dir while resolving the binary from the framework repo's environment.

**Where it bit:** the first real `/reviewers:template-audit` probe (2026-05-31). Steps 3 + 6 of `.claude/commands/reviewers/template-audit.md` (the two `audit-prepare` calls that run from inside `/tmp/template-audit-render`). Steps 8–9 (`audit-finalize`/`template-map`) run from `$FW_ROOT`, so they correctly use bare `uv run framework`.

**Why:** caught by actually running the slash command rather than only writing it — reinforces probing end-to-end before trusting a recipe. Related: the template-audit mechanism overall, and watch for quota throttling / silent agent drops on the full 18-agent run.

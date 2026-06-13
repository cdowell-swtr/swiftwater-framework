---
name: gate-cadence-framework-slices
description: "For subagent-driven framework/template slices, the per-commit gate over-fires 18 app-agents on review-infra/template files — use lighter per-task review + controller skip-marker commits + one branch-end full review."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 61c129b2-5eb7-4302-935f-554fa0cc0686
---

When implementing a framework feature slice subagent-driven, the pre-commit gate (`/reviewers:gate`)
fires the **full ~18-agent project roster** on most changes — confirmed for `review/context.py`,
`cli.py`, `review/findings.py`, and all **template payload** under `src/framework_cli/template/`.
A few pure-helper framework files match **0 agents** (`review/decisions.py`, `migrations.py`, test
files). Each 18-agent run costs ~600k subagent tokens, and the agents are calibrated for
*generated-project app code*, so on framework-internal review-infra they're mostly noise (though
not always — a real fail-open gap and a real duplicate-log bug were caught this way).

**Why:** the user chose this cadence explicitly (cost vs. coverage) on the decisions-log + DLQ-PII
slices: per-task verify with targeted tests + at most one focused reviewer, **defer the per-commit
gate to a single full review at branch-end** (which doubles as the mandated final whole-branch
review), and dispatch an opus whole-branch reviewer at the end.

**Updated by Plan 20b (2026-06-09):** the per-commit gate mechanism changed. `framework
gate-prepare`/`gate-finalize` are gone; the hook (`.claude/hooks/reviewers-gate-check.sh`) now
runs **`framework gate` inline**, which **degrades skip-neutral** (PASS marker, exit 0) when no
backend is configured. Since this repo ships NO `.framework/review.toml`, the per-commit hook is
skip-neutral by default — it no longer fires the 18-agent roster at all unless someone opts a
backend in. So the cadence below is now the DEFAULT (free), not a manual skip-marker dance.

**How to apply (post-20b):**
1. Implementers STAGE + verify (tests/lint) but do NOT commit ([[subagent-implementers-stop-before-commit]]).
2. Controller commits each task: `git add` the files + the CLAUDE.md Current-State update (call A),
   then `git commit` (call B). The hook self-runs `framework gate` → skip-neutral PASS → exit 0.
   No marker pre-write needed. (See [[controller-skip-marker-recipe]] for the retired manual recipe.)
3. Keep the word "commit" out of Bash commands AND descriptions ([[commit-gate-hook-timing]]).
4. Do `git add` and `git commit` in **SEPARATE Bash tool calls** — the PreToolUse hook fires before
   a Bash command runs, so a chained `git add && git commit` is blocked pre-execution and the add
   never runs.
5. Branch-end: run the real full review (the mandated whole-branch Opus review) before merge — that
   is where the actual agent coverage happens, by design.

To DELIBERATELY run the real per-commit gate (rare), `framework review-config set-backend subagent`
writes `.framework/review.toml` so the hook dispatches affected-only reviews; clear it to return to
skip-neutral. `.framework/audit/marker.json` is gitignored.

**`!` does NOT bypass the hook:** a user-typed `! git commit` still triggers the PreToolUse gate
hook. With no backend configured it passes skip-neutral anyway, so the normal commit path is fine.

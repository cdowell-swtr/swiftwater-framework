---
name: subagent-implementers-stop-before-commit
description: "In subagent-driven-development here, implementer subagents stage + pass the commit-gate but don't fire the final git commit; controller must verify and finish it."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 49f13a1d-7e1e-4c24-8e52-b50a128128c4
---

During subagent-driven-development (worker-tracing slice, 2026-05-31), all 3 implementer subagents (general-purpose, sonnet) reliably did the work — edited files, ran the TDD red→green, staged everything, and triggered the `CLAUDE.md` commit-gate hook (which printed "Gate PASS — marker written. Commit can proceed.") — but then **did not actually run the final `git commit`**, and their reports came back truncated to just that gate line. HEAD stayed at the prior commit with everything staged.

**Why it matters:** if the controller trusts the terse report and moves on, the task looks done but isn't committed; the next task's commit then sweeps up the prior task's staged changes, muddying history.

**Root cause (clarified 2026-05-31, DS-tracing slice):** the **`/reviewers:gate` PreToolUse hook** on `git commit` dispatches the affected review agents via the **`Workflow` tool — which is NOT available in a subagent session** (only the main/controller session has it). So when the staged set triggers affected agents, the subagent's `git commit` is **blocked** and it cannot satisfy the gate (it correctly refuses to bypass with `--no-verify` or to use the paid API). When no agents are affected the gate auto-passes ("Gate PASS — marker written") but the subagent often still doesn't fire the final `git commit`. Either way the result is staged-but-uncommitted.

**How to apply:** after each implementer subagent returns, **independently verify** with `git log --oneline -1` + `git status --short`. If staged-but-uncommitted, confirm the work (diff review + run the task's tests yourself) and **commit from the controller/main session** — it has `Workflow`, so the reviewers-gate hook passes and the commit lands. Re-dispatching a subagent just to commit is wasteful and will hit the same wall. Cross-ref [[commit-gate-hook-timing]] (stage `CLAUDE.md` separately; keep "commit" out of Bash descriptions).

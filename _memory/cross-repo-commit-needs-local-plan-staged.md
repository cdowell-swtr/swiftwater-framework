---
name: cross-repo-commit-needs-local-plan-staged
description: "The commit-gate PreToolUse hook checks whether PLAN.md/ACTION_LOG.md is staged in the SESSION cwd's repo, and fires BEFORE the bash command runs (before any `cd`). So committing to a DIFFERENT repo from a framework session needs a framework PLAN.md/ACTION_LOG.md change staged first."
scope: project
metadata:
  type: project
---

The framework's commit-gate is a `PreToolUse` (Bash) hook in `.claude/settings.json`. It blocks `git commit` unless `PLAN.md` or `ACTION_LOG.md` is staged. Two non-obvious properties bite when you commit to a **different** repo from within a framework session (e.g. appending the framework's row to a sibling tool's implementer registry):

1. **It resolves the repo from the session's cwd, not the commit target.** The hook runs `root=$(git rev-parse --show-toplevel)` and checks `git -C "$root" diff --cached`. Because a `PreToolUse` hook fires **before** the bash command executes, a command like `cd ~/other-repo && git commit …` is evaluated with cwd still at the framework — so the hook inspects the **framework's** staged set, not the other repo's.
2. **It re-reads `settings.json` per invocation** (no session reload needed) — so a hook edit takes effect immediately, but also means you can't dodge it by editing settings mid-session.

**Consequence / recipe:** before running a cross-repo `git commit` from a framework session, stage a framework `PLAN.md`/`ACTION_LOG.md` change in *this* repo (e.g. an `ACTION_LOG` note entry recording the cross-repo action). Then the gate passes, and the cross-repo `git commit` only commits the other repo's staged files. This came up registering the framework in the sibling PI and Committed-Memory registries (Plans 25 and 26).

Related: stage `git add` and `git commit` as SEPARATE tool calls — chaining `git add … && git commit` fails because the gate evaluates before the add runs ([[commit-gate-hook-timing]]); and the gate regex false-matches any command where `git` and `commit` co-occur as substrings ([[commit-gate-hook-false-matches-git-commit-substring]]).

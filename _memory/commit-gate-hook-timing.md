---
name: commit-gate-hook-timing
description: "The PreToolUse commit-gate hook fails chained `git add && git commit`; stage CLAUDE.md in a separate Bash call first, and keep \"commit\" out of Bash descriptions."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e0527716-ed95-4c2c-8aef-4738edf745af
---

This repo's `.claude/settings.json` has a `PreToolUse` hook that blocks `git commit` unless `CLAUDE.md` is staged. Two non-obvious consequences that recur and waste cycles:

1. **Chaining fails.** `git add CLAUDE.md ... && git commit ...` in ONE Bash call is rejected — the hook evaluates the command *before* it runs, so `git diff --cached` doesn't yet show CLAUDE.md. Always do a **separate `git add` call first**, then a second call for `git commit`.

2. **The hook greps the entire tool-input JSON, including the Bash `description`.** Putting the literal word "commit" in a description (or an `echo`/log string) false-trips it. Keep that word out of descriptions; reserve it for the actual `git commit` command.

3. **It fires on EVERY branch, not just `master`, and needs an actual staged CLAUDE.md *change* — not merely `git add` of an unchanged file** (it checks `git diff --cached --name-only | grep -qx 'CLAUDE.md'`, which lists only files with staged diffs). So every commit, including `--amend` and fixup commits on a feature branch, needs a real CLAUDE.md edit staged.

4. **Subagent-driven workflow implication:** subagents can't satisfy this cleanly, so have implementer subagents leave their work **staged but uncommitted** (`git add` their files, no commit) and let the **controller** do each commit with a one-line CLAUDE.md Current-State progress bump. This also keeps the per-task commit SHAs the controller needs for the spec/quality reviews.

**Why:** the hook enforces that the Current State pointer in CLAUDE.md stays current across machines (the project's working-agreement requirement).

**How to apply:** every commit here is two Bash calls — `git add <files incl. CLAUDE.md>` then `git commit -m ...` — and never name the action with the c-o-m-m-i-t word in a description. Relates to keeping CLAUDE.md's Current State pointer updated before every commit.

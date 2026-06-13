---
name: verify-master-content-after-pr-merge
description: "A PR merge can silently land an EARLIER commit's content, not the branch tip — always verify master actually contains the expected content after a merge; prefer single-commit/squash PRs."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 1db7758b-781f-48fb-8307-2870e1d8f397
---

**Incident (2026-06-12):** PR #15 (`meta-plan-future-directions`, 3 commits: `d9fc144` record → `2d305ce` add Plan 27 → `98ff3a9` reconcile) was merged via `gh pr merge 15 --auto --merge`. The resulting merge commit `cdb9043` had parents `de51f0e` + **`d9fc144`** — it merged the **first** commit, silently dropping `2d305ce` and `98ff3a9`. master landed without the Plan-27 / consumer-model reconciliation. Caught only by a paranoid pre-`/clear` `grep` of the files on disk (the dropped commits were still in the object store, so it was recoverable: new branch → `git checkout <lost-sha> -- <files>` → PR #16 → merge → **verify**).

Exact GitHub mechanism uncertain (possibly an `--auto` race against a stale head / required-check-context state on a multi-commit PR). Don't rely on knowing the cause — rely on the rule.

**How to apply:**
- **After ANY PR merge, verify master has the expected content** — `git checkout master && git pull`, then `grep` for a marker string from the change and/or check `git log --format='%h parents:%p' -1` to confirm the merge's PR-side parent is the branch **tip**, not an earlier commit. Never assume the merge took the tip.
- **Prefer single-commit (or squash) PRs** — a one-commit PR structurally removes the "which commit got merged" ambiguity. The recovery PR #16 deliberately used a single commit.
- This matters more under branch protection, where you can't just `git push` a correction to master ([[master-branch-protection-ruleset]]); a wrong merge needs another PR + full CI to fix.

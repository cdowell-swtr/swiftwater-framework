---
name: master-branch-protection-ruleset
description: "master is protected by a GitHub ruleset (id 17579429): PR required (0 approvals), required checks gate+build+render-complete, no force-push/delete, admins enforced. Push to master is blocked — branch + PR."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 1db7758b-781f-48fb-8307-2870e1d8f397
---

Set up 2026-06-11 (PRs #11/#12 + ruleset). The repo owner had a habit of merging/pushing directly to `master`, which caused conflicts; this enforces the PR flow.

**The ruleset** (`gh api repos/cdowell-swtr/swiftwater-framework/rulesets/17579429`): targets `refs/heads/master`, `enforcement: active`, `bypass_actors: []`. Rules: `pull_request` (required_approving_review_count **0** — solo dev, so requiring 1 would self-block, and the branch-end Opus review isn't a GitHub approval anyway); `required_status_checks` (strict/up-to-date) requiring **`gate`** (ci.yml — lint/mypy/pytest/build), **`build`** (docs.yml — MkDocs site), **`render-complete`** (render-matrix.yml); `non_fast_forward` (no force-push); `deletion` (no branch delete).

**Why `render-complete` exists:** render-matrix's per-combo job names (`render (mongodb+pgvector, …)`) are dynamic (seed/strategy), so they can't be named as required checks. `render-complete` (`needs: [generate-matrix, render]`, `if: always()`) is a stable umbrella that passes only when the whole matrix succeeded — that single context is what's required.

**Why review agents are NOT required:** there are no `ANTHROPIC_*` keys in gh secrets (to avoid paying), so the review-agent jobs run **skip-neutral** in CI — requiring `review-aggregate` would be meaningless now and a latent block if keys were ever added. Kept advisory.

**Gotcha — a CONFLICTING PR never runs the required checks (learned on PR #13, the first protected PR):** `gate`/`build`/`render-complete` fire on the `pull_request` **merge ref**, which GitHub can't build while the PR conflicts — so only push-triggered jobs (e.g. `agent-evals`'s `eval`) appear and the required checks are simply *absent*, leaving the PR doubly-stuck (conflict + missing-required-checks). This bites any PR branched off an older `master` (the strict/up-to-date policy). Fix = **update the branch with `master`** (resolve the conflict — usually only `CLAUDE.md` + the meta-plan state pointers collide); once it merges cleanly the merge ref builds and the required checks start. So if a PR's required checks look "missing," check `gh pr view <n> --json mergeable,mergeStateStatus` *first*. After a conflict reconciliation, verify it didn't drop a side of the state docs (grep the branch's `CLAUDE.md`/meta-plan for the newest master content).

**How to apply day-to-day:** never `git push` to `master` — always branch → PR → merge once `gate`/`build`/`render-complete` are green (and the branch is up to date). The owner can self-merge (0 approvals). **Emergency bypass:** `gh api -X PUT repos/.../rulesets/17579429` to flip `enforcement` to `disabled` (or `DELETE` it), then re-enable. **Releases are unaffected** — tag pushes aren't covered by a *branch* ruleset, so `release.yml` still fires on `vX.Y.Z` tags ([[release-cut-procedure]]). Related: [[commit-gate-hook-timing]].

---
name: controller-skip-marker-recipe
description: "As of Plan 20b the commit-gate hook self-runs `framework gate` (skip-neutral when no backend) — no manual marker write needed. Just git add (incl. CLAUDE.md) then git commit as SEPARATE Bash calls. The old gate-prepare skip-marker dance is retired."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: c9002363-27bb-4f03-b690-5224c0833806
---

**Updated by Plan 20b (2026-06-09):** the old skip-marker recipe is RETIRED. `framework
gate-prepare`/`gate-finalize` no longer exist; the PreToolUse hook
`.claude/hooks/reviewers-gate-check.sh` now runs **`framework gate` inline** on every
`git commit`. `framework gate` resolves a backend and **degrades skip-neutral** (writes a
PASS marker, exit 0) when none is configured — and this repo has no `.framework/review.toml`,
so commits pass trivially without any marker pre-write. The hook blocks (exit 2) only on a
real FAIL verdict (which requires an opted-in backend).

Two PreToolUse hooks still gate every `git commit`: (1) a `CLAUDE.md`-must-be-staged check,
and (2) the rewired gate hook above.

**The new recipe (much simpler):**
```bash
# call A: stage everything INCLUDING the CLAUDE.md Current-State update
git add <files> CLAUDE.md
# call B (SEPARATE Bash call): commit — the hook self-runs `framework gate` skip-neutral → exit 0
git commit -m "..."
```

**Still-valid sequencing traps (unchanged):**
1. **Never chain `git add ... && git commit` in one Bash call** — the PreToolUse hook matches
   the whole command on the `git commit` substring and blocks it *before execution*, so the
   `git add` never runs. add = call A, commit = call B. (See [[commit-gate-hook-timing]].)
2. Keep the word "commit" out of Bash command descriptions too.
3. `CLAUDE.md` must be in the staged set or the first hook blocks — always `git add CLAUDE.md`.

If a backend ever IS configured in this repo (`framework review-config set-backend …` writes
`.framework/review.toml`), the hook will actually RUN affected-only reviews per commit — for the
[[gate-cadence-framework-slices]] cadence (defer to one branch-end review) keep the repo with NO
review.toml so the hook stays skip-neutral. `.framework/audit/marker.json` is gitignored.

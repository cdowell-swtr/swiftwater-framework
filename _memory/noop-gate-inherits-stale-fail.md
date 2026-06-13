---
name: noop-gate-inherits-stale-fail
description: "After a FAILED real /reviewers:gate run, a later noop-mode gate-finalize inherits the stale FAIL — clear .framework/audit/latest/findings/ first."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: 61c129b2-5eb7-4302-935f-554fa0cc0686
---

`framework gate-finalize` in **noop mode** (no review-relevant files staged) deliberately does
NOT clear `.framework/audit/latest/findings/` (that's reserved so the regrade-against-prior-findings
workflow keeps working). So if the *previous* real gate run FAILED and left per-agent
`findings/*.json` there, a subsequent noop finalize re-reads those stale records and writes
**verdict=FAIL** even though the current (noop) staged set has nothing to review.

**Symptom:** you stage a docs/test-only change, gate-prepare says `mode: noop`, but
`gate-finalize` returns `verdict=FAIL` (with the old run's summary, e.g. `compliance:5; data-integrity:3`).

**Fix:** `rm -rf .framework/audit/latest/findings` before finalizing the noop gate, then re-run
`gate-finalize` → PASS. (`.framework/audit/` is gitignored, so this is safe.)

Context: the real-gate path clears stale records itself; only noop/regrade leave them. See the
"Gate design quirks" note in CLAUDE.md Known follow-ups and [[flags-is-dual-use-gate-skips-advisory]].

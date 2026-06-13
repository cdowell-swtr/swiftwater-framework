---
name: paid-path-operative-for-builders
description: "UPDATED post-Plan-20 (merged 2026-06-10): free and paid are now ONE engine with a swappable backend, so there's no separate 'cheat path' to distrust. Paid-vs-free divergence is now only model-judgment/calibration variance (Plan 21), not path divergence. The paid api path is still what ships in CI."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a21de392-d362-4517-b988-848d9a8e4434
---

**UPDATED — Plan 20 merged 2026-06-10.** The free/paid SPLIT this memory warned about is GONE:
`framework review`/`eval`/`audit`/`gate` now run ONE in-process engine with a swappable
`messages.create`-shaped backend — `--backend api` (paid SDK) ↔ `--backend subagent` (free
`claude -p`). The free backend is no longer "separate code with stronger guards"; it's the SAME
path, so a free-backend result now DOES predict the paid one structurally (a parity smoke confirmed
both single-turn, no error, same path). What remains is ordinary model-judgment variance on
borderline low/info findings — that's [[reviewer-tuning-is-prompts-not-thresholds]] / Plan 21, not a
path defect. The paid api path is still what ships (CI `review.yml`/`agent-evals.yml` pass
`--backend api`; cost-safe default-None means no spend without explicit `--backend`/env/config).
The original framing is kept below as history.

---

The free subscription-subagent path (the retired `/reviewers:gate`, `/reviewers:audit`,
`/reviewers:tune`, Slice E) WAS a **cost-saving cheat for OUR development** — it
ran reviewers on Claude Code subagents instead of the paid API. **Builders do
not have that.** A builder's `framework review` runs the **paid** `run_agent` /
`run_agent_agentic` path: locally with their own key, or in CI via the shipped
`review.yml` + `ANTHROPIC_FRAMEWORK_CI_RUNTIME`. The paid eval (`agent-evals.yml`)
exercises that same path.

**Why it matters:** the paid (local) and paid (CI) paths are the **operative**
reviewer experience for builders. Do NOT call the free path "operative" or treat
the free-subagent `/reviewers:tune` calibration as the source of truth for what
builders get. When the paid path diverges from the free-path calibration (e.g.
the Plan-18 anchor: 8/20 agents failed their locally-tuned thresholds on the
paid run, with ~7 agents over-flagging their GOOD fixtures fp 1.00), that is
**builders receiving false positives on clean code** — a product-quality defect,
not informational noise.

**How to apply:** weigh paid-path divergence as a real defect — though *which* defect
varies (the diagnosis matters): some divergence is real bugs the free path's weaker/guarded
behaviour missed (e.g. a truncated fixture, [[eval-fixture-patch-truncation]]), some is
genuine agent over-strictness/inconsistency in the PROMPTS
([[reviewer-tuning-is-prompts-not-thresholds]]), and the root enabler is that the two paths
are separate code ([[reviewer-dev-prod-parity-gap]]). The free path's only role is cheap
dev iteration; prompts/fixtures/thresholds must hold on the PAID path because that's what
ships. Related: [[reviewer-subagent-dispatch-model]].

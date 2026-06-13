---
name: reviewer-dev-prod-parity-gap
description: "RESOLVED by Plan 20 (20a+20b merged to master 2026-06-10): the free and paid review paths are now ONE in-process engine with a swappable messages.create-shaped backend (api ↔ claude -p). Dev = prod by construction. Kept as history of WHY the collapse happened."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: a21de392-d362-4517-b988-848d9a8e4434
---

**✅ RESOLVED — Plan 20 merged to master 2026-06-10 (20a backend seam + 20b in-process collapse).**
There is now ONE review code path: `framework review`/`eval`/`audit`/`gate` all run the same
`run_agent`/`run_agent_agentic` loop via the in-process engine, and the ONLY swappable piece is the
`messages.create`-shaped backend — `ApiBackend` (paid SDK) ↔ `SubagentBackend` (free `claude -p`).
The old `/reviewers:*` Workflow-JS/slash/split-manifest dispatch is fully deleted. A paid-vs-free
parity smoke (security agent, same diff) confirmed both backends run the identical path single-turn
with no error; the only divergence is sub-threshold low/info model-judgment variance (now Plan 21's
prompt/threshold calibration, not a path bug). **Dev = prod by construction; every fix lands once.**
The forced-StructuredOutput guard that used to mask prod crashes is gone. Below is the original
gap description, kept as history of why the collapse was necessary.

---

The review system HAD **two divergent code paths** that were supposed to be equivalent:

- **Paid path** (what builders run): `framework review` / `framework eval` →
  `run_agent` / `run_agent_agentic` (`src/framework_cli/review/runner.py`, `agentic.py`)
  → real Anthropic client → **raw model text** → `parse_findings`.
- **Free path** (our dev cost-cheat): `/reviewers:tune` / `:audit` / `:gate` → a
  **different dispatch** (CC subagents via the Workflow tool's `agent()`) with a
  **forced StructuredOutput schema** (always-well-formed JSON).

They run the **same models** — so capability is NOT the difference. The difference is
**scaffolding, running the wrong way**: the dev path is *more constrained/robust* than
production, so it **masks the bugs builders hit**. Proven in the Plan 18 paid anchor
(2026-06-09): the paid path crashed twice on malformed model output the free path can
never produce (the forced JSON guard hid it); a full week of free-path threshold
calibration did **not** predict the paid run (8/20 agents failed their free-tuned
thresholds).

**Implication / fix (Plan 20):** collapse to **one** review code path where the only
swappable piece is the model-call backend (paid client ↔ a subagent-backed client
implementing the same `messages.create`). Then dev = prod by construction and every fix
lands once. Until then: never trust a free-path result as predicting production; the
paid path is the operative one ([[paid-path-operative-for-builders]]). Related:
[[reviewer-tuning-is-prompts-not-thresholds]].

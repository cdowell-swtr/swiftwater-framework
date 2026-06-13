---
name: reviewer-tuning-is-prompts-not-thresholds
description: "The real reviewer-tuning lever is the agent PROMPTS (agents/*.md), not thresholds.yaml. Thresholds are a downstream scalar knob; tuning them to make a prompt's output \"pass\" treats the symptom."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a21de392-d362-4517-b988-848d9a8e4434
---

When a reviewer over-flags, under-finds, grades severity wrong, or contradicts itself,
the fix lives in its **prompt** (`src/framework_cli/review/agents/<name>.md`) — and in its
`block_threshold` — **not** in `tests/eval/fixtures/thresholds.yaml`.

`thresholds.yaml` (recall_min / fp_max per agent) is a downstream pass/fail knob. Every
"calibration" through the entire framework build moved *thresholds* while the prompts —
which define what each agent looks for, how it grades severity, and whether it's
internally consistent — **sat relatively uninspected**. Tweaking a threshold so a prompt's
output "passes" is treating the symptom.

**Why it matters / how to apply:** the reviewers are **ours** — their behaviour is entirely
in our prompts, not an external standard to work around with thresholds. Evidence
(Plan 18 paid run): `data-integrity` grades a correct bulk insert HIGH for missing
validation while ignoring the identical `create_item` in the same file — a prompt-level
**consistency bug** no threshold can fix. So: tune prompts first (consistency, severity
calibration, scope discipline, hallucination resistance, re-derive `block_threshold`),
then re-derive thresholds last — and only on a path that matches production
([[reviewer-dev-prod-parity-gap]]). This is the substance of Plan 21.

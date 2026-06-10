# Phase 0c — baseline anchor (2026-06-10)

Full eval sweep on the **parity'd path**: free `claude -p` subagent backend, `--repeat 3`,
reviewers at their production models (Sonnet for bundle/diff agents, `claude-opus-4-8` for the
7 agentic), against the now-correct + representativeness-validated fixtures (Phases 0a+0b).
159 calls, **$0 actual** (subscription; the scorecard's $74.30 is the notional paid-equivalent).
Full scores: `scorecard.md`; per-call findings: `findings/`.

This is the trustworthy anchor that feeds the Phase 1 audit. Thresholds were **not** re-derived
here — they are re-derived last (Phase 3), after the prompts are fixed.

## Scores vs. the (stale, pre-collapse) thresholds — 9 PASS / 11 FAIL

| Agent | Recall | FP | Status | Read |
|---|---|---|---|---|
| accessibility | 1.00 | 0.00 | PASS | |
| api-design | 1.00 | 0.00 | PASS | |
| application-logic | 1.00 | 0.00 | PASS | |
| architecture | 1.00 | 0.00 | PASS | |
| **compliance** | 1.00 | **1.00** | FAIL | over-flags its good fixture |
| **contracts** | **0.50** | 0.00 | FAIL | under-finds (known weak agent) |
| **data-integrity** | 1.00 | **1.00** | FAIL | over-flags good (matches Plan 18) |
| **data-lineage** | **0.17** | 0.00 | FAIL | badly under-finds |
| dependency | 1.00 | 1.00 | PASS | advisory (fp allowed) |
| documentation | 1.00 | 1.00 | PASS | advisory (fp allowed) |
| **env-parity** | 1.00 | **0.67** | FAIL | over-flags good |
| **observability** | 1.00 | **0.83** | FAIL | over-flags (auto-instrumentation premise) |
| **observability-db** | **0.00** | 0.00 | FAIL | ⚠ degenerate fixture — recall unreliable (Phase 1) |
| **observability-fe** | **0.67** | 0.33 | FAIL | under-finds + over-flags (1 parse failure) |
| observability-infra | 1.00 | 0.33 | PASS | |
| performance | 1.00 | 0.00 | PASS | |
| privacy | 1.00 | 0.00 | PASS | |
| **security** | 1.00 | **0.33** | FAIL | over-flags good |
| **test-quality** | 1.00 | **0.33** | FAIL | over-flags good |
| **usability** | 1.00 | **0.33** | FAIL | over-flags good (1 parse failure) |

## Dominant pattern: over-flagging clean code (fp), exactly the Plan 18 thesis

8 of the 11 failures are **good-fixture over-flagging** (compliance, data-integrity, env-parity,
observability, observability-fe, security, test-quality, usability). 4 are **under-finding**
(contracts, data-lineage, observability-db, observability-fe). This reproduces the Plan 18 paid
over-flagging on the *free* backend — dev = prod (Plan 20) — and confirms the work is in the
**prompts** (Phase 1), not thresholds.

## Caveats to carry into Phase 1

1. **`observability-db` recall 0.00 is an artifact**, not an agent failure: its good fixture
   (re-authored to be representative) is byte-identical to its bad fixture, and the "bad" defect
   isn't a real defect under auto-instrumentation. The whole `observability*` prompt+bad-fixture
   set needs redesign — see [[observability-reviewers-assume-manual-instrumentation]] /
   `PHASE0B-FINDINGS.md`.
2. **Two parse failures** ("no JSON array found in agent response", scored as no findings):
   `observability-fe` good/capped-label r1 and `usability` good/delete-with-confirm r0. These
   may distort those two agents' numbers; Phase 1 should re-check parse robustness on the
   subagent backend (related to the existing parse-hardening work).
3. Thresholds here are the **stale 2026-06-03 values** (pre-collapse). PASS/FAIL is only a
   relative signal of where the prompts diverge; real thresholds come in Phase 3.

## Infra notes from this sweep

- `framework eval` has **no built-in resume** — a self-healing per-agent driver
  (skip-if-complete, append) was used. The Plan-20b checkpoint/resume is for the audit
  `run_engine`, not `eval`.
- **Backend exhaustion bug:** the `claude -p` 429 message *"hit your session limit"* is not in
  `backend.py::_EXHAUSTION_MARKERS`, so it crashed with `RuntimeError` instead of degrading via
  `BackendExhausted`. Fix before Phase 1's larger burn.

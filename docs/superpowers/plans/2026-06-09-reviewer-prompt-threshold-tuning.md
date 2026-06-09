# Plan 21 — Reviewer prompt + threshold re-tuning + fixture quality (STUB — pre-brainstorm)

**Date:** 2026-06-09
**Status:** ⬜ Not started — stub capturing the rationale. **Depends on Plan 20** (parity).
Brainstorm + spec before implementing.

> Rationale-bearing stub, written before the producing context is cleared. The design
> comes from a fresh brainstorm. **Do not start before Plan 20 lands** — tuning against a
> non-representative path is what wasted the Plan 18 week.

## The realisations this plan acts on

1. **Tuning lives in the prompts, not the thresholds.** Every "calibration" to date moved
   `tests/eval/fixtures/thresholds.yaml` — a downstream scalar knob (recall_min/fp_max).
   The reviewers' actual behaviour — what they look for, how they grade severity, whether
   they are internally consistent — lives in `src/framework_cli/review/agents/*.md`, which
   has sat **relatively uninspected through the entire build**. Threshold tweaks to make a
   prompt's output "pass" treat the symptom. → `[[reviewer-tuning-is-prompts-not-thresholds]]`.
2. **The reviewers are ours, not a third-party bar.** When an agent over-flags or
   contradicts itself, that is a bug *we wrote into the prompt*, fixable by us — not an
   external standard to work around with thresholds.

## Evidence of prompt-level defects (Plan 18 paid run, 2026-06-09)

Diagnosed on the **paid** path (the operative one for builders). At repeat=1 these are
single rolls, but the *kind* of finding is the signal:

- **`data-integrity` (block_threshold = `info`, so any finding blocks):** flags a
  *correct, complete* bulk insert at HIGH for missing input validation/dedup — while
  ignoring the identical `create_item` right above it in the same file. **Inconsistent
  with the codebase's own conventions.** Its successive findings ("no dedup" → then,
  after dedup added, "dedup silently drops duplicates") both point at one real gap — an
  **underspecified duplicate-handling contract** — i.e. the *fixture* was underspecified;
  but the agent grading a reasonable bulk insert as HIGH-blocking is over-strict for what
  should block a builder. (NB: earlier in-session this was mischaracterised as "no impl
  can pass" / "mutually incompatible findings" — that was wrong; it is one consistent gap.)
- **`observability`:** mixes genuine gaps (missing `correlation_id` in a success log; a
  span not marked errored on exception) with arguably over-reaching asks (per-endpoint
  SLO for every new route). Severity/scope calibration needs review.
- **Several agents over-flag their *good* fixtures** on the paid path (fp 1.00 where the
  free path reported 0.00): `compliance`, `data-integrity`, `env-parity`, `observability`,
  `observability-infra`. Some of this is real fixture bugs (below); some is prompt
  strictness. Both must be separated case by case.

## Scope (to brainstorm)

1. **Open and audit every agent prompt** (`agents/*.md`): consistency (don't hold new code
   to a stricter bar than the surrounding codebase), severity calibration (what *should*
   block a builder vs. advise), scope discipline (no creep into other agents' domains),
   and hallucination resistance. **Re-derive `block_threshold` per agent** as part of this
   (e.g. `data-integrity` at `info` is almost certainly wrong).
2. **Fix the eval fixtures' quality**, which the paid path exposed:
   - **Malformed-patch / truncation class** — `change.patch` hunk-header line counts that
     are wrong, so `git apply` silently truncates the realised code (`data-integrity`
     fixed in this session by render→edit→`git diff` regeneration; **audit ALL fixtures**
     the same way). → `[[eval-fixture-patch-truncation]]`.
   - Add a **`test_fixtures_are_wellformed` guard that realises each fixture and asserts the
     patch applies *without truncation*** (the diff round-trips), so this class can never
     recur silently.
   - Good fixtures that aren't genuinely clean (the `performance`/`test-quality` class from
     `e365a29`, plus the paid-run fp set) → make them real clean examples.
3. **Re-derive thresholds** only *after* the prompts are right, on the parity'd path
   (Plan 20) — cheaply on the free backend, confirmed on paid sparingly.

## Carried-over provisional state to revisit

- The 4 threshold edits in `e365a29` (`dependency`/`documentation` fp_max→1.00,
  `data-lineage`/`observability-db` recall_min→0.73) were symptom-level tuning against the
  unrepresentative free path — **re-derive them here**, don't trust them.
- The `data-integrity/good/atomic-bulk-insert` fixture (robust regeneration, this session)
  stands as a better example but its dedup contract is still underspecified — revisit when
  tuning that agent's prompt.

## Decision still open (brainstorm)

- Order: prompts first, then fixtures, then thresholds? Or interleave per agent?
- How to measure prompt consistency objectively (e.g. assert an agent does not flag a new
  function for a pattern the baseline template already exhibits).
- Whether `block_threshold` should be reviewed globally (several agents may be miscalibrated).

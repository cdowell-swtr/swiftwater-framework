# Plan 21 — Reviewer prompt + threshold re-tuning + fixture quality — Design

**Date:** 2026-06-10
**Status:** Design (brainstormed). Supersedes the pre-brainstorm stub at
`docs/superpowers/plans/2026-06-09-reviewer-prompt-threshold-tuning.md`.
**Depends on:** Plan 20 (reviewer path parity — collapsed engine, merged `e6f6535`).

## Problem

The Plan 18 paid eval anchor (2026-06-09) showed the review agents **over-flag good
fixtures and apply an inconsistent severity bar** — e.g. `data-integrity` grades a correct,
complete bulk insert HIGH for missing validation while ignoring the identical `create_item`
right above it in the same file. The realisations that frame this plan:

1. **Tuning lives in the prompts, not the thresholds.** Every calibration to date moved
   `tests/eval/fixtures/thresholds.yaml`, a downstream scalar knob. The reviewers' actual
   behaviour lives in `src/framework_cli/review/agents/*.md` — which has sat relatively
   uninspected through the entire build. → `[[reviewer-tuning-is-prompts-not-thresholds]]`.
2. **The reviewers are ours, not a third-party bar.** Over-flagging / self-contradiction is a
   bug *we wrote into the prompt*, fixable by us — not an external standard to threshold around.
3. **The prompts each invent their own severity rule.** Most are 1–4 sentences carrying an
   ad-hoc "X is at least HIGH" with no shared definition of what HIGH/MED/LOW/INFO mean or
   what should *block a builder* vs. *advise*. That inconsistency is the defect.

**The Plan 20 unlock:** dev = prod is now true by construction (one engine, swappable
backend). The free `claude -p` backend no longer has the stronger guardrails that *masked*
the paid over-flagging, so those defects now **reproduce cheaply on the free backend** — we no
longer need paid runs to see them. This plan exploits that to tune cheaply, confirming on paid
only sparingly.

## Goals

- Audit and rewrite every agent prompt against **one shared severity + scope rubric** so the
  bar is consistent across agents, scope-disciplined, hallucination-resistant, and never
  stricter than the surrounding codebase already meets.
- Re-derive `block_threshold` per agent (several are likely miscalibrated;
  `data-integrity` at `info` almost certainly moves).
- Fix the **eval fixture quality** the paid path exposed: the malformed-patch/truncation
  class, plus `good` fixtures that aren't genuinely clean — and add a permanent guard so the
  truncation class can never recur silently.
- Re-derive `thresholds.yaml` **last**, on the parity'd path, with margin; commit a dated
  scorecard.

## Non-goals

- No new bespoke "consistency" test class — the **good fixtures themselves are the consistency
  oracle** (a genuinely-clean good fixture exhibits the codebase's own patterns; asserting its
  fp stays low *is* the "not stricter than the codebase" check).
- No blanket fixture expansion — fixture growth is **data-driven** (only where the baseline
  shows borderline precision).
- No change to the review engine / backend seam (Plan 20 territory).

## The shared rubric (the one new artifact)

A common preamble every agent prompt inherits, defining:

- **Severity semantics, consistent across agents:** what HIGH / MEDIUM / LOW / INFO mean, and
  the dividing line between **what should block a builder** vs. **advise**.
- **The codebase-bar principle:** do not hold new code to a stricter standard than the
  surrounding codebase already meets (the `create_item`/bulk-insert lesson).
- **Internal consistency within a single review:** apply one standard to all instances of a
  pattern in the same review pass — if you don't flag instance A, don't flag an identical
  instance B. (The other half of the `create_item`/bulk-insert defect: the agent graded a bulk
  insert HIGH while leaving the identical `create_item` above it unflagged — an
  internal-consistency failure, not only a stricter-than-codebase one.)
- **Domain boundary per agent:** an explicit statement of what this agent owns, so scope-creep
  into another agent's domain is checkable.

Making every prompt conform to this single rubric is what turns "agent #3's HIGH == agent
#14's HIGH" from aspiration into something enforceable.

## Phases

All LLM-bearing work is **checkpoint/resumable across quota resets** (this burns subscription
quota fast). The deterministic work is front-loaded so no quota is spent until the fixtures are
sound.

### Phase 0a — Fixture infrastructure (deterministic, zero quota)

- Add `test_fixtures_are_wellformed`: realise every committed fixture and assert the diff
  round-trips **without `git apply` truncation** (the realised code == the intended code). A
  permanent regression guard for the truncation class. → `[[eval-fixture-patch-truncation]]`.
- Audit every fixture against the guard and fix each malformed `change.patch`
  (render → edit → `git diff` regeneration).

**Ordering rationale:** fixtures must be correct *before* the baseline sweep. A truncated
fixture realises to broken code; the agent correctly flags the mangled result, which reads as a
false positive but is a fixture bug. Anchoring the audit on findings from broken fixtures would
teach the audit agents to "fix" prompts against garbage.

### Phase 0b — Good-fixture representativeness validation (quota, focused Opus)

The consistency oracle (Non-goals) rests on an assumption that has **never been validated**:
that each `good` fixture exhibits the *codebase's own patterns* rather than arbitrary clean
code. If a good fixture is unrepresentative, asserting its fp stays low proves nothing about
"not stricter than the codebase," and a baseline anchored on it is suspect.

A focused agentic pass (Opus, read/grep the template) checks each `good` fixture: does its
realised code mirror patterns the template actually uses, or is it arbitrary clean code? Flag
and fix the unrepresentative ones (re-author to exhibit a genuine codebase pattern) **before**
the anchor. This sits between the truncation fix (0a) and the baseline (0c) so the anchor rests
on fixtures confirmed both *correct* and *representative*.

### Phase 0c — Empirical baseline anchor (quota)

- Run `framework eval` across all agents on the **free subagent backend**, `--repeat 3
  --findings-out`, on the now-correct, representativeness-validated fixtures. Reviewers-under-
  test run on their **production models** (the 7 agentic agents on `opus-4-8`) — never a
  cheaper stand-in, or we repeat the Plan-18 parity mistake at the model level.
- The committed `thresholds.yaml` is **stale** (calibrated 2026-06-03 on the pre-collapse
  path); these fresh findings, with their `--repeat 3` variance, are the trustworthy anchor fed
  to Phase 1 and tell us which agents are borderline-on-precision (drives fixture targeting).
- Resume: the engine's `checkpoint.py` + `tree_signature` + loud-abort-on-`APIError`
  (Plan 20b) — re-running resumes from the checkpoint.

### Phase 1 — Prompt + fixture audit workflow (ultracode, Opus, layered, file-backed)

**Every spawned agent** (not just every stage) writes its own output **and its resolved input
brief** to `.framework/plan21/<stage>/<id>.json`, and a re-invocation skips any id whose output
already exists — an idempotent, disk-backed work queue with **agent-granularity** resume (not
stage-boundary) that survives process death, new sessions, and quota resets. Persisting the
resolved briefs is for auditability/reproducibility, not mutation-protection: **all
orchestration stays in the deterministic workflow script — no LLM "manager" agents spawn
sub-agents** — so briefs are script-authored and structurally cannot be mutated by an
intermediate agent (the nested-agent alternative was considered and rejected as unnecessary
complexity). **All judgment agents run on Opus** (these are agentic reviewers;
[[subagent-review-model-pattern]] + the standard-case rule both require it).

**Stage 1 — Fan-out audit (one agent per prompt, ~20–21).** Inputs per agent: the prompt text,
its realised `good`/`bad` fixtures + `expect.json`, its **Phase 0c findings (with `--repeat 3`
variance)**, the draft shared rubric, and read/grep access to template conventions. Output
(structured): severity-bar issues, scope-creep, hallucination/over-reach, stricter-than-
codebase and internal-consistency violations; **fixture-validity verdicts** (is each `good`
genuinely clean? is each `bad` an unambiguous defect?); proposed **coupled prompt + fixture
edits** and a proposed `block_threshold`.

*The Plan 18 paid defect classes are deliberately **not** fed to the auditors* — they're from
the pre-collapse path, single-roll, and would anchor the independent audit on a curated
narrative. They are retained as a **controller-side regression checklist**: after Phase 1, the
controller checks that the audit independently surfaced the classes already known (institutional
memory without auditor contamination).

*Anchoring guard:* findings are fed as evidence to explain **and** to reason beyond; `--repeat
3` exposes variance not one roll; the adversarial stage counter-pressures rationalisation.

**Stage 2 — Judge-panel synthesis (~3 independent agents).** Each receives *all* Stage-1
reports + the draft rubric and independently produces a candidate consolidated changelist —
reconciling severity bars across agents (the "#3-HIGH vs #14-LOW for the same class" conflicts
no single audit can see), enforcing scope boundaries, refining the rubric.

**Stage 3 — Meta-synthesis (1 agent).** Judges + merges the ~3 candidates into **one**
changelist: finalised shared rubric, per-agent prompt rewrite, per-agent fixture edits,
per-agent `block_threshold` (global re-derivation lives here), and **which agents get a 2nd
`good` fixture** (data-driven targeting from Phase 0c).

**Stage 4 — Adversarial verification (the spine).** For each proposed change, ~3 skeptics
tasked to *refute*, default-to-refuted-if-uncertain: "this rewrite under-flags defect class X";
"this loosened bar lets `bad/Y` slip"; "you tuned against a dirty `good` fixture"; "this fixture
edit makes the bad case ambiguous." A change ships only if the majority **fail** to refute.
Refuted changes are **logged with the refutation and kicked back** for a human/next-round call
— never silently dropped. **Batched at ≤20–30 spawned skeptics per batch**, with verdicts
checkpointed to disk between batches.

**Output:** a vetted changelist of coupled prompt + fixture + threshold edits + a finalised
shared rubric.

### Phase 2 — Apply + per-agent re-tune (subagent-driven)

Apply each vetted coupled edit (prompt + fixture together). For each agent, re-run `framework
eval <agent> --repeat 3` on the free backend (reviewers at production models); the fixture
`expect.json` *is* the test — `good` fixtures must come back clean, `bad` fixtures caught.
Commit cadence per [[gate-cadence-framework-slices]]: lighter per-task review + controller
skip-markers, one branch-end Opus whole-branch review (these files are review-infra, so the
per-commit gate would over-fire).

### Phase 3 — Whole-set re-sweep + threshold re-derivation

The tuning flow is `framework eval` → `framework eval-analyze` — there is **no `framework
tune`** command (the `/reviewers:tune` slash command was retired in Plan 20b; `--repeat` lives
on `eval`, defaulting to 1, so we pass `--repeat 3` explicitly).
Final `framework eval` over all agents `--repeat 3` on free → `eval-analyze` → re-derive every
`thresholds.yaml` floor/ceiling with margin (recall_min = observed − 0.10, fp_max = observed +
0.10). **Re-derive — do not trust — the carried-over provisional edits from `e365a29`.**
Spot-confirm a sample on the **paid** backend (cheap now that dev = prod). Commit a dated
scorecard under `docs/superpowers/eval-scorecards/`.

## Verification

- New permanent `test_fixtures_are_wellformed` (round-trip / no-truncation).
- Existing `tests/review/test_evals.py` + registry/context-policy tests stay green.
- `block_threshold` changes must keep advisory agents advisory
  ([[flags-is-dual-use-gate-skips-advisory]]).
- Full gate green: `uv run pytest -q` / `uv run ruff check .` / `uv run mypy src`.

## Risks

- **Quota burn** (3 sweeps + 21-agent fan-out + judge panels + adversarial, all on `claude
  -p`): engine checkpoints (0c/2/3) + file-backed idempotent queue (Phase 1) + ≤20–30/batch
  adversarial pacing + optional `ScheduleWakeup` at the ~5-hour reset to auto-resume. Phase 1
  agents must distinguish *quota-hit* from *genuine-empty* so a re-run retries vs. skips.
- **Anchoring** on a single baseline roll → `--repeat 3` + adversarial spine.
- **Model-level parity** → reviewers-under-test always at production models (agentic = Opus).
- **20-agent breadth** → the workflow makes it tractable; the shared rubric keeps it coherent.

## Open decisions resolved by this design

- *Order (prompts vs fixtures vs thresholds)?* Hybrid: fixtures-infra + representativeness +
  baseline first (0a→0b→0c), audit workflow (1), apply per-agent (2), thresholds last (3).
- *How to measure prompt consistency objectively?* The good fixtures are the oracle — no
  separate test class.
- *Review `block_threshold` globally?* Yes — in Stage 3 meta-synthesis.

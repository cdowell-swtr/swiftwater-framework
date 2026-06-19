# FWK4 (Plan 23) — Reviewer self-audit tooling — Design

**Date:** 2026-06-19
**Status:** Design (brainstormed). Captures the Plan 21 audit→synthesis→adversarial
method as a repeatable, in-process capability.
**Depends on:** Plan 20 (collapsed engine + swappable LiteLLM backend, merged
`e6f6535`) and Plan 21 (the shared rubric + the method this generalizes).
**Roadmap:** the last open `Next` item; meta-plan "Plan 23 — agent self-improvement
tooling."

## Problem

Plan 21 re-tuned every reviewer prompt against one shared rubric, but the method —
fan-out audit → judge-panel synthesis → meta-synthesis → adversarial refutation — ran
as a **one-off interactive ultracode Workflow** and evaporated. The deterministic
building blocks survive as committed tooling (`framework eval`, `eval-analyze`, the
in-process engine + swappable backend, fixtures, `thresholds.yaml`, dated scorecards);
the **expensive, novel orchestration does not**. Every future reviewer change — a new
agent (FWK30 just added `coverage-gap`), a retune, a rubric move — re-incurs that
manual sweep or, worse, skips it and lets the shared bar drift.

Two realisations frame the design:

1. **The audit pipeline is itself a set of agentic LLM calls** that each hit
   `backend.messages.create(...)` — exactly the seam `framework eval`/`review` already
   run on. So the method can be captured **in-process on the LiteLLM backend**, not
   coupled to the Claude Code Workflow harness. The provider was already abstracted
   (Plan 5/20); the audit tooling should ride that same abstraction.
2. **Auditing one reviewer in isolation has no consistency oracle.** A reviewer tuned
   alone drifts from the shared bar, and a brand-new agent has nothing to be assessed
   *against*. The value of the rubric is cross-agent consistency, so the tool must
   always load the **full roster + shared rubric as the consistency baseline**, even
   when the changelist targets a single new agent.

A third realisation surfaced while scoping and pulls a prerequisite into the plan:
**the "shared" rubric is physically duplicated, verbatim, into each prompt — and has
already drifted.** Only 10/21 prompts carry the canonical `## Severity` header; the
output/findings-schema contract (13 prompts) has wandered (`architecture` had to bolt
on a "every element MUST include `severity`" reminder). Hand-duplication is not holding
the line. Before building a tool whose job is to *police and evolve* that rubric, the
rubric needs a single source of truth and a defined change-propagation path.

## Goals

- Ship `framework reviewer-audit` — an in-process, checkpoint-resumable command that
  runs the Plan 21 method (audit → cross-agent reconciliation → adversarial refutation)
  over 1..N reviewers and emits a **vetted changelist** of coupled prompt + fixture +
  `block_threshold` + rubric edits, each carrying its adversarial verdict and
  refutation log, plus a **dry-run git-applyable apply-preview patch**.
- Single-source the shared rubric + output/findings-schema contract via **runtime
  prompt assembly**, so consistency for the centralized blocks is structural (cannot
  drift) and the audit focuses its expensive judgment on each agent's **domain block**.
- Make the whole capability testable without burning quota (a stubbed backend drives
  the pipeline) and resumable across subscription-quota resets (agent-granularity
  disk-backed work queue, reusing `checkpoint.py`).

## Non-goals

- **No auditing of agents shipped into rendered projects** (the `--with agents`
  tool-loop agents, etc.). The meta-plan keeps that scope open; it has no eval/fixture
  surface today, so it is an explicit later slice.
- **No auto-apply.** The tool stops at a vetted changelist + an inspectable patch.
  Applying edits stays human/subagent-driven, with `framework eval` as the gate (the
  Plan 21 Phase-1/Phase-2 seam, made repeatable).
- **No reinvention of threshold derivation.** Global `block_threshold`/`thresholds.yaml`
  re-derivation rides the existing `framework eval` → `eval-analyze` → scorecard flow;
  the audit *proposes* per-agent `block_threshold` values, it does not recompute the
  numeric floors/ceilings.
- **No change to the review engine / backend seam** beyond the prompt-assembly seam in
  `request.py` (Phase 0).

## Decisions resolved in brainstorming

| Fork | Decision |
|------|----------|
| Audit target | **Framework reviewers only**; rendered-project agents deferred. |
| Packaging | **In-process `framework` subcommand** on the LiteLLM backend seam — not a Claude Code Workflow. |
| Run unit | **Unified 1..N agents**; full roster always loaded as the consistency baseline. |
| Output boundary | **Vetted changelist + dry-run apply-preview patch**; no auto-apply, no re-eval loop inside the command. |
| Rubric storage | **Runtime assembly** — single canonical preamble composed with each agent's domain block at prompt-build. |

## Phase 0 — Rubric/prompt centralization (runtime assembly)

*Prerequisite; independently valuable and mergeable on its own (the Plan-20-style
slice point).*

- **Canonical shared preamble.** One source of truth (e.g.
  `src/framework_cli/review/rubric.md` + a small `preamble.py` builder) holding the
  blocks that are genuinely shared and currently duplicated-and-drifted: the **severity
  ladder**, **codebase-bar principle**, **internal-consistency**, **scope-discipline**,
  **grounding/diff-awareness**, and the **output / findings-schema contract**.
- **Per-agent parameter, derived not invented.** The one real per-agent variation in
  the shared blocks is the allowed severity enum. It is **derived from
  `block_threshold`**: advisory agents (`block_threshold is None`) cap at `low|info` and
  never emit `high|medium`; threshold-bearing agents get the full ladder. A small
  optional `severity_enum` override field on `AgentSpec` covers the few bespoke cases
  (e.g. `dependency`'s `high|low|info` — no `medium`). No agent hand-writes a severity
  ladder again.
- **Domain-block-only prompts.** `agents/*.md` are trimmed to `## Your domain:
  review-X` + that agent's specific guidance. The shared sections are removed from the
  files.
- **Composition at the seam.** Prompt assembly composes `preamble(params) +
  domain_block`. The single seam is `request.py` where both `build_review_request` and
  `build_agentic_request` currently `system.append({"text": spec.prompt})`; the
  composed text is what gets appended (whether by recomposing `spec.prompt` at load in
  `registry._prompt`, or composing in `request.py` — an implementation detail resolved
  in the plan, kept in exactly one place).
- **Structural consistency, plus a guard.** Consistency for the centralized blocks
  becomes structural — they come from one source, so they cannot drift. A cheap guard
  test asserts no domain block re-introduces a centralized section (no rogue severity
  ladder / output contract leaking back in).
- **Eval is the safety net.** The assembled prompts are semantically equivalent to the
  pre-refactor concatenation, so the existing `tests/review/test_evals.py` recall/fp
  must stay green. That green is the proof Phase 0 did not move behavior — it is the
  consistency oracle for the refactor itself.

### "What if the rubric needs to move?"

The drift guard is **detection of accidental drift, not immutability.** Moving the
rubric is a deliberate edit to the single canonical source; runtime assembly
re-propagates it to every agent by construction, and the guard then validates the new
synced state. The audit pipeline, when it proposes a rubric refinement, emits **one edit
to the canonical preamble** in the changelist — never N independent prompt diffs.

## Phase 1 — Audit pipeline core (in-process, checkpointed)

A deterministic Python driver under `src/framework_cli/review/audit/` mirroring
`run_engine`: sequential dispatch over a work queue, each record checkpointed as it
completes, `BackendExhausted` stops scheduling and is resumable. **All orchestration is
script-authored — no LLM "manager" agent spawns sub-agents** (briefs are
structurally immutable by an intermediate agent). Every spawned agent's **resolved input
brief and output** persist to `.framework/reviewer-audit/<stage>/<id>.json`; a
re-invocation skips any id whose output already exists — an idempotent, agent-granularity
work queue surviving process death, new sessions, and quota resets (reuses
`checkpoint.py` + tree-signature).

Phase 1 lands the spine that produces a changelist for a single agent (reconciliation +
adversarial added in Phase 2):

- **Brief assembler.** Per target agent, gather: the assembled prompt (preamble +
  domain), its `good`/`bad` fixtures + `expect.json`, the **baseline `eval` findings**
  (`--repeat 3` variance), the canonical preamble, and the **full roster's domain
  blocks + `block_threshold`s** (the consistency oracle). Baseline findings are
  **consumed** from a prior `framework eval --findings-out` run via `--baseline <dir>`,
  and optionally generated if absent — the expensive `--repeat 3` sweep stays decoupled
  and independently resumable.
- **Audit fan-out.** One or more passes per target agent (≥1 for diversity), each an
  Opus agentic agent with read/grep over the template + fixtures (the existing tool
  loop). Structured output: severity-bar issues, scope-creep, hallucination/over-reach,
  stricter-than-codebase and internal-consistency violations; **fixture-validity
  verdicts** (is each `good` genuinely clean? is each `bad` an unambiguous defect?);
  proposed **coupled domain-block + fixture edits**; a proposed `block_threshold`.
- **Changelist schema.** A typed, on-disk structure: per-agent proposed edits (domain
  block, fixtures, `block_threshold`, preamble) — the contract every later stage reads
  and writes.

## Phase 2 — Cross-agent reconciliation + adversarial spine

- **Cross-agent reconciliation (always on).** One stage receiving *all* audit reports +
  the full roster's bars; it reconciles severity bars across agents (the "#3-HIGH vs
  #14-LOW for the same class" conflicts no single audit can see), enforces
  one-owner-per-class scope boundaries, and proposes **preamble** refinements. This is
  Plan 21's judge-panel + meta-synthesis, collapsed into one stage now that the run is
  reviewer-scoped rather than a 21-agent cold sweep.
- **Adversarial refutation spine (the spine).** For each proposed change, ~3 skeptics
  tasked to *refute*, default-to-refuted-if-uncertain ("this rewrite under-flags defect
  class X"; "this loosened bar lets `bad/Y` slip"; "you tuned against a dirty `good`
  fixture"). A change ships only if the **majority fail to refute**. Refuted changes are
  **logged with the refutation and kicked back** for a human/next-round call — never
  silently dropped. Batched at ≤20–30 spawned skeptics per batch, verdicts checkpointed
  between batches.
- **Output:** the vetted changelist — coupled prompt + fixture + `block_threshold` +
  preamble edits, each annotated with its adversarial verdict and refutation log.

## Phase 3 — Apply-preview + CLI polish + runbook

- **Dry-run apply-preview.** Render the vetted changelist as a **git-applyable patch**
  the maintainer can inspect and `git apply` themselves. No auto-mutation; the apply
  step is one reviewed command away, and `framework eval <agent>` is the gate on the
  applied result.
- **CLI surface.** `framework reviewer-audit [AGENTS...] --baseline <dir>
  [--backend api|subagent] [--out <dir>] [--resume]`. Default `AGENTS` = all; the full
  roster is always loaded as the consistency baseline regardless of the target subset.
- **Runbook.** A short `docs/.../runbooks/` page (or skill) tying the end-to-end flow:
  `eval --findings-out` baseline → `reviewer-audit` → inspect changelist + apply-preview
  → apply → `eval <agent>` re-confirm → `eval-analyze` threshold re-derivation +
  scorecard. This is the durable record of the method the tool automates.

## Verification

- **Phase 0 oracle:** `tests/review/test_evals.py` recall/fp stays green across the
  centralization (semantically-equivalent assembly); registry + context-policy +
  reference-doc tests stay green; the new structural guard (no domain block redefines a
  centralized section) is bite-proven (inject a rogue severity ladder → RED).
- **Pipeline without quota:** a **backend-stubbed pipeline test** drives the full
  audit → reconcile → adversarial flow with a fake backend returning canned outputs,
  asserting changelist shape **and that refuted changes are excluded** from the vetted
  set. The orchestrator's resume is unit-tested against `checkpoint.py` (re-invocation
  skips completed ids).
- **Advisory invariant:** any proposed `block_threshold` change keeps advisory agents
  advisory ([[flags-is-dual-use-gate-skips-advisory]]).
- **Full gate:** `uv run pytest -q` / `uv run ruff check .` / `uv run ruff format
  --check .` / `uv run mypy src` all green.

## Risks

- **Quota burn** (audit fan-out + reconciliation + adversarial, all on `claude -p`):
  agent-granularity disk-backed idempotent queue + `BackendExhausted`-graceful stop +
  ≤20–30/batch adversarial pacing + optional `ScheduleWakeup`/cron auto-resume at the
  ~5-hour reset. Audit agents must distinguish *quota-hit* from *genuine-empty* so a
  re-run retries vs. skips.
- **Phase 0 behavior drift.** Recomposing prompts could subtly change reviewer
  behavior; the eval suite is the guard, and Phase 0 is a standalone mergeable
  checkpoint so any regression is isolated before the pipeline lands on top.
- **Anchoring** on a single baseline roll → consume `--repeat 3` findings (variance,
  not one roll) + the adversarial spine counter-pressures rationalisation.
- **Model-level parity** → audit/reconciliation/adversarial agents run on **Opus**
  (agentic judgment; [[subagent-review-model-pattern]]), reviewers-under-evaluation at
  their production models — never a cheaper stand-in.
- **Scope creep into a prompt-templating framework.** Phase 0 centralizes the shared
  blocks only; domain blocks stay per-agent and hand-authored. Explicit non-goal: a
  general prompt-templating engine.

## Build phasing

Subagent-driven (executing-plans), per-task TDD. Review-model policy:
implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet;
code-quality + branch-end whole-branch review → **Opus** ([[subagent-review-model-pattern]]).
Commit cadence per [[gate-cadence-framework-slices]] (review-infra files over-fire the
per-commit gate → lighter per-task review + controller skip-markers + one branch-end
Opus whole-branch review).

- **Phase 0** — centralization; mergeable checkpoint, eval-green is the proof.
- **Phase 1** — brief assembler + orchestrator + audit stage + changelist schema;
  single-agent end-to-end.
- **Phase 2** — reconciliation + adversarial spine; full vetted changelist.
- **Phase 3** — apply-preview patch + CLI polish + runbook.

Test/maintainer-tooling only → **no release, no template payload** (the
`reviewer-audit` command and the rubric refactor are framework-internal; rendered
projects are unaffected — Phase 0 must keep the rendered prompt payload, if any,
byte-identical, which it does since reviewers are framework-only).

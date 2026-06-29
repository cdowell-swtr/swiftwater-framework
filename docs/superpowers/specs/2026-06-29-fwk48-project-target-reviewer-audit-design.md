# FWK48 — auditing the review agents as applied to generated projects

> **Date:** 2026-06-29 · **Status:** approved (brainstorm) · **Author:** Chris (with Claude) ·
> **Stream:** experiment-2 **S2** (audit pipeline), tail row after FWK46/47 ·
> **Carving:** `docs/superpowers/specs/2026-06-29-second-worktree-parallel-experiment-carving-design.md`

## Purpose & the debt

`reviewer-audit` (the audit→reconcile→refute calibration pipeline) only ever calibrates the
framework's review-agent prompts against the framework's **own** fixtures
(`tests/eval/fixtures/<agent>/`). But the *same* prompts are what `framework audit --target project`
runs against a **generated project's** code (the `active_agents()` roster — every non-`framework_only`
agent). Those prompts have never had an audit pass in **project context**: an agent calibrated to
review the framework's own Copier-template Python may over- or under-flag a generated FastAPI app's
idioms. That uncalibrated-in-project-context gap is the reviewer debt FWK48 kills.

This is **not** carved into "later" follow-ups — perpetuating the debt is exactly what the experiment
exists to prevent. FWK48 closes the gap end-to-end inside S2, decomposed into three individually-
committable top-level rows (**FWK118 → FWK119 → FWK120**).

## Survey of the ground truth (what exists today)

- **Generated projects ship no agent prompts.** They ship only a thin invocation layer
  (`.claude/commands/reviewers/{gate,audit}.md`, `.claude/hooks/reviewers-gate-check.sh`,
  `.claude/settings.json`) that shells out to the installed `framework` CLI. The agents, registry,
  prompts, and audit pipeline live solely in `framework_cli` and are applied to the project via
  `--target project` auto-detection (`.copier-answers.yml` present → project).
- **`framework audit` is target-aware** (`framework`/`project`, `_detect_audit_target`,
  `_build_audit_items`: `FRAMEWORK_AGENTS` vs `active_agents(read_batteries("."))`).
  **`reviewer-audit` is NOT** — it audits `agent_names()` against `tests/eval/fixtures/` unconditionally.
- **`build_audit_brief(target, *, root, baseline_dir, fixtures_root=None)` already accepts a
  `fixtures_root`** — but `run_audit`'s `_audit` closure never passes it, so the audit always reads
  the framework's own fixtures.
- **Prior art** (`docs/superpowers/specs/2026-05-29-local-reviewers-design.md`): line 74 — "*`tune`
  ships only in the framework repo (projects don't tune because they don't own the fixtures)*"; line
  443 — "*Project-side tuning. Generated projects don't own fixtures… Tooling deferred — likely a
  'bring your own fixtures' extension.*" FWK48 is that deferred extension, now built.

## The combo (operator decision)

Two halves, one shared mechanism. **Rookie-free invariant:** a generated project that does nothing
keeps its agents working out-of-the-box (the gate/audit are already skip-neutral). Tuning is an
*opt-in, advanced* capability — never on a rookie implementer's critical path.

### Half 1 — framework-repo, against a render (the default; maintainer-run)
The framework audits its **built-in** agents *as applied to a project*: the `active_agents()` project
roster against **project-context fixtures** (diffs of generated-project code, authored against a
render) instead of the framework's own fixtures. Rookies inherit the calibrated prompts by doing
nothing. This is the source-of-truth path — prompt edits land in the framework repo (per CLAUDE.md:
"reviewer system = source of truth in the framework").

### Half 2 — consumer-side BYO tuning (opt-in; for projects that add their own reviewers)
A generated project can register its **own** reviewer with zero framework changes, via a
file-convention discovered at audit time:

```
.framework/reviewers/<name>.md                     # the domain prompt (same shape as agents/<name>.md)
.framework/reviewers/<name>.toml                   # block_threshold, context policy, trigger globs, active_when
.framework/reviewers/fixtures/<name>/{good,bad}/<case>/change.patch [+ expect.json]
```

`framework audit --target project` **and** `reviewer-audit --target project` discover these,
merge them into the project roster, and (for the audit) calibrate them against their project-local
fixtures. A project with no `.framework/reviewers/` directory behaves **identically** to today —
the rookie-free invariant, by construction.

### The shared mechanism (what both halves need)
Make the audit pipeline **target-aware**: `reviewer-audit` audits a *chosen agent roster* against a
*chosen `fixtures_root`*, rather than hardcoding `agent_names()` + `tests/eval/fixtures/`. That single
capability serves Half 1 (built-in agents vs project fixtures) and is the foundation Half 2 extends
(project-local agents vs project-local fixtures).

## What is code vs what is an operator op

Building the capability — target-aware audit, project-local reviewer discovery, project fixtures — is
**all plain, unit-testable code**: the pipeline is exercised with the injectable `StubBackend`, and
fixtures are validated by **realization** (`test_evals.py::test_every_fixture_realizes`: render +
`git apply`, no live scoring). The only thing that uses a live backend is an **actual production
recalibration run** (`reviewer-audit --target project` against a real backend) — which is an
operator op that *every* `reviewer-audit` invocation already is, not a code task. So the whole combo
fits S2's "unit-tested, no live backend in dev/tests" character; the live run is the op the
now-closed capability *enables*.

## Decomposition — three top-level rows, all landing in S2

> Per the per-worktree protocol these are **top-level FWK ids** (provisional/local while S2 runs;
> reconciled to the monotonic block at merge), **not** `48a`-style sub-ids. FWK48 is the umbrella.

### FWK118 — Target-aware audit core
Thread `fixtures_root` + an explicit agent roster through `run_audit` → `_audit` →
`build_audit_brief`. Add to the `reviewer-audit` CLI: `--target framework|project` (project →
`active_agents(read_batteries("."))` roster + a project-fixtures root) and `--fixtures-root <dir>`
(the explicit/BYO override). Default (`--target framework`, no flags) is byte-for-byte today's
behavior. The provenance fingerprint (FWK47) already folds `targets` + tree state in; extend it so a
changed `fixtures_root`/target also invalidates a stale resume. **Tests:** unit (StubBackend) — the
audit reads the chosen fixtures_root; `--target project` selects `active_agents()`; framework default
unchanged.

### FWK119 — Project-local custom reviewers
A discovery module that reads `.framework/reviewers/<name>.{md,toml}` + its fixtures and yields
`AgentSpec`-shaped project reviewers, merged into the `--target project` roster for **both**
`framework audit` and `reviewer-audit`. A name-collision with a built-in agent is a loud error (no
silent shadowing). `<name>.toml` carries `block_threshold`, `active_when`, `trigger_globs`, and the
context policy. **Rookie-free:** absent directory → empty list → identical behavior. **Tests:** unit —
discovery parses a fixture project-reviewer; the merged roster includes it; `framework audit --target
project` runs it; `reviewer-audit --target project --fixtures-root .framework/reviewers/fixtures`
audits it; collision → error; empty → no-op.

### FWK120 — Project-context fixtures + the render oracle
A project-context fixture set for the built-in agents (a representative seed authored against a fresh
render — e.g. security/privacy/application-logic good+bad pairs over generated-project code),
validated by the realize test (not live eval). Wire the render-then-audit oracle on top of the
existing `template-map`/`template-audit` scaffold (`cli.py:217`). A smoke/integration test renders a
project, runs `reviewer-audit --target project` through a StubBackend against the project fixtures, and
asserts the path runs end-to-end (changelist written, project roster used). **Tests:** unit/realize +
the render smoke (no live backend).

## Documentation deliverables
- Update `.claude/commands/reviewers/audit.md.jinja` (generated-project doc) with the opt-in
  `.framework/reviewers/` BYO-tuning section + the rookie-free note.
- A maintainer doc (or a section in an existing one) for the framework-repo render-then-audit oracle.
- The generated reviewer-reference page is registry-derived — no hand edits (FWK3).

## Non-goals (genuinely out, not deferred-debt)
- Auto-**applying** a project-target changelist to the built-in prompts — `reviewer-audit` is
  preview-only by design (FWK4); applying stays the maintainer's reconciled hand-edit, eval-gated
  per [[reviewer-tuning-is-prompts-not-thresholds]]. FWK48 produces the changelist; it does not change
  the apply policy.
- A live-eval recalibration **sweep** as a code task — it is the operator op the tooling enables.

## Open risks / loud-finding watch
- If `active_agents()` for the default render is empty/near-empty without batteries, the project-target
  audit covers little — FWK120's seed should render with a representative battery set, and the smoke
  test asserts a non-vacuous project roster.
- The `.framework/` directory is also where audit output + review config live; the `reviewers/`
  subtree must not collide with `audit/`, `review.toml`, etc. (it does not today).

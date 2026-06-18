# FWK38 — CI Actions-minutes savings (concurrency + paths) (design)

> Status: approved design (2026-06-18). Next: writing-plans → implementation plan.
> Goal: cut the GitHub Actions minutes the framework's *generated* workflows cost a
> consumer — so a private consumer (Meridian) stays under its included free-minute cap —
> via `concurrency` cancellation and `paths` filtering, shipped in the template (every
> consumer benefits on upgrade) plus a brief for Meridian to apply the same now.

## Problem

A consumer flagged its GitHub Actions usage at **1,834 / 2,000** included minutes/month
(gross $11.00, **billed $0** — still inside the free allowance, but a `$0` spend budget
will **block** all CI once it crosses 2,000). The consumer is **Meridian** (a private
generated project).

**The framework repo itself is NOT the problem.** `cdowell-swtr/swiftwater-framework` is
**public**, and GitHub gives public repos **unlimited free** minutes on standard runners —
its `/timing` API confirms every run bills 0. So optimizing the framework's *own* CI saves
nothing on the quota; the spend is entirely in **private consumers**.

**Root cause (Meridian, measured via `run_duration` + the generated `ci.yml` job graph):**
the dominant consumer is the generated **`ci.yml`**, which fans out into **9 parallel jobs**
(`integrity → lint → {test, build, contract, contracts, frontend} → review-plan → review →
review-aggregate`). GitHub **rounds every job up to the nearest minute and bills per-job**,
so one CI run costs **≥9 billed minutes regardless of how fast the work is** — and with **no
`concurrency`** in any generated workflow, every mid-PR push starts a fresh 9-job run while
the superseded one keeps billing. Across an actively-iterated repo that is the bulk of the
1,834 minutes. (`deploy-staging` on every `main` push is a distant second; `docs-layout` is
negligible.)

The generated workflows ship **no `concurrency`** and **no `paths`** filters — a template
gap affecting every consumer.

## Scope

Two levers, confirmed in brainstorming (a third — collapsing the 9-job fan-out to cut the
per-job-rounding floor — is **explicitly deferred**: it restructures the gate and deserves
its own evaluation, not a budget-driven rush):

1. **`concurrency` (the ~90% win, universally safe)** — cancel superseded in-progress runs.
2. **`paths` filtering** — skip work on changes that cannot affect it.

And **two delivery targets**:

- **(A) Template fix** — in `swiftwater-framework`, this FWK38. Every consumer inherits it on
  `framework upgrade`. The framework repo is public, so this change and its PR cost **0**
  minutes; its value is *durably shipping the fix to all consumers*.
- **(B) Meridian brief** — a written brief (exact YAML + an integrity-drift note) handed to
  Meridian's own maintainer/session to apply **now**, for immediate relief this billing
  cycle. **This design does NOT edit Meridian** (per the maintainer's instruction); it
  produces the brief.

### The required-check wedge (why lever 3 splits A vs B)

A workflow-level `paths-ignore` on a workflow whose jobs are **branch-protection-required**
wedges PRs at "Expected — waiting for status" (the skipped required check never reports).
- **Meridian** has **no required status checks** on `main` (verified: `required checks: []`,
  no rulesets) → `paths-ignore` on its `ci.yml` is **safe**.
- **The template** ships to consumers who *may* require the CI jobs → a workflow-level
  `paths-ignore` on the generated `ci.yml` would be a footgun. The wedge-safe version (a
  `paths-filter` job gating each heavy job + an always-running `ci-complete` sentinel that
  reports success when work is skipped) is a real restructure with modest payoff (docs-only
  PRs are a minority) → **deferred**; the template `ci.yml` gets a documented opt-in comment
  instead of a shipped `paths-ignore`.

## Design

### Deliverable A — Template (this FWK38)

**A1. `concurrency` on all generated workflows.**

`ci.yml.jinja` and the generated `docs.yml` (PR-iteration workflows) — cancel superseded:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

`deploy-staging.yml` and `deploy-prod.yml` (deploys) — **serialize, never cancel mid-deploy**:
```yaml
concurrency:
  group: deploy-staging   # (deploy-prod for the prod workflow)
  cancel-in-progress: false
```
Cancelling a half-finished deploy is unsafe; concurrent merges queue their deploys instead.

**A2. `paths` (scoped to wedge-safe).**

- Generated `docs.yml` (docs-publish workflow; **not** a required gate): add a `paths:`
  *include* so it runs only on docs-relevant changes (`docs/**`, `mkdocs.yml`, `**.md`), not
  on code-only changes.
- `ci.yml.jinja`: **no** workflow-level `paths-ignore` (wedge risk). Add a comment block
  documenting how a consumer with no required CI checks can opt into `paths-ignore` for
  docs-only changes, and that the wedge-safe sentinel restructure is a tracked follow-up.

### Deliverable B — Meridian brief (produced, not applied)

A markdown brief instructing Meridian's maintainer/session to apply, in Meridian:
- **Concurrency** on all four workflows — `ci.yml` + `docs-layout.yml`:
  `cancel-in-progress: true`; `deploy-staging.yml` + `deploy-prod.yml`: serialized group,
  `cancel-in-progress: false`.
- **`paths-ignore`** on `ci.yml` (`**.md`, `docs/**`, …) — *safe in Meridian* (no required
  checks) → docs-only changes skip the 9-job gate.
- **`paths`** *include* on `docs-layout.yml` (run only on docs changes).
- **Integrity-drift note:** `ci.yml`/`deploy-*.yml` are framework-locked (`LOCKED_TRACKED`),
  so editing them makes `framework integrity` report drift until Meridian next runs
  `framework upgrade` onto the released template — at which point the content matches and the
  drift self-heals. The brief states this explicitly so it is an expected, temporary state.
- The brief is **not committed to this public repo** (it names Meridian's private workflow
  layout); it is handed over as a standalone artifact.

## Out of scope (deferred, with rationale)

- **Lever 2 — collapse the 9-job fan-out** (the per-job-minute-rounding floor). Bigger
  payoff but restructures the gate's parallelism/structure; its own decision.
- **The wedge-safe `ci.yml` `paths` restructure** for the template (paths-filter job +
  `ci-complete` sentinel). Modest payoff, real complexity; tracked follow-up.

## Testing (template side)

- `tests/test_copier_runner.py` render guards: a render asserts the generated `ci.yml` and
  `docs.yml` carry the `${{ github.workflow }}-${{ github.ref }}` concurrency group with
  `cancel-in-progress: true`; `deploy-staging.yml`/`deploy-prod.yml` carry the serialized
  `deploy-*` group with `cancel-in-progress: false`; `docs.yml` carries the `paths` include.
- The existing YAML-validity / `test_workflow_node24` guards still pass (`concurrency` and
  `paths` are valid GHA keys; no action versions change).
- **No FWK29 change:** `concurrency`/`paths` are metadata on existing workflows, not new
  enumerable operational surfaces (the generated `ci.yml` jobs are already classified EXEMPT).

## Release

Template payload. Defaults preserve behavior (concurrency only *cancels redundant* runs;
the `docs.yml` paths-include only narrows an over-broad trigger) — no consumer breakage.
Because the framework repo is **public (free CI)**, there is **no minute-cost reason** to
batch this PR; it batches with the other release-deferred template work (FWK6/FWK36/FWK37)
only for **release cadence** (one release), not for minutes. Meridian's relief does not wait
on the release — it comes from the brief.

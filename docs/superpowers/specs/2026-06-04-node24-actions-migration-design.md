# NODE24-MIGRATION — GitHub Actions Node 24 runtime migration

**Date:** 2026-06-04
**Status:** Design — approved, pending spec review
**Plan placement:** `NODE24-MIGRATION` named priority row (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`), scheduled **next, ahead of Plan 16** (frontend-obs) — the migrated action baseline is what Plan 16's frontend-obs CI will build on.
**Depends on:** none (mechanical + a guard test); independent of Plans 16–19.

## Problem

GitHub is removing the Node.js 20 actions runtime. Per the deprecation notice surfaced in our own workflow logs:

> Node.js 20 actions are deprecated… Actions will be **forced to run with Node.js 24 by default starting June 16th, 2026**. Node.js 20 will be **removed from the runner on September 16th, 2026**.

Both surfaces ship Node-20-pinned actions today:

- **The framework's own 5 workflows** (`ci.yml`, `release.yml`, `render-matrix.yml`, `review.yml`, `agent-evals.yml`) — `actions/checkout@v4`, `astral-sh/setup-uv@v5`, `actions/{upload,download}-artifact@v4`, `actions/setup-node@v4`.
- **The generated template's 3 workflows** (`ci.yml.jinja`, `deploy-prod.yml`, `deploy-staging.yml`) — the same set. Every project a builder scaffolds inherits them.

When the forced-Node-24 default lands, Node-20 actions run on a runtime they weren't built for (a correctness/stability risk, not just a warning), and after the Sept removal they fail outright. EOL is September, but we migrate now — well ahead of the June 16 forced-default — rather than absorb the risk.

## Goal

Pin every workflow action (framework + template) to a Node-24-capable version, and add a regression guard so the repo can't silently drift back onto a Node-20 action — for generated projects as well as the framework itself.

## Approach (chosen)

### Part A — version bumps (both surfaces)

Bump the Node-20 actions to their verified Node-24 versions:

| Action | Now | Node-24 target |
|---|---|---|
| `actions/checkout` | `v4` | `v5` |
| `astral-sh/setup-uv` | `v5` | `v6` |
| `actions/setup-node` | `v4` | `v6` |
| `actions/upload-artifact` | `v4` | `v6` |
| `actions/download-artifact` | `v4` | `v7` |
| `arduino/setup-task` | `v2` | **verify at impl** (pin to a Node-24 release; T1) |
| `softprops/action-gh-release` | `v2` | **verify at impl** (T1) |
| `oasdiff/oasdiff-action/breaking` | `v0.0.21` | **exempt** — Docker-container action (no Node runtime) |
| `gitleaks/gitleaks-action` | `v2` | **exempt** — Docker-container action |

Pinning stays at the existing **major-version-tag** convention (e.g. `@v5`), matching the repo's current style — not full SHAs.

**T1 verification rule for the two uncertain third-party actions:** if a clean Node-24 release exists, pin to it. If `softprops/action-gh-release` still has no Node-24 release at implementation time, hold it at its current version and record it as an explicit, dated `runtime: node20-forced` exception in the allowlist (GHA force-runs it on Node 24 regardless; removal isn't until September). The exception is a tracked, visible decision — not a silent omission.

### Part B — allowlist guard test (the core deliverable)

A single source-of-truth allowlist and one pytest (`tests/test_workflow_node24.py`):

- **`APPROVED_ACTIONS`** — an inline, documented map `action-path → {min_major: int, runtime: "node" | "docker" | "node20-forced"}`. This map *is* the executable policy.
- The test collects every `uses:` reference across **both** surfaces:
  - framework: `.github/workflows/*.yml`
  - template: `src/framework_cli/template/.github/workflows/*.yml` and `*.yml.jinja`
- For each reference it asserts: the action is present in `APPROVED_ACTIONS`, and (for `runtime: node`) its pinned major version is `>= min_major`. `docker` and `node20-forced` entries skip the version-floor check but **must still be listed** — an unrecognized `uses:` fails the test, forcing a human to consciously add it (exhaustive-by-construction; this is why the allowlist beats a denylist).
- **Raw-source scan** (no render): the `.jinja` `uses:` lines are static strings, not Copier-interpolated. A companion assertion fails if any `uses:` value contains `{{`/`{%` (a dynamic action ref) — keeping the raw-scan assumption honest; if that ever fires, we revisit.

### Part C — docs

- A short framework-maintenance note at `docs/maintenance/github-actions-node-runtime.md`: the policy (all workflow actions pinned to Node-24-capable versions), the June-16-forced / Sept-16-removed timeline, that `tests/test_workflow_node24.py::APPROVED_ACTIONS` is the source of truth, and the "bump here + update the allowlist when adding/updating an action" workflow.
- A one-line pointer in CLAUDE.md's critical-conventions section.
- This is framework-maintenance documentation, **not** builder-facing — generated projects inherit correct versions without needing to manage the framework's action policy.

## Components / files

| File | Change |
|---|---|
| `.github/workflows/{ci,release,render-matrix,review,agent-evals}.yml` | Bump Node-20 actions per Part A. |
| `src/framework_cli/template/.github/workflows/{ci.yml.jinja,deploy-prod.yml,deploy-staging.yml}` | Same bumps. |
| `tests/test_workflow_node24.py` | New: `APPROVED_ACTIONS` allowlist + the two-surface guard test (Part B). |
| `docs/maintenance/github-actions-node-runtime.md` | New: the maintenance policy note (Part C). |
| `CLAUDE.md` | One-line conventions pointer. |
| `pyproject.toml` / `uv.lock` / `dogfood.py` | Version bump for the release (template workflows are builder-facing → cut a release). |

## Validation

- **Guard test** is TDD-first: write it with the target allowlist, watch it go **red** against the current `v4`/`v5` workflows (proves it catches the violation), then bump until green on both surfaces.
- **Framework workflows** are validated **live** by pushing the branch — the framework's own CI re-runs on the bumped actions (a green run on Node-24 actions is the proof).
- **Template `ci.yml`** is exercised by the render-matrix (and optionally a dogfood run) on the bumped actions.
- **Template `deploy-*.yml`** get static validation: `actionlint` + the allowlist test + render content tests (no live deploy target exists to run them).
- **Integrity / baseline manifest:** the plan checks whether any bumped template workflow (notably the LOCKED `ci.yml`) is integrity-tracked; if so, this is a one-time baseline manifest shift, called out and reflected in the integrity tests (mirrors how prior LOCKED-file changes were handled).
- **Release:** template workflow changes are builder-facing, so this ships as the next patch release (`v0.1.7`): bump `pyproject` + `uv lock` + `DOGFOOD_COMMIT`, tag, `release.yml`.

## Tasks (subagent-driven; detailed by writing-plans)

- **T1 — verify + pin** the two uncertain third-party action versions (`arduino/setup-task`, `softprops/action-gh-release`); finalize the `APPROVED_ACTIONS` map (investigative, no TDD).
- **T2 — allowlist guard test** (TDD: write → red against current workflows → confirms it catches the violation).
- **T3 — bump the framework's 5 workflows** → guard test green for the framework surface.
- **T4 — bump the template's 3 workflows** → guard test green for the template surface; re-render + `actionlint` + content tests; resolve any integrity/manifest shift.
- **T5 — docs** (maintenance note + CLAUDE.md pointer).
- **T6 — validation + release** (controller): full local gate; live framework-CI + render-matrix green on the bumped actions; branch-end review → merge FF → cut `v0.1.7`.

## Out of scope (YAGNI)

- Migrating away from major-version tags to full-SHA pinning (a separate supply-chain hardening decision).
- The interim `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` runner env var (a stopgap for *not* bumping — we're bumping, so it's unnecessary).
- Bumping Docker-based actions (oasdiff/gitleaks) for the Node migration — they have no Node runtime; routine version maintenance is separate.
- Any non-workflow Node usage (e.g. the react frontend's own Node version) — that's the frontend toolchain, not the Actions runtime.

## Risks / edges

- **A bumped action introduces a breaking change** (esp. `download-artifact@v7`, flagged "breaking") — the live CI run is the catch; if a step's inputs changed, the plan adjusts that step. Low risk (these are well-documented, widely-adopted bumps).
- **`softprops/action-gh-release` has no clean Node-24 release** — handled by the tracked `node20-forced` allowlist exception (Part A / T1), revisited before the Sept removal.
- **Baseline manifest shift** if a template workflow is integrity-tracked — handled as a called-out one-time bump in T4 (not a surprise).

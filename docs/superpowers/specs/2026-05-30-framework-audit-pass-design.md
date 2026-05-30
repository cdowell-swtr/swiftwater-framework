# Framework audit pass — design

**Status:** spec
**Date:** 2026-05-30
**Related:** `docs/superpowers/plans/2026-05-20-meta-plan.md`, `docs/superpowers/specs/2026-05-29-local-reviewers-design.md`

## Context

Plan 11 calibrated all 18 review agents via `/reviewers:tune` against rendered fixtures and committed dated tune scorecards. We have never pointed the agents at the actual framework code to find real problems. `.framework/audit/latest/findings/` is empty; the only `marker.json` is an empty-staged-hash no-op from the commit gate.

This spec defines the first-ever audit pass against framework Python source. It is a **baseline** — a snapshot of starting findings, triage decisions, and what we deferred — preserved as a dated artifact parallel to the existing tune scorecards.

## Goals

1. Surface real issues in `src/framework_cli/` that the calibrated review agents would catch.
2. Produce a preserved, dated baseline artifact so re-runs later have a diff target.
3. Split the mode-multiplexed `eval-prepare` / `eval-finalize` shared commands into mode-specific commands (`tune-*`, `audit-*`, `gate-*`) so each command does one job. The current naming inherits from the paid-tune era; "eval" semantically belongs to tune and the shared commands obscure that audit and gate are operationally distinct paths.
4. Add small, contained tooling on the new audit surface to make a targeted multi-agent audit + preservation a first-class operation.

## Non-goals

- Auditing the template payload (`src/framework_cli/template/`). That's a separate, later pass with different mechanics (must render first; calibrated for rendered output, not raw `.jinja`).
- Auditing tests. Tests aren't the system under test.
- Hooking the audit into CI. This is a manual, milestone-style pass; recurring enforcement is `/reviewers:gate`'s job.
- Implementing fix-now findings. That's planned per-finding via writing-plans once findings are known.

## Scope

### Target
`src/framework_cli/` — framework Python source only. Auto-detection (`--target framework`) already supports this.

### Agent roster (9 of 19)
Selected because they apply to a Python CLI shell over Copier; the rest are calibrated for surfaces this code doesn't have (frontend, databases, data pipelines, observable services, PII, regulatory).

- `application-logic`
- `api-design` (CLI surface = subcommands, flags, exit codes)
- `architecture`
- `contracts`
- `dependency`
- `documentation`
- `performance`
- `security`
- `test-quality`

Skipped: `accessibility`, `usability`, `data-lineage`, `data-integrity`, `observability`, `observability-db`, `observability-infra`, `privacy`, `compliance`.

`observability` is skipped specifically because observability is an ongoing exercise tracked elsewhere, not a one-time review concern for the framework CLI.

## Architecture

Three phases. The spec covers Phases 1 and 2; Phase 3 is planned later.

### Phase 1 — Run
A single `/reviewers:audit` invocation dispatches 9 subagents in parallel (one per roster agent) against the framework source. Produces raw findings + a consolidated markdown report in `.framework/audit/latest/`.

### Phase 2 — Preserve + triage
Copy `latest/` into a dated dir under `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/` and hand-write `triage.md`: each finding gets a decision (`fix-now` / `defer` / `false-positive`) plus a one-line rationale. Commit the dated dir.

### Phase 3 — Fix-now (outside this spec)
Implement the `fix-now` decisions in subsequent commits/PRs. `defer` and `false-positive` rows stay in `triage.md` as the record of what we knowingly didn't fix and why.

## Components

### 0. Split shared commands by mode (prerequisite refactor)

The existing `eval-prepare` / `eval-finalize` commands are mode-multiplexed (~750 LOC total, 9 `mode ==` branches across the two). Split them into three command pairs, one per mode, with the per-mode branch bodies as the new command implementations.

| Today | After |
|---|---|
| `eval-prepare --mode tune ...` | `tune-prepare ...` |
| `eval-prepare --mode audit ...` | `audit-prepare ...` |
| `eval-prepare --mode gate ...` | `gate-prepare ...` |
| `eval-finalize --mode tune ...` | `tune-finalize ...` |
| `eval-finalize --mode audit ...` | `audit-finalize ...` |
| `eval-finalize --mode gate ...` | `gate-finalize ...` |

- `--mode` is removed; each new command knows its mode.
- Shared helpers (e.g. manifest loading, work-item building, agent validation) factor into module-level functions called by all three command pairs.
- The umbrella `framework eval` command (paid tune scoring, Slice D) stays. `framework eval-analyze` stays — it's tune-specific already.
- No backward-compatibility aliases. We control every call site.

**Call sites to update (exhaustive):**

- `.claude/commands/reviewers/audit.md` (slash-command body)
- `.claude/commands/reviewers/tune.md`
- `.claude/commands/reviewers/gate.md`
- `.claude/workflows/reviewers-audit.js` and `.claude/workflows/reviewers-tune.js` and `.claude/workflows/reviewers-gate.js`
- `.claude/hooks/reviewers-gate-check.sh`
- The `template/` mirrors of all four (commands, workflows, hooks) that ship in generated projects
- `docs/superpowers/eval-scorecards/README.md` (the "how to produce one" runbook)
- `docs/superpowers/plans/2026-05-20-meta-plan.md` references (where load-bearing)
- `tests/` — any test that invokes `framework eval-prepare ...` directly
- Any other `framework eval-prepare` / `framework eval-finalize` literal in the repo (a `git grep` will catch stragglers)

### 1. `audit-prepare` — repeatable `--agent`
On the newly-split `audit-prepare`, add support for `--agent` being passed multiple times (`--agent security --agent dependency …`) so the prep manifest builds work-items for an arbitrary subset.

- Single-agent path (one `--agent`) and all-agents path (no `--agent`) stay unchanged.
- Duplicate values are deduplicated.
- Unknown agent names error with a clear message listing valid names.
- This flag is **audit-only**; `tune-prepare` and `gate-prepare` keep their existing agent-selection contracts.

### 2. `audit-finalize` — `--preserve-as <dir>`
New flag on `audit-finalize`. After the workflow finishes and `audit-report.md` is written into `.framework/audit/latest/`, this copies the directory tree (findings + report + meta) into a target dated dir.

- Idempotent: if the target dir doesn't exist, create it; if it exists and is empty, populate it.
- Refuses to overwrite a non-empty target dir without `--force`. Prints the conflicting path.
- Copies: `findings/`, `audit-report.md`, `meta.json`. Does not copy `prep-manifest.json` (intermediate).

### 3. `triage.md` (hand-written)
Lives at the root of the dated baseline dir. Single-table format:

```markdown
# Triage — framework audit YYYY-MM-DD-<sha>

| # | Agent | Severity | File:line | Summary | Decision | Rationale | Fixed-in |
|---|---|---|---|---|---|---|---|
| 1 | review-security | high | cli.py:142 | Unsanitized path to subprocess | fix-now | Real — user input reaches Popen | <commit-sha or PR#> |
| 2 | review-architecture | medium | wizard.py | 600 LOC, two responsibilities | defer | Real but scope creep here; backlog | — |
| 3 | review-documentation | low | naming.py:38 | Missing docstring | false-positive | Obvious one-liner; agent over-eager | — |
```

- `Decision` is one of: `fix-now`, `defer`, `false-positive`.
- `Rationale` is one line.
- `Fixed-in` is filled in during Phase 3 as fixes land; empty for `defer` / `false-positive`.

### 4. `meta.json` (auto-generated in Phase 1)
Mirrors the tune scorecard convention. Records:

- `target`: `"framework"`
- `git_sha`: the SHA the audit ran against
- `agents`: the 9-name roster
- `model_versions`: per-agent model used (most are `claude-sonnet-4-6`; agentic-tier where applicable)
- `timestamp`: ISO-8601 UTC
- `work_item_count`: total subagent dispatches expected
- `results_received`: actual count (for visible drop-detection — see Error handling)

### 5. (Phase 3, optional) `apply.md`
Per-fix implementation notes accumulated as fix-now items land. Same pattern as the tune scorecards' `apply.md`. Not required for the baseline to be considered complete; useful for traceability.

## Data flow

```
1. /reviewers:audit  --target framework  --agent <a1> ... --agent <a9>
   └─> audit-prepare --target framework --agent ... (×9)
       └─> writes .framework/audit/latest/prep-manifest.json
2. Workflow "reviewers-audit" reads manifest, fans out 9 subagents in parallel
   └─> each subagent returns structured findings JSON
3. Claude writes /tmp/reviewers-audit-results.json
4. audit-finalize --results ... --out-dir .framework/audit/latest
   └─> writes findings/, audit-report.md, meta.json into latest/
5. audit-finalize --preserve-as docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/
   └─> copies latest/ tree into dated dir
6. Human triage pass: open audit-report.md, walk findings, write triage.md
7. Commit dated dir (findings/ + audit-report.md + meta.json + triage.md)
8. Subsequent sessions: implement fix-now decisions; update Fixed-in column as fixes land
```

`--preserve-as` could be invoked as a second flag on the same `audit-finalize` call as `--out-dir`, or as a separate invocation. Spec keeps them separable for clarity; implementation can support either.

## Error handling

- **Subagent dropouts** (the documented quota-throttling pattern — see memory note `reviewers-tune-quota-throttling`). If `len(results) < expected`, re-dispatch the missing subset. The audit workflow must print the per-agent expected-vs-received count so drops are visible, not silent. `meta.json` records both `work_item_count` (expected) and `results_received` (actual).
- **Empty findings** for an agent are a valid result, recorded as `{"findings": []}`. Not an error.
- **Hallucinated findings** are caught at triage and marked `false-positive` with rationale. Not a runtime error. The 9-agent roster is chosen to minimize this — domain-mismatched agents (a11y, privacy, data-lineage, etc.) are excluded.
- **`--preserve-as` target collision**: refuse without `--force`; print the conflicting path.
- **`audit-prepare` auto-detect failure**: already handled by the inherited logic from `eval-prepare`. We pass `--target framework` explicitly to be defensive.
- **Stale `/tmp/pytest-of-chris/*`** (the documented pattern — see memory note `reviewers-tune-pytest-tmp-accumulation`): if any pre-audit test invocation produces mass spurious failures, clean `/tmp/pytest-of-chris/*` first. Not directly an audit failure mode but adjacent — flagged here so it's not rediscovered.

## Testing

The new tooling needs tests; the audit run itself doesn't (it's an event, not a feature).

- **Command split**: existing tests of `eval-prepare`/`eval-finalize` get migrated to the appropriate new command (`tune-prepare`, `audit-prepare`, `gate-prepare` etc.). Each per-mode branch's behavior should already be under test; the migration is mostly renaming. New tests cover: `--mode` is gone (invoking the old surface fails with a clear error or — if we delete the old commands cleanly — typer's standard unknown-command message).
- **`audit-prepare` repeatable `--agent`** — unit test: multiple `--agent` flags produce a manifest with the union of work-items, deduplicated; unknown agent name errors clearly.
- **`audit-finalize --preserve-as`** — unit tests: copies the tree into a fresh target dir; refuses to overwrite a non-empty target; accepts `--force` to overwrite.

No test for the actual baseline contents — that's the artifact, not the tooling.

## Definition of done

The audit **baseline** is done when:

1. The dated dir exists under `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/` and contains `findings/`, `audit-report.md`, `meta.json`, and a fully-populated `triage.md`.
2. The dated dir is committed to `master`.
3. Every `fix-now` row in `triage.md` has either (a) been implemented and the row updated with the fixing commit SHA in `Fixed-in`, OR (b) a tracking task created that points back to the row.

Phase 3 fix implementation is outside the scope of this spec; it'll be planned per-finding via writing-plans once findings are known.

## Open questions

None.

## Out-of-band notes

- This is plumbing for a milestone activity; the new tooling (`--agent` repeatable, `--preserve-as`) is intentionally minimal and reusable for any future targeted audit (e.g. re-audit just `security` + `dependency` after a refactor) without overwriting state mid-flight.
- The same baseline pattern will apply to the **template audit** later (target `project` against a representative rendered variant), but that's a separate spec because the mechanics differ (render first, choose variants).

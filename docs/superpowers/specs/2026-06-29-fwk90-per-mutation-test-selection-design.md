# FWK90 — per-mutation test selection (inner-loop accelerator)

> **Date:** 2026-06-29 · **Status:** approved (brainstorm) · **Author:** Chris (with Claude)
> **Stream:** exp-2 worktree-stream **S3**, second sub-PLAN (after FWK70). Carving spec:
> `docs/superpowers/specs/2026-06-29-second-worktree-parallel-experiment-carving-design.md`.

## Purpose & success

During a worktree's tight inner loop (edit → run → edit), run only the tests a code mutation
*affects* instead of the whole fast tier — so per-change feedback stays fast. This is **distinct
from FWK77's commit-vs-merge tiers** (those pick *when* to run fast vs full; this picks *which*
tests inside a single interim run) and **orthogonal to FWK76's parallelism** (scope × shard).

**Success:** a `task test:affected` that, given the current working-tree mutation, runs a correct
*subset* of the fast tier for the common cases, and — critically — **widens** for the one coupling
class that static analysis cannot see: a template edit that drifts an eval fixture's hand-authored
`change.patch` anchor (the FWK100/A1 motivating bug — invisible to the render/integrity set, caught
only by the full PR `gate` via `tests/review/test_evals.py::test_every_fixture_realizes`).

**The governing safety property:** selection only ever *narrows from a known-safe map*. Any path it
does not understand widens to the **full fast tier**. It can never silently drop coverage. It is an
**interim accelerator only** — `task test:fast` remains the commit gate (continuity with
`[[gate-cadence-for-framework-slices]]` + the FWK96/97 tiers).

## Why not off-the-shelf

`pytest-testmon` (import-graph coverage) and `pytest-picked` (changed test files only) were
rejected: **both miss the motivating bug.** The template→fixture link is a *data anchor* — a
hand-authored unified diff anchored to template line numbers (`[[eval-fixtures-coupled-to-template]]`)
— not a Python import, so no import-graph tool sees it. Either would need the widen rule bolted on
anyway, plus a new dependency. The valuable, novel core here is that "which fixtures anchor on
template file F" is **derivable** by parsing the `change.patch` headers — so the dangerous coupling
is *computed*, not a hand-maintained list that drifts.

## Architecture — a pure selector + a thin runner

`scripts/affected_tests.py` (fits the existing `scripts/` helper pattern — `dogfood_e2e.py`,
`doctor.sh`, `worktree.py` — **not** the thin Copier CLI):

- **`select_targets(changed_paths: list[str]) -> Selection`** — a **pure function**, fully
  unit-tested. Maps a set of changed repo-relative paths to either an explicit pytest target list or
  the sentinel `FULL`. No I/O beyond reading the on-disk fixture `change.patch` set (for the derived
  map); deterministic and hermetic for the framework venv.
- **`main()`** — thin: gathers the working-tree mutation (`git diff --name-only HEAD` + untracked via
  `git ls-files --others --exclude-standard`, so a brand-new fixture/file is seen —
  `[[new-file-eval-fixtures-empty-diff]]`), or an explicit `[FILE...]` argv override (for tests and
  scripting); prints a **loud interim-only banner**; runs `pytest -n auto <targets>` within the
  **fast-tier universe** (the two docker acceptance files stay `--ignore`d, matching `test:fast`),
  or the full fast tier on `FULL`; exits with pytest's own code.

**Standalone script, NOT a conftest hook** — this deliberately sidesteps the carving's flagged
S1↔S3 shared file (`tests/acceptance/conftest.py`, which FWK116 edits for the tier-3 sweep). The
predicted overlap does not materialize.

## The three selection rules (inside `select_targets`)

1. **Framework source → coarse path-area map.** A small explicit table keyed on path prefix, e.g.
   `src/framework_cli/integrity/** → tests/integrity/`, `review/** → tests/review/`,
   `runtime_coverage/** → tests/runtime_coverage/`, and the module-level files
   (`naming.py`/`copier_runner.py`/`cli.py`/`source.py`/`version_sync.py`) → their owning test
   file(s). A changed `tests/**/test_*.py` selects **itself**. Coarse on purpose (runs a whole area,
   a few extra tests) — predictable and robust beats minimal-and-fragile for an inner-loop aid.
2. **Template payload → the template guards + the derived widen.** Any `src/framework_cli/template/**`
   change selects the framework-side guards: `tests/test_copier_runner.py` + `tests/integrity/` +
   the non-docker acceptance render checks. **Plus the derived widen:** parse every
   `tests/eval/fixtures/**/change.patch`'s `+++ b/<path>` (and `--- a/<path>`) headers once to build
   `{anchored_template_path → {fixtures}}`; if a changed template path is in that map, **add
   `tests/review/test_evals.py`**. (Generated-project *unit* tests run in a different venv — out of
   scope; the banner points to the template-payload TDD loop, `[[template-payload-tdd-loop]]`.)
3. **Fail-safe.** Doc-only paths (`*.md`, `PLAN.md`, `ACTION_LOG.md`, `docs/**`) select **no tests**.
   **Any unmapped path → `FULL`.** Unknown ⇒ widen, never narrow.

A change set spanning multiple rules takes the **union** of their targets (and `FULL` is absorbing).

## Testing (TDD; framework-venv, pure path logic — no generated project)

`tests/test_affected_selection.py`, written test-first:

- framework module edit → its mapped area, nothing unrelated;
- template file **anchored by a fixture** → includes `tests/review/test_evals.py`;
- template file **not anchored** by any fixture → template guards but **not** `test_evals.py`;
- doc-only change → empty selection;
- unmapped/unknown path → `FULL`;
- multi-path change → union;
- **meta-guard:** the `change.patch` parser resolves at least one real on-disk fixture → it cannot
  silently rot to an empty map (which would defeat the entire widen).

These are pure-Python path-logic tests → they run in the framework venv and the fast tier (no
`/tmp/work` render, no docker).

## Surface

- New: `scripts/affected_tests.py`, `tests/test_affected_selection.py`.
- `Taskfile.yml`: add `test:affected`; and drop the now-stale "carries FWK70's known-failing
  acceptance test" note from `test:full`'s desc (FWK70 landed earlier in this stream).
- Docs: a CLAUDE.md "How we build here" note (interim accelerator vs the `test:fast` commit gate) +
  a short `docs/maintenance/` entry on the selection rules + how to extend the path-area map.

## Findings to record at merge

1. The carving predicted `tests/acceptance/conftest.py` as a shared S1↔S3 file; the standalone-script
   choice **avoids it entirely** — the predicted overlap is a non-event, not a merge conflict to
   coordinate.
2. Off-the-shelf `testmon`/`picked` were rejected (both miss the data-anchor coupling) — recorded so
   the next person doesn't reach for them.

## Out of scope (YAGNI)

Import-graph analysis; generated-project unit-test selection (different venv — the template-payload
loop owns it); wiring selection into the commit-gate hook (the convention + loud banner suffice);
caching the parsed fixture map (the parse is cheap, run once per invocation).

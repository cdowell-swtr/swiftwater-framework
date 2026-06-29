# Per-mutation test selection — the inner-loop accelerator

> `FWK90` (exp-2 stream S3). Distinct from the fast/full tiers (`FWK96`, which pick *when* to
> run fast vs full) and from `pytest-xdist` parallelism (`FWK76`, which picks *how many* at once):
> this picks *which* tests to run inside a single interim run. Design:
> `docs/superpowers/specs/2026-06-29-fwk90-per-mutation-test-selection-design.md`. The logic is
> `scripts/affected_tests.py`; its contract is machine-checked by `tests/test_affected_selection.py`.

## What it is — and is NOT

`task test:affected` runs only the fast-tier tests the **current working-tree mutation** affects,
to keep the tight edit→run→edit loop fast. It is an **interim accelerator only.**

**It is NOT a commit gate.** `task test:fast` stays the gate before every commit. The accelerator
exists to shorten the loop *between* commits, not to replace the gate. The one safety property that
makes that safe: **selection only ever narrows from a known-safe map — any path it does not
understand widens to the full fast tier.** It can never silently drop coverage; the worst case is
that it runs *more* than the minimal set.

## How a change set maps to tests

The mutation is `git diff --name-only HEAD` + untracked files (so a brand-new fixture or test is
seen). Each changed path is classified; the run is the **union** of all targets, and `FULL` (the
whole fast tier) is **absorbing** — one unmapped path forces it.

| Changed path | Selected tests |
|---|---|
| `src/framework_cli/integrity/**` | `tests/integrity/` |
| `src/framework_cli/review/**` (incl. `agents/*.md` prompts) | `tests/review/` |
| `src/framework_cli/runtime_coverage/**` | `tests/runtime_coverage/` |
| top-level `src/framework_cli/<stem>.py` | `tests/test_<stem>.py` if it exists, else **FULL** |
| `src/framework_cli/template/**` | the **template guards** (below) + a *derived* `tests/review/test_evals.py` if a touched template file is fixture-anchored |
| `tests/**/test_*.py` | that file itself |
| `*.md`, `docs/**`, `PLAN.md`, `ACTION_LOG.md` | nothing |
| anything else | **FULL** |

**Template guards:** `tests/integrity/`, `tests/runtime_coverage/`, `tests/test_copier_runner.py`,
`tests/test_template_map.py` — the fast-tier subset that catches render / integrity / completeness
drift. (Generated-project *unit* tests run in a different venv and are out of scope here — the
template-payload TDD loop owns them; `[[template-payload-tdd-loop]]`.)

## The derived template→fixture widen (the load-bearing bit)

A template edit can silently drift an eval fixture's hand-authored `change.patch` anchor — invisible
to the render/integrity set, caught only by `tests/review/test_evals.py::test_every_fixture_realizes`
(the `FWK100` motivating bug). Import-graph tools (`testmon`/`picked`) cannot see this — the link is
a *data anchor*, not a Python import — which is why neither was adopted.

`fixture_anchored_paths()` parses every `tests/eval/fixtures/**/change.patch`'s `+++ b/` / `--- a/`
headers into the set of paths fixtures anchor on. A changed template path matches if **either** its
raw path **or** its rendered normalization (strip the `src/framework_cli/template/` prefix and a
`.jinja` suffix; resolve `{{package_name}}` → the fixtures' package `demo`) is in that set. A match
pulls `test_evals.py` into the run. The match is biased toward over-inclusion (a false positive just
runs `test_evals` needlessly — safe; a false negative is caught at the `task test:fast` gate anyway).

## Extending the map

- **New top-level CLI module** with a 1:1 `tests/test_<stem>.py`: works automatically.
- **New subpackage** under `src/framework_cli/`: add a `_AREA_MAP` entry in
  `scripts/affected_tests.py` (else it correctly fails safe to FULL).
- The `tests/test_affected_selection.py` **meta-guard** asserts the fixture-anchor parser keeps
  resolving real anchors — if a refactor breaks it, that test reddens rather than the widen silently
  going dark.

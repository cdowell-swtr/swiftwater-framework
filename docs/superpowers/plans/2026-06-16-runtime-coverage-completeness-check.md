# Runtime-Coverage Completeness Check (FWK29) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **Review-model policy** (CLAUDE.md): implementers → Sonnet; spec-compliance review → Sonnet; **code-quality review → Opus**; branch-end whole-branch review → Opus. Pass `model` per role explicitly.
>
> **Framework test-only — NO release.** Everything lands under `tests/`; no `src/framework_cli` wheel change, no template payload change. Branch `fwk29-coverage-completeness-check` (already created off master).

**Goal:** A `gate`-tier test that enumerates the template's provisioned operational surfaces from an all-batteries render and asserts each is classified EXERCISED | EXEMPT | KNOWN_GAP in a typed registry — a closed-world ratchet that fails when a new surface is added unclassified.

**Architecture:** Three test-only modules under `tests/runtime_coverage/`: `enumerate.py` (six mechanical rules → canonical surface keys), `registry.py` (typed classification table), `test_completeness.py` (set-equality + reference-integrity over the two). Seeding the registry is the rigorous re-rank; reconciling the FWK18 inventory closes the loop.

**Tech Stack:** pytest, PyYAML (already a dep), `framework_cli.copier_runner.render_project`, `framework_cli.batteries.{battery_names,resolve}`. Spec: `docs/superpowers/specs/2026-06-16-runtime-coverage-completeness-check-design.md`.

---

## File Structure

- Create: `tests/runtime_coverage/__init__.py` — package marker.
- Create: `tests/runtime_coverage/enumerate.py` — the six enumeration rules; pure functions over a rendered project root.
- Create: `tests/runtime_coverage/registry.py` — `Status` enum, `SurfaceClass` dataclass, `REGISTRY` tuple, `registry_keys()`.
- Create: `tests/runtime_coverage/test_enumerate.py` — unit tests that the rules extract expected keys.
- Create: `tests/runtime_coverage/test_completeness.py` — the four completeness assertions over the all-batteries render.
- Modify: `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md` — inventory reconciliation (Task 4).
- Modify: `PLAN.md`, `ACTION_LOG.md` (FWK29 → Done).

`enumerate` is a Python builtin — the **module** is named `enumerate.py` but is only ever imported as `from tests.runtime_coverage import enumerate as surf_enum` / `from .enumerate import enumerate_surfaces`; never shadow the builtin in a namespace where it's used. (Importing a submodule named `enumerate` does not rebind the builtin.)

---

## Task 1: Enumeration rules + their unit tests

**Files:**
- Create: `tests/runtime_coverage/__init__.py`
- Create: `tests/runtime_coverage/enumerate.py`
- Create: `tests/runtime_coverage/test_enumerate.py`

- [ ] **Step 1: Create the package marker.** `tests/runtime_coverage/__init__.py` — empty file.

- [ ] **Step 2: Write the failing test** `tests/runtime_coverage/test_enumerate.py`:

```python
"""Unit tests for the six enumeration rules (FWK29)."""

import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project

from .enumerate import enumerate_surfaces

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


@pytest.fixture(scope="module")
def maximal(tmp_path_factory):
    """An all-batteries (dependency-resolved) render — the maximal operational surface."""
    dest = tmp_path_factory.mktemp("cov-enum") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


def test_enumerate_finds_each_rule_class(maximal):
    keys = enumerate_surfaces(maximal)
    # One concrete representative per rule must be present in an all-batteries render.
    expected = {
        "overlay:prod.yml",                     # compose overlay rule
        "service:dev.yml:redis",                # compose service rule (redis battery)
        "docker-stage:Dockerfile:runtime",      # Dockerfile stage rule
        "script:scripts/entrypoint.sh",         # operational script rule
        "job:ci.yml:gate",                      # workflow job rule
        "hook:gitleaks",                        # pre-commit hook rule
    }
    missing = expected - keys
    assert not missing, f"enumeration missed expected keys: {sorted(missing)}"


def test_enumerate_keys_are_unique_strings(maximal):
    keys = enumerate_surfaces(maximal)
    assert keys, "enumeration returned no surfaces"
    assert all(isinstance(k, str) and ":" in k for k in keys)
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `TMPDIR=/var/tmp uv run pytest tests/runtime_coverage/test_enumerate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.runtime_coverage.enumerate'` (or ImportError for `enumerate_surfaces`).

- [ ] **Step 4: Implement** `tests/runtime_coverage/enumerate.py`:

```python
"""Enumeration rules for FWK29 — extract canonical operational-surface keys from a
rendered project tree. Closed-world: only the surface classes with a rule here are
enumerated; in-app code paths are deliberately NOT covered (see registry.py docstring).
"""

import re
from pathlib import Path

import yaml

_COMPOSE_DIR = Path("infra/compose")
_DOCKER_DIR = Path("infra/docker")
_SCRIPT_DIRS = (Path("scripts"), Path("infra/deploy"))
_WORKFLOWS_DIR = Path(".github/workflows")
_PRECOMMIT = Path(".pre-commit-config.yaml")
_CLAUDE_HOOKS_DIR = Path(".claude/hooks")

_FROM_AS = re.compile(r"^FROM\s+\S+\s+AS\s+(\S+)", re.MULTILINE | re.IGNORECASE)


def _overlays(root: Path) -> set[str]:
    d = root / _COMPOSE_DIR
    return {f"overlay:{p.name}" for p in d.glob("*.yml")} if d.is_dir() else set()


def _services(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _COMPOSE_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*.yml"):
        data = yaml.safe_load(p.read_text()) or {}
        for svc in (data.get("services") or {}):
            keys.add(f"service:{p.name}:{svc}")
    return keys


def _docker_stages(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _DOCKER_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*Dockerfile*"):
        for stage in _FROM_AS.findall(p.read_text()):
            keys.add(f"docker-stage:{p.name}:{stage}")
    return keys


def _scripts(root: Path) -> set[str]:
    keys: set[str] = set()
    for base in _SCRIPT_DIRS:
        d = root / base
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in {".sh", ".py"}:
                keys.add(f"script:{p.relative_to(root).as_posix()}")
    return keys


def _workflow_jobs(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _WORKFLOWS_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*.yml"):
        data = yaml.safe_load(p.read_text()) or {}
        for job in (data.get("jobs") or {}):
            keys.add(f"job:{p.name}:{job}")
    return keys


def _hooks(root: Path) -> set[str]:
    keys: set[str] = set()
    pc = root / _PRECOMMIT
    if pc.is_file():
        data = yaml.safe_load(pc.read_text()) or {}
        for repo in (data.get("repos") or []):
            for hook in (repo.get("hooks") or []):
                hook_id = hook.get("id")
                if hook_id:
                    keys.add(f"hook:{hook_id}")
    hd = root / _CLAUDE_HOOKS_DIR
    if hd.is_dir():
        for p in hd.glob("*"):
            if p.is_file():
                keys.add(f"hook:.claude:{p.name}")
    return keys


def enumerate_surfaces(root: Path) -> set[str]:
    """All canonical operational-surface keys in the rendered project at ``root``."""
    return (
        _overlays(root)
        | _services(root)
        | _docker_stages(root)
        | _scripts(root)
        | _workflow_jobs(root)
        | _hooks(root)
    )
```

- [ ] **Step 5: Run it to confirm it passes**

Run: `TMPDIR=/var/tmp uv run pytest tests/runtime_coverage/test_enumerate.py -q`
Expected: PASS (2 passed). If `test_enumerate_finds_each_rule_class` fails on a specific key, print the full key set (`-s` + a temp `print(sorted(keys))`) and correct the *expected* representative to match the real rendered name — do NOT loosen the rule. Likely adjustments: the redis service may live under a different overlay (try `service:services.yml:redis`) or the gate job name may differ — read the rendered `infra/compose/dev.yml` / `.github/workflows/ci.yml` and use the real names.

- [ ] **Step 6: Confirm the all-batteries render itself succeeds.** If `render_project(... resolve(battery_names()))` raises (mutually-incompatible batteries), fall back to the render-matrix "full" set: import and render the same battery list the matrix's `full` combo uses (see `tests/` render-matrix fixtures / `render-matrix.yml`), and note the substitution in a code comment. (Expected: all batteries co-render — `test_rendered_all_extensions_chain_passes` already combines the extension batteries.)

- [ ] **Step 7: Lint + commit**

Run: `uv run ruff check tests/runtime_coverage/ && uv run ruff format --check tests/runtime_coverage/`
```bash
git add tests/runtime_coverage/__init__.py tests/runtime_coverage/enumerate.py tests/runtime_coverage/test_enumerate.py PLAN.md ACTION_LOG.md
```
then separately: `git commit -m "test(fwk29): operational-surface enumeration rules"` (tick a PLAN sub-item / add an ACTION_LOG note first so the commit-gate passes).

---

## Task 2: Registry types + the completeness test (red)

**Files:**
- Create: `tests/runtime_coverage/registry.py`
- Create: `tests/runtime_coverage/test_completeness.py`

> The completeness test goes **red** here (empty registry → every surface unclassified). It is made green in Task 3 by seeding the registry, and the two are committed together (a red `gate` test must never be committed).

- [ ] **Step 1: Implement the registry scaffold** `tests/runtime_coverage/registry.py`:

```python
"""FWK29 classification registry — the closed-world ratchet's data.

Every operational surface that `enumerate.py` finds must appear here exactly once,
classified as EXERCISED (a test drives it — evidence names the test function), EXEMPT
(intentionally undriven — evidence is the reason), or KNOWN_GAP (a real, tracked gap —
evidence is "FWK<N> ...").

OUT OF SCOPE (by design): in-app code-path surfaces — the create_app/lifespan bootstrap,
DB engine/pool lifecycle, per-battery live routes, worker tracing. They are not
mechanically enumerable and are owned by the FWK30 open-world reviewer, which defers to
THIS registry (treats anything classified here as handled).
"""

import enum
from dataclasses import dataclass


class Status(enum.Enum):
    EXERCISED = "exercised"
    EXEMPT = "exempt"
    KNOWN_GAP = "known_gap"


@dataclass(frozen=True)
class SurfaceClass:
    key: str  # canonical enumeration key, e.g. "service:dev.yml:worker"
    provisioned_at: str  # "infra/compose/dev.yml.jinja:131-162"
    status: Status
    evidence: str  # EXERCISED: test fn name | EXEMPT: reason | KNOWN_GAP: "FWK<N> ..."


REGISTRY: tuple[SurfaceClass, ...] = ()


def registry_keys() -> set[str]:
    return {entry.key for entry in REGISTRY}
```

- [ ] **Step 2: Write the completeness test** `tests/runtime_coverage/test_completeness.py`:

```python
"""FWK29 — the closed-world coverage-completeness ratchet."""

import re
from pathlib import Path

import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project

from .enumerate import enumerate_surfaces
from .registry import REGISTRY, Status, registry_keys

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}
_TESTS_ROOT = Path(__file__).resolve().parents[1]  # the repo's tests/ dir
_TEST_FN = re.compile(r"^def (test_\w+)", re.MULTILINE)
_FWK_REF = re.compile(r"^FWK\d+\b")


@pytest.fixture(scope="module")
def maximal(tmp_path_factory):
    dest = tmp_path_factory.mktemp("cov-complete") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


def _all_test_function_names() -> set[str]:
    names: set[str] = set()
    for p in _TESTS_ROOT.rglob("test_*.py"):
        names |= set(_TEST_FN.findall(p.read_text()))
    return names


def test_every_surface_is_classified(maximal):
    enumerated = enumerate_surfaces(maximal)
    classified = registry_keys()
    unclassified = enumerated - classified
    assert not unclassified, (
        "Unclassified operational surface(s) — classify each in "
        "tests/runtime_coverage/registry.py as EXERCISED / EXEMPT / KNOWN_GAP:\n"
        + "\n".join(f"  - {k}" for k in sorted(unclassified))
    )


def test_no_stale_registry_entries(maximal):
    stale = registry_keys() - enumerate_surfaces(maximal)
    assert not stale, (
        "Stale registry entries (surface no longer rendered) — remove from registry.py:\n"
        + "\n".join(f"  - {k}" for k in sorted(stale))
    )


def test_registry_keys_are_unique():
    keys = [e.key for e in REGISTRY]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"duplicate registry keys: {dupes}"


def test_exercised_entries_name_an_existing_test():
    names = _all_test_function_names()
    bad = [
        e.key for e in REGISTRY if e.status is Status.EXERCISED and e.evidence not in names
    ]
    assert not bad, (
        "EXERCISED entries whose evidence is not an existing test function name "
        f"(registry rot): {bad}"
    )


def test_known_gap_entries_link_a_task():
    bad = [
        e.key
        for e in REGISTRY
        if e.status is Status.KNOWN_GAP and not _FWK_REF.match(e.evidence)
    ]
    assert not bad, f"KNOWN_GAP entries whose evidence does not start 'FWK<N>': {bad}"


def test_exempt_entries_have_a_reason():
    bad = [
        e.key for e in REGISTRY if e.status is Status.EXEMPT and not e.evidence.strip()
    ]
    assert not bad, f"EXEMPT entries with an empty reason: {bad}"
```

- [ ] **Step 3: Run it to confirm it fails (red as expected)**

Run: `TMPDIR=/var/tmp uv run pytest tests/runtime_coverage/test_completeness.py -q`
Expected: `test_every_surface_is_classified` FAILS, listing the full set of unclassified keys (~50–60). The other tests pass (empty registry). **Capture that printed key list** — it is the exact work-list for Task 3. Do not commit yet.

---

## Task 3: Seed the registry (the re-rank) → green

**Files:**
- Modify: `tests/runtime_coverage/registry.py` (populate `REGISTRY`).

> This is the rigorous per-surface classification. Method: for each unclassified key from Task 2 Step 3, decide its status with evidence. The classification of the deploy/compose/build surfaces is already determined by the FWK18 inventory + its 2026-06-16 deploy-model Correction + the "Overturned" list — reuse those verdicts. For anything not in the inventory (e.g. individual workflow jobs, pre-commit hooks), grep `tests/` to decide.

- [ ] **Step 1: Seed the inventory-derived entries.** Add these to `REGISTRY` (verbatim verdicts from the FWK18 inventory; test names verified to exist). This is the canonical pattern — extend it for every remaining key:

```python
REGISTRY: tuple[SurfaceClass, ...] = (
    # --- Compose overlays --------------------------------------------------------
    SurfaceClass(
        "overlay:prod.yml", "infra/compose/prod.yml.jinja:3-52", Status.EXEMPT,
        "config-validated only; consumer-implemented deploy target — app-host.yml is the "
        "shipped overlay (deploy-model Correction 2026-06-16)",
    ),
    SurfaceClass(
        "overlay:staging.yml", "infra/compose/staging.yml.jinja:4-53", Status.KNOWN_GAP,
        "FWK19 — add compose-config merge-validation (parity with prod.yml); no live bring-up",
    ),
    SurfaceClass(
        "overlay:app-host.yml", "infra/compose/app-host.yml.jinja:1", Status.EXERCISED,
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    SurfaceClass(
        "overlay:test.yml", "infra/compose/test.yml.jinja:5-41", Status.KNOWN_GAP,
        "FWK19 — bring up via task test:stack; assert tmpfs ephemeral-DB reset",
    ),
    # --- Compose services --------------------------------------------------------
    SurfaceClass(
        "service:dev.yml:redis", "infra/compose/dev.yml.jinja", Status.EXERCISED,
        "test_rendered_workers_dev_stack_leaves_no_root_owned_files",
    ),
    SurfaceClass(
        "service:dev.yml:worker", "infra/compose/dev.yml.jinja:131-162", Status.KNOWN_GAP,
        "FWK20 — live broker->worker->DLQ; tests run Celery eager",
    ),
    SurfaceClass(
        "service:dev.yml:beat", "infra/compose/dev.yml.jinja:164-184", Status.KNOWN_GAP,
        "FWK20 — beat scheduler not live-exercised",
    ),
    # --- Dockerfile stages -------------------------------------------------------
    SurfaceClass(
        "docker-stage:Dockerfile:builder", "infra/docker/Dockerfile.jinja:5-11",
        Status.EXERCISED, "test_rendered_claudesubscriptioncli_docker_builder_stage_builds",
    ),
    SurfaceClass(
        "docker-stage:Dockerfile:runtime", "infra/docker/Dockerfile.jinja:24-34",
        Status.EXERCISED, "test_rendered_project_dev_lite_stack_serves_health",
    ),
    # --- Operational scripts -----------------------------------------------------
    SurfaceClass(
        "script:scripts/entrypoint.sh", "scripts/entrypoint.sh", Status.EXERCISED,
        "test_rendered_project_dev_stack_serves_seeded_items",
    ),
    # ... continue for EVERY remaining enumerated key ...
)
```

- [ ] **Step 2: Classify every remaining key by the rubric.** For each key still reported unclassified, in order: (a) is it an FWK18 inventory entry? use that verdict; (b) else grep `tests/` for a test that drives it → EXERCISED (name the test fn); (c) else is it intentionally undriven (a `_todo` seam, a consumer-implemented surface, a GitHub-platform feature like dependabot)? → EXEMPT with the reason; (d) else → KNOWN_GAP with the owning FWK id (use the inventory's follow-on grouping: FWK19 overlays/validation, FWK20 workers/beat, FWK21 battery Docker runtime, FWK23 obs, FWK24 routes, FWK25 Taskfile, FWK26 dev-loop, FWK27 hooks, FWK28 seams). Re-run after each batch:

Run: `TMPDIR=/var/tmp uv run pytest tests/runtime_coverage/test_completeness.py -q`
Iterate until `test_every_surface_is_classified` passes. The failure message lists exactly what's still unclassified each run.

- [ ] **Step 3: Confirm all six completeness tests pass**

Run: `TMPDIR=/var/tmp uv run pytest tests/runtime_coverage/ -q`
Expected: all pass (enumerate + completeness). If `test_exercised_entries_name_an_existing_test` fails, the named test fn is wrong/renamed — grep `tests/` for the real name and fix the evidence (do not downgrade to KNOWN_GAP to dodge it unless the surface genuinely isn't tested).

- [ ] **Step 4: Lint + commit Tasks 2+3 together**

Run: `uv run ruff check tests/runtime_coverage/ && uv run ruff format --check tests/runtime_coverage/`
```bash
git add tests/runtime_coverage/registry.py tests/runtime_coverage/test_completeness.py PLAN.md ACTION_LOG.md
```
then separately: `git commit -m "test(fwk29): coverage-completeness check + seeded classification registry"`

---

## Task 4: Reconcile the FWK18 inventory + finalize

**Files:**
- Modify: `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`
- Modify: `PLAN.md`, `ACTION_LOG.md`

- [ ] **Step 1: Reconcile the inventory.** While seeding (Task 3), note every key whose classification *disagreed* with the FWK18 inventory (a "gap" found already-exercised, or a new exempt seam). For each, add a one-line correction to the inventory's "Correction" section (or a new `### Correction (2026-06-16b): registry-seeding reconciliation` subsection) so the static inventory and the executable registry agree. If none disagreed, state that explicitly in the new subsection.

- [ ] **Step 2: Record the registry as the inventory's successor.** Add a sentence near the top of the inventory pointing to `tests/runtime_coverage/registry.py` as the now-authoritative, always-current view; the inventory remains the prose rationale.

- [ ] **Step 3: Full gate.** Confirm no wider breakage:
Run: `TMPDIR=/var/tmp uv run pytest -q tests/runtime_coverage/ && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: green. (`mypy src` is unaffected — the new code is under `tests/`. The full suite isn't required for a tests/-only addition, but the new dir + lint/format must be clean; run the broader suite if the all-batteries render fixture is shared elsewhere.)

- [ ] **Step 4: PLAN/ACTION_LOG.** Move FWK29 → Done with the final classified count (N exercised / M exempt / K known-gap); append an ACTION_LOG completion entry noting any inventory reconciliations. Commit (stage PLAN/ACTION_LOG + the inventory edit; separate `add` then `commit`).

- [ ] **Step 5: Finish the branch** ([[finishing-a-development-branch]]): push `fwk29-coverage-completeness-check`, open one PR, confirm `gate`/`build`/`render-complete` green (the new test runs in `gate`), squash-merge. **No tag / no release** (tests/-only). Grep `master` post-merge for `tests/runtime_coverage/registry.py` ([[verify-master-content-after-pr-merge]]). Then FWK30 (the reviewer) is brainstormed against the now-existing registry.

---

## Self-Review (completed by plan author)

- **Spec coverage:** registry (Task 2 — types + three statuses) · enumeration rules / closed-world boundary (Task 1, with in-app-code-paths documented OUT in registry.py docstring) · the check / set-equality + reference-integrity (Task 2 test_completeness — six assertions) · seeding = re-rank (Task 3) · inventory reconciliation / loop-closing (Task 4 Steps 1–2) · FWK30 seam (registry docstring) · `gate`-tier, no docker (render+parse only) · test-only / no release (header + Task 4 Step 5). All spec sections map to a task.
- **Status model:** EXERCISED/EXEMPT/KNOWN_GAP consistent across registry.py, the three well-formedness tests, and the seeding rubric. Evidence contract consistent: EXERCISED=test-fn-name (checked against `_all_test_function_names`), KNOWN_GAP=`^FWK\d+`, EXEMPT=non-empty.
- **Name consistency:** `enumerate_surfaces`, `registry_keys`, `REGISTRY`, `SurfaceClass`, `Status` used identically in every task. `_BASE` render dict matches `test_obs_completeness`'s shape. Module `enumerate.py` imported via `from .enumerate import …` (builtin-shadow note in File Structure).
- **No placeholders:** all module code is complete; Task 3's seeding shows the canonical entry pattern + ~10 real worked entries + an explicit rubric for the rest (a bounded data-entry task, not a TODO). The one runtime unknown (exact rendered service/job names) is handled by Task 1 Step 5's "print + correct the representative" instruction.
- **Risk flagged:** all-batteries co-render (Task 1 Step 6 fallback) and rendered-name drift (Task 1 Step 5) are the two execution-time unknowns, each with a concrete remedy.

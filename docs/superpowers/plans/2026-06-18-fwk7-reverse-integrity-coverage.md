# FWK7 — Reverse Integrity-Coverage Check + Battery-Infra Classification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the one-directional gap in the integrity classification so every framework-infra file under `infra/`, `scripts/`, `.github/workflows/` is classified, by adding a battery-gated lock mechanism and a standing `gate`-tier reverse-coverage check.

**Architecture:** Add two new classification categories to `src/framework_cli/integrity/classes.py` — `BATTERY_LOCKED` (path → gating batteries; checksummed only in projects whose batteries activate it) and `EXEMPT` (placeholders with no content to checksum). `rules()` grows an optional `batteries` parameter (empty default = unchanged baseline); `build_manifest()` feeds it the project's own `read_batteries()`. A pure `integrity/coverage.py` helper plus a `gate`-tier `tests/integrity/test_coverage.py` assert that an all-batteries render has zero unclassified infra files, with anti-stale and under-lock guards.

**Tech Stack:** Python 3.12, `pytest`, Copier (rendering), `pathspec`, `pyyaml`. Tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-06-18-fwk7-reverse-integrity-coverage-design.md`

**Execution model (per CLAUDE.md / [[subagent-review-model-pattern]]):** implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; code-quality review → **Opus**; branch-end whole-branch review → **Opus**. Pass `model` explicitly per role. TDD per task. Branch: `fwk7-reverse-integrity-coverage` (already created; the spec commit is its first commit).

**Commit-gate note:** a `PreToolUse` hook blocks `git commit` until `PLAN.md` or `ACTION_LOG.md` is staged, and it fires on any Bash command where `git` and `commit` co-occur. Stage `git add` and run `git commit` as **separate** Bash calls (chaining trips the hook before `add` runs). Keep the word "commit" out of Bash tool *descriptions*. Each task's commit step stages a one-line `ACTION_LOG.md` note alongside the code.

---

## File Map

- **Modify** `src/framework_cli/integrity/classes.py` — add 5 paths to `LOCKED_TRACKED`; add `BATTERY_LOCKED` dict + `EXEMPT` tuple; add `batteries` param to `rules()`; update the header comment. (Tasks 1, 2.)
- **Modify** `src/framework_cli/integrity/generate.py` — `build_manifest()` reads `read_batteries(project)` and passes it to `rules()`. (Task 3.)
- **Create** `src/framework_cli/integrity/coverage.py` — pure surface-scan + classification-union helper. (Task 4.)
- **Create** `tests/integrity/test_coverage.py` — the reverse-coverage check (forward + anti-stale + genuinely-gated + per-gate accuracy). (Tasks 4, 5, 6.)
- **Modify** `tests/integrity/test_classes.py` — narrow classification asserts for the new entries. (Tasks 1, 2.)
- **Modify** `PLAN.md` / `ACTION_LOG.md` — state tracking each commit; final close in Task 7.

No template-payload files change. No FWK29 registry change (Task 7 confirms `test_every_surface_is_classified` stays green).

---

## Task 1: Reclassify the 5 baseline escapees + add `EXEMPT`

The 5 files render in a **baseline** project, so they satisfy `LOCKED_TRACKED`'s "present in a baseline render" invariant directly. The 2 `.gitkeep` placeholders get the new `EXEMPT` category.

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_classes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integrity/test_classes.py`:

```python
def test_baseline_escapees_are_locked():
    """FWK7: framework-owned files that render in a baseline project but had escaped the
    locked registry (a PORT_OFFSET wrapper + 4 static obs configs)."""
    from framework_cli.integrity.classes import LOCKED_TRACKED

    for rel in (
        "scripts/compose.sh",
        "infra/observability/grafana/dashboards/otel-collector.json",
        "infra/observability/grafana/dashboards/prometheus.json",
        "infra/observability/prometheus/alerts/otel_collector_alerts.yml",
        "infra/observability/prometheus/alerts/prometheus_alerts.yml",
    ):
        assert rel in LOCKED_TRACKED, f"{rel} should be locked (baseline framework infra)"


def test_gitkeep_placeholders_are_exempt():
    """FWK7: empty .gitkeep dir-placeholders have no checksummable content."""
    from framework_cli.integrity.classes import EXEMPT, LOCKED_TRACKED

    for rel in ("infra/traefik/certs/.gitkeep", "infra/tls/ca/.gitkeep"):
        assert rel in EXEMPT
        assert rel not in LOCKED_TRACKED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integrity/test_classes.py::test_baseline_escapees_are_locked tests/integrity/test_classes.py::test_gitkeep_placeholders_are_exempt -v`
Expected: FAIL — `test_baseline_escapees_are_locked` asserts paths not yet in `LOCKED_TRACKED`; `test_gitkeep_placeholders_are_exempt` fails at `ImportError: cannot import name 'EXEMPT'`.

- [ ] **Step 3: Add the 5 paths to `LOCKED_TRACKED` and add `EXEMPT`**

In `src/framework_cli/integrity/classes.py`, inside `LOCKED_TRACKED`, add `scripts/compose.sh` in the `scripts/` run (alphabetical, before `scripts/coverage.sh`):

```python
    "scripts/check_migrations.py",
    "scripts/compose.sh",
    "scripts/coverage.sh",
```

Add the two static dashboards after `dashboards/postgres.json`:

```python
    "infra/observability/grafana/dashboards/slo.json",
    "infra/observability/grafana/dashboards/postgres.json",
    "infra/observability/grafana/dashboards/otel-collector.json",
    "infra/observability/grafana/dashboards/prometheus.json",
```

Add the two static alert files after `alerts/alertmanager_alerts.yml`:

```python
    "infra/observability/prometheus/alerts/slo_alerts.yml",
    "infra/observability/prometheus/alerts/postgres_alerts.yml",
    "infra/observability/prometheus/alerts/alertmanager_alerts.yml",
    "infra/observability/prometheus/alerts/otel_collector_alerts.yml",
    "infra/observability/prometheus/alerts/prometheus_alerts.yml",
```

Then add the `EXEMPT` tuple immediately **after** `INTENTIONALLY_UNLOCKED` (before `GITIGNORED_EXISTENCE`):

```python
# Framework-shipped placeholders with no checksummable content: empty .gitkeep files that only
# exist to keep an otherwise-empty directory in git. Recorded explicitly (like INTENTIONALLY_UNLOCKED)
# so the FWK7 reverse-coverage check can distinguish "deliberately uncovered" from "a framework file
# that escaped classification".
EXEMPT: tuple[str, ...] = (
    "infra/traefik/certs/.gitkeep",  # local-TLS cert dir placeholder
    "infra/tls/ca/.gitkeep",  # FWK6 CA-bundle dir placeholder
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integrity/test_classes.py -v`
Expected: PASS — the two new tests pass and the existing `test_every_locked_path_exists_in_a_rendered_project` / `test_no_locked_path_is_gitignored` still pass (the 5 additions render in baseline and are git-tracked).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: lock baseline escapees (compose.sh + static obs) + add EXEMPT"
```

---

## Task 2: Add `BATTERY_LOCKED` and the `rules(batteries=...)` parameter

`BATTERY_LOCKED` maps each battery-conditional framework file to the batteries that gate it (lock applies when **any** is active, matching the jinja `or` conditionals). `rules()` gains an optional `batteries` arg that appends locked Rules for active battery files; the empty default reproduces today's baseline-only behavior.

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_classes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integrity/test_classes.py`:

```python
def test_battery_locked_covers_the_expected_files():
    from framework_cli.integrity.classes import BATTERY_LOCKED, LOCKED_TRACKED

    # 22 battery-conditional framework files; none also in the baseline locked set.
    assert len(BATTERY_LOCKED) == 22
    for path, gate in BATTERY_LOCKED.items():
        assert path not in LOCKED_TRACKED, f"{path} is both baseline-locked and battery-locked"
        assert isinstance(gate, tuple) and gate, f"{path} needs a non-empty gate tuple"
    # spot-check a single-gate, a multi-gate, and a non-obs entry
    assert BATTERY_LOCKED["infra/observability/grafana/dashboards/redis.json"] == ("redis", "workers")
    assert BATTERY_LOCKED["infra/docker/postgres.Dockerfile"] == ("pgvector", "timescaledb", "age")
    assert BATTERY_LOCKED[".github/workflows/docs.yml"] == ("docs",)


def test_rules_default_is_baseline_only():
    from framework_cli.integrity.classes import LOCKED_TRACKED, rules

    paths = {r.path for r in rules()}
    # no battery-conditional path leaks into the default (baseline) rule set
    assert "infra/observability/grafana/dashboards/redis.json" not in paths
    assert set(LOCKED_TRACKED) <= paths


def test_rules_adds_battery_locked_for_active_batteries():
    from framework_cli.integrity.classes import rules

    redis_rule = "infra/observability/grafana/dashboards/redis.json"
    assert redis_rule in {r.path for r in rules(["redis"])}
    # shared gate: workers also activates the redis dashboards
    assert redis_rule in {r.path for r in rules(["workers"])}
    # a non-gating battery activates none of redis's files
    assert redis_rule not in {r.path for r in rules(["graphql"])}
    # every activated battery file is a locked/tracked Rule
    for r in rules(["redis"]):
        if r.path == redis_rule:
            assert r.cls == "locked" and r.tier == "tracked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integrity/test_classes.py -k "battery_locked or rules_default or rules_adds" -v`
Expected: FAIL — `ImportError: cannot import name 'BATTERY_LOCKED'` / `rules()` takes no positional argument.

- [ ] **Step 3: Add `BATTERY_LOCKED`, the `Sequence` import, and the `rules` parameter**

In `src/framework_cli/integrity/classes.py`, add the import at the top (under `from dataclasses import dataclass`):

```python
from collections.abc import Sequence
from dataclasses import dataclass
```

Add `BATTERY_LOCKED` immediately **after** `EXEMPT` (added in Task 1):

```python
# Battery-conditional framework files: locked, but present only when a gating battery is active.
# Maps the rendered path to the batteries that produce it (lock applies when ANY is active, mirroring
# the template's jinja `or` conditionals). build_manifest() enforces these per-project via the
# project's own recorded batteries, so LOCKED_TRACKED keeps its "present in a baseline render"
# invariant. Gates are transcribed directly from the conditional filenames in
# src/framework_cli/template/ (the single source of truth).
BATTERY_LOCKED: dict[str, tuple[str, ...]] = {
    "infra/observability/grafana/dashboards/agents.json": ("agents",),
    "infra/observability/prometheus/alerts/agents_alerts.yml": ("agents",),
    "infra/observability/grafana/dashboards/frontend.json": ("react",),
    "infra/observability/prometheus/alerts/frontend_alerts.yml": ("react",),
    "infra/observability/grafana/dashboards/graphql.json": ("graphql",),
    "infra/observability/prometheus/alerts/graphql_alerts.yml": ("graphql",),
    "infra/observability/grafana/dashboards/llm.json": ("llm",),
    "infra/observability/prometheus/alerts/llm_alerts.yml": ("llm",),
    "infra/observability/grafana/dashboards/mongodb.json": ("mongodb",),
    "infra/observability/prometheus/alerts/mongodb_alerts.yml": ("mongodb",),
    "infra/observability/grafana/dashboards/redis.json": ("redis", "workers"),
    "infra/observability/prometheus/alerts/redis_alerts.yml": ("redis", "workers"),
    "infra/observability/grafana/dashboards/webhooks.json": ("webhooks",),
    "infra/observability/prometheus/alerts/webhooks_alerts.yml": ("webhooks",),
    "infra/observability/grafana/dashboards/websockets.json": ("websockets",),
    "infra/observability/prometheus/alerts/websockets_alerts.yml": ("websockets",),
    "infra/observability/grafana/dashboards/workers.json": ("workers",),
    "infra/observability/prometheus/alerts/workers_alerts.yml": ("workers",),
    "infra/docker/postgres.Dockerfile": ("pgvector", "timescaledb", "age"),
    "scripts/export-graphql-schema.sh": ("graphql",),
    "scripts/pact-publish.sh": ("consumers",),
    ".github/workflows/docs.yml": ("docs",),
}
```

Replace the `rules()` function:

```python
def rules(batteries: Sequence[str] = ()) -> list[Rule]:
    """The full classification: locked + hybrid tracked files, plus gitignored/existence paths.

    `batteries` (the project's active battery set) additionally activates the matching
    BATTERY_LOCKED rules. The empty default reproduces the baseline-only rule set, so existing
    callers and the baseline render tests are unchanged.
    """
    active = set(batteries)
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    battery = [
        Rule(p, "locked", "tracked")
        for p, gate in BATTERY_LOCKED.items()
        if active.intersection(gate)
    ]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + battery + hybrid + gitignored
```

Update the module header comment (the `classes.py:13-19` block) to record that the reverse check is no longer deferred:

```python
# Coverage is closed by the FWK7 reverse-coverage check (tests/integrity/test_coverage.py): an
# all-batteries render asserts every infra-surface file is classified into exactly one of
# LOCKED_TRACKED, HYBRID_TRACKED, GITIGNORED_EXISTENCE, INTENTIONALLY_UNLOCKED, BATTERY_LOCKED, or
# EXEMPT. BATTERY_LOCKED holds framework files that exist only when a gating battery is active;
# EXEMPT holds empty placeholders with no checksummable content. A newly added framework file under
# the scanned surface roots now fails that check until it is classified here.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integrity/test_classes.py -v`
Expected: PASS (all, including the three new tests and the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: add BATTERY_LOCKED registry + battery-aware rules()"
```

---

## Task 3: Wire battery-aware locking into `build_manifest`

A real project's manifest must lock the battery files it actually has. `build_manifest()` reads the project's recorded batteries and passes them to `rules()`.

**Files:**
- Modify: `src/framework_cli/integrity/generate.py`
- Test: `tests/integrity/test_generate.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integrity/test_generate.py` (match the existing import/render style in that file; this uses `render_project` + `build_manifest` directly):

```python
def test_manifest_locks_battery_files_when_battery_active(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import build_manifest

    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": ["redis"],
        },
    )
    manifest = build_manifest(dest, "v0.0.0-test")
    paths = {e.path for e in manifest.entries}
    assert "infra/observability/grafana/dashboards/redis.json" in paths


def test_manifest_omits_battery_files_in_baseline(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import build_manifest

    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    manifest = build_manifest(dest, "v0.0.0-test")
    paths = {e.path for e in manifest.entries}
    assert "infra/observability/grafana/dashboards/redis.json" not in paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integrity/test_generate.py -k "battery_files" -v`
Expected: FAIL — `test_manifest_locks_battery_files_when_battery_active` fails (the redis path is not in the manifest, because `build_manifest` still calls `rules()` with no batteries).

- [ ] **Step 3: Read the project's batteries in `build_manifest`**

In `src/framework_cli/integrity/generate.py`, add the import:

```python
from framework_cli.integrity.classes import rules
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Entry, Manifest
from framework_cli.integrity.sections import section_sha256
from framework_cli.source import read_batteries
```

Change the loop in `build_manifest`:

```python
    spec = _gitignore_spec(project)
    entries: list[Entry] = []
    for rule in rules(read_batteries(project)):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integrity/test_generate.py -v`
Expected: PASS — battery file present with `--with redis`, absent in baseline; all pre-existing generate tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/generate.py tests/integrity/test_generate.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: build_manifest locks battery files per project batteries"
```

---

## Task 4: Pure `coverage.py` helper + the forward reverse-coverage check

The helper is unit-testable against a synthetic tree (no render). The forward check renders all batteries and asserts zero unclassified files. The all-batteries render is shared via a module-scoped fixture.

**Files:**
- Create: `src/framework_cli/integrity/coverage.py`
- Create: `tests/integrity/test_coverage.py`

- [ ] **Step 1: Write the failing helper unit tests**

Create `tests/integrity/test_coverage.py`:

```python
from pathlib import Path

import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project
from framework_cli.integrity import coverage
from framework_cli.integrity.classes import BATTERY_LOCKED, EXEMPT

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def test_infra_surface_files_scans_only_surface_roots(tmp_path):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "a.yml").write_text("x")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "b.sh").write_text("x")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "c.yml").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")  # NOT a surface root

    found = set(coverage.infra_surface_files(tmp_path))
    assert found == {"infra/a.yml", "scripts/b.sh", ".github/workflows/c.yml"}


def test_unclassified_flags_an_unknown_surface_file(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mystery.sh").write_text("x")
    assert coverage.unclassified_infra_files(tmp_path) == ["scripts/mystery.sh"]


def test_classified_paths_includes_every_category():
    classified = coverage.classified_paths()
    assert "scripts/compose.sh" in classified  # LOCKED_TRACKED
    assert "scripts/seed.py" in classified  # INTENTIONALLY_UNLOCKED
    assert "infra/observability/grafana/dashboards/redis.json" in classified  # BATTERY_LOCKED
    assert "infra/traefik/certs/.gitkeep" in classified  # EXEMPT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integrity/test_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.integrity.coverage'`.

- [ ] **Step 3: Create `coverage.py`**

Create `src/framework_cli/integrity/coverage.py`:

```python
"""FWK7 — reverse integrity-coverage check.

Forward coverage is one-directional in `classes.py` (registered paths must render). This module
adds the reverse direction: every framework-infra file under the scanned surface roots must be
classified into exactly one category, so a new framework file cannot silently escape integrity
coverage. Scope is intentionally limited to the surface roots below; widening it is a one-line
change to `_SURFACE_ROOTS` plus its own per-file audit (see the design doc's Non-goals).
"""

from __future__ import annotations

from pathlib import Path

from framework_cli.integrity.classes import (
    BATTERY_LOCKED,
    EXEMPT,
    GITIGNORED_EXISTENCE,
    HYBRID_TRACKED,
    INTENTIONALLY_UNLOCKED,
    LOCKED_TRACKED,
)

# Extensibility seam: the framework-infra directories the reverse check polices.
_SURFACE_ROOTS: tuple[str, ...] = ("infra", "scripts", ".github/workflows")


def classified_paths() -> set[str]:
    """Every path the integrity classification accounts for, across all categories."""
    return (
        set(LOCKED_TRACKED)
        | set(HYBRID_TRACKED)
        | set(GITIGNORED_EXISTENCE)
        | set(INTENTIONALLY_UNLOCKED)
        | set(BATTERY_LOCKED)
        | set(EXEMPT)
    )


def infra_surface_files(project: Path) -> list[str]:
    """Project-root-relative posix paths of every file under the scanned surface roots."""
    found: list[str] = []
    for root in _SURFACE_ROOTS:
        base = project / root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                found.append(p.relative_to(project).as_posix())
    return found


def unclassified_infra_files(project: Path) -> list[str]:
    """Surface-root files not accounted for by any classification category (sorted)."""
    return sorted(set(infra_surface_files(project)) - classified_paths())
```

- [ ] **Step 4: Run the helper unit tests**

Run: `uv run pytest tests/integrity/test_coverage.py -v`
Expected: PASS (the three helper tests).

- [ ] **Step 5: Add the forward reverse-coverage check (renders all batteries)**

Append to `tests/integrity/test_coverage.py`:

```python
@pytest.fixture(scope="module")
def all_batteries_render(tmp_path_factory):
    dest = tmp_path_factory.mktemp("fwk7-all") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


@pytest.fixture(scope="module")
def baseline_render(tmp_path_factory):
    dest = tmp_path_factory.mktemp("fwk7-base") / "demo"
    render_project(dest, {**_BASE})
    return dest


def test_no_infra_file_is_unclassified(all_batteries_render):
    unclassified = coverage.unclassified_infra_files(all_batteries_render)
    assert unclassified == [], (
        "unclassified framework-infra files (classify in integrity/classes.py — "
        f"LOCKED_TRACKED / BATTERY_LOCKED / EXEMPT / INTENTIONALLY_UNLOCKED): {unclassified}"
    )
```

- [ ] **Step 6: Run the forward check and bite-prove it**

Run: `uv run pytest tests/integrity/test_coverage.py::test_no_infra_file_is_unclassified -v`
Expected: PASS.

Bite-proof (do NOT commit this): temporarily comment out `"scripts/compose.sh"` from `LOCKED_TRACKED`, re-run — expect FAIL naming `scripts/compose.sh`. Restore it, re-run — PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/integrity/coverage.py tests/integrity/test_coverage.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: reverse-coverage check — all-infra-files-classified"
```

---

## Task 5: Anti-stale + genuinely-battery-gated guards

Mirror the existing "no stale locked entry" hygiene: every registered `BATTERY_LOCKED`/`EXEMPT` path must still render, and every `BATTERY_LOCKED` path must be genuinely battery-gated (absent from a baseline render — so a baseline file can't be mis-filed here).

**Files:**
- Test: `tests/integrity/test_coverage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integrity/test_coverage.py`:

```python
def test_battery_locked_entries_all_render_with_all_batteries(all_batteries_render):
    missing = [p for p in BATTERY_LOCKED if not (all_batteries_render / p).is_file()]
    assert missing == [], f"stale BATTERY_LOCKED entries (not rendered): {missing}"


def test_exempt_entries_all_render_with_all_batteries(all_batteries_render):
    missing = [p for p in EXEMPT if not (all_batteries_render / p).is_file()]
    assert missing == [], f"stale EXEMPT entries (not rendered): {missing}"


def test_battery_locked_entries_are_absent_in_baseline(baseline_render):
    leaked = [p for p in BATTERY_LOCKED if (baseline_render / p).is_file()]
    assert leaked == [], (
        f"BATTERY_LOCKED paths present in a baseline render (should be in LOCKED_TRACKED): {leaked}"
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/integrity/test_coverage.py -k "stale or render_with_all or absent_in_baseline" -v`
Expected: PASS — the Task 1/2 classification is correct, so all entries render with all batteries and none leak into baseline. (If `test_battery_locked_entries_are_absent_in_baseline` fails, a path was mis-filed as battery-gated when it is actually a baseline file → move it to `LOCKED_TRACKED`.)

> These tests assert the classification done in Tasks 1-2 is *consistent* — they are written after, not before, that code, because their RED state would mean a mis-classification rather than missing production code. Confirm non-vacuity by the bite-proof in Step 3.

- [ ] **Step 3: Bite-prove non-vacuity (do not commit)**

Temporarily add a fake entry `"infra/observability/grafana/dashboards/nope.json": ("redis",)` to `BATTERY_LOCKED`; run the anti-stale test — expect FAIL naming `nope.json`. Remove it; re-run — PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integrity/test_coverage.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: anti-stale + genuinely-gated guards for BATTERY_LOCKED/EXEMPT"
```

---

## Task 6: `test_battery_locked_gating_is_accurate` (the under-lock guard)

The one silent failure mode the earlier checks miss: a `BATTERY_LOCKED` entry whose gate does **not** actually match the battery that produces the file. Such a file is "classified" and renders with all batteries, but a real single-battery project would not lock it. For each distinct gate battery, render a project with only that battery and assert every file gated on it is both present and recorded in that project's manifest.

**Files:**
- Test: `tests/integrity/test_coverage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integrity/test_coverage.py`:

```python
def test_battery_locked_gating_is_accurate(tmp_path_factory):
    """For each gate battery, a project with ONLY that battery must render every file gated on it
    AND record it in the built manifest. Catches an under-broad/wrong gate (the otherwise-silent
    under-lock failure mode)."""
    from framework_cli.integrity.generate import build_manifest

    gate_batteries = sorted({b for gate in BATTERY_LOCKED.values() for b in gate})
    for battery in gate_batteries:
        dest = tmp_path_factory.mktemp(f"fwk7-gate-{battery}") / "demo"
        render_project(dest, {**_BASE, "batteries": resolve([battery])})
        manifest_paths = {e.path for e in build_manifest(dest, "v0.0.0-test").entries}
        expected = [p for p, gate in BATTERY_LOCKED.items() if battery in gate]
        for path in expected:
            assert (dest / path).is_file(), (
                f"{path} is gated on {battery!r} but did not render with only that battery — "
                "wrong gate in BATTERY_LOCKED"
            )
            assert path in manifest_paths, (
                f"{path} rendered for {battery!r} but was not locked in the manifest"
            )
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/integrity/test_coverage.py::test_battery_locked_gating_is_accurate -v`
Expected: PASS — every gate in `BATTERY_LOCKED` matches the template's actual conditional.

> Cost note: this renders once per distinct gate battery (~11 baseline+1 renders). If the gate tier drags unacceptably, the spec's approved fallback is to keep the anti-stale presence checks (Task 5) and reduce this to 2-3 representative batteries (`redis` for the multi-gate `or`, `graphql` for script+obs, `docs` for the workflow). Default is the full per-gate version.

- [ ] **Step 3: Bite-prove non-vacuity (do not commit)**

Temporarily change `".github/workflows/docs.yml": ("docs",)` to `("graphql",)`; run — expect FAIL (the workflow does not render under `--with graphql`). Restore to `("docs",)`; re-run — PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integrity/test_coverage.py ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: per-gate accuracy guard for BATTERY_LOCKED"
```

---

## Task 7: Docs, FWK29 confirmation, full gate, and state close

**Files:**
- Modify: `documentation/` integrity/upgrading doc that enumerates the managed set (locate via grep)
- Modify: `PLAN.md`, `ACTION_LOG.md`

- [ ] **Step 1: Find the doc that enumerates the managed/locked categories**

Run: `grep -rln "INTENTIONALLY_UNLOCKED\|LOCKED_TRACKED\|locked file\|managed file" documentation/ docs/ | grep -iv specs/ | grep -iv plans/`
For each hit that lists the integrity categories for a human audience, add a sentence describing `BATTERY_LOCKED` ("framework files locked only in projects whose battery activates them") and `EXEMPT` ("empty placeholders, not checksummed"). If no human-facing doc enumerates the categories, skip — the `classes.py` header comment (Task 2) is the record. Note the decision in the commit body.

- [ ] **Step 2: Confirm FWK29 stays green**

Run: `uv run pytest tests/runtime_coverage/ -v`
Expected: PASS — FWK7 adds only Python + tests (no new `scripts/*.sh`, workflow, compose service, or Dockerfile stage), so `test_every_surface_is_classified` is unaffected.

- [ ] **Step 3: Run the full offline gate**

Run:
```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (`mypy src` covers the new `coverage.py`; the `dict[str, tuple[str, ...]]` and `Sequence` annotations are explicit.)

- [ ] **Step 4: Update PLAN.md and ACTION_LOG.md**

In `PLAN.md`: move FWK7 from `Next` to `Done` with a one-paragraph summary (29 files classified: 5 baseline-locked incl. the `compose.sh` escapee, 22 battery-locked via the new `BATTERY_LOCKED` registry, 2 exempt; reverse-coverage `gate`-tier check over the `_SURFACE_ROOTS` seam; battery-aware `build_manifest`; test/integrity-infra only → no release). Append the closing `ACTION_LOG.md` entry (taxonomy: `completed`).

- [ ] **Step 5: Commit**

```bash
git add documentation PLAN.md ACTION_LOG.md
```
(separate call:)
```bash
git commit -m "FWK7: docs + close — reverse integrity-coverage check"
```

---

## Reviews (branch-end, before PR)

- [ ] **Spec-compliance review (Sonnet):** all 4 spec Goals met; the 29-file appendix split is implemented exactly; the `_SURFACE_ROOTS` seam and `test_battery_locked_gating_is_accurate` are present.
- [ ] **Code-quality review (Opus):** `coverage.py` boundaries, `rules()` backward-compat, `build_manifest` integration, test non-vacuity (the bite-proofs).
- [ ] **Open PR** (master is protected — PR required; required checks `gate`+`build`+`render-complete`). No release cut.

---

## Self-Review (author)

- **Spec coverage:** Goal "classify all 29" → Tasks 1-2 (registry) + appendix split. Goal "battery-gated lock mechanism" → Tasks 2-3. Goal "reverse-coverage check + seam" → Task 4. Goal "anti-stale symmetry" → Task 5. Spec §4 under-lock guard → Task 6. Non-goal (no scope widening) honored — `_SURFACE_ROOTS` fixed to the three roots. Rollout (no release) → Task 7 + reviews.
- **Type consistency:** `BATTERY_LOCKED: dict[str, tuple[str, ...]]`, `EXEMPT: tuple[str, ...]`, `rules(batteries: Sequence[str] = ())`, `coverage.classified_paths() -> set[str]`, `infra_surface_files(project) -> list[str]`, `unclassified_infra_files(project) -> list[str]` — used consistently across Tasks 2-6.
- **Placeholder scan:** every code/test step carries complete code; Task 7 Step 1 is a conditional doc edit with an explicit skip-and-record fallback, not a placeholder.
- **Count check:** `BATTERY_LOCKED` table = 22 entries (18 obs + Dockerfile + 2 scripts + docs.yml); `LOCKED_TRACKED` additions = 5; `EXEMPT` = 2; total 29. Matches the spec appendix.

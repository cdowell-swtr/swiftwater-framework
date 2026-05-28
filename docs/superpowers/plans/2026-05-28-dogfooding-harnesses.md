# Dogfooding Harnesses (Plan 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the framework repo its own CI — a fast gate, a dynamically-generated template render matrix, tidied agent-evals, tag-triggered release automation — and ship a builder-facing `SECRETS.md`.

**Architecture:** A unit-tested combo-generator (`framework dev-combos`) emits matrix JSON the render-matrix workflow fans out over, driving the real `framework new` path; triggers are change-driven (PR=representative, push/schedule=broad) with pairwise-floor + seeded-random coverage. The framework's workflow files live at the repo root and are **not** template payload; the only rendered change is a plain `SECRETS.md.jinja` (sibling of `DEPLOY.md`/`SERVICES.md`, so not integrity-tracked → no manifest shift).

**Tech Stack:** Python 3.12, Typer CLI, `pytest`, `ruff`/`mypy`, GitHub Actions (reusable workflows, dynamic `strategy.matrix` via `fromJSON`), `uv`, Copier/Jinja template.

**Spec:** `docs/superpowers/specs/2026-05-28-dogfooding-harnesses-design.md`

---

## File Structure

**New framework source (tooling, not payload):**
- `src/framework_cli/devmatrix.py` — the combo-generator: `Combo` dataclass + `representative_combos`, `pairwise_combos`, `sample_combos`, `broad_combos`, `combos_for_strategy`.
- `src/framework_cli/release.py` — release tag/version invariant guard.
- `scripts/verify_release_tag.py` — thin CLI wrapper the release workflow runs.

**New repo-root workflows (NOT template payload):**
- `.github/workflows/ci.yml` — fast tier.
- `.github/workflows/render-matrix.yml` — the render matrix.
- `.github/workflows/release.yml` — tag-triggered release.

**Modified framework source:**
- `src/framework_cli/cli.py` — add the `dev-combos` subcommand.

**New tests:**
- `tests/test_devmatrix.py` — combo-generator unit tests.
- `tests/test_release.py` — invariant-guard unit tests.
- `tests/test_workflows.py` — extend with assertions for the three new workflows.
- `tests/test_copier_runner.py` — extend with a `SECRETS.md` render assertion.

**New template payload (the only rendered change):**
- `src/framework_cli/template/SECRETS.md.jinja`.

**Modified docs:**
- `RELEASING.md` — note release is now automated on tag push.
- `CLAUDE.md` + `docs/superpowers/plans/2026-05-20-meta-plan.md` — state (final task).

---

## Task 1: Combo-generator core — `Combo`, representative + pairwise

**Files:**
- Create: `src/framework_cli/devmatrix.py`
- Test: `tests/test_devmatrix.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_devmatrix.py
import itertools

from framework_cli.batteries import battery_names, resolve
from framework_cli.devmatrix import (
    Combo,
    pairwise_combos,
    representative_combos,
)


def test_combo_with_flags_and_dict():
    c = Combo(name="graphql+react", batteries=("graphql", "react"))
    assert c.with_flags == "--with graphql --with react"
    assert c.alerts_flag == ""
    d = c.as_dict()
    assert d["name"] == "graphql+react"
    assert d["batteries"] == ["graphql", "react"]
    assert d["with_flags"] == "--with graphql --with react"
    assert d["has_react"] is True


def test_baseline_combo_has_empty_flags():
    c = Combo(name="baseline", batteries=())
    assert c.with_flags == ""
    assert c.as_dict()["batteries"] == []
    assert c.as_dict()["has_react"] is False


def test_representative_is_the_documented_set():
    names = [c.name for c in representative_combos()]
    assert names == [
        "baseline",
        "webhooks+workers",
        "graphql+react",
        "mongodb+pgvector",
        "workers+redis",
        "full",
    ]
    full = next(c for c in representative_combos() if c.name == "full")
    assert set(full.batteries) == set(battery_names())
    assert full.alerts_flag == "--alerts webhook,slack,email,pagerduty"


def test_pairwise_covers_every_battery_pair():
    combos = pairwise_combos()
    covered = set()
    for c in combos:
        for a, b in itertools.combinations(c.batteries, 2):
            covered.add(frozenset((a, b)))
    all_pairs = {frozenset(p) for p in itertools.combinations(battery_names(), 2)}
    assert all_pairs <= covered


def test_pairwise_is_deterministic_and_valid():
    assert [c.batteries for c in pairwise_combos()] == [
        c.batteries for c in pairwise_combos()
    ]
    for c in pairwise_combos():
        # every emitted combo is a valid, resolvable battery set
        assert resolve(c.batteries) == sorted(set(resolve(c.batteries)))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_devmatrix.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framework_cli.devmatrix'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/framework_cli/devmatrix.py
from __future__ import annotations

import itertools
from dataclasses import dataclass

from framework_cli.batteries import battery_names

_ALL_CHANNELS = ("webhook", "slack", "email", "pagerduty")


@dataclass(frozen=True)
class Combo:
    """One render-matrix entry: a battery set + optional alert channels."""

    name: str
    batteries: tuple[str, ...]
    alerts: tuple[str, ...] = ()

    @property
    def with_flags(self) -> str:
        return " ".join(f"--with {b}" for b in self.batteries)

    @property
    def alerts_flag(self) -> str:
        return f"--alerts {','.join(self.alerts)}" if self.alerts else ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "batteries": list(self.batteries),
            "with_flags": self.with_flags,
            "alerts_flag": self.alerts_flag,
            "has_react": "react" in self.batteries,
        }


def _name_for(batteries: tuple[str, ...]) -> str:
    return "+".join(batteries) if batteries else "baseline"


def representative_combos() -> list[Combo]:
    """The fixed, fast PR set — one per known interaction class (spec §5.3)."""
    return [
        Combo("baseline", ()),
        Combo("webhooks+workers", ("webhooks", "workers")),
        Combo("graphql+react", ("graphql", "react")),
        Combo("mongodb+pgvector", ("mongodb", "pgvector")),
        Combo("workers+redis", ("redis", "workers")),
        Combo("full", tuple(battery_names()), _ALL_CHANNELS),
    ]


def pairwise_combos(max_size: int = 4) -> list[Combo]:
    """Greedy all-pairs: every battery pair co-occurs in at least one combo."""
    names = battery_names()
    uncovered = {frozenset(p) for p in itertools.combinations(names, 2)}
    combos: list[Combo] = []
    while uncovered:
        seed = min(uncovered, key=lambda p: sorted(p))
        chosen = list(sorted(seed))
        while len(chosen) < max_size:
            best: str | None = None
            best_gain = 0
            for c in names:
                if c in chosen:
                    continue
                gain = sum(frozenset((c, x)) in uncovered for x in chosen)
                if gain > best_gain:
                    best, best_gain = c, gain
            if best is None:
                break
            chosen.append(best)
        chosen = sorted(chosen)
        for a, b in itertools.combinations(chosen, 2):
            uncovered.discard(frozenset((a, b)))
        combos.append(Combo(_name_for(tuple(chosen)), tuple(chosen)))
    return combos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_devmatrix.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/devmatrix.py tests/test_devmatrix.py
git commit -m "feat(devmatrix): Combo + representative + pairwise combo generation"
```

---

## Task 2: Combo-generator — seeded sampling, broad, dispatcher

**Files:**
- Modify: `src/framework_cli/devmatrix.py`
- Test: `tests/test_devmatrix.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_devmatrix.py
import pytest

from framework_cli.devmatrix import (
    broad_combos,
    combos_for_strategy,
    sample_combos,
)


def test_sample_is_deterministic_for_a_seed():
    assert [c.batteries for c in sample_combos(seed=7, n=5)] == [
        c.batteries for c in sample_combos(seed=7, n=5)
    ]


def test_sample_differs_across_seeds():
    a = [c.batteries for c in sample_combos(seed=1, n=8)]
    b = [c.batteries for c in sample_combos(seed=2, n=8)]
    assert a != b


def test_sample_yields_n_distinct_valid_combos():
    combos = sample_combos(seed=3, n=6)
    assert len(combos) == 6
    seen = {c.batteries for c in combos}
    assert len(seen) == 6  # distinct
    for c in combos:
        assert all(b in battery_names() for b in c.batteries)


def test_broad_is_pairwise_floor_plus_sample():
    broad = broad_combos(seed=5, sample_size=4)
    floor = {c.batteries for c in pairwise_combos()}
    broad_sets = {c.batteries for c in broad}
    assert floor <= broad_sets  # pairwise floor always present
    assert len(broad_sets) >= len(floor)


def test_combos_for_strategy_dispatch():
    assert [c.name for c in combos_for_strategy("representative")] == [
        c.name for c in representative_combos()
    ]
    assert [c.batteries for c in combos_for_strategy("pairwise")] == [
        c.batteries for c in pairwise_combos()
    ]
    assert combos_for_strategy("sample", seed=9, sample_size=3)
    assert combos_for_strategy("broad", seed=9, sample_size=3)
    with pytest.raises(ValueError, match="unknown strategy"):
        combos_for_strategy("nonsense")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_devmatrix.py -q`
Expected: FAIL with `ImportError: cannot import name 'broad_combos'`

- [ ] **Step 3: Write the minimal implementation**

```python
# append to src/framework_cli/devmatrix.py
import random


def sample_combos(seed: int, n: int) -> list[Combo]:
    """N distinct pseudo-random battery subsets, deterministic for `seed`."""
    rng = random.Random(seed)
    names = battery_names()
    seen: set[tuple[str, ...]] = set()
    combos: list[Combo] = []
    attempts = 0
    while len(combos) < n and attempts < n * 50:
        attempts += 1
        k = rng.randint(1, len(names))
        subset = tuple(sorted(rng.sample(names, k)))
        if subset in seen:
            continue
        seen.add(subset)
        combos.append(Combo(_name_for(subset), subset))
    return combos


def broad_combos(seed: int, sample_size: int = 6) -> list[Combo]:
    """The pairwise floor plus a seeded random rotation (spec §5.3)."""
    floor = pairwise_combos()
    floor_sets = {c.batteries for c in floor}
    extra = [c for c in sample_combos(seed, sample_size) if c.batteries not in floor_sets]
    return floor + extra


def combos_for_strategy(
    strategy: str, *, seed: int = 0, sample_size: int = 6
) -> list[Combo]:
    if strategy == "representative":
        return representative_combos()
    if strategy == "pairwise":
        return pairwise_combos()
    if strategy == "sample":
        return sample_combos(seed, sample_size)
    if strategy == "broad":
        return broad_combos(seed, sample_size)
    raise ValueError(f"unknown strategy: {strategy!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_devmatrix.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/devmatrix.py tests/test_devmatrix.py
git commit -m "feat(devmatrix): seeded sampling, broad set, strategy dispatch"
```

---

## Task 3: `framework dev-combos` CLI subcommand

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cli.py
def test_dev_combos_emits_matrix_json():
    result = runner.invoke(app, ["dev-combos", "--strategy", "representative"])
    assert result.exit_code == 0, result.output
    combos = _json.loads(result.output)
    assert isinstance(combos, list)
    names = [c["name"] for c in combos]
    assert names[0] == "baseline" and "full" in names
    full = next(c for c in combos if c["name"] == "full")
    assert full["alerts_flag"] == "--alerts webhook,slack,email,pagerduty"
    assert all({"name", "batteries", "with_flags", "has_react"} <= set(c) for c in combos)


def test_dev_combos_broad_is_seeded():
    a = runner.invoke(app, ["dev-combos", "--strategy", "broad", "--seed", "4"])
    b = runner.invoke(app, ["dev-combos", "--strategy", "broad", "--seed", "4"])
    assert a.exit_code == 0 and a.output == b.output


def test_dev_combos_rejects_unknown_strategy():
    result = runner.invoke(app, ["dev-combos", "--strategy", "nope"])
    assert result.exit_code == 1
    assert "unknown strategy" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k dev_combos -q`
Expected: FAIL (exit code 2 / "No such command 'dev-combos'")

- [ ] **Step 3: Write the minimal implementation**

Add `import json` near the top of `src/framework_cli/cli.py` (after `import os`), then append this command (place it after the `integrity` command for proximity):

```python
@app.command(name="dev-combos")
def dev_combos(
    strategy: str = typer.Option(
        "representative",
        "--strategy",
        help="representative | pairwise | sample | broad",
    ),
    seed: int = typer.Option(0, "--seed", help="Seed for the random rotation."),
    sample_size: int = typer.Option(
        6, "--sample-size", help="Random combos added to the broad/sample set."
    ),
) -> None:
    """Emit the render-matrix battery combinations as JSON (framework dogfooding CI)."""
    from framework_cli.devmatrix import combos_for_strategy

    try:
        combos = combos_for_strategy(strategy, seed=seed, sample_size=sample_size)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps([c.as_dict() for c in combos]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k dev_combos -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py
git commit -m "feat(cli): framework dev-combos emits render-matrix JSON"
```

---

## Task 4: Framework `ci.yml` (the fast tier)

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: `tests/test_workflows.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflows.py
_CI = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def test_framework_ci_fast_tier():
    wf = yaml.safe_load(_CI.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert "pull_request" in triggers
    assert "workflow_call" in triggers  # reusable by release.yml
    steps = wf["jobs"]["gate"]["steps"]
    run = " ".join(str(s.get("run", "")) for s in steps)
    assert "ruff check" in run
    assert "ruff format --check" in run
    assert "mypy src" in run
    assert "pytest -q --ignore=tests/acceptance" in run
    assert "uv lock --check" in run
    assert "uv build" in run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflows.py::test_framework_ci_fast_tier -q`
Expected: FAIL with `FileNotFoundError` (no `ci.yml`)

- [ ] **Step 3: Create the workflow**

```yaml
# .github/workflows/ci.yml
name: ci

on:
  pull_request:
  push:
    branches: [master]
  workflow_call:

permissions:
  contents: read

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -q --ignore=tests/acceptance
      - run: uv lock --check
      - run: uv build
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflows.py::test_framework_ci_fast_tier -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_workflows.py
git commit -m "ci: framework fast-tier workflow (lint/type/test/lock/build)"
```

---

## Task 5: `render-matrix.yml` (the render matrix)

**Files:**
- Create: `.github/workflows/render-matrix.yml`
- Test: `tests/test_workflows.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflows.py
_RM = Path(__file__).parent.parent / ".github" / "workflows" / "render-matrix.yml"


def test_render_matrix_workflow():
    wf = yaml.safe_load(_RM.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    # change-driven + backstop + reusable + manual
    assert "pull_request" in triggers
    assert "push" in triggers
    assert "schedule" in triggers
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers

    jobs = wf["jobs"]
    # the generate job emits matrix JSON via the CLI
    gen_run = " ".join(
        str(s.get("run", "")) for s in jobs["generate-matrix"]["steps"]
    )
    assert "framework dev-combos" in gen_run
    assert jobs["generate-matrix"]["outputs"]["combos"]

    # the render job fans out via fromJSON and drives the real CLI
    render = jobs["render"]
    assert "fromJSON" in str(render["strategy"]["matrix"]["combo"])
    assert render["strategy"]["fail-fast"] is False
    render_run = " ".join(str(s.get("run", "")) for s in render["steps"])
    assert "framework new demo" in render_run
    assert "framework integrity --ci" in render_run
    assert "task ci" in render_run
    assert "npm ci" in render_run  # react frontend gate
    # react setup is conditional on the combo
    assert any(
        "setup-node" in str(s.get("uses", ""))
        and "react" in str(s.get("if", ""))
        for s in render["steps"]
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflows.py::test_render_matrix_workflow -q`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Create the workflow**

```yaml
# .github/workflows/render-matrix.yml
name: render-matrix

on:
  pull_request:
  push:
    branches: [master]
  schedule:
    - cron: "0 6 * * 1" # Mondays 06:00 UTC — drift backstop
  workflow_dispatch:
  workflow_call:
    inputs:
      strategy:
        type: string
        required: false

permissions:
  contents: read

jobs:
  generate-matrix:
    runs-on: ubuntu-latest
    outputs:
      combos: ${{ steps.gen.outputs.combos }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - id: gen
        env:
          # PR → fast representative set; everything else → broad (pairwise + rotation).
          # A workflow_call may override via inputs.strategy.
          STRATEGY: ${{ inputs.strategy || (github.event_name == 'pull_request' && 'representative' || 'broad') }}
          SEED: ${{ github.run_number }}
        run: |
          combos=$(uv run framework dev-combos --strategy "$STRATEGY" --seed "$SEED")
          echo "combos=$combos" >> "$GITHUB_OUTPUT"

  render:
    needs: generate-matrix
    strategy:
      fail-fast: false
      matrix:
        combo: ${{ fromJSON(needs.generate-matrix.outputs.combos) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: arduino/setup-task@v2
        with:
          version: 3.x
          repo-token: ${{ secrets.GITHUB_TOKEN }}
      - name: Node (react combos only)
        if: contains(matrix.combo.batteries, 'react')
        uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: uv sync
      - run: uv tool install .
      - name: render the project (real builder path)
        run: framework new demo ${{ matrix.combo.with_flags }} ${{ matrix.combo.alerts_flag }}
      - run: uv sync
        working-directory: demo
      - run: framework integrity --ci
        working-directory: demo
      - run: task ci
        working-directory: demo
      - name: frontend gate (react combos only)
        if: contains(matrix.combo.batteries, 'react')
        working-directory: demo/frontend
        run: |
          npm ci
          npm run lint
          npm run typecheck
          npm test
          npm run build
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflows.py::test_render_matrix_workflow -q`
Expected: PASS

- [ ] **Step 5: Local smoke (parity is set up — see meta-plan Environment Notes)**

Run the representative react combo end-to-end the way CI will, to confirm the real path works before relying on Actions:

```bash
SCRATCH=~/rm-smoke; rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"; FW=$(pwd)
cd "$SCRATCH" && uv run --project "$FW" framework new demo --with graphql --with react
cd demo && uv sync && uv run --project "$FW" framework integrity --ci
cd frontend && npm ci && npm run typecheck && npm run build && npm test
cd "$FW" && rm -rf "$SCRATCH"
```
Expected: integrity OK; `dist/` produced; vitest green (1 file, 2 tests).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/render-matrix.yml tests/test_workflows.py
git commit -m "ci: template render matrix (dynamic strategy.matrix per combo)"
```

---

## Task 6: Release invariant guard (`release.py`)

**Files:**
- Create: `src/framework_cli/release.py`
- Create: `scripts/verify_release_tag.py`
- Test: `tests/test_release.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_release.py
from pathlib import Path

import pytest

from framework_cli.release import assert_tag_matches, read_project_version

_PYPROJECT = """\
[project]
name = "framework-cli"
version = "1.4.0"
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(_PYPROJECT)
    return p


def test_read_project_version(tmp_path):
    assert read_project_version(_write(tmp_path)) == "1.4.0"


def test_tag_matches_version(tmp_path):
    assert_tag_matches("v1.4.0", _write(tmp_path))  # no raise


def test_tag_mismatch_raises(tmp_path):
    with pytest.raises(ValueError, match="does not match"):
        assert_tag_matches("v1.4.1", _write(tmp_path))


def test_real_pyproject_version_is_readable():
    # the repo's own pyproject must expose [project].version
    root = Path(__file__).parent.parent / "pyproject.toml"
    assert read_project_version(root)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_release.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framework_cli.release'`

- [ ] **Step 3: Write the implementation**

```python
# src/framework_cli/release.py
from __future__ import annotations

import tomllib
from pathlib import Path


def read_project_version(pyproject: Path) -> str:
    data = tomllib.loads(pyproject.read_text())
    return str(data["project"]["version"])


def assert_tag_matches(tag: str, pyproject: Path) -> None:
    """Raise unless `tag` equals `v<project version>` (the RELEASING.md invariant)."""
    version = read_project_version(pyproject)
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(
            f"release tag {tag!r} does not match project version {version!r} "
            f"(expected {expected!r}); fix the tag or the pyproject version"
        )
```

```python
# scripts/verify_release_tag.py
"""Release-time invariant guard: assert the pushed tag == pyproject version."""

import sys
from pathlib import Path

from framework_cli.release import assert_tag_matches

if __name__ == "__main__":
    tag = sys.argv[1]
    assert_tag_matches(tag, Path("pyproject.toml"))
    print(f"release tag {tag} matches the project version — OK")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_release.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/release.py scripts/verify_release_tag.py tests/test_release.py
git commit -m "feat(release): tag/version invariant guard"
```

---

## Task 7: `release.yml` + `RELEASING.md`

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `RELEASING.md`
- Test: `tests/test_workflows.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflows.py
_REL = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def test_release_workflow():
    wf = yaml.safe_load(_REL.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["tags"] == ["v*"]
    assert wf["permissions"]["contents"] == "write"  # to create a Release

    jobs = wf["jobs"]
    guard_run = " ".join(str(s.get("run", "")) for s in jobs["guard"]["steps"])
    assert "verify_release_tag.py" in guard_run
    # the gate + render matrix are reused and gate the release
    assert jobs["gate"]["uses"].endswith("ci.yml")
    assert jobs["matrix"]["uses"].endswith("render-matrix.yml")
    assert set(jobs["release"]["needs"]) >= {"gate", "matrix"}
    rel_uses = " ".join(str(s.get("uses", "")) for s in jobs["release"]["steps"])
    assert "action-gh-release" in rel_uses
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflows.py::test_release_workflow -q`
Expected: FAIL with `FileNotFoundError`

- [ ] **Step 3: Create the workflow**

```yaml
# .github/workflows/release.yml
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write # create the GitHub Release

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - name: invariant guard (tag == pyproject version)
        run: uv run python scripts/verify_release_tag.py "${GITHUB_REF_NAME}"

  gate:
    needs: guard
    uses: ./.github/workflows/ci.yml

  matrix:
    needs: guard
    uses: ./.github/workflows/render-matrix.yml
    with:
      strategy: broad

  release:
    needs: [gate, matrix]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv build
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflows.py::test_release_workflow -q`
Expected: PASS

- [ ] **Step 5: Update `RELEASING.md`**

In `RELEASING.md`, under `## Procedure`, replace step 4 (the "invariant holds by construction" note) with an automation note. Add after the existing numbered steps:

```markdown
4. **Automated on tag push:** the `release.yml` workflow then (a) asserts the tag equals the
   `pyproject` version (the invariant — a mismatch fails the release), (b) re-runs the fast
   gate and the broad render matrix on the tagged commit (*the template is never released
   unless rendered projects are green*), (c) builds the wheel, and (d) creates the GitHub
   Release with generated notes + the wheel attached. Do not move a tag after release.
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/release.yml RELEASING.md tests/test_workflows.py
git commit -m "ci: tag-triggered release.yml (guard + gate + matrix + GitHub Release)"
```

---

## Task 8: Verify agent-evals triggers cover the new agents

**Files:**
- Test: `tests/test_workflows.py`

The `agent-evals.yml` workflow already exists and is path-triggered on `agents/**` and `review/**.py`. Confirm those globs still cover the agents added since (`review-contracts`, `review-observability-infra`, `review-observability-db`) — they all live under `src/framework_cli/review/agents/`, so the existing globs suffice. Lock that in with a test that fails if the prompt path moves out from under the trigger.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_workflows.py
def test_agent_evals_triggers_cover_all_agent_prompts():
    wf = yaml.safe_load(_WF.read_text())
    triggers = wf[True] if True in wf else wf["on"]
    push_paths = triggers["push"]["paths"]
    agents_dir = (
        Path(__file__).parent.parent
        / "src" / "framework_cli" / "review" / "agents"
    )
    prompts = list(agents_dir.glob("*.md"))
    # the newer agents must exist and live under the triggered directory
    have = {p.stem for p in prompts}
    assert {"contracts", "observability-infra", "observability-db"} <= have
    # at least one push path glob matches that agents directory
    assert any("agents" in p for p in push_paths)
```

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `uv run pytest tests/test_workflows.py::test_agent_evals_triggers_cover_all_agent_prompts -q`
Expected: PASS if the three prompts exist under `agents/` (they do, from Plan 9 + OBS-COMPLETE). If it FAILS because a prompt filename differs, adjust the asserted stems to the actual filenames (`ls src/framework_cli/review/agents/*.md`) — the point is to assert the trigger covers them.

- [ ] **Step 3: Commit**

```bash
git add tests/test_workflows.py
git commit -m "test(workflows): assert agent-evals triggers cover the newer agents"
```

---

## Task 9: Ship `SECRETS.md` in the template

**Files:**
- Create: `src/framework_cli/template/SECRETS.md.jinja`
- Test: `tests/test_copier_runner.py`

**Note:** top-level docs (`DEPLOY.md`/`SERVICES.md`/`README.md`) are plain rendered files — **not** in `LOCKED_TRACKED`/`HYBRID_TRACKED`. `SECRETS.md` follows that precedent: a plain rendered doc, builder-owned, **not** integrity-tracked → **no manifest shift**, integrity stays green.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_copier_runner.py
def test_secrets_doc_renders_with_convention(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    secrets = (dest / "SECRETS.md").read_text()
    # the two-tier naming convention + the project's secrets are documented
    assert "ANTHROPIC_API_KEY" in secrets
    assert "GITLEAKS_LICENSE" in secrets
    assert "provider console" in secrets.lower()
    # project/package name interpolates (it is a builder-facing doc).
    # DATA renders project_name="Demo", package_name="demo".
    assert "demo" in secrets.lower()
```

(`DATA` is the existing module-level render fixture in `tests/test_copier_runner.py` —
`project_name="Demo"`, `package_name="demo"`; reuse it as-is.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_secrets_doc_renders_with_convention -q`
Expected: FAIL with `FileNotFoundError` (no `SECRETS.md` rendered)

- [ ] **Step 3: Create the template file**

```jinja
{# src/framework_cli/template/SECRETS.md.jinja #}
# Secrets — {{ project_name }}

How this project's API keys and secrets are named and where they live. This is the targeted,
in-repo reference; the comprehensive conventions home is the framework documentation pack.

## The two-tier naming convention

Every secret has **two** names:

1. A **descriptive label** in the *provider console* (e.g. the Anthropic or GitHub console) —
   metadata for audit and rotation, never the token value itself:

   ```
   <service>_<package>_<owner>_<env>_<host>_<scope>_<created>_<rand>
   # e.g. anthropic_{{ package_name }}_jane_ci_gha_runtime_20260601_3f8d0c1e
   ```

   - `service`: the provider (`anthropic`, `gh`, …)
   - `package`: this project (`{{ package_name }}`)
   - `owner`: the person accountable for rotation/revocation
   - `env`: `dev | ci | stage | prod`
   - `host`: the machine, or `gha | shared | n-a` for non-local
   - `scope`: `runtime | eval | ro | rw` (chain with `-`)
   - `created`: `YYYYMMDD` issue date
   - `rand`: 8 hex chars

2. A **stable boring name** where the secret is *consumed*: the environment variable the code
   reads (e.g. `ANTHROPIC_API_KEY`), and — in GitHub Actions — a GH-legal secret name
   (uppercase, underscores, no date/rand since the slot rotates in place) mapped into that env
   var in the workflow.

## Secrets this project uses

| Purpose | GitHub secret name | Consumed as |
|---------|--------------------|-------------|
| Review-agent LLM key (CI review job) | `ANTHROPIC_{{ package_name | upper }}_CI_RUNTIME` | `ANTHROPIC_API_KEY` env |
| Gitleaks license (full-history scan) | `GITLEAKS_LICENSE` | `GITLEAKS_LICENSE` env |
| Container registry (deploy) | registry creds (e.g. `GHCR_TOKEN`) | login step env |
| Alert delivery (if alert channels configured) | per channel — Slack webhook URL / SMTP password / PagerDuty routing key | mounted secret files (`slack_api_url_file` / `smtp_auth_password_file` / `routing_key_file`) |

Set GitHub secrets under **Settings → Secrets and variables → Actions**. Map each into the
boring env var its consumer expects (see `.github/workflows/` and `infra/`).

> The framework's *own* CI uses this same convention — e.g. the review-agent eval key is the
> GitHub secret `ANTHROPIC_FRAMEWORK_CI_EVAL` mapped to `ANTHROPIC_API_KEY`. Name your project's
> secrets the same way.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_secrets_doc_renders_with_convention -q`
Expected: PASS. (If the `package_name`/`project_name` assertions miss, check the rendered file and align the assertion to `DATA`'s values.)

- [ ] **Step 5: Confirm integrity is unaffected (no manifest shift)**

Run: `uv run pytest tests/test_copier_runner.py tests/test_cli.py -k "integrity or manifest" -q`
Expected: PASS — `SECRETS.md` is not integrity-tracked, so the manifest is unchanged.

- [ ] **Step 6: Commit**

```bash
git add "src/framework_cli/template/SECRETS.md.jinja" tests/test_copier_runner.py
git commit -m "feat(template): ship SECRETS.md (two-tier secret-naming convention)"
```

---

## Task 10: Final integration — full gate, parity render check, state

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Run the full framework gate**

Run:
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q --ignore=tests/acceptance && uv lock --check && uv build
```
Expected: all green; the new `devmatrix`/`release`/`dev-combos`/workflow/`SECRETS.md` tests pass alongside the prior ~485.

- [ ] **Step 2: Confirm `framework dev-combos` works as CI will invoke it**

Run:
```bash
uv run framework dev-combos --strategy representative | python -c "import sys,json; print(len(json.load(sys.stdin)), 'combos')"
uv run framework dev-combos --strategy broad --seed 1 | python -c "import sys,json; print(len(json.load(sys.stdin)), 'combos')"
```
Expected: valid JSON arrays (6 representative; pairwise floor + sample for broad).

- [ ] **Step 3: Update `CLAUDE.md` Current State + Known follow-ups**

Update the **Last updated** entry to record Plan 10 merged: the framework now has its own CI (fast `ci.yml`, dynamic `render-matrix.yml` with pairwise+sample coverage, tag-triggered `release.yml`), `agent-evals` triggers verified, and `SECRETS.md` ships in the template (plain doc, no manifest shift). Note the react matrix job is the standing frontend regression gate (closes the §2.1 follow-up). Note Plan 11 is now unblocked (real-key eval scoring + full GitHub Actions react/image-build confirmation).

- [ ] **Step 4: Update the meta-plan status table**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`, set row 10's status to ✅ Done with the merge SHA, and add a one-line summary mirroring the CLAUDE.md note.

- [ ] **Step 5: Commit the state update**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs: Plan 10 (dogfooding harnesses) complete — state + meta-plan"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** §4 → Task 4; §5 (matrix + generator + react job + triggers + coverage) → Tasks 1–3, 5; §6 (agent-evals) → Task 8; §7 (release) → Tasks 6–7; §8 (SECRETS.md) → Task 9; §9 testing woven through; §12 success criteria → Task 10.
- **Correction vs spec §8.1:** `SECRETS.md` is a plain rendered doc (sibling of `DEPLOY.md`/`SERVICES.md`, which are *not* integrity-tracked) → **no baseline manifest shift**, integrity trivially green. The spec assumed a shift; Task 9 documents the corrected reality.
- **Deferred to Plan 11 (do NOT attempt here):** the real-key `agent-evals` scoring run + threshold tuning; the full GitHub Actions confirmation of the react Playwright/axe e2e and end-to-end BuildKit image build. This plan *builds* the matrix that runs them; Plan 11 *reads the result*.
- **Naming consistency:** `combos_for_strategy(strategy, *, seed, sample_size)` and `Combo.as_dict()` keys (`name`, `batteries`, `with_flags`, `alerts_flag`, `has_react`) are used identically in Tasks 1–3 and the workflow (`matrix.combo.batteries`, `matrix.combo.with_flags`, `matrix.combo.alerts_flag`).
- **CI caveats the executor should expect on first live run:** `uv tool install .` must install from the working tree (PR changes), not a published tag; `fromJSON` needs a top-level JSON array (Task 1/3 guarantee it); `arduino/setup-task` provides the `task` binary the rendered project's gate needs.
```

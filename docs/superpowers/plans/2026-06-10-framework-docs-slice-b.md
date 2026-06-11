# Per-Project Docs Battery (Slice 22b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `docs` battery that renders a versioning-ready MkDocs+Material documentation site into generated projects, with a static OpenAPI render, mkdocstrings Python API, and tag-driven `mike` versioning published as a portable `gh-pages` artifact.

**Architecture:** Pure template payload + one `BatterySpec`. Every docs file renders only under `{% if "docs" in batteries %}` guards, so a no-docs render is byte-identical to today (protects existing render tests + eval fixtures). The docs **build-strict gate** lives as a battery-conditional `docs` job in the generated `ci.yml` (tracked by the dogfood harness via `BATTERY_JOBS`) and as a `docs:build` step in the local `task ci` (so the render-matrix exercises it). The **mike publish** lives in a separate, tag-triggered `docs.yml` workflow that pushes versioned HTML to a `gh-pages` branch — a portable artifact, served via Pages / any static host / `mike serve`, opt-in.

**Tech Stack:** Copier/Jinja template payload, MkDocs + Material, `mkdocstrings[python]`, `mkdocs-render-swagger-plugin`, `mike`, `uv` dependency-groups, GitHub Actions (node24-pinned), pytest.

---

## Background the implementer needs

**This is template payload, not framework source.** Files under `src/framework_cli/template/` are rendered into generated projects. Do **not** lint/type-check them as framework code. They are validated by *rendering* + exercising the generated project. The TDD loop for template payload (see `CLAUDE.md` "Template-payload TDD loop"):

1. `render_project(dest, DATA)` writes a generated project to a tmp dir.
2. Assert on the rendered files' presence/content (`tests/test_copier_runner.py`) — fast, no deps.
3. For build-level checks (`tests/acceptance/test_rendered_project.py`): render → `uv sync` → run a real command in the generated project → assert exit code.

**Battery-conditional rendering pattern** (already used by `react`, `consumers`, `webhooks`):
- Conditional *directories/files* use brace-templated path segments, e.g.
  `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/...`
  — when the guard is false the segment renders empty and the file is skipped.
- Conditional *blocks inside shared files* (e.g. `pyproject.toml.jinja`, `Taskfile.yml.jinja`,
  `ci.yml.jinja`) use inline `{% if "docs" in batteries %} ... {% endif %}`.

**Critical invariant — no-docs renders must stay byte-identical.** The eval fixtures and dozens of
existing render tests render *without* the docs battery. Every edit to a shared file
(`pyproject.toml.jinja`, `Taskfile.yml.jinja`, `ci.yml.jinja`) MUST be wrapped so the no-docs
output is unchanged. After each shared-file edit, run the existing render suite
(`uv run pytest tests/test_copier_runner.py -q`) to confirm nothing regressed.

**How tests render with a battery:** `render_project(dest, {**DATA, "batteries": ["docs"]})`.

**Auto-covered guards (no new fixtures needed, but must stay green):**
- `tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface` is parametrized over
  `battery_names()`. A `rides-existing` battery must add **no** scrape job / alert rule / dashboard /
  prod service / exporter. The docs battery adds none → passes automatically.
- `tests/test_workflow_node24.py::test_template_workflows_use_node24_actions` scans
  `template/.github/workflows/*.yml.jinja`. The new `docs.yml.jinja` must use only actions already in
  `APPROVED_ACTIONS` (`actions/checkout@v5`, `astral-sh/setup-uv@v7` — both already approved).

**Commit cadence (see `CLAUDE.md` "Gate cadence for framework slices"):** do NOT run the full
18-agent review gate per commit on template files. Implementers stage + pass the commit-gate hook but
the **controller finishes each commit** (implementers stop before `git commit`). Use a per-task light
review + a single branch-end Opus whole-branch review. The `CLAUDE.md` Current-State pointer + the
meta-plan 22b row must be staged with each commit (a PreToolUse hook enforces `CLAUDE.md` is staged).

---

## File structure

**Framework source (lint/type-checked):**
- Modify `src/framework_cli/batteries.py` — add the `docs` `BatterySpec`.
- Modify `src/framework_cli/dogfood.py` — add `BATTERY_JOBS["docs"] = "docs"`.

**Template payload (rendered, not linted):**
- Modify `src/framework_cli/template/pyproject.toml.jinja` — battery-guarded `docs` dependency-group.
- Create `src/framework_cli/template/{% if "docs" in batteries %}documentation{% endif %}/index.md.jinja`
- Create `…/{% if "docs" in batteries %}documentation{% endif %}/architecture.md.jinja`
- Create `…/{% if "docs" in batteries %}documentation{% endif %}/api/rest.md.jinja`
- Create `…/{% if "docs" in batteries %}documentation{% endif %}/api/python.md.jinja`
- Create `…/{% if "docs" in batteries %}documentation{% endif %}/see-also.md.jinja`
- Create `…/{% if "docs" in batteries %}documentation{% endif %}/.gitignore` (ignore the built `openapi.json` copy)
- Create `src/framework_cli/template/{{ 'mkdocs.yml' if 'docs' in batteries else '' }}.jinja`
- Modify `src/framework_cli/template/Taskfile.yml.jinja` — battery-guarded `docs:*` tasks + `docs:build` in `ci`.
- Modify `src/framework_cli/template/.github/workflows/ci.yml.jinja` — battery-guarded `docs` build-strict job.
- Create `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja` — tag-driven mike publish.

**Tests:**
- Modify `tests/test_copier_runner.py` — render assertions (present-with / absent-without).
- Modify `tests/acceptance/test_rendered_project.py` — `mkdocs build --strict` end-to-end.
- Modify `tests/test_dogfood.py` (or wherever `DogfoodConfig.expected_jobs` is tested) — `docs` job.

---

## Phase 0 — Register the battery

### Task 1: Add the `docs` BatterySpec

**Files:**
- Test: `tests/test_batteries.py` (create the test fn; file already exists — confirm with `ls tests/test_batteries.py`)
- Modify: `src/framework_cli/batteries.py:26-85` (the `_BATTERIES` dict)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_batteries.py`:

```python
from framework_cli.batteries import battery_names, get_battery


def test_docs_battery_is_registered_as_rides_existing():
    assert "docs" in battery_names()
    spec = get_battery("docs")
    assert spec.obs == "rides-existing"
    # The docs battery is pure scaffolding: it gates no review agents and implies no batteries.
    assert spec.gates_agents == ()
    assert spec.requires == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batteries.py::test_docs_battery_is_registered_as_rides_existing -v`
Expected: FAIL — `KeyError: unknown battery: docs`.

- [ ] **Step 3: Add the BatterySpec**

In `src/framework_cli/batteries.py`, add this entry to `_BATTERIES` (after the `"consumers"` entry, before the closing `}`):

```python
    "docs": BatterySpec(
        "docs",
        "Versioning-ready MkDocs+Material documentation site (mkdocstrings Python API, static OpenAPI render, mike per-version docs)",
        obs="rides-existing",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_batteries.py::test_docs_battery_is_registered_as_rides_existing -v`
Expected: PASS.

- [ ] **Step 5: Confirm the obs guard still passes for the new battery**

Run: `uv run pytest "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[docs]" -v`
Expected: PASS (the docs battery adds no observability artifacts).

- [ ] **Step 6: Stage (controller commits)**

```bash
git add src/framework_cli/batteries.py tests/test_batteries.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Controller: update the `CLAUDE.md` Current-State pointer + meta-plan 22b row, then commit
`feat(22b): register docs battery (rides-existing)`.)

---

## Phase 1 — Template payload: the scaffold

### Task 2: Battery-guarded `docs` dependency-group in the generated pyproject

**Files:**
- Test: `tests/test_copier_runner.py`
- Modify: `src/framework_cli/template/pyproject.toml.jinja:30-44` (the `[dependency-groups]` block)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_docs_battery_adds_docs_dependency_group(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    pyproject = (dest / "pyproject.toml").read_text()
    assert "mkdocs-material" in pyproject
    assert "mike" in pyproject
    assert "mkdocs-render-swagger-plugin" in pyproject
    assert "mkdocstrings[python]" in pyproject


def test_render_without_docs_battery_has_no_docs_deps(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    pyproject = (dest / "pyproject.toml").read_text()
    assert "mkdocs" not in pyproject
    assert "mike" not in pyproject
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k docs_battery_adds_docs -v`
Expected: FAIL — `mkdocs-material` not found.

- [ ] **Step 3: Add the guarded group**

In `src/framework_cli/template/pyproject.toml.jinja`, immediately after the closing `]` of the
`dev = [ ... ]` list and before `[build-system]`, add:

```jinja
{% if "docs" in batteries %}
docs = [
    "mkdocs-material>=9.7.6",
    "mkdocstrings[python]>=1.0.4",
    "mkdocs-render-swagger-plugin>=0.1.2",
    "mike>=2.1.3",
]
{% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_docs or without_docs_battery_has_no_docs" -v`
Expected: PASS (both).

- [ ] **Step 5: Confirm no-docs renders are unchanged**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS (the existing baseline-render tests still pass — the guard is inert without the battery).

- [ ] **Step 6: Stage (controller commits)**

```bash
git add src/framework_cli/template/pyproject.toml.jinja tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `feat(22b): docs dependency-group in generated pyproject`.)

### Task 3: The `documentation/` pages + `mkdocs.yml`

**Files:**
- Test: `tests/test_copier_runner.py`
- Create: the `documentation/` page files + `mkdocs.yml.jinja` (paths in File Structure above)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_docs_battery_creates_mkdocs_site(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    assert (dest / "mkdocs.yml").is_file()
    assert (dest / "documentation" / "index.md").is_file()
    assert (dest / "documentation" / "architecture.md").is_file()
    assert (dest / "documentation" / "api" / "rest.md").is_file()
    assert (dest / "documentation" / "api" / "python.md").is_file()
    assert (dest / "documentation" / "see-also.md").is_file()

    mkdocs = (dest / "mkdocs.yml").read_text()
    # Material theme + mike version selector + the two reference plugins.
    assert "material" in mkdocs
    assert "provider: mike" in mkdocs
    assert "mkdocstrings" in mkdocs
    assert "render_swagger" in mkdocs
    # Title interpolated from the project name.
    assert "Demo" in mkdocs

    # The Python-API page targets the project package; the REST page renders the committed spec.
    assert "::: demo" in (dest / "documentation" / "api" / "python.md").read_text()
    assert "!!swagger openapi.json!!" in (dest / "documentation" / "api" / "rest.md").read_text()


def test_render_without_docs_battery_has_no_mkdocs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "mkdocs.yml").exists()
    assert not (dest / "documentation").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_creates_mkdocs or without_docs_battery_has_no_mkdocs" -v`
Expected: FAIL — `mkdocs.yml` missing.

- [ ] **Step 3: Create `mkdocs.yml.jinja`**

Create `src/framework_cli/template/{{ 'mkdocs.yml' if 'docs' in batteries else '' }}.jinja`:

```jinja
site_name: {{ project_name }} docs
site_description: Documentation for the {{ project_name }} service.
docs_dir: documentation

theme:
  name: material
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
    - toc.follow

# Tag-driven per-version docs via mike (see docs.yml). `latest` is the default.
extra:
  version:
    provider: mike
    default: latest

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
          options:
            show_source: false
            docstring_style: google
  - render_swagger

# MkDocs 1.6+ native validation — `--strict` turns these into build failures.
validation:
  nav:
    omitted_files: warn
  links:
    not_found: warn
    anchors: warn
    unrecognized_links: warn

nav:
  - Home: index.md
  - Architecture: architecture.md
  - API reference:
      - REST API: api/rest.md
      - Python modules: api/python.md
  - See also: see-also.md
```

- [ ] **Step 4: Create the page files**

Create `…/{% if "docs" in batteries %}documentation{% endif %}/index.md.jinja`:

```jinja
# {{ project_name }} docs

Welcome to the documentation site for **{{ project_name }}**.

This site is generated with [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/)
and is versioned with [mike](https://github.com/jimporter/mike) — use the version selector in the header to
switch between released versions of these docs.

- **[Architecture](architecture.md)** — how this service is put together.
- **[REST API](api/rest.md)** — the live OpenAPI contract, rendered in-page.
- **[Python modules](api/python.md)** — auto-generated reference for the `{{ package_name }}` package.
- **[See also](see-also.md)** — operational docs (secrets, deploy, services) and framework conventions.

> Serve this site locally with `task docs:serve` (versioned view via `mike serve`), or build the static
> site with `task docs:build`.
```

Create `…/architecture.md.jinja`:

```jinja
# Architecture

{{ project_name }} is a FastAPI service scaffolded by the swiftwater-framework. This page is a starting
point — expand it as the service grows.

## Shape

- **Entry point:** `src/{{ package_name }}/main.py` builds the app via `create_app()`.
- **Routes:** `src/{{ package_name }}/routes/` — each module registers a router; `include_routers` wires them in.
- **Persistence:** PostgreSQL via SQLAlchemy (`src/{{ package_name }}/db/`), migrations under `migrations/`.
- **Observability:** OpenTelemetry traces/metrics/logs are auto-instrumented; see the framework's
  [observability guide](https://cdowell-swtr.github.io/swiftwater-framework/working/observability/).

## Conventions

This service inherits the framework's conventions for quality gates, environment parity, and secrets.
Rather than restate them here, see **[See also](see-also.md)**, which links to the in-repo operational
docs and the framework's published site.
```

Create `…/api/rest.md.jinja`:

```jinja
# REST API

The live OpenAPI contract for {{ project_name }}, rendered from the committed `openapi.json`
(regenerated at docs-build time via `task openapi:export`):

!!swagger openapi.json!!

> The same schema is served by the running app at `/openapi.json`, with interactive docs at `/docs`
> (Swagger UI) and `/redoc` (ReDoc).
```

Create `…/api/python.md.jinja`:

```jinja
# Python modules

Auto-generated reference for the `{{ package_name }}` package, rendered by
[mkdocstrings](https://mkdocstrings.github.io/) from the source docstrings.

::: {{ package_name }}
    options:
      show_submodules: true
```

Create `…/see-also.md.jinja`:

```jinja
# See also

This docs site is the *published* surface. The operational source of truth lives in the repo root and
cross-links here:

- **[`README.md`](../README.md)** — project overview and quickstart.
- **[`SECRETS.md`](../SECRETS.md)** — secrets and environment parity.
- **[`DEPLOY.md`](../DEPLOY.md)** — deployment.
- **[`SERVICES.md`](../SERVICES.md)** — the service topology.

For cross-cutting framework conventions (quality gates, the review system, batteries, upgrading), see the
framework's published docs: <https://cdowell-swtr.github.io/swiftwater-framework/>.
```

Create `…/.gitignore` (plain file, no `.jinja`):

```gitignore
# Built artifact: the OpenAPI spec is copied here at docs-build time (see Taskfile docs:build).
openapi.json
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_creates_mkdocs or without_docs_battery_has_no_mkdocs" -v`
Expected: PASS (both).

- [ ] **Step 6: Confirm no-docs renders unchanged + format-clean**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS.

- [ ] **Step 7: Stage (controller commits)**

```bash
git add "src/framework_cli/template/{{ 'mkdocs.yml' if 'docs' in batteries else '' }}.jinja" "src/framework_cli/template/{% if \"docs\" in batteries %}documentation{% endif %}" tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(If the brace-named paths fight the shell, `git add -A src/framework_cli/template tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md`. Commit: `feat(22b): mkdocs site scaffold (pages + mkdocs.yml)`.)

### Task 4: Taskfile `docs:*` tasks + `docs:build` in `task ci`

**Files:**
- Test: `tests/test_copier_runner.py`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` (the `openapi:export` / `ci` region, ~lines 186-205)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_docs_battery_adds_taskfile_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "docs:serve" in taskfile
    assert "docs:build" in taskfile
    assert "docs:deploy" in taskfile
    assert "mike serve" in taskfile
    assert "mkdocs build --strict" in taskfile
    # docs:build must run inside the `ci` task so the render-matrix (`task ci`) exercises it.
    ci_section = taskfile.split("ci:", 1)[1].split("push:", 1)[0]
    assert "docs:build" in ci_section


def test_render_without_docs_battery_has_no_docs_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "docs:serve" not in (dest / "Taskfile.yml").read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_taskfile or without_docs_battery_has_no_docs_tasks" -v`
Expected: FAIL — `docs:serve` not found.

- [ ] **Step 3: Add the tasks**

In `src/framework_cli/template/Taskfile.yml.jinja`, add a guarded block immediately after the
`openapi:export:` task and before `audit:`:

```jinja
{% if "docs" in batteries %}
  docs:build:
    desc: Build the static docs site (regenerates the OpenAPI spec, then strict-builds MkDocs).
    cmds:
      - task: openapi:export
      - cp openapi.json documentation/openapi.json
      - uv run --group docs mkdocs build --strict

  docs:serve:
    desc: Serve the versioned docs locally (mike) at http://127.0.0.1:8000.
    cmds:
      - task: openapi:export
      - cp openapi.json documentation/openapi.json
      - uv run --group docs mike serve

  docs:deploy:
    desc: Publish the current git tag's docs to the gh-pages branch (mike). Run from a vX.Y.Z tag.
    cmds:
      - task: openapi:export
      - cp openapi.json documentation/openapi.json
      - uv run --group docs mike deploy --push --update-aliases "$(git describe --tags --abbrev=0 | sed 's/^v//' | cut -d. -f1,2)" latest
{% endif %}
```

Then, inside the existing `ci:` task's `cmds:` list, add a guarded `docs:build` step after
`- task: openapi:export`:

```jinja
      - task: openapi:export
{% if "docs" in batteries %}      - task: docs:build
{% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_taskfile or without_docs_battery_has_no_docs_tasks" -v`
Expected: PASS (both).

- [ ] **Step 5: Confirm no-docs renders unchanged**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS.

- [ ] **Step 6: Stage (controller commits)**

```bash
git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `feat(22b): docs Taskfile targets + ci wiring`.)

---

## Phase 2 — CI wiring

### Task 5: Battery-conditional `docs` build-strict job in the generated `ci.yml`

**Files:**
- Test: `tests/test_copier_runner.py`
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja` (alongside the other
  battery-conditional jobs `frontend` / `contracts`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
import yaml  # already imported at top of the module


def test_render_docs_battery_adds_ci_docs_job(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    assert "docs" in ci["jobs"], "the docs battery must add a `docs` job to ci.yml"
    steps = ci["jobs"]["docs"]["steps"]
    flat = " ".join(str(s.get("run", "")) for s in steps)
    assert "mkdocs build --strict" in flat


def test_render_without_docs_battery_has_no_ci_docs_job(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ci = yaml.safe_load((dest / ".github" / "workflows" / "ci.yml").read_text())
    assert "docs" not in ci["jobs"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_ci_docs_job or without_docs_battery_has_no_ci_docs_job" -v`
Expected: FAIL — no `docs` job.

- [ ] **Step 3: Add the guarded job**

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, add a guarded job next to the other
battery-conditional jobs (after the `contracts:` job block). Match the indentation of sibling jobs:

```jinja
{% if "docs" in batteries %}
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv sync --frozen
      - name: regenerate the OpenAPI spec for the docs render
        run: |
          bash scripts/export-openapi.sh
          cp openapi.json documentation/openapi.json
      - name: mkdocs build (strict)
        run: uv run --group docs mkdocs build --strict
{% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_ci_docs_job or without_docs_battery_has_no_ci_docs_job" -v`
Expected: PASS (both).

- [ ] **Step 5: Confirm the node24 guard still passes**

Run: `uv run pytest tests/test_workflow_node24.py -q`
Expected: PASS (only already-approved actions used).

- [ ] **Step 6: Stage (controller commits)**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `feat(22b): docs build-strict job in generated ci.yml`.)

### Task 6: Tag-driven `docs.yml` mike-publish workflow

**Files:**
- Test: `tests/test_copier_runner.py`
- Create: `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_render_docs_battery_adds_publish_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    path = dest / ".github" / "workflows" / "docs.yml"
    assert path.is_file(), "the docs battery must ship a docs.yml publish workflow"
    wf = yaml.safe_load(path.read_text())
    # PyYAML parses the bare `on:` key as boolean True — assert on that key.
    triggers = wf[True]
    assert "tags" in triggers["push"], "publish must be tag-triggered"
    body = path.read_text()
    assert "mike deploy" in body
    assert "contents: write" in body  # needed to push the gh-pages branch


def test_render_without_docs_battery_has_no_publish_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / ".github" / "workflows" / "docs.yml").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_publish_workflow or without_docs_battery_has_no_publish_workflow" -v`
Expected: FAIL — `docs.yml` missing.

- [ ] **Step 3: Create the workflow**

Create `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja`:

```jinja
name: docs

# Tag-driven publish: each release tag adds a frozen version and moves `latest`.
# The build-strict gate runs in ci.yml on every PR/push; this workflow only publishes.
on:
  push:
    tags:
      - "v*"

permissions:
  contents: write # mike pushes the built site to the gh-pages branch

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v7
      - run: uv sync --frozen
      - name: regenerate the OpenAPI spec for the docs render
        run: |
          bash scripts/export-openapi.sh
          cp openapi.json documentation/openapi.json
      - name: publish versioned docs (mike)
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git fetch origin gh-pages --depth=1 || true
          VERSION="{% raw %}${GITHUB_REF_NAME#v}{% endraw %}"   # v1.2.3 -> 1.2.3
          MINOR="{% raw %}${VERSION%.*}{% endraw %}"            # 1.2.3 -> 1.2
          uv run --group docs mike deploy --push --update-aliases "$MINOR" latest
          uv run --group docs mike set-default --push latest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k "docs_battery_adds_publish_workflow or without_docs_battery_has_no_publish_workflow" -v`
Expected: PASS (both).

- [ ] **Step 5: Confirm node24 guard passes (scans the new docs.yml.jinja)**

Run: `uv run pytest tests/test_workflow_node24.py -q`
Expected: PASS.

- [ ] **Step 6: Stage (controller commits)**

```bash
git add -A src/framework_cli/template/.github/workflows tests/test_copier_runner.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `feat(22b): tag-driven mike publish workflow (docs.yml)`.)

### Task 7: Register the `docs` job in the dogfood harness

**Files:**
- Test: `tests/test_dogfood.py` (confirm the filename: `ls tests/test_dogfood.py`; if named
  differently, find it with `grep -rl "expected_jobs\|BATTERY_JOBS" tests`)
- Modify: `src/framework_cli/dogfood.py:33` (`BATTERY_JOBS`)

- [ ] **Step 1: Write the failing test**

Add to the dogfood test module:

```python
from framework_cli.dogfood import BATTERY_JOBS, DogfoodConfig


def test_docs_battery_expects_a_docs_ci_job():
    assert BATTERY_JOBS.get("docs") == "docs"
    cfg = DogfoodConfig(name="docs", batteries=("docs",))
    assert "docs" in cfg.expected_jobs()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dogfood.py -k docs_battery_expects -v`
Expected: FAIL — `BATTERY_JOBS.get("docs")` is `None`.

- [ ] **Step 3: Add the mapping**

In `src/framework_cli/dogfood.py`, extend `BATTERY_JOBS`:

```python
BATTERY_JOBS: dict[str, str] = {
    "react": "frontend",
    "consumers": "contracts",
    "docs": "docs",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dogfood.py -k docs_battery_expects -v`
Expected: PASS.

- [ ] **Step 5: Stage (controller commits)**

```bash
git add src/framework_cli/dogfood.py tests/test_dogfood.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `feat(22b): track docs ci job in the dogfood harness`.)

---

## Phase 3 — Acceptance + branch-end verification

### Task 8: End-to-end `mkdocs build --strict` acceptance test

**Files:**
- Test: `tests/acceptance/test_rendered_project.py`

**Note:** This test needs only `uv` (no docker/Postgres) — `create_app().openapi()` builds the schema
without a DB connection. Gate it on `uv` presence only, so it runs in more environments than the
docker-gated tests.

- [ ] **Step 1: Write the failing test**

Add to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv required to build the rendered project's docs site",
)
def test_rendered_project_docs_battery_builds_strict(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})

    # Battery files must exist.
    assert (dest / "mkdocs.yml").is_file()
    assert (dest / "documentation" / "index.md").is_file()

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Regenerate + stage the OpenAPI spec the REST page renders, then strict-build.
    export = subprocess.run(["bash", "scripts/export-openapi.sh"], cwd=dest)
    assert export.returncode == 0, "OpenAPI export failed"
    shutil.copyfile(dest / "openapi.json", dest / "documentation" / "openapi.json")

    build = subprocess.run(
        ["uv", "run", "--group", "docs", "mkdocs", "build", "--strict"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, f"mkdocs --strict build failed:\n{build.stdout}\n{build.stderr}"
    assert (dest / "site" / "index.html").is_file()
```

- [ ] **Step 2: Run the test to verify it fails (or errors) before the payload is correct**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k docs_battery_builds_strict -v`
Expected: At this point the payload from Phase 1 exists, so this may PASS. If the chosen
swagger-render plugin token/config is wrong, it FAILS at `mkdocs build --strict` — **this strict build
is the gate** for the plugin choice. Adjust `mkdocs.yml` / `api/rest.md` (the `!!swagger ...!!` token,
or the plugin name) until the strict build is clean. If `render_swagger` cannot locate
`documentation/openapi.json`, confirm the page references it relative to `docs_dir` (i.e.
`!!swagger openapi.json!!`, with the copied spec living at `documentation/openapi.json`).

- [ ] **Step 3: Make it pass**

Iterate on `mkdocs.yml` + `api/rest.md` until the strict build is green (no code change needed if
Phase 1 was correct). Re-mirror any template edits and re-run.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k docs_battery_builds_strict -v`
Expected: PASS.

- [ ] **Step 5: Stage (controller commits)**

```bash
git add tests/acceptance/test_rendered_project.py "src/framework_cli/template/{{ 'mkdocs.yml' if 'docs' in batteries else '' }}.jinja" CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `test(22b): acceptance — docs site builds --strict`.)

### Task 9: First `pre-commit` pass stays clean with the docs battery

**Files:**
- Test: `tests/acceptance/test_rendered_project.py`

A freshly generated project must make a clean first `pre-commit` pass (the framework guarantees this).
Confirm the docs payload doesn't break it (e.g. trailing-whitespace / end-of-file hooks on the new
markdown).

- [ ] **Step 1: Find the existing precommit acceptance test**

Run: `grep -n "precommit\|pre-commit\|pre_commit" tests/acceptance/test_rendered_project.py`
Expected: an existing `test_rendered_project_precommit_runs_clean` (or similar).

- [ ] **Step 2: Add a docs-battery variant (mirror the existing precommit test, with `batteries=["docs"]`)**

Copy the existing precommit test body, rename to
`test_rendered_project_precommit_clean_with_docs_battery`, and render with
`{**DATA, "batteries": ["docs"]}`. (Repeat the full body — do not abbreviate; the next engineer may
read this task in isolation. If the existing test uses a helper, call the same helper with the docs
batteries.)

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -k precommit_clean_with_docs -v`
Expected: PASS. If a markdown hook fails (e.g. missing final newline), fix the offending
`.md.jinja` template so the rendered output is hook-clean, then re-run.

- [ ] **Step 4: Stage (controller commits)**

```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
```

(Commit: `test(22b): generated project pre-commit clean with docs battery`.)

### Task 10: Full-suite green + branch-end review + merge prep

- [ ] **Step 1: Run the framework gate (source-only) + the render suite**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```
Expected: all green. (Template payload is excluded from `mypy src` by design.)

- [ ] **Step 2: Run the eval-fixture / no-docs invariant check**

The eval fixtures render *without* docs; confirm they're untouched:

```bash
uv run pytest tests/eval -q
```
Expected: PASS (the docs guards are inert without the battery, so fixtures are byte-identical).

- [ ] **Step 3: Render-matrix smoke (full battery set now includes docs)**

`ALL_BATTERIES` in `dogfood.py` resolves *all* battery names, so it now includes `docs`. Confirm the
all-batteries render + its `task ci` (which now runs `docs:build`) is sound by running the render-matrix
generator's tests:

```bash
uv run pytest tests/test_devmatrix.py tests/test_dogfood.py -q
```
Expected: PASS.

- [ ] **Step 4: Branch-end whole-branch review (Opus)**

Per the review-model policy, dispatch a **code-quality (Opus)** whole-branch review covering: the
no-docs byte-identical invariant, the strict-build gate, the mike publish decoupling (portable
`gh-pages` artifact, no forced Pages), and that the docs battery added no observability surface. Address
findings, re-run the gate.

- [ ] **Step 5: Update state + finish the branch**

Controller: update the `CLAUDE.md` Current-State pointer and the meta-plan 22b row to **22b COMPLETE**
(with the FF SHA on merge), then use `superpowers:finishing-a-development-branch` to merge
`plan-22b-docs` → `master`.

---

## Execution notes (read before starting)

**Review-model policy (restate per `CLAUDE.md`):** implementers → Sonnet (Haiku for trivial);
spec-compliance review → Sonnet; **code-quality review → Opus**; branch-end whole-branch review → Opus.
Pass `model` explicitly per role — do not let the generic "least powerful model" guidance collapse the
reviewers.

**Commit gate / cadence:** template-file edits over-fire the 18-agent gate. Use per-task light review +
the controller skip-marker recipe to commit (`CLAUDE.md` references `[[controller-skip-marker-recipe]]`
and `[[commit-gate-hook-timing]]`: stage with one call, commit with a separate call). The `CLAUDE.md`
state pointer + meta-plan row must be staged with every commit (PreToolUse hook enforces `CLAUDE.md` is
staged). Implementers stop before `git commit`; the controller verifies and commits.

**Template-payload TDD loop:** render to a tmp dir, `uv sync`, edit template source, re-render/mirror,
re-run. After hand-editing any rendered output, run `ruff format --check` on Python (not relevant to the
markdown/yaml here, but applies if you touch any `.py.jinja`).

**Open decisions resolved at build time (spec "open questions"):**
- **Swagger-render plugin:** the plan uses `mkdocs-render-swagger-plugin` (token `!!swagger openapi.json!!`).
  The Task 8 strict build is the gate — if the token/config needs adjustment, fix it there until strict is
  clean. Do not swap plugins without re-confirming the strict build + the `tests/test_copier_runner.py`
  `render_swagger` assertion.
- **Build gate placement:** build-strict lives in `ci.yml` (the canonical CI, render-matrix + dogfood
  coverage) and `docs.yml` is publish-only — a deliberate refinement of the spec's "docs.yml = build +
  publish" so the build gate isn't duplicated.
- **`docs:serve` uses `mike serve`** (versioned view) per the spec's DX intent.
```

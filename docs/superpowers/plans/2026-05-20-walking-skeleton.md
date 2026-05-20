# Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `framework` CLI's `new` command plus a minimal Copier template, so that `framework new "My App"` scaffolds a FastAPI project with `/heartbeat`, `/health`, and `/metrics` endpoints and a green test suite.

**Architecture:** The framework is a Python package (`framework_cli`) exposing a Typer CLI. The CLI is a thin shell over [Copier](https://copier.readthedocs.io/): `new` derives naming from the project name and renders a bundled Copier template into a new directory. The template ships inside the package at `src/framework_cli/template/` and produces a `uv`-managed FastAPI project whose own `uv run pytest` passes. This is the foundation every later plan builds on; it deliberately implements only `new` (not `upskill`/`integrity`/etc.) and a minimal template (no observability stack, no batteries, no AI agents — those are later plans).

**Tech Stack:** Python 3.12, [uv](https://docs.astral.sh/uv/) (packaging + venv), [Typer](https://typer.tiangolo.com/) (CLI), [Copier](https://copier.readthedocs.io/) (templating), [FastAPI](https://fastapi.tiangolo.com/) (generated app), pytest, [Taskfile](https://taskfile.dev/) (task runner), hatchling (build backend).

**Spec reference:** `docs/superpowers/specs/2026-05-20-framework-design.md` — this plan covers the minimal subset of §2 (Layer 1 template), §3 (template structure), §8 (health/heartbeat/metrics endpoints), §16 (`.copier-answers.yml`), and §18 (`framework new`).

**Prerequisites for the implementing engineer:**
- `uv` installed and on PATH (`uv --version` works). Install: https://docs.astral.sh/uv/getting-started/installation/
- `task` (Taskfile) installed for manual verification (Task 8 only). Install: https://taskfile.dev/installation/
- The repo is already a git repository with the spec committed. Run all commands from the repo root: `C:\Users\chris\Claude Code\Projects\framework`.

**Note on a spec correction surfaced while planning:** the spec writes the task-runner file as `TASKFILE.yml`, but the `task` tool only auto-discovers `Taskfile.yml` / `Taskfile.yaml` (and lowercase variants) — not all-caps `TASKFILE.yml`. This plan uses `Taskfile.yml`. The spec should be corrected to match in a later pass.

---

## File Structure

Framework repository layout after this plan:

```
framework/                                  (repo root — already git-init'd)
  pyproject.toml                            # framework_cli package definition
  .python-version                           # framework's own Python pin
  .gitignore                                # ignore .venv, caches
  Taskfile.yml                              # framework's own dev tasks
  README.md
  src/framework_cli/
    __init__.py                             # package version
    __main__.py                             # `python -m framework_cli`
    naming.py                               # derive_names(): name -> slug/package
    copier_runner.py                        # render_project(): wraps copier.run_copy
    cli.py                                  # Typer app + `new` command
    template/                               # Copier template source (bundled)
      copier.yml
      pyproject.toml.jinja
      Taskfile.yml.jinja
      README.md.jinja
      .python-version.jinja
      .gitignore
      .gitattributes
      {{ _copier_conf.answers_file }}.jinja # renders to .copier-answers.yml
      src/{{package_name}}/
        __init__.py
        main.py.jinja
        routes/
          __init__.py
          health.py.jinja
      tests/
        __init__.py
        unit/
          __init__.py
          test_health.py.jinja
  tests/
    test_naming.py                          # unit: derive_names
    test_copier_runner.py                   # unit: render produces expected files
    test_cli.py                             # integration: `new` command
    acceptance/
      test_rendered_project.py              # acceptance: rendered project's tests pass
```

**Responsibilities:**
- `naming.py` — pure string logic, no I/O. Easy to unit test.
- `copier_runner.py` — locates the bundled template and renders it. The only module that touches Copier.
- `cli.py` — argument parsing and orchestration only; delegates to `naming` and `copier_runner`.
- `template/` — the scaffold. Validated end-to-end by the render + acceptance tests, not by isolated unit tests.

---

## Task 1: Framework package skeleton + uv environment

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `Taskfile.yml`
- Create: `README.md`
- Create: `src/framework_cli/__init__.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_smoke.py`:

```python
import framework_cli


def test_package_has_version():
    assert isinstance(framework_cli.__version__, str)
    assert framework_cli.__version__
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli'` (or uv error: no pyproject). This confirms nothing is set up yet.

- [ ] **Step 3: Create the framework package definition**

Create `pyproject.toml`:

```toml
[project]
name = "framework-cli"
version = "0.1.0"
description = "CLI scaffold framework for solid, observable, testable Python projects"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.15",
    "copier>=9.4",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "ruff>=0.8",
    "mypy>=1.13",
    "fastapi>=0.115",
    "httpx>=0.28",
]

[project.scripts]
framework = "framework_cli.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/framework_cli"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
src = ["src", "tests"]

[tool.mypy]
files = ["src"]
python_version = "3.12"
```

Create `.python-version`:

```
3.12
```

Create `.gitignore`:

```
.venv/
__pycache__/
*.py[co]
.pytest_cache/
.ruff_cache/
.mypy_cache/
dist/
build/
*.egg-info/
```

Create `Taskfile.yml`:

```yaml
version: '3'

tasks:
  test:
    desc: Run the framework test suite
    cmds:
      - uv run pytest -q

  lint:
    desc: Lint and type-check the framework
    cmds:
      - uv run ruff check .
      - uv run mypy src
```

Create `README.md`:

```markdown
# framework

A CLI scaffold framework for building solid, observable, testable Python applications.

## Development

```bash
uv sync
uv run pytest -q
```

## Usage

```bash
framework new "My App"
```
```

Create `src/framework_cli/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Sync the environment and run the smoke test**

Run: `uv sync`
Expected: creates `.venv`, installs typer, copier, and dev deps.

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS — `test_package_has_version PASSED`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .python-version .gitignore Taskfile.yml README.md src/framework_cli/__init__.py tests/test_smoke.py
git commit -m "feat: framework package skeleton with uv environment"
```

---

## Task 2: `derive_names` — naming logic

**Files:**
- Create: `src/framework_cli/naming.py`
- Test: `tests/test_naming.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_naming.py`:

```python
from framework_cli.naming import ProjectNames, derive_names


def test_simple_name():
    names = derive_names("My App")
    assert names == ProjectNames(
        project_name="My App",
        project_slug="my-app",
        package_name="my_app",
    )


def test_name_with_punctuation_and_extra_spaces():
    names = derive_names("  Cool!! Service 2  ")
    assert names.project_slug == "cool-service-2"
    assert names.package_name == "cool_service_2"


def test_already_slug_like():
    names = derive_names("data-pipeline")
    assert names.project_slug == "data-pipeline"
    assert names.package_name == "data_pipeline"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.naming'`.

- [ ] **Step 3: Implement the naming module**

Create `src/framework_cli/naming.py`:

```python
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectNames:
    project_name: str
    project_slug: str
    package_name: str


def derive_names(name: str) -> ProjectNames:
    """Derive a directory slug and Python package name from a human project name."""
    lowered = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    package = slug.replace("-", "_")
    return ProjectNames(
        project_name=name.strip(),
        project_slug=slug,
        package_name=package,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_naming.py -v`
Expected: PASS — all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/naming.py tests/test_naming.py
git commit -m "feat: derive project slug and package name from project name"
```

---

## Task 3: Copier template — project configuration files

This task creates the static scaffold files (no app code yet — that is Task 4). These are template assets; they are validated by the render test in Task 5, not by a unit test here.

**Files:**
- Create: `src/framework_cli/template/copier.yml`
- Create: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `src/framework_cli/template/Taskfile.yml.jinja`
- Create: `src/framework_cli/template/README.md.jinja`
- Create: `src/framework_cli/template/.python-version.jinja`
- Create: `src/framework_cli/template/.gitignore`
- Create: `src/framework_cli/template/.gitattributes`
- Create: `src/framework_cli/template/{{ _copier_conf.answers_file }}.jinja`

- [ ] **Step 1: Create the Copier questions file**

Create `src/framework_cli/template/copier.yml`:

```yaml
_templates_suffix: .jinja

project_name:
  type: str
  help: Human-readable project name

project_slug:
  type: str
  help: Directory / repository slug
  default: "{{ project_name | lower | replace(' ', '-') | replace('_', '-') }}"

package_name:
  type: str
  help: Python package name
  default: "{{ project_slug | lower | replace('-', '_') }}"

python_version:
  type: str
  help: Python version to target
  default: "3.12"
```

- [ ] **Step 2: Create the generated project's `pyproject.toml` template**

Create `src/framework_cli/template/pyproject.toml.jinja`:

```toml
[project]
name = "{{ project_slug }}"
version = "0.1.0"
requires-python = ">={{ python_version }}"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{{ package_name }}"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Create the generated project's Taskfile template**

Create `src/framework_cli/template/Taskfile.yml.jinja`:

```yaml
version: '3'

tasks:
  dev:
    desc: Run the app locally with hot reload
    cmds:
      - uv run uvicorn {{ package_name }}.main:app --reload --port 8000

  test:
    desc: Run the test suite
    cmds:
      - uv run pytest -q

  lint:
    desc: Lint and type-check
    cmds:
      - uv run ruff check .
      - uv run mypy src
```

> Note: this file is rendered by Jinja, so `{{ package_name }}` is substituted at scaffold time. The Taskfile contains no Go-template (`{{ "{{" }}.VAR{{ "}}" }}`) syntax yet; when a later plan adds Go-template expressions to a Taskfile, wrap them in `{% raw %}…{% endraw %}` so Jinja leaves them intact.

- [ ] **Step 4: Create the generated project's README template**

Create `src/framework_cli/template/README.md.jinja`:

```markdown
# {{ project_name }}

Generated by the framework.

## Quickstart

```bash
uv sync
task dev      # run the app at http://localhost:8000
task test     # run the test suite
```

## Endpoints

- `GET /heartbeat` — liveness ping
- `GET /health` — readiness + SLO status
- `GET /metrics` — Prometheus metrics
```

- [ ] **Step 5: Create the remaining dotfiles**

Create `src/framework_cli/template/.python-version.jinja`:

```
{{ python_version }}
```

Create `src/framework_cli/template/.gitignore`:

```
.venv/
__pycache__/
*.py[co]
.env
.pytest_cache/
.ruff_cache/
.mypy_cache/
dist/
build/
*.egg-info/
```

Create `src/framework_cli/template/.gitattributes`:

```
* text=auto eol=lf
```

- [ ] **Step 6: Create the Copier answers-file template**

Create `src/framework_cli/template/{{ _copier_conf.answers_file }}.jinja`:

```jinja
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
{{ _copier_answers | to_nice_yaml }}
```

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/
git commit -m "feat: copier template config and project scaffolding files"
```

---

## Task 4: Copier template — application code and tests

This task adds the FastAPI app (the three monitoring endpoints) and the generated project's own test suite to the template.

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/main.py.jinja`
- Create: `src/framework_cli/template/src/{{package_name}}/routes/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Create: `src/framework_cli/template/tests/__init__.py`
- Create: `src/framework_cli/template/tests/unit/__init__.py`
- Create: `src/framework_cli/template/tests/unit/test_health.py.jinja`

- [ ] **Step 1: Create the package init files (empty, copied verbatim)**

Create `src/framework_cli/template/src/{{package_name}}/__init__.py` (empty file).

Create `src/framework_cli/template/src/{{package_name}}/routes/__init__.py` (empty file).

Create `src/framework_cli/template/tests/__init__.py` (empty file).

Create `src/framework_cli/template/tests/unit/__init__.py` (empty file).

- [ ] **Step 2: Create the health routes template**

Create `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`:

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter()

_METRICS_BODY = (
    "# HELP app_up Application up indicator\n"
    "# TYPE app_up gauge\n"
    "app_up 1\n"
)


@router.get("/heartbeat", response_class=PlainTextResponse)
def heartbeat() -> PlainTextResponse:
    """Liveness ping — the process is up. No dependency checks."""
    return PlainTextResponse("OK", status_code=200)


@router.get("/health")
def health() -> JSONResponse:
    """Readiness + SLO status. Walking skeleton: SLO evaluation arrives in a later plan."""
    return JSONResponse({"status": "ok", "slos": {}}, status_code=200)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    """Prometheus exposition format. Walking skeleton: a single static gauge."""
    return PlainTextResponse(
        _METRICS_BODY,
        status_code=200,
        media_type="text/plain; version=0.0.4",
    )
```

- [ ] **Step 3: Create the app entry point template**

Create `src/framework_cli/template/src/{{package_name}}/main.py.jinja`:

```python
from fastapi import FastAPI

from {{ package_name }}.routes import health


def create_app() -> FastAPI:
    app = FastAPI(title="{{ project_name }}")
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 4: Create the generated project's test template**

Create `src/framework_cli/template/tests/unit/test_health.py.jinja`:

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import app

client = TestClient(app)


def test_heartbeat_returns_ok():
    response = client.get("/heartbeat")
    assert response.status_code == 200
    assert response.text == "OK"


def test_health_returns_slo_structure():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "slos" in body


def test_metrics_is_prometheus_text():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "app_up 1" in response.text
```

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/src src/framework_cli/template/tests
git commit -m "feat: scaffold FastAPI app with health/heartbeat/metrics and tests"
```

---

## Task 5: `render_project` — wrap Copier

**Files:**
- Create: `src/framework_cli/copier_runner.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_copier_runner.py`:

```python
from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def test_render_creates_expected_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    assert (dest / "pyproject.toml").is_file()
    assert (dest / "Taskfile.yml").is_file()
    assert (dest / ".copier-answers.yml").is_file()
    assert (dest / "src" / "demo" / "main.py").is_file()
    assert (dest / "src" / "demo" / "routes" / "health.py").is_file()
    assert (dest / "tests" / "unit" / "test_health.py").is_file()


def test_render_substitutes_package_name(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    main_py = (dest / "src" / "demo" / "main.py").read_text()
    assert "from demo.routes import health" in main_py
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.copier_runner'`.

- [ ] **Step 3: Implement the Copier runner**

Create `src/framework_cli/copier_runner.py`:

```python
from importlib.resources import files
from pathlib import Path

from copier import run_copy


def template_path() -> Path:
    """Absolute path to the bundled Copier template directory."""
    return Path(str(files("framework_cli"))) / "template"


def render_project(dest: Path, data: dict[str, str]) -> None:
    """Render the bundled template into `dest` using the provided answers."""
    run_copy(
        str(template_path()),
        str(dest),
        data=data,
        defaults=True,
        overwrite=True,
        quiet=True,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py -v`
Expected: PASS — both tests pass, confirming the template renders and `{{ package_name }}` is substituted.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/copier_runner.py tests/test_copier_runner.py
git commit -m "feat: render bundled copier template into a destination directory"
```

---

## Task 6: Acceptance — the rendered project's own tests pass

This is the key acceptance test for the walking skeleton (and the seed of the §20 dogfooding strategy): render a project, then run *its* test suite with `uv` and assert green.

**Files:**
- Create: `tests/acceptance/__init__.py`
- Create: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing/acceptance test**

Create `tests/acceptance/__init__.py` (empty file).

Create `tests/acceptance/test_rendered_project.py`:

```python
import shutil
import subprocess
from pathlib import Path

import pytest

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_passes_its_own_tests(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "pytest", "-q"], cwd=dest)
    assert result.returncode == 0, "the generated project's test suite did not pass"
```

- [ ] **Step 2: Run the acceptance test**

Run: `uv run pytest tests/acceptance/test_rendered_project.py -v`
Expected: PASS. (This is slow — it creates a venv and installs FastAPI inside the temp project. If `uv` is missing it SKIPS rather than fails.)

If it FAILS, read the captured pytest output from the subprocess — the most likely causes are a typo in a `.jinja` template or a missing `__init__.py` in the template's package tree. Fix the template and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/acceptance/__init__.py tests/acceptance/test_rendered_project.py
git commit -m "test: acceptance test that rendered projects pass their own suite"
```

---

## Task 7: CLI `new` command

**Files:**
- Create: `src/framework_cli/cli.py`
- Create: `src/framework_cli/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from framework_cli.cli import app

runner = CliRunner()


def test_new_creates_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "my-app" / "pyproject.toml").is_file()
    assert (tmp_path / "my-app" / "src" / "my_app" / "main.py").is_file()
    assert (tmp_path / "my-app" / ".copier-answers.yml").is_file()


def test_new_rejects_existing_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my-app").mkdir()
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 1
    assert "already exists" in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.cli'`.

- [ ] **Step 3: Implement the CLI**

Create `src/framework_cli/cli.py`:

```python
from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.naming import derive_names

app = typer.Typer(
    help="Framework CLI — scaffold solid, observable, testable Python projects.",
    no_args_is_help=True,
)


@app.command()
def new(
    name: str = typer.Argument(..., help="Human-readable project name"),
    python_version: str = typer.Option("3.12", help="Python version to target"),
) -> None:
    """Scaffold a new project from the framework template."""
    names = derive_names(name)
    dest = Path.cwd() / names.project_slug

    if dest.exists():
        typer.echo(f"Error: {dest} already exists", err=True)
        raise typer.Exit(code=1)

    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "package_name": names.package_name,
            "python_version": python_version,
        },
    )
    typer.echo(f"Created '{names.project_slug}' at {dest}")
```

Create `src/framework_cli/__main__.py`:

```python
from framework_cli.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS — both tests pass.

- [ ] **Step 5: Run the full suite and lint**

Run: `uv run pytest -q`
Expected: all tests pass (smoke, naming, copier_runner, cli, acceptance).

Run: `uv run ruff check .`
Expected: no errors (or auto-fixable ones — run `uv run ruff check . --fix` if needed, then re-run).

Run: `uv run mypy src`
Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/cli.py src/framework_cli/__main__.py tests/test_cli.py
git commit -m "feat: framework new command scaffolds a project"
```

---

## Task 8: Manual end-to-end verification

This task is human verification of the real `framework new` experience — not an automated test.

**Files:** none (verification only).

- [ ] **Step 1: Install the CLI into the environment**

Run: `uv sync`
Then confirm the entry point is available: `uv run framework --help`
Expected: Typer help text showing the `new` command.

- [ ] **Step 2: Scaffold a real project in a scratch directory**

Run:

```bash
cd /tmp                       # or any scratch dir outside the framework repo (Windows: cd $env:TEMP)
uv run --project "C:/Users/chris/Claude Code/Projects/framework" framework new "Hello Service"
```

Expected: output `Created 'hello-service' at .../hello-service`, and a `hello-service/` directory exists.

- [ ] **Step 2 (alternative if the above path handling is awkward on Windows):**

From the framework repo root, run a throwaway scaffold into a temp dir:

```bash
uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('a:/tmp/hello-service' if False else 'hello-service-demo'), {'project_name':'Hello Service','project_slug':'hello-service','package_name':'hello_service','python_version':'3.12'})"
```

Then inspect `hello-service-demo/`. Delete it afterward (`rm -rf hello-service-demo` / `Remove-Item -Recurse -Force hello-service-demo`). Do not commit it.

- [ ] **Step 3: Run the generated project's tasks**

```bash
cd hello-service              # (or hello-service-demo)
uv sync
task test
```

Expected: `task test` runs `uv run pytest -q` and reports 3 passing tests.

Optionally start the app: `task dev`, then in another shell `curl -s http://localhost:8000/heartbeat` → `OK`, `curl -s http://localhost:8000/health` → `{"status":"ok","slos":{}}`, `curl -s http://localhost:8000/metrics` → contains `app_up 1`. Stop the server when done.

- [ ] **Step 4: Clean up**

Delete the scratch project directory. Confirm `git status` in the framework repo is clean (the scratch project must not be inside the repo or tracked).

- [ ] **Step 5: Final confirmation**

The walking skeleton is complete when: `uv run pytest -q` is green in the framework repo, `framework new` produces a project, and that project's `task test` is green. This is the foundation Plan 2 (quality gates) builds on.

---

## Self-Review

**1. Spec coverage (walking-skeleton subset):**
- §2 Layer 1 (Copier template, CLI as thin shell) → Tasks 3–5, 7 ✓
- §3 template structure (minimal subset: src/, tests/, pyproject, Taskfile, dotfiles, answers file) → Tasks 3–4 ✓
- §8 `/heartbeat` (liveness), `/health` (SLO JSON), `/metrics` (Prometheus text) — roles match the spec's endpoint table → Task 4 ✓
- §16 `.copier-answers.yml` recorded → Task 3 Step 6 ✓
- §18 `framework new <name>` → Task 7 ✓
- **Deliberately out of scope** (later plans): observability stack, batteries, pre-commit, Layer 2 CLAUDE.md/hooks, CI/CD, integrity, upskill, AI agents. Not gaps — sequenced per the plan decomposition.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle errors appropriately" present. Every code step shows complete code; every run step shows the exact command and expected output.

**3. Type consistency:** `derive_names` returns `ProjectNames` (project_name/project_slug/package_name), used consistently in Tasks 2 and 7. `render_project(dest: Path, data: dict[str, str])` defined in Task 5, called identically in Tasks 5, 6, and 7. The four data keys (project_name, project_slug, package_name, python_version) match the `copier.yml` questions in Task 3. Endpoint paths (`/heartbeat`, `/health`, `/metrics`) match between the routes (Task 4 Step 2) and the generated tests (Task 4 Step 4).

---

*End of plan.*

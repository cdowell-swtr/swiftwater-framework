# Quality Gates Implementation Plan (Plan 2 of 9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every generated project ship working quality gates out of the box — a coverage model with a threshold, a pre-commit hook set, and a `CLAUDE.md` encoding the framework's TDD contract — all validated by the framework's own render + acceptance tests.

**Architecture:** This plan adds files to the bundled Copier template at `src/framework_cli/template/` (it does not change the `framework_cli` CLI). New template files: `.pre-commit-config.yaml`, `CLAUDE.md.jinja`; plus edits to `pyproject.toml.jinja` (coverage + new dev deps), `Taskfile.yml.jinja` (coverage/hooks tasks), and `README.md.jinja`. The framework's existing tests (`tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`) are extended to prove the new files render and that a rendered project's coverage gate and pre-commit config are valid.

**Tech Stack:** pytest-cov (coverage with branch + contexts), coverage.py, pre-commit (ruff, mypy, gitleaks, file-hygiene hooks, a local coverage hook), Copier/Jinja, uv.

**Spec reference:** `docs/superpowers/specs/2026-05-20-framework-design.md` — §4 (CLAUDE.md TDD contract / conventions), §5 (pre-commit layer), §6 (coverage model).

**Scope boundaries (intentionally NOT in this plan):**
- Layer-2 Claude Code editor hooks (`.claude/settings.json` PostToolUse) → **Plan 2b**, after the hook schema is verified.
- The full multi-file-type linter set (hadolint, actionlint, shellcheck, eslint, stylelint, prettier) → added with the batteries/files that introduce those file types (Dockerfiles in Plan 3, workflows in Plan 5, React in Plan 8). This plan wires only the linters whose target files already exist in the walking-skeleton template: Python (`ruff`, `mypy`), TOML (`taplo`/`check-toml`), YAML (`check-yaml`), and generic file hygiene + secrets.
- Suite-type coverage *contexts* (unit vs functional vs e2e as separate labels): this plan establishes coverage infrastructure with per-test dynamic contexts and a threshold gate. The unit/functional/e2e split becomes meaningful when those suites exist (e2e arrives in a later plan) and is finalized in the CI plan (Plan 5). Noted explicitly so it is not mistaken for a gap.
- The framework's OWN dogfooding gates → Plan 9.

**Prerequisites:** `uv` on PATH (`uv --version` works). The repo is on `master` with Plan 1 merged; create a feature branch before implementing. Run commands from the repo root.

---

## File Structure

Template files after this plan (changes marked):

```
src/framework_cli/template/
  copier.yml
  pyproject.toml.jinja          # EDIT: add pytest-cov + pre-commit dev deps; add [tool.coverage.*]
  Taskfile.yml.jinja            # EDIT: add test:cov, hooks, hooks:run tasks
  README.md.jinja               # EDIT: document coverage + pre-commit
  .pre-commit-config.yaml       # NEW: pre-commit hook definitions (static, no Jinja)
  CLAUDE.md.jinja               # NEW: hybrid file — locked FRAMEWORK section + builder area
  .python-version.jinja
  .gitignore
  .gitattributes
  {{ _copier_conf.answers_file }}.jinja
  src/{{package_name}}/...      # unchanged
  tests/...                     # unchanged
```

Framework test files extended:

```
tests/
  test_copier_runner.py         # EDIT: assert new template files render
  acceptance/
    test_rendered_project.py    # EDIT: assert coverage gate + pre-commit config validate in rendered project
```

**Responsibilities:** `.pre-commit-config.yaml` owns deterministic local checks; `CLAUDE.md` owns development-time instructions; coverage config in `pyproject.toml` owns the measurement + threshold. The render test proves files exist; the acceptance test proves they actually work in a generated project.

---

## Task 1: Coverage model in the generated project

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`
- Test: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing render-test assertions**

Add to `tests/test_copier_runner.py` (a new test function):

```python
def test_render_includes_coverage_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pytest-cov" in pyproject
    assert "[tool.coverage.run]" in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:cov" in taskfile
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_coverage_config -v`
Expected: FAIL — `pytest-cov` / `[tool.coverage.run]` not yet in the rendered `pyproject.toml`.

- [ ] **Step 3: Add coverage config to the template `pyproject.toml.jinja`**

Edit `src/framework_cli/template/pyproject.toml.jinja`. Change the `[dependency-groups]` `dev` list to add `pytest-cov`:

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
]
```

Then append these two new sections at the end of the file (after `[tool.pytest.ini_options]`):

```toml
[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false
```

- [ ] **Step 4: Add the coverage task to `Taskfile.yml.jinja`**

Edit `src/framework_cli/template/Taskfile.yml.jinja`. Add a `test:cov` task after the existing `test` task (keep `test` as-is for the fast no-coverage run):

```yaml
  test:cov:
    desc: Run tests with coverage and enforce the threshold
    cmds:
      - uv run pytest --cov --cov-context=test --cov-report=term-missing --cov-fail-under=70 -q
```

- [ ] **Step 5: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_coverage_config -v`
Expected: PASS.

- [ ] **Step 6: Extend the acceptance test to prove coverage works in a rendered project**

Add to `tests/acceptance/test_rendered_project.py` a new test (mirror the existing skipif on `uv`):

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "task", "test:cov"], cwd=dest)
    # 'task' may be absent in CI; fall back to invoking pytest directly.
    if result.returncode == 127 or shutil.which("task") is None:
        result = subprocess.run(
            ["uv", "run", "pytest", "--cov", "--cov-fail-under=70", "-q"], cwd=dest
        )
    assert result.returncode == 0, "coverage gate did not pass in the generated project"
```

- [ ] **Step 7: Run the acceptance test (slow) to verify it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_coverage_gate_passes -v`
Expected: PASS — the rendered demo project's three health tests give 100% coverage of its tiny `src`, comfortably above 70%.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
git commit -m "feat: scaffold coverage model with threshold gate in generated projects"
```

---

## Task 2: Pre-commit hooks in the generated project

**Files:**
- Create: `src/framework_cli/template/.pre-commit-config.yaml`
- Modify: `src/framework_cli/template/pyproject.toml.jinja` (add `pre-commit` dev dep)
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` (add `hooks`, `hooks:run`)
- Test: `tests/test_copier_runner.py`
- Test: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the failing render-test assertions**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_precommit_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    cfg = dest / ".pre-commit-config.yaml"
    assert cfg.is_file()
    text = cfg.read_text()
    assert "ruff" in text
    assert "mypy" in text
    assert "gitleaks" in text

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pre-commit" in pyproject
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_precommit_config -v`
Expected: FAIL — `.pre-commit-config.yaml` does not exist in the rendered project.

- [ ] **Step 3: Create `.pre-commit-config.yaml` in the template**

Create `src/framework_cli/template/.pre-commit-config.yaml` (static file, no Jinja). The Python checks use `language: system` so they run inside the project's uv-managed environment rather than pre-commit-managed venvs:

```yaml
# Deterministic, fast quality gate. Runs on every commit.
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: mixed-line-ending
        args: [--fix=lf]
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks

  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
        require_serial: true
      - id: mypy
        name: mypy
        entry: uv run mypy src
        language: system
        pass_filenames: false
        types: [python]
        require_serial: true
      - id: coverage-threshold
        name: unit + functional coverage (>=70%)
        entry: uv run pytest --cov --cov-fail-under=70 -q
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
```

- [ ] **Step 4: Add `pre-commit` to the template dev deps**

Edit `src/framework_cli/template/pyproject.toml.jinja` `[dependency-groups]` `dev` to include `pre-commit` (final list):

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
]
```

- [ ] **Step 5: Add hook tasks to `Taskfile.yml.jinja`**

Add after `test:cov`:

```yaml
  hooks:
    desc: Install git pre-commit hooks
    cmds:
      - uv run pre-commit install

  hooks:run:
    desc: Run all pre-commit hooks against all files
    cmds:
      - uv run pre-commit run --all-files
```

- [ ] **Step 6: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_precommit_config -v`
Expected: PASS.

- [ ] **Step 7: Add an acceptance check that the pre-commit config is valid**

Validating the config offline (without fetching hook repos or running them) keeps the test fast and network-light. Add to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_precommit_config_is_valid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "validate-config", ".pre-commit-config.yaml"],
        cwd=dest,
    )
    assert result.returncode == 0, "pre-commit config is invalid"
```

- [ ] **Step 8: Run the acceptance test to verify it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_config_is_valid -v`
Expected: PASS — `pre-commit validate-config` returns 0 for a well-formed config.

- [ ] **Step 9: Commit**

```bash
git add src/framework_cli/template/.pre-commit-config.yaml src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
git commit -m "feat: scaffold pre-commit quality gate in generated projects"
```

---

## Task 3: CLAUDE.md TDD contract in the generated project

**Files:**
- Create: `src/framework_cli/template/CLAUDE.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render-test assertion**

Add to `tests/test_copier_runner.py`:

```python
def test_render_includes_claude_md(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    claude = dest / "CLAUDE.md"
    assert claude.is_file()
    text = claude.read_text()
    # Hybrid file: framework-owned section is delimited by markers (Plan 6 will checksum it).
    assert "<!-- FRAMEWORK:BEGIN -->" in text
    assert "<!-- FRAMEWORK:END -->" in text
    # Project name is interpolated into the heading.
    assert "Demo" in text
    # Core TDD contract is present.
    assert "write the failing test first" in text.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_claude_md -v`
Expected: FAIL — `CLAUDE.md` does not exist in the rendered project.

- [ ] **Step 3: Create `CLAUDE.md.jinja` in the template**

Create `src/framework_cli/template/CLAUDE.md.jinja`. The framework-owned guidance sits between the markers; content outside the markers is the builder's to edit (Plan 6 will checksum only the marked region):

```markdown
# {{ project_name }} — Working Agreement

<!-- FRAMEWORK:BEGIN -->
<!-- This section is managed by the framework. Edit outside the markers; framework upgrades may rewrite this block. -->

## Test-Driven Development (required)

Write the failing test first, confirm it fails (red), implement the minimum to pass, confirm it passes (green). Do not write implementation code before its test.

Apply the testing obligation that matches what you are building:

| What you are building | Required tests |
|---|---|
| Any code unit | Unit tests — red first, then green |
| Any behaviour or feature | Functional tests — assert outcomes, not implementation |
| A non-functional requirement | Non-functional tests (performance, load, resilience) |
| Any service | Health / heartbeat / metrics endpoints as part of the skeleton |
| A consumer-facing surface (API, webhook, UI, WebSocket) | End-to-end tests against the running stack |

Map the full outcome space before considering a unit done: happy path; every error case; edge cases (empty, null, boundary, concurrent, maximum); and — for consumer-facing surfaces — at least one unhappy end-to-end path.

## Non-functional heuristics

Scaffold a non-functional test (with an explicit threshold) when code: operates on an unbounded/variable-size collection; is I/O-bound (DB, HTTP, file); sits in a hot path; does CPU-bound processing; has retry/circuit-breaker logic; or depends on an external service.

## Conventions

- Read all configuration through the settings object — never hardcode config or secrets.
- Use the structured logger, not `print()`; include context with each log entry.
- Never use a bare `except`; handle every identified error case explicitly.
- Relational schema changes require a new migration; never edit an existing migration.
- Updating an API endpoint requires updating its contract test.

## Quality commands

- `task test` — fast test run
- `task test:cov` — tests with coverage (must stay >= 70%)
- `task lint` — ruff + mypy
- `task hooks` — install pre-commit; `task hooks:run` — run all hooks

<!-- FRAMEWORK:END -->

## Project notes

_Add project-specific context for collaborators and AI assistants here. This area is yours; the framework will not overwrite it._
```

- [ ] **Step 4: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_claude_md -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/CLAUDE.md.jinja tests/test_copier_runner.py
git commit -m "feat: scaffold CLAUDE.md TDD contract in generated projects"
```

---

## Task 4: Document the gates and verify the whole rendered project

**Files:**
- Modify: `src/framework_cli/template/README.md.jinja`
- Test: full suite + manual render verification

- [ ] **Step 1: Update the template README**

Edit `src/framework_cli/template/README.md.jinja`. Replace the `## Quickstart` and `## Endpoints` body so it documents the gates (keep the existing nested code-fence style):

```markdown
# {{ project_name }}

Generated by the framework.

## Quickstart

```bash
uv sync
task hooks     # install pre-commit hooks
task dev       # run the app at http://localhost:8000
task test      # fast test run
task test:cov  # tests with coverage (>= 70%)
task lint      # ruff + mypy
```

## Quality gates

- TDD is the workflow — see `CLAUDE.md`.
- `task test:cov` enforces a 70% coverage floor.
- Pre-commit runs ruff, mypy, gitleaks, file hygiene, and the coverage gate on every commit (`task hooks` to install).

## Endpoints

- `GET /heartbeat` — liveness ping
- `GET /health` — readiness + SLO status
- `GET /metrics` — Prometheus metrics
```

- [ ] **Step 2: Add a render assertion for the README update**

Add to `tests/test_copier_runner.py`:

```python
def test_render_readme_documents_gates(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    readme = (dest / "README.md").read_text()
    assert "Quality gates" in readme
    assert "task test:cov" in readme
```

- [ ] **Step 3: Run the full framework test suite + lint**

Run: `uv run pytest -q`
Expected: all tests pass (smoke, naming, copier_runner incl. the 4 new render tests, cli, acceptance incl. the 2 new acceptance tests).

Run: `uv run ruff check .` → no errors. Run: `uv run mypy src` → `Success`.

- [ ] **Step 4: Manual end-to-end verification**

In a scratch dir OUTSIDE the repo (e.g. `/tmp/fw-q2`):

```bash
uv run --project /path/to/swiftwater-framework framework new "Quality Demo"
cd quality-demo
uv sync
task test:cov                                   # expect coverage >= 70%, all green
uv run pre-commit validate-config .pre-commit-config.yaml   # expect exit 0
```

Confirm `CLAUDE.md` exists with the `FRAMEWORK:BEGIN/END` markers and the project name in the heading. Then delete the scratch dir and confirm `git status` in the framework repo is clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/README.md.jinja tests/test_copier_runner.py
git commit -m "docs: document quality gates in generated project README"
```

---

## Self-Review

**1. Spec coverage (Plan 2 subset):**
- §6 Coverage model → Task 1 (pytest-cov, branch coverage, threshold gate, dynamic contexts). Suite-type context separation explicitly deferred to when e2e/functional suites exist (noted in scope) — not a gap.
- §5 Pre-commit layer → Task 2 (ruff, mypy, gitleaks, file hygiene, check-yaml/toml, coverage hook). File-type linters for files that don't exist yet (Dockerfile/workflow/JS) deferred to the plans that introduce those files — noted in scope.
- §4 CLAUDE.md TDD contract / conventions → Task 3 (hybrid file with markers, obligations table, NFR heuristics, outcome-space mapping, conventions).
- §4 Layer-2 Claude Code editor hooks → explicitly carved to Plan 2b (schema verification) — stated in scope, not a silent omission.

**2. Placeholder scan:** No "TBD"/"handle appropriately". Every code step shows complete file content or a complete diff; every run step gives the exact command and expected result. The acceptance tests fall back to a direct `pytest`/`pre-commit` invocation when `task` is absent, so they don't depend on Taskfile being installed in CI.

**3. Type/consistency check:** The render tests reuse the existing module-level `DATA` dict and `render_project` import already present in `tests/test_copier_runner.py` and `tests/acceptance/test_rendered_project.py` from Plan 1 — no new fixtures introduced. Task/section names (`test:cov`, `hooks`, `hooks:run`) are identical across the Taskfile, README, CLAUDE.md, and acceptance test. The 70% threshold is consistent across `test:cov`, the pre-commit `coverage-threshold` hook, and CLAUDE.md.

---

*End of plan.*

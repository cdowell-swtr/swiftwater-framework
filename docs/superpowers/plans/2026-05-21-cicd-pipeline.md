# CI Pipeline (Plan 5a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects ship an authoritative GitHub Actions CI pipeline from day one — `integrity (seam) → lint → unit/functional/e2e tests with coverage contexts → build → combined 85% coverage gate → OpenAPI contract diff → dependency + secret security → review-agents (seam)` — plus the local `task ci` pre-flight, an e2e test tier, dependabot, and pip-audit.

**Architecture:** Everything is **template payload** under `src/framework_cli/template/`, rendered into every generated project and validated two ways: (1) framework-side render assertions in `tests/test_copier_runner.py` (files render / interpolate / contain the right structure), and (2) Docker-gated acceptance behavior in `tests/acceptance/test_rendered_project.py` (the generated project's own e2e suite, the combined coverage gate, the OpenAPI export, and the no-Docker `pre-commit run --all-files` cleanliness pass — which now also exercises the new `actionlint` + `shellcheck` hooks). GitHub Actions YAML cannot be executed locally, so the workflow itself is validated by **rendering + `actionlint`**, while the logic it invokes (the coverage gate, the OpenAPI export, the e2e suite) lives in testable scripts/tests that the framework *does* run.

**Tech Stack:** GitHub Actions, `uv` + `astral-sh/setup-uv`, `coverage.py` static contexts (`coverage run --context=<suite>`), `pytest` + FastAPI `TestClient` + testcontainers Postgres (e2e), `pip-audit`, `gitleaks-action` (full-history secrets), `oasdiff` (breaking-change OpenAPI diff), `actionlint` + `shellcheck` (pre-commit). Generated-project gates: `ruff`, `mypy`, coverage ≥ 70% (pre-commit, unit+functional) / ≥ 85% (CI, unit+functional+e2e).

**Source spec:** `docs/superpowers/specs/2026-05-20-framework-design.md` §14 (CI/CD pipeline, steps 0–8), §6 (coverage contexts + stage thresholds), §11 (API contracts + versioning — OpenAPI export/diff), §12 (dependency security — pip-audit, dependabot, gitleaks), §5 (pre-commit linter set), §9/§15 (`task ci` vs `task push`). Roadmap row: Plan 5 in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## Scope & Non-Goals

This is **Plan 5a** — the generated project's **CI pipeline** only. Plan 5 was sliced (confirmed with the user during planning, mirroring the Plan 3 → 3a/3b/3c precedent):

- **5a (this plan):** the authoritative per-PR/per-push CI pipeline + supporting test/coverage/contract/security scaffolding.
- **5b (next):** the deploy seam — `deploy-staging.yml` / `deploy-prod.yml`, the deploy-strategy contract, and the four-phase validation sequence (smoke → sniff → E2E → load). **Out of scope here.**

**In scope (spec §14 CI steps 0–8, plus §6/§11/§12/§5 pieces they depend on):**
1. **Coverage suite-type contexts** (unit / functional / e2e as distinct labels) — *the item explicitly deferred from Plan 2 to "finalize in Plan 5"* — via a reusable `scripts/coverage.sh`.
2. **E2E test tier** (`tests/e2e/`) with at least one happy and one **unhappy** path against the full app + real Postgres, tagged with the `e2e` coverage context.
3. **Combined coverage gate** — 70% (unit+functional) in pre-commit, **85%** (unit+functional+e2e) in CI (§6 thresholds).
4. **OpenAPI contract** — `scripts/export-openapi.sh` + `task openapi:export`; CI enforces the committed `openapi.json` is current and runs `oasdiff` for breaking-change classification (§11).
5. **Dependency + secret security** — `pip-audit` (dep + `task audit` + CI step), `.github/dependabot.yml`, full-history `gitleaks` in CI (§12).
6. **Workflow file-type linting** — `actionlint` (workflows) + `shellcheck` (scripts) added to pre-commit + `task lint` + CI (§5; the carried-forward "workflows → Plan 5" note).
7. **The CI workflow** `.github/workflows/ci.yml` — orchestrates the above with `integrity` (Plan 6) and `review` (Plan 7) as documented seam jobs.
8. **`task ci`** — the local full-suite pre-flight (§9/§15) that runs lint + the 85% gate + audit + OpenAPI export before `task push`.

**Explicit non-goals (deferred, with rationale):**
- **Deploy workflows + deploy-strategy contract + 4-phase validation** → **Plan 5b**. No concrete deploy target is chosen (spec §21), so even the seam is its own slice.
- **Framework integrity (CI step 0)** → **Plan 6**. The integrity CLI doesn't exist yet; `ci.yml` ships an `integrity` seam job preserving the step-0 ordering.
- **AI review agents + aggregator (CI steps 9–10)** → **Plan 7**. `ci.yml` ships a `review` seam job (`needs: [test, contract]`) preserving the ordering; the 15 agents and the integration-only-line analysis (which consumes the coverage contexts this plan records) land in Plan 7.
- **Remaining §5 linters** (`taplo`, `yamllint`, `hadolint`, `prettier`) — deferred to a small "complete the §5 linter set" tidy-up. They each need their own tool + config tuning across the dozens of existing YAML/TOML/Dockerfile payload files; bundling them here would balloon scope and risk the no-Docker cleanliness gate. `actionlint` + `shellcheck` are included because Plan 5a *introduces* the file types they cover (workflows + scripts). Noted as a carried-forward item.
- **NFR / sniff test tiers + the `tests/non_functional/` and `tests/sniff/` coverage rules** (§6) — sniff belongs with deploy validation (5b); NFR-threshold gating belongs with the NFR scaffolding work. Out of scope here.
- **`ci` Compose profile** (spec §9) — not needed: the e2e tier runs the app **in-process** (`TestClient`) against a **testcontainers** Postgres, so CI needs only a Docker daemon (present on `ubuntu-latest`), not a separate Compose stack. The "real running stack" ideal is realized by the staging-E2E phase in 5b. Documented deviation.

**Critical conventions (from the repo's CLAUDE.md):** files under `src/framework_cli/template/` are template *payload*, not framework source — the framework's own `ruff`/`mypy` exclude them; they are validated only by rendering + running the generated project. Brace-named paths (`{{package_name}}`) are Copier path templating — leave them. A payload file gets a `.jinja` suffix **iff** it contains Copier variables (e.g. `{{ package_name }}` / `{{ project_slug }}`); otherwise it keeps its plain extension. Each new file below is marked accordingly.

---

## File Structure

New template-payload files (rendered into every generated project):

| File | Suffix | Responsibility |
|---|---|---|
| `scripts/coverage.sh` | `.sh` (no vars) | Run named suites each under its own coverage context (`coverage run --context=<suite>`), then enforce a combined `--fail-under` threshold. Drives both gates. |
| `scripts/export-openapi.sh.jinja` | `.jinja` (imports `{{ package_name }}`) | Export `create_app().openapi()` → `openapi.json` (committed; CI diffs it). |
| `tests/e2e/__init__.py` | `.py` | Package marker for the e2e tier. |
| `tests/e2e/test_items_e2e.py.jinja` | `.jinja` (imports `{{ package_name }}`) | E2E happy path (full app + real DB) + mandatory unhappy path (404 → RFC 7807). |
| `.github/workflows/ci.yml.jinja` | `.jinja` (uses `{{ project_slug }}`) | The CI pipeline: integrity(seam) → lint → test → build → coverage gate → contract → security → review(seam). |
| `.github/dependabot.yml` | `.yml` (no vars) | Weekly dependency PRs for the `uv` (Python) and `github-actions` ecosystems. |

Modified template-payload files:

| File | Change |
|---|---|
| `tests/conftest.py.jinja` | Add the `e2e_client` fixture (full app + committing session on the testcontainers engine). |
| `Taskfile.yml.jinja` | Add `test:unit`, `test:e2e`, `test:cov:ci`, `audit`, `openapi:export`, `ci`; repoint `test:cov` at `scripts/coverage.sh`; extend `lint` with actionlint+shellcheck. |
| `.pre-commit-config.yaml` | Repoint `coverage-threshold` at `scripts/coverage.sh`; add `actionlint` + `shellcheck` hooks. |
| `pyproject.toml.jinja` | Add `pip-audit` to the dev dependency group. |
| `CLAUDE.md.jinja` | Document `task ci` / `task push`, the e2e tier + unhappy-path obligation, and the 70%/85% coverage stages (inside the managed block). |
| `README.md.jinja` | Document the CI pipeline, `task ci`, the e2e tier, OpenAPI export, and pip-audit/dependabot. |

Modified framework-source tests (validate the template renders the pipeline + the generated project behaves):

| File | Change |
|---|---|
| `tests/test_copier_runner.py` | Add `test_render_includes_ci_pipeline` (render assertions for all the above). |
| `tests/acceptance/test_rendered_project.py` | Add `test_rendered_project_exports_openapi` (no Docker) and `test_rendered_project_combined_coverage_gate_passes` (Docker); update `test_rendered_project_coverage_gate_passes` to the contexts-based 70% gate. |

---

## How to render & run during execution

The implementer renders a throwaway project and runs its suite/scripts. From the repo root:

```bash
uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})"
cd /tmp/demo && uv sync
```

Then run scripts/tests inside `/tmp/demo`. **Re-render after every template edit** (Copier does not hot-reload); delete `/tmp/demo` or render to a fresh path between renders.

> **Docker:** the unit + functional + e2e suites include DB tests that use a **testcontainers** Postgres and **fail (not skip) without Docker** (the 3c design). The dev environment has Docker (per the meta-plan's Environment Notes), so Tasks 1–2 and the Docker-gated acceptance checks run locally. The `export-openapi.sh`, render-assertion, and `actionlint`/`shellcheck` checks need **no Docker**.

> Each task's "Run" commands assume the project was (re-)rendered to `/tmp/demo` and `uv sync`'d after that task's template edits.

---

## Task 1: Coverage suite contexts + threshold script

Finalizes the unit/functional context split deferred from Plan 2, behind one reusable script that both gates call.

**Files:**
- Create: `src/framework_cli/template/scripts/coverage.sh`
- Modify: `src/framework_cli/template/.pre-commit-config.yaml`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add (e.g. after `test_render_includes_coverage_config`):

```python
def test_render_coverage_script_and_tasks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    script = dest / "scripts" / "coverage.sh"
    assert script.is_file()
    text = script.read_text()
    assert "coverage run --context=" in text
    assert "--fail-under=" in text

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:unit:" in taskfile

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "scripts/coverage.sh 70 unit functional" in precommit
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_coverage_script_and_tasks -q`
Expected: FAIL — `scripts/coverage.sh` does not exist / `test:unit:` not in the Taskfile.

- [ ] **Step 3: Create the coverage script**

Create `src/framework_cli/template/scripts/coverage.sh`:

```bash
#!/usr/bin/env bash
# Run the named test suites, each tagged with its own coverage context, then enforce a
# combined line-coverage threshold. The contexts (unit / functional / e2e) let CI tell a
# genuinely-uncovered line from one covered only at the integration level.
#
# Usage: scripts/coverage.sh <min_pct> <suite>...
#   pre-commit (fast):  scripts/coverage.sh 70 unit functional
#   CI (full picture):  scripts/coverage.sh 85 unit functional e2e
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <min_pct> <suite>..." >&2
  exit 2
fi

min_pct="$1"
shift

uv run coverage erase
append=""
for suite in "$@"; do
  # $append is intentionally empty on the first suite, "--append" afterwards.
  # shellcheck disable=SC2086
  uv run coverage run --context="$suite" $append -m pytest "tests/$suite" -q
  append="--append"
done
uv run coverage report --fail-under="$min_pct"
```

> **Why `coverage run --context=`, not pytest-cov's `--cov-context`:** pytest-cov's `--cov-context` only supports per-*test* dynamic contexts (`=test`), not arbitrary suite labels. `coverage run --context=unit` records a static label per suite — exactly the "unit vs functional vs e2e" labels §6 wants. `--append` accumulates all three into one `.coverage`; `coverage report` reads `[tool.coverage.run] source=["src"] branch=true` from `pyproject.toml` (already configured) and enforces the threshold. Running `coverage run -m pytest` (no `--cov`) leaves pytest-cov inert, so there's no double measurement.

- [ ] **Step 4: Repoint the pre-commit coverage hook (unit+functional only)**

In `src/framework_cli/template/.pre-commit-config.yaml`, change the `coverage-threshold` hook entry from:

```yaml
      - id: coverage-threshold
        name: unit + functional coverage (>=70%)
        entry: uv run pytest --cov --cov-fail-under=70 -q
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
```

to:

```yaml
      - id: coverage-threshold
        name: unit + functional coverage (>=70%)
        entry: bash scripts/coverage.sh 70 unit functional
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
```

> E2E is intentionally excluded from pre-commit (§5: unit+functional only — E2E needs the full stack and is slow). The full picture (incl. e2e, ≥85%) is the CI gate.

- [ ] **Step 5: Repoint `task test:cov` + add `task test:unit`**

In `src/framework_cli/template/Taskfile.yml.jinja`, replace the `test:cov` task:

```yaml
  test:cov:
    desc: Run tests with coverage and enforce the threshold
    cmds:
      - uv run pytest --cov --cov-context=test --cov-report=term-missing --cov-fail-under=70 -q
```

with:

```yaml
  test:unit:
    desc: Unit tests only.
    cmds:
      - uv run pytest tests/unit -q

  test:cov:
    desc: Fast coverage gate (unit + functional, >=70%) — matches the pre-commit gate.
    cmds:
      - bash scripts/coverage.sh 70 unit functional
```

- [ ] **Step 6: Run the render assertion + the gate (Docker)**

Re-render, `uv sync`, then:
Run: `uv run pytest tests/test_copier_runner.py::test_render_coverage_script_and_tasks -q`
Expected: PASS.

Then exercise the gate itself (needs Docker — unit/functional include DB tests):
Run: `cd /tmp/demo && bash scripts/coverage.sh 70 unit functional`
Expected: both suites run, combined coverage is reported, exit 0 (≥70%).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/scripts/coverage.sh src/framework_cli/template/.pre-commit-config.yaml src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): coverage suite contexts via scripts/coverage.sh (unit/functional gate)"
```

> The pre-commit hook requires `CLAUDE.md` staged — update the Current State pointer per the repo's working agreement (or `git add CLAUDE.md`) before committing. This applies to every commit below.

---

## Task 2: E2E test tier + combined 85% gate

**Files:**
- Create: `src/framework_cli/template/tests/e2e/__init__.py`
- Create: `src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja`
- Modify: `src/framework_cli/template/tests/conftest.py.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing e2e test**

Create `src/framework_cli/template/tests/e2e/__init__.py` (empty file):

```python
```

Create `src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja`:

```python
"""End-to-end: the full app (lifespan + middleware + RFC 7807 handlers) over a real Postgres.

Distinct from the functional tier: using `with TestClient(...)` runs the FastAPI lifespan
(startup + graceful-shutdown engine disposal), and the request flows through the whole app —
the closest in-process analogue of the deployed stack. Spec obligation: every consumer-facing
surface needs at least one unhappy E2E path.
"""

from fastapi.testclient import TestClient

from {{ package_name }}.db.engine import build_session_factory
from {{ package_name }}.db.repository import create_item


def test_items_listed_through_full_stack(engine, e2e_client: TestClient):
    # Seed a row through the SAME engine the app reads from, then list it back over HTTP.
    factory = build_session_factory(engine)
    with factory() as session:
        create_item(session, "e2e-widget")
        session.commit()

    resp = e2e_client.get("/items")
    assert resp.status_code == 200
    names = [row["name"] for row in resp.json()]
    assert "e2e-widget" in names


def test_unknown_resource_returns_problem_json(e2e_client: TestClient):
    # Unhappy path: a request for a resource that doesn't exist is rendered as RFC 7807.
    resp = e2e_client.get("/items/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2: Run it to confirm it fails**

Re-render, `uv sync`, then (needs Docker):
Run: `cd /tmp/demo && uv run pytest tests/e2e -q`
Expected: FAIL — `fixture 'e2e_client' not found`.

- [ ] **Step 3: Add the `e2e_client` fixture**

In `src/framework_cli/template/tests/conftest.py.jinja`, add this fixture after the `db_session` fixture (at the end of the file):

```python
@pytest.fixture
def e2e_client(engine: Engine) -> Iterator["TestClient"]:
    """A TestClient over the full app, wired to the real (testcontainers) Postgres.

    The app's default engine points at APP_DATABASE_URL (the compose host), so we override
    get_session with committing sessions on the test engine — the app then reads/writes the
    same DB the test seeds. Using `with` runs the lifespan (startup + shutdown disposal).
    """
    from fastapi.testclient import TestClient

    from {{ package_name }}.db.engine import build_session_factory, get_session
    from {{ package_name }}.main import create_app

    factory = build_session_factory(engine)

    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client
```

> **Why the override:** the module-level `engine` in `db/engine.py` is built from `get_settings().database_url` at import — it points at the compose Postgres, not the per-session testcontainers one. Overriding `get_session` with a factory bound to the `engine` fixture makes the app operate on the same DB the test seeds, while still exercising the real request → router → response → middleware path. (`Engine`, `Session`, `Iterator`, and `pytest` are already imported at the top of `conftest.py`.)

- [ ] **Step 4: Run the e2e suite to confirm it passes**

Re-render, `uv sync`, then (needs Docker):
Run: `cd /tmp/demo && uv run pytest tests/e2e -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Add `task test:e2e` + the combined CI gate task**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after the `test:cov` task (from Task 1):

```yaml
  test:e2e:
    desc: End-to-end tests only (full app + real Postgres; needs Docker).
    cmds:
      - uv run pytest tests/e2e -q

  test:cov:ci:
    desc: Combined coverage gate (unit + functional + e2e, >=85%) — the CI gate.
    cmds:
      - bash scripts/coverage.sh 85 unit functional e2e
```

- [ ] **Step 6: Run the combined gate (Docker)**

Re-render, `uv sync`, then:
Run: `cd /tmp/demo && bash scripts/coverage.sh 85 unit functional e2e`
Expected: all three suites run; combined coverage ≥ 85% (the project sits at ~96%), exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/tests/e2e src/framework_cli/template/tests/conftest.py.jinja src/framework_cli/template/Taskfile.yml.jinja
git commit -m "feat(template): e2e test tier (happy + unhappy) + combined 85% coverage gate"
```

---

## Task 3: OpenAPI contract export

**Files:**
- Create: `src/framework_cli/template/scripts/export-openapi.sh.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing acceptance test (no Docker)**

In `tests/acceptance/test_rendered_project.py`, add (after `test_rendered_project_precommit_runs_clean`):

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_exports_openapi(tmp_path: Path):
    # The export needs the app importable (uv sync) but NOT a database — create_app()
    # introspects routes without connecting, so this runs without Docker.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    result = subprocess.run(["bash", "scripts/export-openapi.sh"], cwd=dest)
    assert result.returncode == 0, "export-openapi.sh failed"

    spec = json.loads((dest / "openapi.json").read_text())
    # The OpenAPI title is the service identifier (settings.service_name, which defaults to the
    # package name) — the same identifier used for structlog/OTEL, so it is lowercase.
    assert spec["info"]["title"] == DATA["package_name"]
    for path in ("/items", "/health", "/heartbeat", "/metrics"):
        assert path in spec["paths"], f"{path} missing from the exported OpenAPI spec"
```

> **Correction (found in execution):** the app's `info.title` comes from `settings.service_name`, which defaults to `{{ package_name }}` (lowercase, e.g. `demo`) — the same identifier structlog and the OTEL `resource.service.name` use (the trace acceptance test asserts `resource.service.name="demo"`). Asserting the human-readable `"Demo"` was a plan error; the test asserts `DATA["package_name"]`. Do **not** repoint `service_name` at `project_name` — it would break the observability identity.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_exports_openapi -q`
Expected: FAIL — `scripts/export-openapi.sh` does not exist (non-zero return).

- [ ] **Step 3: Create the export script**

Create `src/framework_cli/template/scripts/export-openapi.sh.jinja`:

```bash
#!/usr/bin/env bash
# Export the FastAPI OpenAPI schema to openapi.json. The spec is committed and CI checks it
# is current (.github/workflows/ci.yml) and diffs it for breaking changes. Run after changing
# any route or response model, then commit the result. Convenience: `task openapi:export`.
set -euo pipefail

uv run python - > openapi.json <<'PY'
import json
import sys

from {{ package_name }}.main import create_app

json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
PY
```

> **Render note:** the heredoc is single-quoted (`<<'PY'`) so *bash* won't expand it — but *Copier/Jinja* renders the whole file first, so `{{ package_name }}` becomes the real package name in the output. `sort_keys=True` makes the output deterministic so the CI "is the committed spec current?" check is stable.

- [ ] **Step 4: Add `task openapi:export`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after the `db:seed` task (at the end):

```yaml
  openapi:export:
    desc: Export the OpenAPI schema to openapi.json (commit it; CI diffs it).
    cmds:
      - bash scripts/export-openapi.sh
```

- [ ] **Step 5: Run the acceptance test to confirm it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_exports_openapi -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/scripts/export-openapi.sh.jinja src/framework_cli/template/Taskfile.yml.jinja tests/acceptance/test_rendered_project.py
git commit -m "feat(template): OpenAPI export script + task openapi:export"
```

---

## Task 4: Dependency security (pip-audit + dependabot)

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Create: `src/framework_cli/template/.github/dependabot.yml`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_dependency_security(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pip-audit" in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "audit:" in taskfile

    dependabot = dest / ".github" / "dependabot.yml"
    assert dependabot.is_file()
    cfg = yaml.safe_load(dependabot.read_text())
    ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
    assert {"uv", "github-actions"} <= ecosystems
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dependency_security -q`
Expected: FAIL — `pip-audit` not in `pyproject.toml` / no `dependabot.yml`.

- [ ] **Step 3: Add pip-audit to the dev dependency group**

In `src/framework_cli/template/pyproject.toml.jinja`, in `[dependency-groups].dev`, add `pip-audit` after `pre-commit`:

```toml
    "pre-commit>=4.0",
    "pip-audit>=2.7",
    "pyyaml>=6.0",
```

- [ ] **Step 4: Add `task audit`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after the `openapi:export` task (from Task 3):

```yaml
  audit:
    desc: Scan dependencies for known vulnerabilities (CVEs).
    cmds:
      - uv run pip-audit
```

- [ ] **Step 5: Create the dependabot config**

Create `src/framework_cli/template/.github/dependabot.yml`:

```yaml
# Weekly dependency-update PRs. pip-audit (CI) gates known CVEs; dependabot keeps deps fresh.
version: 2
updates:
  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

> `package-ecosystem: "uv"` is Dependabot's native ecosystem for `uv.lock`-managed Python projects. If a target GitHub instance is older and rejects it, fall back to `"pip"` (it reads `pyproject.toml`).

- [ ] **Step 6: Run the render assertion to confirm it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dependency_security -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/Taskfile.yml.jinja src/framework_cli/template/.github/dependabot.yml tests/test_copier_runner.py
git commit -m "feat(template): pip-audit dependency scan + dependabot config"
```

---

## Task 5: Workflow + script linting (actionlint + shellcheck)

These are the file-type linters for the file types Plan 5a introduces: GitHub Actions workflows (`actionlint`) and shell scripts (`shellcheck`). They run in pre-commit, `task lint`, and CI.

**Files:**
- Modify: `src/framework_cli/template/.pre-commit-config.yaml`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_workflow_and_shell_linters(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "actionlint" in precommit
    assert "shellcheck" in precommit

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "actionlint" in taskfile
    assert "shellcheck" in taskfile
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_workflow_and_shell_linters -q`
Expected: FAIL — neither linter in the pre-commit config / Taskfile.

- [ ] **Step 3: Add the actionlint + shellcheck pre-commit hooks**

In `src/framework_cli/template/.pre-commit-config.yaml`, add these two repos after the `gitleaks` block and before the `- repo: local` block:

```yaml
  - repo: https://github.com/rhysd/actionlint
    rev: v1.7.7
    hooks:
      - id: actionlint

  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.10.0.1
    hooks:
      - id: shellcheck
```

> Pin to whatever the current released tags are at execution time (verify on the hook repos); the ids (`actionlint`, `shellcheck`) are stable. `actionlint` lints `.github/workflows/*.yml`; `shellcheck` lints `*.sh` (`scripts/entrypoint.sh`, `scripts/coverage.sh`, `scripts/export-openapi.sh`).

- [ ] **Step 4: Extend `task lint`**

In `src/framework_cli/template/Taskfile.yml.jinja`, replace the `lint` task:

```yaml
  lint:
    desc: Lint and type-check
    cmds:
      - uv run ruff check .
      - uv run mypy src
```

with:

```yaml
  lint:
    desc: Lint and type-check (ruff, mypy, actionlint, shellcheck).
    cmds:
      - uv run ruff check .
      - uv run mypy src
      - uv run pre-commit run actionlint --all-files
      - uv run pre-commit run shellcheck --all-files
```

- [ ] **Step 5: Verify the linters pass clean on the rendered project (no Docker)**

Re-render, `uv sync`, then run the full pre-commit set the way the acceptance test does (this fetches the new hook repos and runs them over the rendered files):

```bash
cd /tmp/demo && git init -q && git add -A
SKIP=coverage-threshold uv run pre-commit run --all-files
```

Expected: PASS — including `actionlint` (no workflow yet at this task → trivially clean) and `shellcheck` over `scripts/entrypoint.sh`, `scripts/coverage.sh`, and `scripts/export-openapi.sh`.

> **If `shellcheck` flags `scripts/entrypoint.sh`** (written in Plan 3c, not previously shellcheck'd): fix the findings (typically quoting — `"$VAR"` — or `# shellcheck disable=SCxxxx` with a one-line justification). Do not loosen the hook globally. Re-run until clean. The render assertion from Step 1 should also now pass:
> Run: `uv run pytest tests/test_copier_runner.py::test_render_workflow_and_shell_linters -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/.pre-commit-config.yaml src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): actionlint + shellcheck in pre-commit and task lint"
```

> If Step 5 required edits to `scripts/entrypoint.sh`, `git add` that file too.

---

## Task 6: The CI workflow + `task ci`

**Files:**
- Create: `src/framework_cli/template/.github/workflows/ci.yml.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_includes_ci_pipeline(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "ci.yml"
    assert wf.is_file()
    ci = yaml.safe_load(wf.read_text())

    # NB: PyYAML parses the workflow `on:` key as the boolean True.
    assert True in ci or "on" in ci
    jobs = ci["jobs"]
    # the spec §14 ordering, with integrity (Plan 6) + review (Plan 7) as seam jobs
    for job in ("integrity", "lint", "test", "build", "contract", "security", "review"):
        assert job in jobs, f"ci.yml missing the {job} job"
    assert jobs["lint"]["needs"] == "integrity"
    assert jobs["review"]["needs"] == ["test", "contract"]

    # the test job runs the combined 85% gate via the shared script
    test_run = " ".join(str(s.get("run", "")) for s in jobs["test"]["steps"])
    assert "scripts/coverage.sh 85 unit functional e2e" in test_run

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "ci:" in taskfile
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_ci_pipeline -q`
Expected: FAIL — `.github/workflows/ci.yml` does not exist.

- [ ] **Step 3: Create the CI workflow**

Create `src/framework_cli/template/.github/workflows/ci.yml.jinja`:

```yaml
# Authoritative CI pipeline (spec §14). `task push` triggers this; the local `task ci` is a
# fast pre-flight against the same checks. Steps 0 (integrity) and 9-10 (AI review agents)
# are seam jobs until framework v6/v7 (Plans 6/7) wire them in.
name: CI

on:
  push:
    branches: ["main"]
  pull_request:

permissions:
  contents: read

jobs:
  # Step 0: framework integrity. Wired in framework v6 (Plan 6 — `framework integrity --ci`).
  integrity:
    runs-on: ubuntu-latest
    steps:
      - run: echo "framework integrity --ci runs here once the integrity CLI ships (Plan 6)."

  # Step 2: lint + type-check across file types.
  lint:
    needs: integrity
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - name: actionlint + shellcheck
        run: |
          uv run pre-commit run actionlint --all-files
          uv run pre-commit run shellcheck --all-files

  # Step 1 (security half) + 12: dependency CVEs + full-history secret scan.
  security:
    needs: integrity
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: pip-audit (fail on known CVEs)
        run: uv run pip-audit
      - name: gitleaks (full-history secrets scan)
        uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}

  # Steps 3, 5, 6, 8: unit + functional + e2e with coverage contexts, then the combined gate.
  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: unit + functional + e2e (contexts) + combined >=85% gate
        run: bash scripts/coverage.sh 85 unit functional e2e
      - name: coverage report with contexts
        if: always()
        run: uv run coverage json --show-contexts -o coverage-contexts.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-contexts
          path: coverage-contexts.json
          if-no-files-found: ignore

  # Step 4: build the application image (validates the Dockerfile builds).
  build:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: docker build (app image)
        run: docker build -f infra/docker/Dockerfile -t {{ project_slug }}:ci .

  # Step 7: OpenAPI contract — the committed spec must be current; breaking changes fail.
  contract:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: fail if openapi.json is missing or stale
        run: |
          bash scripts/export-openapi.sh
          if [ -n "$(git status --porcelain -- openapi.json)" ]; then
            echo "::error::openapi.json is missing or out of date. Run 'task openapi:export' and commit it."
            git --no-pager diff -- openapi.json
            exit 1
          fi
      - name: breaking-change check (oasdiff)
        if: github.event_name == 'pull_request'
        uses: oasdiff/oasdiff-action/breaking@v0.0.21
        with:
          base: https://raw.githubusercontent.com/${{ github.repository }}/${{ github.base_ref }}/openapi.json
          revision: openapi.json
          fail-on: ERR

  # Steps 9-10: AI review agents + aggregator. Wired in framework v7 (Plan 7).
  review:
    needs: [test, contract]
    runs-on: ubuntu-latest
    steps:
      - run: echo "Layer-3 AI review agents + aggregator run here (Plan 7)."
```

> **Notes.** `uv sync --frozen` requires the committed `uv.lock` (a spec §15 requirement; the dev creates it with `uv sync` and commits it). The `test` job needs only a Docker daemon (present on `ubuntu-latest`) for the testcontainers Postgres — no Compose stack. The `git status --porcelain` check fails when `openapi.json` is absent **or** modified, forcing the dev to commit a current spec. `oasdiff` classifies *breaking* changes on PRs (additive changes don't fail). Pin `setup-uv@v5`, `gitleaks-action@v2`, and `oasdiff-action/breaking@v0.0.21` to current releases at execution time. `gitleaks-action` needs `GITLEAKS_LICENSE` only for organizations.

- [ ] **Step 4: Add `task ci`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after the `audit` task (from Task 4):

```yaml
  ci:
    desc: Full local CI pre-flight before `task push` (lint, 85% gate, audit, OpenAPI export).
    cmds:
      - task: lint
      - task: test:cov:ci
      - task: audit
      - task: openapi:export
```

- [ ] **Step 5: Validate the workflow renders + lints clean (no Docker)**

Re-render, `uv sync`. First the render assertion:
Run: `uv run pytest tests/test_copier_runner.py::test_render_includes_ci_pipeline -q`
Expected: PASS.

Then `actionlint` over the real workflow (this is the only way to validate the YAML short of running GitHub Actions):

```bash
cd /tmp/demo && git init -q && git add -A
uv run pre-commit run actionlint --all-files
```

Expected: PASS (no actionlint findings on `ci.yml`).

> If `actionlint` flags `shellcheck` issues inside a `run:` block (it shellchecks inline scripts), fix the quoting in the workflow until clean.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): GitHub Actions CI pipeline (lint/test/build/contract/security) + task ci"
```

---

## Task 7: Docs, acceptance coverage, full verification + roadmap/state update

**Files:**
- Modify: `src/framework_cli/template/CLAUDE.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Modify: `tests/acceptance/test_rendered_project.py`
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`
- Modify: `CLAUDE.md` (Current State pointer)

- [ ] **Step 1: Document the pipeline in CLAUDE.md (managed block)**

In `src/framework_cli/template/CLAUDE.md.jinja`, inside the `<!-- FRAMEWORK:BEGIN -->` … `<!-- FRAMEWORK:END -->` block, replace the `## Quality commands` section:

```markdown
## Quality commands

- `task test` — fast test run
- `task test:cov` — tests with coverage (must stay >= 70%)
- `task lint` — ruff + mypy
- `task hooks` — install pre-commit; `task hooks:run` — run all hooks
- An editor hook runs ruff + mypy on each Python file as it is edited; fix what it reports before moving on.
```

with:

```markdown
## Tests & coverage

Tests live in three tiers, each with its own coverage context:

- `tests/unit/` — code units (red first, then green).
- `tests/functional/` — behaviour/outcomes.
- `tests/e2e/` — consumer-facing surfaces against the full app + real Postgres. **Every consumer-facing surface needs at least one unhappy E2E path** (not found, bad input, dependency failure).

Coverage gates by stage (spec §6): **pre-commit** runs unit+functional at **>=70%** (E2E is too slow/heavy for the inner loop); **CI** runs all three at **>=85%**. A line covered only by E2E is integration-only coverage, not a failure.

## CI/CD

- `task ci` — full local pre-flight (lint, the 85% gate, pip-audit, OpenAPI export) against your working tree. Run it before pushing.
- `task push` — pushes; GitHub Actions (`.github/workflows/ci.yml`) runs the authoritative pipeline (the canonical green badge). `task ci` makes that run more likely to pass first try; it does not replace it.
- Updating a route or response model requires re-exporting the API contract: `task openapi:export`, then commit `openapi.json` — CI fails if it is stale or a change is breaking.
- `task audit` — scan dependencies for known CVEs (also a CI gate).

## Quality commands

- `task test` — fast test run; `task test:unit` / `task test:e2e` — a single tier
- `task test:cov` — fast coverage gate (unit+functional, >=70%); `task test:cov:ci` — combined gate (>=85%)
- `task lint` — ruff + mypy + actionlint + shellcheck
- `task hooks` — install pre-commit; `task hooks:run` — run all hooks
- An editor hook runs ruff + mypy on each Python file as it is edited; fix what it reports before moving on.
```

- [ ] **Step 2: Document the pipeline in README.md**

In `src/framework_cli/template/README.md.jinja`, replace the `## Quality gates` section:

```markdown
## Quality gates

- TDD is the workflow — see `CLAUDE.md`.
- `task test:cov` enforces a 70% coverage floor.
- Pre-commit runs ruff, mypy, gitleaks, file hygiene, and the coverage gate on every commit (`task hooks` to install).
- A Claude Code hook lints each Python file right after it is edited (`.claude/settings.json`).
```

with:

```markdown
## Quality gates

- TDD is the workflow — see `CLAUDE.md`. Tests are tiered: `tests/unit`, `tests/functional`, `tests/e2e`.
- Coverage gates by stage: pre-commit runs unit+functional at >=70% (`task test:cov`); CI runs all three at >=85% (`task test:cov:ci`).
- Pre-commit runs ruff, mypy, actionlint, shellcheck, gitleaks, file hygiene, and the coverage gate on every commit (`task hooks` to install).
- A Claude Code hook lints each Python file right after it is edited (`.claude/settings.json`).

## CI/CD

- `task ci` — local pre-flight: lint + the 85% coverage gate + pip-audit + OpenAPI export. Run before pushing.
- `task push` — pushes and triggers `.github/workflows/ci.yml`, the authoritative pipeline: integrity (seam) → lint → tests (unit/functional/e2e + 85% gate) → build → OpenAPI contract diff → pip-audit + full-history gitleaks → review agents (seam).
- `task openapi:export` — regenerate `openapi.json` after changing routes; commit it (CI fails on a stale or breaking spec).
- `task audit` — scan dependencies for CVEs. `.github/dependabot.yml` opens weekly update PRs.
```

- [ ] **Step 3: Add the acceptance tests (no-Docker contract + Docker 85% gate)**

The no-Docker OpenAPI export test was added in Task 3. Now add the combined-gate test and update the existing 70% gate test. In `tests/acceptance/test_rendered_project.py`, replace `test_rendered_project_coverage_gate_passes`:

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "task", "test:cov"], cwd=dest)
    if result.returncode == 127 or shutil.which("task") is None:
        result = subprocess.run(
            ["uv", "run", "pytest", "--cov", "--cov-fail-under=70", "-q"], cwd=dest
        )
    assert result.returncode == 0, "coverage gate did not pass in the generated project"
```

with (the `task test:cov` fallback can no longer be the old single-command form, since `test:cov` now shells out to `scripts/coverage.sh`):

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    # The fast pre-commit-equivalent gate: unit + functional, >=70%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["bash", "scripts/coverage.sh", "70", "unit", "functional"], cwd=dest)
    assert result.returncode == 0, "the 70% unit+functional coverage gate did not pass"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the e2e tier runs against real Postgres",
)
def test_rendered_project_combined_coverage_gate_passes(tmp_path: Path):
    # The authoritative CI gate: unit + functional + e2e, >=85%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "85", "unit", "functional", "e2e"], cwd=dest
    )
    assert result.returncode == 0, "the 85% combined coverage gate did not pass"
```

- [ ] **Step 4: Framework Layer-A gate (no Docker)**

Run from the repo root:

```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/test_copier_runner.py tests/test_cli.py tests/test_naming.py tests/test_smoke.py -q
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_exports_openapi" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean" -q
```

Expected: all PASS. `precommit_runs_clean` now also runs the new `actionlint` + `shellcheck` hooks over the rendered project (incl. `ci.yml` and the three shell scripts) and must be clean. `exports_openapi` proves the export works without Docker.

> If `ruff format` would change any new payload file, fix it: `cd /tmp/demo && uv run ruff format --check .` mirrors the hook. (The plan's Python is pre-formatted; verify after rendering — this caught misses in Plans 3c and 4.)

- [ ] **Step 5: Generated-project full suite + both coverage gates (Docker)**

```bash
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_coverage_gate_passes" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_combined_coverage_gate_passes" -q
```

Expected: PASS — the generated suite now includes `tests/e2e`; both the 70% and 85% gates hold (the project sits at ~96%). If Docker is unavailable these skip; note that in the final review and rely on the no-Docker Layer-A gate plus the eventual real CI run.

- [ ] **Step 6: Update the meta-plan status table**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`: change the Plan 5 row to reflect the 5a/5b slice — mark **5a done** with this plan's filename + the merge commit (fill after merge), and add a **5b (deploy seam) — Not started** entry. Update the prose "Done so far" paragraph to mention the generated-project CI pipeline (lint/test/e2e/coverage-contexts/85%-gate/OpenAPI-contract/pip-audit/dependabot, with integrity & review-agent seams). Add to the "Carried-Forward Notes": *remaining §5 linters (taplo, yamllint, hadolint, prettier) — complete the linter set in a tidy-up; actionlint+shellcheck landed in 5a.*

- [ ] **Step 7: Update CLAUDE.md Current State pointer**

In `CLAUDE.md`, update **Last updated** (datetime + timezone), **Where we are** (Plan 5a merged — generated-project CI pipeline), and **Next** (Plan 5b — deploy seam). Stage `CLAUDE.md` (the pre-commit hook blocks the commit otherwise).

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/CLAUDE.md.jinja src/framework_cli/template/README.md.jinja tests/acceptance/test_rendered_project.py docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git commit -m "docs(template): document CI pipeline; acceptance gates; mark Plan 5a complete"
```

---

## Self-Review

**Spec coverage (§14 CI steps 0–8, + §6/§11/§12/§5):**
- Step 0 framework integrity → `integrity` **seam job** (Plan 6), ordering preserved. ✅ (intentional gap)
- Step 1 pre-flight (deps install, pip-audit, gitleaks full-history) → `security` job (Task 4 deps + Task 6 workflow). ✅
- Step 2 lint + type-check → `lint` job: ruff, ruff-format, mypy, actionlint, shellcheck (Tasks 5–6). `taplo`/`yamllint`/`hadolint`/`prettier` deferred with rationale. ✅ (partial, documented)
- Step 3 unit+functional with contexts → Tasks 1–2 + `test` job. ✅
- Step 4 build images → `build` job (`docker build`, Task 6). ✅
- Steps 5–6 start stack + e2e with context → e2e via testcontainers + in-process app (Task 2), run in the `test` job; no separate Compose stack (documented deviation). ✅
- Step 7 export+diff openapi.json → Task 3 export + `contract` job (drift check + oasdiff breaking). ✅
- Step 8 combined ≥85% coverage gate → `scripts/coverage.sh 85 unit functional e2e` (Tasks 1–2, `test` job). ✅
- Steps 9–10 AI agents + aggregator → `review` **seam job** (Plan 7). ✅ (intentional gap)
- §6 coverage contexts (unit/functional/e2e labels) + stage thresholds (70%/85%) → Tasks 1–2; contexts recorded + emitted as a CI artifact for Plan 7's integration-only analysis. ✅
- §11 OpenAPI export/commit/diff/versioning → Task 3 + `contract` job. ✅ (GraphQL export/diff is GraphQL-battery → Plan 8; not applicable here.)
- §12 pip-audit + dependabot + gitleaks → Task 4 + `security` job. ✅
- §9/§15 `task ci` vs `task push` → Task 6 `task ci` + CLAUDE.md/README docs (Task 7). ✅
- Deploy (§14 staging/prod, deploy-strategy contract, 4-phase validation) → **Plan 5b**. ✅ (intentional gap, scoped)

**Placeholder scan:** No TBD / "add error handling" / "similar to Task N". Every code step shows full file content or an exact old→new replacement; every run step shows the command + expected result. The two seam jobs are deliberate, named, and documented (not placeholders for *this* plan's work). ✅

**Type / name consistency across tasks:**
- `scripts/coverage.sh <min_pct> <suite>...` — defined Task 1; called with `70 unit functional` (pre-commit hook Task 1, `task test:cov` Task 1, acceptance Task 7) and `85 unit functional e2e` (`task test:cov:ci` Task 2, `test` job Task 6, acceptance Task 7). Consistent. ✅
- Suite dirs `tests/unit` (exists), `tests/functional` (exists), `tests/e2e` (created Task 2) — the script's `tests/$suite` resolves all three. ✅
- `e2e_client` fixture — defined Task 2 in `conftest.py.jinja`; used by both e2e tests (Task 2). Uses `Engine`, `Session`, `Iterator`, `pytest` already imported in `conftest`; imports `build_session_factory`, `get_session`, `create_app` (all exist: `db/engine.py`, `main.py`). ✅
- `create_item(session, name)` / `build_session_factory(engine)` — used in the e2e test + fixture; match `db/repository.py` and `db/engine.py` signatures verified against the current template. ✅
- `scripts/export-openapi.sh` writes `openapi.json` → consumed by `task openapi:export` (Task 3), the `contract` job (Task 6), and `test_rendered_project_exports_openapi` (Task 3). Name consistent. ✅
- Taskfile additions — `test:unit` (Task 1), `test:e2e` + `test:cov:ci` (Task 2), `openapi:export` (Task 3), `audit` (Task 4), extended `lint` (Task 5), `ci` (Task 6) — `task ci` calls `lint`, `test:cov:ci`, `audit`, `openapi:export`, all defined before it. ✅
- CI job graph — `lint`/`security` need `integrity`; `test`/`build`/`contract` need `lint`; `review` needs `[test, contract]`. The render assertion (Task 6) checks `lint.needs == "integrity"` and `review.needs == ["test","contract"]`, matching the YAML. ✅
- Render-suffix correctness — `coverage.sh` (no vars) `.sh`; `export-openapi.sh.jinja` + `test_items_e2e.py.jinja` (import `{{ package_name }}`) `.jinja`; `ci.yml.jinja` (uses `{{ project_slug }}`) `.jinja`; `dependabot.yml` (no vars) `.yml`; `tests/e2e/__init__.py` plain. Matches the established convention. ✅

**Validation-boundary honesty:** GitHub Actions YAML is validated by render assertions + `actionlint`, not by executing Actions (the framework can't run a generated project's CI locally). All *logic* the workflow invokes — the coverage gate, the OpenAPI export, the e2e suite, pip-audit availability — lives in scripts/tests the framework runs (Tasks 1–5 + the Docker-gated acceptance checks). The breaking-diff (oasdiff) and full-history gitleaks are declarative workflow steps, exercised in the generated project's real CI. This boundary is stated in Architecture and the §14 step mapping. ✅

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-21-cicd-pipeline.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration (matches this repo's established flow: branch → implementer per task → controller verification → Opus final review → merge to `master`).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

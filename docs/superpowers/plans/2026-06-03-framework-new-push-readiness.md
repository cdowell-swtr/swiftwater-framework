# `framework new` Push-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a vanilla `framework new` project green-on-first-push to GitHub Actions with zero manual artifact setup, without turning `framework new` into a heavy install-dependent operation.

**Architecture:** Two mechanisms split by cost. (A) `framework new` runs `uv lock` (cheap, resolve-only) to ship a committed `uv.lock` — warn-and-continue on failure. (B) the generated `ci.yml` `contract` job self-seeds `openapi.json`/`schema.graphql`: enforce currency + breaking-change diffs when the spec is git-tracked, generate + notice + skip the gates when absent. Validated by simplifying Plan 13's dogfood (drop its manual `prepare_project`) and re-running it green.

**Tech Stack:** Python 3.12 (Typer CLI, `subprocess`, `shutil`), Copier/Jinja template, GitHub Actions YAML, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-03-framework-new-push-readiness-design.md`

---

## Key facts (verified — do not re-derive)

- `framework new` (`src/framework_cli/cli.py`) is a pure render: `render_project` → `write_manifest(dest, installed_framework_version())` → `record_portable_source(dest, installed_framework_version())` → echo. No network/install/git.
- `uv lock` resolves deps + writes `uv.lock` WITHOUT installing or creating a venv (fast). `uv` is on PATH wherever the framework CLI runs.
- `uv.lock` is a builder artifact, NOT a locked manifest file — integrity passes with it present (verified in Plan 13), and `new` generates it *after* `write_manifest`, so no integrity interaction.
- The generated `contract` job (`ci.yml.jinja`) currently: `uv sync --frozen`; regenerate `openapi.json` + fail on `git status --porcelain` drift (runs on push AND pr); PR-only oasdiff `uses:` step (fetches base `openapi.json` from `raw.githubusercontent.com`); for graphql, the same staleness pattern + a PR-only `graphql-core` breaking-change `run:` step (already skips if no base schema).
- An `oasdiff` step is a `uses:` action, so its tracked-ness guard must be a `steps.<id>.outputs.*` gate (set by a preceding `run:` step), not inline shell.
- Commit-gate: `git add` in a SEPARATE Bash call before `git commit` (the PreToolUse hook evaluates staged files before a chained add); update CLAUDE.md Current State + write the `.framework/audit/marker.json` skip-marker before each commit (per `[[gate-cadence-framework-slices]]`). The controller commits; subagents stage + stop.
- Template-payload TDD runs in a GENERATED project (`[[template-payload-tdd-loop]]`); but Tasks 1–2 are framework-source (hermetic, normal suite). Task 3's behavioral proof is the live dogfood (Task 5).

## File structure

| File | Responsibility |
|---|---|
| `src/framework_cli/lockfile.py` (new) | `write_lockfile(project) -> bool` — run `uv lock` in `project`; True on success, False+warn on failure (never raises). |
| `src/framework_cli/cli.py` (`new`) | Call `write_lockfile(dest)` after `record_portable_source`; thin shell. |
| `tests/test_lockfile.py` (new) | Hermetic unit tests for `write_lockfile` (monkeypatched `uv`). |
| `tests/test_cli.py` (modify) | Integration: `new` leaves `uv.lock`; a lock failure doesn't abort the scaffold. |
| `src/framework_cli/template/.github/workflows/ci.yml.jinja` (`contract` job) | Self-seed rework (tracked-vs-untracked). |
| `src/framework_cli/template/{{ 'CLAUDE.md' }}.jinja` (or the contract doc) | One-line nudge to commit the API spec. |
| `tests/test_copier_runner.py` (modify) | Content assertions on the rendered `contract` job. |
| `scripts/dogfood_e2e.py` (modify) | `render()` += `write_lockfile`; drop `prepare_project`; bump `DOGFOOD_COMMIT`. |

---

## Task 1: `write_lockfile` helper

**Files:**
- Create: `src/framework_cli/lockfile.py`
- Test: `tests/test_lockfile.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lockfile.py
import subprocess
from pathlib import Path

from framework_cli.lockfile import write_lockfile


def test_write_lockfile_success(tmp_path, monkeypatch):
    calls = {}

    def fake_run(args, cwd=None, capture_output=False, text=False):
        calls["args"] = args
        calls["cwd"] = cwd
        (Path(cwd) / "uv.lock").write_text("# lock\n")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr("framework_cli.lockfile.subprocess.run", fake_run)

    assert write_lockfile(tmp_path) is True
    assert calls["args"] == ["uv", "lock"]
    assert Path(calls["cwd"]) == tmp_path
    assert (tmp_path / "uv.lock").exists()


def test_write_lockfile_uv_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: None)
    assert write_lockfile(tmp_path) is False
    assert "uv.lock" in capsys.readouterr().err


def test_write_lockfile_lock_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("framework_cli.lockfile.shutil.which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(
        "framework_cli.lockfile.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(["uv", "lock"], 1, "", "boom"),
    )
    assert write_lockfile(tmp_path) is False  # never raises
    assert "uv.lock" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_lockfile.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.lockfile`.

- [ ] **Step 3: Implement**

```python
# src/framework_cli/lockfile.py
"""Generate a project's uv.lock at scaffold time (Plan 14 push-readiness).

`framework new` ships a committed uv.lock so the generated ci.yml's `uv sync --frozen`
jobs + the Dockerfile `COPY uv.lock` work on the builder's first push. `uv lock` only
RESOLVES dependencies (writes uv.lock) — it does not install or create a venv, so this
stays cheap. Failure is non-fatal: a transient/offline scaffold still succeeds and the
builder's first `uv sync` recovers the lock.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

_FALLBACK = "run `uv sync` (or `uv lock`) before your first push to generate it"


def write_lockfile(project: Path) -> bool:
    """Run `uv lock` in `project` to produce uv.lock. Returns True on success; on any
    failure warns to stderr and returns False (never raises)."""
    if shutil.which("uv") is None:
        typer.echo(
            f"Warning: `uv` not found — skipping uv.lock generation; {_FALLBACK}.",
            err=True,
        )
        return False
    result = subprocess.run(
        ["uv", "lock"], cwd=str(project), capture_output=True, text=True
    )
    if result.returncode != 0:
        typer.echo(
            f"Warning: `uv lock` failed — skipping uv.lock generation; {_FALLBACK}.\n"
            f"{result.stderr}",
            err=True,
        )
        return False
    return True
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_lockfile.py -q && uv run mypy src && uv run ruff check src/framework_cli/lockfile.py tests/test_lockfile.py && uv run ruff format --check src/framework_cli/lockfile.py tests/test_lockfile.py`
Expected: PASS, clean.

- [ ] **Step 5: Stage (controller commits)**

```bash
git add src/framework_cli/lockfile.py tests/test_lockfile.py
```
Do NOT `git commit` — the controller handles commits.

---

## Task 2: Wire `write_lockfile` into `framework new`

**Files:**
- Modify: `src/framework_cli/cli.py` (import + `new` body)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py (append)
from pathlib import Path

from typer.testing import CliRunner

from framework_cli.cli import app

runner = CliRunner()


def test_new_generates_uv_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Make write_lockfile deterministic + offline: fake a successful `uv lock`.
    import framework_cli.lockfile as lockmod

    def fake_run(args, cwd=None, capture_output=False, text=False):
        import subprocess
        (Path(cwd) / "uv.lock").write_text("# lock\n")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(lockmod.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(lockmod.subprocess, "run", fake_run)

    result = runner.invoke(app, ["new", "Demo App", "--with", ""], input="\n")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo-app" / "uv.lock").exists()


def test_new_succeeds_when_lock_generation_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import framework_cli.lockfile as lockmod

    monkeypatch.setattr(lockmod.shutil, "which", lambda _: None)  # uv "missing" → warn

    result = runner.invoke(app, ["new", "Demo App", "--with", ""], input="\n")
    assert result.exit_code == 0, result.output  # scaffold still succeeds
    assert (tmp_path / "demo-app").exists()
    assert not (tmp_path / "demo-app" / "uv.lock").exists()
```

> NB: adjust the `runner.invoke` args/`input` to match how `test_cli.py`'s existing `new` tests drive the wizard non-interactively (some pass `--with`/`--alerts` to skip prompts). Match the existing convention in that file — the assertions (uv.lock present / absent + exit_code 0) are the point.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -q -k "uv_lock or lock_generation"`
Expected: FAIL — `new` doesn't call `write_lockfile` yet (uv.lock not created).

- [ ] **Step 3: Implement** — add the import and the call

In `src/framework_cli/cli.py`, add to the import block (near line 16, after the `naming` import):
```python
from framework_cli.lockfile import write_lockfile
```

In the `new` command body, immediately after `record_portable_source(dest, installed_framework_version())` and before the `msg = ...` line, add:
```python
    write_lockfile(dest)  # ship a committed uv.lock so the first push's --frozen jobs pass
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -q -k "uv_lock or lock_generation" && uv run mypy src && uv run ruff check src/framework_cli/cli.py`
Expected: PASS, clean.

- [ ] **Step 5: Stage**

```bash
git add src/framework_cli/cli.py tests/test_cli.py
```
Do NOT commit.

---

## Task 3: Self-seed the `contract` job + nudge to commit the spec

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja` (`contract` job)
- Modify: the generated `CLAUDE.md` template (contract/convention section)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing content tests**

```python
# tests/test_copier_runner.py (append)
def test_contract_job_self_seeds_openapi_when_untracked(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": []})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    # tracked-vs-untracked branch + the tracked guard
    assert "git ls-files --error-unmatch openapi.json" in ci
    assert "openapi_tracked=true" in ci and "openapi_tracked=false" in ci
    # oasdiff is gated on tracked-ness (won't 404 on base for a never-committed spec)
    assert "steps.spec.outputs.openapi_tracked == 'true'" in ci


def test_contract_job_self_seeds_graphql_schema_when_untracked(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "git ls-files --error-unmatch schema.graphql" in ci
    assert "steps.gqlspec.outputs.schema_tracked == 'true'" in ci
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -q -k "self_seeds"`
Expected: FAIL — current contract job has none of these markers.

- [ ] **Step 3: Implement** — replace the `contract` job's openapi + graphql steps

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, replace the `- name: fail if openapi.json is missing or stale` step AND the `- name: breaking-change check (oasdiff)` step with:

```yaml
      - id: spec
        name: openapi.json — seed if absent, enforce if committed
        run: |
          bash scripts/export-openapi.sh
          if git ls-files --error-unmatch openapi.json >/dev/null 2>&1; then
            echo "openapi_tracked=true" >> "$GITHUB_OUTPUT"
            if [ -n "$(git status --porcelain -- openapi.json)" ]; then
              echo "::error::openapi.json is out of date. Run 'task openapi:export' and commit it."
              git --no-pager diff -- openapi.json
              exit 1
            fi
          else
            echo "openapi_tracked=false" >> "$GITHUB_OUTPUT"
            echo "::notice::openapi.json is not committed — generated for this run. Commit it to track the API contract and enable breaking-change diffs."
          fi
      - name: breaking-change check (oasdiff)
        if: {% raw %}${{ github.event_name == 'pull_request' && steps.spec.outputs.openapi_tracked == 'true' }}{% endraw %}
        uses: oasdiff/oasdiff-action/breaking@v0.0.21
        with:
          base: https://raw.githubusercontent.com/{% raw %}${{ github.repository }}/${{ github.base_ref }}{% endraw %}/openapi.json
          revision: openapi.json
          fail-on: ERR
```

And in the `{%- if "graphql" in batteries %}` block, replace the `- name: fail if schema.graphql is missing or stale` step AND the `- name: graphql breaking-change check (graphql-core)` step with:

```yaml
      - id: gqlspec
        name: schema.graphql — seed if absent, enforce if committed
        run: |
          bash scripts/export-graphql-schema.sh
          if git ls-files --error-unmatch schema.graphql >/dev/null 2>&1; then
            echo "schema_tracked=true" >> "$GITHUB_OUTPUT"
            if [ -n "$(git status --porcelain -- schema.graphql)" ]; then
              echo "::error::schema.graphql is out of date. Run scripts/export-graphql-schema.sh and commit it."
              git --no-pager diff -- schema.graphql
              exit 1
            fi
          else
            echo "schema_tracked=false" >> "$GITHUB_OUTPUT"
            echo "::notice::schema.graphql is not committed — generated for this run. Commit it to track the schema and enable breaking-change diffs."
          fi
      - name: graphql breaking-change check (graphql-core)
        if: {% raw %}${{ github.event_name == 'pull_request' && steps.gqlspec.outputs.schema_tracked == 'true' }}{% endraw %}
        run: |
          git show "origin/{% raw %}${{ github.base_ref }}{% endraw %}:schema.graphql" > /tmp/base.graphql 2>/dev/null || { echo "no base schema — skipping"; exit 0; }
          uv run python - <<'PY'
          import sys
          from pathlib import Path

          from graphql import build_schema, find_breaking_changes

          old = build_schema(Path("/tmp/base.graphql").read_text())
          new = build_schema(Path("schema.graphql").read_text())
          breaking = find_breaking_changes(old, new)
          for b in breaking:
              print(f"::error::breaking GraphQL change: {b.type.name}: {b.description}")
          sys.exit(1 if breaking else 0)
          PY
```

- [ ] **Step 4: Add the spec-commit nudge to the generated CLAUDE.md**

Find the generated CLAUDE.md template (`grep -rl "openapi" src/framework_cli/template --include="*CLAUDE.md*"` or the contract/convention section of `…/{{ 'CLAUDE.md' }}.jinja`). Add one line to the API/contract convention, e.g.:
```markdown
- Commit `openapi.json` (run `task openapi:export`{% if "graphql" in batteries %} and `schema.graphql`{% endif %}) to track your API contract — once committed, CI enforces it's current and diffs it for breaking changes. Until then CI generates it per-run and passes.
```
(Place it next to the existing API/openapi convention; match the file's bullet style. If no obvious contract section exists, add it under the CI/quality conventions.)

- [ ] **Step 5: Run to verify it passes + render sanity**

Run:
```bash
uv run pytest tests/test_copier_runner.py -q -k "self_seeds or contract or openapi or graphql"
# render + actionlint-sanity the workflow
uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('/var/tmp/p14'), {'project_name':'D','out':'/var/tmp/p14','package_name':'demo','batteries':['graphql'],'alert_channels':['webhook']})"
uv run pre-commit run actionlint --files /var/tmp/p14/.github/workflows/ci.yml || true   # if actionlint available
```
Expected: tests PASS; the rendered `ci.yml` is valid YAML (the `id:`/`steps.*.outputs` wiring parses).

- [ ] **Step 6: Stage**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py
git add "$(grep -rl 'API contract' src/framework_cli/template --include='*CLAUDE.md*' || true)"
```
Do NOT commit.

---

## Task 4: Simplify the Plan 13 dogfood harness

The dogfood no longer needs to pre-generate artifacts: `render()` mirrors the new `framework new` (`uv lock`), and the `contract` job self-seeds openapi/schema. Drop `prepare_project`.

**Files:**
- Modify: `scripts/dogfood_e2e.py`
- Test: `tests/test_dogfood.py` (only if a `prepare_project` reference exists there — the existing 15 tests are pure-logic and shouldn't reference it)

- [ ] **Step 1: Update `render()` to mirror `framework new` (add the lock)**

In `scripts/dogfood_e2e.py`, import `write_lockfile` and call it in `render()` after `record_portable_source`:
```python
from framework_cli.lockfile import write_lockfile  # noqa: E402  (with the other framework_cli imports)
```
At the end of `render()`:
```python
    write_lockfile(dest)  # mirror `framework new`: ship a committed uv.lock
```

- [ ] **Step 2: Remove `prepare_project` and its call**

Delete the `prepare_project(config, project)` function entirely, and remove the `prepare_project(config, project)` line from `run_config` (the `uv sync` + `export-openapi.sh` + `export-graphql-schema.sh` are no longer needed — the lock comes from `render()`, the spec self-seeds in CI). Also drop the now-unused `log("preparing project: …")` line if it was inside `prepare_project`.

- [ ] **Step 3: Verify**

Run:
```bash
uv run pytest tests/test_dogfood.py -q
uv run ruff check scripts/dogfood_e2e.py && uv run ruff format --check scripts/dogfood_e2e.py
uv run python scripts/dogfood_e2e.py --help >/dev/null && echo "imports OK"
# render+lock sanity (no prepare_project): render baseline via the harness, confirm uv.lock present, no openapi.json committed-prep
uv run python -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; import dogfood_e2e as d; from framework_cli.dogfood import BASELINE; import tempfile; t=tempfile.mkdtemp(dir='/var/tmp'); p=Path(t)/'r'; d.render(BASELINE,p); print('uv.lock:', (p/'uv.lock').exists())"
```
Expected: 15 tests pass; ruff clean; imports OK; `uv.lock: True`.

- [ ] **Step 4: Stage**

```bash
git add scripts/dogfood_e2e.py
```
Do NOT commit.

---

## Task 5: Live dogfood validation (controller — on the branch)

The simplified dogfood IS Plan 14's acceptance test: a vanilla `framework new`-shaped project goes green on real GHA with no manual prep.

- [ ] **Step 1: Confirm the local gate is green** (per `[[gate-cadence-framework-slices]]`, skip the slow acceptance tier)

```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: all green (incl. the new lockfile + contract-content + dogfood tests).

- [ ] **Step 2: Run the live dogfood on the branch** (DOGFOOD_COMMIT stays `v0.1.4` — integrity step-0 installs that CLI; the rendered template is HEAD's, integrity is self-consistent via write_manifest)

```bash
uv run python scripts/dogfood_e2e.py > /tmp/dogfood-p14.log 2>&1 &
```
Watch via the `[dogfood]` progress lines + `gh`. Expected: **GREEN** for baseline + all-batteries × push/PR, with NO `prepare_project` step in the log — proving the project is push-ready from `render()`'s `uv lock` + the self-seeding `contract` job. Re-run any single external-flake combo (timescaledb/Docker Hub) per Plan 13.

- [ ] **Step 3: Confirm the react image-build acceptance test now passes** (it hit `/uv.lock not found`)

```bash
uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_react_battery_passes" -q
```
Expected: PASS — the rendered project now has `uv.lock` (note: this acceptance test renders via its own helper; if that helper does NOT use `framework new`/`write_lockfile`, this test stays a known residual — record which, don't force it).

- [ ] **Step 4: Record the scorecard** (the green run is the proof)

Write `docs/superpowers/eval-scorecards/push-readiness-<date>/scorecard.md` with the run URLs + "vanilla project green-on-first-push, no manual prep". Stage it (controller commits in Task 6).

---

## Task 6: Branch-end review, release, merge, state (controller)

- [ ] **Step 1: Branch-end review** — use `superpowers:requesting-code-review` (Opus whole-branch). Focus: the `contract` job self-seed YAML (tracked-vs-untracked correctness across push/PR + the oasdiff output-gate), `write_lockfile` failure semantics, dogfood simplification. Address findings.

- [ ] **Step 2: Merge FF to `master`** (controller; user-authorized push)

```bash
git checkout master && git merge --ff-only <branch> && git push origin master
```

- [ ] **Step 3: Cut `v0.1.5`** (ships push-readiness to builders) — bump `pyproject.toml` 0.1.4→0.1.5 + `uv lock`; bump `DOGFOOD_COMMIT`→`v0.1.5` in `src/framework_cli/dogfood.py`; update CLAUDE.md; commit `chore(release): v0.1.5`; `git tag v0.1.5 && git push origin master v0.1.5`; watch `release.yml` green (re-run timescaledb flake if needed per Plan 15's known issue).

- [ ] **Step 4: Update state** — meta-plan row 14 → ✅ Done (FF SHA, v0.1.5); Remaining Sequence + footer → next is **Plan 15**; CLAUDE.md Current State pointer (concise). Commit.

---

## Self-review notes (filled by the plan author)

- **Spec coverage:** Part A → Tasks 1+2 (`write_lockfile` + wire into `new`, warn-and-continue). Part B → Task 3 (contract self-seed, tracked-vs-untracked, oasdiff output-gate, graphql, CLAUDE.md nudge). Part C → Tasks 4+5 (simplify dogfood, drop `prepare_project`, live re-run green + react acceptance check). Release/validation → Tasks 5+6. All spec sections mapped.
- **No placeholders:** every code step has complete code; the one "match existing convention" note (Task 2 wizard-invocation, Task 3 CLAUDE.md placement) is a deliberate fit-to-file instruction with the assertion/intent specified.
- **Type consistency:** `write_lockfile(project: Path) -> bool` used identically in Tasks 1, 2, 4; the contract step ids (`spec`/`gqlspec`) match their `steps.<id>.outputs.*_tracked` gates; `DOGFOOD_COMMIT` bump deferred to Task 6 (release) — branch validation (Task 5) intentionally runs against `v0.1.4`.
- **Risk carried from spec:** the react acceptance test may render without `framework new` (Task 5 Step 3 notes this — record, don't force).

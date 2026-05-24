# Battery Removal — `downskill` (Plan 8a-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `framework downskill <project> <battery>` removes a battery from a generated project — framework-owned (Copier can't un-render), reusing the 8a-1/8b machinery.

**Architecture:** Enumerate a battery's owned files via a **two-render diff** of the bundled template (`render(current) − render(current−{X})`); delete them (preserve migrations); for shared files the battery *changed*, splice hybrid managed sections / overwrite unmodified framework content / warn on builder-modified files; re-record the reduced battery set and regenerate the integrity manifest; run `task test` as the backstop. Guarded by a usage scan + a reverse-dependency check.

**Tech Stack:** Python 3.12, Typer, Copier (`render_project`), the existing `framework_cli` modules (`batteries`, `source`, `integrity.restore`/`generate`/`classes`, `upskill`), pytest + `CliRunner`.

**Source spec:** `docs/superpowers/specs/2026-05-24-battery-removal-design.md`

> **Refinement vs. spec §3/§4 (approved):** for a shared file the battery *changed*, the rule is **splice (hybrid) / overwrite-if-builder-unmodified / warn-if-builder-modified** — not "leave all non-managed + warn." This is required because 8b's `migrations/env.py` carries a battery-conditional *import* of the (now-deleted) `webhooks.models`; leaving it breaks `alembic` (`ModuleNotFoundError` → red `task test`). Overwriting it when the builder hasn't touched it strips the import cleanly; it also cleanly strips the unmodified `settings.py` field. Builder-*modified* files are still left + warned.

---

## Standing rules for every task

- **TDD:** failing test → red → minimum → green → commit.
- **Commit-gate hook:** bump `CLAUDE.md`'s `**Last updated:**` line + `git add CLAUDE.md` in every commit step. `git add` and `git commit` are SEPARATE Bash calls; avoid the literal word "commit" in Bash `description` fields (read-only git inspection too).
- Run only targeted tests per task; clear `/tmp/pytest-of-chris/*` before the Docker acceptance run (Task 5).
- Per-task gate: `uv run pytest -q <touched>`, `uv run ruff check .`, `uv run mypy src`.
- All new logic is **framework source** (`src/framework_cli/`) — fully unit/integration-testable hermetically (render + file ops, no Docker), except the final acceptance variant.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/framework_cli/downskill.py` (create) | Removal: `blocking_dependents`, `usage_references`, `owned_files` (two-render diff), `remove_battery` (orchestration → `RemovalReport`), `downskill_project` (wrap + `task test`), `DownskillError`. | 1–4 |
| `src/framework_cli/cli.py` (modify) | The `framework downskill <project> <battery> [--force]` command. | 4 |
| `tests/test_downskill.py` (create) | Unit + integration (reverse-dep, usage scan, owned-files diff, `remove_battery` end-to-end on a real bundled render). | 1–3 |
| `tests/test_cli.py` (modify) | The `downskill` CLI command (wiring + exit codes). | 4 |
| `tests/acceptance/test_rendered_project.py` (modify) | Docker: downskill a webhooks project → remaining suite green. | 5 |

**Reuse (no changes to these):** `source.read_batteries`/`record_batteries`; `integrity.restore._answers`/`_restore_section`; `integrity.classes.HYBRID_TRACKED`; `integrity.generate.write_manifest` + `integrity.manifest.installed_framework_version`; `batteries.get_battery`/`battery_names`/`resolve`/`_BATTERIES`; `upskill._is_git_tracked`; `copier_runner.render_project`.

---

## Task 1: Reverse-dependency check + usage scan

**Files:** Create `src/framework_cli/downskill.py`; Test `tests/test_downskill.py`.

- [ ] **Step 1: Failing tests** — create `tests/test_downskill.py`:

```python
def test_blocking_dependents_flags_a_requirer():
    from framework_cli import batteries as bat
    from framework_cli.downskill import blocking_dependents

    bat._BATTERIES["_pgvector"] = bat.BatterySpec("_pgvector", "x", requires=("_postgres",))
    bat._BATTERIES["_postgres"] = bat.BatterySpec("_postgres", "x")
    try:
        # removing _postgres while _pgvector is active -> _pgvector blocks it
        assert blocking_dependents(["_pgvector", "_postgres"], "_postgres") == ["_pgvector"]
        assert blocking_dependents(["_postgres"], "_postgres") == []
    finally:
        del bat._BATTERIES["_pgvector"], bat._BATTERIES["_postgres"]


def test_usage_references_finds_builder_import(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "app.py").write_text("from demo.webhooks.handler import handle_event\n")
    (tmp_path / "src" / "demo" / "clean.py").write_text("x = 1\n")
    refs = usage_references(tmp_path, "webhooks", package_name="demo", owned={"src/demo/webhooks/handler.py"})
    assert any("app.py" in r for r in refs)
    assert not any("clean.py" in r for r in refs)


def test_usage_references_ignores_owned_files(tmp_path):
    from framework_cli.downskill import usage_references

    (tmp_path / "src" / "demo" / "webhooks").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "webhooks" / "handler.py").write_text("import demo.webhooks\n")
    refs = usage_references(
        tmp_path, "webhooks", package_name="demo", owned={"src/demo/webhooks/handler.py"}
    )
    assert refs == []  # the battery's own file is excluded
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_downskill.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** — create `src/framework_cli/downskill.py`:

```python
from __future__ import annotations

from pathlib import Path

from framework_cli.batteries import resolve


class DownskillError(Exception):
    """Battery removal cannot proceed (refusal or invalid request)."""


def blocking_dependents(active: list[str], battery: str) -> list[str]:
    """Active batteries (other than `battery`) whose dependency-closure includes `battery`."""
    return sorted(b for b in active if b != battery and battery in resolve([b]))


def usage_references(project: Path, battery: str, *, package_name: str, owned: set[str]) -> list[str]:
    """Builder files that reference the battery (heuristic). Excludes the battery's own owned files.

    Looks for the battery's package import (`<package_name>.<battery>`) or a bare `<battery>`
    token in the project's `src/` tree. A guardrail, not a guarantee (can't see dynamic refs).
    """
    hits: list[str] = []
    needles = (f"{package_name}.{battery}", battery)
    src = project / "src"
    if not src.is_dir():
        return hits
    for path in sorted(src.rglob("*.py")):
        rel = str(path.relative_to(project))
        if rel in owned:
            continue
        text = path.read_text()
        if any(n in text for n in needles):
            hits.append(rel)
    return hits
```

- [ ] **Step 4: Run green** — `uv run pytest tests/test_downskill.py -q` → PASS.

- [ ] **Step 5: Gate + commit** — ruff/mypy clean; bump CLAUDE.md (`8a-2 Task 1: reverse-dep + usage scan`):
```bash
git add src/framework_cli/downskill.py tests/test_downskill.py CLAUDE.md
```
```bash
git commit -m "feat(downskill): reverse-dependency check + usage-reference scan

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Owned-files two-render diff

**Files:** Modify `src/framework_cli/downskill.py`; Test `tests/test_downskill.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_downskill.py`:

```python
_ANSWERS = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
    "batteries": ["webhooks"],
}


def test_owned_files_for_webhooks():
    from framework_cli.downskill import owned_files

    owned = owned_files(_ANSWERS, "webhooks")
    assert "src/demo/routes/webhooks.py" in owned
    assert "src/demo/webhooks/signature.py" in owned
    assert "tests/functional/test_webhooks.py" in owned
    assert "migrations/versions/0002_webhook_events.py" in owned  # owned, but preserved at delete time
    # shared files the battery only *edited* (not created) are NOT owned:
    assert ".env.example" not in owned
    assert "src/demo/config/settings.py" not in owned


def test_owned_files_empty_for_absent_battery():
    from framework_cli.downskill import owned_files

    assert owned_files({**_ANSWERS, "batteries": []}, "webhooks") == set()
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_downskill.py -k owned_files -q` → FAIL.

- [ ] **Step 3: Implement** — add to `src/framework_cli/downskill.py` (add imports `import tempfile`, `from collections.abc import Mapping`, `from framework_cli.copier_runner import render_project`):

```python
def _render_paths(answers: Mapping[str, object], batteries: list[str], dest: Path) -> set[str]:
    render_project(dest, {**answers, "batteries": batteries})
    return {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}


def owned_files(answers: Mapping[str, object], battery: str) -> set[str]:
    """Files a battery owns = those present WITH it but absent at the reduced set (two renders)."""
    current = [str(b) for b in answers.get("batteries", [])]  # type: ignore[union-attr]
    reduced = [b for b in current if b != battery]
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with_paths = _render_paths(answers, current, Path(a) / "r")
        without_paths = _render_paths(answers, reduced, Path(b) / "r")
    return with_paths - without_paths
```

- [ ] **Step 4: Run green** — `uv run pytest tests/test_downskill.py -q` → PASS.

- [ ] **Step 5: Gate + commit** — bump CLAUDE.md (`8a-2 Task 2: owned-files two-render diff`):
```bash
git add src/framework_cli/downskill.py tests/test_downskill.py CLAUDE.md
```
```bash
git commit -m "feat(downskill): enumerate a battery's owned files via a two-render diff

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: `remove_battery` orchestration

**Files:** Modify `src/framework_cli/downskill.py`; Test `tests/test_downskill.py`.

- [ ] **Step 1: Failing integration test** — add to `tests/test_downskill.py` (renders a real webhooks project via `framework new`, then removes the battery; hermetic — no Docker, no `task test`):

```python
def test_remove_battery_webhooks_end_to_end(tmp_path, monkeypatch):
    import subprocess

    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.downskill import remove_battery
    from framework_cli.source import read_batteries

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    project = tmp_path / "my-app"
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "-c", "commit.gpgsign=false", "-c", "user.email=b@b",
         "-c", "user.name=b", "commit", "-qm", "scaffold"], check=True,
    )

    report = remove_battery(project, "webhooks", force=False)

    # owned whole-files gone
    assert not (project / "src" / "my_app" / "routes" / "webhooks.py").exists()
    assert not (project / "src" / "my_app" / "webhooks").exists()
    assert not (project / "tests" / "functional" / "test_webhooks.py").exists()
    # migration PRESERVED (+ reported)
    assert (project / "migrations" / "versions" / "0002_webhook_events.py").is_file()
    assert any("0002_webhook_events" in p for p in report.preserved)
    # .env.example secret STRIPPED (managed-section splice); settings field stripped (overwrite)
    assert "WEBHOOK_SIGNING_SECRET" not in (project / ".env.example").read_text()
    assert "webhook_signing_secret" not in (project / "src" / "my_app" / "config" / "settings.py").read_text()
    # battery de-recorded + integrity green
    assert read_batteries(project) == []
    assert CliRunner().invoke(app, ["integrity", "--ci"], catch_exceptions=False) is not None
    monkeypatch.chdir(project)
    assert CliRunner().invoke(app, ["integrity", "--ci"]).exit_code == 0


def test_remove_battery_usage_refusal(tmp_path, monkeypatch):
    import subprocess

    import pytest
    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.downskill import DownskillError, remove_battery

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    project = tmp_path / "my-app"
    # builder code references the battery
    (project / "src" / "my_app" / "uses_it.py").write_text("from my_app.webhooks.handler import handle_event\n")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "-c", "commit.gpgsign=false", "-c", "user.email=b@b",
         "-c", "user.name=b", "commit", "-qm", "s"], check=True,
    )
    with pytest.raises(DownskillError, match="in use"):
        remove_battery(project, "webhooks", force=False)
    # --force proceeds
    remove_battery(project, "webhooks", force=True)
    assert not (project / "src" / "my_app" / "routes" / "webhooks.py").exists()
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_downskill.py -k remove_battery -q` → FAIL.

- [ ] **Step 3: Implement `remove_battery`** — add to `src/framework_cli/downskill.py` (add imports: `from dataclasses import dataclass, field`; `from framework_cli.batteries import get_battery`; `from framework_cli.integrity.classes import HYBRID_TRACKED`; `from framework_cli.integrity.generate import write_manifest`; `from framework_cli.integrity.manifest import installed_framework_version`; `from framework_cli.integrity.restore import _answers, _restore_section`; `from framework_cli.source import read_batteries, record_batteries`):

```python
_MIGRATIONS_PREFIX = "migrations/versions/"
_LOCK_REL = ".framework/integrity.lock"


@dataclass
class RemovalReport:
    removed: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)   # migrations kept (+ why)
    warnings: list[str] = field(default_factory=list)     # builder-modified files left as-is


def remove_battery(project: Path, battery: str, *, force: bool = False) -> RemovalReport:
    """Remove `battery` from `project` (framework-owned). Raises DownskillError on a refusal."""
    get_battery(battery)  # KeyError -> unknown battery (caller maps to a clean error)
    current = read_batteries(project)
    if battery not in current:
        raise DownskillError(f"battery {battery!r} is not active in this project")

    dependents = blocking_dependents(current, battery)
    if dependents:
        raise DownskillError(
            f"cannot remove {battery!r}: still required by {', '.join(dependents)}"
        )

    answers = _answers(project)
    package_name = str(answers.get("package_name", ""))
    owned = owned_files(answers, battery)

    refs = usage_references(project, battery, package_name=package_name, owned=owned)
    if refs and not force:
        raise DownskillError(
            f"battery {battery!r} appears in use by: {', '.join(refs)}. "
            "Re-run with --force to remove it anyway."
        )

    report = RemovalReport()
    reduced = [b for b in current if b != battery]

    # 1) delete owned whole-files, preserving migrations
    for rel in sorted(owned):
        if rel.startswith(_MIGRATIONS_PREFIX):
            report.preserved.append(rel)
            continue
        target = project / rel
        if target.is_file():
            target.unlink()
        report.removed.append(rel)
    # prune now-empty owned dirs (e.g. the battery package dir)
    for rel in sorted(owned, key=len, reverse=True):
        d = (project / rel).parent
        if d.is_dir() and d != project and not any(d.iterdir()):
            d.rmdir()

    # 2) shared files the battery CHANGED: splice hybrid / overwrite-if-unmodified / warn
    import tempfile

    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with_root = Path(a) / "r"
        without_root = Path(b) / "r"
        with_paths = _render_paths(answers, current, with_root)
        without_paths = _render_paths(answers, reduced, without_root)
        for rel in sorted(with_paths & without_paths):
            wf, wo = with_root / rel, without_root / rel
            if wf.read_bytes() == wo.read_bytes():
                continue  # battery didn't touch this file
            target = project / rel
            if rel in HYBRID_TRACKED:
                _restore_section(target, wo)  # strip the battery's managed-section lines
            elif target.is_file() and target.read_bytes() == wf.read_bytes():
                target.write_bytes(wo.read_bytes())  # builder unmodified -> overwrite clean
            else:
                report.warnings.append(rel)  # builder modified -> leave for manual review

    # 3) re-record + regenerate the manifest (inverse of 8b's upskill regen)
    record_batteries(project, reduced)
    if (project / _LOCK_REL).is_file():
        write_manifest(project, installed_framework_version())

    if report.preserved:
        report.warnings.append(
            "migration(s) preserved: " + ", ".join(report.preserved)
            + " — write a contract down-migration to drop the table(s) if desired."
        )
    return report
```

- [ ] **Step 4: Run green** — `uv run pytest tests/test_downskill.py -q` → PASS. ruff + mypy clean.

- [ ] **Step 5: Commit** — bump CLAUDE.md (`8a-2 Task 3: remove_battery orchestration`):
```bash
git add src/framework_cli/downskill.py tests/test_downskill.py CLAUDE.md
```
```bash
git commit -m "feat(downskill): remove_battery — delete owned, splice/overwrite shared, re-record + regen manifest

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `downskill_project` + the `framework downskill` command

**Files:** Modify `src/framework_cli/downskill.py`, `src/framework_cli/cli.py`; Test `tests/test_downskill.py`, `tests/test_cli.py`.

- [ ] **Step 1: Failing test (downskill_project wraps remove + task test)** — add to `tests/test_downskill.py`:

```python
def test_downskill_project_runs_remove_then_task_test(tmp_path, monkeypatch):
    import framework_cli.downskill as ds

    calls = {}
    monkeypatch.setattr(ds, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(ds, "remove_battery", lambda project, battery, *, force=False: calls.setdefault("removed", (battery, force)) or ds.RemovalReport())
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())

    ok = ds.downskill_project(tmp_path, "webhooks", force=True)
    assert ok is True and calls["removed"] == ("webhooks", True)
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_downskill.py -k downskill_project -q` → FAIL.

- [ ] **Step 3: Implement `downskill_project`** — add to `src/framework_cli/downskill.py` (add `import subprocess`; `from framework_cli.upskill import _is_git_tracked, UpskillError`):

```python
def downskill_project(project: Path, battery: str, *, force: bool = False) -> bool:
    """Remove `battery`, then run `task test`. Returns whether the project is green afterward."""
    if not _is_git_tracked(project):
        raise DownskillError(
            "downskill requires a git-tracked project (commit first, so you can review/revert)"
        )
    remove_battery(project, battery, force=force)
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
```

- [ ] **Step 4: Failing CLI test** — add to `tests/test_cli.py`:

```python
def test_downskill_command_removes_battery(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    captured = {}
    monkeypatch.setattr(
        cli_mod, "downskill_project",
        lambda project, battery, *, force=False: captured.update(b=battery, f=force) or True,
    )
    result = runner.invoke(app, ["downskill", str(tmp_path / "proj"), "webhooks"])
    assert result.exit_code == 0, result.output
    assert captured == {"b": "webhooks", "f": False}


def test_downskill_command_refusal_exits_1(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.downskill import DownskillError

    def boom(project, battery, *, force=False):
        raise DownskillError("battery 'webhooks' appears in use by: src/x.py. Re-run with --force...")

    monkeypatch.setattr(cli_mod, "downskill_project", boom)
    result = runner.invoke(app, ["downskill", str(tmp_path / "proj"), "webhooks"])
    assert result.exit_code == 1
    assert "in use" in result.output
```

- [ ] **Step 5: Add the command** — in `src/framework_cli/cli.py`, add the import `from framework_cli.downskill import DownskillError, downskill_project` and the command:

```python
@app.command()
def downskill(
    name: str = typer.Argument(..., help="Path to the project."),
    battery: str = typer.Argument(..., help="Battery to remove, e.g. 'webhooks'."),
    force: bool = typer.Option(False, "--force", help="Remove even if the battery appears in use."),
) -> None:
    """Remove a battery from a project (deletes its files; preserves migrations), then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)
    try:
        green = downskill_project(project, battery, force=force)
    except (DownskillError, KeyError, UpskillError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if green:
        typer.echo(f"Removed '{battery}' from {name}; tests pass.")
    else:
        typer.echo(
            f"Removed '{battery}' from {name}, but `task test` failed — review the removal diff "
            "and fix references before committing.",
            err=True,
        )
        raise typer.Exit(1)
```

(`UpskillError` is already imported in cli.py from Plan 6b; if not, add `from framework_cli.upskill import UpskillError`.)

- [ ] **Step 6: Run green** — `uv run pytest tests/test_downskill.py tests/test_cli.py -q` → PASS. `framework downskill --help` shows `<battery>` + `--force`. ruff + mypy clean.

- [ ] **Step 7: Commit** — bump CLAUDE.md (`8a-2 Task 4: downskill_project + framework downskill command`):
```bash
git add src/framework_cli/downskill.py src/framework_cli/cli.py tests/test_downskill.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(cli): framework downskill <project> <battery> removes a battery

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: With-downskill acceptance variant (Docker)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Read the sibling** — read `test_rendered_project_with_webhooks_battery_passes` (8b) for the render helper + `_docker_available` skipif + the `uv sync` / `bash scripts/coverage.sh 70 unit functional` invocation.

- [ ] **Step 2: Add the variant** — `test_rendered_project_downskill_webhooks_is_green`:
  1. Render with `{**DATA, "batteries": ["webhooks"]}`.
  2. `git init` + commit the rendered project (downskill requires git-tracked).
  3. Call `downskill_project(dest, "webhooks", force=True)` — or run the generated-suite mutation via `remove_battery(dest, "webhooks")` then the coverage gate directly (mirror the sibling's invocation). Assert the webhooks files are gone and the `0002` migration is preserved.
  4. Run the rendered project's suite (`bash scripts/coverage.sh 70 unit functional`, the same way the sibling does) → assert returncode 0: the project (now without webhooks) is still green — proving removal leaves a working project (no dangling imports, the stripped `env.py`/`settings.py` don't break `alembic`).

  Match the sibling's exact skipif + invocation. Note: after removal the `webhook_events` table/migration remain (preserved), which is harmless — `alembic upgrade head` still applies `0001`+`0002`; the app just no longer references the table.

- [ ] **Step 3: Run it** — `rm -rf /tmp/pytest-of-chris/*` then `uv run pytest tests/acceptance/test_rendered_project.py -k downskill -q` → PASS.

- [ ] **Step 4: Commit** — bump CLAUDE.md (`8a-2 Task 5: downskill acceptance variant`):
```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
```
```bash
git commit -m "test(acceptance): downskilling the webhooks battery leaves a green project

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final whole-branch review (controller, after all tasks)

- [ ] `uv run pytest -q` — full suite incl. Docker acceptance (websockets + webhooks + downskill variants), all green. Clear `/tmp/pytest-of-chris/*` first.
- [ ] `uv run ruff check .`, `uv run mypy src`, `uv lock --check` — clean (no new runtime deps).
- [ ] **End-to-end downskill on the bundled template** (no Docker needed for this part): `framework new --with webhooks` → `git init`+commit → `framework downskill <proj> webhooks --force` (or `remove_battery`) → confirm: webhooks files gone, `0002` migration preserved, `.env.example` secret stripped, `settings.py` field stripped (overwrite, since unmodified), **`migrations/env.py` battery import stripped** (the refinement — confirm no dangling `webhooks` import), `read_batteries == []`, `framework integrity --ci` green.
- [ ] **The env.py breaking-import case specifically:** confirm a downskilled webhooks project's `migrations/env.py` no longer imports `<pkg>.webhooks.models` (else `alembic` would break) — this is the whole reason for the overwrite-if-unmodified refinement; verify it empirically.
- [ ] Usage-scan + reverse-dep refusals behave (covered by unit tests; spot-check the CLI error messages).

Then **superpowers:finishing-a-development-branch**: finalize CLAUDE.md + the meta-plan 8a-2 row (→ ✅ merged), FF-merge to `master`, push.

---

## Self-review (against the spec)

**Spec coverage:** §1 scope (downskill command + framework-owned removal) — Tasks 3,4; §2 decisions (two-render diff, preserve migrations, strip managed sections, usage/reverse-dep guards, re-record+regen) — Tasks 1–3; §3 mechanic (`downskill_project`/`remove_battery` order: validate → reverse-dep → usage → delete owned[−migrations] → splice/overwrite/warn → record → regen → task test) — Tasks 3,4; §4 hard cases (migrations preserved+warn — Task 3; the **refined** non-managed handling overwrite-if-unmodified / warn-if-modified — Task 3; usage heuristic + task-test backstop — Tasks 1,4; reverse-dep — Task 1); §5 command + reporting — Task 4; §6 testing (unit diff/reverse-dep/usage, integration remove_battery, CLI, acceptance) — Tasks 1–5. ✔

**Refinement note:** spec §3/§4's "leave non-managed + warn" is implemented as the approved **splice / overwrite-if-builder-unmodified / warn-if-builder-modified** rule (Task 3, Step 3), because the `migrations/env.py` battery import is a breaking (not harmless) leftover. The final review verifies the env.py import is stripped.

**Placeholder scan:** concrete code/commands throughout. Task 5 defers to the sibling acceptance helper (a read step), not a placeholder.

**Type consistency:** `blocking_dependents(active, battery) -> list[str]`; `usage_references(project, battery, *, package_name, owned) -> list[str]`; `owned_files(answers, battery) -> set[str]`; `remove_battery(project, battery, *, force=False) -> RemovalReport`; `downskill_project(project, battery, *, force=False) -> bool`; `RemovalReport(removed, preserved, warnings)`; `DownskillError`. Reuses `_answers`/`_restore_section`/`read_batteries`/`record_batteries`/`write_manifest`/`HYBRID_TRACKED`/`_is_git_tracked` with their real signatures. Consistent across tasks.

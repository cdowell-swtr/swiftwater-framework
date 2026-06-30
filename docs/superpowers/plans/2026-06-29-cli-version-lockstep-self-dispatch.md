# CLI/template version lockstep via self-dispatch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CLI/template version skew impossible by re-execing the project-pinned CLI automatically, so `integrity`/`restore` are always correct, `upgrade` moves CLI+template together, and staleness surfaces via `upgrade --dry-run`.

**Architecture:** A pre-`app()` `main()` wrapper calls a new `dispatch()` that classifies the subcommand, resolves the project's `_commit`, and (when the installed CLI ≠ the version that should run) re-execs `uvx --from git+$REPO@<ref> framework <argv…>` (ephemeral, uv-cached, **no global mutation**). `new`/`upgrade` dispatch to the target (latest/`--to`); `integrity`/`restore`/`upskill`/`downskill` dispatch to the project pin; everything else runs self. A loop-guard env var prevents re-dispatch. Pure policy (`classify`, `decide_dispatch`) is separated from I/O seams (project resolution, `reexec`) for unit-testability.

**Tech Stack:** Python 3.12, Typer, `uv`/`uvx`, pytest (+ `CliRunner`), copier (template payload).

## Global Constraints

- **No global mutation.** Dispatch must use `uvx --from git+$REPO@<ref>` (ephemeral); never `uv tool install` (the deleted `self_bump.run_uv_tool_install` path). Verified by tests asserting the re-exec argv.
- **Security property (design-spec:719):** integrity logic stays in the CLI, never vendored into the project. The pinned CLI is fetched from `REPO_URL` at the ref — satisfied by `uvx --from git+…`.
- **Fail-loud, never silent-green:** any "could not verify" path exits **non-zero**. No `raise typer.Exit(0)` on skew/uncertainty.
- **Loop guard:** re-exec sets `FRAMEWORK_PINNED_EXEC=1`; when set, `dispatch()` is a no-op. Escape hatch `FRAMEWORK_NO_DISPATCH=1` forces self (framework-dev against the working tree).
- **Self == target/pin ⇒ zero overhead** (no exec).
- **YAGNI:** no materialized project-local install in this plan (uvx cache only); revisit only if pre-commit latency is measured-bad.
- **`REPO_URL`** = `https://github.com/cdowell-swtr/swiftwater-framework` (from `framework_cli.source`).
- **Review-model policy:** implementers Sonnet (Haiku trivial); code-quality review **Opus**; branch-end whole-branch review **Opus**. Ships a tagged release.
- Spec: `docs/superpowers/specs/2026-06-29-cli-version-lockstep-self-dispatch-design.md`.

---

## File structure

- **Create** `src/framework_cli/dispatch.py` — `classify()`, `decide_dispatch()` (pure), `resolve_project_commit()`, `reexec()` seam, `dispatch()` orchestration.
- **Modify** `src/framework_cli/cli.py` — add `main()` wrapper; reframe `upgrade` (drop `--bump-cli`/`maybe_self_bump`, add `--dry-run` + staleness preview); integrity skew branch → fail-loud; deprecate `check`.
- **Modify** `pyproject.toml` — `[project.scripts] framework = "framework_cli.cli:main"`.
- **Modify** `src/framework_cli/self_bump.py` — delete `run_uv_tool_install` + `maybe_self_bump` (mutate-global upgrade path); keep `is_uv_tool_install`, `reexec` is moved to `dispatch.py` (re-home), `BumpRefused`/`decide_bump` removed.
- **Create** `tests/test_dispatch.py`; **modify** `tests/test_cli_upgrade.py` / `tests/test_cli_check*.py` / integrity CLI tests (exact names confirmed in each task).
- **Modify** template payload: `src/framework_cli/template/src/{{package_name}}/../../.github/workflows/ci.yml.jinja` (comment only — CI keeps its explicit pin) and the generated `Taskfile.yml.jinja` integrity precondition comment; **modify** `README.md` bootstrap/usage docs.

---

## Task 1: `classify()` — command → dispatch kind

**Files:**
- Create: `src/framework_cli/dispatch.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Produces: `classify(command: str | None) -> str` returning one of `"advancing"`, `"cwd_project"`, `"arg_project"`, `"self"`. Command sets: `_ADVANCING = {"new", "upgrade"}`, `_CWD_PROJECT = {"integrity", "restore"}`, `_ARG_PROJECT = {"upskill", "downskill"}`. `None`/unknown → `"self"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py
import pytest
from framework_cli.dispatch import classify

@pytest.mark.parametrize(
    "command,kind",
    [
        ("new", "advancing"),
        ("upgrade", "advancing"),
        ("integrity", "cwd_project"),
        ("restore", "cwd_project"),
        ("upskill", "arg_project"),
        ("downskill", "arg_project"),
        ("check", "self"),
        ("eval", "self"),
        ("review-aggregate", "self"),
        (None, "self"),
        ("totally-unknown", "self"),
    ],
)
def test_classify(command, kind):
    assert classify(command) == kind
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dispatch.py::test_classify -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.dispatch`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/dispatch.py
"""Self-dispatch: run the CLI version that matches the project, automatically.

A version-coupled CLI installed as an unversioned global floats free of each
project's `_commit` pin. `dispatch()` (called before Typer parses) re-execs the
project-pinned version via cached `uvx` so the running CLI and the project's
template are always in lockstep. Pure policy (`classify`, `decide_dispatch`) is
separated from the I/O seams for unit-testing.
"""

from __future__ import annotations

_ADVANCING = frozenset({"new", "upgrade"})
_CWD_PROJECT = frozenset({"integrity", "restore"})
_ARG_PROJECT = frozenset({"upskill", "downskill"})


def classify(command: str | None) -> str:
    """Map a subcommand to its dispatch kind."""
    if command in _ADVANCING:
        return "advancing"
    if command in _CWD_PROJECT:
        return "cwd_project"
    if command in _ARG_PROJECT:
        return "arg_project"
    return "self"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dispatch.py::test_classify -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/dispatch.py tests/test_dispatch.py
git commit -m "feat(dispatch): classify subcommands by dispatch kind"
```

---

## Task 2: `decide_dispatch()` — pure self-vs-reexec policy

**Files:**
- Modify: `src/framework_cli/dispatch.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `classify` (Task 1); `framework_cli.version_sync.parse_version`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Dispatch:
      action: str   # "self" | "reexec"
      ref: str | None = None   # the vX.Y.Z (or sha) to uvx, when action == "reexec"

  def decide_dispatch(*, kind: str, installed_tag: str,
                      target_tag: str | None, project_commit: str | None,
                      reexecuted: bool) -> Dispatch
  ```
  Rules: `reexecuted` → `Dispatch("self")`. `kind == "self"` → `Dispatch("self")`. `kind == "advancing"`: ref = `target_tag` (caller passes latest/`--to`); if `target_tag` is None or equals `installed_tag` → self, else `reexec(target_tag)`. `kind in {cwd_project, arg_project}`: ref = `project_commit`; if `project_commit` is None (no project) or equals `installed_tag` → self, else `reexec(project_commit)`. Version equality uses `parse_version` for `vX.Y.Z`; a non-parseable ref (sha) that differs from `installed_tag` → `reexec(ref)` (string-unequal).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py (append)
from framework_cli.dispatch import Dispatch, decide_dispatch

def D(**kw):
    base = dict(kind="cwd_project", installed_tag="v0.4.5",
               target_tag=None, project_commit=None, reexecuted=False)
    base.update(kw)
    return decide_dispatch(**base)

def test_loop_guard_forces_self():
    assert D(reexecuted=True, project_commit="v0.4.2") == Dispatch("self")

def test_self_kind_runs_self():
    assert D(kind="self", project_commit="v0.4.2") == Dispatch("self")

def test_project_in_sync_runs_self():
    assert D(project_commit="v0.4.5") == Dispatch("self")

def test_project_behind_reexecs_pin():
    assert D(project_commit="v0.4.2") == Dispatch("reexec", "v0.4.2")

def test_no_project_runs_self():
    assert D(project_commit=None) == Dispatch("self")

def test_advancing_to_newer_reexecs_target():
    assert D(kind="advancing", target_tag="v0.5.0") == Dispatch("reexec", "v0.5.0")

def test_advancing_to_installed_runs_self():
    assert D(kind="advancing", target_tag="v0.4.5") == Dispatch("self")

def test_sha_pin_differs_reexecs():
    assert D(project_commit="abc1234") == Dispatch("reexec", "abc1234")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dispatch.py -k "decide or guard or sync or behind or advancing or sha or self_kind or no_project" -v`
Expected: FAIL — `ImportError: cannot import name 'Dispatch'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/dispatch.py (add imports + below classify)
from dataclasses import dataclass

from framework_cli.version_sync import parse_version


@dataclass(frozen=True)
class Dispatch:
    action: str  # "self" | "reexec"
    ref: str | None = None


def _same_version(a: str, b: str) -> bool:
    try:
        return parse_version(a) == parse_version(b)
    except Exception:
        return a == b


def decide_dispatch(*, kind: str, installed_tag: str, target_tag: str | None,
                    project_commit: str | None, reexecuted: bool) -> Dispatch:
    if reexecuted or kind == "self":
        return Dispatch("self")
    ref = target_tag if kind == "advancing" else project_commit
    if ref is None or _same_version(ref, installed_tag):
        return Dispatch("self")
    return Dispatch("reexec", ref)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dispatch.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/dispatch.py tests/test_dispatch.py
git commit -m "feat(dispatch): pure self-vs-reexec policy"
```

---

## Task 3: project resolution + `reexec` seam + `dispatch()` orchestration

**Files:**
- Modify: `src/framework_cli/dispatch.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `classify`, `decide_dispatch`, `framework_cli.source.read_commit(project: Path) -> str | None`, `framework_cli.source.latest_release() -> str | None`, `framework_cli.version_sync.installed_version_tag() -> str`, `framework_cli.source.REPO_URL`.
- Produces:
  - `resolve_project_commit(kind: str, positionals: list[str]) -> str | None` — `cwd_project` → `read_commit(Path.cwd())`; `arg_project` → `read_commit(Path(positionals[0]))` if a positional exists; else `None`.
  - `reexec(ref: str, argv: list[str]) -> None` — I/O seam; `os.execvpe("uvx", ["uvx", "--from", f"git+{REPO_URL}@{ref}", "framework", *argv], {**os.environ, "FRAMEWORK_PINNED_EXEC": "1"})`.
  - `dispatch(argv: list[str]) -> None` — orchestrates: honor `FRAMEWORK_NO_DISPATCH`/`FRAMEWORK_PINNED_EXEC`; parse command + positionals from `argv`; classify; compute `target_tag` (`--to` value or `latest_release()`) for `advancing`; `resolve_project_commit` otherwise; `decide_dispatch`; on `reexec`, if `uvx` is unavailable → fail loud (`SystemExit(<non-zero>)` with remediation), else `reexec`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py (append)
import framework_cli.dispatch as disp

def test_dispatch_reexecs_pin_for_cwd_project(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "_uvx_available", lambda: True)
    captured = {}
    monkeypatch.setattr(disp, "reexec", lambda ref, argv: captured.update(ref=ref, argv=argv))
    disp.dispatch(["integrity", "--ci"])
    assert captured == {"ref": "v0.4.2", "argv": ["integrity", "--ci"]}

def test_dispatch_self_when_in_sync(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.5\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    called = {"reexec": False}
    monkeypatch.setattr(disp, "reexec", lambda *a: called.update(reexec=True))
    disp.dispatch(["integrity"])
    assert called["reexec"] is False

def test_dispatch_noop_when_reexecuted(monkeypatch):
    monkeypatch.setenv("FRAMEWORK_PINNED_EXEC", "1")
    monkeypatch.setattr(disp, "reexec", lambda *a: pytest.fail("must not re-exec"))
    disp.dispatch(["integrity"])  # returns cleanly

def test_dispatch_fail_loud_when_uvx_missing(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "_uvx_available", lambda: False)
    with pytest.raises(SystemExit) as exc:
        disp.dispatch(["integrity"])
    assert exc.value.code != 0

def test_dispatch_advancing_reexecs_latest(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no project
    monkeypatch.setattr(disp, "installed_version_tag", lambda: "v0.4.5")
    monkeypatch.setattr(disp, "latest_release", lambda: "v0.5.0")
    monkeypatch.setattr(disp, "_uvx_available", lambda: True)
    captured = {}
    monkeypatch.setattr(disp, "reexec", lambda ref, argv: captured.update(ref=ref))
    disp.dispatch(["upgrade", "someproj"])
    assert captured["ref"] == "v0.5.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dispatch.py -k dispatch -v`
Expected: FAIL — `AttributeError: module 'framework_cli.dispatch' has no attribute 'dispatch'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/dispatch.py (add imports + functions)
import os
import shutil
from pathlib import Path

from framework_cli.source import REPO_URL, latest_release, read_commit
from framework_cli.version_sync import installed_version_tag


def resolve_project_commit(kind: str, positionals: list[str]) -> str | None:
    if kind == "cwd_project":
        return read_commit(Path.cwd())
    if kind == "arg_project" and positionals:
        return read_commit(Path(positionals[0]))
    return None


def _uvx_available() -> bool:
    return shutil.which("uvx") is not None


def reexec(ref: str, argv: list[str]) -> None:  # pragma: no cover - exec seam
    env = {**os.environ, "FRAMEWORK_PINNED_EXEC": "1"}
    cmd = ["uvx", "--from", f"git+{REPO_URL}@{ref}", "framework", *argv]
    os.execvpe("uvx", cmd, env)


def _split_argv(argv: list[str]) -> tuple[str | None, list[str]]:
    """Return (command, positionals-after-command) ignoring leading options."""
    command, positionals, i = None, [], 0
    while i < len(argv):
        tok = argv[i]
        if command is None:
            if tok.startswith("-"):
                i += 1
                continue
            command = tok
        elif not tok.startswith("-"):
            positionals.append(tok)
        i += 1
    return command, positionals


def _target_tag(argv: list[str]) -> str | None:
    if "--to" in argv:
        idx = argv.index("--to")
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return latest_release()


def dispatch(argv: list[str]) -> None:
    if os.environ.get("FRAMEWORK_PINNED_EXEC") or os.environ.get("FRAMEWORK_NO_DISPATCH"):
        return
    command, positionals = _split_argv(argv)
    kind = classify(command)
    if kind == "self":
        return
    installed = installed_version_tag()
    target = _target_tag(argv) if kind == "advancing" else None
    project_commit = resolve_project_commit(kind, positionals)
    decision = decide_dispatch(
        kind=kind, installed_tag=installed, target_tag=target,
        project_commit=project_commit, reexecuted=False,
    )
    if decision.action == "self":
        return
    if not _uvx_available():
        raise SystemExit(
            f"framework: this project needs CLI {decision.ref} but `uvx` is unavailable "
            f"to run it (install uv, or `uv tool install git+{REPO_URL}@{decision.ref}`). "
            "Refusing to run a mismatched CLI."
        )
    reexec(decision.ref, argv)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dispatch.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/dispatch.py tests/test_dispatch.py
git commit -m "feat(dispatch): project resolution, uvx re-exec seam, orchestration"
```

---

## Task 4: wire `main()` entry + repoint the console script

**Files:**
- Modify: `src/framework_cli/cli.py` (add `main()` near the bottom, after `app` is fully defined)
- Modify: `pyproject.toml:36`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `framework_cli.dispatch.dispatch`, the existing `app` Typer object.
- Produces: `main() -> None` — `dispatch(sys.argv[1:]); app()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py (append)
def test_main_dispatches_then_runs_app(monkeypatch):
    import framework_cli.cli as climod
    calls = []
    monkeypatch.setattr(climod, "dispatch", lambda argv: calls.append(("dispatch", argv)))
    monkeypatch.setattr(climod, "app", lambda: calls.append(("app",)))
    monkeypatch.setattr(climod.sys, "argv", ["framework", "integrity"])
    climod.main()
    assert calls == [("dispatch", ["integrity"]), ("app",)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dispatch.py::test_main_dispatches_then_runs_app -v`
Expected: FAIL — `AttributeError: module 'framework_cli.cli' has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/cli.py — add import near the top with the other framework_cli imports
from framework_cli.dispatch import dispatch

# src/framework_cli/cli.py — add at the very bottom of the module
def main() -> None:
    """Console entry: self-dispatch to the project-pinned CLI, then run Typer."""
    dispatch(sys.argv[1:])
    app()
```

```toml
# pyproject.toml
[project.scripts]
framework = "framework_cli.cli:main"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dispatch.py::test_main_dispatches_then_runs_app -v && uv run framework --version`
Expected: test PASS; `framework --version` prints the installed version (dispatch is a no-op outside a project).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py pyproject.toml tests/test_dispatch.py
git commit -m "feat(cli): self-dispatch main() entry point"
```

---

## Task 5: reframe `upgrade` — drop `--bump-cli`, add `--dry-run` + staleness

**Files:**
- Modify: `src/framework_cli/cli.py:398-462` (the `upgrade` command)
- Test: `tests/test_cli_upgrade.py` (existing; confirm the path with `git ls-files tests | grep -i upgrade`)

**Interfaces:**
- Consumes: `framework_cli.upgrade.upgrade_project`, `framework_cli.source.latest_release`, `framework_cli.source.read_commit`.
- Produces: `upgrade(name, to, dry_run)` — no `--bump-cli`, no `maybe_self_bump` (the dispatch front-end already runs the target CLI). `--dry-run` reports the pin→target gap and applies nothing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_upgrade.py (add; uses typer.testing.CliRunner + the app)
from typer.testing import CliRunner
from framework_cli.cli import app
import framework_cli.cli as climod

runner = CliRunner()

def test_upgrade_dry_run_reports_gap(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.setattr(climod, "latest_release", lambda: "v0.4.5")
    called = {"upgrade": False}
    monkeypatch.setattr(climod, "upgrade_project",
                        lambda *a, **k: called.update(upgrade=True))
    result = runner.invoke(app, ["upgrade", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "v0.4.2" in result.output and "v0.4.5" in result.output
    assert called["upgrade"] is False  # dry-run applies nothing

def test_upgrade_dry_run_already_current(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.5\n")
    monkeypatch.setattr(climod, "latest_release", lambda: "v0.4.5")
    result = runner.invoke(app, ["upgrade", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "current" in result.output.lower()

def test_upgrade_has_no_bump_cli_option():
    result = runner.invoke(app, ["upgrade", "--help"])
    assert "--bump-cli" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_upgrade.py -k "dry_run or bump_cli" -v`
Expected: FAIL — `--dry-run` unknown / `--bump-cli` still present.

- [ ] **Step 3: Write minimal implementation** — replace the `upgrade` command body:

```python
@app.command()
def upgrade(
    name: str = typer.Argument(..., help="Path to the project to upgrade."),
    to: str = typer.Option(
        None, "--to", help="Target release tag (default: the latest release)."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report whether the project is behind the latest release; apply nothing.",
    ),
) -> None:
    """Move a project onto a newer framework release, then run its tests.

    The CLI version that runs this command is the target version (the self-dispatch
    front-end re-execs it), so no separate CLI bump is needed.
    """
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)

    target = to if to is not None else latest_release()
    if target is None:
        typer.echo(
            "Error: no framework release found (or the remote is unreachable); "
            "cannot determine the target.",
            err=True,
        )
        raise typer.Exit(1)

    if dry_run:
        from framework_cli.source import read_commit

        pin = read_commit(project)
        if pin == target:
            typer.echo(f"This project is current ({target}).")
        elif pin is None:
            typer.echo(
                f"Cannot determine staleness: this project has no release-tag pin "
                f"(latest is {target})."
            )
        else:
            typer.echo(
                f"This project is pinned {pin} — {target} available. "
                f"Run `framework upgrade {name}` to move CLI + template together."
            )
        return

    try:
        outcome = upgrade_project(project, to=target)
    except UpgradeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    for warning in outcome.warnings:
        typer.echo(f"warning: {warning}", err=True)
    if outcome.status == "already-current":
        typer.echo(f"Already up to date ({outcome.target}).")
        return
    if outcome.status == "red":
        typer.echo(
            f"Upgraded to {outcome.target}, but `task test` failed — resolve any Copier "
            "conflict markers and fix failures, then re-run `task test` before committing.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(
        f"Upgraded to {outcome.target}; tests pass. Review the diff, then snapshot it:"
    )
    typer.echo(
        f'  git add -A && git commit -m "chore: upgrade framework to {outcome.target}" && git push'
    )
```

Also remove the now-unused import: delete `from framework_cli.self_bump import BumpRefused, maybe_self_bump` from `cli.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_upgrade.py -v`
Expected: PASS. Fix any existing upgrade test that asserted `--bump-cli`/self-bump behavior (those scenarios are obsolete — the dispatch front-end owns version selection; update them to the new `--dry-run`/no-bump contract).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli_upgrade.py
git commit -m "feat(upgrade): drop --bump-cli, add --dry-run staleness preview"
```

---

## Task 6: integrity skew branch → fail-loud floor

**Files:**
- Modify: `src/framework_cli/cli.py:150-171` (the skew branch in `integrity`)
- Test: integrity CLI test file (confirm with `git ls-files tests | grep -i integrity`)

**Interfaces:**
- Consumes: existing `project_version_skew`, `skew_remedy`.
- Produces: on skew (the bypass case — normally unreachable because dispatch runs the pinned CLI), integrity exits **non-zero** instead of `Exit(0)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_integrity.py (add)
from typer.testing import CliRunner
from framework_cli.cli import app
import framework_cli.cli as climod

runner = CliRunner()

def test_integrity_fails_loud_on_skew(monkeypatch, tmp_path):
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.4.2\n")
    monkeypatch.chdir(tmp_path)
    # Force the bypass path: pretend dispatch was skipped and the CLI is ahead.
    monkeypatch.setenv("FRAMEWORK_NO_DISPATCH", "1")
    import framework_cli.version_sync as vs
    monkeypatch.setattr(vs, "installed_version_tag", lambda: "v0.4.5")
    result = runner.invoke(app, ["integrity"])
    assert result.exit_code != 0
    assert "could not verify" in result.output.lower() or "skew" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_integrity.py::test_integrity_fails_loud_on_skew -v`
Expected: FAIL — exit_code is 0 (current silent skip).

- [ ] **Step 3: Write minimal implementation** — replace the skew branch + its comment:

```python
    # Skew is normally impossible: the self-dispatch front-end (dispatch.py) re-execs the
    # project-pinned CLI, so by the time integrity runs, the installed CLI == `_commit`.
    # This branch is the fail-loud FLOOR for a bypass (FRAMEWORK_NO_DISPATCH, or `uvx`
    # unavailable). A verification gate must never pass while verifying nothing.
    from framework_cli.version_sync import (
        VersionSkew,
        project_version_skew,
        skew_remedy,
    )

    try:
        skew, installed_tag, commit_tag = project_version_skew(project)
    except VersionSkewError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if skew is not VersionSkew.IN_SYNC:
        typer.echo(
            f"framework integrity: could not verify — your CLI is {installed_tag} but this "
            f"project is pinned {commit_tag} (self-dispatch was bypassed). "
            + skew_remedy(skew, installed_tag, commit_tag),
            err=True,
        )
        raise typer.Exit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_integrity.py -v`
Expected: PASS. Update any existing test that asserted the old `Exit(0)` skip-message to the new fail-loud contract.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli_integrity.py
git commit -m "fix(integrity): fail loud on skew bypass instead of silent exit 0"
```

---

## Task 7: deprecate `check`

**Files:**
- Modify: `src/framework_cli/cli.py:463-479` (the `check` command)
- Test: check CLI test file (confirm with `git ls-files tests | grep -i check`)

**Interfaces:**
- Produces: `check()` prints a deprecation pointer to `framework upgrade --dry-run <project>` and exits 0 (it no longer reports the misleading installed-CLI-vs-latest line that BRG42 #2 flagged).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_check.py (add)
from typer.testing import CliRunner
from framework_cli.cli import app

runner = CliRunner()

def test_check_is_deprecated_and_points_to_upgrade_dry_run():
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    out = result.output.lower()
    assert "deprecat" in out
    assert "upgrade --dry-run" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_check.py -k deprecated -v`
Expected: FAIL — current output reports "up to date"/"installed … latest …".

- [ ] **Step 3: Write minimal implementation** — replace the `check` body:

```python
@app.command()
def check() -> None:
    """Deprecated — use `framework upgrade --dry-run <project>`."""
    typer.echo(
        "framework check is deprecated: it reported the CLI version, not the project's. "
        "Use `framework upgrade --dry-run <project>` to see if a project is behind the "
        "latest release."
    )
```

Remove any now-unused imports in `cli.py` left dangling by this change (`version_tag`/`installed_framework_version` if no other caller — verify with a grep before deleting).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_check.py -v`
Expected: PASS. Update/replace existing `check` tests asserting the old version-report behavior.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli_check.py
git commit -m "feat(check): deprecate in favor of upgrade --dry-run"
```

---

## Task 8: retire the mutate-global path in `self_bump.py`

**Files:**
- Modify: `src/framework_cli/self_bump.py`
- Test: existing `tests/test_self_bump.py` (confirm name); `tests/test_dispatch.py`

**Interfaces:**
- Keep: `is_uv_tool_install()` (still a useful detector if referenced; otherwise delete). Delete: `decide_bump`, `BumpDecision`, `BumpRefused`, `run_uv_tool_install`, `maybe_self_bump`, `reexec` (re-homed in `dispatch.py`), and the `_interactive`/`_confirm` helpers if unused.

- [ ] **Step 1: Find all references**

Run: `git grep -nE "self_bump|maybe_self_bump|BumpRefused|run_uv_tool_install|decide_bump"`
Expected: references only in `cli.py` (removed in Task 5), `self_bump.py`, and its tests.

- [ ] **Step 2: Delete the dead code + its tests**

Remove `maybe_self_bump`, `run_uv_tool_install`, `decide_bump`, `BumpDecision`, `BumpRefused`, and (if unreferenced) `reexec`/`_interactive`/`_confirm` from `self_bump.py`. Delete the corresponding tests in `tests/test_self_bump.py`. If the module is left empty, delete the file and remove its imports.

- [ ] **Step 3: Run the suite to confirm nothing references the removed symbols**

Run: `uv run pytest tests/test_self_bump.py tests/test_dispatch.py -q && uv run ruff check src/framework_cli && uv run mypy src`
Expected: PASS; no unused-import or undefined-name errors.

- [ ] **Step 4: Commit**

```bash
git add src/framework_cli/self_bump.py tests/test_self_bump.py
git commit -m "refactor: retire mutate-global self-bump path (replaced by dispatch)"
```

---

## Task 9: template payload + docs

**Files:**
- Modify: `src/framework_cli/template/.../.github/workflows/ci.yml.jinja` (comment only — CI keeps its explicit `uv tool install @$_commit`, already correct per spec §11.3)
- Modify: generated `Taskfile.yml.jinja` integrity-precondition comment (drop the "do NOT hard-fail on skew" wording — no longer true)
- Modify: `README.md` (bootstrap/usage: project-scoped commands auto-run the project's pinned version; drop "your global CLI must match your project" guidance)
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

**Interfaces:** none (docs/comments only).

- [ ] **Step 1: Edit the comments + README**

Update the three payload/doc spots to match the lockstep model. Keep CI's pinned-install step unchanged (only its comment if it referenced the old skew rationale).

- [ ] **Step 2: Render + verify the generated project is unaffected**

Run (sandbox off, `TMPDIR=/var/tmp` per CLAUDE.md):
`uv run pytest tests/test_copier_runner.py -q`
Expected: PASS (no interpolation/render breakage).

- [ ] **Step 3: Eval-fixture coupling check** — if any edited `.jinja` is anchored by an eval fixture's `change.patch` ([[eval-fixtures-coupled-to-template]]):

Run: `uv run pytest tests/review/test_evals.py::test_every_fixture_realizes -q`
Expected: PASS. (Comment-only edits to Taskfile/CI rarely anchor fixtures, but verify.)

- [ ] **Step 4: Commit**

```bash
git add src/framework_cli/template README.md
git commit -m "docs(template): align CLI invocation guidance with lockstep model"
```

---

## Task 10: branch-end — full gate, render-readiness, release prep

**Files:** none new — verification + release bump.

- [ ] **Step 1: Fast-tier gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && task test:fast`
Expected: all green. Fix any drift.

- [ ] **Step 2: Full tier (docker/acceptance) at branch-end**

Run (sandbox off, `TMPDIR=/var/tmp`): `task test:full`
Expected: green except known-environmental `deploy-e2e :8080` cases ([[deploy-e2e-port-8080-conflict-this-box]]).

- [ ] **Step 3: Release-readiness render** (local gate misses ruff-format / template mypy / dep drift — [[release-readiness-needs-render-not-local-gate]])

Render baseline + all-batteries + a touched single, run their own mypy/ruff. Confirm a freshly rendered project's first `pre-commit` passes.

- [ ] **Step 4: Manual smoke of the dispatch path**

In a scratch rendered project pinned to an older `_commit`, run `uv run framework integrity` and confirm it re-execs the pinned CLI (or fail-louds if `uvx`/network is unavailable) — the one behavior unit tests mock. Document the result in ACTION_LOG.

- [ ] **Step 5: Cut the release** — per [[release-cut-procedure]]: bump `pyproject` + `uv.lock` + `DOGFOOD_COMMIT` + meta-plan/CLAUDE.md, `chore(release)` commit, push (render-matrix = proof), tag → `release.yml`. The dispatch behavior must be in a release for a global CLI to pick it up.

- [ ] **Step 6: Update PLAN/ACTION_LOG**

Tick FWK140 (+ the re-scoped FWK138 floor) to Done; close FWK139's pinned-CLI feature as obviated; append the ACTION_LOG completion entry.

```bash
git add PLAN.md ACTION_LOG.md
git commit -m "chore: FWK140 done — CLI version lockstep shipped"
```

---

## Self-review

**Spec coverage:**
- §2.1 dispatch rule → Tasks 1–4. §2.2 ephemeral-not-global inversion → Task 3 (`reexec` uses `uvx --from`), Task 8 (delete mutate path). §2.3 atomic upgrade / `--bump-cli` retired → Task 5. §2.4 integrity/restore trivially correct → emergent from Tasks 1–4; restore needs no change (runs at the pin). §2.5 staleness in `upgrade --dry-run` → Task 5. §2.6 fail-loud floor → Tasks 3 (uvx-missing) + 6 (integrity bypass). §3 components → Tasks 1–9. §4 edge cases: loop guard (Task 3), SHA pin (Task 2 `_same_version`), offline/uvx-missing (Task 3), no-uv (Task 3), framework-dev escape `FRAMEWORK_NO_DISPATCH` (Task 3), perf self==pin no-op (Task 2). §5 migration → Task 9 docs + Task 10 release. §7 testing → per-task + Task 10. §8 review/release → Task 10.
- **`restore` under bypass:** `restore_file` already fails loud via `require_version_sync` (confirmed BRG42 #3) — no change needed; noted, not a task.
- **Gap check:** none outstanding. `check` deprecation (Task 7) is beyond the strict spec text but follows from §2.5 ("`check` carries no version/staleness role").

**Placeholder scan:** no TBD/"handle edge cases"/uncoded steps — every code step shows code; test bodies are concrete.

**Type consistency:** `Dispatch(action, ref)`, `decide_dispatch(kind, installed_tag, target_tag, project_commit, reexecuted)`, `classify(command)`, `resolve_project_commit(kind, positionals)`, `reexec(ref, argv)`, `dispatch(argv)`, `main()` — names/signatures consistent across Tasks 1–4 and their call sites in Tasks 5–6. `read_commit`/`latest_release`/`installed_version_tag`/`parse_version`/`REPO_URL` match `framework_cli.source` + `version_sync` exports verified in the source.

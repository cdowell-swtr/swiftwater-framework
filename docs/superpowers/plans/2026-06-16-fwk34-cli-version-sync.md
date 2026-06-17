# FWK34 — CLI/project version-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the manual developer paths (`upgrade`, `restore`, `integrity`) uphold the invariant that `restore`/`integrity` are only correct when the installed CLI version equals the project's recorded `_commit` — so a project upgraded past the CLI stops silently producing wrong-version canonicals.

**Architecture:** A new pure `version_sync` helper compares `version_tag(installed_framework_version())` to the project's `_commit`. `restore` hard-refuses on skew; `integrity` warns non-fatally on skew (never blocks `task dev`); `upgrade` offers to self-bump the CLI to the target (`uv tool install …@target` + `os.execvp` re-exec) when it's a `uv tool` install on a TTY, else refuses. Plus a `framework --version` flag. Framework source only — no template payload.

**Tech Stack:** Python 3.12, Typer CLI (`typer.testing.CliRunner` for tests), `uv` package manager, pytest.

**Spec:** `docs/superpowers/specs/2026-06-16-fwk34-cli-version-sync-design.md`
**Branch:** `fwk34-cli-version-sync` (already created; carries the spec + this plan).

**Execution notes (read before starting):**
- **Review-model policy** (per `CLAUDE.md` / [[subagent-review-model-pattern]]): implementers → **Sonnet** (Haiku for the trivial `--version` task); spec-compliance review → **Sonnet**; code-quality review → **Opus**; branch-end whole-branch review → **Opus**. Pass `model` explicitly per role.
- This is **framework source** (`src/framework_cli/`), tested in the framework venv via `uv run pytest` — *not* template payload. No render/acceptance loop needed.
- Quality gate per task: `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy src`.
- Commit-gate: stage `PLAN.md`/`ACTION_LOG.md` with each commit; separate `git add` then `git commit` ([[commit-gate-hook-timing]]).
- Existing facts you'll reuse: `framework_cli.integrity.manifest.installed_framework_version()` → bare `"0.2.11"`; `framework_cli.source.version_tag(v)` → `"v0.2.11"`; `framework_cli.source.read_commit(project)` → the `.copier-answers.yml` `_commit` (e.g. `"v0.2.11"`) or `None`; `framework_cli.source.REPO_URL` → the HTTPS repo URL; `latest_release()` → highest remote `vX.Y.Z` tag.

---

## File Structure

**Framework source (ships v0.2.12):**
- Create: `src/framework_cli/version_sync.py` — skew helper + `VersionSkew` + `VersionSkewError` + `parse_version` + `require_version_sync`.
- Create: `src/framework_cli/self_bump.py` — `decide_bump` (pure) + I/O seams (`is_uv_tool_install`, `run_uv_tool_install`, `reexec`) + `maybe_self_bump` orchestrator + `BumpRefused`.
- Modify: `src/framework_cli/cli.py` — `--version` callback; `restore` already raises `ValueError`→exit (covered); `integrity` command skew-aware branch; `upgrade` command `--bump-cli` + self-bump wiring.
- Modify: `src/framework_cli/integrity/restore.py` — `restore_file` hard-guard.

**Tests:**
- Create: `tests/test_version_sync.py`, `tests/test_self_bump.py`.
- Modify: `tests/test_cli.py` (`--version`, `integrity` skew), `tests/integrity/` (restore guard), `tests/test_upgrade.py` (self-bump wiring).

---

## Task 1: `framework --version`

**Files:**
- Modify: `src/framework_cli/cli.py` (callback at line ~50)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cli.py`:

```python
def test_version_flag_prints_installed_version():
    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.integrity.manifest import installed_framework_version

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert installed_framework_version() in result.stdout
```

(Confirm `tests/test_cli.py` already imports/uses `CliRunner` + `app`; if so, reuse the module-level imports instead of the local ones.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_version_flag_prints_installed_version -q`
Expected: FAIL — `--version` is an unknown option (exit code 2).

- [ ] **Step 3: Add the `--version` callback** — in `src/framework_cli/cli.py`, replace the existing callback:

```python
@app.callback()
def _main() -> None:
    """Framework CLI — scaffold solid, observable, testable Python projects."""
```

with:

```python
def _version_callback(value: bool) -> None:
    if value:
        typer.echo(installed_framework_version())
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed framework CLI version and exit.",
    ),
) -> None:
    """Framework CLI — scaffold solid, observable, testable Python projects."""
```

(`installed_framework_version` is already imported in `cli.py` at line 13.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_version_flag_prints_installed_version -q`
Expected: PASS.

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff format src/framework_cli/cli.py tests/test_cli.py
uv run ruff check src/framework_cli/cli.py tests/test_cli.py
uv run mypy src
```
Then (update `ACTION_LOG.md` first; separate add then commit):
```bash
git add src/framework_cli/cli.py tests/test_cli.py ACTION_LOG.md
git commit -m "feat(fwk34): framework --version"
```

---

## Task 2: `version_sync.py` — skew helper

**Files:**
- Create: `src/framework_cli/version_sync.py`
- Test: `tests/test_version_sync.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_version_sync.py`:

```python
import pytest

from framework_cli import version_sync as vs
from framework_cli.version_sync import VersionSkew, VersionSkewError, parse_version


def _project(tmp_path, commit: str | None):
    answers = tmp_path / ".copier-answers.yml"
    body = "project_slug: demo\n"
    if commit is not None:
        body += f"_commit: {commit}\n"
    answers.write_text(body)
    return tmp_path


@pytest.mark.parametrize(
    "installed,commit,expected",
    [
        ("0.2.11", "v0.2.11", VersionSkew.IN_SYNC),
        ("0.2.8", "v0.2.11", VersionSkew.CLI_BEHIND),
        ("0.2.11", "v0.2.8", VersionSkew.CLI_AHEAD),
    ],
)
def test_project_version_skew(monkeypatch, tmp_path, installed, commit, expected):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: installed)
    skew, installed_tag, commit_tag = vs.project_version_skew(_project(tmp_path, commit))
    assert skew is expected
    assert installed_tag == f"v{installed}"
    assert commit_tag == commit


def test_missing_commit_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    with pytest.raises(VersionSkewError, match="_commit"):
        vs.project_version_skew(_project(tmp_path, None))


def test_require_version_sync_passes_in_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    vs.require_version_sync(_project(tmp_path, "v0.2.11"))  # no raise


def test_require_version_sync_behind_names_remedy(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    with pytest.raises(VersionSkewError, match="uv tool install.*@v0.2.11"):
        vs.require_version_sync(_project(tmp_path, "v0.2.11"))


def test_require_version_sync_ahead_suggests_upgrade(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    with pytest.raises(VersionSkewError, match="framework upgrade"):
        vs.require_version_sync(_project(tmp_path, "v0.2.8"))


def test_parse_version():
    assert parse_version("v0.2.11") == (0, 2, 11)
    assert parse_version("0.2.11") == (0, 2, 11)
    with pytest.raises(ValueError):
        parse_version("v0+unknown")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_version_sync.py -q`
Expected: FAIL — `No module named 'framework_cli.version_sync'`.

- [ ] **Step 3: Create `src/framework_cli/version_sync.py`**:

```python
"""Compare the installed framework CLI version against a project's recorded `_commit`.

`restore`/`integrity` render the canonical from the *bundled* (installed-CLI) template, so
they are only correct when the installed version equals the project's `_commit`. This module
is the single source of truth for that comparison (FWK34).
"""

from __future__ import annotations

import enum
from pathlib import Path

from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.source import REPO_URL, read_commit, version_tag


class VersionSkewError(Exception):
    """The installed CLI version does not match the project's recorded `_commit`."""


class VersionSkew(enum.Enum):
    IN_SYNC = "in_sync"
    CLI_BEHIND = "cli_behind"  # installed < _commit  (project upgraded past the CLI)
    CLI_AHEAD = "cli_ahead"  # installed > _commit  (CLI newer than the project pin)


def parse_version(tag: str) -> tuple[int, int, int]:
    """Parse a ``vX.Y.Z`` (or ``X.Y.Z``) tag into a comparable tuple."""
    core = tag[1:] if tag.startswith("v") else tag
    parts = core.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a vX.Y.Z version: {tag!r}")
    a, b, c = (int(p) for p in parts)
    return (a, b, c)


def project_version_skew(project: Path) -> tuple[VersionSkew, str, str]:
    """Return ``(skew, installed_tag, commit_tag)`` for ``project``.

    Raises ``VersionSkewError`` if the project has no `_commit`, or the installed CLI
    version is unparseable (odd install state).
    """
    installed_tag = version_tag(installed_framework_version())
    commit_tag = read_commit(project)
    if commit_tag is None:
        raise VersionSkewError(
            ".copier-answers.yml has no _commit — cannot determine the project's "
            "framework version"
        )
    try:
        installed_v = parse_version(installed_tag)
    except ValueError as exc:
        raise VersionSkewError(
            f"cannot determine the installed framework CLI version ({installed_tag})"
        ) from exc
    commit_v = parse_version(commit_tag)
    if installed_v == commit_v:
        return (VersionSkew.IN_SYNC, installed_tag, commit_tag)
    if installed_v < commit_v:
        return (VersionSkew.CLI_BEHIND, installed_tag, commit_tag)
    return (VersionSkew.CLI_AHEAD, installed_tag, commit_tag)


def skew_remedy(skew: VersionSkew, installed_tag: str, commit_tag: str) -> str:
    """The directional 'how to fix' sentence for a non-IN_SYNC skew."""
    install_cmd = f"uv tool install git+{REPO_URL}@{commit_tag}"
    if skew is VersionSkew.CLI_BEHIND:
        return f"Upgrade the CLI: {install_cmd}, then retry."
    return (
        f"Either upgrade the project (`framework upgrade`), or pin a matching CLI: "
        f"{install_cmd}."
    )


def require_version_sync(project: Path) -> None:
    """Raise ``VersionSkewError`` with actionable guidance unless installed == `_commit`."""
    skew, installed_tag, commit_tag = project_version_skew(project)
    if skew is VersionSkew.IN_SYNC:
        return
    raise VersionSkewError(
        f"This project is pinned {commit_tag} but your framework CLI is {installed_tag}. "
        + skew_remedy(skew, installed_tag, commit_tag)
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_version_sync.py -q`
Expected: PASS (all parametrizations).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff format src/framework_cli/version_sync.py tests/test_version_sync.py
uv run ruff check src/framework_cli/version_sync.py tests/test_version_sync.py
uv run mypy src
git add src/framework_cli/version_sync.py tests/test_version_sync.py ACTION_LOG.md
git commit -m "feat(fwk34): version_sync skew helper"
```

---

## Task 3: `restore` hard guard

**Files:**
- Modify: `src/framework_cli/integrity/restore.py` (`restore_file`, line 54)
- Test: `tests/integrity/test_restore_version_guard.py` (new)

- [ ] **Step 1: Write the failing test** — create `tests/integrity/test_restore_version_guard.py`:

```python
import pytest

import framework_cli.version_sync as vs
from framework_cli.integrity import restore as restore_mod
from framework_cli.version_sync import VersionSkewError


def test_restore_refuses_on_skew(monkeypatch, tmp_path):
    # A project pinned ahead of the installed CLI: restore must refuse, not render.
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.2.11\n")
    (tmp_path / ".framework").mkdir()
    (tmp_path / ".framework" / "integrity.lock").write_text("{}")  # never reached
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")

    rendered = []
    monkeypatch.setattr(
        restore_mod, "render_project", lambda *a, **k: rendered.append(1)
    )
    with pytest.raises(VersionSkewError, match="uv tool install.*@v0.2.11"):
        restore_mod.restore_file(tmp_path, "infra/docker/Dockerfile")
    assert rendered == []  # guard fired before any render
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_restore_version_guard.py -q`
Expected: FAIL — no `VersionSkewError` raised (restore proceeds past the guard).

- [ ] **Step 3: Add the guard** — in `src/framework_cli/integrity/restore.py`, add the import near the top:

```python
from framework_cli.version_sync import require_version_sync
```

and call it as the first line inside `restore_file`, before the lock check:

```python
def restore_file(project: Path, rel: str) -> None:
    """Re-render `rel` from the bundled template and overwrite the project's copy.

    6a restores locked (full-file) entries to the installed framework version.
    """
    require_version_sync(project)  # FWK34: refuse rather than render a wrong-version canonical
    lock = project / _LOCK_REL
    ...
```

(Placing it first means a CLI/`_commit` skew is reported before anything else. `require_version_sync` reads `.copier-answers.yml`; the test writes one.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_restore_version_guard.py -q`
Expected: PASS.

- [ ] **Step 5: Confirm the `restore` command surfaces it** — `cli.py::restore` already catches `ValueError` (line 259). `VersionSkewError` is **not** a `ValueError`, so add it to the except. In `cli.py`, change the `restore` command's except clause:

```python
    try:
        restore_file(Path.cwd(), file)
    except (ValueError, FileNotFoundError, VersionSkewError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
```

and add the import at the top of `cli.py`:

```python
from framework_cli.version_sync import VersionSkewError
```

- [ ] **Step 6: Verify the full restore test set still passes**

Run: `uv run pytest tests/integrity/ tests/test_cli.py -q`
Expected: PASS. (Existing restore tests that don't set up a skew must still pass — they either monkeypatch `installed_framework_version`/`_commit` to match, or their fixture `.copier-answers.yml` records a `_commit` equal to the installed version. If an existing restore test now fails on the guard, make its `.copier-answers.yml` `_commit` match `installed_framework_version()` — that is the in-sync precondition restore now requires. Show the fixup in the commit.)

- [ ] **Step 7: Gate + commit**

```bash
uv run ruff format src/framework_cli/integrity/restore.py src/framework_cli/cli.py tests/integrity/test_restore_version_guard.py
uv run ruff check src/framework_cli/integrity/restore.py src/framework_cli/cli.py tests/integrity/test_restore_version_guard.py
uv run mypy src
git add src/framework_cli/integrity/restore.py src/framework_cli/cli.py tests/integrity/test_restore_version_guard.py ACTION_LOG.md
git commit -m "feat(fwk34): restore hard-refuses on CLI/_commit skew"
```

---

## Task 4: `integrity` skew-aware (non-blocking)

**Files:**
- Modify: `src/framework_cli/cli.py` (`integrity` command, line ~109)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_cli.py`:

```python
def test_integrity_warns_non_fatally_on_skew(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.2.11\n")
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    monkeypatch.chdir(tmp_path)

    # If the skew branch fails to short-circuit, this would run the real check and explode.
    def _boom(*a, **k):
        raise AssertionError("check_integrity must not run under skew")

    monkeypatch.setattr(cli, "check_integrity", _boom)

    result = CliRunner().invoke(app, [])  # `framework integrity`
    # NOTE: invoke with ["integrity"] — see Step 3 note on command name.
    assert result.exit_code == 0  # non-fatal: never blocks `task dev`
    assert "0.2.8" in result.stdout and "v0.2.11" in result.stdout
    assert "uv tool install" in result.stdout
```

Correct the invoke to the real command name: `CliRunner().invoke(app, ["integrity"])`. Final assertion block:

```python
    result = CliRunner().invoke(app, ["integrity"])
    assert result.exit_code == 0
    assert "0.2.8" in result.stdout and "v0.2.11" in result.stdout
    assert "uv tool install" in result.stdout
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_integrity_warns_non_fatally_on_skew -q`
Expected: FAIL — `check_integrity` runs (the `_boom` assertion fires) because there's no skew short-circuit yet.

- [ ] **Step 3: Add the skew branch** — in `src/framework_cli/cli.py`, in the `integrity` command, after the `allow_drift` block and before `findings = check_integrity(...)`, insert:

```python
    from framework_cli.version_sync import (
        VersionSkew,
        project_version_skew,
        skew_remedy,
    )

    skew, installed_tag, commit_tag = project_version_skew(project)
    if skew is not VersionSkew.IN_SYNC:
        # Drift computed against a wrong-version canonical is unreliable, so do not assert
        # it — warn and exit 0 so `task dev`/`task ci` are never blocked on benign skew.
        typer.echo(
            f"framework integrity: skipped — your framework CLI is {installed_tag} but this "
            f"project is pinned {commit_tag}, so integrity cannot verify against the matching "
            f"template version (and `framework restore` is disabled until they match). "
            + skew_remedy(skew, installed_tag, commit_tag)
        )
        raise typer.Exit(0)

    findings = check_integrity(project, ci=ci)
```

`project_version_skew` raises `VersionSkewError` on a missing `_commit`; the command should surface that as an error. Wrap just the skew lookup:

```python
    try:
        skew, installed_tag, commit_tag = project_version_skew(project)
    except VersionSkewError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
```

(`VersionSkewError` is imported at the top of `cli.py` from Task 3.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_integrity_warns_non_fatally_on_skew -q`
Expected: PASS.

- [ ] **Step 5: Add the in-sync regression test** — append to `tests/test_cli.py` (proves `--ci`/in-sync still runs the real check):

```python
def test_integrity_runs_normally_when_in_sync(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.2.11\n")
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    monkeypatch.chdir(tmp_path)

    called = []
    monkeypatch.setattr(cli, "check_integrity", lambda project, ci: called.append(ci) or [])

    result = CliRunner().invoke(app, ["integrity"])
    assert result.exit_code == 0
    assert called == [False]  # the real check ran (no findings → OK)
    assert "framework integrity: OK" in result.stdout
```

Run: `uv run pytest tests/test_cli.py -k integrity -q` → PASS.

- [ ] **Step 6: Gate + commit**

```bash
uv run ruff format src/framework_cli/cli.py tests/test_cli.py
uv run ruff check src/framework_cli/cli.py tests/test_cli.py
uv run mypy src
git add src/framework_cli/cli.py tests/test_cli.py ACTION_LOG.md
git commit -m "feat(fwk34): integrity warns (non-fatal) on CLI/_commit skew"
```

---

## Task 5: `self_bump.py` — pure decision + seams

**Files:**
- Create: `src/framework_cli/self_bump.py`
- Test: `tests/test_self_bump.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_self_bump.py`:

```python
import pytest

from framework_cli.self_bump import BumpDecision, decide_bump


def d(installed, target, *, uv=True, tty=True, flag=False) -> BumpDecision:
    return decide_bump(
        installed_tag=installed,
        target_tag=target,
        is_uv_tool=uv,
        is_tty=tty,
        bump_flag=flag,
    )


def test_proceed_when_target_not_newer():
    assert d("0.2.11", "v0.2.11").action == "proceed"
    assert d("0.2.11", "v0.2.8").action == "proceed"


def test_refuse_when_not_uv_tool_install():
    dec = d("0.2.8", "v0.2.11", uv=False)
    assert dec.action == "refuse"
    assert "uv tool install" in dec.message and "@v0.2.11" in dec.message


def test_bump_when_flag_set_even_non_tty():
    assert d("0.2.8", "v0.2.11", tty=False, flag=True).action == "bump"


def test_prompt_when_uv_tool_and_tty():
    assert d("0.2.8", "v0.2.11", tty=True, flag=False).action == "prompt"


def test_refuse_when_non_interactive_and_no_flag():
    dec = d("0.2.8", "v0.2.11", tty=False, flag=False)
    assert dec.action == "refuse"
    assert "--bump-cli" in dec.message
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_self_bump.py -q`
Expected: FAIL — `No module named 'framework_cli.self_bump'`.

- [ ] **Step 3: Create `src/framework_cli/self_bump.py`**:

```python
"""Assisted CLI self-bump for `framework upgrade` (FWK34).

When the upgrade target is newer than the installed CLI, the developer's CLI must be bumped
to the target first (restore/integrity render from the installed CLI). `decide_bump` is the
pure policy; the I/O seams below are monkeypatched in tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from framework_cli.source import REPO_URL
from framework_cli.version_sync import parse_version


class BumpRefused(Exception):
    """The CLI must be bumped to the target but cannot/should not be self-bumped."""


@dataclass(frozen=True)
class BumpDecision:
    action: str  # "proceed" | "prompt" | "bump" | "refuse"
    message: str  # populated only for "refuse"


def decide_bump(
    *,
    installed_tag: str,
    target_tag: str,
    is_uv_tool: bool,
    is_tty: bool,
    bump_flag: bool,
) -> BumpDecision:
    """Pure policy: proceed (target not newer), bump, prompt, or refuse-with-message."""
    if parse_version(target_tag) <= parse_version(installed_tag):
        return BumpDecision("proceed", "")
    install_cmd = f"uv tool install git+{REPO_URL}@{target_tag}"
    if not is_uv_tool:
        return BumpDecision(
            "refuse",
            f"Your framework CLI is {installed_tag}; the target is {target_tag}. "
            f"restore/integrity render from the installed CLI, so it must match the target. "
            f"This CLI was not installed via `uv tool`, so it can't self-update — upgrade it "
            f"manually: {install_cmd}, then re-run.",
        )
    if bump_flag:
        return BumpDecision("bump", "")
    if is_tty:
        return BumpDecision("prompt", "")
    return BumpDecision(
        "refuse",
        f"Your framework CLI is {installed_tag}; the target is {target_tag}. Upgrade the "
        f"CLI first: {install_cmd} (or pass --bump-cli), then re-run.",
    )


# --- I/O seams (monkeypatched in tests) ---
def is_uv_tool_install() -> bool:
    """True if the running `framework` console-script lives under `uv tool dir`.

    Fail safe: any uncertainty (no `uv`, unreadable path) returns False so we never
    self-mutate a non-`uv tool` install.
    """
    try:
        tool_dir = subprocess.run(
            ["uv", "tool", "dir"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    if not tool_dir:
        return False
    exe = shutil.which("framework") or sys.argv[0]
    try:
        Path(exe).resolve().relative_to(Path(tool_dir).resolve())
        return True
    except (ValueError, OSError):
        return False


def run_uv_tool_install(target_tag: str) -> None:
    subprocess.run(
        ["uv", "tool", "install", f"git+{REPO_URL}@{target_tag}"], check=True
    )


def reexec(argv: list[str]) -> None:
    os.execvp(argv[0], argv)  # replaces the process image; returns only on failure
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_self_bump.py -q`
Expected: PASS.

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff format src/framework_cli/self_bump.py tests/test_self_bump.py
uv run ruff check src/framework_cli/self_bump.py tests/test_self_bump.py
uv run mypy src
git add src/framework_cli/self_bump.py tests/test_self_bump.py ACTION_LOG.md
git commit -m "feat(fwk34): self_bump decision policy + I/O seams"
```

---

## Task 6: Wire self-bump into `upgrade`

**Files:**
- Modify: `src/framework_cli/self_bump.py` (add `maybe_self_bump` orchestrator)
- Modify: `src/framework_cli/cli.py` (`upgrade` command, line ~358)
- Test: `tests/test_upgrade.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_upgrade.py`:

```python
def test_upgrade_bumps_cli_then_reexecs_when_target_newer(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.self_bump as sb
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    monkeypatch.setattr(sb, "is_uv_tool_install", lambda: True)
    monkeypatch.setattr(sb, "_interactive", lambda: True)
    monkeypatch.setattr(sb, "_confirm", lambda msg: True)

    installed, reexeced = [], []
    monkeypatch.setattr(sb, "run_uv_tool_install", lambda tag: installed.append(tag))
    monkeypatch.setattr(sb, "reexec", lambda argv: reexeced.append(argv))
    # upgrade_project must NOT run in this process (the re-exec'd one does it)
    monkeypatch.setattr(
        cli, "upgrade_project", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )

    CliRunner().invoke(app, ["upgrade", str(project)])
    assert installed == ["v0.2.11"]
    assert reexeced and reexeced[0][1:3] == ["upgrade", str(project)]


def test_upgrade_refuses_when_non_uv_tool(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.self_bump as sb
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    monkeypatch.setattr(sb, "is_uv_tool_install", lambda: False)

    result = CliRunner().invoke(app, ["upgrade", str(project)])
    assert result.exit_code == 1
    assert "uv tool install" in result.stdout and "@v0.2.11" in result.stdout


def test_upgrade_proceeds_when_target_not_newer(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.version_sync as vs
    from framework_cli.cli import app
    from framework_cli.upgrade import UpgradeOutcome

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    called = []
    monkeypatch.setattr(
        cli,
        "upgrade_project",
        lambda p, to: called.append(to)
        or UpgradeOutcome(status="already-current", target=to),
    )

    result = CliRunner().invoke(app, ["upgrade", str(project)])
    assert result.exit_code == 0
    assert called == ["v0.2.11"]  # resolved target passed through; no bump attempted
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_upgrade.py -k "bumps_cli or refuses_when_non_uv or proceeds_when_target" -q`
Expected: FAIL — `upgrade` does not yet resolve the target / call the self-bump path (`maybe_self_bump`, `_interactive`, `_confirm` don't exist).

- [ ] **Step 3: Add the orchestrator** — append to `src/framework_cli/self_bump.py`:

```python
def _interactive() -> bool:
    return sys.stdin.isatty()


def _confirm(message: str) -> bool:
    import typer

    return typer.confirm(message, default=True)


def maybe_self_bump(
    *, installed_tag: str, target_tag: str, bump_flag: bool, argv: list[str]
) -> None:
    """If the target is newer than the installed CLI: self-bump+re-exec, or raise BumpRefused.

    Returns normally only when the upgrade should proceed in *this* process (target is not
    newer than the installed CLI). On a bump it `reexec`s and never returns.
    """
    decision = decide_bump(
        installed_tag=installed_tag,
        target_tag=target_tag,
        is_uv_tool=is_uv_tool_install(),
        is_tty=_interactive(),
        bump_flag=bump_flag,
    )
    if decision.action == "proceed":
        return
    if decision.action == "refuse":
        raise BumpRefused(decision.message)
    if decision.action == "prompt":
        if not _confirm(
            f"Your framework CLI is {installed_tag}; the target is {target_tag}. "
            "Bump the CLI and continue the upgrade?"
        ):
            raise BumpRefused(
                f"Upgrade the CLI when ready: uv tool install git+{REPO_URL}@{target_tag}"
            )
    run_uv_tool_install(target_tag)
    reexec(argv)
```

- [ ] **Step 4: Wire the `upgrade` command** — in `src/framework_cli/cli.py`, add the import:

```python
from framework_cli.self_bump import BumpRefused, maybe_self_bump
```

and rewrite the `upgrade` command body. New signature + body:

```python
@app.command()
def upgrade(
    name: str = typer.Argument(..., help="Path to the project to upgrade."),
    to: str = typer.Option(
        None, "--to", help="Target release tag (default: the latest release)."
    ),
    bump_cli: bool = typer.Option(
        False,
        "--bump-cli",
        help="Bump the framework CLI to the target non-interactively before upgrading.",
    ),
) -> None:
    """Move a project onto a newer framework release, then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)

    target = to if to is not None else latest_release()
    if target is None:
        typer.echo(
            "Error: no framework release found (or the remote is unreachable); "
            "cannot upgrade.",
            err=True,
        )
        raise typer.Exit(1)

    # FWK34: restore/integrity render from the installed CLI, so the CLI must be at least the
    # target. Offer to self-bump (uv tool + TTY) or re-exec; otherwise refuse with guidance.
    installed_tag = version_tag(installed_framework_version())
    try:
        maybe_self_bump(
            installed_tag=installed_tag,
            target_tag=target,
            bump_flag=bump_cli,
            argv=sys.argv,
        )
    except BumpRefused as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        outcome = upgrade_project(project, to=target)
    except UpgradeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

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
        f'  git add -A && git commit -m "chore: upgrade framework to {outcome.target}" '
        "&& git push"
    )
```

(`version_tag`, `installed_framework_version`, `latest_release`, `sys` are all already imported in `cli.py`. The previous `upgrade_project(project, to=to)` becomes `to=target` — the resolved tag — so `upgrade_project` does not re-resolve `latest_release()` and the version compared by self-bump is the version actually applied.)

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/test_upgrade.py -q`
Expected: PASS — including the three new tests and the existing upgrade tests. (Existing `upgrade` tests call `upgrade_project` directly or invoke the command with installed==target; if any existing command-level test now hits the self-bump path, monkeypatch `latest_release`/`installed_framework_version` so target ≤ installed, or `is_uv_tool_install`→False with the expected refuse. Show fixups in the commit.)

- [ ] **Step 6: Gate + commit**

```bash
uv run ruff format src/framework_cli/self_bump.py src/framework_cli/cli.py tests/test_upgrade.py
uv run ruff check src/framework_cli/self_bump.py src/framework_cli/cli.py tests/test_upgrade.py
uv run mypy src
git add src/framework_cli/self_bump.py src/framework_cli/cli.py tests/test_upgrade.py ACTION_LOG.md
git commit -m "feat(fwk34): upgrade offers assisted CLI self-bump (+ --bump-cli)"
```

---

## Task 7: Full validation, review, release

**Files:** verification + release bump only.

- [ ] **Step 1: Full framework gate**

```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (Acceptance/docker tier unaffected — this is CLI behaviour.)

- [ ] **Step 2: Manual smoke (optional, sanity)** — `uv run framework --version` prints the version; in a scratch project dir whose `.copier-answers.yml` `_commit` differs from the installed version, `uv run framework restore <file>` refuses and `uv run framework integrity` warns non-fatally (exit 0).

- [ ] **Step 3: Branch-end review** — spec-compliance (**Sonnet**) against `docs/superpowers/specs/2026-06-16-fwk34-cli-version-sync-design.md`, then code-quality (**Opus**) over `git diff master..HEAD`. Address findings; controller verifies commits.

- [ ] **Step 4: Cut the release (v0.2.12)** — per [[release-cut-procedure]], folded into this PR: bump `pyproject.toml` `0.2.11 → 0.2.12`; `DOGFOOD_COMMIT v0.2.11 → v0.2.12` (`src/framework_cli/dogfood.py`); `uv lock`. Meta-plan/CLAUDE.md untouched (frozen). Move FWK34 → PLAN `Done`. Commit `chore(release): v0.2.12 — FWK34 CLI/project version-sync`.

- [ ] **Step 5: Finish the branch** — push, open/update the PR; required checks `gate` + `build` + `render-complete` green; squash-merge; tag `v0.2.12` on master → `release.yml`; verify the published release + master content.

---

## Self-Review (completed during planning)

- **Spec coverage:** change 1 `--version` → Task 1 ✓; change 2 skew helper → Task 2 ✓; change 3 B (`restore` hard) → Task 3 ✓; change 3 B (`integrity` advisory, non-blocking, both directions, `--ci`/in-sync unchanged) → Task 4 ✓; change 4 C (pure decision + seams) → Task 5 ✓; C (orchestrator + `upgrade` wiring + `--bump-cli`) → Task 6 ✓; testing items → covered per task; release → Task 7 ✓. Rejected alternative A → not implemented (correct).
- **Placeholder scan:** none — every step has full code; the one fail-safe detail (`is_uv_tool_install` detection) is fully implemented with a documented "uncertainty → False" default.
- **Type/name consistency:** `VersionSkew`/`VersionSkewError`/`project_version_skew`/`require_version_sync`/`skew_remedy` (version_sync), `BumpDecision`/`decide_bump`/`maybe_self_bump`/`is_uv_tool_install`/`run_uv_tool_install`/`reexec`/`_interactive`/`_confirm`/`BumpRefused` (self_bump), and `installed_tag`/`target_tag`/`commit_tag` vocabulary are identical across tasks and tests. `decide_bump` returns the four actions `proceed|prompt|bump|refuse` used identically by `maybe_self_bump` and `tests/test_self_bump.py`.
- **Open verification deferred to implementation (flagged inline):** existing `restore`/`upgrade`/`integrity` tests may assume no skew; Tasks 3/6 Step notes require aligning their fixture `_commit` to the installed version (the in-sync precondition the guard now enforces).

# `framework upgrade` + rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `framework upgrade` as the single path that moves a generated project across framework versions, separating version movement (`upgrade`) from battery mutation (`upskill --with` / `downskill`), and fix the identity-stripping bug in the shared update core.

**Architecture:** Extract today's `upskill_project` update mechanics into one shared `_apply_update(project, *, vcs_ref, batteries, channels)` helper that reads + passes + re-records the four identity answers (with a fail-closed guard on missing identity). Two re-render callers use it: a new `upgrade_project` (moves to a target tag, default latest, with a clean-tree precondition) and the existing `upskill_project` (now *pins* to the project's recorded version — battery change only, no implicit version bump). `downskill` is untouched (it splices files, never runs `copier update`).

**Tech Stack:** Python, Typer (CLI), Copier (`run_update`), pytest, go-task (`task test`), git.

**Spec:** `docs/superpowers/specs/2026-06-11-framework-upgrade-design.md`

**Review-model policy (restate per the working agreement — do NOT let the generic "least powerful model" guidance collapse these):** implementers → **Sonnet** (Haiku only for trivial mechanical tasks); spec-compliance review → **Sonnet**; code-quality review → **Opus**; the final whole-branch review → **Opus**. Pass `model` explicitly per role.

**Conventions:**
- Run all tooling via `uv run` (e.g. `uv run pytest …`). Heavy render tests: prefix `TMPDIR=/var/tmp`.
- The gate must be green before each commit: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`.
- A `PreToolUse` hook blocks `git commit` until `CLAUDE.md` is staged. Update the **Current State** pointer (with a `Last updated` datetime + timezone) and `git add CLAUDE.md` as part of each commit. Stage with a separate `git add` call, then `git commit` as its own call (chaining trips the hook).

---

## File Structure

- **Create:** `src/framework_cli/upgrade.py` — `framework upgrade` logic: `UpgradeError`, `_is_clean_tree`, `UpgradeOutcome`, `upgrade_project(project, *, to=None)`. Thin; delegates mechanics to `_apply_update`.
- **Modify:** `src/framework_cli/source.py` — add `read_identity`, `record_identity`, `read_commit`.
- **Modify:** `src/framework_cli/upskill.py` — extract `_apply_update(project, *, vcs_ref, batteries, channels)`; identity read/guard/pass/record live here; `upskill_project` now resolves the recorded version and calls `_apply_update` (pins version).
- **Modify:** `src/framework_cli/cli.py` — add the `upgrade` command; block bare `upskill`; re-point `check`'s message at `upgrade`.
- **Modify:** `documentation/using/upgrading.md` — drop the "Planned" banner; make it the real reference.
- **Create:** `tests/test_upgrade.py` — `upgrade_project` + identity-invariant tests (synthetic throwaway repos).
- **Modify:** `tests/test_upskill.py` — retarget version-movement tests to `upgrade`; add the version-pin assertion to battery tests.
- **Modify:** `tests/test_source.py` — `read_identity` / `record_identity` / `read_commit` unit tests.
- **Modify:** `tests/test_cli.py` — bare-`upskill` block, `upgrade` command messaging, `check` re-point.

**Identity keys (exact, from `src/framework_cli/template/copier.yml`):** `project_name`, `project_slug`, `package_name`, `python_version`.

---

## Task 1: `read_identity` / `record_identity` / `read_commit` in `source.py`

**Files:**
- Modify: `src/framework_cli/source.py`
- Test: `tests/test_source.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_source.py`:

```python
def test_read_identity_returns_the_four_answers(tmp_path):
    from framework_cli.source import read_identity

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text(
        '_commit: v0.1.0\n'
        'project_name: My App\n'
        'project_slug: my-app\n'
        'package_name: my_app\n'
        'python_version: "3.12"\n'
        'batteries: []\n'
    )
    assert read_identity(proj) == {
        "project_name": "My App",
        "project_slug": "my-app",
        "package_name": "my_app",
        "python_version": "3.12",
    }


def test_read_identity_omits_missing_keys(tmp_path):
    from framework_cli.source import read_identity

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text("project_name: Only Name\n")
    assert read_identity(proj) == {"project_name": "Only Name"}


def test_record_identity_round_trips_through_read(tmp_path):
    from framework_cli.source import read_identity, record_identity

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text("_commit: v0.1.0\nbatteries: []\n")
    identity = {
        "project_name": "My App",
        "project_slug": "my-app",
        "package_name": "my_app",
        "python_version": "3.12",
    }
    record_identity(proj, identity)
    text = (proj / ".copier-answers.yml").read_text()
    assert "_commit: v0.1.0" in text  # untouched
    assert read_identity(proj) == identity


def test_record_identity_replaces_existing_values(tmp_path):
    from framework_cli.source import read_identity, record_identity

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text(
        "package_name: old_name\npython_version: \"3.11\"\n"
    )
    record_identity(proj, {"package_name": "new_name", "python_version": "3.12"})
    assert read_identity(proj) == {"package_name": "new_name", "python_version": "3.12"}


def test_read_commit_returns_recorded_tag(tmp_path):
    from framework_cli.source import read_commit

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text("_commit: v0.2.2\nbatteries: []\n")
    assert read_commit(proj) == "v0.2.2"


def test_read_commit_none_when_absent(tmp_path):
    from framework_cli.source import read_commit

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text("batteries: []\n")
    assert read_commit(proj) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_source.py -k "identity or read_commit" -v`
Expected: FAIL — `ImportError`/`AttributeError` (`read_identity` not defined).

- [ ] **Step 3: Implement the three helpers**

Add to `src/framework_cli/source.py` (after `record_alert_channels`). Add `import json` at the top with the other imports.

```python
IDENTITY_KEYS = ("project_name", "project_slug", "package_name", "python_version")


def read_identity(project: Path) -> dict[str, str]:
    """The identity answers present in .copier-answers.yml ({} if none/absent).

    Only keys actually present are returned, so callers can detect a missing/stripped set.
    """
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return {}
    data = yaml.safe_load(answers.read_text()) or {}
    return {k: str(data[k]) for k in IDENTITY_KEYS if k in data and data[k] is not None}


def record_identity(project: Path, identity: dict[str, str]) -> None:
    """Write the identity answers into .copier-answers.yml (framework-owned, like batteries).

    Copier does not reliably re-emit these subdir-declared answers through the portable
    `_subdirectory` source on update, so the framework re-records them: drop any existing
    line for each key and re-append it. Values are JSON-quoted, which is valid YAML and
    preserves strings such as python_version ("3.12") and names with spaces.
    """
    answers = project / _ANSWERS_REL
    out = [
        line
        for line in answers.read_text().splitlines()
        if not any(line.startswith(f"{k}:") for k in IDENTITY_KEYS)
    ]
    for key in IDENTITY_KEYS:
        if key in identity:
            out.append(f"{key}: {json.dumps(identity[key])}")
    answers.write_text("\n".join(out) + "\n")


def read_commit(project: Path) -> str | None:
    """The framework version tag recorded in .copier-answers.yml `_commit` (None if absent)."""
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return None
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("_commit")
    return str(value) if value is not None else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_source.py -k "identity or read_commit" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Then (separate calls — update the CLAUDE.md Current State pointer first):
```bash
git add src/framework_cli/source.py tests/test_source.py CLAUDE.md
```
```bash
git commit -m "feat(source): identity + commit readers/recorders for upgrade"
```

---

## Task 2: Extract `_apply_update` (pure refactor, no behavior change)

**Files:**
- Modify: `src/framework_cli/upskill.py:37-99` (`upskill_project`)
- Test: `tests/test_upskill.py` (existing tests must stay green)

- [ ] **Step 1: Run the existing upskill tests to capture the green baseline**

Run: `uv run pytest tests/test_upskill.py -v`
Expected: PASS (all existing tests). This is the refactor's safety net.

- [ ] **Step 2: Extract the helper, keep `upskill_project` behavior identical**

Replace the body of `upskill_project` in `src/framework_cli/upskill.py` so the `copier.run_update` + re-record + integrity + `task test` mechanics live in a new `_apply_update`, and `upskill_project` delegates to it. Keep the existing module-level `from copier import run_update` import (tests monkeypatch `up.run_update`).

```python
def _apply_update(
    project: Path,
    *,
    vcs_ref: str | None,
    batteries: list[str],
    channels: list[str],
) -> bool:
    """Re-render `project` at `vcs_ref` via Copier, preserving identity, then run `task test`.

    The single low-level update path shared by `framework upgrade` and `upskill --with`.
    Assumes preconditions (git-tracked, and for upgrade a clean tree) are already checked.
    """
    from framework_cli.migrations import migration_context
    from framework_cli.source import read_identity, record_identity

    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={
            "batteries": batteries,
            "alert_channels": channels,
            **migration_context(batteries),
        },
    )
    from framework_cli.source import record_alert_channels, record_batteries

    record_batteries(project, batteries)
    record_alert_channels(project, channels)
    if (project / ".framework" / "integrity.lock").is_file():
        write_manifest(project, installed_framework_version())
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
```

Then rewrite `upskill_project` to delegate (still passing its current `vcs_ref`, default `None` = latest — pinning comes in Task 4):

```python
def upskill_project(
    project: Path,
    vcs_ref: str | None = None,
    with_batteries: list[str] | None = None,
    alert_channels: list[str] | None = None,
) -> bool:
    """Add batteries / reconfigure channels for `project`, then run `task test`."""
    from framework_cli.source import read_alert_channels, read_batteries

    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    effective = (
        with_batteries if with_batteries is not None else read_batteries(project)
    )
    channels = (
        alert_channels if alert_channels is not None else read_alert_channels(project)
    )
    return _apply_update(
        project, vcs_ref=vcs_ref, batteries=effective, channels=channels
    )
```

> Note: `read_identity`/`record_identity` are imported in `_apply_update` but only *used* in Task 3 — to keep this step a pure refactor, leave the identity read/record/guard for Task 3. (If `ruff` flags the unused import now, move the `read_identity, record_identity` import line into Task 3 instead.)

- [ ] **Step 3: Run the existing upskill tests to verify still green**

Run: `uv run pytest tests/test_upskill.py -v`
Expected: PASS (unchanged) — behavior is identical; only structure moved.

- [ ] **Step 4: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
```bash
git add src/framework_cli/upskill.py CLAUDE.md
```
```bash
git commit -m "refactor(upskill): extract shared _apply_update helper"
```

---

## Task 3: Identity preservation + fail-closed guard in `_apply_update`

**Files:**
- Modify: `src/framework_cli/upskill.py` (`_apply_update`)
- Test: `tests/test_upskill.py`

- [ ] **Step 1: Write the failing tests (the headline two-hop invariant + the guard)**

Append to `tests/test_upskill.py`. These use a synthetic source template that has the four identity answers and a `src/{{package_name}}/` path.

```python
def _identity_source_repo(tmp_path: Path) -> Path:
    """Minimal git template with the four identity answers + a src/<package>/ path, tag v1."""
    repo = tmp_path / "isrc"
    sub = repo / "tmpl"
    pkg = sub / "src" / "{{ package_name }}"
    pkg.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\n"
        "project_name:\n  type: str\n"
        "project_slug:\n  type: str\n  default: \"{{ project_name|lower }}\"\n"
        "package_name:\n  type: str\n  default: \"{{ project_slug }}\"\n"
        "python_version:\n  type: str\n  default: \"3.12\"\n"
        "batteries:\n  type: yaml\n  default: []\n"
        "alert_channels:\n  type: yaml\n  default: [\"webhook\"]\n"
    )
    (pkg / "__init__.py.jinja").write_text("# {{ package_name }}\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml }}"
    )
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _identity_project(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    from framework_cli.source import record_identity

    proj = tmp_path / "iproj"
    run_copy(
        str(source),
        str(proj),
        data={"project_name": "demo"},
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
    ans = proj / ".copier-answers.yml"
    kept = [
        ln
        for ln in ans.read_text().splitlines()
        if not ln.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    # The git+_subdirectory source omits answers from _copier_answers; record identity as the
    # real `framework new` does via the local template (which includes them).
    record_identity(
        proj,
        {
            "project_name": "demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def _bump_identity_source(source: Path, tag: str) -> None:
    (source / "tmpl" / "framework_line.txt").write_text(f"framework {tag}\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", tag)
    _git(source, "tag", tag)


def test_identity_survives_two_sequential_updates(tmp_path: Path):
    """The headline invariant: identity + src/<package>/ survive a multi-hop update."""
    from framework_cli.source import read_identity

    source = _identity_source_repo(tmp_path)
    proj = _identity_project(tmp_path, source)
    from framework_cli.upskill import _apply_update

    _bump_identity_source(source, "v2")
    _apply_update(proj, vcs_ref="v2", batteries=[], channels=["webhook"])
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "to v2")

    _bump_identity_source(source, "v3")
    _apply_update(proj, vcs_ref="v3", batteries=[], channels=["webhook"])

    assert read_identity(proj) == {
        "project_name": "demo",
        "project_slug": "demo",
        "package_name": "demo",
        "python_version": "3.12",
    }
    assert (proj / "src" / "demo" / "__init__.py").is_file(), (
        "package dir lost — identity stripped across the second update"
    )


def test_apply_update_refuses_when_identity_missing(tmp_path: Path):
    from framework_cli.upskill import UpskillError, _apply_update

    source = _identity_source_repo(tmp_path)
    proj = _identity_project(tmp_path, source)
    # Strip identity from the recorded answers.
    ans = proj / ".copier-answers.yml"
    ans.write_text(
        "\n".join(
            ln
            for ln in ans.read_text().splitlines()
            if not ln.startswith(("project_name:", "project_slug:", "package_name:", "python_version:"))
        )
        + "\n"
    )
    with pytest.raises(UpskillError, match="identity"):
        _apply_update(proj, vcs_ref="v1", batteries=[], channels=["webhook"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upskill.py -k "two_sequential or identity_missing" -v`
Expected: FAIL — the two-hop test loses the package dir (identity stripped); the guard test does not raise.

- [ ] **Step 3: Add identity read, fail-closed guard, pass-through, and re-record to `_apply_update`**

In `src/framework_cli/upskill.py`, edit `_apply_update` so it reads identity first, refuses if any key is missing, passes identity into `run_update`'s `data`, and re-records it after. Replace the start of `_apply_update` (through the `run_update` call) and add the re-record:

```python
    from framework_cli.migrations import migration_context
    from framework_cli.source import IDENTITY_KEYS, read_identity, record_identity

    identity = read_identity(project)
    missing = [k for k in IDENTITY_KEYS if not identity.get(k)]
    if missing:
        raise UpskillError(
            f".copier-answers.yml is missing identity answers ({', '.join(missing)}); "
            "refusing to update rather than render an empty project. Restore them and retry."
        )

    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={
            **identity,
            "batteries": batteries,
            "alert_channels": channels,
            **migration_context(batteries),
        },
    )
    from framework_cli.source import record_alert_channels, record_batteries

    record_batteries(project, batteries)
    record_alert_channels(project, channels)
    record_identity(project, identity)
```

(Remove the now-duplicated `from framework_cli.source import read_identity, record_identity` line added in Task 2 if present.)

- [ ] **Step 4: Run to verify they pass (and the existing suite stays green)**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upskill.py -v`
Expected: PASS (two-hop invariant + guard now pass; pre-existing upskill tests unchanged).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
```bash
git add src/framework_cli/upskill.py tests/test_upskill.py CLAUDE.md
```
```bash
git commit -m "fix(upskill): preserve identity across copier update; fail-closed on missing"
```

---

## Task 4: Pin the battery path to the recorded version (decision A)

**Files:**
- Modify: `src/framework_cli/upskill.py` (`upskill_project`)
- Test: `tests/test_upskill.py`

- [ ] **Step 1: Write the failing test (battery add must NOT move the version)**

Append to `tests/test_upskill.py`:

```python
def test_upskill_with_pins_recorded_version(tmp_path: Path):
    """upskill --with adds a battery at the recorded version — it does not bump _commit."""
    from framework_cli.source import read_batteries

    source = _battery_source_repo(tmp_path)
    proj = _battery_project(tmp_path, source, [])
    assert "_commit: v1" in (proj / ".copier-answers.yml").read_text()

    _bump_source_to_v2(source)  # a newer release exists...
    assert upskill_project(proj, with_batteries=["websockets"]) is True

    text = (proj / ".copier-answers.yml").read_text()
    assert "_commit: v1" in text, "upskill --with moved the framework version (decision A violated)"
    assert "_commit: v2" not in text
    assert (proj / "ws.txt").is_file()
    assert read_batteries(proj) == ["websockets"]
```

> The `_battery_source_repo` / `_battery_project` / `_bump_source_to_v2` helpers already exist in this file (used by the existing battery tests). The battery template at v1 already gates `ws.txt` on `websockets`, so adding the battery at the *recorded* v1 still creates the file.

- [ ] **Step 2: Run to verify it fails**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upskill.py::test_upskill_with_pins_recorded_version -v`
Expected: FAIL — `_commit` becomes `v2` (today's `upskill_project` passes `vcs_ref=None` → latest).

- [ ] **Step 3: Resolve the recorded version inside `upskill_project` and pin to it**

In `src/framework_cli/upskill.py`, change `upskill_project` to resolve `vcs_ref` from the project's recorded `_commit` when the caller didn't pass one, so the battery path never moves the version:

```python
def upskill_project(
    project: Path,
    vcs_ref: str | None = None,
    with_batteries: list[str] | None = None,
    alert_channels: list[str] | None = None,
) -> bool:
    """Add batteries / reconfigure channels for `project` at its recorded version, then test."""
    from framework_cli.source import read_alert_channels, read_batteries, read_commit

    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    effective = (
        with_batteries if with_batteries is not None else read_batteries(project)
    )
    channels = (
        alert_channels if alert_channels is not None else read_alert_channels(project)
    )
    pinned = vcs_ref if vcs_ref is not None else read_commit(project)
    return _apply_update(
        project, vcs_ref=pinned, batteries=effective, channels=channels
    )
```

- [ ] **Step 4: Retarget the version-movement tests that no longer fit `upskill`**

`upskill_project` no longer moves the framework version, so two existing tests assert behavior that now belongs to `upgrade` (Task 5). **Delete** these two tests from `tests/test_upskill.py` (they are reborn against `upgrade_project` in `tests/test_upgrade.py`):
- `test_upskill_applies_framework_change_and_stays_green`
- `test_upskill_reports_not_green_when_tests_fail`

Keep `test_upskill_requires_git_tracked_project`, `test_upskill_preserves_recorded_batteries`, `test_upskill_with_adds_battery_and_records_it`, `test_upskill_regenerates_the_manifest`, and `test_upskill_records_alert_channels` — they exercise the (still valid) battery/channel path. (`test_upskill_records_alert_channels` monkeypatches `run_update`; it also needs identity present — add the four identity lines to its inline `.copier-answers.yml` so the new guard passes; see Step 5.)

- [ ] **Step 5: Make the monkeypatched channel test satisfy the identity guard**

In `test_upskill_records_alert_channels`, the inline answers file must now include identity (the guard reads it before `run_update`). Change its `write_text` to:

```python
    (project / ".copier-answers.yml").write_text(
        "_src_path: gh:x\n_commit: v0.1.0\n"
        "project_name: Demo\nproject_slug: demo\npackage_name: demo\npython_version: \"3.12\"\n"
        "batteries: []\nalert_channels:\n- webhook\n"
    )
```

Also assert identity travels into `run_update`'s data:
```python
    assert calls["data"]["package_name"] == "demo"
```

- [ ] **Step 6: Run the full upskill suite**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upskill.py -v`
Expected: PASS (battery/channel + identity tests; the two version-movement tests are gone).

- [ ] **Step 7: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
```bash
git add src/framework_cli/upskill.py tests/test_upskill.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): pin battery changes to the recorded version (decision A)"
```

---

## Task 5: `upgrade.py` — `upgrade_project` with clean-tree precondition + target resolution

**Files:**
- Create: `src/framework_cli/upgrade.py`
- Test: `tests/test_upgrade.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upgrade.py`. Reuse the identity-source pattern (copy the three helpers here so the file is self-contained; the engineer may read tasks out of order).

```python
import subprocess
from pathlib import Path

import pytest

from framework_cli.upgrade import UpgradeError, upgrade_project


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "isrc"
    sub = repo / "tmpl"
    pkg = sub / "src" / "{{ package_name }}"
    pkg.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\n"
        "project_name:\n  type: str\n"
        "project_slug:\n  type: str\n  default: \"{{ project_name|lower }}\"\n"
        "package_name:\n  type: str\n  default: \"{{ project_slug }}\"\n"
        "python_version:\n  type: str\n  default: \"3.12\"\n"
        "batteries:\n  type: yaml\n  default: []\n"
        "alert_channels:\n  type: yaml\n  default: [\"webhook\"]\n"
    )
    (pkg / "__init__.py.jinja").write_text("# {{ package_name }}\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml }}"
    )
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _project(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    from framework_cli.source import record_identity

    proj = tmp_path / "iproj"
    run_copy(
        str(source), str(proj), data={"project_name": "demo"},
        defaults=True, overwrite=True, quiet=True, vcs_ref="v1",
    )
    ans = proj / ".copier-answers.yml"
    kept = [
        ln for ln in ans.read_text().splitlines()
        if not ln.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    record_identity(proj, {
        "project_name": "demo", "project_slug": "demo",
        "package_name": "demo", "python_version": "3.12",
    })
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def _bump(source: Path, tag: str, *, green: bool = True) -> None:
    (source / "tmpl" / "framework_line.txt").write_text(f"framework {tag}\n")
    if not green:
        (source / "tmpl" / "Taskfile.yml").write_text(
            "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n"
        )
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", tag)
    _git(source, "tag", tag)


def test_upgrade_refuses_dirty_tree(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    (proj / "dirty.txt").write_text("uncommitted\n")  # dirty working tree
    with pytest.raises(UpgradeError, match="clean"):
        upgrade_project(proj, to="v2")
    assert (proj / "framework_line.txt").read_text() == "framework v1\n"  # untouched


def test_upgrade_no_op_when_already_at_target(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    outcome = upgrade_project(proj, to="v1")
    assert outcome.status == "already-current"
    assert outcome.target == "v1"


def test_upgrade_applies_target_and_reports_green(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    assert outcome.target == "v2"
    assert (proj / "framework_line.txt").read_text() == "framework v2\n"
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()
    assert (proj / "src" / "demo" / "__init__.py").is_file()  # identity preserved


def test_upgrade_reports_red_when_tests_fail(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2", green=False)
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "red"
    assert outcome.target == "v2"


def test_upgrade_requires_git_tracked(tmp_path: Path):
    from copier import run_copy

    source = _source_repo(tmp_path)
    proj = tmp_path / "bare"
    run_copy(
        str(source), str(proj), data={"project_name": "demo"},
        defaults=True, overwrite=True, quiet=True, vcs_ref="v1",
    )
    with pytest.raises(UpgradeError, match="git"):
        upgrade_project(proj, to="v1")
```

- [ ] **Step 2: Run to verify they fail**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upgrade.py -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.upgrade`.

- [ ] **Step 3: Implement `src/framework_cli/upgrade.py`**

```python
"""`framework upgrade`: move a generated project across framework versions.

The one path that bumps a project's recorded framework version. Re-renders the template at
the target release (default: latest) via the shared `_apply_update` core, preserving project
identity, then runs `task test`. Battery mutation lives in `upskill --with` / `downskill`.

Rollback is plain git: a clean working tree is required up front (so the upgrade is one
reviewable diff), and on success the caller is told to commit and push immediately.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from framework_cli.source import latest_release, read_commit
from framework_cli.upskill import UpskillError, _apply_update, _is_git_tracked


class UpgradeError(Exception):
    """Upgrade cannot proceed (not git-tracked, dirty tree, or no target release)."""


@dataclass
class UpgradeOutcome:
    status: str  # "already-current" | "green" | "red"
    target: str


def _is_clean_tree(project: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def upgrade_project(project: Path, *, to: str | None = None) -> UpgradeOutcome:
    """Upgrade `project` to `to` (default: latest release). Raises UpgradeError on refusal."""
    if not _is_git_tracked(project):
        raise UpgradeError(
            "upgrade requires a git-tracked project (run `git init` and commit first)"
        )
    if not _is_clean_tree(project):
        raise UpgradeError(
            "commit or stash your changes before upgrading — the upgrade needs a clean "
            "tree so its diff is reviewable and reversible."
        )
    target = to if to is not None else latest_release()
    if target is None:
        raise UpgradeError(
            "no framework release found (or the remote is unreachable); cannot upgrade."
        )
    if read_commit(project) == target:
        return UpgradeOutcome(status="already-current", target=target)

    from framework_cli.source import read_alert_channels, read_batteries

    try:
        green = _apply_update(
            project,
            vcs_ref=target,
            batteries=read_batteries(project),
            channels=read_alert_channels(project),
        )
    except UpskillError as exc:  # missing identity / `task` not found
        raise UpgradeError(str(exc)) from exc
    return UpgradeOutcome(status="green" if green else "red", target=target)
```

- [ ] **Step 4: Run to verify they pass**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_upgrade.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
```bash
git add src/framework_cli/upgrade.py tests/test_upgrade.py CLAUDE.md
```
```bash
git commit -m "feat(upgrade): upgrade_project with clean-tree precondition + target resolution"
```

---

## Task 6: CLI — `upgrade` command, bare-`upskill` block, `check` re-point

**Files:**
- Modify: `src/framework_cli/cli.py:264-316` (`upskill`), `:348-363` (`check`), add `upgrade`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Append to `tests/test_cli.py` (it already uses Typer's `CliRunner`; mirror the existing pattern in that file for `runner`/`app` import — typically `from typer.testing import CliRunner` and `from framework_cli.cli import app`).

```python
def test_bare_upskill_is_blocked_with_a_battery_message(tmp_path):
    from typer.testing import CliRunner

    from framework_cli.cli import app

    (tmp_path / ".copier-answers.yml").write_text("batteries: []\n")
    result = CliRunner().invoke(app, ["upskill", str(tmp_path)])
    assert result.exit_code != 0
    assert "at least one `--with`" in result.output
    assert "framework upgrade" in result.output


def test_upgrade_success_prints_commit_after_instruction_last(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.upgrade import UpgradeOutcome

    monkeypatch.setattr(
        cli, "upgrade_project", lambda project, to=None: UpgradeOutcome("green", "v0.3.0")
    )
    (tmp_path / "x").mkdir()
    result = CliRunner().invoke(app := cli.app, ["upgrade", str(tmp_path / "x")])
    assert result.exit_code == 0
    # The commit/push instruction is the final thing the user sees.
    tail = result.output.strip().splitlines()[-1]
    assert "git" in tail and "commit" in tail and "push" in tail


def test_upgrade_already_current_is_a_noop(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.upgrade import UpgradeOutcome

    monkeypatch.setattr(
        cli, "upgrade_project",
        lambda project, to=None: UpgradeOutcome("already-current", "v0.3.0"),
    )
    (tmp_path / "x").mkdir()
    result = CliRunner().invoke(cli.app, ["upgrade", str(tmp_path / "x")])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_check_points_at_upgrade(monkeypatch):
    from typer.testing import CliRunner

    import framework_cli.cli as cli

    monkeypatch.setattr(cli, "installed_framework_version", lambda: "0.2.0")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.3.0")
    result = CliRunner().invoke(cli.app, ["check"])
    assert "framework upgrade" in result.output
    assert "framework upskill" not in result.output
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "upskill_is_blocked or upgrade or check_points" -v`
Expected: FAIL — no `upgrade` command; bare upskill currently proceeds; `check` says `upskill`.

- [ ] **Step 3a: Block bare `upskill`**

In `src/framework_cli/cli.py`, at the top of the `upskill` command body (after the `project.is_dir()` check, before resolving batteries), add:

```python
    if not with_ and alerts is None:
        typer.echo(
            "framework upskill adds batteries — pass at least one `--with <battery>`. "
            "To move the framework version, use `framework upgrade <project>`.",
            err=True,
        )
        raise typer.Exit(1)
```

- [ ] **Step 3b: Add the `upgrade` command**

Add a new command (e.g. just after `upskill`/`downskill`). Import `upgrade_project` at the top of `cli.py` alongside the existing `from framework_cli.upskill import …` line: `from framework_cli.upgrade import UpgradeError, upgrade_project`.

```python
@app.command()
def upgrade(
    name: str = typer.Argument(..., help="Path to the project to upgrade."),
    to: str = typer.Option(
        None, "--to", help="Target release tag (default: the latest release)."
    ),
) -> None:
    """Move a project onto a newer framework release, then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)
    try:
        outcome = upgrade_project(project, to=to)
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
    # green: the commit-after instruction is deliberately the LAST thing printed.
    typer.echo(f"Upgraded to {outcome.target}; tests pass. Review the diff, then snapshot it:")
    typer.echo(
        f'  git add -A && git commit -m "chore: upgrade framework to {outcome.target}" && git push'
    )
```

- [ ] **Step 3c: Re-point `check`**

In the `check` command, change the trailing guidance from `framework upskill <project>` to `framework upgrade <project>`:

```python
        typer.echo(
            f"framework check: installed {current_tag}, latest {latest}. "
            f"Upgrade the CLI with `uv tool install git+{REPO_URL}@{latest}`, "
            f"then run `framework upgrade <project>`."
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "upskill_is_blocked or upgrade or check_points" -v`
Expected: PASS.

- [ ] **Step 5: Run the full CLI + upskill + upgrade + source suites**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_cli.py tests/test_upskill.py tests/test_upgrade.py tests/test_source.py -q`
Expected: PASS.

- [ ] **Step 6: Gate + commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(cli): framework upgrade command; block bare upskill; re-point check"
```

---

## Task 7: Docs — make `upgrading.md` the real reference

**Files:**
- Modify: `documentation/using/upgrading.md`

- [ ] **Step 1: Remove the "Planned" banner and rewrite for the shipped command**

Edit `documentation/using/upgrading.md`:
- Delete the `!!! warning "Planned — not yet available"` admonition block at the top.
- Replace the "Intended UX" framing with the actual flow: `framework upgrade <project> [--to <tag>]`; clean-tree precondition; re-render at the target; `task test`; resolve conflict markers if any; **commit & push immediately** for clean before/after snapshots.
- In "Rolling back", keep the git-history philosophy; add that `framework upgrade` *requires* a clean tree up front and prints the commit/push instruction on success, which is what makes the two-snapshot rollback reliable.
- Replace the "Today: check, then upskill" section: `framework check` now prints the `framework upgrade <project>` command; clarify that `framework upskill --with` / `downskill` are battery-only and pin the framework version, and that bare `framework upskill` is rejected (use `framework upgrade`).

Concretely, the new top of the page (replacing lines 1–4 and the UX section) reads:

```markdown
# Upgrading to a newer framework release

The framework itself evolves: new releases improve the template — CI workflows, Compose
files, observability config, review agents, and scaffolded code patterns. **Upgrading** pulls
an existing project *forward* onto a newer framework release, distinct from
[adding or removing batteries](batteries-add-remove.md) (which change a project's feature set
without changing the framework version).

## The command

```bash
framework check                 # is there a newer release? prints the upgrade command
framework upgrade my-app        # move my-app onto the latest release
framework upgrade my-app --to v0.3.0   # …or onto a specific release
```

`framework upgrade` requires a **clean git working tree** (commit or stash first) — that is
what makes the upgrade one reviewable, reversible diff. It re-renders the template at the
target release via Copier's three-way merge (your app code is preserved; conflicts become
standard inline markers), regenerates the integrity manifest, and runs `task test`. On
success it tells you to **commit and push immediately**, so you keep clean before/after
snapshots.
```

- [ ] **Step 2: Verify the docs build (strict) if the framework docs job is available**

Run: `uv run mkdocs build --strict` (from the repo root; the framework site uses `documentation/` as its docs dir).
Expected: build succeeds with no warnings about the edited page. (If `mkdocs` is not installed in this environment, skip — the docs CI job covers it.)

- [ ] **Step 3: Commit**

```bash
git add documentation/using/upgrading.md CLAUDE.md
```
```bash
git commit -m "docs(upgrading): document the shipped framework upgrade command"
```

---

## Task 8: Full-suite verification + branch wrap

**Files:** none (verification only)

- [ ] **Step 1: Run the full gate**

```bash
TMPDIR=/var/tmp uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (Note any pre-existing unrelated reds — e.g. the known anthropic-SDK httpx `_state` teardown failures on `api`-backend paths — and confirm they are identical on `master`, not introduced here.)

- [ ] **Step 2: Update the meta-plan status table + CLAUDE.md**

- In `docs/superpowers/plans/2026-05-20-meta-plan.md`, flip Plan 24's row/entry to reflect "implemented on `plan-24-framework-upgrade`" (keep ✅ for merge-time).
- Update the `CLAUDE.md` Current State pointer (datetime + what shipped).

```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
```
```bash
git commit -m "docs(plan-24): mark framework upgrade implemented; update state"
```

- [ ] **Step 3: Branch-end review + finish**

Run the final whole-branch review with **Opus** (per the review-model policy), then use the `superpowers:finishing-a-development-branch` skill to open the PR against `master` (required checks: `gate`, `build`, `render-complete`).

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Command surface (`upgrade`, `upskill --with` pin, bare-`upskill` block, `check` re-point) → Tasks 4, 6. ✓
- Shared `_apply_update` core + identity preservation + fail-closed guard → Tasks 2, 3. ✓
- Clean-tree precondition + no-op + target resolution (`--to`/latest, single jump) → Task 5. ✓
- Commit-after instruction as the last success output → Task 6 (Step 3b + test). ✓
- Rollback = plain git (no `--rollback`, no dry-run) → reflected by the clean-tree design; nothing built (correct). ✓
- `downskill` unchanged → no task touches it (correct per the spec fix). ✓
- Docs de-planned → Task 7. ✓
- Throwaway synthetic-tag repos, local-only, rmtree'd → tests use pytest `tmp_path` (auto-removed) + local `git init`/tag sources, no network remotes, no push executed. ✓ (Note: tests rely on pytest's `tmp_path` cleanup; that satisfies "no temp dirs/repos survive" without an explicit finalizer since each test gets a fresh `tmp_path`. If stale `/tmp/pytest-of-*` accumulation appears, the `TMPDIR=/var/tmp` prefix on heavy runs is the mitigation already specified.)

**Placeholder scan:** no TBD/TODO; every code step shows complete code. ✓

**Type/name consistency:** `_apply_update(project, *, vcs_ref, batteries, channels)`, `read_identity`/`record_identity`/`read_commit`, `IDENTITY_KEYS`, `UpgradeOutcome(status, target)`, `UpgradeError`, `upgrade_project(project, *, to=None)` — used consistently across Tasks 1–6. ✓

**Two-hop invariant** (the headline) is an explicit failing-first test in Task 3. ✓

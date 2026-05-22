# Portable Template Source + Upskill/Version (Plan 6b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the template source portable and git-tag-versioned so `framework upskill` (`copier update`) works across machines, ship `framework check`/`upskill`, and activate the 6a CI step-0 integrity job.

**Architecture:** A repo-root `copier.yml` (`_subdirectory: src/framework_cli/template` + an explicit `_exclude`) makes `git+<framework-repo>@<tag>` a valid Copier source while the subdir `copier.yml` stays the single source of truth for questions. `framework new` keeps its bundled local render, then rewrites the generated `.copier-answers.yml` to record the portable git source + version tag. `framework check` compares the installed version to the latest remote tag; `framework upskill` runs Copier's `run_update` on a git-tracked project then `task test`. Distribution is git tags only (`uv tool install git+<repo>@vX.Y.Z`).

**Tech Stack:** Python 3.12, Typer, Copier (`run_update`), `git ls-remote`, pytest. Design: `docs/superpowers/specs/2026-05-22-template-source-and-upskill-design.md`.

**Spike already done (findings baked into this plan, no longer open):**
- Root `copier.yml` with `_subdirectory` renders the subdir AND reads the subdir's `copier.yml` questions — no question duplication needed.
- Rendering from the repo root leaks the subdir's `copier.yml` into output **unless** the **root** `copier.yml` sets `_exclude` including `copier.yml` (the subdir's `_exclude` does NOT prevent it). `_exclude` replaces Copier's defaults, so the root list must re-include them.
- `copier update` requires the target project to be **git-tracked**; it advances `_commit` and applies framework changes, emitting **inline 3-way conflict markers** (`<<<<<<< before updating … >>>>>>> after updating`) where a builder edited a changed line (not `.rej` files).
- The bundled local-subdir render (`framework new`) is unaffected by the root `copier.yml` (the root file isn't in the installed package).

**Framework repo coordinates:** `gh:cdowell-swtr/swiftwater-framework` (Copier source form) / `https://github.com/cdowell-swtr/swiftwater-framework` (for `git ls-remote`).

---

## Scope

**In scope:** repo-root `copier.yml`; `framework new` records a portable `_src_path`+`_commit`; `framework check`; `framework upskill` (version-update only); CI step-0 activation; `RELEASING.md`. (This single plan covers what the design called 6b-1/6b-2/6b-3.)

**Out of scope:** PyPI publishing; `upskill --with <battery>` (Plan 8); GitHub release-automation workflow (Plan 9); cutting the first real tags (operational).

## Repo working agreement for EVERY commit in this plan

A `PreToolUse` hook **blocks `git commit` unless `CLAUDE.md` has a staged change.** For each "Commit" step: (1) bump the `CLAUDE.md` Current State → Last updated line (datetime + `PDT`); (2) `git add <changed files> CLAUDE.md` as ONE call; (3) `git commit` as a SEPARATE call. End the commit body with:
```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

> **Tests that build a git repo:** several tasks build a throwaway git repo in `tmp_path` and commit to it from Python (`subprocess`). That's fine — those commits are on temp repos, unrelated to this repo's commit hook (the hook only guards commits to the framework repo). Do NOT put the literal phrase `git` + space + `commit` in a *Bash tool command string* (the hook pattern-matches it); run such tests via `uv run pytest …` (the test does the git work internally).

## File Structure

**New (framework source):**
- `src/framework_cli/source.py` — template-source config + helpers: repo constants, `version_tag`, `record_portable_source`, `latest_release`.
- `src/framework_cli/upskill.py` — `upskill_project` (run_update + `task test`).

**Modified (framework source):**
- `src/framework_cli/cli.py` — `new` records the portable source; add `check` + `upskill` commands.

**New (repo root):**
- `copier.yml` — `_subdirectory` + `_exclude` (makes the repo a Copier source).
- `RELEASING.md` — the release procedure.

**Modified (template payload):**
- `src/framework_cli/template/.github/workflows/ci.yml.jinja` — activate the step-0 integrity job.

**New/extended tests:**
- `tests/test_source.py`, `tests/test_upskill.py` (new)
- `tests/test_cli.py` (extend: `new` records portable source; `check`/`upskill` commands)
- `tests/test_copier_runner.py` (extend: root copier.yml renders with no `copier.yml` leak)

---

### Task 1: Repo-root `copier.yml` makes the repo a Copier source

**Files:**
- Create: `copier.yml` (repo root)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test** — add to `tests/test_copier_runner.py`:

```python
def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "framework_cli").is_dir():
            return parent
    raise RuntimeError("repo root not found")


def test_root_copier_yml_renders_template_without_leaking_config(tmp_path: Path):
    import shutil
    import yaml
    from copier import run_copy

    root = _repo_root()
    # Root copier.yml must exist and point at the template subdir.
    cfg = yaml.safe_load((root / "copier.yml").read_text())
    assert cfg["_subdirectory"] == "src/framework_cli/template"

    # Render from a NON-git copy of {root copier.yml + the template subdir} so Copier uses the
    # working-tree files (not a committed git ref). The output must NOT contain copier.yml.
    src = tmp_path / "src"
    (src / "src" / "framework_cli").mkdir(parents=True)
    shutil.copy(root / "copier.yml", src / "copier.yml")
    shutil.copytree(
        root / "src" / "framework_cli" / "template",
        src / "src" / "framework_cli" / "template",
    )
    dest = tmp_path / "out"
    run_copy(
        str(src),
        str(dest),
        data={"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
        defaults=True,
        overwrite=True,
        quiet=True,
    )
    assert not (dest / "copier.yml").exists(), "subdir copier.yml leaked into the rendered project"
    assert (dest / "pyproject.toml").is_file()  # a known rendered file
    assert (dest / ".copier-answers.yml").is_file()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_root_copier_yml_renders_template_without_leaking_config -q`
Expected: FAIL — no root `copier.yml` (`FileNotFoundError`/KeyError).

- [ ] **Step 3: Implement** — Create `copier.yml` at the repo root:

```yaml
# Repo-root Copier config: makes git+<this repo>@<tag> a valid template source for
# `copier update` / `framework upskill`. The template files live in _subdirectory; the
# questions/settings are read from that subdir's own copier.yml. _exclude REPLACES Copier's
# defaults, so the subdir copier.yml is dropped from rendered projects (it would otherwise
# leak) — the rest of the list re-states Copier's defaults.
_subdirectory: src/framework_cli/template
_exclude:
  - "copier.yml"
  - "copier.yaml"
  - "~*"
  - "*.py[co]"
  - "__pycache__"
  - ".git"
  - ".DS_Store"
  - ".svn"
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS — the rendered project has `pyproject.toml` + `.copier-answers.yml` and **no** `copier.yml`. Existing render tests still pass (the bundled render path is unchanged; it points at the subdir directly).

- [ ] **Step 5: Commit**

```bash
git add copier.yml tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): repo-root copier.yml makes the repo a versioned Copier source"
```

---

### Task 2: `framework new` records a portable source

**Files:**
- Create: `src/framework_cli/source.py`
- Modify: `src/framework_cli/cli.py` (the `new` command)
- Test: `tests/test_source.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — Create `tests/test_source.py`:

```python
from pathlib import Path

from framework_cli.source import REPO_GH, record_portable_source, version_tag


def test_version_tag():
    assert version_tag("0.3.0") == "v0.3.0"


def test_record_portable_source_rewrites_answers(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    answers = project / ".copier-answers.yml"
    answers.write_text(
        "# managed\n_src_path: /abs/local/path\nproject_name: Demo\npackage_name: demo\n"
    )
    record_portable_source(project, "0.3.0")
    text = answers.read_text()
    assert f"_src_path: {REPO_GH}" in text
    assert "_commit: v0.3.0" in text
    assert "/abs/local/path" not in text  # the machine-specific path is gone
    assert "project_name: Demo" in text and "package_name: demo" in text  # answers preserved
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_source.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.source`.

- [ ] **Step 3: Implement** — Create `src/framework_cli/source.py`:

```python
"""Template-source coordinates and the portable-answers rewrite.

The bundled render records a machine-specific `_src_path`; we rewrite it to the portable
git source + version tag so `copier update` / `framework upskill` work from any machine.
"""

from __future__ import annotations

from pathlib import Path

# Copier source form (recorded in .copier-answers.yml _src_path).
REPO_GH = "gh:cdowell-swtr/swiftwater-framework"
# HTTPS form (for `git ls-remote` and `uv tool install git+...`).
REPO_URL = "https://github.com/cdowell-swtr/swiftwater-framework"

_ANSWERS_REL = ".copier-answers.yml"


def version_tag(version: str) -> str:
    """Map a package version to its git release tag."""
    return f"v{version}"


def record_portable_source(project: Path, version: str) -> None:
    """Rewrite the project's .copier-answers.yml to a portable git source + version tag.

    Drops any `_src_path`/`_commit` lines and re-adds them pointing at REPO_GH / vX.Y.Z;
    leaves all real answers untouched.
    """
    answers = project / _ANSWERS_REL
    kept = [
        line
        for line in answers.read_text().splitlines()
        if not line.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {REPO_GH}", f"_commit: {version_tag(version)}"]
    answers.write_text("\n".join(kept) + "\n")
```

In `src/framework_cli/cli.py`, add the import:

```python
from framework_cli.source import record_portable_source
```

In the `new` command, immediately AFTER the existing `write_manifest(dest, installed_framework_version())` line, add:

```python
    record_portable_source(dest, installed_framework_version())
```

(Order: render → write_manifest → record_portable_source → echo. `installed_framework_version()` is already imported in cli.py from Plan 6a.)

Add to `tests/test_cli.py`:

```python
def test_new_records_portable_source(tmp_path: Path, monkeypatch):
    from framework_cli.source import REPO_GH

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    answers = (tmp_path / "my-app" / ".copier-answers.yml").read_text()
    assert f"_src_path: {REPO_GH}" in answers
    assert "_commit: v" in answers
    assert "/src/framework_cli/template" not in answers  # no machine-specific local path
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_source.py tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean. (Note: `record_portable_source` must run AFTER `write_manifest`, because the manifest is generated from the rendered tree before the answers rewrite — the rewrite only touches `.copier-answers.yml`, which is not a manifest-tracked file, so order is safe either way, but keep it after for clarity.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/source.py src/framework_cli/cli.py tests/test_source.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): framework new records a portable git source + version tag"
```

---

### Task 3: `framework check` — is there a newer framework?

**Files:**
- Modify: `src/framework_cli/source.py` (add `latest_release`)
- Modify: `src/framework_cli/cli.py` (add `check` command)
- Test: `tests/test_source.py`, `tests/test_cli.py`

`latest_release` runs `git ls-remote --tags <url>` and returns the highest `vX.Y.Z` tag. Tested against a local git repo with tags (no network).

- [ ] **Step 1: Write the failing test** — Add to `tests/test_source.py`:

```python
import subprocess


def _tagged_repo(tmp_path: Path, tags: list[str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

    g("init", "-q")
    g("config", "user.email", "t@x")
    g("config", "user.name", "t")
    (repo / "f").write_text("x")
    g("add", "-A")
    g("commit", "-qm", "c")  # noqa
    for t in tags:
        g("tag", t)
    return repo


def test_latest_release_picks_highest_semver(tmp_path: Path):
    from framework_cli.source import latest_release

    repo = _tagged_repo(tmp_path, ["v0.1.0", "v0.2.0", "v0.10.0", "v0.2.1"])
    assert latest_release(str(repo)) == "v0.10.0"


def test_latest_release_none_when_no_tags(tmp_path: Path):
    from framework_cli.source import latest_release

    repo = _tagged_repo(tmp_path, [])
    assert latest_release(str(repo)) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_source.py -k latest_release -q`
Expected: FAIL — `latest_release` undefined.

- [ ] **Step 3: Implement** — In `src/framework_cli/source.py`, add the imports + function:

```python
import re
import subprocess

_TAG_RE = re.compile(r"refs/tags/(v\d+\.\d+\.\d+)$")


def latest_release(url: str = REPO_URL) -> str | None:
    """Highest vX.Y.Z tag in the remote, or None. `url` may be a local path (for tests)."""
    result = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    versions: list[tuple[int, int, int]] = []
    tags: dict[tuple[int, int, int], str] = {}
    for line in result.stdout.splitlines():
        m = _TAG_RE.search(line)
        if m:
            tag = m.group(1)
            parts = tuple(int(n) for n in tag[1:].split("."))
            key = (parts[0], parts[1], parts[2])
            versions.append(key)
            tags[key] = tag
    if not versions:
        return None
    return tags[max(versions)]
```

In `src/framework_cli/cli.py`, add the import + command:

```python
from framework_cli.source import latest_release
from framework_cli.integrity.manifest import installed_framework_version  # already imported
```

```python
@app.command()
def check() -> None:
    """Report whether a newer framework release is available."""
    current = installed_framework_version()
    latest = latest_release()
    if latest is None:
        typer.echo("framework check: no releases found (or the remote is unreachable).")
        raise typer.Exit(0)
    current_tag = f"v{current}"
    if latest == current_tag:
        typer.echo(f"framework check: up to date ({current_tag}).")
    else:
        typer.echo(
            f"framework check: installed {current_tag}, latest {latest}. "
            f"Upgrade the CLI with `uv tool install git+{__import__('framework_cli.source', fromlist=['REPO_URL']).REPO_URL}@{latest}`, "
            f"then run `framework upskill <project>`."
        )
```

> Implementer note: the inline `__import__` above is ugly — instead add `from framework_cli.source import REPO_URL` to the imports and use `REPO_URL` directly in the f-string. Use the clean import; do not ship the `__import__` form.

Add to `tests/test_cli.py`:

```python
def test_check_runs_and_reports(monkeypatch):
    # latest_release returns None when the default remote is unreachable in the test env;
    # the command must still exit 0 with a message (no crash).
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "framework check" in result.output
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_source.py tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean. (Replace the `__import__` hack with a clean `REPO_URL` import before running.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/source.py src/framework_cli/cli.py tests/test_source.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): framework check compares installed version to the latest tag"
```

---

### Task 4: `framework upskill` — copier update + task test

**Files:**
- Create: `src/framework_cli/upskill.py`
- Modify: `src/framework_cli/cli.py` (add `upskill` command)
- Test: `tests/test_upskill.py`, `tests/test_cli.py`

`upskill_project` requires a git-tracked project, runs Copier's `run_update` to the target ref, then runs `task test`; returns whether the project is green. The copier-update mechanics are tested with a local two-tag repo built from the **real** root `copier.yml` + template; the `task test` gating is tested with a trivial Taskfile.

- [ ] **Step 1: Write the failing test** — Create `tests/test_upskill.py`:

```python
import subprocess
from pathlib import Path

import pytest

from framework_cli.upskill import UpskillError, upskill_project


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _source_repo(tmp_path: Path) -> Path:
    """A minimal git template repo: root copier.yml (_subdirectory) + a tiny template, tag v1."""
    repo = tmp_path / "src"
    sub = repo / "tmpl"
    sub.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text("_templates_suffix: .jinja\nname:\n  type: str\n  default: world\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "app.txt.jinja").write_text("app for {{ name }}\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text("{{ _copier_answers|to_nice_yaml }}")
    # a Taskfile whose `test` task is trivially green (so upskill's task test passes)
    (sub / "Taskfile.yml").write_text("version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, *("commit -qm v1".split()))
    _git(repo, "tag", "v1")
    return repo


def _project_at_v1(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    proj = tmp_path / "proj"
    run_copy(str(source), str(proj), data={"name": "demo"}, defaults=True, overwrite=True, quiet=True, vcs_ref="v1")
    # record the portable source + ref (as `framework new` would) and git-init the project
    ans = proj / ".copier-answers.yml"
    kept = [l for l in ans.read_text().splitlines() if not l.startswith(("_src_path:", "_commit:"))]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, *("commit -qm scaffold".split()))
    return proj


def test_upskill_applies_framework_change_and_stays_green(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project_at_v1(tmp_path, source)

    # builder edits a builder-owned file (no overlap with framework changes)
    (proj / "app.txt").write_text("app for demo\nMY BUILDER LINE\n")
    _git(proj, "add", "-A")
    _git(proj, *("commit -qm edit".split()))

    # framework v2 changes a framework file
    sub = source / "tmpl"
    (sub / "framework_line.txt").write_text("framework v2 CHANGED\n")
    _git(source, "add", "-A")
    _git(source, *("commit -qm v2".split()))
    _git(source, "tag", "v2")

    green = upskill_project(proj)

    assert green is True
    assert (proj / "framework_line.txt").read_text() == "framework v2 CHANGED\n"  # framework change applied
    assert "MY BUILDER LINE" in (proj / "app.txt").read_text()  # builder content preserved
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()


def test_upskill_reports_not_green_when_tests_fail(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project_at_v1(tmp_path, source)
    # v2 makes the project's `task test` fail
    sub = source / "tmpl"
    (sub / "Taskfile.yml").write_text("version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n")
    _git(source, "add", "-A")
    _git(source, *("commit -qm v2".split()))
    _git(source, "tag", "v2")

    assert upskill_project(proj) is False


def test_upskill_requires_git_tracked_project(tmp_path: Path):
    source = _source_repo(tmp_path)
    from copier import run_copy

    proj = tmp_path / "bare"
    run_copy(str(source), str(proj), data={"name": "demo"}, defaults=True, overwrite=True, quiet=True, vcs_ref="v1")
    # not git-initialized
    with pytest.raises(UpskillError, match="git"):
        upskill_project(proj)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_upskill.py -q`
Expected: FAIL — `framework_cli.upskill` does not exist.

- [ ] **Step 3: Implement** — Create `src/framework_cli/upskill.py`:

```python
"""`framework upskill`: bring a project up to a newer framework version.

Runs Copier's update (3-way merge from the project's recorded version to the target),
then `task test`; reports whether the upgraded project is green. Conflicts are left as
inline markers for manual resolution (Copier's standard behavior).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from copier import run_update


class UpskillError(Exception):
    """Upskill cannot proceed (e.g., the project is not git-tracked)."""


def _is_git_tracked(project: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def upskill_project(project: Path, vcs_ref: str | None = None) -> bool:
    """Update `project` to `vcs_ref` (default: latest tag) and run `task test`.

    Returns True if the project is green afterward. Raises UpskillError if the project is
    not git-tracked (Copier's update requires it).
    """
    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        **({"vcs_ref": vcs_ref} if vcs_ref else {}),
    )
    test = subprocess.run(["task", "test"], cwd=project, check=False)
    return test.returncode == 0
```

In `src/framework_cli/cli.py`, add the import + command:

```python
from framework_cli.upskill import UpskillError, upskill_project
```

```python
@app.command()
def upskill(
    name: str = typer.Argument(..., help="Path to the project to upskill."),
) -> None:
    """Update a project to a newer framework version, then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)
    try:
        green = upskill_project(project)
    except UpskillError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if green:
        typer.echo(f"Upskilled {name}; tests pass.")
    else:
        typer.echo(
            f"Upskilled {name}, but `task test` failed — resolve any Copier conflict markers "
            "and fix failures before committing.",
            err=True,
        )
        raise typer.Exit(1)
```

Add to `tests/test_cli.py`:

```python
def test_upskill_command_rejects_non_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["upskill", "nope"])
    assert result.exit_code == 1
    assert "not a directory" in result.output
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_upskill.py tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (the two update-mechanics tests, the not-green test, the git-tracked guard, and the CLI directory guard); mypy + ruff clean. (`task` and `git` must be on PATH — they are in the framework dev env.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/upskill.py src/framework_cli/cli.py tests/test_upskill.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): framework upskill (copier update + task test)"
```

---

### Task 5: Activate CI step-0 (`framework integrity --ci`)

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`
- Test: `tests/test_copier_runner.py`

The generated CI integrity job (an echo placeholder since 6a) becomes real: install the framework pinned to the project's recorded `_commit`, then run `framework integrity --ci`.

- [ ] **Step 1: Write the failing test** — Add to `tests/test_copier_runner.py`:

```python
def test_ci_activates_integrity_step(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework integrity --ci" in ci
    assert "uv tool install" in ci and "_commit" in ci  # installs the recorded framework version
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_ci_activates_integrity_step -q`
Expected: FAIL — the integrity job is still the echo placeholder.

- [ ] **Step 3: Implement** — In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, replace the step-0 `integrity` job (the comment block + `integrity:` job with its echo) with:

```yaml
  # Step 0: framework integrity — verify the framework scaffolding is intact before anything
  # else. Installs the framework CLI pinned to the version this project was generated from
  # (recorded in .copier-answers.yml `_commit`), then runs the check.
  integrity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: install the framework CLI at the recorded version
        run: |
          ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"
          uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"
      - name: framework integrity --ci
        run: framework integrity --ci
```

(Leave the other jobs' `needs: integrity` unchanged.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS. Then validate the workflow lints: `uv run pytest tests/acceptance/test_rendered_project.py -k precommit -q` (the generated project's pre-commit includes actionlint over the workflow) — or if that test is Docker-gated/slow, at minimum ensure the YAML is well-formed by rendering + `yaml.safe_load` in the test above.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(upskill): activate CI step-0 framework integrity --ci"
```

---

### Task 6: `RELEASING.md`

**Files:**
- Create: `RELEASING.md` (repo root)
- Test: none (documentation) — verified by review.

- [ ] **Step 1: Create `RELEASING.md`**

```markdown
# Releasing the framework

A release is a git tag `vX.Y.Z` on this repo, equal to the `framework-cli` version in
`pyproject.toml`. Generated projects record `_commit: vX.Y.Z` in `.copier-answers.yml`, and
`framework upskill` / `framework check` / CI step-0 all resolve that tag — so the tag MUST exist
and MUST point at the commit whose bundled template you shipped.

## Procedure

1. Ensure `master` is green (`uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`).
2. Bump `version` in `pyproject.toml` to `X.Y.Z` (semver). Update `CLAUDE.md` + the meta-plan.
3. Commit. **Tag the same commit:** `git tag vX.Y.Z && git push origin master vX.Y.Z`.
4. The invariant holds by construction: CLI `X.Y.Z`'s bundled template == the template at `vX.Y.Z`,
   because they are the same commit. Do not move a tag after release.

## Install / upgrade

- Install: `uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@vX.Y.Z`
- Check for newer: `framework check`
- Upgrade a project: bump the installed CLI, then `framework upskill <project>` (the project must
  be a clean git working tree; Copier leaves inline conflict markers where a builder edited a
  changed framework line).
```

- [ ] **Step 2: Commit**

```bash
git add RELEASING.md CLAUDE.md
```
```bash
git commit -m "docs: framework release procedure (tag == version == bundled template)"
```

---

## Self-Review

**1. Spec coverage (`docs/superpowers/specs/2026-05-22-template-source-and-upskill-design.md`):**
- §3 versioned source → Task 1 (root `copier.yml` + `_subdirectory` + `_exclude`); the spike that §3 demanded is resolved (findings in the header) and encoded as Task 1's leak test.
- §4 `new` records portable source → Task 2 (`record_portable_source`, wired into `new`).
- §5 `check` + `upskill` → Tasks 3 (`latest_release` + `check`) and 4 (`upskill_project` + command; git-tracked precondition; `task test` gating; conflict-marker behavior).
- §6 CI activation → Task 5.
- §7 testing → the local-tagged-repo fixtures in Tasks 3/4 (no published tags/network), the render-leak test (Task 1), `new`-records assertion (Task 2), CI render-assert (Task 5).
- §8 release discipline → Task 6 (`RELEASING.md`).

**2. Placeholder scan:** none — every code step is complete. The one cosmetic wart (the `__import__` in Task 3's first draft) is explicitly flagged with the clean replacement to use; no task ships it.

**3. Type consistency:** `record_portable_source(project: Path, version: str)`, `version_tag(version) -> str`, `latest_release(url=REPO_URL) -> str | None`, `upskill_project(project: Path, vcs_ref=None) -> bool`, `UpskillError`, `REPO_GH`/`REPO_URL` are referenced identically across tasks and tests. `new` calls `record_portable_source` after `write_manifest`. CLI commands `check`/`upskill` match their lib functions.

**Plan-time spike status:** resolved before writing (header) — root `copier.yml` needs `_exclude`; `copier update` needs a git-tracked project; questions stay in the subdir. No task depends on an unresolved unknown.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-template-source-and-upskill.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.

**2. Inline Execution** — execute here with checkpoints.

Which approach?

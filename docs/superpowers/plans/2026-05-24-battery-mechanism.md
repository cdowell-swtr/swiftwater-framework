# Battery Mechanism — Additive (Plan 8a-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the additive battery mechanism — `framework new --with <battery>` / `upskill --with <battery>`, a battery registry, conditional rendering, router-autodiscovery, and a recorded battery set — proven with a `websockets` vehicle battery.

**Architecture:** A CLI-side `batteries.py` registry resolves `--with` selections (validation + dependency closure) into a `batteries` list passed as a Copier answer. The base app gains a router-autodiscovery convention so route-adding batteries are pure file-adds. `batteries` is a declared `type: yaml` Copier question, so it's recorded in `.copier-answers.yml` and reliably reused by `run_update` (upskill). Conditional rendering uses spike-proven templated paths gated on `{% if "<b>" in batteries %}`.

**Tech Stack:** Python 3.12, Typer, Copier (`run_copy`/`run_update`), FastAPI (WebSockets + APIRouter), `pkgutil`/`importlib`, PyYAML, pytest + `typer.testing.CliRunner`.

**Source spec:** `docs/superpowers/specs/2026-05-24-battery-mechanism-design.md`

> **Refinement vs. the spec (§6):** the spec said the framework would own the `batteries` record by extending `record_portable_source`. This plan instead declares `batteries` as a **`type: yaml`** Copier question — Copier records it cleanly and, crucially, **reuses it on `run_update`** so a plain `framework upskill` doesn't drop battery files. `record_portable_source`'s existing line-filter preserves the `batteries:` block untouched, so it needs no change. This is strictly more robust for the upskill path.

---

## Standing rules for every task

- **TDD:** failing test → red → minimum code → green → commit.
- **Commit-gate hook:** a `PreToolUse` hook blocks `git commit` unless a **staged change to `CLAUDE.md`** is present. In each commit step, bump the `**Last updated:**` line near the top of `CLAUDE.md` (datetime + `PDT` + a one-clause note) and `git add CLAUDE.md` with the task files. An unmodified `CLAUDE.md` does not satisfy it.
- **`git add` and `git commit` are SEPARATE Bash calls** (the hook reads the staged index before the commit runs). Avoid the literal word "commit" in Bash `description` fields for read-only git inspection.
- Run only targeted tests during a task. Do **not** run the full Docker acceptance suite mid-task except where a task explicitly is the acceptance task (Task 6); clear `/tmp/pytest-of-chris/*` first if you do.
- Per-task gate before commit: `uv run pytest -q <touched tests>`, `uv run ruff check .`, `uv run mypy src`.
- **`src/framework_cli/template/` is template payload** — not linted/typed as framework source; validated by rendering + the acceptance suite.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/framework_cli/batteries.py` (create) | Battery registry: `BatterySpec`, `_BATTERIES` (websockets), `battery_names`, `get_battery`, `resolve` (validate + dependency closure). | 1 |
| `src/framework_cli/template/src/{{package_name}}/routes/__init__.py` (modify) | `include_routers(app)` autodiscovery over the `routes/` package. | 2 |
| `src/framework_cli/template/src/{{package_name}}/main.py.jinja` (modify) | Use `include_routers(app)` instead of explicit `include_router` calls. | 2 |
| `src/framework_cli/template/copier.yml` (modify) | Declare `batteries: {type: yaml, default: []}`. | 3 |
| `src/framework_cli/copier_runner.py` (modify) | Widen `render_project` `data` type to carry the `batteries` list. | 3 |
| `src/framework_cli/template/.../routes/{{ 'websockets.py' if ... }}.jinja` etc. (create) | The websockets battery: conditional route + connection-manager package + a generated test. | 3 |
| `src/framework_cli/cli.py` (modify) | `new --with` (resolve + pass `batteries`); `upskill --with`. | 4, 5 |
| `src/framework_cli/source.py` (modify) | `read_batteries(project)` — parse the recorded set for upskill union. | 5 |
| `src/framework_cli/upskill.py` (modify) | `upskill_project(..., with_batteries=None)` passes `data={"batteries": …}` to `run_update`. | 5 |
| `tests/test_batteries.py` (create) | Registry unit tests. | 1 |
| `tests/test_copier_runner.py` (modify) | Autodiscovery + conditional-render tests. | 2, 3 |
| `tests/test_cli.py` (modify) | `new --with` + `upskill --with` tests. | 4, 5 |
| `tests/acceptance/test_rendered_project.py` (modify) | With-websockets rendered variant (Docker). | 6 |

---

## Task 1: Battery registry (`batteries.py`)

**Files:** Create `src/framework_cli/batteries.py`; Test `tests/test_batteries.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_batteries.py`:

```python
import pytest


def test_websockets_is_registered():
    from framework_cli.batteries import battery_names, get_battery

    assert "websockets" in battery_names()
    spec = get_battery("websockets")
    assert spec.name == "websockets" and spec.requires == () and spec.gates_agent is None


def test_resolve_unknown_battery_errors():
    from framework_cli.batteries import resolve

    with pytest.raises(ValueError, match="bogus"):
        resolve(["bogus"])


def test_resolve_returns_sorted_unique():
    from framework_cli.batteries import resolve

    assert resolve(["websockets", "websockets"]) == ["websockets"]


def test_resolve_includes_dependency_closure():
    # Use a synthetic spec to prove the closure walks `requires` (no real multi-battery yet).
    from framework_cli import batteries

    batteries._BATTERIES["_child"] = batteries.BatterySpec("_child", "x", requires=("websockets",))
    try:
        assert batteries.resolve(["_child"]) == ["_child", "websockets"]
    finally:
        del batteries._BATTERIES["_child"]
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_batteries.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.batteries`.

- [ ] **Step 3: Implement `batteries.py`**

Create `src/framework_cli/batteries.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BatterySpec:
    name: str                       # token used in templates + `--with`
    summary: str                    # one line, for --help / error messages
    requires: tuple[str, ...] = ()  # batteries this one implies (e.g. pgvector -> postgres, later)
    gates_agent: str | None = None  # review agent activated when present (wired by 8d/8g)


_BATTERIES: dict[str, BatterySpec] = {
    "websockets": BatterySpec(
        "websockets", "FastAPI WebSocket routes + a connection manager"
    ),
}


def battery_names() -> list[str]:
    return sorted(_BATTERIES)


def get_battery(name: str) -> BatterySpec:
    if name not in _BATTERIES:
        raise KeyError(f"unknown battery: {name}")
    return _BATTERIES[name]


def resolve(selected: Iterable[str]) -> list[str]:
    """Validate the selection and return its dependency-closed set (sorted, unique).

    Unknown names raise ValueError naming the offender.
    """
    seen: set[str] = set()
    stack = list(selected)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        if name not in _BATTERIES:
            raise ValueError(f"unknown battery: {name!r} (known: {', '.join(battery_names())})")
        seen.add(name)
        stack.extend(_BATTERIES[name].requires)
    return sorted(seen)
```

- [ ] **Step 4: Run green**

Run: `uv run pytest tests/test_batteries.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md **Last updated:** — "8a-1 Task 1: battery registry"
git add src/framework_cli/batteries.py tests/test_batteries.py CLAUDE.md
```
```bash
git commit -m "feat(batteries): battery registry with resolve() dependency closure

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Router autodiscovery (base-app change)

**Files:** Modify `src/framework_cli/template/src/{{package_name}}/routes/__init__.py` and `.../main.py.jinja`; Test `tests/test_copier_runner.py`.

> This changes the **always-on** base app every project gets. The guard is that the rendered app must still wire `health` + `items` (the existing acceptance suite exercises `/health` and `/items`).

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py` (module already imports `yaml`, `Path`, `render_project`, and defines `DATA`):

```python
def test_render_routes_use_autodiscovery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    init = (dest / "src" / "demo" / "routes" / "__init__.py").read_text()
    assert "include_routers" in init and "iter_modules" in init
    main = (dest / "src" / "demo" / "main.py").read_text()
    # main wires routers via the convention, not per-router include_router calls
    assert "include_routers(app)" in main
    assert "include_router(health.router)" not in main
    assert "include_router(items.router)" not in main
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_copier_runner.py -k autodiscovery -q`
Expected: FAIL (current `__init__.py` is empty; `main.py` uses explicit includes).

- [ ] **Step 3: Implement `include_routers`**

Replace the contents of `src/framework_cli/template/src/{{package_name}}/routes/__init__.py` (currently empty; keep it a plain `.py` — no interpolation needed) with:

```python
"""Route autodiscovery.

`include_routers(app)` includes every APIRouter exposed as `router` by a module in this
package, in a deterministic (sorted) order. A route-adding battery drops a
`routes/<name>.py` exposing `router` and it is wired automatically — no edit to main.py.
"""

import importlib
import pkgutil

from fastapi import APIRouter, FastAPI


def include_routers(app: FastAPI) -> None:
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
```

- [ ] **Step 4: Switch `main.py.jinja` to the convention**

In `src/framework_cli/template/src/{{package_name}}/main.py.jinja`:
- Replace the import line `from {{ package_name }}.routes import health, items` with `from {{ package_name }}.routes import include_routers`.
- Replace the two lines
  ```
      app.include_router(health.router)
      app.include_router(items.router)
  ```
  with
  ```
      include_routers(app)
  ```

- [ ] **Step 5: Run green + confirm the existing render suite still passes**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS (the new test + all existing render tests — the rendered app still has `health`/`items` routers, now via discovery).

- [ ] **Step 6: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md — "8a-1 Task 2: router autodiscovery"
git add "src/framework_cli/template/src/{{package_name}}/routes/__init__.py" "src/framework_cli/template/src/{{package_name}}/main.py.jinja" tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(template): route autodiscovery so route batteries are additive

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: The `batteries` answer + the websockets battery (conditional render)

**Files:** Modify `src/framework_cli/template/copier.yml`, `src/framework_cli/copier_runner.py`; Create the websockets battery files; Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_without_battery_has_no_websockets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # DATA has no "batteries" -> defaults to []
    assert not (dest / "src" / "demo" / "routes" / "websockets.py").exists()
    assert not (dest / "src" / "demo" / "websockets").exists()


def test_render_with_websockets_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    assert (dest / "src" / "demo" / "routes" / "websockets.py").is_file()
    assert (dest / "src" / "demo" / "websockets" / "connection_manager.py").is_file()
    assert (dest / "tests" / "test_websockets.py").is_file()
    # the WS route exposes `router` so autodiscovery wires it
    assert "router" in (dest / "src" / "demo" / "routes" / "websockets.py").read_text()
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_copier_runner.py -k websockets -q`
Expected: FAIL — `render_project` rejects the `batteries` key / the files don't exist.

- [ ] **Step 3: Declare the `batteries` answer + widen `render_project`**

In `src/framework_cli/template/copier.yml`, append:

```yaml
batteries:
  type: yaml
  help: Active batteries (set via `framework new --with`); not prompted.
  default: []
```

In `src/framework_cli/copier_runner.py`, widen the `data` type so a list value type-checks:

```python
def render_project(dest: Path, data: dict[str, object]) -> None:
```

(The body is unchanged — `run_copy(..., data=data, ...)` already forwards it.)

- [ ] **Step 4: Create the websockets battery files**

Create `src/framework_cli/template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/__init__.py` (empty file).

Create `src/framework_cli/template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/connection_manager.py` (plain `.py`, no interpolation):

```python
"""Minimal WebSocket connection registry."""

from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._active:
            self._active.remove(ws)

    async def broadcast(self, message: str) -> None:
        for ws in list(self._active):
            await ws.send_text(message)
```

Create the conditional route file `src/framework_cli/template/src/{{package_name}}/routes/{{ 'websockets.py' if 'websockets' in batteries else '' }}.jinja`:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from {{ package_name }}.websockets.connection_manager import ConnectionManager

router = APIRouter()
_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Echo + broadcast: each received message is broadcast to all connections."""
    await _manager.connect(ws)
    try:
        while True:
            message = await ws.receive_text()
            await _manager.broadcast(message)
    except WebSocketDisconnect:
        _manager.disconnect(ws)
```

Create the conditional generated test `src/framework_cli/template/tests/{{ 'test_websockets.py' if 'websockets' in batteries else '' }}.jinja`:

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app


def test_websocket_echo_broadcast() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_text("hello")
        assert ws.receive_text() == "hello"
```

> Idiom note (spike-validated): a templated filename that renders to an empty string is skipped by Copier — so `{{ 'websockets.py' if 'websockets' in batteries else '' }}.jinja` becomes `routes/websockets.py` when the battery is present and is skipped otherwise; the `{% if … %}websockets{% endif %}` directory is included/skipped likewise.

- [ ] **Step 5: Run green + the full render suite**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS (with/without-battery tests + all existing render tests; the no-battery default render is unchanged).

- [ ] **Step 6: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md — "8a-1 Task 3: batteries answer + websockets battery"
git add src/framework_cli/template/copier.yml src/framework_cli/copier_runner.py "src/framework_cli/template/src/{{package_name}}/routes" "src/framework_cli/template/src/{{package_name}}" "src/framework_cli/template/tests" tests/test_copier_runner.py CLAUDE.md
```
(If `git add` of the brace-dir globs is awkward, `git add -A src/framework_cli/template` then `git add` the framework files + CLAUDE.md.)
```bash
git commit -m "feat(template): websockets battery + conditional rendering via batteries answer

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: `framework new --with`

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (`runner`, `app` already imported):

```python
def test_new_with_websockets_battery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App", "--with", "websockets"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py").is_file()


def test_new_without_battery_has_no_websockets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    assert not (tmp_path / "my-app" / "src" / "my_app" / "routes" / "websockets.py").exists()


def test_new_rejects_unknown_battery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App", "--with", "bogus"])
    assert result.exit_code == 1
    assert "unknown battery" in result.output
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_cli.py -k "with_websockets or unknown_battery or without_battery" -q`
Expected: FAIL — `new` has no `--with` option.

- [ ] **Step 3: Wire `--with` into `new`**

In `src/framework_cli/cli.py`, add the import near the top:

```python
from framework_cli.batteries import resolve as resolve_batteries
```

Change the `new` command signature + body to accept `--with` and pass the resolved set:

```python
@app.command()
def new(
    name: str = typer.Argument(..., help="Human-readable project name"),
    python_version: str = typer.Option("3.12", help="Python version to target"),
    with_: list[str] = typer.Option(
        [], "--with", help="Activate a battery (repeatable), e.g. --with websockets."
    ),
) -> None:
    """Scaffold a new project from the framework template."""
    names = derive_names(name)
    dest = Path.cwd() / names.project_slug

    if dest.exists():
        typer.echo(f"Error: {dest} already exists", err=True)
        raise typer.Exit(code=1)

    try:
        batteries = resolve_batteries(with_)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "package_name": names.package_name,
            "python_version": python_version,
            "batteries": batteries,
        },
    )
    write_manifest(dest, installed_framework_version())
    record_portable_source(dest, installed_framework_version())
    msg = f"Created '{names.project_slug}' at {dest}"
    if batteries:
        msg += f" (batteries: {', '.join(batteries)})"
    typer.echo(msg)
```

- [ ] **Step 4: Run green + confirm no `new` regressions**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS (new battery tests + the existing `test_new_*` tests, which still render with no batteries).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md — "8a-1 Task 4: framework new --with"
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(cli): framework new --with <battery> selection

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: `framework upskill --with` (+ recorded-set readback)

**Files:** Modify `src/framework_cli/source.py`, `src/framework_cli/upskill.py`, `src/framework_cli/cli.py`; Test `tests/test_cli.py`, `tests/test_source.py`.

- [ ] **Step 1: Write the failing test for the recorded set + union**

Add to `tests/test_cli.py`:

```python
def test_new_records_batteries_in_answers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "websockets"]).exit_code == 0
    from framework_cli.source import read_batteries

    assert read_batteries(tmp_path / "my-app") == ["websockets"]


def test_read_batteries_empty_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    from framework_cli.source import read_batteries

    assert read_batteries(tmp_path / "my-app") == []
```

- [ ] **Step 2: Run red**

Run: `uv run pytest tests/test_cli.py -k "records_batteries or read_batteries" -q`
Expected: FAIL — `read_batteries` doesn't exist (and confirm `new --with` actually wrote `batteries:` to `.copier-answers.yml`; Copier records the declared `type: yaml` answer).

- [ ] **Step 3: Add `read_batteries` to `source.py`**

In `src/framework_cli/source.py`, add:

```python
def read_batteries(project: Path) -> list[str]:
    """The battery set recorded in the project's .copier-answers.yml ([] if none)."""
    import yaml

    answers = project / _ANSWERS_REL
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("batteries", [])
    return [str(b) for b in value] if isinstance(value, list) else []
```

- [ ] **Step 4: Run the readback tests green**

Run: `uv run pytest tests/test_cli.py -k "records_batteries or read_batteries" -q`
Expected: PASS. (If `batteries:` is NOT in the answers file, Copier didn't record the `type: yaml` answer — STOP and report; the fallback is to have `record_portable_source` write it, per the spec's original §6.)

- [ ] **Step 5: Write the failing `upskill --with` test**

Add to `tests/test_cli.py`. This monkeypatches the update seam so no real Copier update/network runs — it asserts the unioned battery set is what gets passed through:

```python
def test_upskill_with_unions_batteries(tmp_path, monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "websockets"]).exit_code == 0
    project = tmp_path / "my-app"

    captured = {}

    def fake_upskill(proj, vcs_ref=None, with_batteries=None):
        captured["with_batteries"] = with_batteries
        return True

    monkeypatch.setattr(cli_mod, "upskill_project", fake_upskill)
    # add a second battery; the union of recorded {websockets} + resolve({websockets}) is stable,
    # so use the synthetic registry entry to prove union (register, invoke, cleanup)
    from framework_cli import batteries as bat

    bat._BATTERIES["_x"] = bat.BatterySpec("_x", "x")
    try:
        result = runner.invoke(app, ["upskill", str(project), "--with", "_x"])
    finally:
        del bat._BATTERIES["_x"]
    assert result.exit_code == 0, result.output
    assert captured["with_batteries"] == ["_x", "websockets"]  # union, sorted
```

- [ ] **Step 6: Run red**

Run: `uv run pytest tests/test_cli.py -k upskill_with_unions -q`
Expected: FAIL — `upskill` has no `--with`.

- [ ] **Step 7: Add `with_batteries` to `upskill_project`**

In `src/framework_cli/upskill.py`, change `upskill_project` to pass battery data to the update:

```python
def upskill_project(
    project: Path, vcs_ref: str | None = None, with_batteries: list[str] | None = None
) -> bool:
    """Update `project` to `vcs_ref` (default: latest tag) and run `task test`.

    When `with_batteries` is given, that battery set is passed as the update's `batteries`
    answer (used by `upskill --with` to add batteries); otherwise the recorded answers — including
    the existing `batteries` — are reused as-is.
    """
    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    data = {"batteries": with_batteries} if with_batteries is not None else None
    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data=data,
    )
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
```

(Copier's `run_update` accepts `data=None`; passing `None` is equivalent to today's call.)

- [ ] **Step 8: Add `--with` to the `upskill` command**

In `src/framework_cli/cli.py`, update the `upskill` command to read the recorded set, union with the resolved `--with`, and pass it through:

```python
@app.command()
def upskill(
    name: str = typer.Argument(..., help="Path to the project to upskill."),
    with_: list[str] = typer.Option(
        [], "--with", help="Add a battery to the project (repeatable)."
    ),
) -> None:
    """Update a project to a newer framework version, then run its tests."""
    from framework_cli.source import read_batteries

    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)

    with_batteries = None
    if with_:
        try:
            with_batteries = resolve_batteries([*read_batteries(project), *with_])
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        green = upskill_project(project, with_batteries=with_batteries)
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

- [ ] **Step 9: Run green + the full CLI/source suites**

Run: `uv run pytest tests/test_cli.py tests/test_source.py tests/test_upskill.py -q`
Expected: PASS (new tests + existing upskill tests — the no-`--with` path passes `with_batteries=None`, identical to today).

- [ ] **Step 10: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md — "8a-1 Task 5: framework upskill --with + read_batteries"
git add src/framework_cli/source.py src/framework_cli/upskill.py src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(cli): framework upskill --with adds a battery to an existing project

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: With-websockets acceptance variant (Docker)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

> The acceptance suite renders a project and runs its own tooling. This adds a variant rendered **with** the websockets battery, proving the generated project (battery files + autodiscovered WS route + the generated WS test) lints, type-checks, and passes its suite. Mirror the existing skipif/`uv`-gating in that file.

- [ ] **Step 1: Read the existing acceptance helpers**

Read `tests/acceptance/test_rendered_project.py` to reuse its render helper, the `_docker_available`/`uv`-present skipif markers, and how it invokes the rendered project's tooling (e.g. `uv run pytest` / `task` in the rendered dir).

- [ ] **Step 2: Write the failing variant test**

Add a test that renders with `{**DATA, "batteries": ["websockets"]}` (or the file's render helper plus the batteries answer), then runs the rendered project's unit tests, asserting green and that `tests/test_websockets.py` is collected. Follow the file's existing pattern exactly (same skipif marker, same invocation), e.g.:

```python
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_with_websockets_battery_is_green(tmp_path: Path):
    dest = tmp_path / "demo-ws"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    assert (dest / "src" / "demo" / "routes" / "websockets.py").is_file()
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/test_websockets.py", "-q"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

(Adjust `DATA`/`render_project`/`demo` names to match the file's actual fixtures and the rendered package dir. If the rendered project needs `uv sync` first, mirror how the sibling acceptance tests prepare the project.)

- [ ] **Step 3: Run it (Docker/uv present)**

Clear tmp first if needed: `rm -rf /tmp/pytest-of-chris/*`.
Run: `uv run pytest tests/acceptance/test_rendered_project.py -k websockets -q`
Expected: PASS — the with-websockets project renders and its WS test passes (the route is autodiscovered; FastAPI's `TestClient` drives the WebSocket).

- [ ] **Step 4: Quality gate + commit**

```bash
uv run ruff check .
uv run mypy src
# bump CLAUDE.md — "8a-1 Task 6: with-websockets acceptance variant"
git add tests/acceptance/test_rendered_project.py CLAUDE.md
```
```bash
git commit -m "test(acceptance): rendered project with the websockets battery is green

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final whole-branch review (controller, after all tasks)

- [ ] `uv run pytest -q` — full suite incl. the Docker acceptance suite (both the default and with-websockets variants), all green. Clear `/tmp/pytest-of-chris/*` first.
- [ ] `uv run ruff check .`, `uv run mypy src`, `uv lock --check` — clean (no new runtime deps).
- [ ] Render both variants and confirm a freshly generated project makes a clean first `pre-commit` pass (the acceptance suite's `test_rendered_project_precommit_runs_clean` covers the default; spot-check the websockets variant).
- [ ] **Verify the upskill round-trip for real** (the riskiest mechanic): in a temp git-tracked project generated at a tag, run `framework upskill --with websockets` and confirm the WS files appear and the recorded `batteries` updates; and that a plain `framework upskill` (no `--with`) on a battery-bearing project **preserves** the battery files (the `type: yaml` answer is reused by `run_update`). If a real tag isn't available locally, exercise `upskill_project(..., with_batteries=[...])` against a local-path source as the existing upskill tests do, and note that the tag round-trip is validated by the first real release.
- [ ] `framework new --help` shows `--with`; `framework new "X" --with websockets` produces a working app.

Then **superpowers:finishing-a-development-branch**: finalize the CLAUDE.md narrative + the meta-plan 8a-1 row (→ ✅ merged), FF-merge to `master`, push.

---

## Self-review (against the spec)

**Spec coverage:**
- §3 registry (`batteries.py`: `BatterySpec`, `resolve` dep-closure, `gates_agent`) — Task 1. ✔
- §4 selection (`new --with`, `upskill --with`, registry validation + dep resolution, non-interactive) — Tasks 4, 5. ✔
- §5 conditional rendering (templated paths via the `batteries` answer) + router autodiscovery (additive route batteries) — Tasks 2, 3. Managed-section injection is specified in the spec but not exercised (websockets needs none) — correctly out of this plan. ✔
- §6 recorded battery set — Task 5 (`read_batteries`), via the declared `type: yaml` answer (the documented refinement vs. the spec's `record_portable_source` approach — more robust for upskill); surfacing to the data agents is recorded-set-only here, richer context deferred to 8f per the spec. ✔
- §7 websockets vehicle (route + connection manager + generated test, no dep/service) — Task 3. ✔
- §8 agent gating — `gates_agent` is declared (Task 1); no battery-gated agent exists yet, and `active_agents` already excludes `active_when="battery"` (7b), so there is no activation plumbing to build in 8a-1 (YAGNI — lands with graphql/8d). Noted, no task needed. ✔
- §9 testing (registry, render with/without, autodiscovery, answers record, upskill --with, acceptance with-websockets variant) — Tasks 1-6. ✔

**Placeholder scan:** concrete code/commands throughout. Task 6 intentionally defers to the file's existing acceptance helpers (read them first) rather than guessing the render-helper/skipif details — flagged as a read step, not a placeholder.

**Type consistency:** `BatterySpec(name, summary, requires, gates_agent)`, `resolve(selected) -> list[str]`, `battery_names`/`get_battery`, `read_batteries(project) -> list[str]`, `upskill_project(project, vcs_ref=None, with_batteries=None) -> bool`, the `batteries` answer is a `list[str]` end-to-end (CLI `resolve` → `render_project` data → Copier `type: yaml` → `.copier-answers.yml` → `read_batteries`). Consistent across tasks.

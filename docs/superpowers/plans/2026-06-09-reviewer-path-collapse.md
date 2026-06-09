# Reviewer Path Collapse (Plan 20b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With the swappable backend in place (Plan 20a), collapse the reviewer's prepare→split-manifest→Workflow-JS→finalize orchestration into ONE in-process Python engine, add cost-safe opt-in backend resolution + checkpoint/resume, and **completely retire** the dead JS/slash/split-manifest path.

**Architecture:** A single `run_engine` iterates review items, calls the 20a loop (`run_agent`/`run_agent_agentic`) with a resolved `Backend`, and checkpoints each record to disk as it completes. `framework audit` / `framework gate` drive it in-process; the prepare/dispatch/finalize commands and their Workflow-JS counterparts — which existed only to bridge Python→JS→Python — are deleted. Backend selection is cost-safe opt-in (R1–R4): no spend without explicit intent, no cross-backend fallback, informed opt-in, mutable any time. Mid-run subscription exhaustion checkpoints and resumes.

**Prerequisite:** Plan 20a merged (`backend.py`, `request.py`, the parity contract test, and `eval`/`review --backend` exist).

**Tech Stack:** Python 3.12, `uv`, Typer, `pytest`, `claude` CLI, `tomllib`.

**Spec:** `docs/superpowers/specs/2026-06-09-reviewer-path-parity-design.md`.

**Working agreement:** Every commit stages an updated `CLAUDE.md` Current-State pointer (a `PreToolUse` hook enforces it). Pre-commit gate: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`. Full-suite runs use `TMPDIR=/var/tmp` (per `[[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]`). All unit tests are hermetic (fake backend / fake `claude -p` runner); live calls appear only in the explicit smoke task. Per `[[gate-cadence-framework-slices]]`, one branch-end review, not per-commit. **Review-model policy:** implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; **code-quality review → Opus**; final/branch-end review → Opus (see `[[subagent-review-model-pattern]]`).

---

## Retirement contract (read before starting)

20b deletes a path that is woven through `cli.py`, the Workflow scripts, the slash commands, the template, and the gate hook. To guarantee **nothing is left as dead code** — and without leaving permanent "absence tests" as cruft — retirement is governed by a **transient kill-list manifest**, not regression guards:

1. **Delete-with-replacement.** Every task that lands an engine-backed command deletes its prepare/split/finalize counterpart **in the same commit**. There is no "remove the old path later" task to forget.
2. **A transient manifest** (`/tmp/20b-killlist.json`, untracked, gitignored) enumerates every dead artifact with a check-kind. It is built in Task 5.1 and is the master completeness list.
3. **A throwaway verification runner** (`/tmp/verify_killlist.py`, never committed) asserts every manifest entry is gone, backed by `ruff check` (F401) and one-shot `uvx vulture`. It runs in the final retirement task.
4. **When the whole manifest is green → delete the runner and the manifest.** No absence-checking survives into the committed tree.
5. **Permanent tests are only *positive* assertions** with ongoing value — the new commands work, the gate hook invokes `framework gate`, the rendered project passes its existing acceptance suite. The proof the dead path is gone is *implicit and free*: the full suite stays green **without** the deleted code.

**Surviving review entry points after 20b** (the definition of "not dead" — anything in the review surface unreachable from these is dead):
`framework review`, `framework review config {show,set-backend,clear}`, `framework eval`, `framework eval-analyze`, `framework audit`, `framework gate`, `framework review-aggregate`, `framework review-agents`.

**The kill-list** (built into the manifest in Task 5.1):
- cli.py symbols: `_build_work_item`, `_build_audit_work_item`, `_emit_audit_prep`, `_emit_gate_prep`, `_emit_tune_prep`, `_prepare_split_dir`, `_load_finalize_payload` (verify orphaned), and the command functions `audit_prepare`, `audit_finalize`, plus the `gate-prepare`/`gate-finalize`/`tune-prepare`/`tune-finalize` commands.
- files: `.claude/workflows/reviewers-{audit,gate,tune}.js`; `.claude/commands/reviewers/{audit,gate,tune,template-audit}.md`; every `src/framework_cli/template/.claude/**` `.jinja` copy of those.
- tests: the split-manifest tests in `tests/test_cli.py` (`test_tune_prepare_split_manifest_write`, the `audit-prepare`/`gate-prepare` split tests).
- settings: the gate-hook command string invoking the old `/reviewers:gate` / `gate-prepare` (framework + template).

Note: `_finalize_audit` / `_finalize_gate` / `_finalize_tune` (the record→artifacts helpers) are **kept** — the engine feeds them. Only the prepare/split producers and the `*-finalize` *commands* die.

---

## Phase 1 — Backend resolution & cost-safe opt-in (R1–R4)

### Task 1.1: `.framework/review.toml` read/write/clear

**Files:**
- Create: `src/framework_cli/review/config.py`
- Test: `tests/review/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_config.py
from framework_cli.review.config import read_backend_choice, write_backend_choice, clear_backend_choice


def test_write_read_clear_roundtrip(tmp_path):
    assert read_backend_choice(tmp_path) is None
    write_backend_choice(tmp_path, "subagent")
    assert read_backend_choice(tmp_path) == "subagent"
    write_backend_choice(tmp_path, "api")
    assert read_backend_choice(tmp_path) == "api"
    clear_backend_choice(tmp_path)
    assert read_backend_choice(tmp_path) is None


def test_read_ignores_malformed_toml(tmp_path):
    (tmp_path / ".framework").mkdir()
    (tmp_path / ".framework" / "review.toml").write_text("not = [valid")
    assert read_backend_choice(tmp_path) is None  # fail-open, never crashes a review


def test_write_rejects_unknown_backend(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_backend_choice(tmp_path, "gpt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_config.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/config.py
from __future__ import annotations

import tomllib
from pathlib import Path

_VALID: tuple[str, ...] = ("api", "subagent")
_CONFIG_REL = Path(".framework") / "review.toml"


def _config_path(root: Path) -> Path:
    return root / _CONFIG_REL


def read_backend_choice(root: Path) -> str | None:
    """The persisted backend, or None. Fail-open: malformed config → None (the
    resolution layer treats None as 'no intent')."""
    path = _config_path(root)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return None
    choice = data.get("backend")
    return choice if choice in _VALID else None


def write_backend_choice(root: Path, backend: str) -> None:
    if backend not in _VALID:
        raise ValueError(f"unknown backend {backend!r}; expected one of {_VALID}")
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'backend = "{backend}"\n')


def clear_backend_choice(root: Path) -> None:
    """Remove the persisted choice → resolution returns to the no-intent default."""
    _config_path(root).unlink(missing_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/config.py tests/review/test_config.py CLAUDE.md
git commit -m "feat(review): .framework/review.toml backend-choice read/write/clear"
```

### Task 1.2: `resolve_backend` — R1 no-spend-without-intent, R2 no cross-fallback

**Files:**
- Modify: `src/framework_cli/review/config.py`
- Test: `tests/review/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_config.py
from framework_cli.review.config import resolve_backend


def _avail(api_key=False, claude=False):
    return {"api_key_present": api_key, "claude_available": claude}


def test_no_intent_resolves_to_skip(tmp_path):
    r = resolve_backend(root=tmp_path, flag=None, env={}, availability=_avail(api_key=True, claude=True))
    assert r.backend is None and r.reason == "no-intent"  # R1: presence != consent


def test_flag_api_with_key_resolves_api(tmp_path):
    r = resolve_backend(root=tmp_path, flag="api", env={}, availability=_avail(api_key=True))
    assert r.backend == "api"


def test_flag_api_without_key_skips_no_fallback(tmp_path):
    r = resolve_backend(root=tmp_path, flag="api", env={}, availability=_avail(api_key=False, claude=True))
    assert r.backend is None and r.reason == "api-unavailable"  # R2: does NOT use claude


def test_flag_subagent_without_claude_skips_no_fallback(tmp_path):
    r = resolve_backend(root=tmp_path, flag="subagent", env={}, availability=_avail(api_key=True, claude=False))
    assert r.backend is None and r.reason == "subagent-unavailable"  # R2: does NOT spend key


def test_env_overrides_config_but_flag_wins(tmp_path):
    write_backend_choice(tmp_path, "subagent")
    r = resolve_backend(root=tmp_path, flag=None, env={"FRAMEWORK_REVIEW_BACKEND": "api"},
                        availability=_avail(api_key=True, claude=True))
    assert r.backend == "api"
    r2 = resolve_backend(root=tmp_path, flag="subagent", env={"FRAMEWORK_REVIEW_BACKEND": "api"},
                         availability=_avail(api_key=True, claude=True))
    assert r2.backend == "subagent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_config.py -q -k resolve`
Expected: FAIL — `resolve_backend` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/config.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    backend: str | None      # "api" | "subagent" | None (degrade)
    reason: str              # resolved | no-intent | api-unavailable | subagent-unavailable
    intent: str | None       # chosen backend before availability check (for messaging)


def resolve_backend(*, root: Path, flag: str | None, env: dict[str, str],
                    availability: dict[str, bool]) -> Resolution:
    intent = flag or env.get("FRAMEWORK_REVIEW_BACKEND") or read_backend_choice(root)
    if intent not in _VALID:
        return Resolution(backend=None, reason="no-intent", intent=None)
    if intent == "api":
        if availability.get("api_key_present"):
            return Resolution(backend="api", reason="resolved", intent="api")
        return Resolution(backend=None, reason="api-unavailable", intent="api")
    if availability.get("claude_available"):
        return Resolution(backend="subagent", reason="resolved", intent="subagent")
    return Resolution(backend=None, reason="subagent-unavailable", intent="subagent")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/config.py tests/review/test_config.py CLAUDE.md
git commit -m "feat(review): resolve_backend — cost-safe R1/R2 policy"
```

### Task 1.3: `probe_availability` (presence only, never consent)

**Files:**
- Modify: `src/framework_cli/review/config.py`
- Test: `tests/review/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_config.py
from framework_cli.review.config import probe_availability


def test_probe_detects_key_and_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "sk-x")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None)
    a = probe_availability(key_env="ANTHROPIC_RUNTIME_API_KEY")
    assert a == {"api_key_present": True, "claude_available": True}


def test_probe_no_key_no_claude(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    a = probe_availability(key_env="ANTHROPIC_RUNTIME_API_KEY")
    assert a == {"api_key_present": False, "claude_available": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_config.py -q -k probe`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/config.py
import os
import shutil


def probe_availability(*, key_env: str) -> dict[str, bool]:
    """What backends *could* run here. Presence only — never consent (R1)."""
    return {
        "api_key_present": bool(os.environ.get(key_env)),
        "claude_available": shutil.which("claude") is not None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/config.py tests/review/test_config.py CLAUDE.md
git commit -m "feat(review): probe_availability (key + claude presence)"
```

### Task 1.4: `framework review config` command (show / set-backend / clear)

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py` (assert on `result.stdout` per `[[audit-prepare-snapshot-stderr-breaks-cli-runner-output]]`)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_review_config_set_show_clear(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    r = runner.invoke(app, ["review-config", "show"])
    assert r.exit_code == 0 and "none" in r.stdout.lower()

    r = runner.invoke(app, ["review-config", "set-backend", "subagent", "--yes"])
    assert r.exit_code == 0
    assert (tmp_path / ".framework" / "review.toml").read_text().strip() == 'backend = "subagent"'

    r = runner.invoke(app, ["review-config", "show"])
    assert r.exit_code == 0 and "subagent" in r.stdout

    r = runner.invoke(app, ["review-config", "clear"])
    assert r.exit_code == 0 and not (tmp_path / ".framework" / "review.toml").exists()
```

(Decision: expose as `framework review-config` — a flat command group — to sidestep Typer's inability to nest a sub-group under the existing single `review` command. If you instead refactor `review` into a Typer group with a default callback, use `["review","config",...]` and keep the test in sync.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_review_config_set_show_clear -q`
Expected: FAIL — no such command.

- [ ] **Step 3: Write minimal implementation**

```python
# cli.py
review_config_app = typer.Typer(help="Configure the AI review backend (mutable any time).")
app.add_typer(review_config_app, name="review-config")

@review_config_app.command("show")
def review_config_show() -> None:
    from framework_cli.review.config import read_backend_choice
    choice = read_backend_choice(Path.cwd())
    typer.echo(f"review backend: {choice or 'none (skip-neutral; AI review not enabled)'}")

@review_config_app.command("set-backend")
def review_config_set(backend: str, yes: bool = typer.Option(False, "--yes")) -> None:
    from framework_cli.review.config import write_backend_choice
    if backend not in ("api", "subagent"):
        typer.echo("backend must be 'api' or 'subagent'", err=True)
        raise typer.Exit(2)
    if not yes:
        cost = ("paid per use (your API key)" if backend == "api"
                else "free within your Claude subscription; may consume overage past your limit")
        typer.echo(f"Enabling AI review on the '{backend}' backend — {cost}.")
        typer.confirm("Proceed?", abort=True)
    write_backend_choice(Path.cwd(), backend)
    typer.echo(f"review backend set to '{backend}'")

@review_config_app.command("clear")
def review_config_clear() -> None:
    from framework_cli.review.config import clear_backend_choice
    clear_backend_choice(Path.cwd())
    typer.echo("review backend cleared → AI review is skip-neutral until re-enabled")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_review_config_set_show_clear -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(cli): framework review-config show/set-backend/clear (R3 informed, R4 mutable)"
```

### Phase 1 gate

- [ ] Full quality gate green.

---

## Phase 2 — Checkpoint / resume / exhaustion (Component 6)

### Task 2.1: `run-state.json` manifest + incremental record append

**Files:**
- Create: `src/framework_cli/review/checkpoint.py`
- Test: `tests/review/test_checkpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_checkpoint.py
from framework_cli.review.checkpoint import init_run, append_record, load_state, pending_items, is_stale


def test_checkpoint_tracks_done_and_pending(tmp_path):
    run = tmp_path / "run"
    init_run(run, planned=["security", "architecture", "documentation"],
             git_sha="abc123", dirty_hash="d0", backend="subagent")
    append_record(run, "security", {"agent": "security", "findings": []})
    state = load_state(run)
    assert state["done"] == ["security"]
    assert pending_items(run) == ["architecture", "documentation"]
    assert (run / "findings" / "security.json").is_file()


def test_is_stale_detects_tree_change(tmp_path):
    run = tmp_path / "run"
    init_run(run, planned=["security"], git_sha="abc123", dirty_hash="d0", backend="api")
    assert is_stale(run, git_sha="abc123", dirty_hash="d0") is False
    assert is_stale(run, git_sha="abc123", dirty_hash="d1") is True
    assert is_stale(run, git_sha="zzz", dirty_hash="d0") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_checkpoint.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/checkpoint.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_STATE = "run-state.json"


def _state_path(run_dir: Path) -> Path:
    return run_dir / _STATE


def init_run(run_dir: Path, *, planned: list[str], git_sha: str, dirty_hash: str,
             backend: str) -> None:
    (run_dir / "findings").mkdir(parents=True, exist_ok=True)
    _write_state(run_dir, {"planned": list(planned), "done": [], "git_sha": git_sha,
                           "dirty_hash": dirty_hash, "backend": backend})


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    tmp = _state_path(run_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(_state_path(run_dir))  # atomic: a crash mid-write never corrupts state


def load_state(run_dir: Path) -> dict[str, Any]:
    return json.loads(_state_path(run_dir).read_text())


def append_record(run_dir: Path, agent: str, record: dict[str, Any]) -> None:
    """Write one agent's record AND mark it done — so resume never re-runs a completed
    agent or loses a written record."""
    rec = run_dir / "findings" / f"{agent}.json"
    rec.write_text(json.dumps(record, indent=2, sort_keys=True))
    rec.chmod(0o600)
    state = load_state(run_dir)
    if agent not in state["done"]:
        state["done"].append(agent)
    _write_state(run_dir, state)


def pending_items(run_dir: Path) -> list[str]:
    state = load_state(run_dir)
    done = set(state["done"])
    return [a for a in state["planned"] if a not in done]


def is_stale(run_dir: Path, *, git_sha: str, dirty_hash: str) -> bool:
    state = load_state(run_dir)
    return state["git_sha"] != git_sha or state["dirty_hash"] != dirty_hash
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_checkpoint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/checkpoint.py tests/review/test_checkpoint.py CLAUDE.md
git commit -m "feat(review): checkpoint run-state + incremental record append + staleness"
```

### Task 2.2: Working-tree signature

**Files:**
- Modify: `src/framework_cli/review/checkpoint.py`
- Test: `tests/review/test_checkpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_checkpoint.py
import subprocess
from framework_cli.review.checkpoint import tree_signature


def test_tree_signature_changes_with_content(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("one")
    _, dirty1 = tree_signature(tmp_path)
    (tmp_path / "f.txt").write_text("two")
    _, dirty2 = tree_signature(tmp_path)
    assert dirty1 != dirty2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_checkpoint.py::test_tree_signature_changes_with_content -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/checkpoint.py
import hashlib
import subprocess


def tree_signature(root: Path) -> tuple[str, str]:
    """(HEAD sha, dirty-hash). The dirty-hash digests `git status --porcelain` + `git diff`,
    so any uncommitted change moves it. Fail-open: a non-git dir returns ("", <digest>)."""
    def _git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True,
                                  text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""
    sha = _git("rev-parse", "HEAD").strip()
    digest = hashlib.sha256((_git("status", "--porcelain") + _git("diff")).encode("utf-8", "replace")).hexdigest()[:16]
    return sha, digest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_checkpoint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/checkpoint.py tests/review/test_checkpoint.py CLAUDE.md
git commit -m "feat(review): tree_signature for checkpoint staleness"
```

### Phase 2 gate

- [ ] Full quality gate green.

---

## Phase 3 — The in-process engine

### Task 3.1: `run_engine` — dispatch + per-item checkpoint + exhaustion stop

**Files:**
- Create: `src/framework_cli/review/engine.py`
- Test: `tests/review/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_engine.py
from framework_cli.review.engine import run_engine, EngineItem
from framework_cli.review.backend import BackendExhausted, Message, TextBlock
from framework_cli.review.registry import ContextPolicy


class _Spec:
    def __init__(self, name, strategy="diff"):
        self.name = name; self.model = "m"; self.context = ContextPolicy(strategy); self.prompt = "P"


def _backend_returning(findings_json):
    class _Msgs:
        def create(self, **kw):
            return Message(content=[TextBlock(text=findings_json)], stop_reason="end_turn")
    return type("B", (), {"messages": _Msgs()})()


def test_engine_writes_record_per_item(tmp_path):
    items = [EngineItem(agent="security", diff="D", spec=_Spec("review-security")),
             EngineItem(agent="documentation", diff="D", spec=_Spec("review-documentation"))]
    run = tmp_path / "run"
    result = run_engine(items, backend=_backend_returning("[]"), run_dir=run, root=tmp_path,
                        git_sha="s", dirty_hash="h", backend_name="api")
    assert result.completed == ["security", "documentation"]
    assert result.exhausted is False
    assert (run / "findings" / "security.json").is_file()


def test_engine_checkpoints_then_stops_on_exhaustion(tmp_path):
    calls = {"n": 0}
    class _Msgs:
        def create(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")
            raise BackendExhausted("limit", reset_hint="3pm")
    backend = type("B", (), {"messages": _Msgs()})()
    items = [EngineItem(agent="security", diff="D", spec=_Spec("review-security")),
             EngineItem(agent="architecture", diff="D", spec=_Spec("review-architecture"))]
    run = tmp_path / "run"
    result = run_engine(items, backend=backend, run_dir=run, root=tmp_path,
                        git_sha="s", dirty_hash="h", backend_name="subagent")
    assert result.exhausted is True and result.reset_hint == "3pm"
    assert result.completed == ["security"]
    assert "architecture" not in result.completed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_engine.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/engine.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic
from framework_cli.review.backend import BackendExhausted
from framework_cli.review.checkpoint import append_record, init_run, pending_items
from framework_cli.review.context import assemble
from framework_cli.review.decisions import relevant_decisions
from framework_cli.review.runner import run_agent


@dataclass(frozen=True)
class EngineItem:
    agent: str
    diff: str
    spec: Any
    review_mode: str = "snapshot"
    base_sha: str | None = None
    base_baseline: str | None = None


@dataclass
class EngineResult:
    completed: list[str] = field(default_factory=list)
    exhausted: bool = False
    reset_hint: str | None = None
    records: list[dict[str, Any]] = field(default_factory=list)


def _run_one(item: EngineItem, backend: Any, root: Path) -> dict[str, Any]:
    spec = item.spec
    report: dict[str, Any] = {}
    if spec.context.strategy == "agentic":
        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS
        findings = run_agent_agentic(item.diff, root, spec, backend, max_turns=turns,
                                     report=report,
                                     decisions=tuple(relevant_decisions(item.agent, root)))
    else:
        bundle = assemble(item.diff, root, spec.context, model=spec.model, agent=item.agent)
        findings = run_agent(bundle, spec, backend, report=report)
    return {
        "agent": item.agent, "spec_name": spec.name,
        "findings": [f.__dict__ for f in findings],
        "review_mode": item.review_mode, "base_sha": item.base_sha,
        "base_baseline": item.base_baseline,
        "usage": report.get("usage", {}), "latency_ms": report.get("latency_ms"),
        "stop_reason": report.get("stop_reason"), "raw_text": report.get("raw_text", ""),
        "turns": report.get("turns", 1), "tool_calls": report.get("tool_calls", []),
    }


def run_engine(items: list[EngineItem], *, backend: Any, run_dir: Path, root: Path,
               git_sha: str, dirty_hash: str, backend_name: str,
               resume: bool = False) -> EngineResult:
    """Iterate items → dispatch via the unified loop → checkpoint each record as it
    completes. On BackendExhausted, stop scheduling and return what completed."""
    if not resume:
        init_run(run_dir, planned=[i.agent for i in items], git_sha=git_sha,
                 dirty_hash=dirty_hash, backend=backend_name)
    todo = set(pending_items(run_dir))
    result = EngineResult()
    for item in items:
        if item.agent not in todo:
            continue
        try:
            record = _run_one(item, backend, root)
        except BackendExhausted as exc:
            result.exhausted = True
            result.reset_hint = exc.reset_hint
            break
        append_record(run_dir, item.agent, record)
        result.completed.append(item.agent)
        result.records.append(record)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Verify the record shape matches `_finalize_audit`'s expectations**

Read `_finalize_audit` (cli.py ~1736–1835) and confirm it consumes records keyed `agent` / `findings` / `usage` / `review_mode` / `base_sha` / `base_baseline`. If the engine's record dict differs from what the finalize functions read (e.g. nested vs flat findings, or `raw_text`/`turns` names), reconcile here — adjust `_run_one`'s dict to the finalize schema and add an assertion test. Do NOT change `_finalize_audit`'s logic; match its input.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/engine.py tests/review/test_engine.py CLAUDE.md
git commit -m "feat(review): in-process engine — dispatch + per-item checkpoint + exhaustion stop"
```

---

## Phase 4 — `framework audit` / `framework gate` (replace prepare→JS→finalize)

### Task 4.1: `framework audit` — selection + engine + finalize + resume

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

This task **deletes** `audit-prepare` and `audit-finalize` (commands) and `_emit_audit_prep`, `_build_audit_work_item`, in the same commit that adds `framework audit` (delete-with-replacement). Keep `_finalize_audit`, `_detect_audit_target`, `_resolve_audit_base`, `delta_diff`, `snapshot_seed`.

- [ ] **Step 1: Write the failing test** (hermetic — inject stub backend + force resolution)

```python
# add to tests/test_cli.py
def test_audit_runs_in_process_and_writes_report(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    import framework_cli.cli as climod
    from framework_cli.cli import app
    from framework_cli.review.backend import Message, TextBlock
    class _Msgs:
        def create(self, **kw): return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")
    monkeypatch.setattr(climod, "_make_backend", lambda name, key_env: type("B", (), {"messages": _Msgs()})())
    monkeypatch.setattr(climod, "_resolve_review_backend",
                        lambda **kw: type("R", (), {"backend": "api", "reason": "resolved", "intent": "api"})())
    # ... init a git repo + framework markers under tmp_path; chdir there ...
    r = CliRunner().invoke(app, ["audit", "--target", "framework", "--backend", "api",
                                 "--out-dir", str(tmp_path / "out")])
    assert r.exit_code == 0
    assert (tmp_path / "out" / "audit-report.md").is_file()
    assert (tmp_path / "out" / "meta.json").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_audit_runs_in_process_and_writes_report -q`
Expected: FAIL — no `audit` command.

- [ ] **Step 3: Implement `framework audit` + shared helpers; delete the audit prepare/finalize commands**

```python
# cli.py — shared backend wiring (used by audit/gate/review/eval)
def _resolve_review_backend(*, flag, key_env):
    from framework_cli.review.config import probe_availability, resolve_backend
    return resolve_backend(root=Path.cwd(), flag=flag, env=dict(os.environ),
                           availability=probe_availability(key_env=key_env))

def _explain_no_backend(res, *, command):
    if res.reason == "api-unavailable":
        msg = "review backend 'api' selected but no API key is set"
    elif res.reason == "subagent-unavailable":
        msg = "review backend 'subagent' selected but the `claude` CLI was not found"
    else:
        msg = "no review backend enabled (set --backend, FRAMEWORK_REVIEW_BACKEND, or `framework review-config set-backend`)"
    typer.echo(f"{command}: {msg}", err=False)

@app.command()
def audit(target: str = typer.Option("", "--target"),
          agent: list[str] = typer.Option(None, "--agent"),
          out_dir: str = typer.Option(".framework/audit/latest", "--out-dir"),
          backend: str = typer.Option(None, "--backend"),
          snapshot: bool = typer.Option(False, "--snapshot"),
          since: str = typer.Option("", "--since"),
          resume: bool = typer.Option(False, "--resume"),
          fresh: bool = typer.Option(False, "--fresh")) -> None:
    res = _resolve_review_backend(flag=backend, key_env=RUNTIME_KEY_ENV)
    if res.backend is None:
        _explain_no_backend(res, command="audit")
        raise typer.Exit(2)  # explicit invocation → actionable error (spec: audit/tune error)
    from framework_cli.review.checkpoint import is_stale, tree_signature
    from framework_cli.review.engine import EngineItem, run_engine
    out = Path(out_dir)
    sha, dirty = tree_signature(Path.cwd())
    if resume and out.exists() and is_stale(out, git_sha=sha, dirty_hash=dirty) and not fresh:
        typer.echo("audit: checkpoint is stale (tree changed); re-run with --fresh to restart", err=False)
        raise typer.Exit(2)
    items = _build_audit_items(target, list(agent or []), snapshot, since or None)  # uses existing selection helpers
    result = run_engine(items, backend=_make_backend(res.backend, RUNTIME_KEY_ENV),
                        run_dir=out, root=Path.cwd(), git_sha=sha, dirty_hash=dirty,
                        backend_name=res.backend, resume=resume)
    if result.exhausted:
        hint = f" (resets {result.reset_hint})" if result.reset_hint else ""
        typer.echo(f"Subscription limit reached after {len(result.completed)} agents. "
                   f"Progress checkpointed at {out}. Resume with `framework audit --resume`{hint}.")
    findings_dir = out / "findings"; findings_dir.mkdir(parents=True, exist_ok=True)
    _finalize_audit(_load_records_from_checkpoint(out), findings_dir, out, _audit_meta_in(target))
```

Add `_build_audit_items(...)` (returns `list[EngineItem]` via the existing `_detect_audit_target` + per-agent `_resolve_audit_base` + `delta_diff`/`snapshot_seed` logic lifted from `_emit_audit_prep`), `_load_records_from_checkpoint(out)` (reads `findings/*.json`), and `_audit_meta_in(target)`. Then **delete** the `audit-prepare` / `audit-finalize` commands and `_emit_audit_prep` / `_build_audit_work_item` in this same commit.

- [ ] **Step 4: Run test to verify it passes; delete the now-failing audit-prepare tests**

Run: `uv run pytest tests/test_cli.py -q -k audit`
Expected: the new test passes; the old `audit-prepare`/split tests fail because the command is gone — **delete them** (they are part of the kill-list).

- [ ] **Step 5: Commit**

```bash
git add -A && git add CLAUDE.md
git commit -m "feat(cli): framework audit in-process; delete audit-prepare/finalize + _emit_audit_prep"
```

### Task 4.2: `framework gate` (skip-neutral degrade) + delete gate-prepare/finalize commands

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

Deletes `gate-prepare`/`gate-finalize` commands + `_emit_gate_prep` in the same commit. Keeps `_finalize_gate`, `_affected_agents`, `staged_diff`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_cli.py
def test_gate_skip_neutral_without_backend(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda n: None)
    r = CliRunner().invoke(app, ["gate"])
    assert r.exit_code == 0 and "skip" in r.stdout.lower()  # never blocks the commit

def test_audit_errors_without_backend(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda n: None)
    r = CliRunner().invoke(app, ["audit", "--target", "framework"])
    assert r.exit_code == 2 and "backend" in r.stdout.lower()  # explicit → actionable error
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_cli.py -q -k "gate_skip_neutral or audit_errors"`
Expected: FAIL.

- [ ] **Step 3: Implement `framework gate`; delete gate-prepare/finalize + `_emit_gate_prep`**

`gate` resolves the backend; if `res.backend is None` → write a skip-neutral marker (verdict PASS, reason "no backend") and `raise typer.Exit(0)`. Otherwise build affected-only `EngineItem`s via `_affected_agents` + `staged_diff`, `run_engine`, then `_finalize_gate(records, ...)`. Delete the `gate-prepare`/`gate-finalize` commands and `_emit_gate_prep` in this commit. Delete their split tests.

- [ ] **Step 4: Run to verify they pass; delete stale gate-prepare tests**

Run: `uv run pytest tests/test_cli.py -q -k gate`
Expected: PASS; remove the dead gate-prepare split tests.

- [ ] **Step 5: Commit**

```bash
git add -A && git add CLAUDE.md
git commit -m "feat(cli): framework gate skip-neutral; delete gate-prepare/finalize + _emit_gate_prep"
```

### Task 4.3: Retire `tune-prepare`/`tune-finalize` (tune runs in-process via eval path)

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

`tune` is a framework-dev calibration activity. With `framework eval --backend subagent` (20a) producing the same records the tune-finalize scorecard consumes, the JS tune path is redundant. Either fold tune-finalize's scorecard generation into `eval-analyze`, or keep `_finalize_tune` reachable from `eval --findings-out` + a small `tune` wrapper. Delete `tune-prepare`, `tune-finalize` commands, `_emit_tune_prep`, `_build_work_item` in the same commit.

- [ ] **Step 1: Decide tune's surviving entry point and write its test**

Confirm Plan 21's needs: it tunes via repeated `framework eval <agent> --backend subagent --findings-out DIR` then `framework eval-analyze DIR`. If that already yields the scorecard + threshold proposal, `tune-prepare`/`finalize` are pure kill-list. Write a test asserting `framework eval-analyze` over an eval `--findings-out` dir produces `scorecard.md` / `thresholds.proposal.yaml` (porting `_finalize_tune`'s scorecard logic into `eval-analyze` if needed).

- [ ] **Step 2–4: Implement, run, delete dead tune tests** (mirror 4.1/4.2)

- [ ] **Step 5: Commit**

```bash
git add -A && git add CLAUDE.md
git commit -m "refactor(cli): tune via eval+eval-analyze; delete tune-prepare/finalize + _build_work_item"
```

### Task 4.4: Route `review`/`eval` through full resolution (gate skip-neutral semantics)

**Files:**
- Modify: `src/framework_cli/cli.py`
- Test: `tests/test_cli.py`

20a gave `review`/`eval` a `--backend` flag defaulting to `api`. Now route them through `_resolve_review_backend` so they honor `FRAMEWORK_REVIEW_BACKEND` / `.framework/review.toml` and degrade per the matrix (review/eval explicit → error on no backend; keep `eval --require-key` semantics mapped onto resolution).

- [ ] Steps mirror the pattern above (test → implement → run → commit).

### Phase 4 gate

- [ ] Full quality gate green with `TMPDIR=/var/tmp`.

---

## Phase 5 — Retire the Workflow/JS/slash/template path (manifest-driven)

### Task 5.1: Build the kill-list manifest and delete the framework's own JS + slash files

**Files:**
- Create (untracked): `/tmp/20b-killlist.json`
- Delete: `.claude/workflows/reviewers-{audit,gate,tune}.js`, `.claude/commands/reviewers/{audit,gate,tune,template-audit}.md`
- Modify: `cli.py` — remove any remaining prepare/split helpers (`_prepare_split_dir`, `_load_finalize_payload` if orphaned)

- [ ] **Step 1: Build the manifest** (the master completeness list; see the Retirement contract)

```bash
cat > /tmp/20b-killlist.json <<'JSON'
{
  "symbols": ["_build_work_item","_build_audit_work_item","_emit_audit_prep","_emit_gate_prep",
              "_emit_tune_prep","_prepare_split_dir","_load_finalize_payload"],
  "commands": ["audit-prepare","audit-finalize","gate-prepare","gate-finalize","tune-prepare","tune-finalize"],
  "files": [".claude/workflows/reviewers-audit.js",".claude/workflows/reviewers-gate.js",
            ".claude/workflows/reviewers-tune.js",".claude/commands/reviewers/audit.md",
            ".claude/commands/reviewers/gate.md",".claude/commands/reviewers/tune.md",
            ".claude/commands/reviewers/template-audit.md"],
  "grep": ["split_to","index.json","item-","reviewers-audit","reviewers-gate","reviewers-tune"],
  "settings_strings": ["reviewers:gate","gate-prepare"]
}
JSON
echo "/tmp/20b-killlist.json" # untracked scratch; ensure /tmp is gitignored or outside the repo
```

- [ ] **Step 2: Delete the framework's own JS + slash files; remove orphaned helpers**

```bash
git rm .claude/workflows/reviewers-audit.js .claude/workflows/reviewers-gate.js .claude/workflows/reviewers-tune.js
git rm .claude/commands/reviewers/audit.md .claude/commands/reviewers/gate.md .claude/commands/reviewers/tune.md .claude/commands/reviewers/template-audit.md
```

Grep for and delete `_prepare_split_dir` / `_load_finalize_payload` if no surviving entry point references them.

- [ ] **Step 3: Run the full suite with `TMPDIR=/var/tmp`; delete any remaining split-manifest tests**

Run: `TMPDIR=/var/tmp uv run pytest -q`
Expected: failures only in deleted-feature tests → delete them. Re-run until green.

- [ ] **Step 4: Commit**

```bash
git add -A && git add CLAUDE.md
git commit -m "refactor(review): delete Workflow JS + slash commands + split-manifest plumbing"
```

### Task 5.2: Replace the template's reviewer payload with `framework` entry points

**Files:**
- Delete: `src/framework_cli/template/.claude/workflows/reviewers-*.js.jinja`
- Replace/Delete: `src/framework_cli/template/.claude/commands/reviewers/*.md.jinja` → one-line stubs that shell to `framework audit`/`gate`, or delete + document in the rendered README
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the positive template test** (new correct state, not an absence guard against future regressions — this is permanent because it asserts the rendered project's *shape*)

```python
# tests/test_copier_runner.py
def test_rendered_project_uses_framework_review_entrypoints(rendered_project):
    assert not (rendered_project / ".claude" / "workflows" / "reviewers-audit.js").exists()
    # the rendered project documents `framework audit`/`gate` as the entry points
```

- [ ] **Step 2: Run to verify it fails**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py::test_rendered_project_uses_framework_review_entrypoints -q`
Expected: FAIL — the JS still renders.

- [ ] **Step 3: Delete/replace the template payload**

```bash
git rm src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja \
       src/framework_cli/template/.claude/workflows/reviewers-gate.js.jinja \
       src/framework_cli/template/.claude/workflows/reviewers-tune.js.jinja
```

Replace each `template/.claude/commands/reviewers/*.md.jinja` with a one-line `framework`-invoking stub or delete + add the entry-point note to the README template.

- [ ] **Step 4: Re-render + acceptance** (per `[[template-payload-tdd-loop]]`)

Run: `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py tests/acceptance/test_rendered_project.py -q`
Expected: PASS — the generated project renders, its tests pass, and its first `pre-commit` is clean (`test_rendered_project_precommit_runs_clean`).

- [ ] **Step 5: Commit**

```bash
git add -A && git add CLAUDE.md
git commit -m "refactor(template): reviewer payload → framework-CLI entry points (no Workflow JS)"
```

### Task 5.3: Rewire the gate hook (framework + template)

**Files:**
- Modify: `.claude/settings.json`, `src/framework_cli/template/.claude/settings.json.jinja`

- [ ] **Step 1: Find the current wiring**

Run: `grep -rn "reviewers:gate\|gate-prepare\|gate-finalize\|reviewers-gate" .claude/ src/framework_cli/template/.claude/`

- [ ] **Step 2: Replace the hook command with `framework gate`** (skip-neutral, so a key-less builder is never blocked). Keep the separate CLAUDE.md-staged check.

- [ ] **Step 3: Dry-run**

Stage a trivial change; run `framework gate` manually. Confirm exit 0 + marker written, and skip-neutral when `ANTHROPIC_RUNTIME_API_KEY` is unset and `claude` is absent.

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json src/framework_cli/template/.claude/settings.json.jinja CLAUDE.md
git commit -m "chore(review): gate hook invokes framework gate (skip-neutral degrade)"
```

### Task 5.4: Run the completeness verification, then delete the scaffolding

**Files:** none committed (transient `/tmp/verify_killlist.py`, `/tmp/20b-killlist.json`)

- [ ] **Step 1: Write the throwaway verifier** (untracked; never committed)

```python
# /tmp/verify_killlist.py
import json, subprocess, sys, importlib
from typer.testing import CliRunner

m = json.load(open("/tmp/20b-killlist.json"))
fail = []

cli = importlib.import_module("framework_cli.cli")
for sym in m["symbols"]:
    if hasattr(cli, sym):
        fail.append(f"symbol still present: {sym}")

runner = CliRunner()
for cmd in m["commands"]:
    r = runner.invoke(cli.app, [cmd, "--help"])
    if r.exit_code == 0:
        fail.append(f"command still present: {cmd}")

import os
for f in m["files"]:
    if os.path.exists(f):
        fail.append(f"file still present: {f}")

for pat in m["grep"]:
    out = subprocess.run(["grep","-rn","--",pat,"src","tests",".claude"],
                         capture_output=True, text=True).stdout.strip()
    if out:
        fail.append(f"grep hit for {pat!r}:\n{out}")

for s in m["settings_strings"]:
    out = subprocess.run(["grep","-rn","--",s,".claude","src/framework_cli/template/.claude"],
                         capture_output=True, text=True).stdout.strip()
    if out:
        fail.append(f"settings still reference {s!r}:\n{out}")

print("DEAD CODE FOUND:\n" + "\n".join(fail) if fail else "KILL-LIST CLEAN")
sys.exit(1 if fail else 0)
```

- [ ] **Step 2: Run the verifier + ruff + vulture backstop**

```bash
uv run python /tmp/verify_killlist.py
uv run ruff check .            # F401 unused imports must be clean
uvx vulture src/framework_cli/review src/framework_cli/cli.py --min-confidence 80
```

Expected: `KILL-LIST CLEAN`, ruff clean, and vulture reporting no unused review/cli symbols (triage any false positive — e.g. a Typer-decorated command — and confirm it's genuinely reachable). If anything is flagged, delete it and re-run until clean.

- [ ] **Step 3: Delete the scaffolding**

```bash
rm -f /tmp/verify_killlist.py /tmp/20b-killlist.json
```

The dead path is now provably gone; the proof was scaffolding and is discarded. No absence tests remain in the committed tree — the green suite without the deleted code is the standing proof.

- [ ] **Step 4: Commit** (nothing to add beyond any final cleanup the verifier surfaced + CLAUDE.md)

```bash
git add -A && git add CLAUDE.md
git commit -m "chore(review): kill-list verified clean — dead reviewer path fully retired"
```

### Phase 5 gate

- [ ] Full quality gate green with `TMPDIR=/var/tmp`, including render/acceptance.

---

## Phase 6 — Parity confirmation & finish

### Task 6.1: Live subagent vs api smoke (one agent)

- [ ] Opt in and run one agent on the free backend, then the paid:

```bash
framework review-config set-backend subagent --yes
framework audit --target framework --agent security --backend subagent --out-dir /tmp/parity-smoke
framework audit --target framework --agent security --backend api --out-dir /tmp/parity-smoke-api
```

Expected: the subagent run uses `claude -p` (free), `meta.json` records `backend: subagent`, findings parse without `FindingsParseError`. Compare the two reports for the same agent — material divergence is a real parity bug (calibrated thresholds are Plan 21, not here).

### Task 6.2: Status, review, merge

- [ ] Mark Plan 20b ✅ in the meta-plan + CLAUDE.md; note the parity-smoke result.
- [ ] Branch-end full review.
- [ ] superpowers:finishing-a-development-branch → merge to `master`.
- [ ] Update memories: `[[reviewer-dev-prod-parity-gap]]` / `[[paid-path-operative-for-builders]]` → parity gap **closed** (one engine, swappable backend); retire `[[reviewer-subagent-dispatch-model]]` (Workflow dispatch no longer exists).

---

## Self-Review

**Spec coverage (20b slice):** in-process engine + shared synthesis (Phase 3 + `_finalize_*` reuse); R1–R4 resolution (Phase 1); checkpoint/resume + `BackendExhausted` (Phase 2 + Tasks 4.1); gate skip-neutral vs audit/tune error (Tasks 4.1/4.2/4.4); `framework new` informed opt-in reachable via `review-config set-backend` (Task 1.4 — note: wiring a *render-time* prompt into `framework new` is flagged as a follow-up below); retire Workflow/slash/split-manifest/template (Phase 5); gate-hook rewire (Task 5.3); parity smoke (Task 6.1).

**Dead-code guarantee:** Retirement contract + Task 5.4 manifest verification; delete-with-replacement per task; transient scaffolding self-deletes; only positive permanent tests remain.

**Placeholder scan:** Tasks 4.3/4.4 are intentionally pattern-referenced (they repeat the test→implement→delete→commit shape of 4.1/4.2 against tune/eval-resolution) rather than re-printing identical code — each names its exact deletions and surviving entry point. Task 4.1 Step 3 leaves `_build_audit_items`/`_audit_meta_in` as named helpers to lift from the existing `_emit_audit_prep` body (the source logic exists; this is a move, not new design).

**Flagged follow-ups (resolve during execution, do not silently skip):**
1. `framework new` render-time opt-in prompt (R3 at first-render) — small addition if `new` is interactive; otherwise builders opt in via `review-config`.
2. `--require-backend` for CI hard-fail on `gate`/`audit`.
3. Confirm the engine record schema matches `_finalize_audit`/`_finalize_gate`/`_finalize_tune` exactly (Task 3.1 Step 5).

**Type consistency:** `Resolution(backend, reason, intent)`, `EngineItem`/`EngineResult`, `run_engine(...)`, checkpoint `init_run`/`append_record`/`pending_items`/`is_stale`/`tree_signature`, `_make_backend`/`_resolve_review_backend`/`_explain_no_backend` consistent across tasks and shared with 20a.
</content>

# Audit Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `audit-prepare`'s `HEAD~1...HEAD` diff source with snapshot-primary semantics + per-agent delta-vs-prior-baseline auto-discovery, behind two explicit override flags (`--snapshot`, `--since <ref-or-dir>`).

**Architecture:** A new `framework_cli.review.baselines` module houses per-(target, agent) baseline discovery. New `snapshot_seed()` and `delta_diff()` helpers in `review/diff.py` produce the per-agent diff text. `audit-prepare` calls a new `_resolve_audit_base(agent, target, ...)` helper to compute `(review_mode, base_sha, base_baseline)` per agent, and `_emit_audit_prep` builds mixed-mode work-items. The workflow branches its per-item prompt on `item.review_mode`. `audit-finalize` records the per-agent decisions in `meta.json` for future delta-discovery.

**Tech Stack:** Python (Typer CLI), pytest, ruff, mypy, `uv`. Plan touches `src/framework_cli/review/diff.py`, new `src/framework_cli/review/baselines.py`, `src/framework_cli/cli.py`, `tests/review/test_diff.py`, new `tests/review/test_baselines.py`, `tests/test_cli.py`, `.claude/workflows/reviewers-audit.js` (+ template mirror), `.claude/commands/reviewers/audit.md` (+ template mirror), and `CLAUDE.md`.

**Spec:** `docs/superpowers/specs/2026-05-30-audit-semantics-design.md`

---

## Background — relevant prior state

Today (master at `bf95e90`):
- `audit-prepare` calls `_review_diff()` → `pr_diff()` → `git diff HEAD~1...HEAD`. This is the bug being fixed.
- `audit-prepare` already has `--target`, `--agent` (repeatable), `--output-dir`, `--split-to`.
- `audit-finalize` writes `findings/<agent>.json` and `audit-report.md` via `_finalize_audit`. Does NOT write `meta.json` today (the prior baseline at `audit-2026-05-30-2446de8/meta.json` was hand-written by the controller during T7 — this plan adds proper meta.json generation).
- `reviewers-audit.js` has a single ITEM_PROMPT (agentic-aware) that always frames the input as a diff to review.
- `/reviewers:audit` slash command already supports `--target`, `--agents`, `--preserve-as`, `--force`.
- CLAUDE.md "Known follow-ups" contains a `*(resolved on the framework-audit-pass branch, 2026-05-30)*` entry about gate quirks — keep it. There is NOT yet a "audit-prepare reuses pr_diff" entry that needs removing; the spec's DoD item 7 is moot. (If future drift adds one, the implementer should remove it; otherwise skip.)

The audit baseline dirs live under `docs/superpowers/eval-scorecards/audit-YYYY-MM-DD-<sha>/` and each contains a `meta.json` with at least `target`, `git_sha`, and `agents`. Today's only existing baseline is `audit-2026-05-30-2446de8/`.

---

### Task 1: New `framework_cli.review.baselines` module

**Goal:** A small, pure module that locates prior baselines on disk and extracts their metadata. Self-contained, easily unit-tested.

**Files:**
- Create: `src/framework_cli/review/baselines.py`
- Create: `tests/review/test_baselines.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/review/test_baselines.py` with:

```python
"""Tests for framework_cli.review.baselines (baseline discovery on disk)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework_cli.review.baselines import (
    find_latest_baseline_for_agent,
    is_baseline_dir,
    read_baseline_sha,
)


def _write_baseline(
    root: Path,
    name: str,
    target: str,
    git_sha: str,
    agents: list[str],
) -> Path:
    """Helper: create a baseline dir with a minimal meta.json."""
    d = root / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(
        json.dumps(
            {"target": target, "git_sha": git_sha, "agents": agents},
            indent=2,
            sort_keys=True,
        )
    )
    return d


def test_is_baseline_dir_true_for_valid_dir(tmp_path: Path) -> None:
    d = _write_baseline(tmp_path, "audit-2026-01-01-aaa", "framework", "abc1234", ["security"])
    assert is_baseline_dir(d) is True


def test_is_baseline_dir_false_for_missing_meta(tmp_path: Path) -> None:
    d = tmp_path / "no-meta"
    d.mkdir()
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_meta_without_git_sha(tmp_path: Path) -> None:
    d = tmp_path / "bad-meta"
    d.mkdir()
    (d / "meta.json").write_text('{"target": "framework"}')
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_unparseable_meta(tmp_path: Path) -> None:
    d = tmp_path / "broken-meta"
    d.mkdir()
    (d / "meta.json").write_text("not json {{{")
    assert is_baseline_dir(d) is False


def test_is_baseline_dir_false_for_file(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir"
    f.write_text("just a file")
    assert is_baseline_dir(f) is False


def test_read_baseline_sha_returns_git_sha(tmp_path: Path) -> None:
    d = _write_baseline(tmp_path, "audit-x", "framework", "deadbeef1234", ["x"])
    assert read_baseline_sha(d) == "deadbeef1234"


def test_read_baseline_sha_returns_none_for_missing_meta(tmp_path: Path) -> None:
    d = tmp_path / "no-meta"
    d.mkdir()
    assert read_baseline_sha(d) is None


def test_read_baseline_sha_returns_none_for_meta_without_git_sha(tmp_path: Path) -> None:
    d = tmp_path / "incomplete"
    d.mkdir()
    (d / "meta.json").write_text('{"target": "framework"}')
    assert read_baseline_sha(d) is None


def test_find_latest_baseline_for_agent_picks_newest_match(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "framework", "sha-old", ["security", "documentation"])
    _write_baseline(tmp_path, "audit-2026-03-01-c", "framework", "sha-new", ["security"])
    _write_baseline(tmp_path, "audit-2026-02-01-b", "framework", "sha-mid", ["security", "architecture"])

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-03-01-c"


def test_find_latest_baseline_for_agent_filters_by_target(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-fwk", "framework", "sha-f", ["security"])
    _write_baseline(tmp_path, "audit-2026-02-01-tpl", "project", "sha-p", ["security"])

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-fwk"


def test_find_latest_baseline_for_agent_filters_by_agent(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "framework", "sha-1", ["security"])
    _write_baseline(tmp_path, "audit-2026-02-01-b", "framework", "sha-2", ["architecture"])

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-a"


def test_find_latest_baseline_for_agent_returns_none_when_no_match(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "project", "sha-1", ["security"])

    assert find_latest_baseline_for_agent("framework", "security", tmp_path) is None


def test_find_latest_baseline_for_agent_returns_none_when_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    assert find_latest_baseline_for_agent("framework", "security", missing) is None


def test_find_latest_baseline_for_agent_skips_malformed_meta(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-good", "framework", "sha-good", ["security"])
    bad = tmp_path / "audit-2026-02-01-bad"
    bad.mkdir()
    (bad / "meta.json").write_text("not json {{{")

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-good"


def test_find_latest_baseline_for_agent_ignores_non_audit_dirs(tmp_path: Path) -> None:
    _write_baseline(tmp_path, "audit-2026-01-01-a", "framework", "sha-1", ["security"])
    # Tune scorecards live in the same parent — must NOT be picked up.
    tune = tmp_path / "2026-02-01-something"
    tune.mkdir()
    (tune / "meta.json").write_text(
        json.dumps({"target": "framework", "git_sha": "sha-tune", "agents": ["security"]})
    )

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-a"


def test_find_latest_baseline_for_agent_lexicographic_tiebreak(tmp_path: Path) -> None:
    # Two baselines with same prefix — lexicographic order is deterministic.
    _write_baseline(tmp_path, "audit-2026-01-01-aaa", "framework", "sha-aaa", ["security"])
    _write_baseline(tmp_path, "audit-2026-01-01-bbb", "framework", "sha-bbb", ["security"])

    result = find_latest_baseline_for_agent("framework", "security", tmp_path)
    assert result is not None
    assert result.name == "audit-2026-01-01-bbb"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/review/test_baselines.py -v
```

Expected: ALL fail with `ModuleNotFoundError: No module named 'framework_cli.review.baselines'`.

- [ ] **Step 3: Implement the module**

Create `src/framework_cli/review/baselines.py`:

```python
"""Discovery helpers for prior `/reviewers:audit` baseline directories.

Audit baselines live under `docs/superpowers/eval-scorecards/audit-*/`. Each
contains a `meta.json` with at least `target`, `git_sha`, and `agents`. These
helpers locate the newest baseline for a given (target, agent) and read its
SHA. Used by `audit-prepare` to compute per-agent delta diffs.
"""

from __future__ import annotations

import json
from pathlib import Path

_AUDIT_PREFIX = "audit-"


def is_baseline_dir(path: Path) -> bool:
    """True iff `path` is a directory with a readable meta.json containing a
    non-empty `git_sha`. Used to disambiguate `--since <ref>` from
    `--since <baseline-dir>`.
    """
    if not path.is_dir():
        return False
    meta_path = path / "meta.json"
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return bool(meta.get("git_sha"))


def read_baseline_sha(baseline_dir: Path) -> str | None:
    """Return the `git_sha` recorded in baseline_dir/meta.json, or None if
    the file is missing, unreadable, or missing the field.
    """
    meta_path = baseline_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    sha = meta.get("git_sha")
    return sha if isinstance(sha, str) and sha else None


def find_latest_baseline_for_agent(
    target: str, agent: str, scorecards_root: Path
) -> Path | None:
    """Return the newest baseline dir under `scorecards_root` whose target
    matches and whose `agents` list includes `agent`.

    Scan order: lexicographic dir name (deterministic). Newest = greatest
    name. Skips dirs that don't start with `audit-`, that aren't valid
    baseline dirs (`is_baseline_dir`), or whose meta.json doesn't list the
    requested agent. Returns None if no match.
    """
    if not scorecards_root.is_dir():
        return None
    matches: list[Path] = []
    for entry in scorecards_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith(_AUDIT_PREFIX):
            continue
        if not is_baseline_dir(entry):
            continue
        try:
            meta = json.loads((entry / "meta.json").read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("target") != target:
            continue
        agents = meta.get("agents") or []
        if not isinstance(agents, list) or agent not in agents:
            continue
        matches.append(entry)
    if not matches:
        return None
    matches.sort(key=lambda p: p.name)
    return matches[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/review/test_baselines.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 6: Update CLAUDE.md and stage**

Update the **Last updated** line on line 13 of `CLAUDE.md` with the current datetime (`date "+%Y-%m-%d %H:%M %Z"`) and a one-sentence note: `"Audit semantics Task 1 DONE: new framework_cli.review.baselines module + 14 unit tests for per-(target, agent) baseline discovery."`

Stage:

```bash
git add src/framework_cli/review/baselines.py tests/review/test_baselines.py CLAUDE.md
```

**STOP** — controller handles the gate + commit. The staged set is NOT review-relevant (none of `src/framework_cli/review/baselines.py`, `tests/review/test_baselines.py`, `CLAUDE.md` falls under `src/framework_cli/template/` / `src/framework_cli/review/agents/` / `tests/eval/fixtures/`), so gate should be noop and the commit lands cleanly. Report DONE.

---

### Task 2: Add `snapshot_seed` and `delta_diff` helpers to `review/diff.py`

**Goal:** Two small new helpers that produce the per-agent diff input for snapshot and delta modes respectively. Extends the existing `pr_diff` / `staged_diff` / `framework_diff` family.

**Files:**
- Modify: `src/framework_cli/review/diff.py`
- Modify: `tests/review/test_diff.py`

- [ ] **Step 1: Inspect current `diff.py` to match style**

```bash
cat src/framework_cli/review/diff.py
```

Note the existing module conventions (subprocess calls, capture_output, check=False return-of-stdout, etc.). Match those.

- [ ] **Step 2: Write the failing tests**

Append to `tests/review/test_diff.py`:

```python
def test_snapshot_seed_returns_empty_string(tmp_path: Path) -> None:
    """snapshot_seed is intentionally empty for bundle agents — the bundled
    context block carries the source files, no diff seed needed."""
    from framework_cli.review.diff import snapshot_seed

    assert snapshot_seed("framework", tmp_path) == ""


def test_snapshot_seed_returns_empty_for_any_target(tmp_path: Path) -> None:
    """Behavior is the same for project target — empty seed; bundled context
    does the work."""
    from framework_cli.review.diff import snapshot_seed

    assert snapshot_seed("project", tmp_path) == ""


def test_delta_diff_returns_diff_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """delta_diff calls `git diff <base_sha>...HEAD` and returns its stdout."""
    import subprocess

    from framework_cli.review.diff import delta_diff

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        result = subprocess.CompletedProcess(args=args, returncode=0)
        result.stdout = "diff --git a/foo b/foo\n+++ added line\n"
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = delta_diff("abc1234")
    assert "diff --git" in out
    assert captured["args"] == ["git", "diff", "abc1234...HEAD"]


def test_delta_diff_raises_when_ref_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """delta_diff raises a ValueError with a clear message when git diff fails
    (e.g., bad ref). Callers translate that into a CLI exit."""
    import subprocess

    from framework_cli.review.diff import delta_diff

    def fake_run(args, **kwargs):
        result = subprocess.CompletedProcess(args=args, returncode=128)
        result.stdout = ""
        result.stderr = "fatal: bad revision 'nope...HEAD'\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError) as exc:
        delta_diff("nope")
    assert "nope" in str(exc.value)
    assert "bad revision" in str(exc.value).lower() or "is that ref reachable" in str(exc.value).lower()
```

(If `tests/review/test_diff.py` doesn't import `Path` or `pytest`, add those imports at the top.)

- [ ] **Step 3: Run new tests to verify they fail**

```bash
uv run pytest tests/review/test_diff.py -k "snapshot_seed or delta_diff" -v
```

Expected: 4 FAILs with `ImportError: cannot import name 'snapshot_seed'` (and similar for `delta_diff`).

- [ ] **Step 4: Add the helpers**

Append to `src/framework_cli/review/diff.py` (after the existing `framework_diff` function):

```python
def snapshot_seed(target: str, root: Path) -> str:
    """Return the diff seed for audit snapshot mode.

    For bundle agents this is always empty: the per-agent bundled context block
    (driven by ContextPolicy.context_globs) already carries the relevant source
    files, so no diff is needed. Agentic agents get a root_dir at the workflow
    layer and explore the tree via their tools; they also don't need a diff
    seed here.

    Returns an empty string. The `target` and `root` parameters are kept for
    symmetry with `delta_diff(base_sha)` and to allow future extension (e.g.,
    target-specific synthetic diffs) without breaking the call sites.
    """
    del target, root  # currently unused; kept for symmetry and future extension
    return ""


def delta_diff(base_sha: str) -> str:
    """Return ``git diff <base_sha>...HEAD`` as a unified diff string.

    Raises ValueError when `git diff` exits non-zero (e.g., ref unreachable).
    The CLI layer translates this into a clear ``typer.Exit(2)`` with the
    git error attached.
    """
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (result.stderr or "").strip() or f"unable to compute diff for {base_sha}...HEAD"
        raise ValueError(f"delta_diff({base_sha!r}) failed: {msg}. Is that ref reachable?")
    return result.stdout
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/review/test_diff.py -v
```

Expected: all `test_diff.py` tests pass (the 4 new ones plus any existing).

- [ ] **Step 6: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 7: Update CLAUDE.md and stage**

Update **Last updated** with current datetime and note: `"Task 2 DONE: snapshot_seed() + delta_diff() helpers in review/diff.py."`

```bash
git add src/framework_cli/review/diff.py tests/review/test_diff.py CLAUDE.md
```

**STOP** — staged set is not review-relevant; gate noop. Report DONE.

---

### Task 3: New `_resolve_audit_base` helper in `cli.py`

**Goal:** A single helper that — given an agent, the target, the two flag values, and the scorecards root — decides `(review_mode, base_sha, base_baseline_name)`. Testable in isolation; callers use it to build per-agent work-items.

**Files:**
- Modify: `src/framework_cli/cli.py` (add helper + its import; do NOT yet change `_emit_audit_prep` or `audit_prepare` signatures — that's Task 4)
- Modify: `tests/test_cli.py` (or extract to `tests/review/test_audit_base.py` if you prefer — your call; the existing audit tests are in `tests/test_cli.py` so adding alongside them is fine)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (near the existing `test_audit_prepare_*` block):

```python
def test_resolve_audit_base_snapshot_flag_forces_snapshot(tmp_path):
    """snapshot_flag=True → ("snapshot", None, None) regardless of available baselines."""
    from framework_cli.cli import _resolve_audit_base

    # Seed a matching baseline that would otherwise be picked up.
    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=True,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None


def test_resolve_audit_base_since_as_baseline_dir_delta_when_agent_in_baseline(tmp_path):
    """since_arg points at a baseline dir AND agent is in that baseline → delta vs its SHA."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security", "architecture"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=str(bd),
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "shaX"
    assert name == "audit-2026-01-01-x"


def test_resolve_audit_base_since_as_baseline_dir_snapshot_fallback_when_agent_not_in_baseline(tmp_path):
    """since_arg points at a baseline dir but agent wasn't in it → snapshot fallback."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-01-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaX", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "documentation",  # not in the baseline
        "framework",
        snapshot_flag=False,
        since_arg=str(bd),
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None


def test_resolve_audit_base_since_as_ref_resolves_via_rev_parse(tmp_path, monkeypatch):
    """since_arg looks like a ref (not a baseline dir) → resolve via git rev-parse,
    use the resolved SHA for every agent (no per-agent presence question)."""
    import subprocess

    from framework_cli.cli import _resolve_audit_base

    def fake_run(args, **kwargs):
        # Pretend "v1.0" resolves to "abc123..."
        if args[:3] == ["git", "rev-parse", "--verify"]:
            assert args[3] == "v1.0^{commit}"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="abc1234567890\n", stderr="")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg="v1.0",
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "abc1234567890"
    assert name is None  # ref form has no baseline-dir name


def test_resolve_audit_base_since_as_bad_ref_raises(tmp_path, monkeypatch):
    """since_arg is a ref but git rev-parse fails → ValueError (caller exits 2)."""
    import subprocess

    from framework_cli.cli import _resolve_audit_base

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=128, stdout="", stderr="fatal: bad revision")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ValueError) as exc:
        _resolve_audit_base(
            "security",
            "framework",
            snapshot_flag=False,
            since_arg="nope",
            scorecards_root=tmp_path,
        )
    assert "nope" in str(exc.value)


def test_resolve_audit_base_autodiscover_finds_latest_baseline(tmp_path):
    """No flags → auto-discover the newest baseline that included this agent."""
    from framework_cli.cli import _resolve_audit_base

    bd = tmp_path / "audit-2026-03-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaNew", "agents": ["security"]}'
    )

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "delta"
    assert sha == "shaNew"
    assert name == "audit-2026-03-01-x"


def test_resolve_audit_base_autodiscover_falls_back_to_snapshot_when_no_baseline(tmp_path):
    """No flags + no prior baseline for this agent → snapshot fallback."""
    from framework_cli.cli import _resolve_audit_base

    mode, sha, name = _resolve_audit_base(
        "security",
        "framework",
        snapshot_flag=False,
        since_arg=None,
        scorecards_root=tmp_path,
    )
    assert mode == "snapshot"
    assert sha is None
    assert name is None
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -k "resolve_audit_base" -v
```

Expected: 7 FAILs with `ImportError: cannot import name '_resolve_audit_base'`.

- [ ] **Step 3: Implement `_resolve_audit_base`**

In `src/framework_cli/cli.py`, near the other audit-related helpers (around `_emit_audit_prep`), add:

```python
def _resolve_audit_base(
    agent: str,
    target: str,
    *,
    snapshot_flag: bool,
    since_arg: str | None,
    scorecards_root: Path,
) -> tuple[str, str | None, str | None]:
    """Return (review_mode, base_sha, base_baseline_name) for one agent.

    review_mode is "snapshot" or "delta".
    base_sha is the commit to diff HEAD against (None for snapshot).
    base_baseline_name is the dated-dir name of the resolved baseline, if any.

    Cases:
      * snapshot_flag → ("snapshot", None, None) — forced.
      * since_arg is a baseline dir → per-agent: ("delta", sha, name) if agent
        was in that baseline, else ("snapshot", None, None) (fallback).
      * since_arg is a ref/SHA → ("delta", resolved_sha, None); raises
        ValueError if the ref doesn't resolve.
      * No flags → auto-discover the newest baseline for this (target, agent);
        ("delta", sha, name) if found, else ("snapshot", None, None) (fallback).
    """
    from framework_cli.review.baselines import (
        find_latest_baseline_for_agent,
        is_baseline_dir,
        read_baseline_sha,
    )

    if snapshot_flag:
        return ("snapshot", None, None)

    if since_arg:
        since_path = Path(since_arg)
        if is_baseline_dir(since_path):
            meta = json.loads((since_path / "meta.json").read_text())
            agents_in_baseline = meta.get("agents") or []
            if agent in agents_in_baseline:
                sha = read_baseline_sha(since_path)
                return ("delta", sha, since_path.name)
            return ("snapshot", None, None)
        # Treat as a ref/SHA. Resolve via git rev-parse.
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{since_arg}^{{commit}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            msg = (result.stderr or "").strip() or f"could not resolve ref {since_arg!r}"
            raise ValueError(f"{msg}. Is that ref reachable?")
        return ("delta", result.stdout.strip(), None)

    # Auto-discover.
    found = find_latest_baseline_for_agent(target, agent, scorecards_root)
    if found is None:
        return ("snapshot", None, None)
    sha = read_baseline_sha(found)
    return ("delta", sha, found.name)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "resolve_audit_base" -v
```

Expected: 7 passed.

- [ ] **Step 5: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 6: Update CLAUDE.md and stage**

Update **Last updated** with current datetime and note: `"Task 3 DONE: _resolve_audit_base helper (mode/base_sha/base_baseline per agent across 4 cases) + 7 unit tests."`

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```

**STOP** — staged set is not review-relevant; gate noop. Report DONE.

---

### Task 4: Wire `audit-prepare` flags + per-agent work-items

**Goal:** `audit-prepare` accepts `--snapshot` / `--since`, enforces mutual exclusion, and `_emit_audit_prep` uses `_resolve_audit_base` to compute per-agent `review_mode` / `base_sha` / `base_baseline`. Each work-item now carries these fields. The `system_blocks[0]` diff text is built from `delta_diff(base_sha)` when delta, or omitted entirely when snapshot.

**Files:**
- Modify: `src/framework_cli/cli.py` (`audit_prepare` signature + `_emit_audit_prep` body)
- Modify: `tests/test_cli.py` (new integration tests; update one existing test that relied on `pr_diff()` being the source)

- [ ] **Step 1: Identify existing call site changes**

```bash
grep -n "def audit_prepare\|def _emit_audit_prep\|_review_diff()" src/framework_cli/cli.py
```

Note line numbers. The `diff = _review_diff()` line in `_emit_audit_prep` is the one being replaced with per-agent resolution.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_audit_prepare_snapshot_flag_produces_snapshot_items(tmp_path, monkeypatch):
    """--snapshot → every work-item has review_mode='snapshot' and an empty/missing diff."""
    import framework_cli.cli as cli_mod

    # Force auto-discovery to find nothing (irrelevant for --snapshot but safe).
    monkeypatch.setattr(cli_mod, "_default_scorecards_root", lambda: tmp_path)

    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
            "--snapshot",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = _json.loads(result.stdout)
    assert len(manifest["work_items"]) == 1
    wi = manifest["work_items"][0]
    assert wi["review_mode"] == "snapshot"
    assert wi.get("base_sha") is None
    assert wi.get("base_baseline") is None


def test_audit_prepare_since_with_sha_produces_delta(tmp_path, monkeypatch):
    """--since <SHA> (not a baseline dir) → every item delta against that SHA."""
    import subprocess

    import framework_cli.cli as cli_mod

    def fake_rev_parse(args, **kwargs):
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="deadbeef\n", stderr="")
        # Other subprocess calls (like git diff inside delta_diff) — return empty.
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_rev_parse)
    monkeypatch.setattr(cli_mod, "_default_scorecards_root", lambda: tmp_path)

    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
            "--since", "abc123",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = _json.loads(result.stdout)
    wi = manifest["work_items"][0]
    assert wi["review_mode"] == "delta"
    assert wi["base_sha"] == "deadbeef"
    assert wi.get("base_baseline") is None  # ref form, no baseline name


def test_audit_prepare_snapshot_and_since_mutually_exclusive(tmp_path, monkeypatch):
    """Passing both --snapshot and --since → exit 2 with a clear message."""
    import framework_cli.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_default_scorecards_root", lambda: tmp_path)

    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
            "--snapshot",
            "--since", "abc123",
        ],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output.lower()


def test_audit_prepare_autodiscover_picks_latest_baseline(tmp_path, monkeypatch):
    """No flags + a matching baseline exists → delta against its SHA."""
    import subprocess

    import framework_cli.cli as cli_mod

    bd = tmp_path / "audit-2026-03-01-x"
    bd.mkdir()
    (bd / "meta.json").write_text(
        '{"target": "framework", "git_sha": "shaNew", "agents": ["security"]}'
    )

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(cli_mod, "_default_scorecards_root", lambda: tmp_path)

    result = runner.invoke(
        app,
        [
            "audit-prepare",
            "--target", "framework",
            "--agent", "security",
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = _json.loads(result.stdout)
    wi = manifest["work_items"][0]
    assert wi["review_mode"] == "delta"
    assert wi["base_sha"] == "shaNew"
    assert wi["base_baseline"] == "audit-2026-03-01-x"
```

- [ ] **Step 3: Run new tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -k "audit_prepare_snapshot or audit_prepare_since or audit_prepare_autodiscover" -v
```

Expected: 4 FAILs — the `--snapshot` / `--since` options don't exist yet; work-items don't have `review_mode`.

- [ ] **Step 4: Add the flags to `audit_prepare` and wire the helper**

In `src/framework_cli/cli.py`, modify the `audit_prepare` command:

```python
@app.command(name="audit-prepare")
def audit_prepare(
    agent: list[str] = typer.Option(
        None,
        "--agent",
        help=(
            "Restrict to this agent. Repeat for multiple agents. "
            "Omit for all active agents for the target."
        ),
    ),
    target: str = typer.Option(
        "",
        "--target",
        help="'framework' or 'project' (default: auto-detect).",
    ),
    output_dir: str = typer.Option(
        "",
        "--output-dir",
        help="Output dir for finalize (echoed in the prep manifest).",
    ),
    split_to: str = typer.Option(
        "",
        "--split-to",
        help=(
            "If set, write a small index.json + per-item items/item-NNNN.json under "
            "DIR (in addition to the stdout manifest). Lets the Workflow tool be "
            "invoked with a tiny args payload instead of a multi-MB inline manifest. "
            "Idempotent: an existing DIR is cleared first."
        ),
    ),
    snapshot: bool = typer.Option(
        False,
        "--snapshot",
        help=(
            "Force every agent into snapshot mode (no diff seed; bundled context "
            "does the work). Skips per-agent baseline auto-discovery."
        ),
    ),
    since: str = typer.Option(
        "",
        "--since",
        help=(
            "Force delta mode against a chosen anchor — either a git ref/SHA "
            "(all agents diff HEAD vs that ref) or a baseline directory under "
            "docs/superpowers/eval-scorecards/ (per-agent: agents in that baseline "
            "diff against its SHA; agents not in the baseline fall back to snapshot)."
        ),
    ),
) -> None:
    """Emit the audit-mode work-item manifest (current code, one item per agent).

    Output is JSON on stdout; consumed by /reviewers:audit. When ``--split-to DIR``
    is set, also writes a split-manifest layout (``index.json`` + ``items/item-NNNN.json``)
    under DIR for the Workflow tool to consume via ``{indexPath, itemsDir}`` args.

    By default, each agent's mode is auto-discovered: if a prior baseline under
    ``docs/superpowers/eval-scorecards/audit-*/`` exists for this (target, agent),
    the agent runs in delta mode (diff vs that baseline's git_sha). Otherwise the
    agent falls back to snapshot mode (with a visible log line per agent).
    """
    if snapshot and since:
        typer.echo(
            "audit-prepare: --snapshot and --since are mutually exclusive",
            err=True,
        )
        raise typer.Exit(2)
    _emit_audit_prep(agent or [], target, output_dir, split_to, snapshot, since or None)
```

Also add a module-level helper for the scorecards root (so tests can monkeypatch it):

```python
def _default_scorecards_root() -> Path:
    """The directory under which preserved audit baselines live."""
    return Path("docs/superpowers/eval-scorecards")
```

Update `_emit_audit_prep`'s signature and body:

```python
def _emit_audit_prep(
    selected_agents: list[str],
    target_arg: str,
    output_dir: str,
    split_to: str = "",
    snapshot_flag: bool = False,
    since_arg: str | None = None,
) -> None:
    """Emit the audit-mode manifest to stdout (always) plus, when ``split_to`` is
    non-empty, an on-disk split-manifest layout under ``split_to``.

    Each work-item now carries ``review_mode`` / ``base_sha`` / ``base_baseline``
    fields, resolved per-agent via :func:`_resolve_audit_base`. The
    ``system_blocks[0]`` diff text is :func:`delta_diff` output when
    ``review_mode == "delta"``, or the (empty) :func:`snapshot_seed` output
    when ``review_mode == "snapshot"``.

    The split layout exists so the Workflow tool can be invoked with a tiny
    ``{indexPath, itemsDir}`` args payload instead of a multi-MB inline manifest
    (the documented ~1.76 MB Workflow-args ceiling). Mirrors ``_emit_tune_prep``
    and ``_emit_gate_prep``.
    """
    import shutil

    from framework_cli.review.context import FRAMEWORK_AGENTS
    from framework_cli.review.diff import delta_diff, snapshot_seed
    from framework_cli.source import read_batteries

    target = _detect_audit_target(target_arg)
    if target == "framework":
        all_agents = sorted(FRAMEWORK_AGENTS)
    else:
        all_agents = active_agents("pull_request", read_batteries(Path(".")))
    # Dedupe selected agents while preserving insertion order.
    selected = list(dict.fromkeys(selected_agents))
    if selected:
        unknown = [a for a in selected if a not in all_agents]
        if unknown:
            typer.echo(
                f"audit-prepare: unknown agent(s): {', '.join(unknown)}. "
                f"Valid agents for target '{target}': {', '.join(sorted(all_agents))}",
                err=True,
            )
            raise typer.Exit(2)
        agents_set = selected
    else:
        agents_set = all_agents

    scorecards_root = _default_scorecards_root()
    work_items: list[dict] = []
    root = Path.cwd()
    for a in agents_set:
        try:
            mode, base_sha, base_baseline = _resolve_audit_base(
                a,
                target,
                snapshot_flag=snapshot_flag,
                since_arg=since_arg,
                scorecards_root=scorecards_root,
            )
        except ValueError as exc:
            typer.echo(f"audit-prepare: {exc}", err=True)
            raise typer.Exit(2) from exc

        if mode == "delta":
            try:
                diff = delta_diff(base_sha)  # type: ignore[arg-type]
            except ValueError as exc:
                typer.echo(f"audit-prepare: {exc}", err=True)
                raise typer.Exit(2) from exc
        else:
            diff = snapshot_seed(target, root)
            # Visible log for the fallback / forced-snapshot path.
            typer.echo(f"audit-prepare: {a} running in snapshot mode", err=True)

        wi = _build_audit_work_item_with_mode(a, target, diff, root, mode, base_sha, base_baseline)
        work_items.append(wi)

    manifest = {
        "mode": "audit",
        "target": target,
        "agents_set": agents_set,
        "work_items": work_items,
        "output_dir": output_dir or "",
    }

    # [Existing split-to block stays as-is; it just writes the same work_items
    #  to disk. The new fields on each work-item carry through.]
    if split_to:
        # ... existing block unchanged
        pass  # IMPLEMENTER: keep the existing implementation here verbatim

    typer.echo(json.dumps(manifest, indent=2))
```

You'll need to add `_build_audit_work_item_with_mode` (or update the existing `_build_audit_work_item` to accept the new fields). Look at the current signature first:

```bash
grep -n "_build_audit_work_item" src/framework_cli/cli.py
```

If it exists, extend it with `review_mode`, `base_sha`, `base_baseline` parameters and add them to the returned dict alongside the existing fields. If it doesn't (the audit work-item is built inline today), factor it into a small helper. Either way, the resulting work-item dict must include:

```python
{
    "agent": <name>,
    "subagent_type": <general-purpose or agentic type>,
    "model": <claude-sonnet-4-6 or claude-opus-4-8>,
    "system_blocks": [{"text": <diff or empty>}, {"text": <bundled context>}, ...],
    "user_message": <existing>,
    "review_mode": "snapshot" | "delta",
    "base_sha": <sha or None>,
    "base_baseline": <dir name or None>,
}
```

The two new fields appear AT THE TOP LEVEL of the work-item (not nested under `meta`) so the workflow's per-item dispatch can branch on them without parsing nested structures.

- [ ] **Step 5: Update one existing test that may have relied on `pr_diff()`**

```bash
grep -n "test_audit_prepare_split_to" tests/test_cli.py
```

The existing `test_audit_prepare_split_to_writes_index_and_items` monkeypatches `_review_diff` to return `"diff content"`. After this task, the snapshot path is the default — `_review_diff` isn't called from `_emit_audit_prep`. Either:
- Update the test to add `--snapshot` (so `_review_diff` doesn't need patching at all and the diff is empty), OR
- Update the test to pass `--since some-sha` (and patch `delta_diff` to return `"diff content"`).

Pick whichever fits the test's intent. For the existing test (which just verifies the split layout structure), `--snapshot` is the simpler choice and keeps the test focused.

Apply the same pattern to `test_audit_prepare_split_to_clears_existing_dir` if it relied on `_review_diff` monkeypatching.

- [ ] **Step 6: Run all audit-prepare tests**

```bash
uv run pytest tests/test_cli.py -k "audit_prepare" -v
```

Expected: all pass — the 4 new mode-resolution tests, the original audit_prepare tests (with updated patching), and the split-to tests.

- [ ] **Step 7: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 8: Update CLAUDE.md and stage**

Update **Last updated** with current datetime and note: `"Task 4 DONE: audit-prepare wires --snapshot/--since; per-agent work-items now carry review_mode/base_sha/base_baseline; _emit_audit_prep uses delta_diff/snapshot_seed instead of pr_diff."`

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```

**STOP** — staged set is not review-relevant; gate noop. Report DONE.

---

### Task 5: Per-item prompt branching in `reviewers-audit.js`

**Goal:** The workflow inspects each item's `review_mode` and dispatches one of two distinct prompt templates. Mirror the change in the template `.jinja`.

**Files:**
- Modify: `.claude/workflows/reviewers-audit.js`
- Modify: `src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja`

- [ ] **Step 1: Read the current workflow**

```bash
cat .claude/workflows/reviewers-audit.js
```

Identify the single `ITEM_PROMPT` constant and the per-item dispatch loop. The change: replace the single template with two templates and select based on `item.review_mode`.

- [ ] **Step 2: Update the workflow**

In `.claude/workflows/reviewers-audit.js`, replace the single `ITEM_PROMPT = (path) => \`...\`` block with two named templates and a selector. Roughly:

```javascript
const DELTA_ITEM_PROMPT = (path, baseSha, baseBaselineName) => `
You are acting as a code reviewer. Your inputs live in a JSON file on disk.

This is a DELTA review: the diff below is the change between the prior baseline
(commit ${baseSha}${baseBaselineName ? `, recorded in baseline ${baseBaselineName}` : ''}) and the current HEAD. Focus on what is new or
changed; the rest of the codebase has been reviewed previously and is out of
scope for this run.

1. Read the JSON file at ${path}. It has fields:
   - system_blocks: array of {text} — these together form the system context for the reviewer
     (the unified diff vs the prior baseline, optionally bundled context files, and the reviewer's prompt).
   - user_message: string — the final user instruction (typically "Return your findings as a JSON array only.").
   - tools_allowed: array of strings or null. If non-null, use ONLY those tools.
   - root_dir: string — when present, all tool paths should be ABSOLUTE paths starting with this root.

2. Concatenate the text of every system_block with double newlines as your effective system context.
   Treat this as your operating identity and instructions.

3. Execute the review as that reviewer would. If tools_allowed is non-null (an agentic reviewer),
   you may use the listed tools to explore the code under root_dir; use absolute paths only.

4. Return a JSON object: {"findings": [...]} where findings is the JSON array the reviewer would
   produce (each finding has path/line/severity/message and optional suggestion). If no issues,
   return {"findings": []}. The response will be schema-validated.
`

const SNAPSHOT_ITEM_PROMPT = (path) => `
You are acting as a code reviewer. Your inputs live in a JSON file on disk.

This is a SNAPSHOT review: there is no prior baseline to diff against, so review
the current code from scratch. For bundle reviewers, the bundled context files
in system_blocks are the code to review. For agentic reviewers, explore the code
under root_dir using the listed tools.

1. Read the JSON file at ${path}. It has fields:
   - system_blocks: array of {text} — these together form the system context for the reviewer.
     For snapshot mode, the first block (the diff) is empty/missing; the bundled context block
     (and/or root_dir for agentic reviewers) carries the code to review.
   - user_message: string — the final user instruction.
   - tools_allowed: array of strings or null. If non-null, use ONLY those tools.
   - root_dir: string — when present, all tool paths should be ABSOLUTE paths starting with this root.

2. Concatenate the text of every system_block with double newlines as your effective system context.
   Treat this as your operating identity and instructions.

3. Execute the review as that reviewer would. If tools_allowed is non-null (an agentic reviewer),
   you may use the listed tools to explore the code under root_dir; use absolute paths only.

4. Return a JSON object: {"findings": [...]} where findings is the JSON array the reviewer would
   produce (each finding has path/line/severity/message and optional suggestion). If no issues,
   return {"findings": []}. The response will be schema-validated.
`
```

Then in the per-item dispatch loop, branch:

```javascript
const itemPrompt = item.review_mode === 'delta'
  ? DELTA_ITEM_PROMPT(itemPath, item.base_sha, item.base_baseline)
  : SNAPSHOT_ITEM_PROMPT(itemPath)
```

Use `itemPrompt` as the `prompt` argument to the per-item `agent()` call.

If the current code reads `item.review_mode` and the field is missing (older split-manifest from before this change), default to the snapshot template (safe fallback).

- [ ] **Step 3: Mirror to the template `.jinja`**

```bash
cp .claude/workflows/reviewers-audit.js src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja
```

(The two files are byte-identical mirrors today; if the implementer's prior cleanup added any Jinja interpolations to the template, preserve them — but in our current state the cp is correct.)

- [ ] **Step 4: Smoke-test the workflow change**

There aren't existing unit tests for the workflow .js itself, but we can verify the workflow loads + dispatches correctly by exercising the audit-finalize path with a sample result. Run the full test suite to confirm nothing breaks:

```bash
uv run pytest -q --ignore=tests/acceptance
```

Expected: all green.

- [ ] **Step 5: Quality gate**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 6: Update CLAUDE.md and stage**

Update **Last updated** with current datetime and note: `"Task 5 DONE: reviewers-audit.js (+ template mirror) branches per-item prompt on review_mode (snapshot vs delta templates)."`

```bash
git add .claude/workflows/reviewers-audit.js \
        src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja \
        CLAUDE.md
```

**STOP** — staged set IS review-relevant (`src/framework_cli/template/.claude/workflows/reviewers-audit.js.jinja` lives under `template/`). The gate will fire 18 agents on this commit. Controller handles gate + commit (expect 0 HIGH findings; documentation may surface INFO/LOW that gets the same `--no-verify` treatment as prior branch commits). Report DONE.

---

### Task 6: `audit-finalize` writes per-agent `meta.json`

**Goal:** `audit-finalize` produces a `meta.json` in `out_dir` with run-level metadata + a `per_agent` block recording each agent's `review_mode`, `base_sha`, `base_baseline`. Per-agent finding records also gain these fields.

**Files:**
- Modify: `src/framework_cli/cli.py` (`_finalize_audit` body)
- Modify: `tests/test_cli.py` (extend existing audit-finalize test + add 1 new test)

- [ ] **Step 1: Find `_finalize_audit` and the existing test**

```bash
grep -n "def _finalize_audit\|test_audit_finalize" src/framework_cli/cli.py tests/test_cli.py
```

Read the current `_finalize_audit` body. Today it writes `findings/<agent>.json` and `audit-report.md` but NOT `meta.json`. The existing audit-finalize test (`test_audit_finalize_writes_audit_report` or similar) checks the existing outputs.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_audit_finalize_writes_per_agent_meta_json(tmp_path):
    """audit-finalize writes a meta.json with run-level + per_agent fields."""
    out_dir = tmp_path / "latest"
    out_dir.mkdir()

    results_path = tmp_path / "results.json"
    results_path.write_text(_json.dumps({
        "results": [
            {
                "agent": "security",
                "findings": [],
                "review_mode": "delta",
                "base_sha": "shaX",
                "base_baseline": "audit-2026-01-01-aaa",
                "raw_text": "[]",
            },
            {
                "agent": "architecture",
                "findings": [],
                "review_mode": "snapshot",
                "base_sha": None,
                "base_baseline": None,
                "raw_text": "[]",
            },
        ],
        "meta": {
            "mode": "audit",
            "target": "framework",
            "agents_set": ["security", "architecture"],
        },
    }))

    result = runner.invoke(
        app,
        [
            "audit-finalize",
            "--results", str(results_path),
            "--out-dir", str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    meta_path = out_dir / "meta.json"
    assert meta_path.is_file()
    meta = _json.loads(meta_path.read_text())

    # Run-level fields
    assert meta["target"] == "framework"
    assert meta["agents"] == ["security", "architecture"]
    assert "git_sha" in meta
    assert "timestamp" in meta

    # Per-agent traceability
    assert meta["per_agent"]["security"]["review_mode"] == "delta"
    assert meta["per_agent"]["security"]["base_sha"] == "shaX"
    assert meta["per_agent"]["security"]["base_baseline"] == "audit-2026-01-01-aaa"
    assert meta["per_agent"]["architecture"]["review_mode"] == "snapshot"
    assert meta["per_agent"]["architecture"]["base_sha"] is None
    assert meta["per_agent"]["architecture"]["base_baseline"] is None

    # Per-agent findings records also include the fields
    sec_record = _json.loads((out_dir / "findings" / "security.json").read_text())
    assert sec_record["review_mode"] == "delta"
    assert sec_record["base_sha"] == "shaX"
```

- [ ] **Step 3: Run the new test to verify it fails**

```bash
uv run pytest tests/test_cli.py -k "test_audit_finalize_writes_per_agent_meta_json" -v
```

Expected: FAIL — `meta_path.is_file()` is False (audit-finalize doesn't write meta.json today).

- [ ] **Step 4: Update `_finalize_audit`**

In `src/framework_cli/cli.py`, extend `_finalize_audit` to:
1. Write each per-agent record with `review_mode`, `base_sha`, `base_baseline` carried from the workflow result.
2. After writing all per-agent records, compose and write `meta.json`.

The added meta.json composition (after the existing record-write + audit-report.md write):

```python
from datetime import datetime, timezone

# Determine the current git SHA (full, not short — for future use).
sha_result = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    capture_output=True, text=True, check=False,
)
git_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""

per_agent: dict[str, dict] = {}
for r in records:
    per_agent[r["agent"]] = {
        "review_mode": r.get("review_mode", "snapshot"),
        "base_sha": r.get("base_sha"),
        "base_baseline": r.get("base_baseline"),
    }

meta_out = {
    "target": meta_in.get("target", ""),
    "git_sha": git_sha,
    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "agents": [r["agent"] for r in records],
    "per_agent": per_agent,
}
(out / "meta.json").write_text(json.dumps(meta_out, indent=2, sort_keys=True))
```

For per-agent records, update the existing write loop to include the new fields:

```python
for r in records:
    record = {
        "agent": r["agent"],
        "findings": r.get("findings", []),
        "raw_text": r.get("raw_text", ""),
        "review_mode": r.get("review_mode", "snapshot"),
        "base_sha": r.get("base_sha"),
        "base_baseline": r.get("base_baseline"),
        # ... preserve other existing fields (latency_ms, stop_reason, turns, tool_calls)
    }
    record_path = findings_dir / f"{r['agent']}.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    record_path.chmod(0o600)  # consistent with the gate finalize tightening
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -k "audit_finalize" -v
```

Expected: the new test passes; existing audit-finalize tests still pass.

- [ ] **Step 6: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 7: Update CLAUDE.md and stage**

Update **Last updated** with current datetime and note: `"Task 6 DONE: audit-finalize writes meta.json (run-level + per_agent block recording review_mode/base_sha/base_baseline per agent); per-agent finding records also include those fields."`

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```

**STOP** — staged set is not review-relevant; gate noop. Report DONE.

---

### Task 7: `/reviewers:audit` slash command + final cleanup

**Goal:** Forward `--snapshot` / `--since` from the slash command to `audit-prepare`. Mirror in the template `.jinja`. Remove the stale "audit-prepare reuses pr_diff" entry from CLAUDE.md Known follow-ups (if any), update the meta-plan if needed.

**Files:**
- Modify: `.claude/commands/reviewers/audit.md`
- Modify: `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read the current slash command**

```bash
cat .claude/commands/reviewers/audit.md
```

Identify the **Inputs** section and the audit-prepare invocation in step 2.

- [ ] **Step 2: Add the new Inputs**

Append to the **Inputs** list (after the existing `--force` bullet):

```markdown
- Optional flag: `--snapshot` — force every agent into snapshot mode (no diff seed; bundled context does the work). Skips per-agent baseline auto-discovery.
- Optional flag: `--since <ref-or-dir>` — force delta mode against a chosen anchor. Either a git ref/SHA (every agent diffs HEAD vs that ref) or a baseline directory under `docs/superpowers/eval-scorecards/` (per-agent: agents that were in that baseline diff against its `git_sha`; agents not in that baseline fall back to snapshot). Mutually exclusive with `--snapshot`.
```

Also extend the parsing step (step 1) to bind `SNAPSHOT` and `SINCE`:

```markdown
1. **Parse the user's arguments**. Extract the optional positional agent name, `--target`, `--agents`, `--preserve-as`, `--force`, `--snapshot`, and `--since`. Bind the parsed values to shell vars `AGENT`, `AGENTS`, `TARGET`, `PRESERVE_AS`, `FORCE`, `SNAPSHOT`, `SINCE` (empty if not supplied) so the snippets below can reference them.
```

- [ ] **Step 3: Update the audit-prepare invocation**

In step 2's bash snippet, add the two new flags. Find the existing block and replace with:

```bash
   AGENT_FLAGS=""
   if [ -n "$AGENTS" ]; then
     IFS=',' read -ra ARR <<< "$AGENTS"
     for a in "${ARR[@]}"; do AGENT_FLAGS="$AGENT_FLAGS --agent $a"; done
   elif [ -n "$AGENT" ]; then
     AGENT_FLAGS="--agent $AGENT"
   fi
   rm -rf /tmp/reviewers-audit-prep-split 2>/dev/null
   uv run framework audit-prepare \
     ${TARGET:+--target "$TARGET"} \
     $AGENT_FLAGS \
     ${SNAPSHOT:+--snapshot} \
     ${SINCE:+--since "$SINCE"} \
     --output-dir .framework/audit/latest \
     --split-to /tmp/reviewers-audit-prep-split > /tmp/reviewers-audit-prep.json
```

(The `${SNAPSHOT:+--snapshot}` form is shell idiom for "if `SNAPSHOT` is non-empty, expand to `--snapshot`, else expand to nothing.")

- [ ] **Step 4: Update the frontmatter description**

Extend the YAML frontmatter `description:` to mention the new flags:

```yaml
---
description: Hygiene review — run review agents against current code state via local subagents (no paid API). Auto-detects framework vs project target. Optional positional arg = single agent shortcut; --agents a,b,c for a subset; --snapshot (force all-snapshot) or --since <ref-or-dir> (force all-delta against ref or baseline-dir); --preserve-as <dir> [--force] to snapshot the run as a dated baseline under docs/superpowers/eval-scorecards/audit-…/.
---
```

- [ ] **Step 5: Mirror to the template `.jinja`**

Apply the same three edits (Inputs, step 1 binding, step 2 bash snippet, frontmatter) to `src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja`. Verify they stay byte-identical to the live `.claude/` copy (modulo any pre-existing Jinja interpolations).

- [ ] **Step 6: Check CLAUDE.md Known follow-ups for any stale "audit-prepare reuses pr_diff" entry**

```bash
grep -n "audit-prepare reuses pr_diff\|HEAD~1.*audit\|audit.*HEAD~1" CLAUDE.md
```

If a Known follow-ups bullet about audit-prepare's diff source exists, replace it with a resolved entry:

```markdown
- *(resolved on the audit-semantics work, 2026-05-30)* **audit-prepare diff source.** Was `pr_diff()` (`HEAD~1...HEAD`) which made audit review the prior commit's diff instead of the current code state. Fixed by introducing snapshot-primary semantics + per-(target, agent) delta-vs-baseline auto-discovery; see `docs/superpowers/specs/2026-05-30-audit-semantics-design.md`.
```

If no such entry exists, skip — it was a triage caveat, not yet promoted to a Known follow-ups bullet.

Update **Last updated** with current datetime and note: `"Task 7 DONE: /reviewers:audit slash command (+ template mirror) forwards --snapshot/--since; frontmatter description updated. Audit semantics plan COMPLETE."`

- [ ] **Step 7: Render-time check**

Confirm the rendered slash command in a fresh project doesn't break:

```bash
TMP=$(mktemp -d)
uv run framework new --no-input demo --output "$TMP/proj" 2>/dev/null || true
test -f "$TMP/proj/.claude/commands/reviewers/audit.md" && grep -c "snapshot\|since" "$TMP/proj/.claude/commands/reviewers/audit.md"
rm -rf "$TMP"
```

Expected: the rendered file contains the new flag mentions (`grep` count > 0).

(If `framework new` syntax differs, look at how the test_copier_runner tests invoke it and adapt.)

- [ ] **Step 8: Quality gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: all green.

- [ ] **Step 9: Stage**

```bash
git add .claude/commands/reviewers/audit.md \
        src/framework_cli/template/.claude/commands/reviewers/audit.md.jinja \
        CLAUDE.md
```

**STOP** — staged set IS review-relevant (`template/`). Controller handles gate + commit. Report DONE.

After this task: all 7 components in the spec are done; the audit-semantics work is complete. Branch can be merged to master.

---

## Self-Review

**1. Spec coverage check:**
- Component 1 (`baselines.py`) → Task 1 ✓
- Component 2 (`diff.py` helpers) → Task 2 ✓
- Component 3 (`_resolve_audit_base` helper) → Task 3 ✓
- Component 4 (`audit-prepare` flags + `_emit_audit_prep` wiring) → Task 4 ✓
- Component 5 (workflow per-item branching) → Task 5 ✓
- Component 6 (`audit-finalize` meta.json) → Task 6 ✓
- Component 7 (slash command + final cleanup) → Task 7 ✓
- DoD items 1-7 all map to a task ✓
- The Out-of-scope section (deferred items / calibration / registry changes) is correctly NOT planned ✓

**2. Placeholder scan:** No "TBD" / "TODO" / "fill in" / "appropriate" / "similar to" in the plan body. The one `pass  # IMPLEMENTER: keep the existing implementation here verbatim` line in Task 4 is intentional — it tells the implementer to preserve the existing split-to block while editing the surrounding signature. Acceptable.

**3. Type/name consistency:**
- `_resolve_audit_base` signature is identical in Task 3 (definition) and Task 4 (use).
- `review_mode` / `base_sha` / `base_baseline` field names are identical across Tasks 3, 4, 5, 6.
- `find_latest_baseline_for_agent`, `is_baseline_dir`, `read_baseline_sha` signatures match between Task 1 (definition) and Task 3 (use).
- `snapshot_seed` / `delta_diff` signatures match between Task 2 (definition) and Task 4 (use).
- `_default_scorecards_root` introduced in Task 4 is referenced by tests in Task 4 (via `monkeypatch.setattr(cli_mod, "_default_scorecards_root", ...)`). Tests in Task 3 don't use it (they pass `scorecards_root=tmp_path` directly to the helper). Consistent.

No issues found in self-review.

---

## Notes for the executing agent

- Several earlier branches on this codebase hit `documentation@info` block_threshold noise during the gate phase. Expect 1–2 documentation INFO/LOW findings per template-touching commit (Tasks 5 and 7). Address the trivial ones (frontmatter staleness, docstring gaps); for the rest, the `--no-verify` escape hatch was used before with justification — same convention applies if needed (ask the user before invoking it).
- Memory `commit-gate-hook-timing`: `git add` and `git commit` MUST be separate Bash invocations — do NOT chain.
- Memory `reviewers-tune-pytest-tmp-accumulation`: if pytest produces mass spurious failures, clean `/tmp/pytest-of-chris/*` first.
- CLAUDE.md is the user's source of truth for the "Last updated" pointer and "Known follow-ups." The user (or their linter) may rewrite CLAUDE.md while a task is in flight — that's intentional; preserve those changes.
- All commits should be created with `git -c commit.gpgsign=false commit -m "..."` to avoid gpg-sign issues.

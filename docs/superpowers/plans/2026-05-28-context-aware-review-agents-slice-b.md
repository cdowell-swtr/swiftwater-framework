# Context-Aware Review Agents — Slice B (Agentic Tier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 7 cross-repo review agents an `agentic` strategy: a Messages-API tool-use loop with custom read-only, root-confined `read_file`/`grep`/`glob` tools and a turn-cap + graceful-finalize budget, so each can explore the project tree on demand.

**Architecture:** A new focused module `src/framework_cli/review/agentic.py` holds the tools and `run_agent_agentic(diff, root, spec, client, *, max_turns)` (target-blind — takes `root`/`diff`, never target identity). `run_agent` (Slice A) stays the single-call diff/bundle path. The CLI dispatches on `spec.context.strategy`: `"agentic"` → the loop; else `assemble` + `run_agent`. All Slice B tests are hermetic (a scripted fake client + a real rendered tree via `realize_fixture`); the 7 agents' rendered-project fixtures + real-key scoring are deferred to Slice D, so they keep their legacy `.diff` fixtures.

**Tech Stack:** Python 3.12, the Anthropic Messages API tool-use loop (SDK 0.104), `pathlib`/`re` (pure-Python tools, no shell), `pytest`. Run all tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-28-context-aware-review-agents-slice-b-design.md`

---

## File Structure

- `src/framework_cli/review/agentic.py` (create) — `_resolve_within_root`, the three tools (`read_file`/`grep`/`glob`) + their JSON schemas + a `_run_tool` dispatch, `DEFAULT_MAX_TURNS`, and `run_agent_agentic`.
- `src/framework_cli/review/registry.py` (modify) — add `ContextPolicy.max_agentic_turns`; flip the 7 agents to `ContextPolicy("agentic")`.
- `src/framework_cli/cli.py` (modify) — `_review_run`/`_eval_run` dispatch on `strategy == "agentic"`.
- `tests/review/test_agentic.py` (create) — tools (tmp tree + a real render), confinement, caps, the loop, the budget.
- `tests/review/test_context_policy.py` (modify) — agentic-tier ledger assertion.

---

## Task 1: `ContextPolicy.max_agentic_turns`

**Files:**
- Modify: `src/framework_cli/review/registry.py`
- Test: `tests/review/test_context_policy.py`

- [ ] **Step 1: Write the failing test** (append to `tests/review/test_context_policy.py`)

```python
def test_contextpolicy_max_agentic_turns_defaults_none_and_roundtrips():
    assert ContextPolicy("agentic").max_agentic_turns is None
    assert ContextPolicy("agentic", max_agentic_turns=20).max_agentic_turns == 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_context_policy.py::test_contextpolicy_max_agentic_turns_defaults_none_and_roundtrips -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'max_agentic_turns'`.

- [ ] **Step 3: Add the field** to `ContextPolicy` in `registry.py` (after `max_context_tokens`)

```python
    max_agentic_turns: int | None = None
```

Update the class docstring's last line to mention it:

```python
    `max_context_tokens` overrides the bundle budget; `max_agentic_turns` overrides the
    agentic loop's turn cap. Both default to the strategy's standard limit when None.
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_context_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py tests/review/test_context_policy.py
git commit -m "feat(review): add ContextPolicy.max_agentic_turns"
```

---

## Task 2: The agentic tools (`read_file`/`grep`/`glob`)

**Files:**
- Create: `src/framework_cli/review/agentic.py`
- Test: `tests/review/test_agentic.py`

- [ ] **Step 1: Write the failing tests** — create `tests/review/test_agentic.py`

```python
from pathlib import Path

import pytest

from framework_cli.review.agentic import _run_tool


def _tree(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("import os\nSECRET = 'x'\n")
    (root / "pkg" / "b.py").write_text("from pkg.a import SECRET\n")
    (root / "README.md").write_text("# Demo\n")


def test_read_file_returns_contents(tmp_path):
    _tree(tmp_path)
    out = _run_tool("read_file", {"path": "pkg/a.py"}, tmp_path)
    assert "SECRET = 'x'" in out


def test_read_file_rejects_escape(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("read_file", {"path": "../secrets"}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {"path": "/etc/passwd"}, tmp_path).lower()


def test_read_file_truncates_large_file(tmp_path):
    _tree(tmp_path)
    (tmp_path / "big.py").write_text("x = 1\n" * 20000)  # > 50k chars
    out = _run_tool("read_file", {"path": "big.py"}, tmp_path)
    assert "[truncated]" in out
    assert len(out) < 60_000


def test_grep_finds_matches_with_location(tmp_path):
    _tree(tmp_path)
    out = _run_tool("grep", {"pattern": "SECRET"}, tmp_path)
    assert "pkg/a.py:2:" in out
    assert "pkg/b.py:1:" in out


def test_grep_bad_regex_returns_error(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("grep", {"pattern": "["}, tmp_path).lower()


def test_glob_lists_paths(tmp_path):
    _tree(tmp_path)
    out = _run_tool("glob", {"pattern": "pkg/*.py"}, tmp_path)
    assert "pkg/a.py" in out
    assert "pkg/b.py" in out
    assert "README.md" not in out


def test_unknown_tool_and_missing_arg_return_error(tmp_path):
    assert "error" in _run_tool("nope", {}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {}, tmp_path).lower()  # missing 'path'
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_agentic.py -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.agentic`.

- [ ] **Step 3: Create `src/framework_cli/review/agentic.py`** with the tools

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from framework_cli.review.findings import Finding, parse_findings

DEFAULT_MAX_TURNS = 12
_MAX_TOKENS = 4096
_READ_MAX_CHARS = 50_000
_GREP_MAX_HITS = 100
_GLOB_MAX = 200


class _ToolError(Exception):
    """A tool could not run; surfaced to the model as an error string, never raised into the loop."""


def _resolve_within_root(root: Path, path: str) -> Path:
    """Resolve `path` against `root`, rejecting anything that escapes the tree."""
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise _ToolError(f"path escapes the project root: {path!r}")
    return resolved


def _skip(p: Path) -> bool:
    return ".git" in p.parts


def _read_file(root: Path, path: str) -> str:
    fp = _resolve_within_root(root, path)
    if not fp.is_file():
        return f"error: not a file: {path}"
    text = fp.read_text(errors="replace")
    if len(text) > _READ_MAX_CHARS:
        return text[:_READ_MAX_CHARS] + "\n...[truncated]"
    return text


def _grep(root: Path, pattern: str, path_glob: str | None = None) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"error: invalid regex: {exc}"
    paths = root.glob(path_glob) if path_glob else root.rglob("*")
    hits: list[str] = []
    for p in sorted(paths):
        if not p.is_file() or _skip(p):
            continue
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                hits.append(f"{p.relative_to(root)}:{i}: {line.strip()}")
                if len(hits) >= _GREP_MAX_HITS:
                    return "\n".join(hits) + "\n...[truncated]"
    return "\n".join(hits) if hits else "(no matches)"


def _glob(root: Path, pattern: str) -> str:
    out: list[str] = []
    for p in sorted(root.glob(pattern)):
        if _skip(p):
            continue
        out.append(str(p.relative_to(root)))
        if len(out) >= _GLOB_MAX:
            out.append("...[truncated]")
            break
    return "\n".join(out) if out else "(no matches)"


def _run_tool(name: str, args: dict, root: Path) -> str:
    """Execute a tool by name against `root`; always returns a string (errors included)."""
    try:
        if name == "read_file":
            return _read_file(root, args["path"])
        if name == "grep":
            return _grep(root, args["pattern"], args.get("path_glob"))
        if name == "glob":
            return _glob(root, args["pattern"])
        return f"error: unknown tool: {name}"
    except _ToolError as exc:
        return f"error: {exc}"
    except KeyError as exc:
        return f"error: missing argument {exc}"


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file by its path relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": "Search file contents with a Python regex. Optional path_glob limits the search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path_glob": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": "List files matching a glob pattern (e.g. 'src/**/*.py') relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_agentic.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Add a real-render tool test** (append to `tests/review/test_agentic.py`)

```python
def test_tools_work_on_a_real_rendered_project(tmp_path):
    from framework_cli.review.evals import realize_fixture

    patch = (
        "--- a/src/demo/routes/items.py\n"
        "+++ b/src/demo/routes/items.py\n"
        "@@ -1,1 +1,2 @@\n"
        " from fastapi import APIRouter\n"
        "+SEEDED_MARKER = 1\n"
    )
    # If the first line differs, the implementer adjusts the patch context; the assertions
    # below don't depend on the patch applying — they exercise the tools on the render.
    try:
        root, _diff = realize_fixture(tmp_path, batteries=[], patch=patch)
    except Exception:
        from framework_cli.copier_runner import render_project

        root = tmp_path / "demo"
        render_project(root, {
            "project_name": "Demo", "project_slug": "demo",
            "package_name": "demo", "python_version": "3.12", "batteries": [],
        })
    listing = _run_tool("glob", {"pattern": "src/demo/routes/*.py"}, root)
    assert "src/demo/routes/items.py" in listing
    contents = _run_tool("read_file", {"path": "src/demo/routes/items.py"}, root)
    assert "router" in contents.lower()
    matches = _run_tool("grep", {"pattern": "APIRouter", "path_glob": "src/demo/**/*.py"}, root)
    assert "items.py" in matches
    # .git (created by realize_fixture) is never surfaced.
    assert ".git" not in _run_tool("glob", {"pattern": "**/*"}, root)
```

- [ ] **Step 6: Run + verify**

Run: `uv run pytest tests/review/test_agentic.py -v`
Expected: PASS (8 passed). Then `uv run ruff check src/framework_cli/review/agentic.py tests/review/test_agentic.py && uv run ruff format --check src/framework_cli/review/agentic.py tests/review/test_agentic.py && uv run mypy src` → clean. (`Finding`/`parse_findings` are imported for Task 3; if ruff flags them unused now, add them in Task 3 instead — or keep with `# noqa: F401` and remove the noqa in Task 3. Prefer keeping the imports.)

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/agentic.py tests/review/test_agentic.py
git commit -m "feat(review): agentic file-exploration tools (read_file/grep/glob, root-confined)"
```

---

## Task 3: `run_agent_agentic` — the tool-use loop (normal termination)

**Files:**
- Modify: `src/framework_cli/review/agentic.py`
- Test: `tests/review/test_agentic.py`

- [ ] **Step 1: Write the failing test** (append to `tests/review/test_agentic.py`)

```python
from framework_cli.review.agentic import run_agent_agentic
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent


class _ToolUse:
    type = "tool_use"

    def __init__(self, id, name, input):
        self.id, self.name, self.input = id, name, input


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, content):
        self.content = content


class _ScriptedClient:
    """Returns the queued responses in order; records each create() kwargs."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def test_agentic_loop_runs_tools_then_returns_findings(tmp_path):
    (tmp_path / "x.py").write_text("BAD = 1\n")
    client = _ScriptedClient([
        _Resp([_ToolUse("t1", "glob", {"pattern": "*.py"})]),
        _Resp([_ToolUse("t2", "read_file", {"path": "x.py"})]),
        _Resp([_TextBlock('[{"path": "x.py", "line": 1, "severity": "high", "message": "bad"}]')]),
    ])
    findings = run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n", tmp_path, get_agent("architecture"), client, max_turns=12
    )
    assert findings == [Finding("x.py", 1, "high", "bad")]
    # Two tool rounds happened, then a final answer: 3 create() calls.
    assert len(client.calls) == 3
    # The diff is the cached first system block; tools were offered.
    assert client.calls[0]["system"][0]["text"].startswith("Review this unified diff:")
    assert client.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in client.calls[0]["tools"]] == ["read_file", "grep", "glob"]
    # The tool result was fed back as a user turn before the final call.
    assert any(
        msg["role"] == "user" and isinstance(msg["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in msg["content"])
        for msg in client.calls[2]["messages"]
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_agentic.py::test_agentic_loop_runs_tools_then_returns_findings -v`
Expected: FAIL — `ImportError: cannot import name 'run_agent_agentic'`.

- [ ] **Step 3: Implement `run_agent_agentic`** in `agentic.py` (append)

```python
_INITIAL_INSTRUCTION = (
    "Review the change shown in the diff. Use the read_file, grep, and glob tools to "
    "explore the surrounding repository as needed. When done, reply with ONLY a JSON "
    "array of findings (no tools)."
)
_FINALIZE_INSTRUCTION = (
    "Stop exploring. Return your findings now as a JSON array only. Do not request tools."
)


def _text_of(resp: Any) -> str:
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )


def run_agent_agentic(
    diff: str, root: Path, spec: Any, client: Any, *, max_turns: int
) -> list[Finding]:
    """Drive a tool-use loop letting `spec` explore the tree at `root`; return findings.

    The diff seeds the review (cached system prefix); read_file/grep/glob let the agent
    pull whatever cross-file context it needs. At `max_turns` tool rounds we force a final
    answer so the call always terminates with a (possibly partial) findings list.
    """
    system = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{diff}",
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": spec.prompt},
    ]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _INITIAL_INSTRUCTION}
    ]
    for _turn in range(max_turns):
        resp = client.messages.create(
            model=spec.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            return parse_findings(_text_of(resp))
        messages.append({"role": "assistant", "content": resp.content})
        results = [
            {
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": _run_tool(tu.name, tu.input, root),
            }
            for tu in tool_uses
        ]
        messages.append({"role": "user", "content": results})

    messages.append({"role": "user", "content": _FINALIZE_INSTRUCTION})
    resp = client.messages.create(
        model=spec.model, max_tokens=_MAX_TOKENS, system=system, messages=messages
    )
    return parse_findings(_text_of(resp))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_agentic.py -v`
Expected: PASS (9 passed). Run `uv run mypy src` → clean (the `Finding`/`parse_findings` imports from Task 2 are now used).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/agentic.py tests/review/test_agentic.py
git commit -m "feat(review): run_agent_agentic tool-use loop (normal termination)"
```

---

## Task 4: Budget — turn cap + graceful finalize

**Files:**
- Test: `tests/review/test_agentic.py` (the loop code from Task 3 already implements the finalize; this task proves it)

- [ ] **Step 1: Write the failing/▶ proving test** (append to `tests/review/test_agentic.py`)

```python
class _AlwaysToolClient:
    """Always asks for a tool, until create() is called without a `tools` kwarg (the
    finalize call), at which point it returns findings."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "tools" not in kwargs:  # the finalize call
            return _Resp([_TextBlock('[{"path": "x.py", "line": 1, "severity": "high", "message": "late"}]')])
        return _Resp([_ToolUse(f"t{len(self.calls)}", "glob", {"pattern": "*"})])


def test_agentic_loop_finalizes_at_turn_cap(tmp_path):
    (tmp_path / "x.py").write_text("Y = 1\n")
    client = _AlwaysToolClient()
    findings = run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n", tmp_path, get_agent("architecture"), client, max_turns=3
    )
    # 3 tool rounds (each WITH tools) + 1 finalize (WITHOUT tools) = 4 calls.
    assert len(client.calls) == 4
    assert all("tools" in c for c in client.calls[:3])
    assert "tools" not in client.calls[3]
    # Still returns a (partial) findings list, never hangs or raises.
    assert findings == [Finding("x.py", 1, "high", "late")]
```

- [ ] **Step 2: Run to verify it passes** (Task 3's loop already implements this)

Run: `uv run pytest tests/review/test_agentic.py::test_agentic_loop_finalizes_at_turn_cap -v`
Expected: PASS. (If it fails, the loop's finalize branch is wrong — fix `run_agent_agentic` so the post-loop call omits `tools=`.)

- [ ] **Step 3: Commit**

```bash
git add tests/review/test_agentic.py
git commit -m "test(review): agentic loop finalizes with partial findings at the turn cap"
```

---

## Task 5: Flip the 7 agents to agentic + CLI dispatch + ledger

**Files:**
- Modify: `src/framework_cli/review/registry.py` (the 7 entries)
- Modify: `src/framework_cli/cli.py` (`_review_run`, `_eval_run`)
- Modify: `tests/review/test_context_policy.py` (ledger)
- Test: `tests/review/test_agentic.py` (a dispatch test)

- [ ] **Step 1: Write the failing ledger + dispatch tests**

In `tests/review/test_context_policy.py`, replace `test_agentspec_context_defaults_to_diff` with the two-tier invariant:

```python
def test_every_agent_has_an_explicit_context_strategy():
    # Slice A migrated 11 agents to "bundle"; Slice B migrates 7 to "agentic".
    # After Slice B, NO registered agent is left on the "diff" default.
    bundle = {
        "observability", "application-logic", "performance", "data-integrity",
        "security", "compliance", "test-quality", "documentation", "dependency",
        "accessibility", "usability",
    }
    agentic = {
        "architecture", "data-lineage", "privacy", "api-design",
        "observability-infra", "observability-db", "contracts",
    }
    for name in agent_names():
        strat = get_agent(name).context.strategy
        if name in bundle:
            assert strat == "bundle", f"{name} should be bundle, is {strat}"
        elif name in agentic:
            assert strat == "agentic", f"{name} should be agentic, is {strat}"
        else:
            raise AssertionError(f"{name} is in neither tier — classify it")
```

In `tests/review/test_agentic.py`, add a dispatch test:

```python
def test_cli_dispatches_agentic_strategy(monkeypatch, tmp_path):
    import framework_cli.cli as cli_mod

    called = {}

    def fake_agentic(diff, root, spec, client, *, max_turns):
        called["root"] = root
        called["max_turns"] = max_turns
        return []

    monkeypatch.setattr("framework_cli.review.agentic.run_agent_agentic", fake_agentic)
    monkeypatch.setattr(cli_mod, "default_client", lambda: object())
    monkeypatch.chdir(tmp_path)
    cli_mod._review_run("--- a/x\n+++ b/x\n", get_agent("architecture"))
    assert called["root"] == tmp_path
    assert called["max_turns"] == 12  # DEFAULT_MAX_TURNS (architecture sets no override)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/review/test_context_policy.py tests/review/test_agentic.py::test_cli_dispatches_agentic_strategy -v`
Expected: FAIL — the 7 agents are still `"diff"`; `_review_run` doesn't dispatch agentic.

- [ ] **Step 3: Flip the 7 agents** in `registry.py` — add `context=ContextPolicy("agentic")` to each of: `architecture`, `data-lineage`, `privacy`, `api-design`, `observability-infra`, `observability-db`, `contracts`. Keep all existing args (name, prompt, threshold, active_when, model, on_push/trigger_globs). Example for the compact `architecture` entry:

```python
    "architecture": AgentSpec(
        "review-architecture",
        _prompt("architecture"),
        "high",
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy("agentic"),
    ),
```

(For `data-lineage`/`observability-infra`/`observability-db` which use keyword args like `on_push=`/`trigger_globs=`, add `context=ContextPolicy("agentic")` alongside them.)

- [ ] **Step 4: Add CLI dispatch** in `cli.py` — replace `_review_run` and `_eval_run`:

```python
def _review_run(diff: str, spec: object) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    if spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(diff, Path.cwd(), spec, default_client(), max_turns=turns)
    bundle = assemble(diff, Path.cwd(), spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client())  # type: ignore[arg-type]


def _eval_run(diff: str, root: object, spec: object) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    base = root if isinstance(root, Path) else Path.cwd()
    if spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(diff, base, spec, default_client(), max_turns=turns)
    bundle = assemble(diff, base, spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client())  # type: ignore[arg-type]
```

- [ ] **Step 5: Run to verify they pass + full gate**

Run:
```bash
uv run pytest tests/review/test_context_policy.py tests/review/test_agentic.py -v
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: all green. (The 7 agents still have legacy `.diff` fixtures, so `test_every_registered_agent_has_fixtures`/`test_fixtures_are_wellformed` stay green; the eval scoring loop is unchanged and only runs with a key.)

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/registry.py src/framework_cli/cli.py tests/review/test_context_policy.py tests/review/test_agentic.py
git commit -m "feat(review): flip the 7 cross-repo agents to agentic; CLI dispatches the loop"
```

---

## Task 6: Branch finalize — full gate + state update

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Confirm the full gate** (final)

Run:
```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: green. (Docker acceptance tier intentionally not run; note it.)

- [ ] **Step 2: Update state docs** — CLAUDE.md Current State (Slice B merged: agentic engine + tools + budget + the 7 agents flipped; fixtures/scoring → Slice D) and the meta-plan Plan 11 row (Slice B done, Slice C next). Stage `CLAUDE.md` (the commit-gate hook requires it).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs(state): Slice B (agentic tier) complete"
```

---

## Self-review notes

- **Spec coverage:** §3 architecture + integration → T3/T5; §4 tools (read_file/grep/glob, confinement, caps, error strings) → T2; §5 loop (seed/loop/finalize/parse) → T3+T4; §6 registry (`max_agentic_turns` + flip 7 + ledger) → T1/T5; §7 error handling (tool errors as strings; exceptions propagate to the CLI's existing try/except) → T2 (`_run_tool` swallows tool errors) + the existing CLI wrapper; §8 testing (tools on real render, loop, budget, confinement, registry) → T2/T3/T4/T5. Fixture deferral + legacy `.diff` retention → preserved (no fixture files touched).
- **Placeholder scan:** none — every code step is complete; the one defensive `try/except` in the real-render test is intentional (decouples the assertions from exact patch-context).
- **Type consistency:** `run_agent_agentic(diff, root, spec, client, *, max_turns)`, `_run_tool(name, args, root) -> str`, `TOOL_SCHEMAS`, `DEFAULT_MAX_TURNS`, `ContextPolicy.max_agentic_turns`, `_resolve_within_root(root, path)` used consistently across tasks and the CLI dispatch.
- **No scope creep:** no template payload, no prompt `.md` edits, no eval-harness scoring-loop change, no rendered-project fixtures for the 7 (Slice D).

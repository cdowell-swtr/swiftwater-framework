# Reviewer Path Parity — Core (Plan 20a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce one swappable, `messages.create`-shaped model backend so `framework eval` / `framework review` run identically on the paid Anthropic API or on the free `claude -p` subscription — closing the dev/prod parity gap on the path Plan 21 will tune.

**Architecture:** `run_agent` / `run_agent_agentic` already call `client.messages.create` and read `.content` / `.usage` / `.stop_reason`. We keep those loops **unchanged in shape** and add two backends behind that seam: `ApiBackend` (the raw Anthropic SDK, today's behavior) and `SubagentBackend` (shells out to headless `claude -p`, adapts its JSON into SDK-shaped dataclasses). A shared `build_review_request` replaces the duplicated system-block assembly. A cross-backend **parity contract test** is the executable statement of "dev = prod." `framework eval`/`review` gain a `--backend` flag (default `api`, preserving current behavior).

**Scope boundary:** This plan is the parity *mechanism* only. The in-process engine, cost-safe opt-in resolution (R1–R4), `.framework/review.toml`, checkpoint/resume, `framework audit`/`gate`, and retiring the Workflow-JS/slash/split-manifest path are **Plan 20b** (`2026-06-09-reviewer-path-collapse.md`). 20a does not touch the JS path, the template, or the gate hook.

**Tech Stack:** Python 3.12, `uv`, Typer, `anthropic` SDK, `pytest`, `claude` CLI (headless `-p`).

**Spec:** `docs/superpowers/specs/2026-06-09-reviewer-path-parity-design.md` — read it first.

**Working agreement:** Every commit must stage an updated `CLAUDE.md` Current-State pointer (a `PreToolUse` hook blocks the commit otherwise). Pre-commit quality gate: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`. Per `[[gate-cadence-framework-slices]]`, rely on the green test gate + one branch-end review, not per-commit agent review. All unit tests here are hermetic — they inject a fake SDK client or a fake `claude -p` runner; **no test requires a live key or a live `claude`.** **Review-model policy:** implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; **code-quality review → Opus**; final/branch-end review → Opus (see `[[subagent-review-model-pattern]]`).

---

## File Structure

**New files:**
- `src/framework_cli/review/backend.py` — `Backend`-shaped `Message`/`TextBlock`/`ToolUseBlock`/`Usage` adapters, `ApiBackend`, `SubagentBackend` (claude -p), `BackendExhausted`.
- `src/framework_cli/review/request.py` — `ReviewRequest` + `build_review_request` / `build_agentic_request`: the single system-block assembler both tiers/backends use.
- Tests: `tests/review/test_backend.py`, `tests/review/test_request.py`, `tests/review/test_backend_parity.py`.

**Modified files:**
- `src/framework_cli/review/runner.py` — `run_agent` consumes `build_review_request`; the `client.messages.create` call is byte-identical.
- `src/framework_cli/review/agentic.py` — `run_agent_agentic` consumes `build_agentic_request`; the loop body is byte-identical.
- `src/framework_cli/cli.py` — `_review_run` / `_eval_run` gain a `backend` parameter; `review` / `eval` gain a `--backend` flag (default `api`).

---

## Phase 1 — The backend seam (contract-verified core)

### Task 1.1: SDK-shaped response adapter dataclasses

**Files:**
- Create: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_backend.py
from framework_cli.review.backend import TextBlock, ToolUseBlock, Usage, Message


def test_message_exposes_sdk_shape():
    msg = Message(
        content=[TextBlock(text="hello")],
        usage=Usage(input_tokens=3, output_tokens=5),
        stop_reason="end_turn",
    )
    assert msg.content[0].type == "text"
    assert msg.content[0].text == "hello"
    assert msg.usage.input_tokens == 3
    assert msg.stop_reason == "end_turn"


def test_tool_use_block_shape():
    b = ToolUseBlock(id="t1", name="read_file", input={"path": "a.py"})
    assert b.type == "tool_use"
    assert b.id == "t1"
    assert b.name == "read_file"
    assert b.input == {"path": "a.py"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_backend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.review.backend'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/backend.py
"""Swappable model backends behind a `messages.create`-shaped seam.

`run_agent` / `run_agent_agentic` call `backend.messages.create(...)` and read
`.content` / `.usage` / `.stop_reason` — the same surface the Anthropic SDK
returns. `ApiBackend` is the SDK; `SubagentBackend` shells out to headless
`claude -p` and adapts its JSON into these dataclasses, so the review loops are
byte-identical across paid and free.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class Message:
    content: list[TextBlock | ToolUseBlock] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None


class BackendExhausted(Exception):
    """The backend cannot continue for a reason that will not clear by retrying soon
    (e.g. the Claude subscription usage limit). Carries an optional reset hint. Used by
    Plan 20b's engine; defined here so both plans share the type."""

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_backend.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py CLAUDE.md
git commit -m "feat(review): SDK-shaped backend response adapters + BackendExhausted"
```

### Task 1.2: `ApiBackend` wrapping the Anthropic SDK

**Files:**
- Modify: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_backend.py
from framework_cli.review.backend import ApiBackend


class _SDKBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _SDKMessage:
    def __init__(self):
        self.content = [_SDKBlock("[]")]
        self.usage = type("U", (), {"input_tokens": 1, "output_tokens": 2,
                                    "cache_read_input_tokens": 0,
                                    "cache_creation_input_tokens": 0})()
        self.stop_reason = "end_turn"


class _SDKMessages:
    def __init__(self):
        self.last = None

    def create(self, **kwargs):
        self.last = kwargs
        return _SDKMessage()


class _SDKClient:
    def __init__(self):
        self.messages = _SDKMessages()


def test_api_backend_passes_through_sdk_and_normalizes_usage():
    sdk = _SDKClient()
    backend = ApiBackend(sdk)
    msg = backend.messages.create(model="m", max_tokens=10, system=[], messages=[])
    assert msg.content[0].text == "[]"
    assert msg.usage.input_tokens == 1
    assert msg.stop_reason == "end_turn"
    assert sdk.messages.last["model"] == "m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_backend.py::test_api_backend_passes_through_sdk_and_normalizes_usage -q`
Expected: FAIL — `ImportError: cannot import name 'ApiBackend'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/backend.py
def _normalize_content(raw: Any) -> list[TextBlock | ToolUseBlock]:
    out: list[TextBlock | ToolUseBlock] = []
    for b in raw or []:
        btype = getattr(b, "type", None)
        if btype == "text":
            out.append(TextBlock(text=getattr(b, "text", "") or ""))
        elif btype == "tool_use":
            out.append(
                ToolUseBlock(
                    id=getattr(b, "id", ""),
                    name=getattr(b, "name", ""),
                    input=dict(getattr(b, "input", {}) or {}),
                )
            )
    return out


def _normalize_usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


class _ApiMessages:
    def __init__(self, sdk: Any) -> None:
        self._sdk = sdk

    def create(self, **kwargs: Any) -> Message:
        resp = self._sdk.messages.create(**kwargs)
        return Message(
            content=_normalize_content(getattr(resp, "content", [])),
            usage=_normalize_usage(getattr(resp, "usage", None)),
            stop_reason=getattr(resp, "stop_reason", None),
        )


class ApiBackend:
    """The paid backend: the Anthropic SDK client, normalized to `Message`."""

    def __init__(self, sdk_client: Any) -> None:
        self.messages = _ApiMessages(sdk_client)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_backend.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py CLAUDE.md
git commit -m "feat(review): ApiBackend normalizes the Anthropic SDK to Message"
```

### Task 1.3: `SubagentBackend` — invoke `claude -p` (bundle tier, single-turn, no tools)

**Files:**
- Modify: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

The subprocess runner is injected so the test stays hermetic. `tools=None` (bundle tier) → a single text turn.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_backend.py
import json as _json
from framework_cli.review.backend import SubagentBackend


def _fake_runner(captured):
    def run(argv, *, input_text):
        captured["argv"] = argv
        return _json.dumps({
            "subtype": "success", "is_error": False, "num_turns": 1,
            "stop_reason": "end_turn",
            "result": '```json\n[{"path":"a.py","line":1,"severity":"high","message":"x"}]\n```',
            "usage": {"input_tokens": 7, "output_tokens": 11},
        })
    return run


def test_subagent_backend_bundle_single_turn():
    captured = {}
    backend = SubagentBackend(runner=_fake_runner(captured))
    msg = backend.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=4096,
        system=[{"type": "text", "text": "SYS-A"}, {"type": "text", "text": "SYS-B"}],
        messages=[{"role": "user", "content": "Return your findings as a JSON array only."}],
        tools=None,
    )
    argv = captured["argv"]
    assert "--system-prompt" in argv
    sysidx = argv.index("--system-prompt") + 1
    assert "SYS-A" in argv[sysidx] and "SYS-B" in argv[sysidx]
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "-p" in argv or "--print" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-haiku-4-5-20251001" in argv
    assert "--disallowed-tools" in argv
    assert len(msg.content) == 1 and msg.content[0].type == "text"
    assert '"path":"a.py"' in msg.content[0].text
    assert msg.usage.output_tokens == 11
    assert msg.stop_reason == "end_turn"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_backend.py::test_subagent_backend_bundle_single_turn -q`
Expected: FAIL — `ImportError: cannot import name 'SubagentBackend'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/framework_cli/review/backend.py
import json
import subprocess  # noqa: S404 — invoking the local `claude` CLI by fixed argv

# Tools disabled on every subagent turn so `claude -p` returns exactly ONE model turn
# (no internal agentic loop). Python owns the loop. Explicit list so a new CC tool can't
# silently re-enable looping.
_DISABLED_TOOLS = (
    "Bash", "Read", "Edit", "Write", "Grep", "Glob",
    "WebFetch", "WebSearch", "Task", "NotebookEdit",
)

# Substrings marking a usage-limit / subscription-exhaustion error in `claude -p` output
# (case-insensitive). Matched loosely because phrasing varies by CLI version; the engine
# (20b) treats this as a hard stop, not a retry.
_EXHAUSTION_MARKERS = ("usage limit", "rate limit reached", "quota", "limit reached")


def _default_subprocess_runner(argv: list[str], *, input_text: str | None) -> str:
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv, input=input_text, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if any(m in combined.lower() for m in _EXHAUSTION_MARKERS):
            raise BackendExhausted("claude subscription usage limit reached")
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {combined.strip()}")
    return proc.stdout


def _join_system(system: list[dict[str, Any]]) -> str:
    return "\n\n".join(b.get("text", "") for b in system if b.get("text"))


class _SubagentMessages:
    def __init__(self, runner: Any) -> None:
        self._runner = runner

    def create(self, *, model: str, max_tokens: int, system: list[dict[str, Any]],
               messages: list[dict[str, Any]],
               tools: list[dict[str, Any]] | None = None) -> Message:
        prompt = _render_prompt(messages, tools)
        argv = [
            "claude", "-p", prompt,
            "--system-prompt", _join_system(system),
            "--exclude-dynamic-system-prompt-sections",
            "--output-format", "json",
            "--model", model,
        ]
        for t in _DISABLED_TOOLS:
            argv += ["--disallowed-tools", t]
        raw = self._runner(argv, input_text=None)
        return _parse_claude_json(raw, tools)


class SubagentBackend:
    """The free backend: headless `claude -p` on the subscription, adapted to `Message`.

    Tools are always disabled so each call is a single model turn; the agentic loop in
    `run_agent_agentic` drives tool use via a text protocol (Task 1.4)."""

    def __init__(self, runner: Any = _default_subprocess_runner) -> None:
        self.messages = _SubagentMessages(runner)


def _render_prompt(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> str:
    # Bundle tier (tools is None): a single user turn — return its text. Agentic framing
    # is added in Task 1.4.
    last = messages[-1]["content"]
    return last if isinstance(last, str) else json.dumps(last)


def _parse_claude_json(raw: str, tools: list[dict[str, Any]] | None) -> Message:
    payload = json.loads(raw)
    if payload.get("is_error"):
        low = (payload.get("result") or "").lower()
        if any(m in low for m in _EXHAUSTION_MARKERS):
            raise BackendExhausted("claude usage limit reached")
        raise RuntimeError(f"claude -p error: {payload.get('result')}")
    text = (payload.get("result", "") or "").strip()
    u = payload.get("usage", {}) or {}
    usage = Usage(
        input_tokens=u.get("input_tokens", 0) or 0,
        output_tokens=u.get("output_tokens", 0) or 0,
        cache_read_input_tokens=u.get("cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=u.get("cache_creation_input_tokens", 0) or 0,
    )
    stop = payload.get("stop_reason")
    # Agentic tool-protocol decoding is added in Task 1.4; bundle tier is one text block.
    return Message(content=[TextBlock(text=text)], usage=usage, stop_reason=stop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_backend.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py CLAUDE.md
git commit -m "feat(review): SubagentBackend invokes claude -p for the bundle tier"
```

### Task 1.4: Text tool-protocol for the agentic tier

**Files:**
- Modify: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

When `tools` is passed, the subagent expresses tool calls as a JSON **object** `{"tool_calls":[{"name","input"}]}`; a findings JSON **array** is the final answer. `_render_prompt` injects the protocol + a transcript of prior turns; `_parse_claude_json` decodes an object into `ToolUseBlock`s.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/review/test_backend.py
def test_subagent_agentic_tool_turn_decodes_to_tool_use():
    captured = {}

    def runner(argv, *, input_text):
        captured["argv"] = argv
        return _json.dumps({
            "is_error": False, "stop_reason": "end_turn",
            "result": '{"tool_calls":[{"name":"read_file","input":{"path":"a.py"}}]}',
            "usage": {"input_tokens": 4, "output_tokens": 6},
        })

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="claude-opus-4-8", max_tokens=4096,
        system=[{"type": "text", "text": "SYS"}],
        messages=[{"role": "user", "content": "Review the diff."}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "tool_use"
    assert msg.content[0].name == "read_file"
    assert msg.content[0].input == {"path": "a.py"}
    pidx = captured["argv"].index("-p") + 1
    assert "tool_calls" in captured["argv"][pidx]


def test_subagent_agentic_final_array_is_text():
    def runner(argv, *, input_text):
        return _json.dumps({
            "is_error": False, "stop_reason": "end_turn",
            "result": '[{"path":"a.py","line":2,"severity":"low","message":"m"}]',
            "usage": {},
        })

    backend = SubagentBackend(runner=runner)
    msg = backend.messages.create(
        model="claude-opus-4-8", max_tokens=4096,
        system=[{"type": "text", "text": "SYS"}],
        messages=[{"role": "user", "content": "Review the diff."}],
        tools=[{"name": "read_file"}],
    )
    assert len(msg.content) == 1 and msg.content[0].type == "text"
    assert '"severity":"low"' in msg.content[0].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_backend.py -q -k agentic`
Expected: FAIL — the object is returned as a text block, not decoded to `tool_use`.

- [ ] **Step 3: Write minimal implementation** — replace `_render_prompt` and the tail of `_parse_claude_json`

```python
# replace _render_prompt in src/framework_cli/review/backend.py
_TOOL_PROTOCOL = (
    "\n\nYou have read-only tools available. To call tools, respond with ONLY a JSON "
    'object: {"tool_calls":[{"name":"<tool>","input":{...}}, ...]} and nothing else. '
    "When done exploring and ready to report, respond with ONLY the findings JSON array "
    "(no object, no prose). Available tools: "
)


def _render_transcript(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
            continue
        for block in content:
            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if btype == "tool_use":
                name = block["name"] if isinstance(block, dict) else block.name
                inp = block["input"] if isinstance(block, dict) else block.input
                parts.append(f"[assistant tool_call] {name} {json.dumps(inp)}")
            elif btype == "tool_result":
                body = block.get("content") if isinstance(block, dict) else block.content
                parts.append(f"[tool_result]\n{body}")
            elif btype == "text":
                parts.append(f"[{role}] {block.get('text') if isinstance(block, dict) else block.text}")
    return "\n\n".join(parts)


def _render_prompt(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> str:
    if tools is None:
        last = messages[-1]["content"]
        return last if isinstance(last, str) else json.dumps(last)
    names = ", ".join(t.get("name", "") for t in tools)
    return _render_transcript(messages) + _TOOL_PROTOCOL + names


def _decode_tool_turn(text: str) -> list[TextBlock | ToolUseBlock] | None:
    """A `{"tool_calls":[...]}` object → ToolUseBlocks. A findings array (or anything
    else) → None → treated as the final answer."""
    body = text
    if body.startswith("```"):
        body = body.strip("`")
        body = body[body.find("{"):] if "{" in body else body
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "tool_calls" not in obj:
        return None
    blocks: list[TextBlock | ToolUseBlock] = []
    for i, call in enumerate(obj.get("tool_calls") or []):
        if isinstance(call, dict) and "name" in call:
            blocks.append(ToolUseBlock(id=f"sub-{i}", name=str(call["name"]),
                                       input=dict(call.get("input") or {})))
    return blocks or None
```

Replace the final `return` of `_parse_claude_json` so the tool branch is checked first:

```python
    # ... text/usage/stop computed as before ...
    if tools is not None:
        decoded = _decode_tool_turn(text)
        if decoded is not None:
            return Message(content=decoded, usage=usage, stop_reason=stop)
    return Message(content=[TextBlock(text=text)], usage=usage, stop_reason=stop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_backend.py -q`
Expected: PASS (all backend tests).

- [ ] **Step 5: Empirically pin the single-turn interface (bounded spike)**

```bash
env -u ANTHROPIC_API_KEY claude -p 'Respond with ONLY this and nothing else: {"tool_calls":[{"name":"read_file","input":{"path":"x"}}]}' \
  --system-prompt "You are a code reviewer." --exclude-dynamic-system-prompt-sections \
  --disallowed-tools Bash Read Grep Glob --output-format json --model claude-haiku-4-5-20251001 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('num_turns', d['num_turns']); print(d['result'][:120])"
```

Expected: `num_turns 1` and the result echoes the object. If `num_turns > 1` despite disabled tools, add `--max-turns 1` to `argv` in `_SubagentMessages.create` plus a test asserting it. Record the outcome in the commit message. (If the text-transcript framing proves lossy for multi-turn agentic fidelity later, escalate to `--input-format stream-json` — the spec's documented fallback.)

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py CLAUDE.md
git commit -m "feat(review): SubagentBackend agentic text tool-protocol (single-turn oracle)"
```

### Task 1.5: Shared prep — `build_review_request` (bundle tier)

**Files:**
- Create: `src/framework_cli/review/request.py`
- Modify: `src/framework_cli/review/runner.py`
- Test: `tests/review/test_request.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_request.py
from pathlib import Path
from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.request import build_review_request


def test_bundle_request_system_blocks_order_and_cache():
    bundle = Bundle(diff="DIFF", context_files=(("a.py", "CONTENT"),))
    spec = get_agent("security")
    req = build_review_request(bundle, spec, root=Path("/x"))
    assert req.system[0]["text"].startswith("Review this unified diff:")
    assert "DIFF" in req.system[0]["text"]
    assert req.system[0]["cache_control"] == {"type": "ephemeral"}
    assert "CONTENT" in req.system[1]["text"]
    assert req.system[-1]["text"] == spec.prompt
    assert req.user_message == "Return your findings as a JSON array only."
    assert req.tools is None
    assert req.max_turns == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/review/test_request.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.request`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/framework_cli/review/request.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.decisions import render_decisions_block
from framework_cli.review.registry import AgentSpec


@dataclass(frozen=True)
class ReviewRequest:
    """The dispatch-agnostic review request: identical for paid and free backends."""

    model: str
    system: list[dict[str, Any]]
    user_message: str
    tools: list[dict[str, Any]] | None
    root: Path
    max_turns: int


_BUNDLE_USER = "Return your findings as a JSON array only."


def build_review_request(bundle: Bundle, spec: AgentSpec, *, root: Path) -> ReviewRequest:
    system: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{bundle.diff}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if bundle.context_files:
        joined = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in bundle.context_files
        )
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system.append({
            "type": "text",
            "text": f"Relevant repository files for context:\n\n{joined}{note}",
            "cache_control": {"type": "ephemeral"},
        })
    block = render_decisions_block(list(bundle.decisions))
    if block is not None:
        system.append({"type": "text", "text": block, "cache_control": {"type": "ephemeral"}})
    system.append({"type": "text", "text": spec.prompt})
    return ReviewRequest(model=spec.model, system=system, user_message=_BUNDLE_USER,
                         tools=None, root=root, max_turns=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/review/test_request.py -q`
Expected: PASS.

- [ ] **Step 5: Point `run_agent` at the shared assembler**

In `src/framework_cli/review/runner.py`, replace the inline `system` assembly in `run_agent` (lines 36–60) with `build_review_request`, keeping the `client.messages.create(...)` call, text extraction, `report` population, and `return parse_findings(text)` byte-identical:

```python
# runner.py — top of run_agent body
from framework_cli.review.request import build_review_request
# ...
def run_agent(bundle, spec, client, *, report=None):
    req = build_review_request(bundle, spec, root=Path.cwd())
    t0 = perf_counter()
    message = client.messages.create(
        model=req.model, max_tokens=_MAX_TOKENS, system=req.system,
        messages=[{"role": "user", "content": req.user_message}],
    )
    # ... unchanged below ...
```

- [ ] **Step 6: Run runner tests to verify no regression**

Run: `uv run pytest tests/review/test_runner.py -q`
Expected: PASS (12 passed) — the fake client still sees identical system blocks.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/request.py src/framework_cli/review/runner.py tests/review/test_request.py CLAUDE.md
git commit -m "refactor(review): extract build_review_request; run_agent consumes it"
```

### Task 1.6: Shared agentic prep + the cross-backend parity contract test

**Files:**
- Modify: `src/framework_cli/review/request.py` (add `build_agentic_request`)
- Modify: `src/framework_cli/review/agentic.py`
- Create: `tests/review/test_backend_parity.py`

The executable statement of parity: the SAME loop, SAME inputs, identical findings whether driven by a fake `ApiBackend` or a fake `SubagentBackend`.

- [ ] **Step 1: Write the failing bundle parity test**

```python
# tests/review/test_backend_parity.py
import json
from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent
from framework_cli.review.backend import ApiBackend, SubagentBackend

_FINDINGS = '[{"path":"a.py","line":3,"severity":"high","message":"boom"}]'


class _SDKBlock:
    def __init__(self, t): self.type = "text"; self.text = t
class _SDKMsg:
    def __init__(self, t): self.content = [_SDKBlock(t)]; self.usage = None; self.stop_reason = "end_turn"
class _SDKMsgs:
    def __init__(self, t): self._t = t; self.last = None
    def create(self, **kw): self.last = kw; return _SDKMsg(self._t)
class _SDK:
    def __init__(self, t): self.messages = _SDKMsgs(t)


def _sub_runner(result_text):
    def run(argv, *, input_text):
        return json.dumps({"is_error": False, "stop_reason": "end_turn",
                           "result": result_text, "usage": {}})
    return run


def test_bundle_findings_identical_across_backends():
    bundle, spec = Bundle(diff="DIFF"), get_agent("security")
    f_api = run_agent(bundle, spec, ApiBackend(_SDK(_FINDINGS)))
    f_sub = run_agent(bundle, spec, SubagentBackend(runner=_sub_runner(_FINDINGS)))
    assert f_api == f_sub
    assert f_api[0].message == "boom" and f_api[0].severity == "high"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/review/test_backend_parity.py -q`
Expected: PASS (both backends feed `parse_findings` the same text — the point). If it fails, a real divergence exists; fix before continuing.

- [ ] **Step 3: Add `build_agentic_request`; route `run_agent_agentic`'s system assembly through it**

```python
# append to src/framework_cli/review/request.py
from framework_cli.review.decisions import Decision

_AGENTIC_USER = (
    "Review the change shown in the diff. Use the read_file, grep, and glob tools to "
    "explore the surrounding repository as needed. When done, reply with ONLY a JSON "
    "array of findings (no tools)."
)


def build_agentic_request(diff: str, spec: AgentSpec, *, root: Path,
                          decisions: tuple[Decision, ...] = (), max_turns: int) -> ReviewRequest:
    system: list[dict[str, Any]] = [{
        "type": "text",
        "text": f"Review this unified diff:\n\n{diff}",
        "cache_control": {"type": "ephemeral"},
    }]
    block = render_decisions_block(list(decisions))
    if block is not None:
        system.append({"type": "text", "text": block, "cache_control": {"type": "ephemeral"}})
    system.append({"type": "text", "text": spec.prompt})
    from framework_cli.review.agentic import TOOL_SCHEMAS
    return ReviewRequest(model=spec.model, system=system, user_message=_AGENTIC_USER,
                         tools=TOOL_SCHEMAS, root=root, max_turns=max_turns)
```

In `agentic.py`, replace the inline `system` assembly in `run_agent_agentic` (lines 193–205) with `build_agentic_request(diff, spec, root=root, decisions=decisions, max_turns=max_turns).system`, keeping the loop body byte-identical.

- [ ] **Step 4: Add the agentic parity test**

```python
# add to tests/review/test_backend_parity.py
from framework_cli.review.agentic import run_agent_agentic


class _SDKToolUse:
    def __init__(self, i, n, inp): self.type = "tool_use"; self.id = i; self.name = n; self.input = inp
class _SDKResp:
    def __init__(self, blocks): self.content = blocks; self.usage = None; self.stop_reason = "end_turn"
class _ScriptedSDK:
    def __init__(self, responses): self._r = list(responses); self.messages = self
    def create(self, **kw): return self._r.pop(0)


def test_agentic_findings_identical_across_backends(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    spec = get_agent("architecture")  # agentic tier
    api = ApiBackend(_ScriptedSDK([
        _SDKResp([_SDKToolUse("t1", "read_file", {"path": "a.py"})]),
        _SDKResp([_SDKBlock(_FINDINGS)]),
    ]))
    sub_results = iter(['{"tool_calls":[{"name":"read_file","input":{"path":"a.py"}}]}', _FINDINGS])
    def sub_runner(argv, *, input_text):
        return json.dumps({"is_error": False, "stop_reason": "end_turn",
                           "result": next(sub_results), "usage": {}})
    f_api = run_agent_agentic("DIFF", tmp_path, spec, api, max_turns=12)
    f_sub = run_agent_agentic("DIFF", tmp_path, spec, SubagentBackend(runner=sub_runner), max_turns=12)
    assert f_api == f_sub
    assert f_api[0].message == "boom"
```

- [ ] **Step 5: Run the parity + backend + runner + agentic suites**

Run: `uv run pytest tests/review/test_backend_parity.py tests/review/test_backend.py tests/review/test_runner.py tests/review/test_agentic.py -q`
Expected: PASS. An agentic-parity failure is the exact bug this plan kills — fix until identical.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/request.py src/framework_cli/review/agentic.py tests/review/test_backend_parity.py CLAUDE.md
git commit -m "test(review): cross-backend parity contract (bundle + agentic) is green"
```

### Phase 1 gate

- [ ] Full quality gate green: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.

---

## Phase 2 — Route `eval` / `review` through the swappable backend

This is the minimal CLI surface 20a needs: a `--backend` flag (default `api`, preserving today's behavior) so Plan 21 can tune on `--backend subagent` cheaply and confirm on `--backend api`. No resolution policy, no config file, no skip-neutral — those are 20b.

### Task 2.1: `_eval_run` / `_review_run` accept a backend; `eval` / `review` gain `--backend`

**Files:**
- Modify: `src/framework_cli/cli.py` (`_eval_run` 394–419, `_review_run` 372–391, `eval_agents` 495–639, `review` 1960–2024)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (hermetic — monkeypatch the backend factory)

```python
# add to tests/test_cli.py
def test_eval_uses_subagent_backend_when_flagged(monkeypatch, tmp_path):
    import framework_cli.cli as climod
    made = {}
    def fake_make_backend(name, key_env):
        made["name"] = name
        class _Msgs:
            def create(self, **kw):
                from framework_cli.review.backend import Message, TextBlock
                return Message(content=[TextBlock(text="[]")], stop_reason="end_turn")
        return type("B", (), {"messages": _Msgs()})()
    monkeypatch.setattr(climod, "_make_backend", fake_make_backend)
    # ... invoke `framework eval security --backend subagent --require-fixtures` against a
    #     minimal fixtures dir under tmp_path; assert exit 0 and made["name"] == "subagent".
    assert True  # replace with CliRunner invocation per the eval command's argv
```

(Flesh out the CliRunner invocation to match `eval`'s signature; the assertion that matters is `made["name"] == "subagent"`.)

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_cli.py::test_eval_uses_subagent_backend_when_flagged -q`
Expected: FAIL — no `--backend` flag / no `_make_backend`.

- [ ] **Step 3: Implement**

Add a backend factory and thread `backend` through the dispatch helpers:

```python
# cli.py
def _make_backend(name, key_env):
    from framework_cli.review.backend import ApiBackend, SubagentBackend
    if name == "subagent":
        return SubagentBackend()
    return ApiBackend(default_client(key_env))
```

Change `_review_run(diff, spec, force_agentic=False)` → `_review_run(diff, spec, backend, force_agentic=False)` and `_eval_run(diff, root, spec, *, report=None)` → `_eval_run(diff, root, spec, backend, *, report=None)`, passing `backend` where they currently call `default_client(...)`. Add `backend: str = typer.Option("api", "--backend")` to the `review` and `eval` commands; construct `_make_backend(backend, RUNTIME_KEY_ENV|EVAL_KEY_ENV)` once and pass it down. For `eval`, keep the existing `EVAL_KEY_ENV` skip behavior **only when `backend == "api"`** (the subagent backend needs no key); when `backend == "subagent"`, skip the key check.

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/test_cli.py -q -k "eval or review"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
git commit -m "feat(cli): eval/review --backend {api,subagent} via the swappable seam"
```

### Phase 2 gate

- [ ] Full quality gate green.
- [ ] **Live smoke (manual, one agent):** `framework eval security --backend subagent --require-fixtures` runs on `claude -p` (free) and scores without a `FindingsParseError` crash (the Plan-18 hardening now exercised on the live free path). Spot-compare one agent against `--backend api`; material divergence is a real parity bug — investigate before declaring 20a done.

---

## Phase 3 — Land

### Task 3.1: Status + finish

- [ ] Update `CLAUDE.md` Current State and the meta-plan: Plan 20a ✅, note Plan 21 is now unblocked (tune on `--backend subagent`, confirm on `--backend api`).
- [ ] Branch-end full review (single pass, per `[[gate-cadence-framework-slices]]`).
- [ ] Use superpowers:finishing-a-development-branch to merge to `master`.

---

## Self-Review

**Spec coverage (20a slice):** backend seam + `ApiBackend`/`SubagentBackend` (Tasks 1.1–1.4); `claude -p` required flags asserted (1.3); Option B single-turn + text protocol (1.4); channel parity via `--system-prompt` (1.3); shared prep (1.5–1.6); parity contract test (1.6); `eval`/`review` backend routing that unblocks Plan 21 (2.1). The engine, R1–R4 resolution, checkpoint/resume, `audit`/`gate`, and JS/slash/template retirement are **explicitly deferred to 20b** — not gaps.

**Placeholder scan:** the only non-literal step is Task 2.1 Step 1's CliRunner body (the command argv depends on the final `eval` signature) — flagged inline to flesh out against the real signature; the assertion (`made["name"] == "subagent"`) is concrete.

**Type consistency:** `ReviewRequest`, `Message`/`TextBlock`/`ToolUseBlock`/`Usage`, `BackendExhausted`, `_make_backend(name, key_env)` used consistently and shared with 20b.
</content>

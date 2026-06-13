# LiteLLM Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-home the review/eval engine's two backends (`ApiBackend`, `SubagentBackend`) onto LiteLLM as the single transport seam, with the `claude -p` subscription route re-expressed as an in-tree, extraction-ready LiteLLM `CustomLLM` provider — proven behavior-preserving by the existing parity tests.

**Architecture:** Keep the public seam (`backend.messages.create(model, max_tokens, system, messages, tools=None) -> Message`, the four dataclasses, `_make_backend` selection) exactly as-is; replace only the *innards* of the two backends so both call LiteLLM. A go/no-go spike (Task 1) decides the LiteLLM input surface: **primary** `litellm.anthropic_messages` (Anthropic `/v1/messages` shape — matches the engine, ~zero adapter) or **fallback** `litellm.completion` (OpenAI shape + bidirectional translator). All LiteLLM-version-specific call details are localized to one function, `_anthropic_messages(...)`, whose body Task 1 confirms. Everything above `backend.py` is untouched.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, `mypy`, `litellm` (new dep), the local `claude` CLI (subscription path), Anthropic API (paid path).

**Design spec:** `docs/superpowers/specs/2026-06-13-litellm-backend-foundation-design.md` — read it first; it carries the decomposition, the spike-gated interface decision, and the rationale.

---

## Pre-flight (read before Task 1)

- Source of truth for the seam: `src/framework_cli/review/backend.py`. Re-read it; this plan moves its `claude -p` mechanics into a new module and rewires the two `create()` methods.
- The seam's consumers — `src/framework_cli/review/runner.py` (`run_agent`), `agentic.py` (`run_agent_agentic`), `request.py` (system blocks + `TOOL_SCHEMAS`) — **must not change**. If a task tempts you to edit them, stop: that means the adapter boundary is wrong.
- Run everything via `uv run`. Quality gate: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.
- The repo's commit-gate hook blocks `git commit` until `PLAN.md` or `ACTION_LOG.md` is staged, and false-matches any Bash command where `git` + `commit` co-occur. Stage `git add` and `git commit` as **separate** Bash calls, and keep the word "commit" out of Bash command descriptions.

## File structure

- **Create** `src/framework_cli/review/litellm_provider.py` — the self-contained `claude -p` LiteLLM `CustomLLM` plugin (`ClaudeCliLLM`) + its registration helper. **Zero `framework_cli` imports** (extraction-ready for decomposition row 2). Holds the `claude -p` mechanics moved verbatim from `backend.py`.
- **Create** `tests/review/test_litellm_provider.py` — unit tests for the plugin (fake subprocess runner; the `MAX_ARG_STRLEN` guard; exhaustion mapping; tool-turn decode).
- **Create** `tests/review/test_litellm_spike.py` — the live go/no-go spike (Task 1), `@pytest.mark.live`, skipped without credentials.
- **Modify** `src/framework_cli/review/backend.py` — both `create()` methods now route through `_anthropic_messages(...)`; the `claude -p` mechanics move out to `litellm_provider.py`; the dataclasses + `BackendExhausted` stay.
- **Modify** `tests/review/test_backend.py`, `tests/review/test_backend_parity.py` — re-point mocks at the LiteLLM layer (mock `_anthropic_messages` / the litellm call, not the Anthropic SDK / raw subprocess).
- **Modify** `pyproject.toml` (add `litellm`), `uv.lock` (regen), and the `[tool.mypy]` overrides if litellm lacks types.
- **Modify** `PLAN.md` + `ACTION_LOG.md` per task (state-keeping is required before each commit).

---

## Task 1: Add `litellm` and run the interface spike (GO/NO-GO gate)

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Create: `tests/review/test_litellm_spike.py`

This task is exploratory, not test-first: its product is a **decision** (which LiteLLM surface the rest of the plan builds on) plus a kept live spike test. It needs the real box: `litellm` installed, the `claude` CLI on PATH, and `ANTHROPIC_EVAL_API_KEY` set.

- [ ] **Step 1: Add the dependency**

Add `litellm` to `[project].dependencies` in `pyproject.toml` (unpinned for the spike; Task 8 pins to the version proven here). Then:

Run: `uv lock && uv sync`
Expected: `litellm` resolves and installs; `uv run python -c "import litellm; print(litellm.__version__)"` prints a version.

- [ ] **Step 2: Write the spike test (two probes, marked live)**

```python
# tests/review/test_litellm_spike.py
"""Go/no-go spike for the LiteLLM interface decision (Plan 27, Task 1).

Resolves two facts the docs do not: (S1) anthropic_messages preserves Anthropic
cache_control on the request and returns non-zero cache_read on a repeat call;
(S2) a custom_provider_map CustomLLM is actually invoked through anthropic_messages.
Marked `live` — skipped unless RUN_LITELLM_SPIKE=1 and credentials are present.
Records nothing itself; the implementer records GO/NO-GO in ACTION_LOG.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_SPIKE") != "1",
    reason="live spike; set RUN_LITELLM_SPIKE=1 with ANTHROPIC_EVAL_API_KEY + claude CLI",
)

_MODEL = "claude-haiku-4-5-20251001"
_BIG = "You are a reviewer. " + ("context " * 2000)  # force a cacheable prefix


def _anthropic_system():
    return [{"type": "text", "text": _BIG, "cache_control": {"type": "ephemeral"}}]


def test_s1_api_path_caching_passthrough():
    """anthropic provider via anthropic_messages: cache_control honored, cache_read>0 on repeat."""
    import litellm

    key = os.environ["ANTHROPIC_EVAL_API_KEY"]

    def call():
        # NOTE: confirm the exact entrypoint here (sync `litellm.anthropic.messages.create`
        # vs async-only `...acreate` driven by asyncio.run). Record what works.
        return litellm.anthropic_messages(
            model="anthropic/" + _MODEL,
            max_tokens=64,
            system=_anthropic_system(),
            messages=[{"role": "user", "content": "Reply with []"}],
            api_key=key,
        )

    first = call()
    second = call()
    usage = second["usage"] if isinstance(second, dict) else second.usage
    cache_read = (
        usage.get("cache_read_input_tokens")
        if isinstance(usage, dict)
        else getattr(usage, "cache_read_input_tokens", 0)
    )
    assert cache_read and cache_read > 0, f"no cache hit on repeat call: {usage!r}"


def test_s2_custom_provider_routes_through_anthropic_messages():
    """A trivial CustomLLM under custom_provider_map must be invoked by anthropic_messages."""
    import litellm
    from litellm import CustomLLM

    invoked = {"hit": False}

    class _Probe(CustomLLM):
        def completion(self, *args, **kwargs):  # signature per litellm version
            invoked["hit"] = True
            return litellm.ModelResponse(
                choices=[{"message": {"role": "assistant", "content": "[]"}}]
            )

        async def acompletion(self, *args, **kwargs):
            invoked["hit"] = True
            return litellm.ModelResponse(
                choices=[{"message": {"role": "assistant", "content": "[]"}}]
            )

    litellm.custom_provider_map = [{"provider": "claude-cli", "custom_handler": _Probe()}]
    try:
        litellm.anthropic_messages(
            model="claude-cli/" + _MODEL,
            max_tokens=16,
            system=[{"type": "text", "text": "probe"}],
            messages=[{"role": "user", "content": "go"}],
        )
    finally:
        litellm.custom_provider_map = []
    assert invoked["hit"], "anthropic_messages did not route to the custom provider"
```

- [ ] **Step 3: Run the spike on the real box**

Run: `RUN_LITELLM_SPIKE=1 uv run pytest tests/review/test_litellm_spike.py -v`
Expected (GO): both tests pass. If `test_s1` fails on caching, retry once (cache write/read ordering). If the exact entrypoint differs, fix the `call()` body and the `_anthropic_messages` shape note, then re-run.

- [ ] **Step 4: Record the decision**

Append an `ACTION_LOG.md` entry: GO (anthropic_messages — record the exact entrypoint + litellm version) or NO-GO (which probe failed). On **NO-GO**, the rest of this plan switches to the `litellm.completion` fallback — see "Fallback path" at the end; the spike test stays as the regression record of why.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/review/test_litellm_spike.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "feat(review): add litellm dep + interface go/no-go spike (Plan 27 Task 1)"
```

> **The remaining tasks assume GO (anthropic_messages).** If NO-GO, read "Fallback path" before continuing.

---

## Task 2: The `claude-cli` CustomLLM plugin (self-contained, extraction-ready)

Move the `claude -p` mechanics out of `backend.py` into a standalone module with **no `framework_cli` imports**. The handler renders the (OpenAI-shaped, because litellm bridges) messages litellm hands it into a `claude -p` text prompt and returns a `litellm.ModelResponse`.

**Files:**
- Create: `src/framework_cli/review/litellm_provider.py`
- Test: `tests/review/test_litellm_provider.py`

- [ ] **Step 1: Write the failing test — single-turn, system via file, prompt via stdin**

```python
# tests/review/test_litellm_provider.py
import json as _json

import pytest

from framework_cli.review.litellm_provider import (
    ClaudeCliLLM,
    ClaudeExhausted,
    _render_messages_to_prompt,
)


def _runner(captured, result):
    def run(argv, *, input_text):
        captured["argv"] = list(argv)
        captured["input_text"] = input_text
        try:
            idx = argv.index("--system-prompt-file")
            with open(argv[idx + 1]) as fh:
                captured["sys"] = fh.read()
        except (ValueError, IndexError, OSError):
            captured["sys"] = None
        return _json.dumps(result)

    return run


def test_handler_single_turn_system_via_file_prompt_via_stdin():
    captured = {}
    result = {
        "is_error": False, "stop_reason": "end_turn",
        "result": "[]", "usage": {"input_tokens": 7, "output_tokens": 11},
    }
    llm = ClaudeCliLLM(runner=_runner(captured, result))
    resp = llm.completion(
        model="claude-cli/claude-haiku-4-5-20251001",
        messages=[
            {"role": "system", "content": "SYS-A"},
            {"role": "user", "content": "Return your findings as a JSON array only."},
        ],
        optional_params={},
    )
    argv = captured["argv"]
    assert "--system-prompt-file" in argv and "--system-prompt" not in argv
    assert captured["sys"] == "SYS-A"
    assert captured["input_text"] == "Return your findings as a JSON array only."
    assert "--output-format" in argv and "json" in argv
    assert "--model" in argv and "claude-haiku-4-5-20251001" in argv  # prefix stripped
    assert "--disallowed-tools" in argv
    text = resp.choices[0].message.content
    assert text == "[]"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_litellm_provider.py::test_handler_single_turn_system_via_file_prompt_via_stdin -v`
Expected: FAIL — `ModuleNotFoundError: framework_cli.review.litellm_provider`.

- [ ] **Step 3: Write the plugin (mechanics moved verbatim from `backend.py`)**

```python
# src/framework_cli/review/litellm_provider.py
"""Self-contained `claude -p` LiteLLM CustomLLM provider (the subscription route).

NO `framework_cli` imports — this module is lifted to its own package in a later
plan. It re-expresses the headless `claude -p` mechanics (system via 0o600 temp
file, prompt via stdin, tools disabled, JSON output) as a litellm.CustomLLM whose
`completion`/`acompletion` return a litellm.ModelResponse.
"""
from __future__ import annotations

import json
import os
import re
import subprocess  # noqa: S404 — fixed-argv local `claude` CLI
import tempfile
from typing import Any, Callable

import litellm
from litellm import CustomLLM

_DISABLED_TOOLS = (
    "Bash", "Read", "Edit", "Write", "Grep",
    "Glob", "WebFetch", "WebSearch", "Task", "NotebookEdit",
)
_EXHAUSTION_MARKERS = (
    "usage limit", "rate limit reached", "quota", "limit reached", "session limit",
)
_EXHAUSTION_MESSAGE = "claude subscription usage limit reached"


class ClaudeExhausted(Exception):
    """Subscription usage-limit hit; carries an optional human reset hint.

    Raised from inside the handler. The framework maps this to its own
    BackendExhausted at the seam (this module stays framework-agnostic)."""

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint


def _exhaustion_error(text: str) -> "ClaudeExhausted | None":
    if not any(m in text.lower() for m in _EXHAUSTION_MARKERS):
        return None
    m = re.search(r"resets[^\"}\n]*", text, re.IGNORECASE)
    hint = m.group(0).strip().rstrip(".") if m else None
    msg = _EXHAUSTION_MESSAGE + (f" — {hint}" if hint else "")
    return ClaudeExhausted(msg, reset_hint=hint)


def _default_runner(argv: list[str], *, input_text: str | None) -> str:
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv, input=input_text, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        exhausted = _exhaustion_error(combined)
        if exhausted is not None:
            raise exhausted
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {combined.strip()}")
    return proc.stdout


def _render_messages_to_prompt(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """Split litellm's OpenAI-shaped messages into (system_text, user_prompt).

    System messages are joined for the --system-prompt-file; the remainder is
    rendered to a transcript passed via stdin. Tool calls/results (OpenAI shape)
    are flattened to the same text protocol the engine's loop already parses."""
    system_parts: list[str] = []
    body_parts: list[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            system_parts.append(_text_of_content(content))
            continue
        if role == "tool":
            body_parts.append(f"[tool_result]\n{_text_of_content(content)}")
            continue
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                body_parts.append(f"[assistant tool_call] {fn.get('name')} {fn.get('arguments')}")
            continue
        body_parts.append(f"[{role}] {_text_of_content(content)}")
    return "\n\n".join(p for p in system_parts if p), "\n\n".join(body_parts)


def _text_of_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text", "") if b.get("type") == "text" else json.dumps(b))
            else:
                out.append(str(b))
        return "\n".join(out)
    return "" if content is None else str(content)


def _strip_prefix(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


def _build_response(raw: str) -> "litellm.ModelResponse":
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"claude -p returned non-JSON output: {raw[:120]!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"claude -p returned unexpected JSON: {type(payload).__name__}")
    if payload.get("is_error"):
        result = payload.get("result") or ""
        exhausted = _exhaustion_error(result)
        if exhausted is not None:
            raise exhausted
        raise RuntimeError(f"claude -p error: {payload.get('result')}")
    text = (payload.get("result", "") or "").strip()
    u = payload.get("usage", {}) or {}
    resp = litellm.ModelResponse(
        choices=[{"message": {"role": "assistant", "content": text},
                  "finish_reason": payload.get("stop_reason") or "stop"}],
    )
    resp.usage = litellm.Usage(
        prompt_tokens=u.get("input_tokens", 0) or 0,
        completion_tokens=u.get("output_tokens", 0) or 0,
        total_tokens=(u.get("input_tokens", 0) or 0) + (u.get("output_tokens", 0) or 0),
    )
    # Anthropic cache token fields, surfaced for the seam's Usage mapping.
    resp.usage.cache_read_input_tokens = u.get("cache_read_input_tokens", 0) or 0
    resp.usage.cache_creation_input_tokens = u.get("cache_creation_input_tokens", 0) or 0
    return resp


class ClaudeCliLLM(CustomLLM):
    """Headless `claude -p` on the subscription as a litellm CustomLLM."""

    def __init__(self, runner: Callable[..., str] = _default_runner) -> None:
        super().__init__()
        self._runner = runner

    def completion(self, *args: Any, **kwargs: Any) -> "litellm.ModelResponse":
        model = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        return self._run(model, messages)

    async def acompletion(self, *args: Any, **kwargs: Any) -> "litellm.ModelResponse":
        model = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        return self._run(model, messages)

    def _run(self, model: str, messages: list[dict[str, Any]]) -> "litellm.ModelResponse":
        system_text, prompt = _render_messages_to_prompt(messages)
        fd, sys_path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(system_text)
            os.chmod(sys_path, 0o600)  # noqa: S103 — owner-read-only temp file
            argv = [
                "claude", "-p",
                "--system-prompt-file", sys_path,
                "--exclude-dynamic-system-prompt-sections",
                "--output-format", "json",
                "--model", _strip_prefix(model),
            ]
            for t in _DISABLED_TOOLS:
                argv += ["--disallowed-tools", t]
            raw = self._runner(argv, input_text=prompt)
        finally:
            try:
                os.unlink(sys_path)
            except OSError:
                pass
        return _build_response(raw)


def register() -> None:
    """Idempotently register the claude-cli provider in litellm.custom_provider_map."""
    existing = [p for p in (litellm.custom_provider_map or [])
                if p.get("provider") != "claude-cli"]
    litellm.custom_provider_map = existing + [
        {"provider": "claude-cli", "custom_handler": ClaudeCliLLM()}
    ]
```

> Note: the exact `CustomLLM.completion`/`acompletion` parameter names are pinned by the litellm version from Task 1. The `*args/**kwargs` shim above tolerates the version's keyword set; tighten to the real signature once Task 1 records it.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_litellm_provider.py::test_handler_single_turn_system_via_file_prompt_via_stdin -v`
Expected: PASS.

- [ ] **Step 5: Add the MAX_ARG_STRLEN guard test (the class only the real box catches; mirror it as a unit guard)**

```python
def test_large_system_never_appears_as_argv():
    captured = {}
    big = "x" * 200_000
    result = {"is_error": False, "stop_reason": "end_turn", "result": "[]", "usage": {}}
    llm = ClaudeCliLLM(runner=_runner(captured, result))
    llm.completion(
        model="claude-cli/claude-haiku-4-5-20251001",
        messages=[{"role": "system", "content": big},
                  {"role": "user", "content": "go"}],
        optional_params={},
    )
    for elem in captured["argv"]:
        assert len(elem) <= 131072, f"argv element of {len(elem)} exceeds MAX_ARG_STRLEN"
    assert "--system-prompt-file" in captured["argv"]
    assert captured["sys"] == big
    assert captured["input_text"] == "go"
```

Run: `uv run pytest tests/review/test_litellm_provider.py -v` → PASS.

- [ ] **Step 6: Add the exhaustion-mapping test**

```python
def test_session_limit_raises_claude_exhausted_with_hint():
    result = {"is_error": True, "api_error_status": 429,
              "result": "You've hit your session limit · resets 11:30am (America/Los_Angeles)"}
    llm = ClaudeCliLLM(runner=_runner({}, result))
    with pytest.raises(ClaudeExhausted) as ei:
        llm.completion(
            model="claude-cli/m",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "go"}],
            optional_params={},
        )
    assert ei.value.reset_hint and "11:30" in ei.value.reset_hint
```

Run: `uv run pytest tests/review/test_litellm_provider.py -v` → PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/litellm_provider.py tests/review/test_litellm_provider.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "feat(review): self-contained claude-cli CustomLLM provider (Plan 27 Task 2)"
```

---

## Task 3: The `_anthropic_messages` seam helper (one place for all litellm specifics)

A single function the two backends share: prefix the model, call litellm's anthropic-messages entrypoint, normalize the response to our `Message`, and map errors. **This is the only function that knows the litellm call surface** — Task 1 confirmed its body.

**Files:**
- Modify: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

- [ ] **Step 1: Write the failing test (normalization + prefixing, litellm mocked)**

```python
# add to tests/review/test_backend.py
def test_anthropic_messages_normalizes_and_prefixes(monkeypatch):
    import framework_cli.review.backend as bk

    seen = {}

    def fake_call(*, model, max_tokens, system, messages, tools, api_key, num_retries):
        seen.update(model=model, system=system, tools=tools, api_key=api_key)
        return {
            "content": [{"type": "text", "text": "[]"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 2,
                      "cache_read_input_tokens": 9, "cache_creation_input_tokens": 0},
        }

    monkeypatch.setattr(bk, "_litellm_anthropic_messages", fake_call)
    msg = bk._anthropic_messages(
        model_prefix="anthropic/", model="claude-sonnet-4-6", max_tokens=10,
        system=[{"type": "text", "text": "S"}],
        messages=[{"role": "user", "content": "go"}], tools=None,
        api_key="k", num_retries=8,
    )
    assert seen["model"] == "anthropic/claude-sonnet-4-6"
    assert msg.content[0].type == "text" and msg.content[0].text == "[]"
    assert msg.usage.cache_read_input_tokens == 9
    assert msg.stop_reason == "end_turn"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_backend.py::test_anthropic_messages_normalizes_and_prefixes -v`
Expected: FAIL — `AttributeError: _anthropic_messages`.

- [ ] **Step 3: Implement the helper in `backend.py`**

Add to `backend.py` (keep `_normalize_content`/`_normalize_usage` — they already parse Anthropic-shaped content/usage and survive verbatim):

```python
def _litellm_anthropic_messages(*, model, max_tokens, system, messages, tools,
                                api_key, num_retries):
    """The ONE call site for litellm. Body pinned by Task 1 (entrypoint + kwargs +
    sync vs asyncio.run of acreate). Returns litellm's raw Anthropic-shaped response."""
    import litellm
    kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
    if tools is not None:
        kwargs["tools"] = tools
    if api_key is not None:
        kwargs["api_key"] = api_key
    if num_retries is not None:
        kwargs["num_retries"] = num_retries
    return litellm.anthropic_messages(**kwargs)  # confirm exact entrypoint in Task 1


def _resp_get(resp, key, default=None):
    return resp.get(key, default) if isinstance(resp, dict) else getattr(resp, key, default)


def _anthropic_messages(*, model_prefix, model, max_tokens, system, messages, tools,
                        api_key=None, num_retries=None) -> Message:
    raw = _litellm_anthropic_messages(
        model=model_prefix + model, max_tokens=max_tokens, system=system,
        messages=messages, tools=tools, api_key=api_key, num_retries=num_retries,
    )
    return Message(
        content=_normalize_content(_resp_get(raw, "content", []) or []),
        usage=_normalize_usage(_resp_get(raw, "usage", None)),
        stop_reason=_resp_get(raw, "stop_reason", None),
    )
```

> `_normalize_content`/`_normalize_usage` use `getattr` and so already read either dict-or-object content blocks/usage. If litellm returns dicts (not objects), extend the two helpers to also read `b["type"]/b["text"]` and `usage["input_tokens"]` — add a test first if so.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/review/test_backend.py::test_anthropic_messages_normalizes_and_prefixes -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "feat(review): _anthropic_messages seam helper over litellm (Plan 27 Task 3)"
```

---

## Task 4: Re-home `SubagentBackend` onto the `claude-cli` provider

Rewire `SubagentBackend.messages.create` to register the provider and call `_anthropic_messages` with the `claude-cli/` prefix. Map the plugin's `ClaudeExhausted` → the seam's `BackendExhausted`. Delete the `claude -p` mechanics now living in `litellm_provider.py`.

**Files:**
- Modify: `src/framework_cli/review/backend.py`
- Test: `tests/review/test_backend.py`

- [ ] **Step 1: Update the existing subagent unit test to the new seam**

Re-point `tests/review/test_backend.py`'s subagent tests: instead of a raw subprocess `runner`, construct `SubagentBackend(runner=...)` where `runner` is still the fake subprocess (the backend passes it through to `ClaudeCliLLM`). The `create()` assertions (argv, stdin, exhaustion, tool decode) stay — they now flow through the plugin + litellm-shaped path. Keep `test_subagent_large_system_goes_via_file_not_argv` (it must still hold).

> If routing the fake subprocess through litellm's `anthropic_messages` is impractical to mock end-to-end, split the assertions: keep the argv/stdin/MAX_ARG_STRLEN assertions in `test_litellm_provider.py` (Task 2, direct on `ClaudeCliLLM`), and in `test_backend.py` assert only that `SubagentBackend` maps a `ClaudeExhausted` to `BackendExhausted` and returns a normalized `Message` (mock `_anthropic_messages`).

- [ ] **Step 2: Run to verify the updated test fails**

Run: `uv run pytest tests/review/test_backend.py -k subagent -v`
Expected: FAIL (old `_SubagentMessages` mechanics gone / not yet rewired).

- [ ] **Step 3: Rewrite `SubagentBackend`**

```python
# backend.py — replace _SubagentMessages + SubagentBackend
from framework_cli.review.litellm_provider import ClaudeExhausted, ClaudeCliLLM, register


class _SubagentMessages:
    def __init__(self, runner: Any | None = None) -> None:
        # Register a provider bound to this runner (default: real subprocess).
        handler = ClaudeCliLLM() if runner is None else ClaudeCliLLM(runner=runner)
        import litellm
        existing = [p for p in (litellm.custom_provider_map or [])
                    if p.get("provider") != "claude-cli"]
        litellm.custom_provider_map = existing + [
            {"provider": "claude-cli", "custom_handler": handler}
        ]

    def create(self, *, model, max_tokens, system, messages, tools=None) -> Message:
        try:
            return _anthropic_messages(
                model_prefix="claude-cli/", model=model, max_tokens=max_tokens,
                system=system, messages=messages, tools=tools,
            )
        except ClaudeExhausted as exc:
            raise BackendExhausted(str(exc), reset_hint=exc.reset_hint) from exc


class SubagentBackend:
    """The subscription backend: headless `claude -p` via the litellm CustomLLM seam."""

    def __init__(self, runner: Any | None = None) -> None:
        self.messages = _SubagentMessages(runner)
```

Then delete from `backend.py` the now-relocated `claude -p` mechanics: `_DISABLED_TOOLS`, `_EXHAUSTION_*`, `_exhaustion_error`, `_default_subprocess_runner`, `_join_system`, `_TOOL_PROTOCOL`, `_render_transcript`, `_render_prompt`, `_decode_tool_turn`, `_parse_claude_json` (they live in `litellm_provider.py` now). Keep `_join_system` only if a test imports it — Task 2's tests do not; `test_backend.py` imports it, so re-point that import to `litellm_provider` or drop the assertion.

> Verify whether litellm propagates `ClaudeExhausted` raised inside the custom handler, or wraps it. If it wraps, the handler must raise a litellm exception type and `_SubagentMessages.create` must detect the wrapped marker. Add a test that a handler-raised exhaustion reaches `BackendExhausted` through the real litellm call path (mark `live` if it needs the real dispatcher).

- [ ] **Step 4: Run the subagent + provider tests**

Run: `uv run pytest tests/review/test_backend.py tests/review/test_litellm_provider.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/backend.py tests/review/test_backend.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "feat(review): route SubagentBackend through the claude-cli litellm provider (Plan 27 Task 4)"
```

---

## Task 5: Re-home `ApiBackend` onto the litellm `anthropic/` provider

**Files:**
- Modify: `src/framework_cli/review/backend.py`, `src/framework_cli/cli.py` (factory), `src/framework_cli/review/runner.py` (`default_client` → key/retries source)
- Test: `tests/review/test_backend.py`

- [ ] **Step 1: Write the failing test — ApiBackend calls litellm with the anthropic prefix + key + retries**

```python
# add to tests/review/test_backend.py
def test_api_backend_calls_litellm_anthropic(monkeypatch):
    import framework_cli.review.backend as bk

    seen = {}

    def fake(*, model, max_tokens, system, messages, tools, api_key, num_retries):
        seen.update(model=model, api_key=api_key, num_retries=num_retries)
        return {"content": [{"type": "text", "text": "[]"}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 2}}

    monkeypatch.setattr(bk, "_litellm_anthropic_messages", fake)
    backend = bk.ApiBackend(api_key="sekret", num_retries=8)
    msg = backend.messages.create(model="claude-sonnet-4-6", max_tokens=10,
                                  system=[], messages=[])
    assert seen["model"] == "anthropic/claude-sonnet-4-6"
    assert seen["api_key"] == "sekret" and seen["num_retries"] == 8
    assert msg.content[0].text == "[]"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/review/test_backend.py::test_api_backend_calls_litellm_anthropic -v`
Expected: FAIL — `ApiBackend.__init__` still takes an `sdk_client`.

- [ ] **Step 3: Rewrite `ApiBackend`**

```python
# backend.py — replace _ApiMessages + ApiBackend
class _ApiMessages:
    def __init__(self, api_key: str | None, num_retries: int | None) -> None:
        self._api_key = api_key
        self._num_retries = num_retries

    def create(self, *, model, max_tokens, system, messages, tools=None) -> Message:
        try:
            return _anthropic_messages(
                model_prefix="anthropic/", model=model, max_tokens=max_tokens,
                system=system, messages=messages, tools=tools,
                api_key=self._api_key, num_retries=self._num_retries,
            )
        except Exception as exc:  # noqa: BLE001 — narrow to litellm's rate-limit type
            import litellm
            if isinstance(exc, litellm.RateLimitError):
                raise BackendExhausted(str(exc)) from exc
            raise


class ApiBackend:
    """The paid backend: Anthropic via litellm, normalized to `Message`."""

    def __init__(self, api_key: str | None, num_retries: int | None = None) -> None:
        self.messages = _ApiMessages(api_key, num_retries)
```

- [ ] **Step 4: Update the factory and key/retries source**

In `cli.py` `_make_backend`:

```python
def _make_backend(name: str, key_env: str) -> object:
    from framework_cli.review.backend import ApiBackend, SubagentBackend
    if name == "subagent":
        return SubagentBackend()
    from framework_cli.review.runner import _max_retries
    return ApiBackend(api_key=os.environ.get(key_env), num_retries=_max_retries())
```

`runner.py`'s `default_client` (the `anthropic.Anthropic(...)` constructor) is now unused by the backends — keep `_max_retries`/`DEFAULT_MAX_RETRIES`/`MAX_RETRIES_CAP` (Task 6 + the retained `test_runner.py`), and remove `default_client` only if nothing else imports it (grep first: `rg "default_client" src tests`).

- [ ] **Step 5: Run to verify it passes + fix `test_backend_parity.py`**

Re-point `tests/review/test_backend_parity.py`: replace the `_SDK*` fakes and `ApiBackend(_SDK(...))` / `SubagentBackend(runner=...)` construction with a single `monkeypatch` of `backend._litellm_anthropic_messages` returning Anthropic-shaped dicts, then build `ApiBackend(api_key="x")` and `SubagentBackend()` and assert findings identical. The parity *intent* (api ↔ subagent produce identical findings through the same engine) is preserved.

Run: `uv run pytest tests/review/test_backend.py tests/review/test_backend_parity.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/backend.py src/framework_cli/cli.py src/framework_cli/review/runner.py tests/review/test_backend.py tests/review/test_backend_parity.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "feat(review): route ApiBackend through litellm anthropic provider (Plan 27 Task 5)"
```

---

## Task 6: Retry + exhaustion semantics through litellm

Confirm the `ANTHROPIC_MAX_RETRIES` contract still governs and the existing `test_runner.py` retry tests hold (they test `_max_retries`, which Task 5 keeps as the source feeding `num_retries`).

**Files:**
- Test: `tests/review/test_runner.py` (should pass unchanged)
- Modify (only if needed): `src/framework_cli/review/runner.py`

- [ ] **Step 1: Run the retained retry tests**

Run: `uv run pytest tests/review/test_runner.py -v`
Expected: PASS unchanged — `_max_retries()` and its env override/clamp/fallback still exist.

- [ ] **Step 2: Add an exhaustion-mapping test for the API path**

```python
# add to tests/review/test_backend.py
def test_api_backend_maps_rate_limit_to_exhausted(monkeypatch):
    import litellm
    import framework_cli.review.backend as bk

    def boom(**kw):
        raise litellm.RateLimitError("429", llm_provider="anthropic", model="m")

    monkeypatch.setattr(bk, "_litellm_anthropic_messages", boom)
    backend = bk.ApiBackend(api_key="k")
    with pytest.raises(bk.BackendExhausted):
        backend.messages.create(model="m", max_tokens=1, system=[], messages=[])
```

Run: `uv run pytest tests/review/test_backend.py::test_api_backend_maps_rate_limit_to_exhausted -v` → PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/review/test_backend.py src/framework_cli/review/runner.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "test(review): retry contract + api-path exhaustion mapping over litellm (Plan 27 Task 6)"
```

---

## Task 7: Live smoke + real caching check

The live smoke is the only thing that catches the `MAX_ARG_STRLEN`/large-input class end-to-end and proves real caching passthrough.

**Files:**
- Modify: the existing live smoke test (grep: `rg -l "live" tests/review tests/eval`), or create `tests/review/test_litellm_live_smoke.py`

- [ ] **Step 1: Point the live smoke at the new seam**

The smoke must, against the real `claude` CLI (subagent) and real Anthropic key (api): run a bundle review with a **large** system block (>128 KB) and a real diff via stdin, through `SubagentBackend()` and `ApiBackend(api_key=…)`, and assert findings parse. Add a caching assertion on the API path: two identical calls, second returns `usage.cache_read_input_tokens > 0`.

```python
@pytest.mark.skipif(os.environ.get("RUN_LIVE_SMOKE") != "1", reason="live")
def test_live_subagent_large_input_and_api_caching():
    from framework_cli.review.backend import ApiBackend, SubagentBackend
    from framework_cli.review.context import Bundle
    from framework_cli.review.registry import get_agent
    from framework_cli.review.runner import run_agent

    spec = get_agent("security")
    big_diff = "diff --git a/x b/x\n" + ("+# pad line\n" * 20000)  # > 128 KB
    bundle = Bundle(diff=big_diff)
    findings = run_agent(bundle, spec, SubagentBackend())  # must not blow MAX_ARG_STRLEN
    assert isinstance(findings, list)

    rep1, rep2 = {}, {}
    api = ApiBackend(api_key=os.environ["ANTHROPIC_EVAL_API_KEY"])
    run_agent(bundle, spec, api, report=rep1)
    run_agent(bundle, spec, api, report=rep2)
    assert rep2["usage"]["cache_read_input_tokens"] > 0
```

- [ ] **Step 2: Run it on the real box**

Run: `RUN_LIVE_SMOKE=1 uv run pytest tests/review/test_litellm_live_smoke.py -v`
Expected: PASS (both paths). Record the result in `ACTION_LOG.md`.

- [ ] **Step 3: Commit**

```bash
git add tests/review/test_litellm_live_smoke.py PLAN.md ACTION_LOG.md
```
```bash
git commit -m "test(review): live smoke over litellm seam + api caching passthrough (Plan 27 Task 7)"
```

---

## Task 8: Pin litellm, mypy, full gate, state + roadmap

**Files:**
- Modify: `pyproject.toml`, `uv.lock`, `PLAN.md`, `ACTION_LOG.md`, `CLAUDE.md` (only the model-facts/known-followups if affected)

- [ ] **Step 1: Pin litellm to the spike-proven version**

Set `litellm==<version from Task 1>` in `pyproject.toml`; `uv lock && uv sync`.

- [ ] **Step 2: Resolve mypy on the new module**

Run: `uv run mypy src`
If litellm lacks types and errors surface in `litellm_provider.py`/`backend.py`, add a **targeted** override to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["litellm.*"]
ignore_missing_imports = true
```
Re-run `uv run mypy src` → clean.

- [ ] **Step 3: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all green. (Use `TMPDIR=/var/tmp` if running the full suite with docker/acceptance tiers.)

- [ ] **Step 4: Update state + roadmap**

- `PLAN.md`: tick **FWK5** → Done (`→ log:#NNNN`); add the downstream `Next` items: externalize-plugin (row 2), `--with Agents` battery (row 3), `--with HotSwapAgents` battery (row 4, deps 2+3). Add the adapter-removal item (row 5) **only if Task 1 was NO-GO**.
- `ACTION_LOG.md`: completion entry summarizing the GO/NO-GO outcome, the pinned litellm version, and that parity + live smoke are green.

- [ ] **Step 5: Final commit**

```bash
git add pyproject.toml uv.lock PLAN.md ACTION_LOG.md
```
```bash
git commit -m "chore(review): pin litellm + mypy override; close Plan 27 foundation (Task 8)"
```

---

## Fallback path (only if Task 1 = NO-GO)

If `anthropic_messages` does not route to the custom provider, or does not preserve request `cache_control`, switch the seam to `litellm.completion` (OpenAI shape). Changes vs the GO plan:

- `_litellm_anthropic_messages` → `_litellm_completion`, and `_anthropic_messages` becomes `_complete` with a **bidirectional translator**:
  - inbound: Anthropic `system` blocks → a `system` role message with content blocks carrying `cache_control`; `tool_use` blocks → assistant `tool_calls` (synthesize/correlate `tool_call_id` from `ToolUseBlock.id`); `tool_result` blocks → `{"role":"tool","tool_call_id":…,"content":…}`; `TOOL_SCHEMAS` → OpenAI `{"type":"function","function":{…}}`.
  - outbound: `ModelResponse.choices[0].message` → `Message` (`.tool_calls` → `ToolUseBlock`s else `TextBlock`); OpenAI usage (`prompt_tokens_details.cached_tokens`) → `Usage.cache_read_input_tokens`.
  - set `litellm.modify_params = True` to sanitize orphaned tool calls/results.
- The `ClaudeCliLLM` handler is unchanged (it already speaks OpenAI-shaped messages via litellm's bridge).
- Add translator unit tests (inbound/outbound round-trip for bundle + agentic transcripts) before wiring.
- Keep decomposition **row 5** (adapter removal) in `PLAN.md`.

---

## Execution

**Review-model policy (restated per `CLAUDE.md` / [[subagent-review-model-pattern]]; do not let the generic "least powerful model" guidance collapse the reviewers):**
- **Implementers:** Sonnet (`claude-sonnet-4-6`); Haiku (`claude-haiku-4-5-20251001`) only for trivial mechanical steps.
- **Spec-compliance review:** Sonnet.
- **Code-quality review:** **Opus** (`claude-opus-4-8`).
- **Final / whole-branch review:** **Opus**.
- Pass `model` explicitly per role on every dispatch.

**Gate cadence (per [[gate-cadence-framework-slices]]):** this is review-infra/framework source, not template payload — the per-commit 18-app-agent gate over-fires. Use lighter per-task review + controller skip-marker commits ([[controller-skip-marker-recipe]]), then one Opus whole-branch review at the end. The implementers stage + pass the commit-gate but stop before `git commit` ([[subagent-implementers-stop-before-commit]]); the controller verifies (`git log`/`status`) and finishes each commit.

**Branch:** feature branch off `master`; PR at the end (master is protected — [[master-branch-protection-ruleset]]). Prefer a single squash-style merge and verify the tip landed ([[verify-master-content-after-pr-merge]]).

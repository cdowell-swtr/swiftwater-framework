"""Swappable model backends behind a `messages.create`-shaped seam.

`run_agent` / `run_agent_agentic` call `backend.messages.create(...)` and read
`.content` / `.usage` / `.stop_reason` — the same surface the Anthropic SDK
returns. `ApiBackend` is the SDK; `SubagentBackend` shells out to headless
`claude -p` and adapts its JSON into these dataclasses, so the review loops are
byte-identical across paid and free.
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # noqa: S404 — invoking the local `claude` CLI by fixed argv
import tempfile
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


# Tools disabled on every subagent turn so `claude -p` returns exactly ONE model turn
# (no internal agentic loop). Python owns the loop. Explicit list so a new CC tool can't
# silently re-enable looping.
_DISABLED_TOOLS = (
    "Bash",
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Glob",
    "WebFetch",
    "WebSearch",
    "Task",
    "NotebookEdit",
)

# Substrings marking a usage-limit / subscription-exhaustion error in `claude -p` output
# (case-insensitive). Matched loosely because phrasing varies by CLI version; the engine
# (20b) treats this as a hard stop, not a retry. "session limit" is the real 5-hour
# subscription-window 429 phrasing that crashed the Plan 21 baseline sweep.
_EXHAUSTION_MARKERS = (
    "usage limit",
    "rate limit reached",
    "quota",
    "limit reached",
    "session limit",
)
_EXHAUSTION_MESSAGE = "claude subscription usage limit reached"


def _exhaustion_error(text: str) -> "BackendExhausted | None":
    """If `text` (claude -p stdout/stderr or a result string) signals subscription
    exhaustion, return a BackendExhausted carrying any "resets …" hint; else None."""
    if not any(m in text.lower() for m in _EXHAUSTION_MARKERS):
        return None
    m = re.search(r"resets[^\"}\n]*", text, re.IGNORECASE)
    hint = m.group(0).strip().rstrip(".") if m else None
    msg = _EXHAUSTION_MESSAGE + (f" — {hint}" if hint else "")
    return BackendExhausted(msg, reset_hint=hint)


def _default_subprocess_runner(argv: list[str], *, input_text: str | None) -> str:
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        exhausted = _exhaustion_error(combined)
        if exhausted is not None:
            raise exhausted
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {combined.strip()}")
    return proc.stdout


def _join_system(system: list[dict[str, Any]]) -> str:
    return "\n\n".join(b.get("text", "") for b in system if b.get("text"))


_TOOL_PROTOCOL = (
    "\n\nYou DO have working read-only tools in this environment (do not claim otherwise). "
    "To call them, respond with ONLY a complete, valid JSON object — "
    '{"tool_calls":[{"name":"<tool>","input":{...}}, ...]} — and nothing else (no prose '
    "before or after, and close every brace). When done exploring and ready to report, "
    "respond with ONLY the findings JSON array (no object, no prose) — `[]` if there are "
    "none. Available tools: "
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
            btype = (
                block.get("type")
                if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if btype == "tool_use":
                name = block.get("name", "") if isinstance(block, dict) else block.name
                inp = block.get("input", {}) if isinstance(block, dict) else block.input
                parts.append(f"[assistant tool_call] {name} {json.dumps(inp)}")
            elif btype == "tool_result":
                body = (
                    block.get("content") if isinstance(block, dict) else block.content
                )
                parts.append(f"[tool_result]\n{body}")
            elif btype == "text":
                parts.append(
                    f"[{role}] {block.get('text') if isinstance(block, dict) else block.text}"
                )
    return "\n\n".join(parts)


def _render_prompt(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> str:
    if tools is None:
        # Bundle tier: a single user turn — return its text.
        if len(messages) == 1:
            last = messages[-1]["content"]
            return last if isinstance(last, str) else json.dumps(last)
        # Agentic turn-cap finalize (tools omitted this turn, but a full multi-turn
        # transcript exists): render the whole conversation so the subagent finalizes
        # with everything it explored — matching what the API path's messages array carries.
        return _render_transcript(messages)
    names = ", ".join(t.get("name", "") for t in tools)
    return _render_transcript(messages) + _TOOL_PROTOCOL + names


def _decode_tool_turn(text: str) -> list[TextBlock | ToolUseBlock] | None:
    """A `{"tool_calls":[...]}` object → ToolUseBlocks. A findings array (or anything
    else) → None → treated as the final answer. Tolerant of leading/trailing prose and
    a ``` fence (mirrors findings._extract_array's raw_decode scan for the array case)."""
    body = text
    if body.startswith("```"):
        body = body.strip("`")
    decoder = json.JSONDecoder()
    idx = body.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(body, idx)
        except json.JSONDecodeError:
            idx = body.find("{", idx + 1)
            continue
        if isinstance(obj, dict) and "tool_calls" in obj:
            blocks: list[TextBlock | ToolUseBlock] = []
            for i, call in enumerate(obj.get("tool_calls") or []):
                if isinstance(call, dict) and "name" in call:
                    blocks.append(
                        ToolUseBlock(
                            id=f"sub-{i}",
                            name=str(call["name"]),
                            input=dict(call.get("input") or {}),
                        )
                    )
            return blocks or None
        idx = body.find("{", idx + 1)
    return None


def _parse_claude_json(raw: str, tools: list[dict[str, Any]] | None) -> Message:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude -p returned non-JSON output: {raw[:120]!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"claude -p returned unexpected JSON type: {type(payload).__name__}"
        )
    if payload.get("is_error"):
        result = payload.get("result") or ""
        exhausted = _exhaustion_error(result)
        if exhausted is not None:
            raise exhausted
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
    if tools is not None:
        decoded = _decode_tool_turn(text)
        if decoded is not None:
            return Message(content=decoded, usage=usage, stop_reason=stop)
    return Message(content=[TextBlock(text=text)], usage=usage, stop_reason=stop)


class _SubagentMessages:
    def __init__(self, runner: Any) -> None:
        self._runner = runner

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        prompt = _render_prompt(messages, tools)
        sys_content = _join_system(system)
        # Write system content to a temp file (mode 0o600) so it never appears as an
        # argv element — Linux's MAX_ARG_STRLEN (~128 KB) rejects large per-argument
        # strings, and bundle-agent system blocks regularly exceed that on real targets.
        # The user prompt is passed via stdin for the same reason.
        fd, sys_path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(sys_content)
            os.chmod(sys_path, 0o600)  # noqa: S103 — temp file; owner-read-only is correct
            argv = [
                "claude",
                "-p",
                "--system-prompt-file",
                sys_path,
                "--exclude-dynamic-system-prompt-sections",
                "--output-format",
                "json",
                "--model",
                model,
            ]
            for t in _DISABLED_TOOLS:
                argv += ["--disallowed-tools", t]
            raw = self._runner(argv, input_text=prompt)
        finally:
            try:
                os.unlink(sys_path)
            except OSError:
                pass
        return _parse_claude_json(raw, tools)


class SubagentBackend:
    """The free backend: headless `claude -p` on the subscription, adapted to `Message`.

    Tools are always disabled so each call is a single model turn; the agentic loop in
    `run_agent_agentic` drives tool use via a text protocol (Task 1.4)."""

    def __init__(self, runner: Any = _default_subprocess_runner) -> None:
        self.messages = _SubagentMessages(runner)

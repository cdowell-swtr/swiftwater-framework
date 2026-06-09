from __future__ import annotations

import re
from pathlib import Path
from time import perf_counter
from typing import Any

from framework_cli.review.decisions import Decision
from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.request import TOOL_SCHEMAS, build_agentic_request


def _accum_usage(into: dict[str, int], resp: Any) -> None:
    u = getattr(resp, "usage", None)
    for k in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        into[k] = into.get(k, 0) + (getattr(u, k, 0) or 0)


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


def _within_root(p: Path, root_resolved: Path) -> bool:
    """True if `p` (after resolving symlinks) is `root` itself or a descendant of it."""
    try:
        rp = p.resolve()
    except OSError:
        return False
    return rp == root_resolved or root_resolved in rp.parents


def _safe_glob(root: Path, pattern: str) -> list[Path]:
    """`root.glob`, confined to the tree: rejects non-relative patterns and drops any
    match (e.g. via `../`) that resolves outside `root`."""
    try:
        matches = list(root.glob(pattern))
    except (ValueError, NotImplementedError) as exc:
        # pathlib rejects absolute / non-relative patterns (NotImplementedError on 3.12).
        raise _ToolError(f"invalid glob pattern: {pattern!r} ({exc})") from exc
    root_resolved = root.resolve()
    return [p for p in matches if _within_root(p, root_resolved)]


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
    if path_glob:
        paths = _safe_glob(root, path_glob)
    else:
        root_resolved = root.resolve()
        paths = [p for p in root.rglob("*") if _within_root(p, root_resolved)]
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
    for p in sorted(_safe_glob(root, pattern)):
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


_FINALIZE_INSTRUCTION = "Stop exploring. Return your findings now as a JSON array only. Do not request tools."


def _text_of(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def run_agent_agentic(
    diff: str,
    root: Path,
    spec: Any,
    client: Any,
    *,
    max_turns: int,
    report: dict | None = None,
    decisions: tuple[Decision, ...] = (),
) -> list[Finding]:
    """Drive a tool-use loop letting `spec` explore the tree at `root`; return findings.

    The diff seeds the review (cached system prefix); read_file/grep/glob let the agent
    pull whatever cross-file context it needs. At `max_turns` tool rounds we force a final
    answer so the call always terminates with a (possibly partial) findings list.
    """
    req = build_agentic_request(
        diff, spec, root=root, decisions=decisions, max_turns=max_turns
    )
    system = req.system
    messages: list[dict[str, Any]] = [{"role": "user", "content": req.user_message}]
    t0 = perf_counter()
    usage: dict[str, int] = {}
    tool_calls: list[dict[str, Any]] = []
    turns = 0
    last_resp: Any = None
    for _turn in range(max_turns):
        turns += 1
        resp = client.messages.create(
            model=spec.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        last_resp = resp
        _accum_usage(usage, resp)
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            text = _text_of(resp)
            if report is not None:
                report["usage"] = usage
                report["latency_ms"] = int((perf_counter() - t0) * 1000)
                report["stop_reason"] = getattr(resp, "stop_reason", None)
                report["raw_text"] = text
                report["turns"] = turns
                report["tool_calls"] = tool_calls
            return parse_findings(text)
        for tu in tool_uses:
            tool_calls.append({"turn": turns, "tool": tu.name, "input": dict(tu.input)})
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
    turns += 1
    resp = client.messages.create(
        model=spec.model, max_tokens=_MAX_TOKENS, system=system, messages=messages
    )
    last_resp = resp
    _accum_usage(usage, resp)
    text = _text_of(resp)
    if report is not None:
        report["usage"] = usage
        report["latency_ms"] = int((perf_counter() - t0) * 1000)
        report["stop_reason"] = getattr(last_resp, "stop_reason", None)
        report["raw_text"] = text
        report["turns"] = turns
        report["tool_calls"] = tool_calls
    return parse_findings(text)

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from framework_cli.review.findings import Finding, parse_findings  # noqa: F401

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

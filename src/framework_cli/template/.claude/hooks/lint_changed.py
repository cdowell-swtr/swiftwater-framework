"""PostToolUse hook: lint the Python file Claude Code just edited.

Reads the hook payload from stdin. If the edited file is a Python file, runs
ruff and mypy on it; on findings, prints them to stderr and exits 2 so Claude
Code surfaces them to the model to fix immediately. Non-Python files, missing
files, and unparsable payloads are silent no-ops (exit 0).

Invoked via `uv run python`, so ruff and mypy resolve from the project venv.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def edited_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path")
    if isinstance(path, str) and path:
        return path
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = edited_path(payload)
    if path is None or not path.endswith(".py") or not Path(path).is_file():
        return 0

    findings: list[str] = []
    for cmd in (["ruff", "check", path], ["mypy", path]):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except OSError:
            continue  # Tool not available: fail open rather than crash.
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            if output:
                findings.append(output)

    if findings:
        print("\n\n".join(findings), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

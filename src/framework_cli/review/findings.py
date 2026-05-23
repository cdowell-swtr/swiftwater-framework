from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class FindingsParseError(Exception):
    """The agent response could not be parsed as a findings JSON array."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: Severity
    message: str
    suggestion: str | None = None


def severity_rank(severity: str) -> int:
    return _RANK[severity]


def _extract_array(text: str) -> str:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise FindingsParseError("no JSON array found in agent response")
    return text[start : end + 1]


def parse_findings(text: str) -> list[Finding]:
    try:
        data = json.loads(_extract_array(text))
    except json.JSONDecodeError as exc:
        raise FindingsParseError(str(exc)) from exc
    if not isinstance(data, list):
        raise FindingsParseError("findings payload is not a list")
    findings: list[Finding] = []
    for item in data:
        if not isinstance(item, dict) or item.get("severity") not in _RANK:
            raise FindingsParseError(f"invalid finding: {item!r}")
        findings.append(
            Finding(
                path=str(item["path"]),
                line=int(item["line"]),
                severity=item["severity"],
                message=str(item["message"]),
                suggestion=str(item["suggestion"]) if item.get("suggestion") else None,
            )
        )
    return findings

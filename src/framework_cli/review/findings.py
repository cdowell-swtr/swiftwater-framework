from __future__ import annotations

import json
import re
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
    acknowledged: str | None = None
    stale: str | None = None


def severity_rank(severity: str) -> int:
    return _RANK[severity]


def _coerce_line(value: object) -> int:
    """Best-effort line number. Agents sometimes put a code snippet, range, or
    ``"?"`` in ``line``; that must neither crash (``int("x")`` raises) nor discard
    an otherwise-valid finding (scoring keys on path + severity, not line). Use
    the value if it's an int, the leading integer of a string if present, else 0.
    """
    if isinstance(value, bool):  # bool is an int subclass — treat as unknown
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.match(r"\s*(\d+)", value)
        if m:
            return int(m.group(1))
    return 0


def _extract_array(text: str) -> str:
    """Return the substring of the best top-level JSON findings array in ``text``.

    Agents are told to emit only a JSON array, but sometimes wrap it in prose
    that contains its own brackets — a trailing explanation (``... line [42]``),
    a second bracketed token, or a leading ``[]``/``[42]`` citation. A naive
    first-``[``..last-``]`` span over-reaches and ``json.loads`` fails with
    "Extra data" (which crashed the paid eval once); naively taking the first
    JSON list instead wrongly returns a prose ``[]`` or ``[42]``.

    Scan candidate ``[`` positions and prefer the first NON-EMPTY array of
    objects (a real findings list). Skip arrays whose elements aren't objects
    (e.g. ``[42]``) and invalid JSON. Fall back to an empty ``[]`` only if no
    findings-shaped array exists (a genuine "no findings" response).

    Returns a substring of ``text`` that ``json.loads`` accepts as a JSON list;
    raises ``FindingsParseError`` if no JSON array is found.
    """
    decoder = json.JSONDecoder()
    empty_fallback: str | None = None
    idx = text.find("[")
    while idx != -1:
        try:
            value, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx = text.find("[", idx + 1)
            continue
        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                return text[idx:end]
            if not value and empty_fallback is None:
                empty_fallback = text[idx:end]
        idx = text.find("[", idx + 1)
    if empty_fallback is not None:
        return empty_fallback
    raise FindingsParseError("no JSON array found in agent response")


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
        # Coerce each field defensively: a non-numeric `line` is tolerated
        # (see _coerce_line), but a missing required field (path/message) or a
        # type that won't stringify is wrapped as FindingsParseError rather than
        # a raw KeyError/TypeError — so the eval loop and `framework review`
        # degrade gracefully instead of crashing on a malformed agent response.
        try:
            findings.append(
                Finding(
                    path=str(item["path"]),
                    line=_coerce_line(item.get("line", 0)),
                    severity=item["severity"],
                    message=str(item["message"]),
                    suggestion=str(item["suggestion"])
                    if item.get("suggestion")
                    else None,
                    acknowledged=str(item["acknowledged"])
                    if item.get("acknowledged")
                    else None,
                    stale=str(item["stale"]) if item.get("stale") else None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FindingsParseError(
                f"invalid finding fields: {item!r} ({exc})"
            ) from exc
    return findings

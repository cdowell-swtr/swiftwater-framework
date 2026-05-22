"""Extract and hash the FRAMEWORK:BEGIN/END region of a hybrid file.

Markers are matched by the literal tokens appearing on a line, so this is agnostic to
the file's comment syntax (`<!-- -->`, `#`, ...). Exactly one balanced, in-order pair is
required; anything else is treated as "no section" (the checker reports it as damaged).
"""

from __future__ import annotations

from framework_cli.integrity.hashing import sha256_bytes

_BEGIN = "FRAMEWORK:BEGIN"
_END = "FRAMEWORK:END"


def section_span(text: str) -> tuple[int, int] | None:
    """The (begin, end) line indices inclusive of the marker lines, or None if the
    markers are absent, duplicated, or out of order."""
    lines = text.splitlines()
    begins = [i for i, line in enumerate(lines) if _BEGIN in line]
    ends = [i for i, line in enumerate(lines) if _END in line]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        return None
    return begins[0], ends[0]


def section_content(text: str) -> str | None:
    """The text strictly between the marker lines, or None if the markers are malformed."""
    span = section_span(text)
    if span is None:
        return None
    begin, end = span
    return "\n".join(text.splitlines()[begin + 1 : end])


def section_sha256(text: str) -> str | None:
    """SHA-256 of the managed section, or None if the markers are malformed."""
    content = section_content(text)
    return None if content is None else sha256_bytes(content.encode())

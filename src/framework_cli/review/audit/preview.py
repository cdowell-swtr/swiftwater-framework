"""Render a vetted changelist as an inspectable, git-applyable patch (textual edits)
plus a human-readable summary for non-textual edits (block_threshold). No mutation —
the maintainer inspects and `git apply`s themselves."""

from __future__ import annotations

import difflib

from framework_cli.review.audit.changelist import Changelist, ProposedEdit

_TEXTUAL = {"domain_prompt", "fixture", "rubric"}


def _diff(edit: ProposedEdit) -> str:
    path = edit.path or "<unknown-path>"
    before = edit.before.splitlines(keepends=True)
    after = edit.after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}")
    )


def render_patch(changelist: Changelist) -> str:
    out: list[str] = []
    notes: list[str] = []
    for ac in changelist.agents:
        for e in ac.edits:
            if e.target in _TEXTUAL and e.path:
                out.append(f"# {ac.agent}: {e.rationale}\n{_diff(e)}")
            elif e.target == "block_threshold":
                notes.append(
                    f"# {ac.agent}: set block_threshold {e.before} -> {e.after} "
                    f"({e.rationale}) — edit registry.py by hand"
                )
    for e in changelist.preamble_edits:
        if e.path or e.target == "rubric":
            e2 = ProposedEdit(
                e.target,
                e.rationale,
                e.before,
                e.after,
                e.path or "src/framework_cli/review/rubric.md",
                e.verdict,
            )
            out.append(f"# rubric: {e.rationale}\n{_diff(e2)}")
    header = "\n".join(notes)
    return (header + "\n\n" if header else "") + "\n".join(out)

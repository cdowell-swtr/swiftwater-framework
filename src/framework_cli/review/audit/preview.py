"""Render a vetted changelist as an inspectable, git-applyable patch (textual edits)
plus a human-readable summary for non-textual edits (block_threshold). No mutation —
the maintainer inspects and `git apply`s themselves."""

from __future__ import annotations

import difflib

from framework_cli.review.audit.changelist import Changelist, ProposedEdit

_TEXTUAL = {"domain_prompt", "fixture", "rubric"}
_RUBRIC_PATH = "src/framework_cli/review/rubric.md"


def _diff(edit: ProposedEdit, path: str) -> str:
    before = edit.before.splitlines(keepends=True)
    after = edit.after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}")
    )


def _resolved_path(edit: ProposedEdit) -> str | None:
    """The file an edit applies to, or None if it can't be placed in a patch. A rubric
    edit defaults to the canonical rubric.md when no explicit path is given."""
    if edit.path:
        return edit.path
    if edit.target == "rubric":
        return _RUBRIC_PATH
    return None


def _emit(label: str, edit: ProposedEdit, out: list[str], notes: list[str]) -> None:
    path = _resolved_path(edit)
    if edit.target in _TEXTUAL and path:
        out.append(f"# {label}: {edit.rationale}\n{_diff(edit, path)}")
    elif edit.target == "block_threshold":
        notes.append(
            f"# {label}: set block_threshold {edit.before} -> {edit.after} "
            f"({edit.rationale}) — edit registry.py by hand"
        )
    else:
        # Never silently drop a vetted edit: a textual edit with no placeable path is
        # recorded as a note pointing at the full changelist.
        notes.append(
            f"# {label}: {edit.target} edit not renderable as a patch "
            f"({edit.rationale}) — see changelist-full.json"
        )


def render_patch(changelist: Changelist) -> str:
    out: list[str] = []
    notes: list[str] = []
    for ac in changelist.agents:
        for e in ac.edits:
            _emit(ac.agent, e, out, notes)
    for e in changelist.preamble_edits:
        _emit("rubric", e, out, notes)
    header = "\n".join(notes)
    return (header + "\n\n" if header else "") + "\n".join(out)

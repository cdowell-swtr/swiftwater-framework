"""Render a vetted changelist as an inspectable, git-applyable patch (textual edits)
plus a human-readable notes file for non-textual edits (block_threshold, fixture
rewrites, quarantined hunks). No mutation — the maintainer inspects and `git apply`s
themselves."""

from __future__ import annotations

import difflib
import subprocess
import tempfile
from pathlib import Path

from framework_cli.review.audit.changelist import Changelist, ProposedEdit

# fixture edits are NOT simple before/after text edits — their `after` may contain
# nested diff headers that corrupt a unified patch. Route them to notes only.
_TEXTUAL = {"domain_prompt", "rubric"}
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


def _hunk_applies(patch: str, root: Path) -> bool:
    """Return True if `patch` (a unified-diff string, possibly multi-hunk) applies
    cleanly in `root`. Returns False on any error, including git not found."""
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as tf:
        tf.write(patch if patch.endswith("\n") else patch + "\n")
        p = tf.name
    try:
        return (
            subprocess.run(
                ["git", "apply", "--check", p],
                cwd=root,
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )
    except (FileNotFoundError, OSError):
        return False
    finally:
        Path(p).unlink(missing_ok=True)


def render_patch(changelist: Changelist, root: Path | None = None) -> tuple[str, str]:
    """Render a changelist as a unified diff patch plus a notes string.

    Returns ``(patch, notes)`` where:

    * ``patch`` — diff hunks only (empty string when nothing applies cleanly).
      Each accepted hunk is preceded by a ``# <label>: <rationale>`` comment
      line; git ignores those adjacent comment lines.
    * ``notes`` — human-readable lines describing fixture rewrites, quarantined
      hunks, and non-textual changes (block_threshold etc.).  Empty string when
      there is nothing to report.

    When ``root`` is given, hunks are validated *cumulatively*: a candidate
    hunk is accepted only if it applies on top of the already-accepted hunks.
    This catches the case where two edits to the same file each pass in
    isolation but conflict when combined.  When ``root`` is None the function
    falls back to best-effort: textual edits are emitted unvalidated (preserving
    the previous behaviour for tests that don't supply a real repo).
    """
    hunks: list[str] = []  # "# comment\n<raw diff>" blocks accepted so far
    accepted_diffs: list[str] = []  # raw diffs only, for cumulative validation
    notes: list[str] = []

    def _consider(label: str, edit: ProposedEdit) -> None:
        # fixture edits always go to notes — their content is a nested diff, not plain text
        if edit.target == "fixture":
            notes.append(
                f"# {label}: rewrite fixture {edit.path or '(path unknown)'} "
                f"({edit.rationale}) — see changelist-full.json"
            )
            return

        if edit.target == "block_threshold":
            notes.append(
                f"# {label}: set block_threshold {edit.before} -> {edit.after} "
                f"({edit.rationale}) — edit registry.py by hand"
            )
            return

        path = _resolved_path(edit)
        if edit.target not in _TEXTUAL or not path:
            # Never silently drop a vetted edit: record it as a note.
            notes.append(
                f"# {label}: {edit.target} edit not renderable as a patch "
                f"({edit.rationale}) — see changelist-full.json"
            )
            return

        raw = _diff(edit, path)
        if root is not None:
            # Cumulative check: trial = all previously accepted diffs + candidate, so a
            # same-file edit that conflicts with an earlier one is quarantined rather than
            # combined into a patch that fails as a whole. O(n^2) `git apply --check` calls
            # but n (textual edits per run) is small; negligible vs. the Opus calls.
            trial = "\n".join(accepted_diffs + [raw])
            if not _hunk_applies(trial, root):
                notes.append(
                    f"# {label}: {edit.target} edit did not apply cleanly to {path} "
                    f"({edit.rationale}) — see changelist-full.json"
                )
                return

        accepted_diffs.append(raw)
        hunks.append(f"# {label}: {edit.rationale}\n{raw}")

    for ac in changelist.agents:
        for e in ac.edits:
            _consider(ac.agent, e)
    for e in changelist.preamble_edits:
        _consider("rubric", e)

    return "\n".join(hunks), "\n".join(notes)

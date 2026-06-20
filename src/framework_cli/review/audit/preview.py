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
_AGENTS_DIR = "src/framework_cli/review/agents"


def _diff(edit: ProposedEdit, path: str) -> str:
    """Best-effort standalone diff of before→after (used only when no repo root is given
    to anchor against — produces a `@@ -1 +1 @@` hunk that git apply can't reliably place)."""
    before = edit.before.splitlines(keepends=True)
    after = edit.after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(before, after, fromfile=f"a/{path}", tofile=f"b/{path}")
    )


def _anchored_diff(edit: ProposedEdit, path: str, root: Path) -> str | None:
    """A unified diff that applies `before`→`after` at its REAL location in `root/path`,
    with surrounding context + correct line numbers, so `git apply` can place it. Returns
    None when `before` is not a unique exact substring of the file (not found, ambiguous,
    or the file is absent) — the caller then quarantines the edit to notes. This is what
    makes a model-proposed prose rewrite into an actually-applyable hunk."""
    full = root / path
    if not full.is_file():
        return None
    content = full.read_text()
    if not edit.before or content.count(edit.before) != 1:
        return None
    updated = content.replace(edit.before, edit.after, 1)
    return "".join(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _resolved_path(edit: ProposedEdit, label: str) -> str | None:
    """The file an edit applies to, or None if it can't be placed in a patch. When the
    model omits a path: a rubric edit defaults to the canonical rubric.md, and a
    domain_prompt edit defaults to its agent's prompt file (agents/<agent>.md, derived
    from the changelist label). A wrong derived path is still caught by the cumulative
    git-apply check and quarantined to notes."""
    if edit.path:
        return edit.path
    if edit.target == "rubric":
        return _RUBRIC_PATH
    if edit.target == "domain_prompt" and label and label != "rubric":
        return f"{_AGENTS_DIR}/{label}.md"
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

        path = _resolved_path(edit, label)
        if edit.target not in _TEXTUAL or not path:
            # Never silently drop a vetted edit: record it as a note.
            notes.append(
                f"# {label}: {edit.target} edit not renderable as a patch "
                f"({edit.rationale}) — see changelist-full.json"
            )
            return

        if root is not None:
            # Anchor the diff against the real file so git apply can place it, then do a
            # cumulative check: trial = all previously accepted diffs + candidate, so a
            # same-file edit that conflicts with an earlier one is quarantined rather than
            # combined into a patch that fails as a whole. O(n^2) `git apply --check` calls
            # but n (textual edits per run) is small; negligible vs. the Opus calls.
            raw = _anchored_diff(edit, path, root)
            if raw is None or not _hunk_applies(
                "\n".join(accepted_diffs + [raw]), root
            ):
                notes.append(
                    f"# {label}: {edit.target} edit did not apply cleanly to {path} "
                    f"({edit.rationale}) — see changelist-full.json"
                )
                return
        else:
            raw = _diff(edit, path)

        accepted_diffs.append(raw)
        hunks.append(f"# {label}: {edit.rationale}\n{raw}")

    for ac in changelist.agents:
        for e in ac.edits:
            _consider(ac.agent, e)
    for e in changelist.preamble_edits:
        _consider("rubric", e)

    return "\n".join(hunks), "\n".join(notes)

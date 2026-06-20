import subprocess
from pathlib import Path

from framework_cli.review.audit.changelist import AgentChange, Changelist, ProposedEdit
from framework_cli.review.audit.preview import render_patch


def test_render_patch_emits_unified_diff_for_domain_edit():
    cl = Changelist(
        agents=[
            AgentChange(
                "security",
                "high",
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="r",
                        before="old line\n",
                        after="new line\n",
                        path="src/framework_cli/review/agents/security.md",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, _ = render_patch(cl)
    assert "--- a/src/framework_cli/review/agents/security.md" in patch
    assert "+new line" in patch and "-old line" in patch


def test_render_patch_skips_non_textual_targets():
    cl = Changelist(
        agents=[
            AgentChange(
                "security",
                "high",
                edits=[
                    ProposedEdit(
                        target="block_threshold",
                        rationale="r",
                        before="info",
                        after="high",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    _, notes = render_patch(cl)
    assert "block_threshold" in notes
    assert "security" in notes


def test_render_patch_renders_path_less_rubric_edit():
    # a per-agent rubric edit with no path defaults to the canonical rubric.md — never
    # silently dropped (the Opus branch-end finding).
    cl = Changelist(
        agents=[
            AgentChange(
                "security",
                None,
                edits=[
                    ProposedEdit(
                        target="rubric",
                        rationale="tighten severity ladder",
                        before="old\n",
                        after="new\n",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, _ = render_patch(cl)
    assert "src/framework_cli/review/rubric.md" in patch
    assert "+new" in patch and "-old" in patch


def test_rendered_patch_applies_with_git(tmp_path: Path):
    # a tiny git repo with one file; render a patch editing it; `git apply --check` must pass
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    f = repo / "agents.md"
    f.write_text("alpha\nbeta\ngamma\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    cl = Changelist(
        agents=[
            AgentChange(
                "x",
                None,
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="swap beta",
                        before="alpha\nbeta\ngamma\n",
                        after="alpha\nBETA\ngamma\n",
                        path="agents.md",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, _ = render_patch(cl)
    (repo / "p.patch").write_text(patch if patch.endswith("\n") else patch + "\n")
    # git apply --check validates the patch applies cleanly (NO --allow-empty)
    r = subprocess.run(
        ["git", "apply", "--check", "p.patch"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"git apply --check failed: {r.stderr}\n---\n{patch}"


def test_render_patch_routes_fixture_edits_to_notes_not_hunks():
    cl = Changelist(
        agents=[
            AgentChange(
                "accessibility",
                None,
                edits=[
                    ProposedEdit(
                        target="fixture",
                        rationale="add good pair",
                        before="(no good fixture)",
                        after=(
                            "diff --git a/x.tsx b/x.tsx\n"
                            "--- a/x.tsx\n"
                            "+++ b/x.tsx\n"
                            "@@ -1 +1 @@\n"
                            "-a\n"
                            "+b\n"
                        ),
                        path="tests/eval/fixtures/accessibility/good/semantic-button",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, notes = render_patch(cl)
    assert "diff --git a/x.tsx" not in patch
    assert "tests/eval/fixtures/accessibility/good/semantic-button" in notes
    assert "changelist-full.json" in notes


def test_render_patch_quarantines_non_applying_hunk(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "f.md").write_text("real content\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    cl = Changelist(
        agents=[
            AgentChange(
                "x",
                None,
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="stale before",
                        before="WRONG content\n",
                        after="new\n",
                        path="f.md",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, notes = render_patch(cl, root=tmp_path)
    # patch is empty (no hunks) — not comments-only — so plain git apply is fine
    assert patch == ""
    assert "changelist-full.json" in notes  # the bad hunk was quarantined to notes


def test_render_patch_valid_domain_edit_still_applies(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "f.md").write_text("alpha\nbeta\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    cl = Changelist(
        agents=[
            AgentChange(
                "x",
                None,
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="ok",
                        before="alpha\nbeta\n",
                        after="alpha\nBETA\n",
                        path="f.md",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, _ = render_patch(cl, root=tmp_path)
    assert "BETA" in patch
    (tmp_path / "p.patch").write_text(patch if patch.endswith("\n") else patch + "\n")
    # NO --allow-empty: patch has real hunks, plain git apply must succeed
    assert (
        subprocess.run(["git", "apply", "--check", "p.patch"], cwd=tmp_path).returncode
        == 0
    )


def test_render_patch_cumulative_same_file_conflict_quarantined(tmp_path: Path):
    """Two edits to the same file: each passes alone vs the original, but they
    conflict when combined. The second must be quarantined to notes."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "r.md").write_text("alpha\nbeta\ngamma\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    cl = Changelist(
        agents=[
            AgentChange(
                "x",
                None,
                edits=[
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="e1",
                        before="alpha\nbeta\ngamma\n",
                        after="ALPHA\nbeta\ngamma\n",
                        path="r.md",
                    ),
                    ProposedEdit(
                        target="domain_prompt",
                        rationale="e2",
                        before="alpha\nbeta\ngamma\n",
                        after="alpha\nBETA\ngamma\n",
                        path="r.md",
                    ),
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, notes = render_patch(cl, root=tmp_path)
    # The combined patch must apply cleanly (only the first hunk is accepted)
    (tmp_path / "p.patch").write_text(patch if patch.endswith("\n") else patch + "\n")
    assert (
        subprocess.run(["git", "apply", "--check", "p.patch"], cwd=tmp_path).returncode
        == 0
    )
    # The second, conflicting edit was quarantined
    assert "e2" in notes


def test_render_patch_all_notes_yields_empty_patch():
    """When every edit routes to notes, patch is an empty string (not comments-only).
    Plain `git apply` on an empty string would exit 128 — but we never write the file
    when patch is empty."""
    cl = Changelist(
        agents=[
            AgentChange(
                "x",
                None,
                edits=[
                    ProposedEdit(
                        target="fixture",
                        rationale="rw",
                        before="a",
                        after="b",
                        path="tests/eval/fixtures/x/good/y",
                    )
                ],
                fixture_verdicts={},
            )
        ],
        preamble_edits=[],
    )
    patch, notes = render_patch(cl)
    assert patch == ""  # no hunks → empty string, not comments-only
    assert "rw" in notes

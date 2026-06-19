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
    patch = render_patch(cl)
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
    patch = render_patch(cl)
    assert "block_threshold" in patch
    assert "security" in patch


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
    patch = render_patch(cl)
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
    patch = render_patch(cl)
    (repo / "p.patch").write_text(patch)
    # git apply --check validates the patch applies cleanly
    r = subprocess.run(
        ["git", "apply", "--check", "p.patch"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"git apply --check failed: {r.stderr}\n---\n{patch}"

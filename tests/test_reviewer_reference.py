"""FWK3 — keep the generated reviewer reference page in sync with the registry + blurbs."""

from pathlib import Path

from framework_cli.review.reference_doc import _BLURBS, render_reference
from framework_cli.review.registry import agent_names

_DOC = (
    Path(__file__).resolve().parents[1]
    / "documentation"
    / "reference"
    / "review-agents.md"
)


def test_reference_doc_is_current():
    assert _DOC.read_text() == render_reference(), (
        "documentation/reference/review-agents.md is stale — run "
        "`uv run python scripts/gen_reviewer_reference.py`"
    )


def test_every_agent_has_a_blurb():
    assert set(agent_names()) <= set(_BLURBS), (
        f"missing blurbs: {set(agent_names()) - set(_BLURBS)}"
    )


def test_no_orphan_blurbs():
    assert set(_BLURBS) <= set(agent_names()), (
        f"orphan blurbs (not in registry): {set(_BLURBS) - set(agent_names())}"
    )

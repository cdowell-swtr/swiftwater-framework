#!/usr/bin/env python
"""Regenerate documentation/reference/review-agents.md from the review registry + blurbs."""

from pathlib import Path

from framework_cli.review.reference_doc import render_reference

_DOC = (
    Path(__file__).resolve().parents[1]
    / "documentation"
    / "reference"
    / "review-agents.md"
)

if __name__ == "__main__":
    _DOC.write_text(render_reference())
    print(f"wrote {_DOC}")

from pathlib import Path

import pytest

from framework_cli.review.decisions import (
    Decision,
    active_decision_ids,
    load_decisions,
    relevant_decisions,
    render_decisions_block,
)


def _write(
    d: Path, name: str, *, id: str, status: str, agents: str, premise: str = "p"
) -> None:
    (d / name).write_text(
        f"---\nid: {id}\nstatus: {status}\nagents: [{agents}]\n"
        f"concern: c\npremise: {premise!r}\ndate: 2026-06-01\n---\n\nrationale\n"
    )


def test_relevant_decisions_filters_by_agent_and_active_status(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    _write(dec, "a.md", id="DEC-0001", status="accepted", agents="data-integrity")
    _write(dec, "b.md", id="DEC-0002", status="deferred", agents="data-integrity")
    _write(dec, "c.md", id="DEC-0003", status="retired", agents="data-integrity")
    _write(dec, "d.md", id="DEC-0004", status="whatever-typo", agents="data-integrity")
    _write(dec, "e.md", id="DEC-0005", status="accepted", agents="security")
    got = {d.id for d in relevant_decisions("data-integrity", tmp_path)}
    assert got == {"DEC-0001", "DEC-0002"}


def test_relevant_decisions_empty_when_dir_missing(tmp_path):
    assert relevant_decisions("data-integrity", tmp_path) == []


def test_missing_premise_is_rejected(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    (dec / "bad.md").write_text(
        "---\nid: DEC-0009\nstatus: accepted\nagents: [security]\nconcern: c\ndate: 2026-06-01\n---\n"
    )
    with pytest.raises(ValueError, match="premise"):
        load_decisions(dec)


def test_active_decision_ids(tmp_path):
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    _write(dec, "a.md", id="DEC-0001", status="accepted", agents="security")
    _write(dec, "b.md", id="DEC-0003", status="invalidated", agents="security")
    assert active_decision_ids(tmp_path) == {"DEC-0001"}


def test_malformed_frontmatter_is_rejected(tmp_path):
    # A human-authored file that opens frontmatter but omits the closing '---'
    # should raise a friendly error, not an opaque unpacking traceback.
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    (dec / "bad.md").write_text(
        "---\nid: DEC-1\nstatus: accepted\nagents: [security]\n"
    )
    with pytest.raises(ValueError, match="frontmatter"):
        load_decisions(dec)


def test_render_decisions_block_none_when_empty():
    assert render_decisions_block([]) is None


def test_render_decisions_block_contains_records_and_protocol():
    d = Decision(
        id="DEC-0001",
        status="accepted",
        agents=("data-integrity",),
        concern="prune commits internally",
        premise="only caller is the beat task",
        body="rationale",
        source="DEC-0001.md",
    )
    block = render_decisions_block([d])
    assert block is not None
    assert "DEC-0001" in block and "only caller is the beat task" in block
    assert "acknowledged:" in block and "stale:" in block  # the protocol preamble


def test_live_loaders_fail_open_on_malformed(tmp_path):
    # load_decisions raises (validation), but the LIVE loaders degrade to empty so a bad
    # decisions file never crashes the gate/review (the primary consumers).
    dec = tmp_path / "docs" / "superpowers" / "decisions"
    dec.mkdir(parents=True)
    (dec / "bad.md").write_text(
        "---\nid: DEC-1\nstatus: accepted\nagents: [security]\n"
    )
    with pytest.raises(ValueError):
        load_decisions(dec)  # strict path still raises
    assert relevant_decisions("security", tmp_path) == []  # fail-open
    assert active_decision_ids(tmp_path) == set()  # fail-open

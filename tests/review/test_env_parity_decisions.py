"""Integration test: review-env-parity rides the agent-agnostic decisions-log mechanism.

The runner calls `relevant_decisions(short, root)` where `short = spec.name.removeprefix("review-")`,
so for `review-env-parity` the token is `"env-parity"`.  Decision files must use that same
short form in their `agents:` list.
"""

from pathlib import Path

from framework_cli.review.decisions import (
    relevant_decisions,
    render_decisions_block,
)

_DECISION = """\
---
id: DEC-ENVPARITY-EX
status: accepted
agents: [env-parity]
concern: "traefik is intentionally dev-only"
premise: >
  Prod TLS is terminated by the platform load balancer, not an in-stack reverse proxy,
  so the app needs no traefik service in staging/prod. STALE if the app gains a runtime
  dependency on traefik in a deployed environment.
date: 2026-06-04
---

Traefik runs only in the dev overlay to provide local HTTPS via mkcert. Reviewed and accepted.
"""


def _write_decision(root: Path) -> None:
    d = root / "docs" / "superpowers" / "decisions"
    d.mkdir(parents=True)
    (d / "DEC-ENVPARITY-EX.md").write_text(_DECISION)


def test_env_parity_decision_is_relevant_and_renders(tmp_path):
    _write_decision(tmp_path)
    decs = relevant_decisions("env-parity", tmp_path)
    assert [d.id for d in decs] == ["DEC-ENVPARITY-EX"]
    block = render_decisions_block(decs)
    assert block is not None
    assert "DEC-ENVPARITY-EX" in block
    assert "acknowledged" in block


def test_env_parity_decision_not_visible_to_other_agents(tmp_path):
    _write_decision(tmp_path)
    # A different agent's short name should not pick up env-parity's decision.
    assert relevant_decisions("security", tmp_path) == []


def test_acknowledged_finding_is_segregated(tmp_path):
    from framework_cli.review.analyze import Record, acknowledged_findings

    record = Record(
        agent="review-env-parity",
        kind="bad",
        case="traefik-dev-only",
        repeat=0,
        seeded_file=None,
        findings=[
            {
                "path": "infra/compose/dev.yml",
                "line": 40,
                "severity": "high",
                "message": "traefik is dev-only",
                "acknowledged": "DEC-ENVPARITY-EX",
            }
        ],
        usage={},
        latency_ms=None,
        stop_reason=None,
        raw_text="",
        turns=1,
        tool_calls=[],
    )
    # With a matching active_ids set, the finding is collected.
    acked = acknowledged_findings([record], {"DEC-ENVPARITY-EX"})
    assert len(acked) == 1
    item = acked[0]
    assert item["acknowledged"] == "DEC-ENVPARITY-EX"
    assert item["agent"] == "review-env-parity"

    # Without the id in active_ids, the finding is NOT collected (it would block instead).
    not_acked = acknowledged_findings([record], set())
    assert not_acked == []

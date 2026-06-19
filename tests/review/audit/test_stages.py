import json
from pathlib import Path

from framework_cli.review.audit.brief import build_audit_brief
from framework_cli.review.audit.changelist import Changelist, ProposedEdit, Verdict
from framework_cli.review.audit.stages import audit_agent, reconcile, refute
from tests.review.audit.conftest import StubBackend


def test_audit_agent_parses_structured_report(tmp_path: Path):
    report_json = json.dumps(
        {
            "agent": "security",
            "severity_issues": ["over-flags hardening as high"],
            "scope_creep": [],
            "fixture_verdicts": {"good/clean": "clean"},
            "proposed_block_threshold": "high",
            "edits": [
                {
                    "target": "domain_prompt",
                    "rationale": "tighten",
                    "before": "x",
                    "after": "y",
                }
            ],
        }
    )
    backend = StubBackend([report_json])
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["agent"] == "security"
    assert report["proposed_block_threshold"] == "high"
    assert report["edits"][0]["target"] == "domain_prompt"
    sent = backend.messages.calls[0]["system"]
    sent_text = " ".join(b.get("text", "") for b in sent)
    assert "## Your domain: `review-security`" in sent_text
    assert "consistency" in sent_text.lower()


def test_audit_agent_tolerates_fenced_json(tmp_path: Path):
    backend = StubBackend(['```json\n{"agent":"security","edits":[]}\n```'])
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["agent"] == "security"
    assert report["edits"] == []


def test_audit_agent_tolerates_surrounding_prose(tmp_path: Path):
    backend = StubBackend(
        ['Here is the report:\n{"agent":"security","edits":[]}\nHope that helps!']
    )
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["agent"] == "security"
    assert report["edits"] == []


def test_audit_agent_normalizes_string_null_threshold(tmp_path: Path):
    backend = StubBackend(['{"agent":"usability","proposed_block_threshold":"null"}'])
    brief = build_audit_brief("usability", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend, root=Path.cwd())
    assert report["proposed_block_threshold"] is None


def test_reconcile_merges_reports_into_changelist():
    cl_json = json.dumps(
        {
            "agents": [
                {
                    "agent": "security",
                    "proposed_block_threshold": "high",
                    "edits": [
                        {
                            "target": "domain_prompt",
                            "rationale": "r",
                            "before": "a",
                            "after": "b",
                        }
                    ],
                    "fixture_verdicts": {},
                }
            ],
            "preamble_edits": [],
        }
    )
    backend = StubBackend([cl_json])
    reports = [
        {
            "agent": "security",
            "edits": [],
            "proposed_block_threshold": "high",
            "severity_issues": ["ZZmarkerReportOnly"],
        },
        {"agent": "usability", "edits": [], "proposed_block_threshold": None},
    ]
    roster = {"security": "high", "usability": None}
    cl = reconcile(reports, roster, backend)
    assert isinstance(cl, Changelist)
    assert cl.agents[0].agent == "security"
    sent = " ".join(b.get("text", "") for b in backend.messages.calls[0]["system"])
    # both the reports (report-only marker) AND the roster are embedded
    assert "ZZmarkerReportOnly" in sent
    assert "usability" in sent and "security" in sent


def test_reconcile_normalizes_string_null_threshold():
    cl_json = json.dumps(
        {
            "agents": [
                {
                    "agent": "usability",
                    "proposed_block_threshold": "null",
                    "edits": [],
                    "fixture_verdicts": {},
                }
            ],
            "preamble_edits": [],
        }
    )
    cl = reconcile([], {"usability": None}, StubBackend([cl_json]))
    assert cl.agents[0].proposed_block_threshold is None


def test_refute_returns_verdict_majority_survives():
    backend = StubBackend(
        [
            json.dumps({"refuted": False, "reason": "edit is sound"}),
            json.dumps({"refuted": False, "reason": "still catches bad case"}),
            json.dumps({"refuted": True, "reason": "loosens bar for bad/Y"}),
        ]
    )
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=3)
    assert isinstance(v, Verdict)
    assert v.refuted is False
    assert v.votes == 2


def test_refute_majority_refutes_kills_change():
    backend = StubBackend(
        [
            json.dumps({"refuted": True, "reason": "x"}),
            json.dumps({"refuted": True, "reason": "y"}),
            json.dumps({"refuted": False, "reason": "z"}),
        ]
    )
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=3)
    assert v.refuted is True
    assert "x" in v.refutation or "y" in v.refutation

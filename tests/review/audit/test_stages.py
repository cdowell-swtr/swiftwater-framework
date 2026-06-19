import json
from pathlib import Path

from framework_cli.review.audit.brief import build_audit_brief
from framework_cli.review.audit.stages import audit_agent
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

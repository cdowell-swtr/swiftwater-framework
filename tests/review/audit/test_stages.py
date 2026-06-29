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
    report = audit_agent(brief, backend)
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
    report = audit_agent(brief, backend)
    assert report["agent"] == "security"
    assert report["edits"] == []


def test_audit_agent_tolerates_surrounding_prose(tmp_path: Path):
    backend = StubBackend(
        ['Here is the report:\n{"agent":"security","edits":[]}\nHope that helps!']
    )
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend)
    assert report["agent"] == "security"
    assert report["edits"] == []


def test_audit_agent_normalizes_string_null_threshold(tmp_path: Path):
    backend = StubBackend(['{"agent":"usability","proposed_block_threshold":"null"}'])
    brief = build_audit_brief("usability", root=Path.cwd(), baseline_dir=None)
    report = audit_agent(brief, backend)
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


# --- FWK46: bounded re-prompt of an unparseable skeptic + loud persistent failure ---


def test_refute_reprompts_unparseable_skeptic_then_parses():
    """A transient parse slip is recovered by a bounded re-prompt — the vote is NOT
    silently dropped (FWK43: a dropped vote flips strict-majority-survives)."""
    responses = iter(
        [
            "I think this edit is fine, honestly",  # unparseable first try
            json.dumps({"refuted": False, "reason": "sound on retry"}),  # parses
        ]
    )
    backend = StubBackend(lambda _system, _messages: next(responses))
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=1, parse_retries=2)
    assert v.refuted is False  # the recovered vote survives
    assert v.votes == 1
    assert v.parse_failures == 0
    assert len(backend.messages.calls) == 2  # one re-prompt was spent


def test_refute_persistent_parse_failure_is_loud_and_recorded():
    """When re-prompts are exhausted the skeptic is recorded as a parse failure and
    surfaced via the log callable — never a silent non-vote."""
    backend = StubBackend(lambda _system, _messages: "still not json")
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    seen: list[str] = []
    v = refute(edit, "security", backend, skeptics=1, parse_retries=2, log=seen.append)
    assert v.parse_failures == 1
    assert v.votes == 0
    assert v.refuted is True  # conservative default-to-refuted is preserved
    assert len(backend.messages.calls) == 3  # 1 initial + 2 re-prompts
    assert any("security" in m and "parse" in m.lower() for m in seen)


def test_refute_treats_persistent_wrong_shape_reply_as_parse_failure():
    """FWK122: a JSON ARRAY (or other non-dict) reply must not crash refute via
    `.get()` — it's routed through the same bounded-retry / loud-non-survival path
    FWK46 built for unparseable replies."""
    backend = StubBackend(
        lambda _s, _m: json.dumps([{"refuted": False}])
    )  # a JSON array
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=1, parse_retries=2)
    assert v.parse_failures == 1
    assert v.votes == 0
    assert v.refuted is True
    assert len(backend.messages.calls) == 3  # 1 initial + 2 re-prompts, no crash


def test_refute_recovers_from_transient_wrong_shape_reply():
    """A wrong-shape reply that self-corrects on re-prompt is recovered, not dropped."""
    responses = iter(
        [
            json.dumps([{"refuted": False}]),  # wrong shape (array) first
            json.dumps({"refuted": False, "reason": "ok on retry"}),  # valid dict
        ]
    )
    backend = StubBackend(lambda _s, _m: next(responses))
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=1, parse_retries=2)
    assert v.refuted is False
    assert v.votes == 1
    assert v.parse_failures == 0
    assert len(backend.messages.calls) == 2


def test_refute_retries_are_per_skeptic_not_shared():
    """One skeptic's re-prompts don't consume another skeptic's budget; a later
    skeptic still parses cleanly on its first attempt."""
    responses = iter(
        [
            "garbage",  # skeptic 0, attempt 0
            "garbage",  # skeptic 0, attempt 1
            "garbage",  # skeptic 0, attempt 2 (exhausted → parse failure)
            json.dumps({"refuted": False, "reason": "ok"}),  # skeptic 1, first try
        ]
    )
    backend = StubBackend(lambda _system, _messages: next(responses))
    edit = ProposedEdit(target="domain_prompt", rationale="r", before="a", after="b")
    v = refute(edit, "security", backend, skeptics=2, parse_retries=2)
    assert v.parse_failures == 1
    assert v.votes == 1
    assert len(backend.messages.calls) == 4


def test_reconcile_normalizes_review_prefixed_agent_names():
    cl_json = json.dumps(
        {
            "agents": [
                {
                    "agent": "review-application-logic",
                    "proposed_block_threshold": "info",
                    "edits": [],
                    "fixture_verdicts": {},
                },
                {
                    "agent": "security",
                    "proposed_block_threshold": "high",
                    "edits": [],
                    "fixture_verdicts": {},
                },
            ],
            "preamble_edits": [],
        }
    )
    cl = reconcile(
        [],
        {"application-logic": "info", "security": "high"},
        StubBackend([cl_json]),
    )
    assert {a.agent for a in cl.agents} == {"application-logic", "security"}


def test_reconcile_drops_unknown_agent_with_note():
    cl_json = json.dumps(
        {
            "agents": [
                {
                    "agent": "totally-made-up",
                    "proposed_block_threshold": "high",
                    "edits": [],
                    "fixture_verdicts": {},
                },
                {
                    "agent": "security",
                    "proposed_block_threshold": "high",
                    "edits": [],
                    "fixture_verdicts": {},
                },
            ],
            "preamble_edits": [],
        }
    )
    seen: list[str] = []
    cl = reconcile([], {"security": "high"}, StubBackend([cl_json]), log=seen.append)
    assert {a.agent for a in cl.agents} == {"security"}
    assert any("totally-made-up" in m for m in seen)

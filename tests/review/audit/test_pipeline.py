import json
from pathlib import Path

import pytest

from framework_cli.review.audit.pipeline import CheckpointProvenanceError, run_audit
from tests.review.audit.conftest import StubBackend


# ---------------------------------------------------------------------------
# Test A — Defect 1 (CRITICAL): a refute-item failure must NOT crash the pipeline
# ---------------------------------------------------------------------------


def test_run_audit_survives_a_refute_item_failure(tmp_path: Path):
    """One skeptic work-item raises → run_stage records {"item":…,"error":…}.
    The vmap build must skip that record (no 'agent'/'idx'/'verdict' keys) and
    the affected edit must survive as unverified (verdict is None)."""

    def scripted(system, messages):
        text = " ".join(b.get("text", "") for b in system)
        if "reviewer-prompt AUDITOR" in text:
            return json.dumps(
                {
                    "agent": "security",
                    "edits": [],
                    "proposed_block_threshold": "high",
                    "fixture_verdicts": {},
                }
            )
        if "roster RECONCILER" in text:
            return json.dumps(
                {
                    "agents": [
                        {
                            "agent": "security",
                            "proposed_block_threshold": "high",
                            "edits": [
                                {
                                    "target": "domain_prompt",
                                    "rationale": "ok",
                                    "before": "a",
                                    "after": "GOOD",
                                },
                                {
                                    "target": "domain_prompt",
                                    "rationale": "boom",
                                    "before": "c",
                                    "after": "BOOM",
                                },
                            ],
                            "fixture_verdicts": {},
                        }
                    ],
                    "preamble_edits": [],
                }
            )
        if "adversarial SKEPTIC" in text:
            if "--- after ---\nBOOM" in text:
                raise RuntimeError("skeptic boom")
            return json.dumps({"refuted": False, "reason": "fine"})
        return "{}"

    cl = run_audit(
        ["security"],
        backend=StubBackend(scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=tmp_path / "out",
        skeptics=1,
    )
    afters = {e.after: e for e in cl.agents[0].edits}
    # pipeline completed; GOOD got 1 survive → kept with verdict
    assert (
        afters["GOOD"].verdict is not None and afters["GOOD"].verdict.refuted is False
    )
    # BOOM's refute raised → verdict None → kept as unverified
    assert afters["BOOM"].verdict is None


# ---------------------------------------------------------------------------
# Test B — Defect 2 (IMPORTANT): resume reuses the pinned reconcile output
# ---------------------------------------------------------------------------


def test_run_audit_resume_reuses_pinned_reconcile(tmp_path: Path):
    """On resume=True, Stage 2 (reconcile) must be read from the checkpoint file,
    NOT re-called. The resumed result must match the FIRST run's edits even when
    the new backend would reconcile to a different edit set."""

    out = tmp_path / "out"

    def make_scripted(recon_edits_after: str):
        def scripted(system, messages):
            text = " ".join(b.get("text", "") for b in system)
            if "reviewer-prompt AUDITOR" in text:
                return json.dumps(
                    {
                        "agent": "security",
                        "edits": [],
                        "proposed_block_threshold": "high",
                        "fixture_verdicts": {},
                    }
                )
            if "roster RECONCILER" in text:
                return json.dumps(
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
                                        "after": recon_edits_after,
                                    }
                                ],
                                "fixture_verdicts": {},
                            }
                        ],
                        "preamble_edits": [],
                    }
                )
            if "adversarial SKEPTIC" in text:
                return json.dumps({"refuted": False, "reason": "ok"})
            return "{}"

        return scripted

    # First run — reconcile returns "FIRST"
    cl1 = run_audit(
        ["security"],
        backend=StubBackend(make_scripted("FIRST")),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    assert [e.after for e in cl1.agents[0].edits] == ["FIRST"]

    # Resume — backend would reconcile to "SECOND", but pinned checkpoint wins
    cl2 = run_audit(
        ["security"],
        backend=StubBackend(make_scripted("SECOND")),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
        resume=True,
    )
    assert [e.after for e in cl2.agents[0].edits] == [
        "FIRST"
    ]  # pinned reconcile reused


def _scripted(system, messages):
    text = " ".join(b.get("text", "") for b in system)
    if "reviewer-prompt AUDITOR" in text:
        return json.dumps(
            {
                "agent": "security",
                "edits": [
                    {
                        "target": "domain_prompt",
                        "rationale": "r",
                        "before": "a",
                        "after": "b",
                    }
                ],
                "proposed_block_threshold": "high",
                "fixture_verdicts": {},
            }
        )
    if "roster RECONCILER" in text:
        return json.dumps(
            {
                "agents": [
                    {
                        "agent": "security",
                        "proposed_block_threshold": "high",
                        "edits": [
                            {
                                "target": "domain_prompt",
                                "rationale": "keep",
                                "before": "a",
                                "after": "b",
                            },
                            {
                                "target": "domain_prompt",
                                "rationale": "drop",
                                "before": "c",
                                "after": "d",
                            },
                        ],
                        "fixture_verdicts": {},
                    }
                ],
                "preamble_edits": [],
            }
        )
    if "adversarial SKEPTIC" in text:
        # refute only the "drop" change (after == "d")
        refuted = "--- after ---\nd" in text
        return json.dumps({"refuted": refuted, "reason": "x"})
    return "{}"


def test_run_audit_logs_stage_transitions(tmp_path: Path):
    """run_audit emits Stage 1 / Stage 2 / Stage 3 + vetted log lines via the log param."""
    logged: list[str] = []

    run_audit(
        ["security"],
        backend=StubBackend(_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=tmp_path / "out",
        skeptics=1,
        log=logged.append,
    )

    joined = "\n".join(logged)
    assert "Stage 1" in joined
    assert "Stage 2" in joined
    assert "Stage 3" in joined
    assert "vetted" in joined


def test_run_audit_surfaces_persistent_skeptic_parse_failure(tmp_path: Path):
    """FWK46: a skeptic that stays unparseable is surfaced loudly through run_audit's
    log AND recorded as parse_failures in the persisted full changelist — not a silent
    dropped vote."""

    def scripted(system, messages):
        text = " ".join(b.get("text", "") for b in system)
        if "reviewer-prompt AUDITOR" in text:
            return json.dumps(
                {
                    "agent": "security",
                    "edits": [],
                    "proposed_block_threshold": "high",
                    "fixture_verdicts": {},
                }
            )
        if "roster RECONCILER" in text:
            return json.dumps(
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
        if "adversarial SKEPTIC" in text:
            return "not parseable at all"
        return "{}"

    logged: list[str] = []
    run_audit(
        ["security"],
        backend=StubBackend(scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=tmp_path / "out",
        skeptics=1,
        log=logged.append,
    )

    assert any("parse" in m.lower() and "security" in m for m in logged)
    full = json.loads((tmp_path / "out" / "changelist-full.json").read_text())
    verdict = full["agents"][0]["edits"][0]["verdict"]
    assert verdict["parse_failures"] == 1


# ---------------------------------------------------------------------------
# FWK47 — --resume checkpoint-provenance guard
# ---------------------------------------------------------------------------


def _noop_scripted(system, messages):
    """An audit that proposes no edits — Stage 3 has nothing to refute, so the
    provenance guard (which fires before any stage) is what these tests exercise."""
    text = " ".join(b.get("text", "") for b in system)
    if "AUDITOR" in text:
        return json.dumps(
            {
                "agent": "security",
                "edits": [],
                "proposed_block_threshold": "high",
                "fixture_verdicts": {},
            }
        )
    if "RECONCILER" in text:
        return json.dumps({"agents": [], "preamble_edits": []})
    return "{}"


def test_run_audit_writes_provenance_on_fresh_run(tmp_path: Path):
    out = tmp_path / "out"
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    prov = json.loads((out / "audit-provenance.json").read_text())
    assert prov["fingerprint"]
    assert prov["targets"] == "security"
    assert prov["skeptics"] == "1"


def test_run_audit_resume_refuses_when_skeptics_changed(tmp_path: Path):
    out = tmp_path / "out"
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    with pytest.raises(CheckpointProvenanceError) as exc:
        run_audit(
            ["security"],
            backend=StubBackend(_noop_scripted),
            root=Path.cwd(),
            baseline_dir=None,
            out_dir=out,
            skeptics=3,
            resume=True,
        )
    assert "skeptics" in exc.value.changed


def test_run_audit_resume_refuses_when_targets_changed(tmp_path: Path):
    out = tmp_path / "out"
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    with pytest.raises(CheckpointProvenanceError) as exc:
        run_audit(
            ["security", "usability"],
            backend=StubBackend(_noop_scripted),
            root=Path.cwd(),
            baseline_dir=None,
            out_dir=out,
            skeptics=1,
            resume=True,
        )
    assert "targets" in exc.value.changed


def test_run_audit_resume_proceeds_when_inputs_match(tmp_path: Path):
    out = tmp_path / "out"
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    # identical inputs → fingerprint matches → resume proceeds without raising
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
        resume=True,
    )


def test_run_audit_resume_warns_when_provenance_absent(tmp_path: Path):
    """A legacy checkpoint with no provenance file can't be verified — proceed but
    surface a warning rather than silently binding to possibly-stale inputs."""
    out = tmp_path / "out"
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
    )
    (out / "audit-provenance.json").unlink()
    logged: list[str] = []
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
        resume=True,
        log=logged.append,
    )
    assert any("provenance" in m.lower() for m in logged)


# ---------------------------------------------------------------------------
# FWK118 — target-aware audit core (fixtures_root threading)
# ---------------------------------------------------------------------------


def test_run_audit_reads_fixtures_from_fixtures_root(tmp_path: Path):
    """run_audit audits against the fixtures under the given fixtures_root, not the
    framework's own tests/eval/fixtures — the seam both combo halves need (FWK118)."""
    froot = tmp_path / "projfx"
    case = froot / "security" / "good" / "mycase"
    case.mkdir(parents=True)
    (case / "change.patch").write_text("ZZMARKER_PROJECT_FIXTURE diff body\n")

    backend = StubBackend(_noop_scripted)
    run_audit(
        ["security"],
        backend=backend,
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=tmp_path / "out",
        skeptics=1,
        fixtures_root=froot,
    )
    auditor = next(
        c
        for c in backend.messages.calls
        if "AUDITOR" in " ".join(b.get("text", "") for b in c["system"])
    )
    sys_text = " ".join(b.get("text", "") for b in auditor["system"])
    assert "ZZMARKER_PROJECT_FIXTURE" in sys_text


def test_run_audit_resume_refuses_when_fixtures_root_changed(tmp_path: Path):
    out = tmp_path / "out"
    fx1 = tmp_path / "fx1"
    fx1.mkdir()
    fx2 = tmp_path / "fx2"
    fx2.mkdir()
    run_audit(
        ["security"],
        backend=StubBackend(_noop_scripted),
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=out,
        skeptics=1,
        fixtures_root=fx1,
    )
    with pytest.raises(CheckpointProvenanceError) as exc:
        run_audit(
            ["security"],
            backend=StubBackend(_noop_scripted),
            root=Path.cwd(),
            baseline_dir=None,
            out_dir=out,
            skeptics=1,
            fixtures_root=fx2,
            resume=True,
        )
    assert "fixtures" in exc.value.changed


def test_run_audit_produces_vetted_changelist(tmp_path: Path):
    backend = StubBackend(_scripted)
    cl = run_audit(
        ["security"],
        backend=backend,
        root=Path.cwd(),
        baseline_dir=None,
        out_dir=tmp_path / "out",
        skeptics=3,
    )
    edits = cl.agents[0].edits
    # the refuted "drop" edit (after == "d") is excluded; the "keep" edit survives
    assert [e.after for e in edits] == ["b"]
    assert edits[0].verdict is not None and edits[0].verdict.refuted is False
    # the changelist + each stage's records were persisted under out_dir
    assert (tmp_path / "out" / "changelist.json").exists()
    assert (tmp_path / "out" / "changelist-full.json").exists()

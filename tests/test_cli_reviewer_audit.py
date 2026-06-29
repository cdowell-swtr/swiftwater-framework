import json

from typer.testing import CliRunner

from framework_cli.cli import app

runner = CliRunner()


def test_reviewer_audit_writes_changelist_and_preview(tmp_path, monkeypatch):
    import framework_cli.cli as climod
    from tests.review.audit.conftest import StubBackend

    def _scripted(system, messages):
        text = " ".join(b.get("text", "") for b in system)
        if "AUDITOR" in text:
            return json.dumps(
                {
                    "agent": "security",
                    "edits": [
                        {
                            "target": "fixture",
                            "rationale": "add good pair",
                            "before": "(no fixture)",
                            "after": "new fixture content",
                            "path": "tests/eval/fixtures/security/good/example",
                        }
                    ],
                    "proposed_block_threshold": "high",
                    "fixture_verdicts": {},
                }
            )
        if "RECONCILER" in text:
            return json.dumps(
                {
                    "agents": [
                        {
                            "agent": "security",
                            "proposed_block_threshold": "high",
                            "edits": [
                                {
                                    "target": "fixture",
                                    "rationale": "add good pair",
                                    "before": "(no fixture)",
                                    "after": "new fixture content",
                                    "path": "tests/eval/fixtures/security/good/example",
                                }
                            ],
                            "fixture_verdicts": {},
                        }
                    ],
                    "preamble_edits": [],
                }
            )
        # Refuter: return refuted=false so the edit survives vetted()
        return json.dumps({"refuted": False, "reason": "change is valid"})

    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: StubBackend(_scripted))
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "audit-out"
    result = runner.invoke(app, ["reviewer-audit", "security", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "changelist.json").exists()
    # fixture edits route to notes (not patch) — notes.txt is written; patch is absent
    assert (out / "apply-preview.notes.txt").exists()
    assert not (out / "apply-preview.patch").exists()


def test_reviewer_audit_emits_progress(tmp_path, monkeypatch):
    """Without --quiet, progress lines (Stage 1, etc.) appear in output."""
    import framework_cli.cli as climod
    from tests.review.audit.conftest import StubBackend

    def _scripted(system, messages):
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
            return json.dumps(
                {
                    "agents": [
                        {
                            "agent": "security",
                            "proposed_block_threshold": "high",
                            "edits": [],
                            "fixture_verdicts": {},
                        }
                    ],
                    "preamble_edits": [],
                }
            )
        return "{}"

    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: StubBackend(_scripted))
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "audit-out"
    result = runner.invoke(app, ["reviewer-audit", "security", "--out", str(out)])
    assert result.exit_code == 0, result.output
    # progress goes to STDOUT (this is an all-human-facing command; nothing to keep
    # clean on stdout, and progress should land where default capture grabs it).
    assert "Stage 1" in result.stdout


def test_run_audit_passes_concurrency_to_fanout(tmp_path, monkeypatch):
    """run_audit forwards concurrency= to both Stage 1 (audit) and Stage 3 (refute) run_stage calls."""
    import framework_cli.review.audit.pipeline as pipeline_mod

    recorded_concurrencies: list[int] = []
    original_run_stage = pipeline_mod.run_stage

    def spy_run_stage(
        items,
        work,
        *,
        run_dir,
        item_id,
        resume=False,
        label="stage",
        log=lambda _: None,
        concurrency=1,
    ):
        recorded_concurrencies.append(concurrency)
        return original_run_stage(
            items,
            work,
            run_dir=run_dir,
            item_id=item_id,
            resume=resume,
            label=label,
            log=log,
            concurrency=concurrency,
        )

    monkeypatch.setattr(pipeline_mod, "run_stage", spy_run_stage)

    import framework_cli.cli as climod
    from tests.review.audit.conftest import StubBackend

    def _scripted(system, messages):
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
            return json.dumps(
                {
                    "agents": [
                        {
                            "agent": "security",
                            "proposed_block_threshold": "high",
                            "edits": [],
                            "fixture_verdicts": {},
                        }
                    ],
                    "preamble_edits": [],
                }
            )
        return "{}"

    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: StubBackend(_scripted))
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "audit-out"
    result = runner.invoke(
        app, ["reviewer-audit", "security", "--out", str(out), "--concurrency", "5"]
    )
    assert result.exit_code == 0, result.output
    # Both fan-out stages (Stage 1 audit + Stage 3 refute) received concurrency=5
    assert recorded_concurrencies == [5, 5], (
        f"Expected [5, 5] but got {recorded_concurrencies}"
    )


def test_reviewer_audit_resume_refuses_stale_checkpoint(tmp_path, monkeypatch):
    """FWK47: resuming a checkpoint produced against different inputs (here a changed
    --skeptics) is refused with a clear message + non-zero exit, not silently reused."""
    import framework_cli.cli as climod
    from tests.review.audit.conftest import StubBackend

    def _scripted(system, messages):
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

    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: StubBackend(_scripted))
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "audit-out"
    fresh = runner.invoke(
        app, ["reviewer-audit", "security", "--out", str(out), "--skeptics", "1"]
    )
    assert fresh.exit_code == 0, fresh.output

    stale = runner.invoke(
        app,
        [
            "reviewer-audit",
            "security",
            "--out",
            str(out),
            "--skeptics",
            "3",
            "--resume",
        ],
    )
    assert stale.exit_code == 2, stale.output
    assert "stale" in stale.output.lower() or "provenance" in stale.output.lower()
    assert "skeptics" in stale.output


def test_reviewer_audit_target_project_selects_active_agents(tmp_path, monkeypatch):
    """FWK118: --target project audits the active_agents() project roster (the agents
    a generated project actually runs), excluding framework_only agents."""
    import framework_cli.cli as climod
    import framework_cli.review.audit.pipeline as pipeline_mod
    from framework_cli.review.audit.changelist import Changelist

    captured: dict[str, object] = {}

    def spy_run_audit(targets, **kw):
        captured["targets"] = list(targets)
        captured["fixtures_root"] = kw.get("fixtures_root")
        return Changelist()

    monkeypatch.setattr(pipeline_mod, "run_audit", spy_run_audit)
    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: object())
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )

    out = tmp_path / "o"
    result = runner.invoke(
        app,
        [
            "reviewer-audit",
            "--target",
            "project",
            "--fixtures-root",
            str(tmp_path / "fx"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "security" in captured["targets"]  # an always-on, non-framework_only agent
    assert "coverage-gap" not in captured["targets"]  # framework_only → excluded
    assert str(captured["fixtures_root"]) == str(tmp_path / "fx")


def test_reviewer_audit_target_project_includes_project_local_reviewer(
    tmp_path, monkeypatch
):
    """FWK119: reviewer-audit --target project audits the project's OWN reviewers
    (discovered from .framework/reviewers/) alongside the built-in project roster."""
    import framework_cli.cli as climod
    import framework_cli.review.audit.pipeline as pipeline_mod
    from framework_cli.review import registry
    from framework_cli.review.audit.changelist import Changelist

    # restore the registry global after the overlay this test installs
    orig_specs = dict(registry._SPECS)

    rdir = tmp_path / ".framework" / "reviewers"
    rdir.mkdir(parents=True)
    (rdir / "house-style.md").write_text("Flag house-style violations.")
    (rdir / "house-style.toml").write_text('active_when = "always"\n')

    captured: dict[str, object] = {}

    def spy_run_audit(targets, **kw):
        captured["targets"] = list(targets)
        return Changelist()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline_mod, "run_audit", spy_run_audit)
    monkeypatch.setattr(climod, "_make_backend", lambda *a, **k: object())
    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": "subagent", "reason": ""})(),
    )
    try:
        result = runner.invoke(
            app, ["reviewer-audit", "--target", "project", "--out", str(tmp_path / "o")]
        )
        assert result.exit_code == 0, result.output
        assert "house-style" in captured["targets"]
        assert "security" in captured["targets"]  # built-in project roster still there
    finally:
        registry._SPECS.clear()
        registry._SPECS.update(orig_specs)


def test_reviewer_audit_skip_neutral_without_backend(tmp_path, monkeypatch):
    import framework_cli.cli as climod

    monkeypatch.setattr(
        climod,
        "_resolve_review_backend",
        lambda **k: type("R", (), {"backend": None, "reason": "no key"})(),
    )
    result = runner.invoke(
        app, ["reviewer-audit", "security", "--out", str(tmp_path / "o")]
    )
    assert result.exit_code == 0
    assert "skipped" in result.output.lower()

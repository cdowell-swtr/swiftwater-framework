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
    assert (out / "changelist.json").exists()
    assert (out / "apply-preview.patch").exists()


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
    assert "Stage 1" in result.output


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

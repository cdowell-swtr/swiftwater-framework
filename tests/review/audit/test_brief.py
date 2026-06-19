import json
from pathlib import Path

from framework_cli.review.audit.brief import AuditBrief, build_audit_brief


def _write_baseline(d: Path) -> None:
    # The real `framework eval --findings-out` writer (cli.py `_write_findings`) produces:
    #   <findings_out>/<agent>/<kind>/<case>__r<repeat>.json
    # Seed exactly 2 files for the "security" agent so the count assertion holds.
    good_dir = d / "security" / "good"
    good_dir.mkdir(parents=True, exist_ok=True)
    (good_dir / "clean__r0.json").write_text(
        json.dumps(
            {
                "agent": "security",
                "kind": "good",
                "case": "clean",
                "repeat": 0,
                "findings": [],
            }
        )
    )

    bad_dir = d / "security" / "bad"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "leak__r0.json").write_text(
        json.dumps(
            {
                "agent": "security",
                "kind": "bad",
                "case": "leak",
                "repeat": 0,
                "findings": [
                    {"path": "a.py", "line": 1, "severity": "high", "message": "secret"}
                ],
            }
        )
    )


def test_brief_collects_target_prompt_fixtures_and_baseline(tmp_path: Path) -> None:
    base = tmp_path / "findings"
    _write_baseline(base)
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=base)
    assert isinstance(brief, AuditBrief)
    assert brief.target == "security"
    assert "## Your domain: `review-security`" in brief.composed_prompt
    assert "## Severity" in brief.composed_prompt
    assert len(brief.baseline_findings) == 2
    assert brief.roster_bars["security"] == "high"
    assert "usability" in brief.roster_bars and brief.roster_bars["usability"] is None


def test_brief_tolerates_absent_baseline(tmp_path: Path) -> None:
    brief = build_audit_brief("security", root=Path.cwd(), baseline_dir=None)
    assert brief.baseline_findings == []

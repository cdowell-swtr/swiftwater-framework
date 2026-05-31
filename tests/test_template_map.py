import json
from pathlib import Path

from framework_cli.template_map import (
    _template_files_by_basename,
    map_finding_path,
    map_findings,
    render_markdown,
)


def _make_template(root: Path) -> None:
    """Build a tiny fake template payload."""
    (root / "src" / "{{package_name}}").mkdir(parents=True)
    (root / "src" / "{{package_name}}" / "main.py.jinja").write_text("x")
    (root / "src" / "{{package_name}}" / "graphql").mkdir()
    (root / "src" / "{{package_name}}" / "graphql" / "schema.py.jinja").write_text("x")
    (root / "tests").mkdir()
    (root / "tests" / "conftest.py.jinja").write_text("x")
    (root / "src" / "{{package_name}}" / "conftest.py.jinja").write_text("x")


def test_unique_match(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path(
        "src/demo/main.py", package_name="demo", template_root=troot, index=idx
    )
    assert r["status"] == "unique"
    assert r["template_source"] == "src/{{package_name}}/main.py.jinja"


def test_unique_match_via_tail_overlap(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path(
        "src/demo/graphql/schema.py",
        package_name="demo",
        template_root=troot,
        index=idx,
    )
    assert r["status"] == "unique"
    assert r["template_source"] == "src/{{package_name}}/graphql/schema.py.jinja"


def test_multi_candidate(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path(
        "conftest.py", package_name="demo", template_root=troot, index=idx
    )
    assert r["status"] == "candidates"
    assert len(r["candidates"]) == 2


def test_unresolved(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path(
        "src/demo/does_not_exist.py",
        package_name="demo",
        template_root=troot,
        index=idx,
    )
    assert r["status"] == "unresolved"
    assert r["template_source"] is None


def test_map_findings_and_markdown(tmp_path):
    troot = tmp_path / "template"
    _make_template(troot)
    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "security.json").write_text(
        json.dumps(
            {
                "agent": "security",
                "findings": [
                    {
                        "path": "src/demo/main.py",
                        "line": 12,
                        "severity": "high",
                        "message": "m",
                    },
                    {
                        "path": "src/demo/nope.py",
                        "line": 3,
                        "severity": "low",
                        "message": "m",
                    },
                ],
            }
        )
    )
    rows = map_findings(findings, troot, "demo")
    assert len(rows) == 2
    assert rows[0]["agent"] == "security"
    md = render_markdown(rows)
    assert "as-rendered" in md
    assert "src/{{package_name}}/main.py.jinja" in md
    assert "UNRESOLVED" in md


def test_missing_path_and_line_are_safe(tmp_path):
    """A finding with no path → unresolved (no crash); a None line → no ':None' cell."""
    troot = tmp_path / "template"
    _make_template(troot)
    idx = _template_files_by_basename(troot)
    r = map_finding_path("", package_name="demo", template_root=troot, index=idx)
    assert r["status"] == "unresolved"
    md = render_markdown([{"agent": "x", "line": None, "severity": "low", **r}])
    assert ":None" not in md


def test_real_template_root_runs(tmp_path):
    from framework_cli.copier_runner import template_path

    findings = tmp_path / "findings"
    findings.mkdir()
    (findings / "x.json").write_text(
        json.dumps(
            {
                "agent": "application-logic",
                "findings": [
                    {
                        "path": "src/demo/main.py",
                        "line": 1,
                        "severity": "low",
                        "message": "m",
                    }
                ],
            }
        )
    )
    rows = map_findings(findings, template_path(), "demo")
    assert rows[0]["status"] in {"unique", "candidates"}

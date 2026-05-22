from pathlib import Path

import pathspec

from framework_cli.copier_runner import render_project
from framework_cli.integrity.classes import GITIGNORED_EXISTENCE, LOCKED_TRACKED, rules


def _render(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    return dest


def test_every_locked_path_exists_in_a_rendered_project(tmp_path: Path):
    dest = _render(tmp_path)
    missing = [p for p in LOCKED_TRACKED if not (dest / p).is_file()]
    assert missing == [], f"stale locked-registry entries (not rendered): {missing}"


def test_no_locked_path_is_gitignored(tmp_path: Path):
    dest = _render(tmp_path)
    spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", (dest / ".gitignore").read_text().splitlines()
    )
    leaked = [p for p in LOCKED_TRACKED if spec.match_file(p)]
    assert leaked == [], f"locked files excluded by .gitignore (cannot be tracked): {leaked}"


def test_rules_cover_both_tiers():
    by_tier = {r.tier for r in rules()}
    assert by_tier == {"tracked", "gitignored"}
    assert set(GITIGNORED_EXISTENCE) == {r.path for r in rules() if r.tier == "gitignored"}

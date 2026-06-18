from pathlib import Path

import pathspec

from framework_cli.copier_runner import render_project
from framework_cli.integrity.classes import (
    GITIGNORED_EXISTENCE,
    HYBRID_TRACKED,
    LOCKED_TRACKED,
    rules,
)


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
        "gitignore", (dest / ".gitignore").read_text().splitlines()
    )
    leaked = [p for p in LOCKED_TRACKED if spec.match_file(p)]
    assert leaked == [], (
        f"locked files excluded by .gitignore (cannot be tracked): {leaked}"
    )


def test_every_hybrid_path_renders_with_markers(tmp_path: Path):
    from framework_cli.integrity.sections import section_content

    dest = _render(tmp_path)
    for rel in HYBRID_TRACKED:
        assert (dest / rel).is_file(), f"hybrid path not rendered: {rel}"
        assert section_content((dest / rel).read_text()) is not None, (
            f"{rel} lacks markers"
        )


def test_no_hybrid_path_is_gitignored(tmp_path: Path):
    dest = _render(tmp_path)
    spec = pathspec.PathSpec.from_lines(
        "gitignore", (dest / ".gitignore").read_text().splitlines()
    )
    leaked = [p for p in HYBRID_TRACKED if spec.match_file(p)]
    assert leaked == [], f"hybrid files excluded by .gitignore: {leaked}"


def test_rules_cover_both_tiers():
    by_tier = {r.tier for r in rules()}
    assert by_tier == {"tracked", "gitignored"}
    assert set(GITIGNORED_EXISTENCE) == {
        r.path for r in rules() if r.tier == "gitignored"
    }


def test_new_deploy_files_are_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "infra/compose/app-host.yml" in LOCKED_TRACKED
    assert "infra/deploy/targets/compose-ssh.sh" in LOCKED_TRACKED


def test_seam_files_are_intentionally_unlocked():
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED

    for rel in ("scripts/seed.py", "infra/deploy/notify.sh"):
        assert rel not in LOCKED_TRACKED, f"{rel} should be unlocked (composition seam)"
        assert rel in INTENTIONALLY_UNLOCKED, (
            f"{rel} should be recorded as intentionally unlocked"
        )


def test_services_overlay_is_a_composition_seam_not_locked():
    """FWK6: services.yml is now operator-edited (managed URLs, omit stores), so it is an
    intentional composition seam, not a checksummed locked file."""
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED, LOCKED_TRACKED

    assert "infra/compose/services.yml" in INTENTIONALLY_UNLOCKED
    assert "infra/compose/services.yml" not in LOCKED_TRACKED


def test_tls_ca_overlay_is_intentionally_unlocked():
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED

    assert "infra/compose/tls-ca.yml" in INTENTIONALLY_UNLOCKED


def test_dev_summary_script_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "scripts/dev_summary.sh" in LOCKED_TRACKED

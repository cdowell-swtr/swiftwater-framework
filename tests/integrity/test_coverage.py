import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project
from framework_cli.integrity import coverage
from framework_cli.integrity.classes import BATTERY_LOCKED, EXEMPT

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def test_infra_surface_files_scans_only_surface_roots(tmp_path):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "a.yml").write_text("x")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "b.sh").write_text("x")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "c.yml").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")  # NOT a surface root

    found = set(coverage.infra_surface_files(tmp_path))
    assert found == {"infra/a.yml", "scripts/b.sh", ".github/workflows/c.yml"}


def test_unclassified_flags_an_unknown_surface_file(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mystery.sh").write_text("x")
    assert coverage.unclassified_infra_files(tmp_path) == ["scripts/mystery.sh"]


def test_classified_paths_includes_every_category():
    classified = coverage.classified_paths()
    assert "scripts/compose.sh" in classified  # LOCKED_TRACKED
    assert "scripts/seed.py" in classified  # INTENTIONALLY_UNLOCKED
    assert (
        "infra/observability/grafana/dashboards/redis.json" in classified
    )  # BATTERY_LOCKED
    assert "infra/traefik/certs/.gitkeep" in classified  # EXEMPT


@pytest.fixture(scope="module")
def all_batteries_render(tmp_path_factory):
    dest = tmp_path_factory.mktemp("fwk7-all") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


@pytest.fixture(scope="module")
def baseline_render(tmp_path_factory):
    dest = tmp_path_factory.mktemp("fwk7-base") / "demo"
    render_project(dest, {**_BASE})
    return dest


def test_no_infra_file_is_unclassified(all_batteries_render):
    unclassified = coverage.unclassified_infra_files(all_batteries_render)
    assert unclassified == [], (
        "unclassified framework-infra files (classify in integrity/classes.py — "
        f"LOCKED_TRACKED / BATTERY_LOCKED / EXEMPT / INTENTIONALLY_UNLOCKED): {unclassified}"
    )


def test_battery_locked_entries_all_render_with_all_batteries(all_batteries_render):
    missing = [p for p in BATTERY_LOCKED if not (all_batteries_render / p).is_file()]
    assert missing == [], f"stale BATTERY_LOCKED entries (not rendered): {missing}"


def test_exempt_entries_all_render_with_all_batteries(all_batteries_render):
    missing = [p for p in EXEMPT if not (all_batteries_render / p).is_file()]
    assert missing == [], f"stale EXEMPT entries (not rendered): {missing}"


def test_battery_locked_entries_are_absent_in_baseline(baseline_render):
    leaked = [p for p in BATTERY_LOCKED if (baseline_render / p).is_file()]
    assert leaked == [], (
        f"BATTERY_LOCKED paths present in a baseline render (should be in LOCKED_TRACKED): {leaked}"
    )


def test_battery_locked_gating_is_accurate(tmp_path_factory):
    """For each gate battery, a project with ONLY that battery must render every file gated on it
    AND record it in the built manifest. Catches an under-broad/wrong gate (the otherwise-silent
    under-lock failure mode)."""
    from framework_cli.integrity.generate import build_manifest

    gate_batteries = sorted({b for gate in BATTERY_LOCKED.values() for b in gate})
    for battery in gate_batteries:
        dest = tmp_path_factory.mktemp(f"fwk7-gate-{battery}") / "demo"
        render_project(dest, {**_BASE, "batteries": resolve([battery])})
        manifest_paths = {e.path for e in build_manifest(dest, "v0.0.0-test").entries}
        expected = [p for p, gate in BATTERY_LOCKED.items() if battery in gate]
        for path in expected:
            assert (dest / path).is_file(), (
                f"{path} is gated on {battery!r} but did not render with only that battery — "
                "wrong gate in BATTERY_LOCKED"
            )
            assert path in manifest_paths, (
                f"{path} rendered for {battery!r} but was not locked in the manifest"
            )

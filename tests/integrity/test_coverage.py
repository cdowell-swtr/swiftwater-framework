import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project
from framework_cli.integrity import coverage

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

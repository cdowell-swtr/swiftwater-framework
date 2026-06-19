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


def test_agents_md_is_hybrid():
    from framework_cli.integrity.classes import HYBRID_TRACKED

    assert "AGENTS.md" in HYBRID_TRACKED


def test_docs_layout_validator_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "scripts/docs_layout_check.sh" in LOCKED_TRACKED


def test_pi_memory_state_files_are_intentionally_unlocked():
    from framework_cli.integrity.classes import (
        INTENTIONALLY_UNLOCKED,
        LOCKED_TRACKED,
    )

    for rel in (
        "PLAN.md",
        "ACTION_LOG.md",
        "MEMORY.md",
        "_archive/ARCHIVED_PLAN.md",
        "_archive/ARCHIVED_ACTION_LOG.md",
    ):
        assert rel not in LOCKED_TRACKED
        assert rel in INTENTIONALLY_UNLOCKED


def test_baseline_escapees_are_locked():
    """FWK7: framework-owned files that render in a baseline project but had escaped the
    locked registry (a PORT_OFFSET wrapper + 4 static obs configs)."""
    from framework_cli.integrity.classes import LOCKED_TRACKED

    for rel in (
        "scripts/compose.sh",
        "infra/observability/grafana/dashboards/otel-collector.json",
        "infra/observability/grafana/dashboards/prometheus.json",
        "infra/observability/prometheus/alerts/otel_collector_alerts.yml",
        "infra/observability/prometheus/alerts/prometheus_alerts.yml",
    ):
        assert rel in LOCKED_TRACKED, (
            f"{rel} should be locked (baseline framework infra)"
        )


def test_gitkeep_placeholders_are_exempt():
    """FWK7: empty .gitkeep dir-placeholders have no checksummable content."""
    from framework_cli.integrity.classes import EXEMPT, LOCKED_TRACKED

    for rel in ("infra/traefik/certs/.gitkeep", "infra/tls/ca/.gitkeep"):
        assert rel in EXEMPT
        assert rel not in LOCKED_TRACKED


def test_battery_locked_covers_the_expected_files():
    from framework_cli.integrity.classes import BATTERY_LOCKED, LOCKED_TRACKED

    # 22 battery-conditional framework files; none also in the baseline locked set.
    assert len(BATTERY_LOCKED) == 22
    for path, gate in BATTERY_LOCKED.items():
        assert path not in LOCKED_TRACKED, (
            f"{path} is both baseline-locked and battery-locked"
        )
        assert isinstance(gate, tuple) and gate, f"{path} needs a non-empty gate tuple"
    # spot-check a single-gate, a multi-gate, and a non-obs entry
    assert BATTERY_LOCKED["infra/observability/grafana/dashboards/redis.json"] == (
        "redis",
        "workers",
    )
    assert BATTERY_LOCKED["infra/docker/postgres.Dockerfile"] == (
        "pgvector",
        "timescaledb",
        "age",
    )
    assert BATTERY_LOCKED[".github/workflows/docs.yml"] == ("docs",)


def test_rules_default_is_baseline_only():
    from framework_cli.integrity.classes import LOCKED_TRACKED, rules

    paths = {r.path for r in rules()}
    # no battery-conditional path leaks into the default (baseline) rule set
    assert "infra/observability/grafana/dashboards/redis.json" not in paths
    assert set(LOCKED_TRACKED) <= paths


def test_rules_adds_battery_locked_for_active_batteries():
    from framework_cli.integrity.classes import rules

    redis_rule = "infra/observability/grafana/dashboards/redis.json"
    assert redis_rule in {r.path for r in rules(["redis"])}
    # shared gate: workers also activates the redis dashboards
    assert redis_rule in {r.path for r in rules(["workers"])}
    # a non-gating battery activates none of redis's files
    assert redis_rule not in {r.path for r in rules(["graphql"])}
    # every activated battery file is a locked/tracked Rule
    for r in rules(["redis"]):
        if r.path == redis_rule:
            assert r.cls == "locked" and r.tier == "tracked"

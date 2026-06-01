import re
from pathlib import Path

import pytest
import yaml

from framework_cli.batteries import battery_names, get_battery
from framework_cli.copier_runner import render_project

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}

_ALERTS_DIR = Path("infra/observability/prometheus/alerts")
_DASHBOARDS_DIR = Path("infra/observability/grafana/dashboards")
_PROMETHEUS = Path("infra/observability/prometheus/prometheus.yml")
_SERVICES = Path("infra/compose/services.yml")
_OBSERVABILITY = Path("infra/compose/observability.yml")


def _alert_files(root: Path) -> set[str]:
    d = root / _ALERTS_DIR
    return {p.name for p in d.glob("*.yml")} if d.is_dir() else set()


def _dashboards(root: Path) -> set[str]:
    d = root / _DASHBOARDS_DIR
    return {p.name for p in d.glob("*.json")} if d.is_dir() else set()


def _scrape_jobs(root: Path) -> set[str]:
    p = root / _PROMETHEUS
    if not p.is_file():
        return set()
    return set(re.findall(r"job_name:\s*(\S+)", p.read_text()))


def _compose_services(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = yaml.safe_load(path.read_text()) or {}
    return set((data.get("services") or {}).keys())


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("obs-base") / "demo"
    render_project(dest, {**_BASE, "batteries": []})
    return dest


@pytest.mark.parametrize("name", battery_names())
def test_battery_obs_matches_declared_surface(
    name: str, baseline: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "demo"
    render_project(dest, {**_BASE, "batteries": [name]})

    new_alerts = _alert_files(dest) - _alert_files(baseline)
    new_dashboards = _dashboards(dest) - _dashboards(baseline)
    new_scrapes = _scrape_jobs(dest) - _scrape_jobs(baseline)
    new_prod_services = _compose_services(dest / _SERVICES) - _compose_services(
        baseline / _SERVICES
    )
    new_prod_exporters = _compose_services(dest / _OBSERVABILITY) - _compose_services(
        baseline / _OBSERVABILITY
    )

    obs = get_battery(name).obs
    if obs == "service":
        assert new_scrapes, (
            f"{name}: a 'service' battery must add a Prometheus scrape job"
        )
        assert new_alerts, f"{name}: a 'service' battery must add an alert-rule file"
        assert new_dashboards, (
            f"{name}: a 'service' battery must add a Grafana dashboard"
        )
        assert new_prod_services, (
            f"{name}: a 'service' battery must add its service to services.yml (prod-wiring)"
        )
        assert new_prod_exporters, (
            f"{name}: a 'service' battery must add its exporter to observability.yml (prod-wiring)"
        )
    elif obs == "in-process":
        assert new_alerts, (
            f"{name}: an 'in-process' battery must add an alert-rule file"
        )
        assert new_dashboards, (
            f"{name}: an 'in-process' battery must add a Grafana dashboard"
        )
        assert not new_scrapes, (
            f"{name}: an 'in-process' battery must not add a scrape job"
        )
        assert not new_prod_services, (
            f"{name}: an 'in-process' battery must not add a prod service"
        )
        assert not new_prod_exporters, (
            f"{name}: an 'in-process' battery must not add a prod exporter"
        )
    else:  # rides-existing
        assert not (
            new_alerts
            or new_dashboards
            or new_scrapes
            or new_prod_services
            or new_prod_exporters
        ), (
            f"{name}: a 'rides-existing' battery must add no new observability artifacts; got "
            f"alerts={new_alerts} dashboards={new_dashboards} scrapes={new_scrapes} "
            f"services={new_prod_services} exporters={new_prod_exporters}"
        )


def _job_referenced(root: Path, subdir: str, glob: str, job: str) -> bool:
    # Matches job="x" (YAML alerts) and job=\"x\" (escaped inside dashboard JSON).
    pat = re.compile(rf'job=\\?"{re.escape(job)}\\?"')
    return any(pat.search(p.read_text()) for p in (root / subdir).glob(glob))


def test_base_obs_components_are_self_monitored(tmp_path: Path) -> None:
    """The base obs infrastructure (otel-collector, prometheus) must self-monitor.

    The per-battery guard above only covers battery obs surfaces; otel-collector and
    prometheus are base components (not batteries), so they need their own check: each
    must be a Prometheus scrape job AND have an alert rule + dashboard referencing its
    job name. (Caught a real gap: otel-collector deployed but unscraped + unalerted.)
    """
    dest = tmp_path / "demo"
    render_project(dest, {**_BASE, "batteries": []})

    jobs = _scrape_jobs(dest)
    for job in ("otel-collector", "prometheus"):
        assert job in jobs, f"base obs component {job!r} has no Prometheus scrape job"
        assert _job_referenced(
            dest, "infra/observability/prometheus/alerts", "*.yml", job
        ), f'base obs component {job!r} has no alert referencing job="{job}"'
        assert _job_referenced(
            dest, "infra/observability/grafana/dashboards", "*.json", job
        ), f'base obs component {job!r} has no dashboard referencing job="{job}"'

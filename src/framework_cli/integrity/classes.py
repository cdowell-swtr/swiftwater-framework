from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    glob: str  # rendered path, relative to the project root
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"


# Locked + tracked: pure framework infrastructure a builder must never edit (spec §17).
# These are full-file checksummed and must be git-tracked.
LOCKED_TRACKED: tuple[str, ...] = (
    ".github/workflows/ci.yml",
    ".github/workflows/deploy-staging.yml",
    ".github/workflows/deploy-prod.yml",
    ".github/dependabot.yml",
    ".pre-commit-config.yaml",
    ".gitattributes",
    ".dockerignore",
    "alembic.ini",
    "infra/compose/base.yml",
    "infra/compose/dev.yml",
    "infra/compose/prod.yml",
    "infra/compose/staging.yml",
    "infra/compose/test.yml",
    "infra/deploy/strategy.sh",
    "infra/deploy/notify.sh",
    "infra/deploy/README.md",
    "infra/docker/Dockerfile",
    "infra/traefik/traefik.yml",
    "infra/traefik/dynamic/tls.yml",
    "infra/observability/alertmanager/alertmanager.yml",
    "infra/observability/loki/loki-config.yml",
    "infra/observability/otel/otel-collector.yml",
    "infra/observability/prometheus/prometheus.yml",
    "infra/observability/prometheus/alerts/slo_alerts.yml",
    "infra/observability/promtail/promtail-config.yml",
    "infra/observability/tempo/tempo.yml",
    "infra/observability/grafana/dashboards/slo.json",
    "infra/observability/grafana/provisioning/dashboards/provider.yml",
    "infra/observability/grafana/provisioning/datasources/loki.yml",
    "infra/observability/grafana/provisioning/datasources/prometheus.yml",
    "infra/observability/grafana/provisioning/datasources/tempo.yml",
    "scripts/check_migrations.py",
    "scripts/coverage.sh",
    "scripts/entrypoint.sh",
    "scripts/export-openapi.sh",
    "scripts/gen_observability.py",
    "scripts/load.sh",
    "scripts/seed.py",
)

# Gitignored + existence-only: framework-managed files legitimately absent from a fresh
# clone (.env derived from .env.example; mkcert certs). Verified locally only, never in CI.
GITIGNORED_EXISTENCE: tuple[str, ...] = (
    ".env",
    "infra/traefik/certs/localhost.pem",
    "infra/traefik/certs/localhost-key.pem",
)


def rules() -> list[Rule]:
    """The full classification: locked/tracked files plus gitignored/existence paths."""
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + gitignored

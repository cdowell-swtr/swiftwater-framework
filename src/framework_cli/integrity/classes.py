from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    path: str  # rendered path, relative to the project root
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"


# Coverage is one-directional: tests assert every registered path exists in a render
# (no stale entries), but NOT that every framework-infra file is registered. A newly
# added framework file therefore escapes integrity coverage until it is listed here.
# The reverse check ("every infra/scripts file must be classified") is deferred to a
# later pass — it needs an explicit allowlist of intentionally-unlocked files
# (app source, .gitkeep, .env.example, the 6a-2 hybrid files) to avoid false positives.

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
    "infra/compose/observability.yml",
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
    "infra/observability/prometheus/alerts/postgres_alerts.yml",
    "infra/observability/promtail/promtail-config.yml",
    "infra/observability/tempo/tempo.yml",
    "infra/observability/grafana/dashboards/slo.json",
    "infra/observability/grafana/dashboards/postgres.json",
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

# Gitignored + existence-only: a framework-managed file legitimately absent from a fresh
# clone, where a local nudge to create it is useful. Verified locally only, never in CI.
# (mkcert certs under infra/traefik/certs/ are intentionally NOT tracked here: they are an
# opt-in local-TLS artifact already gated by the `task dev` precondition, and being
# gitignored they cannot be checksummed — tracking them only produced misleading noise.)
GITIGNORED_EXISTENCE: tuple[str, ...] = (".env",)

# Hybrid + tracked: files the builder extends, carrying a framework-owned region delimited
# by FRAMEWORK:BEGIN/END. The section between the markers is checksummed; content outside is
# the builder's. (pyproject.toml is intentionally excluded — its dependency arrays must stay
# builder-editable, and its breakage is loud, not silent.)
HYBRID_TRACKED: tuple[str, ...] = ("CLAUDE.md", ".env.example", "Taskfile.yml")


def rules() -> list[Rule]:
    """The full classification: locked + hybrid tracked files, plus gitignored/existence paths."""
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + hybrid + gitignored

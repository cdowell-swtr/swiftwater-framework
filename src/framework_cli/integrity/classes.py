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
# INTENTIONALLY_UNLOCKED (below) now records deliberate exclusions so a future reverse
# scan can distinguish "deliberately unlocked" from "escaped classification". The full
# reverse check remains a separate slice — an all-batteries render has ~23 unclassified
# infra files needing a per-file audit before the scan can run without false positives.

# Locked + tracked: pure framework infrastructure a builder must never edit (spec §17).
# These are full-file checksummed and must be git-tracked.
LOCKED_TRACKED: tuple[str, ...] = (
    ".github/workflows/ci.yml",
    ".github/workflows/deploy-staging.yml",
    ".github/workflows/deploy-prod.yml",
    ".github/dependabot.yml",
    ".gitattributes",
    ".dockerignore",
    "alembic.ini",
    "infra/compose/app-host.yml",
    "infra/compose/base.yml",
    "infra/compose/dev.yml",
    "infra/compose/observability.yml",
    "infra/compose/prod.yml",
    "infra/compose/services.yml",
    "infra/compose/staging.yml",
    "infra/compose/test.yml",
    "infra/deploy/strategy.sh",
    "infra/deploy/targets/compose-ssh.sh",
    "infra/deploy/alert_smoke.sh",
    "infra/deploy/check_alert_secrets.sh",
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
    "infra/observability/prometheus/alerts/alertmanager_alerts.yml",
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
    "scripts/doctor.sh",
    "scripts/entrypoint.sh",
    "scripts/export-openapi.sh",
    "scripts/gen_observability.py",
    "scripts/load.sh",
)

# Framework-shipped files deliberately left unmanaged: composition seams the scaffold invites the
# project to replace. Not checksummed. Recorded here so the unlock is intentional and visible, and
# so a future reverse-coverage check can distinguish "deliberately unlocked" from "a framework file
# that escaped classification". (That full reverse scan is a separate slice — an all-batteries
# render has ~23 unclassified infra files needing a per-file audit; see the design doc.)
INTENTIONALLY_UNLOCKED: tuple[str, ...] = (
    "scripts/seed.py",  # thin entrypoint; the idempotent seed() helper in db/seed.py is the mechanism
    "infra/deploy/notify.sh",  # deploy-notification seam — "wire your channel here"
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
# builder-editable, and its breakage is loud, not silent.) `.pre-commit-config.yaml` is hybrid
# (not locked) so a project can add its own hooks below FRAMEWORK:END as more `repos:` entries.
HYBRID_TRACKED: tuple[str, ...] = (
    "CLAUDE.md",
    ".env.example",
    "Taskfile.yml",
    ".pre-commit-config.yaml",
)


def rules() -> list[Rule]:
    """The full classification: locked + hybrid tracked files, plus gitignored/existence paths."""
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + hybrid + gitignored

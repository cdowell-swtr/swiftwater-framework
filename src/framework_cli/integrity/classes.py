from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    path: str  # rendered path, relative to the project root
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"


# Coverage is closed by the FWK7 reverse-coverage check (tests/integrity/test_coverage.py): an
# all-batteries render asserts every infra-surface file is classified into exactly one of
# LOCKED_TRACKED, HYBRID_TRACKED, GITIGNORED_EXISTENCE, INTENTIONALLY_UNLOCKED, BATTERY_LOCKED, or
# EXEMPT. BATTERY_LOCKED holds framework files that exist only when a gating battery is active;
# EXEMPT holds empty placeholders with no checksummable content. A newly added framework file under
# the scanned surface roots now fails that check until it is classified here.

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
    "infra/tls/ca/.gitkeep",
    "infra/observability/alertmanager/alertmanager.yml",
    "infra/observability/loki/loki-config.yml",
    "infra/observability/otel/otel-collector.yml",
    "infra/observability/prometheus/prometheus.yml",
    "infra/observability/prometheus/alerts/slo_alerts.yml",
    "infra/observability/prometheus/alerts/postgres_alerts.yml",
    "infra/observability/prometheus/alerts/alertmanager_alerts.yml",
    "infra/observability/prometheus/alerts/otel_collector_alerts.yml",
    "infra/observability/prometheus/alerts/prometheus_alerts.yml",
    "infra/observability/promtail/promtail-config.yml",
    "infra/observability/tempo/tempo.yml",
    "infra/observability/grafana/dashboards/slo.json",
    "infra/observability/grafana/dashboards/postgres.json",
    "infra/observability/grafana/dashboards/otel-collector.json",
    "infra/observability/grafana/dashboards/prometheus.json",
    "infra/observability/grafana/provisioning/dashboards/provider.yml",
    "infra/observability/grafana/provisioning/datasources/loki.yml",
    "infra/observability/grafana/provisioning/datasources/prometheus.yml",
    "infra/observability/grafana/provisioning/datasources/tempo.yml",
    "scripts/check_migrations.py",
    "scripts/compose.sh",
    "scripts/coverage.sh",
    "scripts/dev_summary.sh",
    "scripts/docs_layout_check.sh",
    "scripts/doctor.sh",
    "scripts/entrypoint.sh",
    "scripts/export-openapi.sh",
    "scripts/gen_observability.py",
    "scripts/load.sh",
)

# Framework-shipped files deliberately left unmanaged: composition seams the scaffold invites the
# project to replace. Not checksummed. Recorded here so the unlock is intentional and visible, and
# so the FWK7 reverse-coverage check (tests/integrity/test_coverage.py) can distinguish "deliberately
# unlocked" from "a framework file that escaped classification".
INTENTIONALLY_UNLOCKED: tuple[str, ...] = (
    "scripts/seed.py",  # thin entrypoint; the idempotent seed() helper in db/seed.py is the mechanism
    "infra/deploy/notify.sh",  # deploy-notification seam — "wire your channel here"
    "infra/compose/services.yml",  # FWK6: self-hosted store overlay — operators edit it (managed URLs / omit stores)
    "infra/compose/tls-ca.yml",  # FWK6: opt-in CA-bundle TLS overlay — operator-supplied bundle + DSN param
    "PLAN.md",  # FWK9: PI stateful file — seeded once, consumer-owned (upgrade never clobbers)
    "ACTION_LOG.md",  # FWK9: PI append-only log — seeded once, consumer-owned
    "MEMORY.md",  # FWK9: committed-memory index — seeded once, consumer-owned
    "_archive/ARCHIVED_PLAN.md",  # FWK9: PI archive stub — consumer-owned
    "_archive/ARCHIVED_ACTION_LOG.md",  # FWK9: PI archive stub — consumer-owned
)

# Framework-shipped placeholders with no checksummable content: genuinely EMPTY (0-byte) .gitkeep
# files that only exist to keep an otherwise-empty directory in git. Recorded explicitly (like
# INTENTIONALLY_UNLOCKED) so the FWK7 reverse-coverage check can distinguish "deliberately uncovered"
# from "a framework file that escaped classification". A .gitkeep that carries guidance content is
# NOT exempt — it has a stable checksum worth protecting and belongs in LOCKED_TRACKED (e.g.
# infra/tls/ca/.gitkeep, which ships a CA-bundle hint).
EXEMPT: tuple[str, ...] = (
    "infra/traefik/certs/.gitkeep",  # 0-byte local-TLS cert dir placeholder
)

# Battery-conditional framework files: locked, but present only when a gating battery is active.
# Maps the rendered path to the batteries that produce it (lock applies when ANY is active, mirroring
# the template's jinja `or` conditionals). build_manifest() enforces these per-project via the
# project's own recorded batteries, so LOCKED_TRACKED keeps its "present in a baseline render"
# invariant. Gates are transcribed directly from the conditional filenames in
# src/framework_cli/template/ (the single source of truth).
BATTERY_LOCKED: dict[str, tuple[str, ...]] = {
    "infra/observability/grafana/dashboards/agents.json": ("agents",),
    "infra/observability/prometheus/alerts/agents_alerts.yml": ("agents",),
    "infra/observability/grafana/dashboards/frontend.json": ("react",),
    "infra/observability/prometheus/alerts/frontend_alerts.yml": ("react",),
    "infra/observability/grafana/dashboards/graphql.json": ("graphql",),
    "infra/observability/prometheus/alerts/graphql_alerts.yml": ("graphql",),
    "infra/observability/grafana/dashboards/llm.json": ("llm",),
    "infra/observability/prometheus/alerts/llm_alerts.yml": ("llm",),
    "infra/observability/grafana/dashboards/mongodb.json": ("mongodb",),
    "infra/observability/prometheus/alerts/mongodb_alerts.yml": ("mongodb",),
    "infra/observability/grafana/dashboards/multitenantauth.json": ("multitenantauth",),
    "infra/observability/prometheus/alerts/multitenantauth_alerts.yml": (
        "multitenantauth",
    ),
    "alembic_control.ini": ("multitenantauth",),
    "infra/observability/grafana/dashboards/redis.json": ("redis", "workers"),
    "infra/observability/prometheus/alerts/redis_alerts.yml": ("redis", "workers"),
    "infra/observability/grafana/dashboards/webhooks.json": ("webhooks",),
    "infra/observability/prometheus/alerts/webhooks_alerts.yml": ("webhooks",),
    "infra/observability/grafana/dashboards/websockets.json": ("websockets",),
    "infra/observability/prometheus/alerts/websockets_alerts.yml": ("websockets",),
    "infra/observability/grafana/dashboards/workers.json": ("workers",),
    "infra/observability/prometheus/alerts/workers_alerts.yml": ("workers",),
    "infra/docker/postgres.Dockerfile": ("pgvector", "timescaledb", "age"),
    "scripts/export-graphql-schema.sh": ("graphql",),
    "scripts/pact-publish.sh": ("consumers",),
    ".github/workflows/docs.yml": ("docs",),
}

# Battery-gated locked SOURCE files: the framework's deliberate exception to FWK7's
# builder-owned-`src/` rule. The multitenantauth MECHANISM (the security-critical machinery — the
# permission evaluator, the request guards, CSRF, password/token handling, the control-plane models
# + engine + repo, the registry, the routes, the control migration chain) is framework-OWNED
# security infrastructure that happens to live under `src/`. Locking it is the de-fork colonization
# guard: a consumer who edits a mechanism file fails `framework integrity`, security fixes flow on
# `framework upgrade`, and Meridian stays on the validated shape instead of re-forking.
#
# Paths carry a `{package_name}` token expanded against the project's recorded answer at manifest
# time (build_manifest); the gating mirrors BATTERY_LOCKED. The authz POLICY catalog
# (authz/permissions.py, authz/roles.py) is DELIBERATELY EXCLUDED — it ships consumer-editable, so
# customization has a home and locking matches design intent rather than fighting it. Completeness
# is fail-safe: tests/integrity/test_auth_mechanism_lock.py walks the rendered tree and fails if any
# mechanism file is missing here, so a forgotten lock is caught (it never silently ships unlocked).
# Shared files the battery only WIRES INTO (main.py, config/settings.py, scripts/entrypoint.sh,
# migrations/env.py, .env.example) are co-owned and stay OUT of this set by design.
BATTERY_LOCKED_SRC: dict[str, tuple[str, ...]] = {
    "src/{package_name}/multitenantauth/__init__.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authn/__init__.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authn/email_norm.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authn/passwords.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authn/tokens.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authz/__init__.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authz/expr.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authz/resolution.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authz/seed.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/authz/service.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/cookies.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/csrf.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/deps.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/errors.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/metrics.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/routes/__init__.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/routes/auth.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/routes/roles.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/routes/tenants.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/tenancy/__init__.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/tenancy/registry.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/tenancy/metrics.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/tenancy/engine_registry.py": (
        "multitenantauth",
    ),
    "src/{package_name}/multitenantauth/tenancy/dsn.py": ("multitenantauth",),
    "src/{package_name}/multitenantauth/tenancy/session.py": ("multitenantauth",),
    "src/{package_name}/db/control/__init__.py": ("multitenantauth",),
    "src/{package_name}/db/control/base.py": ("multitenantauth",),
    "src/{package_name}/db/control/engine.py": ("multitenantauth",),
    "src/{package_name}/db/control/repository.py": ("multitenantauth",),
    "src/{package_name}/db/control/models/__init__.py": ("multitenantauth",),
    "src/{package_name}/db/control/models/authn.py": ("multitenantauth",),
    "src/{package_name}/db/control/models/authz.py": ("multitenantauth",),
    "src/{package_name}/db/control/models/tenant.py": ("multitenantauth",),
    "migrations_control/env.py": ("multitenantauth",),
    "migrations_control/script.py.mako": ("multitenantauth",),
    "migrations_control/versions/c0001_control_tenant.py": ("multitenantauth",),
    "migrations_control/versions/c0002_auth_model.py": ("multitenantauth",),
    "migrations_control/versions/c0003_resource_role_assignment.py": (
        "multitenantauth",
    ),
}

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
    "AGENTS.md",
    "CLAUDE.md",
    ".env.example",
    "Taskfile.yml",
    ".pre-commit-config.yaml",
)


def rules(batteries: Sequence[str] = ()) -> list[Rule]:
    """The full classification: locked + hybrid tracked files, plus gitignored/existence paths.

    `batteries` (the project's active battery set) additionally activates the matching
    BATTERY_LOCKED rules. The empty default reproduces the baseline-only rule set, so existing
    callers and the baseline render tests are unchanged.
    """
    active = set(batteries)
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    battery = [
        Rule(p, "locked", "tracked")
        for p, gate in BATTERY_LOCKED.items()
        if active.intersection(gate)
    ]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + battery + hybrid + gitignored

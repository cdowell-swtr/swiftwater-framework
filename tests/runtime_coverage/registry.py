"""FWK29 classification registry — the closed-world ratchet's data.

Every operational surface that `enumerate.py` finds must appear here exactly once,
classified as EXERCISED (a test drives it — evidence names the test function), EXEMPT
(intentionally undriven — evidence is the reason), or KNOWN_GAP (a real, tracked gap —
evidence is "FWK<N> ...").

OUT OF SCOPE (by design): in-app code-path surfaces — the create_app/lifespan bootstrap,
DB engine/pool lifecycle, per-battery live routes, worker tracing. They are not
mechanically enumerable and are owned by the FWK30 open-world reviewer, which defers to
THIS registry (treats anything classified here as handled).
"""

import enum
from dataclasses import dataclass


class Status(enum.Enum):
    EXERCISED = "exercised"
    EXEMPT = "exempt"
    KNOWN_GAP = "known_gap"


@dataclass(frozen=True)
class SurfaceClass:
    key: str
    provisioned_at: str
    status: Status
    evidence: str


_EX = Status.EXERCISED
_EM = Status.EXEMPT
_KG = Status.KNOWN_GAP


REGISTRY: tuple[SurfaceClass, ...] = (
    # ---- Dockerfile build stages -----------------------------------------------------
    SurfaceClass(
        "docker-stage:Dockerfile:builder",
        "infra/docker/Dockerfile:5-11",
        _EX,
        # The lite stack builds the runtime image, which COPYs --from=builder; building
        # runtime builds the builder stage. Inventory: baseline runtime build overturn (:720).
        "test_rendered_project_dev_lite_stack_serves_health",
    ),
    SurfaceClass(
        "docker-stage:Dockerfile:frontend-build",
        "infra/docker/Dockerfile:13-22",
        _EX,
        # H6/FWK21: the react runtime image is built AND run; GET / asserts the SPA shell
        # (id="root") served from the COPYd /app/frontend/dist, not just returncode==0.
        "test_rendered_react_battery_passes",
    ),
    SurfaceClass(
        "docker-stage:Dockerfile:runtime",
        "infra/docker/Dockerfile:24-34",
        _EX,
        # Inventory overturn (:720): the dev:lite stack builds the runtime image end-to-end
        # and serves /health through it.
        "test_rendered_project_dev_lite_stack_serves_health",
    ),
    # ---- .claude hooks ---------------------------------------------------------------
    SurfaceClass(
        "hook:.claude:lint_changed.py",
        ".claude/hooks/lint_changed.py",
        _EX,
        # Driven via _run_hook with a PreToolUse Write payload; asserts F401 -> exit 2.
        "test_lint_hook_blocks_on_bad_python",
    ),
    SurfaceClass(
        "hook:.claude:reviewers-gate-check.sh",
        ".claude/hooks/reviewers-gate-check.sh",
        _KG,
        # M15: only render-text-checked; no test pipes a PreToolUse git-commit payload and
        # asserts FAIL->exit 2 (unlike lint_changed.py which IS driven).
        "FWK27 reviewers-gate-check.sh PreToolUse hook only render-checked, never invoked with a payload",
    ),
    # ---- pre-commit hooks ------------------------------------------------------------
    # All lint/format/hygiene/static hooks below are fired by `pre-commit run --all-files`
    # (SKIP=coverage-threshold) on a fresh rendered project — they must pass clean.
    SurfaceClass(
        "hook:actionlint",
        ".pre-commit-config.yaml:26",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:check-merge-conflict",
        ".pre-commit-config.yaml:16",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:check-toml",
        ".pre-commit-config.yaml:15",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:check-yaml",
        ".pre-commit-config.yaml:14",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:coverage-threshold",
        ".pre-commit-config.yaml:60",
        _EX,
        # Skipped in precommit-runs-clean (needs Docker/Postgres); the command it runs
        # (scripts/coverage.sh) is driven directly by the coverage-gate acceptance test.
        "test_rendered_project_coverage_gate_passes",
    ),
    SurfaceClass(
        "hook:end-of-file-fixer",
        ".pre-commit-config.yaml:9",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:gitleaks",
        ".pre-commit-config.yaml:21",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:migrations-reversible",
        ".pre-commit-config.yaml:54",
        _EX,
        # Fired by precommit-runs-clean; the script it runs (check_migrations.py) is also
        # behavior-tested by test_rendered_project_blocks_contract_migration.
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:mixed-line-ending",
        ".pre-commit-config.yaml:12",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:mypy",
        ".pre-commit-config.yaml:47",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:ruff-check",
        ".pre-commit-config.yaml:35",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:ruff-format",
        ".pre-commit-config.yaml:41",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:shellcheck",
        ".pre-commit-config.yaml:31",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    SurfaceClass(
        "hook:trailing-whitespace",
        ".pre-commit-config.yaml:11",
        _EX,
        "test_rendered_project_precommit_runs_clean",
    ),
    # ---- ci.yml jobs -----------------------------------------------------------------
    # The generated ci.yml is exercised on real GHA by scripts/dogfood_e2e.py, not by a
    # local pytest function; the completeness test only accepts a def test_ name for
    # EXERCISED, so these are EXEMPT (driven, just not by a local pytest).
    SurfaceClass(
        "job:ci.yml:build",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:contract",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:contracts",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:docs",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:frontend",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:integrity",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:lint",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:review",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:review-aggregate",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:review-plan",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:security",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "job:ci.yml:test",
        ".github/workflows/ci.yml",
        _EM,
        "generated CI job — exercised by scripts/dogfood_e2e.py on real GHA, not a local pytest",
    ),
    # ---- CD workflow jobs ------------------------------------------------------------
    # H8 DROPPED: the deploy is designed to fail loudly until a consumer wires a target;
    # the orchestration + the real compose-ssh->app-host.yml path are covered by the deploy
    # e2e/compose-ssh tests, and actionlint validates the CD workflow YAML. The CD job graph
    # itself is driven by no pytest (dogfood filters to ci.yml).
    SurfaceClass(
        "job:deploy-prod.yml:deploy-prod",
        ".github/workflows/deploy-prod.yml",
        _EM,
        "CD job graph — orchestration covered by deploy e2e; YAML validated by actionlint; "
        "inventory H8 DROPPED (consumer-wired target, fail-loud by design)",
    ),
    SurfaceClass(
        "job:deploy-staging.yml:build-push",
        ".github/workflows/deploy-staging.yml",
        _EM,
        "CD job graph — orchestration covered by deploy e2e; YAML validated by actionlint; "
        "inventory H8 DROPPED (consumer-wired target, fail-loud by design)",
    ),
    SurfaceClass(
        "job:deploy-staging.yml:deploy-staging",
        ".github/workflows/deploy-staging.yml",
        _EM,
        "CD job graph — orchestration covered by deploy e2e; YAML validated by actionlint; "
        "inventory H8 DROPPED (consumer-wired target, fail-loud by design)",
    ),
    SurfaceClass(
        "job:docs.yml:publish",
        ".github/workflows/docs.yml",
        _EM,
        # L3: tag-only mike gh-pages publish; dogfood drives push/PR + filters to CI, never
        # tags. A GitHub-platform publish step, undriveable by local tiers.
        "docs mike publish — tag-triggered gh-pages publish, a GitHub-platform step "
        "undriveable by local tiers (inventory L3); strict docs build covered by ci.yml docs job",
    ),
    # ---- compose overlays ------------------------------------------------------------
    SurfaceClass(
        "overlay:app-host.yml",
        "infra/compose/app-host.yml",
        _EX,
        # The only shipped deploy target brings up app-host.yml via the real strategy.
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    SurfaceClass(
        "overlay:base.yml",
        "infra/compose/base.yml",
        _EX,
        # The foundational overlay merged (-f base -f dev) in every dev/lite stack test.
        "test_rendered_project_dev_lite_stack_serves_health",
    ),
    SurfaceClass(
        "overlay:dev.yml",
        "infra/compose/dev.yml",
        _EX,
        # Merged (-f base -f dev) and brought up --profile dev, routed through Traefik.
        "test_rendered_project_dev_stack_routes_through_traefik",
    ),
    SurfaceClass(
        "overlay:observability.yml",
        "infra/compose/observability.yml",
        _EX,
        # Merged (-f base -f observability -f dev) and brought up; Prometheus scrapes app.
        "test_rendered_project_dev_stack_prometheus_scrapes_app",
    ),
    SurfaceClass(
        "overlay:prod.yml",
        "infra/compose/prod.yml",
        _EM,
        # Correction (2026-06-16): no shipped path brings prod.yml up; it is consumer-target
        # scaffolding. It already has `docker compose config` merge-validation (the right guard).
        "consumer-target overlay — no shipped path brings it up (deploy uses app-host.yml); "
        "already compose-config merge-validated (inventory H1 demoted, prod.yml config-validated)",
    ),
    SurfaceClass(
        "overlay:services.yml",
        "infra/compose/services.yml",
        _KG,
        # Correction: staging/prod battery overlay, only consumed by a consumer-written
        # target; never instantiated with batteries. FWK19 adds batteries-on config merge-validation.
        "FWK19 services.yml battery overlay lacks batteries-on compose-config merge-validation",
    ),
    SurfaceClass(
        "overlay:staging.yml",
        "infra/compose/staging.yml",
        _KG,
        # Correction: staging.yml is only .read_text() substring-checked — it gets NO compose
        # config merge-validation (unlike prod.yml). FWK19 adds the parity merge-validation.
        "FWK19 staging.yml lacks compose-config merge-validation (only substring-checked)",
    ),
    SurfaceClass(
        "overlay:test.yml",
        "infra/compose/test.yml",
        _KG,
        # M3: IS shipped + used by `task test:stack` but the acceptance tier never uses
        # --profile test; the tmpfs ephemeral-DB reset is undriven.
        "FWK19 test.yml never brought up --profile test (tmpfs ephemeral-DB reset undriven)",
    ),
    # ---- deploy scripts --------------------------------------------------------------
    SurfaceClass(
        "script:infra/deploy/alert_smoke.sh",
        "infra/deploy/alert_smoke.sh",
        _EX,
        # Behavior-tested: reports failure but exits 0 (non-fatal advisory smoke).
        "test_alert_smoke_reports_failure_but_exits_zero",
    ),
    SurfaceClass(
        "script:infra/deploy/check_alert_secrets.sh",
        "infra/deploy/check_alert_secrets.sh",
        _EX,
        # Driven in the deploy e2e: APP_ALERT_WEBHOOK_URL satisfies the webhook-secret gate
        # during the rolling deploy.
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    SurfaceClass(
        "script:infra/deploy/notify.sh",
        "infra/deploy/notify.sh",
        _KG,
        # L1: called only by the CD workflows (never strategy.sh); deploy_e2e never runs it.
        # Intentionally non-fatal seam.
        "FWK28 notify.sh non-fatal seam invoked only by CD workflows, never run by a test",
    ),
    SurfaceClass(
        "script:infra/deploy/strategy.sh",
        "infra/deploy/strategy.sh",
        _EX,
        # The real deploy/rollback orchestration is driven end-to-end in the rolling-update e2e.
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    SurfaceClass(
        "script:infra/deploy/targets/compose-ssh.sh",
        "infra/deploy/targets/compose-ssh.sh",
        _EX,
        # The only shipped target; sourced + executed against app-host.yml in the e2e.
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    # ---- scripts/ --------------------------------------------------------------------
    SurfaceClass(
        "script:scripts/check_migrations.py",
        "scripts/check_migrations.py",
        _EX,
        # Driven directly: blocks a contract-breaking migration, passes a safe one.
        "test_rendered_project_blocks_contract_migration",
    ),
    SurfaceClass(
        "script:scripts/compose.sh",
        "scripts/compose.sh",
        _EX,
        # Behavioral: shifts host ports by PORT_OFFSET and respects per-var overrides
        # before exec-ing docker compose (FWK31).
        "test_compose_wrapper_shifts_host_ports_by_offset",
    ),
    SurfaceClass(
        "script:scripts/coverage.sh",
        "scripts/coverage.sh",
        _EX,
        # The fast unit+functional gate is run via `bash scripts/coverage.sh 70 ...`.
        "test_rendered_project_coverage_gate_passes",
    ),
    SurfaceClass(
        "script:scripts/doctor.sh",
        "scripts/doctor.sh",
        _EX,
        # Behavioral: exits 0 when all required host tools are present.
        "test_doctor_passes_when_all_tools_present",
    ),
    SurfaceClass(
        "script:scripts/entrypoint.sh",
        "scripts/entrypoint.sh",
        _EX,
        # Inventory overturn (:1322): alembic upgrade head on container start + exec handoff;
        # the seeded-items dev-stack test proves migrations ran and the app serves.
        "test_rendered_project_dev_stack_serves_seeded_items",
    ),
    SurfaceClass(
        "script:scripts/export-graphql-schema.sh",
        "scripts/export-graphql-schema.sh",
        _EM,
        # Run only inside the generated ci.yml contract job (SDL export + breaking-change
        # check) on real GHA, not by a local pytest.
        "generated-CI script — runs in ci.yml's contract job on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "script:scripts/export-openapi.sh",
        "scripts/export-openapi.sh",
        _EX,
        # Run via `bash scripts/export-openapi.sh`; asserts the OpenAPI spec is exported.
        "test_rendered_project_exports_openapi",
    ),
    SurfaceClass(
        "script:scripts/gen_observability.py",
        "scripts/gen_observability.py",
        _EM,
        # Build-time codegen that serialises provisioning.py into infra/observability/. Its
        # OUTPUT (committed in-template) is validated by test_obs_completeness; it is invoked
        # by `task observability:generate`, not a local pytest.
        "build-time observability codegen — output validated by test_obs_completeness; "
        "invoked by `task observability:generate`, not a local pytest",
    ),
    SurfaceClass(
        "script:scripts/load.sh",
        "scripts/load.sh",
        _KG,
        # L2: only render-checked; runs only inside the unexercised CD validation phase
        # (k6 SLO gate).
        "FWK28 load.sh k6 SLO gate runs only in the unexercised CD validation phase",
    ),
    SurfaceClass(
        "script:scripts/pact-publish.sh",
        "scripts/pact-publish.sh",
        _EM,
        # Run only inside the generated ci.yml contracts job on real GHA (no-ops without a
        # broker); not driven by a local pytest.
        "generated-CI script — runs in ci.yml's contracts job on real GHA, not a local pytest",
    ),
    SurfaceClass(
        "script:scripts/seed.py",
        "scripts/seed.py",
        _EX,
        # The dev-stack serves seeded items (proves seed.py ran against live Postgres).
        "test_rendered_project_dev_stack_serves_seeded_items",
    ),
    # ---- compose services ------------------------------------------------------------
    SurfaceClass(
        "service:app-host.yml:app",
        "infra/compose/app-host.yml",
        _EX,
        # The app brought up on each host by the real deploy strategy.
        "test_deploy_e2e_rolling_update_has_no_downtime",
    ),
    SurfaceClass(
        "service:base.yml:app",
        "infra/compose/base.yml",
        _EX,
        # The base app definition, extended by dev.yml and served in the lite stack.
        "test_rendered_project_dev_lite_stack_serves_health",
    ),
    SurfaceClass(
        "service:dev.yml:app",
        "infra/compose/dev.yml",
        _EX,
        # Brought up --profile dev and routed through Traefik with a verified 200.
        "test_rendered_project_dev_stack_routes_through_traefik",
    ),
    SurfaceClass(
        "service:dev.yml:beat",
        "infra/compose/dev.yml:164-189",
        _EX,
        # FWK20 (H4): beat brought up live; it schedules the heartbeat task through the real
        # broker and the worker runs it, asserted via the redis liveness marker.
        "test_rendered_workers_live_broker_dlq_and_beat",
    ),
    SurfaceClass(
        "service:dev.yml:frontend",
        "infra/compose/dev.yml",
        _EX,
        # FWK24: the dev Vite server is brought up and GET / asserts the served SPA shell (id="root").
        "test_rendered_frontend_dev_server_serves_spa",
    ),
    SurfaceClass(
        "service:dev.yml:grafana",
        "infra/compose/dev.yml:74-79",
        _KG,
        # M13: grafana is merged only so --profile dev config-validation passes ('the obs
        # containers never start'); datasources/dashboards/anon-auth never queried live.
        "FWK23 grafana never brought up live (datasources/dashboards/anon-auth unqueried)",
    ),
    SurfaceClass(
        "service:dev.yml:mongo",
        "infra/compose/dev.yml:83-95",
        _KG,
        # M2: the mongo compose service block (mongosh-ping healthcheck, mongodata volume) is
        # never `compose up`-ed (the data-store round-trip is testcontainers, not this service).
        "FWK26 mongo compose service never brought up live (healthcheck/volume unasserted)",
    ),
    SurfaceClass(
        "service:dev.yml:postgres",
        "infra/compose/dev.yml",
        _EX,
        # Postgres brought up in the dev/lite stack; the app serves seeded items from it.
        "test_rendered_project_dev_stack_serves_seeded_items",
    ),
    SurfaceClass(
        "service:dev.yml:redis",
        "infra/compose/dev.yml",
        _EX,
        # FWK20: redis brought up live as the Celery broker; the worker consumes a real enqueued
        # task through it (the live broker->worker->DLQ round-trip) and beat schedules through it.
        "test_rendered_workers_live_broker_dlq_and_beat",
    ),
    SurfaceClass(
        "service:dev.yml:traefik",
        "infra/compose/dev.yml",
        _EX,
        # Traefik brought up --profile dev; a verified TLS 200 through 127.0.0.1:443 proves it.
        "test_rendered_project_dev_stack_routes_through_traefik",
    ),
    SurfaceClass(
        "service:dev.yml:worker",
        "infra/compose/dev.yml:131-162",
        _EX,
        # FWK20 (H3): the worker is brought up live and a deterministically-failing task is
        # enqueued through the real broker; on_failure writes a dead_letter_tasks row (asserted).
        "test_rendered_workers_live_broker_dlq_and_beat",
    ),
    SurfaceClass(
        "service:observability.yml:alertmanager",
        "infra/compose/observability.yml",
        _KG,
        # M12: amtool check-config (syntax) only; no test fires an alert through alertmanager
        # and asserts routing/delivery.
        "FWK23 alertmanager never routes a live notification (only amtool syntax-checked)",
    ),
    SurfaceClass(
        "service:observability.yml:app",
        "infra/compose/observability.yml",
        _EX,
        # The app under the observability overlay; Prometheus scrapes its /metrics live.
        "test_rendered_project_dev_stack_prometheus_scrapes_app",
    ),
    SurfaceClass(
        "service:observability.yml:celery-exporter",
        "infra/compose/observability.yml:106",
        _KG,
        # M10: present-but-unasserted scrape target (the only live targets test hard-filters
        # to job=='app').
        "FWK23 celery-exporter scrape target present but never asserted up==1",
    ),
    SurfaceClass(
        "service:observability.yml:grafana",
        "infra/compose/observability.yml",
        _KG,
        # M13: grafana under the obs overlay is never started live; datasources/dashboards
        # unqueried.
        "FWK23 grafana (obs overlay) never brought up live (datasources/dashboards unqueried)",
    ),
    SurfaceClass(
        "service:observability.yml:loki",
        "infra/compose/observability.yml",
        _EX,
        # The app's logs are asserted to reach Loki on the live obs stack.
        "test_rendered_project_app_logs_reach_loki",
    ),
    SurfaceClass(
        "service:observability.yml:mongodb-exporter",
        "infra/compose/observability.yml:117",
        _KG,
        # M10: battery-gated exporter scrape target, present-but-unasserted (and not rendered
        # in baseline DATA).
        "FWK23 mongodb-exporter scrape target present but never asserted up==1",
    ),
    SurfaceClass(
        "service:observability.yml:otel-collector",
        "infra/compose/observability.yml",
        _KG,
        # M10: the otel-collector self-scrape target (:8888) is present but unasserted; the
        # live targets test only checks job=='app'.
        "FWK23 otel-collector self-scrape target present but never asserted up==1",
    ),
    SurfaceClass(
        "service:observability.yml:postgres-exporter",
        "infra/compose/observability.yml:84",
        _KG,
        # M10: postgres-exporter scrape target present-but-unasserted.
        "FWK23 postgres-exporter scrape target present but never asserted up==1",
    ),
    SurfaceClass(
        "service:observability.yml:prometheus",
        "infra/compose/observability.yml",
        _EX,
        # Prometheus is brought up live and its API queried for the app scrape target.
        "test_rendered_project_dev_stack_prometheus_scrapes_app",
    ),
    SurfaceClass(
        "service:observability.yml:promtail",
        "infra/compose/observability.yml",
        _EX,
        # Promtail is the log-shipper proven by the app-logs-reach-Loki round-trip.
        "test_rendered_project_app_logs_reach_loki",
    ),
    SurfaceClass(
        "service:observability.yml:redis-exporter",
        "infra/compose/observability.yml:95",
        _KG,
        # M10: redis-exporter scrape target present-but-unasserted.
        "FWK23 redis-exporter scrape target present but never asserted up==1",
    ),
    SurfaceClass(
        "service:observability.yml:tempo",
        "infra/compose/observability.yml",
        _EX,
        # Tempo is brought up live and traces are asserted to reach it.
        "test_rendered_project_traces_reach_tempo",
    ),
    SurfaceClass(
        "service:prod.yml:app",
        "infra/compose/prod.yml:3-52",
        _EM,
        # Correction (H1 demoted): consumer-target topology; no shipped path brings prod.yml
        # up. Already compose-config merge-validated (the right guard, not live bring-up).
        "consumer-target service — no shipped path brings prod.yml up; compose-config "
        "merge-validated (inventory H1 demoted to config-validation)",
    ),
    SurfaceClass(
        "service:prod.yml:postgres",
        "infra/compose/prod.yml:3-52",
        _EM,
        "consumer-target service — no shipped path brings prod.yml up; compose-config "
        "merge-validated (inventory H1 demoted to config-validation)",
    ),
    SurfaceClass(
        "service:services.yml:beat",
        "infra/compose/services.yml:59-72",
        _KG,
        # Correction (2026-06-16): no shipped target brings services.yml up (compose-ssh uses
        # app-host.yml), so the staging/prod overlay is consumer-target scaffolding. FWK20 closed
        # the live beat path on the *dev* stack; services.yml's guard is FWK19 config-validation.
        "FWK19 services.yml beat battery service lacks batteries-on compose-config validation",
    ),
    SurfaceClass(
        "service:services.yml:mongo",
        "infra/compose/services.yml:9-19",
        _KG,
        "FWK19 services.yml mongo battery service lacks batteries-on compose-config validation",
    ),
    SurfaceClass(
        "service:services.yml:redis",
        "infra/compose/services.yml",
        _KG,
        "FWK19 services.yml redis battery service lacks batteries-on compose-config validation",
    ),
    SurfaceClass(
        "service:services.yml:worker",
        "infra/compose/services.yml:35-57",
        _KG,
        # Correction (2026-06-16): no shipped target brings services.yml up (compose-ssh uses
        # app-host.yml), so the staging/prod overlay is consumer-target scaffolding. FWK20 closed
        # the live broker->worker->DLQ path on the *dev* stack; services.yml's guard is FWK19.
        "FWK19 services.yml worker battery service lacks batteries-on compose-config validation",
    ),
    SurfaceClass(
        "service:staging.yml:app",
        "infra/compose/staging.yml:4-53",
        _KG,
        # Correction (H7 demoted): staging.yml is only substring-checked — no compose-config
        # merge-validation. FWK19 adds the parity guard.
        "FWK19 staging.yml app service lacks compose-config merge-validation (only substring-checked)",
    ),
    SurfaceClass(
        "service:staging.yml:postgres",
        "infra/compose/staging.yml:4-53",
        _KG,
        "FWK19 staging.yml postgres service lacks compose-config merge-validation (only substring-checked)",
    ),
    SurfaceClass(
        "service:test.yml:app",
        "infra/compose/test.yml:5-41",
        _KG,
        # M3: shipped + used by `task test:stack` but never brought up --profile test.
        "FWK19 test.yml app never brought up --profile test",
    ),
    SurfaceClass(
        "service:test.yml:postgres-test",
        "infra/compose/test.yml:5-41",
        _KG,
        # M3: the tmpfs ephemeral-DB reset is undriven (acceptance tier never uses --profile test).
        "FWK19 test.yml postgres-test (tmpfs ephemeral-DB reset) never brought up --profile test",
    ),
)


def registry_keys() -> set[str]:
    return {entry.key for entry in REGISTRY}

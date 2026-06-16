# Runtime/Build Coverage-Gap Inventory (FWK18)

> Ranked inventory of swiftwater-framework **template-provisioned** real-runtime/build
> surfaces that **no test exercises** (drives + asserts the effect of). Produced by the
> FWK18 multi-agent `Workflow` assessment (2026-06-15). Spec:
> `docs/superpowers/specs/2026-06-15-runtime-coverage-assessment-design.md`; plan:
> `docs/superpowers/plans/2026-06-15-coverage-assessment.md`. Each gap is a candidate
> follow-on test task; the recurring categories seed **FWK29** (the durable mechanism).

## Method & numbers

- **65 agents, ~2.77M tokens, ~20 min.** Phase 0 census (2 blind enumerators + a controller reconcile) → Phase 1 finders (one per cluster) → Phase 2 adversarial verify (one skeptic per claimed gap, told to *refute* it) → Phase 3 synthesis.
- **Census:** 130 operational surfaces enumerated; **84** fell outside the 7 seed clusters by file-path; reconcile confirmed **51 true residual** surfaces (categories the seed taxonomy missed) + 32 reassigned into existing clusters → an 8th cluster (C8) was assessed.
- **Find:** 116 surfaces across 8 clusters — **63 EXERCISED**, 53 candidate gaps (deduped).
- **Verify:** **48 gaps survived** adversarial refutation; 5 overturned (a driving test was found).
- **Synthesis:** deduped to **27 ranked entries** — originally 8 high / 15 med / 4 low; **revised 2026-06-16 to 4 high / 15 med / 7 low + 1 dropped** (see Correction below).
- **Controller hand-validation** (not an agent): spot-checked prod.yml (config-validate only — confirmed), workers-eager (confirmed `task_always_eager`, no live broker), claudesubscriptioncli (`--target builder` only — confirmed), and the dev:lite runtime build (`:720` — confirmed). All held.

### Correction (2026-06-16): deploy-model re-rank

A reviewer challenge — *"do these stand given there's no staging/prod deploy target defined?"* — exposed a risk-rating error the finders made about the **deploy model**. Verified against the template:

- The **only shipped deploy target** (`infra/deploy/targets/compose-ssh.sh`) brings up **`app-host.yml`** (app-only, no Postgres/Traefik) — *not* `prod.yml`/`staging.yml`. `DEPLOY_ENV=staging|prod` selects only the release-state filename + `APP_ENVIRONMENT`.
- `strategy.sh`'s `__target_*` hooks are **intentional `_todo` stubs that exit 1** until a consumer implements their target. `tests/test_deploy_compose_ssh.py` + `tests/acceptance/test_deploy_e2e.py` already exercise the orchestration + the `compose-ssh → app-host.yml` path (and the `_todo` fail-loudly behaviour).

Consequences for the ranking:
- **H8 (deploy CD workflow graph) — DROPPED.** The CD workflows drive a deploy that is *designed to fail loudly* until the consumer wires a target; the orchestration + real target are already covered. Only a thin workflow-graph assertion remained, and `actionlint` validates the workflow YAML. (Tombstones the proposed **FWK22**.)
- **H1 (prod.yml), H2 (services.yml), H7 (staging.yml) — DEMOTED high → low.** No shipped path brings these up; they are scaffolding for a *consumer-written* target. "Bring prod up live and assert healthy" tests a path the framework never takes — the "ships silently to a consumer's prod (FWK17 class)" rating was inflated. The right guard is cheap `docker compose config` merge-validation (CI-visible), not live bring-up. (`test.yml`, which IS shipped + used by `task test:stack`, stays a live gap — see M-tier / FWK19.)

The dev-stack/build highs the framework genuinely drives are unaffected and stand: **H3 (workers live broker→DLQ), H4 (beat), H5 (claudesubscriptioncli runtime image), H6 (react SPA served).**

### Taxonomy outcome (the independent-completeness check the user asked for)

The blind Phase-0 census confirmed the original 7 stack clusters (C1-C7) are infra-runtime/build-scoped and systematically MISS several whole lifecycle categories, which the reconcile surfaced as a distinct cluster C8 plus ~51 residual category rows (about half of them duplicates of the same underlying surface counted at two line anchors). After deduplication the genuinely-new categories beyond the 7 are: (1) the in-process APPLICATION-BOOT layer the infra clusters don't own — FastAPI app factory + lifespan, app-side OTEL TracerProvider/export, DB engine+pool lifecycle, and the health/readiness route's own SLO/worker-probe logic; (2) an entire CI-TIME phase with no cluster home — the generated ci.yml's gate/lint/security/test/build/integrity/contract/contracts/frontend/docs/AI-review-matrix jobs, exercised only by scripts/dogfood_e2e.py on real GHA (the acceptance tier is local-only and ci.yml ignores it); (3) a COMMIT/EDIT-TIME phase — pre-commit hook stack, coverage.sh gate, check_migrations.py guard, and the .claude PreToolUse/PostToolUse hooks; (4) a DEPLOY-ORCHESTRATION/CD phase — strategy.sh, compose-ssh.sh target, notify.sh, deploy-staging/prod.yml, docs.yml publish, load.sh; and (5) dev-environment/maintenance preflight — doctor.sh, dependabot.yml, export-openapi.sh. Net conclusion: clusters beyond the original 7 DO exist and matter — the key blind spot is that the framework's own test tiers cover the local runtime/build stack well but leave the CI-time, commit-time, and CD-pipeline lifecycle phases driven only by dogfood_e2e (one CI workflow) or by render/static checks, so a large fraction of provisioned surfaces are structurally uncatchable in CI.

The blind census **materially corrected the author's 7-cluster partition**: ~40% of operational surfaces (51) lived in categories the infra-centric clusters never named — the in-process **app-bootstrap** path (`create_app`/lifespan/engine-pool/health-route), the entire **CI-time** lifecycle (`ci.yml` gate/contract/AI-review/frontend/contracts/docs jobs), **commit-time** hooks (`.pre-commit-config`, `.claude/hooks`), and the **deploy-orchestration** layer (`strategy.sh`/`compose-ssh.sh`/`notify.sh`/CD workflows). Without Phase 0 these would have been silently un-assessed.

### Overturned (finder flagged a gap; the skeptic found a driving test)

- redis service (dev.yml + services.yml service definition: image redis:7-alpine, healthcheck, redisdata volume, port 6379) → `tests/acceptance/test_rendered_project.py:1920`
- scripts/entrypoint.sh — `alembic upgrade head` (apply pending migrations on container start) → `tests/acceptance/test_rendered_project.py:1322`
- scripts/entrypoint.sh — APP_RUN_MIGRATIONS gating + idempotent re-run + `exec "$@"` handoff to CMD (uvicorn) → `tests/acceptance/test_rendered_project.py:1322`
- FastAPI app factory + lifespan (create_app wiring logging/metrics/middleware/handlers/routers; lifespan engine-dispose on SIGTERM) → `src/framework_cli/template/tests/functional/test_graceful_shutdown.py.jinja:6 (driven in the acceptance tier via tests/acceptance/test_rendered_project.py:67 functional run)`
- /metrics route (Prometheus exposition + per-battery metric blocks + DLQ gauge) → `src/framework_cli/template/tests/functional/test_health.py.jinja:37 (test_metrics_is_prometheus_text), driven by tests/acceptance/test_rendered_project.py:67`

Notably this overturned the author's own pre-assessment headline assumption ("baseline `docker build` is never run"): the dev:lite stack test builds the runtime image end-to-end (`test_rendered_project.py:720`).

## Ranked inventory

### HIGH (4 — was 8; see Correction)

> **H1/H2/H7 DEMOTED → low (2026-06-16):** no shipped deploy target brings these up (`compose-ssh` uses `app-host.yml`, already covered by `deploy-e2e`); they're consumer-target scaffolding. Right guard = `compose config` merge-validation, not live bring-up. **H8 DROPPED.** See the Correction section. The standing highs are **H3, H4, H5, H6**.

**H1. infra/compose/prod.yml.jinja — production topology brought up live (promoted ${APP_IMAGE}, app+postgres healthchecks, 8000:8000, restart policy, APP_DATABASE_URL DSN, extension-image switch + shared_preload_libraries command for timescaledb/age)**  
> ⚠ **DEMOTED high → low (2026-06-16):** no shipped path brings prod.yml up; guard with `docker compose -f base.yml -f prod.yml config` merge-validation (CI-visible), not live bring-up.  
`src/framework_cli/template/infra/compose/prod.yml.jinja:3-52` · INDIRECT · local-only  
*Risk:* This is the actual production runtime topology. It is only static `docker compose config` merge-validated (test_copier_runner.py:2008,2165) — never brought up, app never built/served through it, postgres never started. A regression in the app/postgres healthcheck command, the 8000:8000 mapping, restart policy, the APP_DATABASE_URL DSN, or the timescaledb/age preload command ships silently to a consumer's prod (FWK17 class). The deploy-e2e routes through compose-ssh->app-host.yml, a DISTINCT file, so prod.yml's postgres+healthcheck path is genuinely undriven.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py: render baseline DATA, then `docker compose -f base.yml -f prod.yml up -d --build` with APP_IMAGE built locally + POSTGRES_PASSWORD set; poll until the app healthcheck passes; GET http://localhost:8000/heartbeat asserting 200 and assert `docker inspect` shows the postgres healthcheck healthy. For an extension variant, render with timescaledb and assert the postgres command carries shared_preload_libraries.

**H2. infra/compose/services.yml staging/prod battery overlay brought up live (mongo+redis+worker+beat for staging/prod, APP_IMAGE/POSTGRES_PASSWORD interpolation, merged with <env>.yml)**  
> ⚠ **DEMOTED high → low (2026-06-16):** the staging/prod battery overlay is only consumed by a consumer-written target (`app-host.yml` is app-only; `compose-ssh` never merges `services.yml`). Guard with a batteries-on `compose config` merge-validation, not a live prod bring-up. (The live worker/beat behaviour itself is H3/H4 via the **dev** stack, which stands.)  
`src/framework_cli/template/infra/compose/services.yml.jinja:1-83` · UNEXERCISED · local-only  
*Risk:* The entire staging/prod battery-services overlay (image-based worker/beat/mongo/redis) is never instantiated with batteries. Deploy-e2e and compose-ssh render baseline (no-battery) DATA, where services.yml is an effectively empty stub, AND the shipped compose-ssh target only brings up app-host.yml — services.yml's `-f` merge in strategy.sh:32-36 is a prose example, never executed. A consumer deploying a workers/redis/mongo project to staging/prod runs this file unexercised: a bad APP_IMAGE interpolation, broker env, or merge key ships silently to prod runtime.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py: render with workers+redis batteries, build+tag a local image as APP_IMAGE, then `docker compose -f prod.yml -f services.yml up -d` with POSTGRES_PASSWORD set; assert worker+beat+redis containers reach running/healthy and that the worker logs show it connected to the redis broker (or enqueue a task and assert it executes).

**H3. workers — Celery worker live job execution through a real Redis broker + DB-backed DLQ (worker compose service: command, broker/result env wiring, inspect-ping healthcheck, depends_on)**  
`src/framework_cli/template/infra/compose/dev.yml.jinja:131-162 (dev) + services.yml.jinja:35-57 (staging/prod)` · INDIRECT · local-only  
*Risk:* The workers acceptance tests run Celery EAGER (task_always_eager=True, 'no live broker required', test_rendered_project.py:391) — the live broker->worker->DLQ path is exercised by NO test. The one test that ups worker+beat (1920) asserts only __pycache__ liveness + host-UID ownership; it never enqueues through the live broker. A broken worker `command:`, wrong APP_CELERY_BROKER_URL, or bad inspect-ping healthcheck would let the worker import the package and pass silently while never actually consuming jobs — a real prod-runtime regression for any workers consumer.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py: render workers battery, `docker compose -f base.yml -f dev.yml --profile dev up -d --build redis postgres worker`, wait for the worker inspect-ping healthcheck to report healthy, enqueue a task that always fails via the app/CLI, then poll the DLQ table (psql) asserting the failed job landed — proving the real broker->worker->DLQ round-trip.

**H4. beat — Celery beat scheduler live compose service (command `celery -A {{package_name}}.tasks.app beat`, redis broker/result env, depends_on redis)**  
`src/framework_cli/template/infra/compose/dev.yml.jinja:164-184 (dev) + services.yml.jinja:59-72 (staging/prod)` · UNEXERCISED · local-only  
*Risk:* beat has no in-process eager equivalent (it is a long-running scheduler, not a .delay() call). The only test that ups beat (1920) is satisfied by the WORKER's __pycache__ write and a host-UID ownership check — beat could crash on a broker-connection failure or schedule misconfiguration and leave no root-owned residue, passing silently. The deploy-e2e renders baseline DATA so beat is absent there. A broken beat command/env ships unexercised to prod for any scheduled-jobs consumer.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py: render workers battery, up redis+beat, then assert beat is connected by tailing `docker logs` for the beat 'Scheduler: Sending due task' / 'beat: Starting...' line (or query redis for the scheduler's heartbeat key), so a beat broker-connect or scheduler-start regression fails the test rather than relying on the worker's liveness signal.

**H5. Dockerfile claudesubscriptioncli FULL runtime stage (builder w/ git -> runtime), built and run end-to-end**  
`src/framework_cli/template/infra/docker/Dockerfile.jinja:5-11 (git builder) + :24-34 (runtime)` · INDIRECT · local-only  
*Risk:* The only claudesubscriptioncli docker test builds `--target builder` ONLY (test_rendered_project.py:336-337) and asserts the builder returncode; the FULL image through runtime is never built or run. The litellm-claude-cli git dep is a FWK17-class hazard — a battery-specific runtime regression (a COPY --from=builder interaction, or a runtime need for that git dep) would pass silently because no test builds past the builder for this battery. The generic baseline runtime is covered (:720) but not this battery's runtime shape.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py (alongside :317): render claudesubscriptioncli, `docker build -f infra/docker/Dockerfile .` to the DEFAULT (runtime) target and assert returncode==0, then `docker run` the image with the app entrypoint and GET /health, asserting the runtime image actually boots with the litellm-claude-cli dep importable.

**H6. Dockerfile react runtime stage — COPY --from=frontend-build /app/frontend/dist into runtime image, served as the SPA**  
`src/framework_cli/template/infra/docker/Dockerfile.jinja:28-30 (gated react)` · INDIRECT · local-only  
*Risk:* test_rendered_react_battery_passes (:1702) builds the react runtime image but asserts ONLY build.returncode==0 (:1740) — Docker COPY succeeds whenever the source exists, so a wrong dist path or broken/empty build would still build green. Nothing runs the image and requests the served SPA (StaticFiles mount, main.py.jinja:52). A consumer's prod SPA could 404 while CI/acceptance stays green — a silent prod-runtime regression.  
*Suggested test:* In test_rendered_react_battery_passes after the build: `docker run -d -p 8000 demo-react:ci`, then GET / (or /index.html) and assert 200 with the SPA HTML body (e.g. the root div id), proving /app/frontend/dist landed in the runtime image and is served — not just that the build exited 0.

**H7. infra/compose/staging.yml.jinja — staging topology (production-equivalent: ${APP_IMAGE}, APP_ENVIRONMENT=staging, postgres extension-image switch + preload, app+postgres healthchecks, restart, pgdata, 8000:8000)**  
> ⚠ **DEMOTED high → low (2026-06-16):** same as H1 — no shipped path brings staging.yml up. The genuinely-missing piece is just the `compose config` merge-validation parity with prod.yml (staging.yml today is only substring-checked). Drop the "+ live up" half of the suggested test.  
`src/framework_cli/template/infra/compose/staging.yml.jinja:4-53` · UNEXERCISED · local-only  
*Risk:* Worse than prod.yml: staging.yml is only ever `.read_text()` substring-checked (test_copier_runner.py:2242,2273,2280) — it gets NO `docker compose config` merge-validation and is never brought up. Deploy tiers pass DEPLOY_ENV=staging but route through compose-ssh->app-host.yml. A bad merge key, healthcheck, or port in staging.yml ships to a consumer's staging runtime caught by nothing but render-text.  
*Suggested test:* Add a `docker compose -f base.yml -f staging.yml config` merge-validation test to tests/test_copier_runner.py (mirroring the prod.yml merge tests at :2008) as a CI-visible floor, AND an acceptance-tier `up -d --build` + /heartbeat 200 test in tests/acceptance/test_rendered_project.py for full runtime coverage.

**H8. Deploy strategy orchestrator + CD pipeline wiring — strategy.sh deploy/rollback driven through the CD workflow (notify, 4-phase validation, image promotion)**  
> ❌ **DROPPED (2026-06-16):** the deploy is *designed to fail loudly* (`strategy.sh` `__target_*` = `_todo` stubs) until a consumer wires a target; the orchestration + the real `compose-ssh → app-host.yml` path are already covered by `test_deploy_compose_ssh.py` + `test_deploy_e2e.py`. Only a thin workflow-graph YAML assertion remained, which `actionlint` already covers. Tombstones proposed FWK22 — no follow-on task.  
`src/framework_cli/template/infra/deploy/strategy.sh:92-129 (driven by deploy-staging.yml:34-72 / deploy-prod.yml:22-63)` · UNEXERCISED · local-only  
*Risk:* strategy.sh's deploy/rollback LOGIC is exercised by test_deploy_e2e.py/test_deploy_compose_ssh.py, but the CD workflows that orchestrate it (deploy-staging.yml, deploy-prod.yml) — build+push GHCR, image promotion, 4-phase smoke/sniff/e2e/k6 validation, if:failure rollback gating, notify — are driven by nothing. dogfood_e2e filters to the CI workflow only; the deploy step is designed to 'fail loudly' until the consumer implements the strategy. A regression in the CD job graph breaks a consumer's real deploy/rollback silently.  
*Suggested test:* Acceptance-tier cannot drive GitHub Environments; closest realistic CI-visible guard is a workflow-graph assertion in tests/test_workflows.py that deploy-staging/prod jobs chain build-push -> strategy.sh deploy -> the 4 validation steps -> `if: failure()` rollback -> notify.sh in order. True end-to-end requires extending scripts/dogfood_e2e.py to dispatch the CD workflow on a tag and poll its run (currently CI-only).

### MED (15)

**M1. Traefik HTTP->HTTPS redirect — web :80 -> websecure**  
`src/framework_cli/template/infra/traefik/traefik.yml:2-8` · UNEXERCISED · local-only  
*Risk:* No test connects to :80. The only through-Traefik test connects to 127.0.0.1:443 (test_rendered_project.py:822). A removed/broken redirect means a consumer's HTTP traffic silently fails to upgrade — a real dev/staging behavior break, but not a hard prod-data hazard (most prod ingress terminates TLS upstream).  
*Suggested test:* In tests/acceptance/test_rendered_project.py dev-stack test, after the stack is up, `socket.create_connection(('127.0.0.1', 80))` and send a raw HTTP GET with Host: {slug}.localhost; assert a 301/302/308 response with a `Location: https://` header.

**M2. mongo compose SERVICE definition (dev.yml + services.yml: image mongo:7, mongosh-ping healthcheck quoting, mongodata volume, port 27017)**  
`src/framework_cli/template/infra/compose/dev.yml.jinja:83-95 + services.yml.jinja:9-19` · INDIRECT · local-only  
*Risk:* The mongo DATA-STORE round-trip is real (testcontainers MongoDbContainer, mongo/repository.py 100%), but the compose `mongo:` service block — the mongosh-ping healthcheck quoting, mongodata volume, dev/services.yml wiring — is never `compose up`-ed. A broken healthcheck quote or volume mount means a consumer's mongo service never reports healthy, blocking dependents; the app code coverage masks it.  
*Suggested test:* In tests/acceptance/test_rendered_project.py: render mongodb battery, `docker compose -f base.yml -f dev.yml --profile dev up -d mongo`, poll `docker inspect` until the mongosh-ping healthcheck reports healthy, and assert a client can connect to 27017.

**M3. infra/compose/test.yml.jinja — test profile (app APP_ENVIRONMENT=test against ephemeral tmpfs-reset postgres-test, extension image/build switch + preload)**  
`src/framework_cli/template/infra/compose/test.yml.jinja:5-41 (driven by Taskfile test:stack)` · UNEXERCISED · local-only  
*Risk:* The acceptance tier only ever uses --profile dev/lite, never test. The sole consumer is `task test:stack`, a manual dev convenience not in `task ci`/the coverage gate, invoked by no test. A regression in the tmpfs reset, extension build context, or postgres-test healthcheck breaks a consumer's full-stack/E2E test workflow, caught by nothing.  
*Suggested test:* In tests/acceptance/test_rendered_project.py: render baseline, `docker compose -f base.yml -f test.yml --profile test up -d --build`, poll the app /health until ready, hit /items asserting 200, and bring the stack down+up again asserting postgres-test reset to empty (tmpfs) — proving the ephemeral-DB behavior.

**M4. hot-reload behavior — --reload + WATCHFILES_FORCE_POLLING (dev.yml app)**  
`src/framework_cli/template/infra/compose/dev.yml.jinja:9,15` · INDIRECT · local-only  
*Risk:* uvicorn runs --reload + WATCHFILES_FORCE_POLLING=true in every dev/lite test, but no test edits a source file and asserts the worker reloads. If polling-reload broke (env removed and inotify fails on the WSL bind mount), every test passes because none re-edits post-startup. Breaks the core dev inner-loop silently — a dev-workflow regression, not prod.  
*Suggested test:* In a dev/lite acceptance test, after /health is up, edit a rendered src/.../routes file to change a route's response, poll the route until the new response appears within a timeout, and assert the change was picked up — proving --reload + polling works on the bind mount.

**M5. Taskfile dev / dev:lite targets — full HTTPS + lite stacks driven through the `task` runner (preconditions, -f merge order, UID/GID env)**  
`src/framework_cli/template/Taskfile.yml.jinja:11-28 (dev) + :30-43 (dev:lite)` · INDIRECT · local-only  
*Risk:* Tests reproduce the compose invocation by hand (raw `docker compose ... --profile dev/lite up`), never running `task dev`/`task dev:lite`. The targets' preconditions (docker/cert-file/uv.lock/framework-integrity, Taskfile:13-21,33-36), -f merge order, and UID/GID shell-outs are never driven; no subprocess.run(['task','dev']) exists. A regression in the precondition list or merge order breaks the primary dev entrypoint — caught only when a human runs it.  
*Suggested test:* In tests/acceptance/test_rendered_project.py (which already runs `task certs`): `subprocess.run(['task','dev:lite'])` in the rendered project, wait for /health 200 over HTTP:8000, then assert the stack is up via the target itself; add a negative case removing uv.lock and asserting the precondition fails fast.

**M6. Taskfile ci / test* / db:migrate / db:seed targets driven through the `task` runner (ci task-graph chain; test:cov:ci 85% args; test:stack compose merge; framework-integrity precondition on test; db target cwd-from-root)**  
`src/framework_cli/template/Taskfile.yml.jinja:54-103,142-150,222-233` · UNEXERCISED · local-only  
*Risk:* No pytest tier runs any of these targets via `task`; the acceptance tier reproduces the BODIES directly (scripts/coverage.sh, alembic upgrade head), bypassing the target definitions' cmds/preconditions. `task ci` is exercised only by the GHA render-matrix (not an enumerated tier). A dropped/mis-chained sub-task in the ci graph or a broken db: target wiring passes every pytest tier silently.  
*Suggested test:* Add a tests/acceptance test that runs `subprocess.run(['task','db:migrate'])` then `['task','db:seed']` in a rendered project with postgres up, asserting the seed rows land; and a lighter CI-visible YAML-graph assertion in tests/test_copier_runner.py that the `ci:` target's cmds list contains lint/test:cov:ci/audit/openapi:export in order (already partially present at :3236).

**M7. OpenTelemetry tracing bootstrap — WORKER side (configure_worker_tracing: CeleryInstrumentor + provider on worker_process_init) exporting a worker/task span to Tempo**  
`src/framework_cli/template/src/{{package_name}}/observability/tracing.py.jinja:61-74` · UNEXERCISED · local-only  
*Risk:* No test runs a Celery task with OTEL on and asserts a worker/task span reaches Tempo. The Tempo test (:1009) is app-only and queries service.name='demo' (shared by app+worker), so an app span alone satisfies it — a worker-span regression passes silently. The worker-tracing unit tests monkeypatch the surface out. Breaks worker observability for any workers consumer.  
*Suggested test:* Add to tests/acceptance/test_rendered_project.py: render workers, bring up the obs+worker stack with OTEL enabled, enqueue a task through the live broker, then query Tempo /api/search filtered to a worker/task-specific span attribute (e.g. celery.task name) asserting the worker span arrived — not just service.name.

**M8. Live per-battery app routes through the running app/Traefik — websockets (/ws), webhooks (signed ingress), llm (/llm/complete + LLM metrics), graphql (/graphql), agents (/agents/run)**  
`src/framework_cli/template/src/{{package_name}}/.../routes/{websockets,webhooks,llm,graphql,agents}.py.jinja` · INDIRECT · local-only  
*Risk:* Each _passes test asserts the route reaches ~100% coverage but IN-PROCESS (TestClient / testcontainers, LLM mocked) — never a live compose stack that serves the route and a client connecting through Traefik. Baseline live-stack tests render no batteries, so these routes are never hit on a running stack. A regression manifesting only on the live ASGI/Traefik path (router not mounted, env-secret wiring, WS upgrade through proxy, introspection accidentally on at HTTP layer) passes silently.  
*Suggested test:* Add a parametrized live-stack acceptance test (one battery per case): render the battery, `--profile dev up`, then through 127.0.0.1:443 with Host header — websocket_connect /ws and echo; POST a signed payload to /webhooks asserting 200 then 401 on bad sig; POST /llm/complete (LiteLLM stubbed in the container) asserting 200 + an LLM metric series on /metrics; POST a /graphql query+mutation asserting introspection is 400; POST /agents/run asserting the tool loop responds.

**M9. react — observability-fe in-process frontend RUM metrics landing on the live app /metrics**  
`src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/src/observability/rum.ts.jinja:1` · UNEXERCISED · local-only  
*Risk:* A real RUM->/internal/rum->/metrics round-trip test EXISTS in the generated project (tests/functional/test_frontend_rum.py.jinja) but no framework tier runs the react project's python pytest — test_rendered_react_battery_passes runs only npm/vitest+docker build, never `uv run pytest`. The vitest unit test mocks sendBeacon. So the frontend telemetry pipeline is asserted by nothing live; a broken RUM ingest ships silently.  
*Suggested test:* In test_rendered_react_battery_passes, additionally run `uv run pytest -q tests/functional/test_frontend_rum.py` (or scripts/coverage.sh functional) in the rendered react project so the existing test_frontend_metrics_round_trip_through_metrics_endpoint (POST /internal/rum -> assert app_frontend_* on /metrics) actually executes.

**M10. Observability exporter services + Prometheus scrape targets — postgres-exporter:9187, redis-exporter:9121, celery-exporter:9808, mongodb-exporter:9216, otel-collector:8888, prometheus self-scrape**  
`src/framework_cli/template/infra/compose/observability.yml.jinja:84,95,106,117 + prometheus.yml.jinja:18,21` · INDIRECT · local-only  
*Risk:* The only live Prometheus-targets test (:858) hard-filters to job=='app' and asserts only that target healthy; postgres/redis/celery/mongodb/otel-collector self-scrape targets are present-but-unasserted (and the battery-gated ones not even rendered in the no-battery DATA). A bad DATA_SOURCE_NAME, wrong telemetry address, or down exporter passes silently — a consumer's dashboards/alerts go blind. Med because it degrades observability rather than breaking the request path.  
*Suggested test:* Extend test_rendered_project_dev_stack_prometheus_scrapes_app to assert the `prometheus` and `otel-collector` self-scrape targets are up (not just `app`); and add a battery variant (render redis+workers+mongodb) that ups the obs overlay and asserts the redis/celery/postgres/mongodb exporter targets report up==1 in /api/v1/targets.

**M11. Prometheus alert rules (base + per-battery _alerts.yml) actually loaded/parsed — rule_files /etc/prometheus/alerts/*.yml**  
`src/framework_cli/template/infra/observability/prometheus/alerts/slo_alerts.yml:1 (+ battery-gated *_alerts.yml.jinja)` · INDIRECT · local-only  
*Risk:* Prometheus loads the mounted alerts dir in live dev-stack tests but no test queries /api/v1/rules or /api/v1/alerts to assert the groups parsed. A malformed PromQL expr fails rule-group load while target health (the only thing asserted) stays green. Battery alert files are mostly not even rendered in the no-battery DATA. Broken alerting ships silently — degraded observability, not request-path.  
*Suggested test:* In the dev-stack obs acceptance test, GET http://localhost:9090/api/v1/rules and assert the expected rule groups (slo, postgres, otel_collector, prometheus, alertmanager) loaded with no parse errors; add a per-battery variant asserting the battery's rule group appears when its battery is rendered.

**M12. alertmanager config behavior — route/grouping/receiver delivery (webhook/slack/pagerduty/email channels)**  
`src/framework_cli/template/infra/observability/alertmanager/alertmanager.yml.jinja:1` · INDIRECT · local-only  
*Risk:* test_alertmanager_config_valid_multichannel runs `amtool check-config` (SYNTAX only); no test fires an alert through alertmanager and asserts a notification routes/dispatches. The email channel is excluded from even the syntax check. A routing/grouping/receiver-wiring regression that stays amtool-valid passes silently — broken alert delivery in prod.  
*Suggested test:* Add an acceptance test that brings up alertmanager with a webhook receiver pointed at a local capture server, POSTs an alert to /api/v2/alerts, and asserts the webhook receiver received the routed/grouped notification (mirroring the deploy-side alert_smoke pattern but against the real alertmanager.yml, not a mock).

**M13. Grafana service + datasource & dashboard provisioning (prometheus/loki/tempo datasources, provider.yml + dashboard JSON, anonymous-admin auth override)**  
`src/framework_cli/template/infra/observability/grafana/provisioning/datasources/prometheus.yml:1 + dashboards/provider.yml:1 + dev.yml.jinja:74-79` · UNEXERCISED · local-only  
*Risk:* Grafana is merged only so `--profile dev` config-validation passes; tests explicitly note 'the obs containers never start' (test_rendered_project.py:1927). No test brings Grafana up and queries /api/datasources, /api/health, or asserts dashboards/panels resolve or anonymous-admin login works. Wrong datasource URL/uid, malformed dashboard JSON, or broken anon auth ships silently — a consumer's Grafana is dead on arrival. Med: observability UX, not request-path.  
*Suggested test:* Add an acceptance test that actually starts grafana in the obs stack, then GET http://localhost:3000/api/health (anonymous) asserting 200, GET /api/datasources asserting prometheus/loki/tempo loaded and each /api/datasources/uid/<uid>/health returns OK, and GET /api/search asserting the provisioned dashboards loaded.

**M14. DB engine + pool connection-lifecycle (pool_pre_ping recovery; dispose_engine on lifespan shutdown)**  
`src/framework_cli/template/src/{{package_name}}/db/engine.py:18` · INDIRECT · local-only  
*Risk:* The engine is imported/queried, but pool_pre_ping recovery from a dropped connection is never tested, and the generated graceful-shutdown test monkeypatches dispose_engine to a stub (asserting call-site wiring, not real pool disposal). The functional suite even builds a separate test engine, bypassing the module-level pooled engine entirely. A pre-ping or dispose regression (connection leaks / stale-conn errors under prod churn) passes silently.  
*Suggested test:* Add a generated-project functional test (rendered + run by the acceptance tier) that drives the real module-level engine: kill the underlying connection (or restart the testcontainers postgres) and assert the next query succeeds via pool_pre_ping; and assert dispose_engine() actually disposes the pool (engine.pool.checkedin()/status) rather than monkeypatching it.

**M15. Claude Code PreToolUse review-gate hook (reviewers-gate-check.sh — git-commit detection, framework gate shell-out, exit-2 on FAIL, marker.json readback)**  
`src/framework_cli/template/.claude/hooks/reviewers-gate-check.sh.jinja:8-16` · UNEXERCISED · local-only  
*Risk:* Only render-text-checked (test_copier_runner.py:3172). No test invokes the hook with a PreToolUse payload and asserts it blocks/passes a commit — unlike lint_changed.py which IS driven (_run_hook at :663). A broken git-commit grep guard or a failure to translate FAIL->exit 2 means the consumer's commit gate silently never fires.  
*Suggested test:* Add a tests/acceptance helper mirroring _run_hook: pipe a PreToolUse JSON payload for a `git commit` Bash command into .claude/hooks/reviewers-gate-check.sh in a rendered project where the gate marker says FAIL, asserting exit 2; and a PASS/skip-neutral payload asserting exit 0.

### LOW (4)

**L1. Deploy notification seam (notify.sh — non-fatal deploy-notify invoked by CD workflows)**  
`src/framework_cli/template/infra/deploy/notify.sh:8-17` · UNEXERCISED · local-only  
*Risk:* notify.sh is called only by the CD workflows (never by strategy.sh), so deploy_e2e never runs it and dogfood only drives ci.yml. Tests touching it check tamper-detection/render only. It is an intentionally non-fatal seam (echo + curl-to-Slack), so a regression degrades deploy notifications without breaking the deploy — low impact.  
*Suggested test:* Add a tests/test_copier_runner-adjacent shell test that `bash infra/deploy/notify.sh 'msg'` exits 0 and echoes the '[deploy notify]' line (and, with a webhook env set, POSTs to a local capture server) — confirming the seam runs non-fatally.

**L2. k6 load-test runner (load.sh — grafana/k6 SLO load gate; CD Phase 4 / task test:load)**  
`src/framework_cli/template/scripts/load.sh:12-18` · UNEXERCISED · local-only  
*Risk:* Only render-checked (test_copier_runner.py:662). It runs only inside the unexercised CD validation phase. A regression in the k6 threshold gate would let a perf regression through in a consumer's CD, but it is a non-blocking perf gate on an opt-in pipeline — low immediate impact.  
*Suggested test:* Add an acceptance test that brings up a minimal app, runs `bash scripts/load.sh` against it, and asserts the k6 run executes and the SLO threshold pass/fail propagates as the script's exit code (pass on a healthy app).

**L3. Docs publish workflow (docs.yml — mike versioned gh-pages publish step)**  
`src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja:13-34` · UNEXERCISED · local-only  
*Risk:* Tag-only trigger; dogfood drives push/PR + filters to CI, never tags. The strict-build gate it relies on is covered separately in ci.yml's docs job; only the mike PUBLISH step (gh-pages push, VERSION/MINOR derivation) is unexercised. A regression breaks docs-site publishing — cosmetic relative to runtime/deploy.  
*Suggested test:* Lowest-cost guard: a tests/test_workflows.py assertion that docs.yml triggers on `push: tags: v*` and its job runs `mike deploy --push --update-aliases` + `mike set-default`. True publish coverage requires a dogfood_e2e extension that pushes a tag and polls the docs workflow run.

**L4. Dependabot config (.github/dependabot.yml — weekly uv-ecosystem update PRs)**  
`src/framework_cli/template/.github/dependabot.yml:8-15` · UNEXERCISED · CI-visible  
*Risk:* Only render/YAML-parse + integrity-membership checked. Dependabot's scheduled-PR behavior is a GitHub-platform feature fired on the rendered repo, fundamentally undriveable by local tiers. The existing render check already asserts ecosystem=='uv' and excludes github-actions (the integrity concern from the dependabot memory) — so the residual gap is genuinely cosmetic/redundant.  
*Suggested test:* Already adequately covered for what's testable: test_copier_runner.py:599-608 asserts the file parses, ecosystem=='uv', and github-actions is excluded. No further local test is meaningful; the runtime behavior is a GitHub platform feature.

## Follow-on test tasks (proposed)

Each gap is a candidate test PR à la FWK8/FWK17. Grouped into themed, PR-sized
tasks; sequence by risk. (IDs proposed, not yet committed to `PLAN.md` — the
prioritization call is the maintainer's.)

- **FWK19 (med — re-scoped 2026-06-16) — Non-dev compose overlays validated; test.yml up live.**
  *Two halves:* (a) **CI-visible `compose config` merge-validation** for `staging.yml` +
  batteries-on `services.yml` (parity with the existing `prod.yml` merge tests) — these
  overlays are consumer-target scaffolding the framework doesn't bring up, so validate
  their *integrity*, don't `up` them. (b) **`test.yml` brought up live** (it IS shipped +
  used by `task test:stack`): render → `-f base -f test --profile test up -d --build` →
  `/health` 200 → assert the tmpfs ephemeral-DB reset. Closes the *validation* part of
  H1/H2/H7 + the live `test.yml` gap. (Was "(high) brought up live" — the live prod/staging
  bring-up was dropped per the Correction.)
- **FWK20 (high) — Workers live broker→worker→DLQ + beat scheduler.** Render workers,
  up redis+worker+beat, enqueue a failing task through the *live* broker, assert it
  lands in the DLQ table; assert beat connects/schedules (logs/redis heartbeat). Closes
  H3, H4 (the eager-mode path is the single biggest live-runtime blind spot).
- **FWK21 (high) — Battery Docker runtime stages, built + run.** claudesubscriptioncli
  full image to the *runtime* target + `docker run` → `/health` (FWK17 class); react
  runtime image `docker run` → `GET /` asserting the SPA body (not just `build==0`).
  Closes H5, H6.
- **FWK22 — DROPPED (2026-06-16, tombstone — id not reused).** Was "Deploy CD workflow
  graph". The deploy is consumer-implemented by design (`strategy.sh` `__target_*` = `_todo`
  stubs); the orchestration + the real `compose-ssh → app-host.yml` path are already covered
  by `test_deploy_compose_ssh.py` + `test_deploy_e2e.py`, and `actionlint` validates the CD
  workflow YAML. See the Correction section.
- **FWK23 (med) — Observability live exercise.** Exporters/self-scrape targets `up==1`,
  `/api/v1/rules` parsed, alertmanager routes a webhook notification, Grafana
  datasources/dashboards resolve, worker-side OTEL span reaches Tempo. Closes the C3 med
  cluster (exporters, alert rules, alertmanager, grafana, worker tracing).
- **FWK24 (med) — Per-battery live routes through Traefik.** Parametrized: websockets
  `/ws`, signed `/webhooks`, `/llm/complete` (+ metric), `/graphql` (introspection off),
  `/agents/run` — hit through `127.0.0.1:443` on a live stack. Plus react RUM round-trip
  (`uv run pytest` the rendered react project). Closes the per-battery live-wiring meds.
- **FWK25 (med) — Taskfile targets through the `task` runner.** Drive `task dev:lite`,
  `task db:migrate`/`db:seed` (+ a negative precondition case); CI-visible YAML-graph
  asserts for `ci`. Closes the Taskfile meds.
- **FWK26 (med) — Dev-loop + service-health surfaces.** Traefik HTTP→HTTPS redirect (:80),
  hot-reload (edit-a-file-and-see-it), mongo service healthcheck up, DB engine pool
  pre-ping recovery + real `dispose_engine`. Closes the remaining C2/C4 meds.
- **FWK27 (med) — Generated-project `.claude` review-gate hook.** Pipe a PreToolUse
  payload (a `git`-staged-commit Bash command) into `reviewers-gate-check.sh` (marker
  FAIL → exit 2; PASS → 0), mirroring the existing `lint_changed.py` `_run_hook` driver.
- **FWK28 (low) — Seam/script smoke + workflow-graph asserts.** `notify.sh` non-fatal
  smoke, `load.sh` k6 gate, docs.yml `mike` publish trigger-assert. (Dependabot is
  already adequately covered — no action.)

## Seeds for FWK29 (the durable mechanism)

The surviving gaps collapse into a handful of **recurring shapes** — which is the
real product of this assessment, because they are what a framework-native reviewer
or a deterministic completeness check could catch going forward:

1. **Provisioned-but-never-up compose service/overlay** — a service block (with a
   `healthcheck`) or an overlay file that is only `compose config`-validated or
   render-text-checked, never `up`-ed and asserted healthy. (prod/staging/test,
   mongo, grafana, exporters, beat.) → *Deterministic check candidate:* every compose
   service with a `healthcheck` (or every `*.yml` overlay) must be referenced by some
   acceptance test that brings it up. Cf. the existing `test_obs_completeness` scrape/
   alert/dashboard guard — same shape, wider surface.
2. **Build target built but only `returncode==0` asserted** — `docker build` succeeds
   without the artifact being *run* (claudesubscriptioncli builder-only; react dist
   COPY). → *Check candidate:* every Dockerfile `--target`/stage reachable by a battery
   must have a build-and-run test.
3. **In-process coverage masks the live path** — a route/worker/telemetry surface at
   ~100% unit coverage (TestClient / eager Celery / mocked beacon) but never hit on a
   running ASGI/Traefik/broker stack. (per-battery routes, worker tracing, RUM, DLQ.)
4. **Script/workflow only render-checked** — a `scripts/*.sh`/`.github/workflows/*`/
   `.claude/hooks/*` surface asserted to *render* but never *run*. (notify, load, CD,
   gate hook.)

The **target-scope wrinkle** stands for FWK29: a framework-native reviewer reasoning
about `template/infra/**` provisioning vs `tests/**` coverage needs a bespoke scope —
the standard framework-target diff *excludes* the template payload. FWK29 decides
reviewer-vs-deterministic-check per shape (shapes 1–2 look deterministic; 3–4 look
judgment-heavy) from this evidence.

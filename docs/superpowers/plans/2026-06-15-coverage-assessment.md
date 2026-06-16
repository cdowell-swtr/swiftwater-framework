# Provisioned-but-Unexercised Coverage Assessment (FWK18a) — Workflow Plan

> **Not a TDD code plan.** FWK18a's deliverable is a *document* (a ranked gap
> inventory), produced by running a multi-agent `Workflow`. This plan is the
> executable design of that sweep: the per-cluster surface enumeration (the
> finders' inputs), the agent prompts + output schemas, and the self-validation
> before the inventory is committed. Spec:
> `docs/superpowers/specs/2026-06-15-runtime-coverage-assessment-design.md`.
>
> **Review this before the run** — the highest-leverage error is a finder pointed
> at an incomplete file list (a surface it never sees reads as "covered"). Eyeball
> the cluster file-lists below.

**Goal:** Produce a ranked inventory of template-provisioned real-runtime/build
surfaces that no test *exercises* (drives + asserts the effect of), so each gap
becomes a follow-on test task (à la FWK8/FWK17) and FWK18b is designed on evidence.

**Branch:** `fwk18a-coverage-assessment`. **No release** (analysis + docs only).

---

## The "exercised" rubric (every finder + verifier uses this verbatim)

A surface is **EXERCISED** iff a test **drives it and asserts its effect** — runs
the real thing (`docker build`, brings the stack up and routes/queries/scrapes
through it) and asserts a real outcome. Not exercised by: rendering it, config-
validating YAML, `compose up` without asserting *its* effect, or a unit test that
mocks it out.
- **EXERCISED** — a test drives it + asserts the effect. (cite the test)
- **INDIRECT** — it runs incidentally during some test but nothing asserts *its*
  effect; a regression in it could pass silently. (cite where it runs + what's missing)
- **UNEXERCISED** — no test touches it. (gap)

`INDIRECT` and `UNEXERCISED` are gaps.

---

## The 7 clusters are a SEED, not a closed set

The clusters below are my (the author's) enumeration — an un-audited assumption.
The finders only assess *within* their cluster; nothing in Phases 1–3 independently
checks whether the **taxonomy itself is complete** (a forgotten category → no finder
ever surfaces it). The 7 are visibly infra-centric and barely reach provisioned
execution surfaces *outside* `infra/` (`.github/workflows/*`, `.pre-commit-config.yaml`,
`alembic/`, `seed.py`, frontend build tooling). **Phase 0 (below) independently
challenges this taxonomy** before any finder runs.

## The 7 surface clusters (finder inputs — REVIEW THESE FILE LISTS)

Every path is under `src/framework_cli/template/`. Brace-named files are Copier
conditionals (rendered only when the battery is selected). Finders read the
**provisioned** side here AND grep the **test** side (next section).

### C1 — Docker image build
- `infra/docker/Dockerfile.jinja` — **all stages**: `builder`, the frontend-build
  stage (`react` battery), `runtime`. Battery-gated `apt-get install git` (FWK17).
- `infra/docker/{{ 'postgres.Dockerfile' ... }}.jinja` — extension image.
- Question to answer: is the **baseline** image (no batteries) ever `docker build`-ed
  end-to-end? Is the **runtime** stage built (vs only `--target builder`)? The
  frontend-build stage? Which battery combos get a real build?

### C2 — base / dev compose stack
- `infra/compose/base.yml.jinja`, `infra/compose/dev.yml.jinja`
- App service, healthchecks, hot-reload mounts, Traefik (`profiles: ["dev"]`),
  `infra/traefik/traefik.yml`, `infra/traefik/dynamic/tls.yml`.

### C3 — Observability stack
- `infra/compose/observability.yml.jinja`
- `infra/observability/prometheus/prometheus.yml.jinja` + `alerts/*.yml(.jinja)`
- `infra/observability/loki/`, `tempo/`, `otel/otel-collector.yml`,
  `promtail/promtail-config.yml`, `alertmanager/alertmanager.yml.jinja`
- `infra/observability/grafana/provisioning/**`, `grafana/dashboards/*.json(.jinja)`
- Question: otel-collector live path? alertmanager actually *firing* an alert?
  grafana datasources/dashboards load? the per-battery exporters scrape?

### C4 — Data + services stack
- `infra/compose/services.yml.jinja` — postgres, mongo, redis, worker, beat.
- `infra/docker/{{ postgres.Dockerfile }}.jinja` extension preload (timescaledb/age/pgvector).
- Question: are mongo/redis/worker/beat brought up **live** and exercised (a real
  enqueue→worker→result, a real mongo/redis round-trip), or only `uv sync`+unit-tested?

### C5 — Entrypoint + certs + Taskfile
- `scripts/entrypoint.sh` — alembic `upgrade head` (idempotency) + seed.
- `Taskfile.yml.jinja` — `certs`, `dev`, `dev:lite`, `ci`, `test*` targets.
- Question: is `entrypoint.sh`'s migrate+seed asserted in isolation (idempotent
  re-run; seed effect), or only incidentally via a stack-up? Which Taskfile targets
  are driven by a test vs assumed?

### C6 — Non-dev compose overlays
- `infra/compose/prod.yml.jinja`, `staging.yml.jinja`, `app-host.yml.jinja`, `test.yml.jinja`
- Question: are these ever **brought up** or even **`config`-validated**? `test.yml`
  is used by CI; `prod`/`staging`/`app-host` — does `test_deploy_e2e` /
  `test_deploy_compose_ssh` cover one, and which are untouched?

### C7 — Per-battery live wiring
- Each battery's runtime surface in a **live stack** (route hit, metric scraped,
  job run) vs only the rendered project's own unit/functional tests.
- Batteries: websockets, webhooks, workers, llm, claudesubscriptioncli, agents,
  graphql, react, redis, mongodb, pgvector, timescaledb, age, consumers, docs.
- Question: which batteries get a live-stack exercise (e.g. workers has a
  root-owned-files dev-stack guard; does anything run a real task?) vs which are
  only `_passes` (uv sync + rendered pytest)?

---

## The test side (what finders grep for "is it exercised")

- `tests/acceptance/test_rendered_project.py` — the big one (~50 tests):
  `*_serves_health`, `*_routes_through_traefik`, `*_prometheus_scrapes_app`,
  `*_logs_reach_loki`, `*_traces_reach_tempo`, `*_serves_seeded_items`,
  `*_docker_builder_stage_builds`, `*_builds_extension_image_and_migrates`,
  `*_leaves_no_root_owned_files`, `test_alertmanager_config_valid_multichannel`,
  every `*_battery_passes`.
- `tests/acceptance/test_deploy_e2e.py` — `harness_smoke`, `rolling_update`, `rollback`.
- `tests/test_deploy_compose_ssh.py`, `tests/test_obs_completeness.py`,
  `tests/test_env_parity_otel.py`, `tests/integrity/`, `scripts/dogfood_e2e.py`
  (the shipped `ci.yml` on real GHA), `tests/test_copier_runner.py` (render-only —
  NOT exercise).
- **CI reality the finder must weigh:** `ci.yml` runs `pytest --ignore=tests/acceptance`
  → the acceptance tier is **local-only**. A surface only covered by an acceptance
  test is exercised *locally* but never in CI/render-matrix — note this in `risk`.

---

## The Workflow

`Workflow` script (authored at run time; persisted to the session dir). Structure:

- **Phase 0 — Independent surface census (2 enumerators, BLIND to the 7 clusters).**
  Neither enumerator is shown my cluster taxonomy — they enumerate provisioned
  real-runtime/build surfaces from scratch over the **whole** rendered template
  (not just `infra/`), with orthogonal lenses so neither anchors on my framing:
  - *Enumerator A — by lifecycle:* for each of image-build / container-boot /
    request-serve / scheduled-background / CI-time / commit-time / deploy-time, list
    every provisioned surface that executes then (`file:line` + one-line what-it-does).
  - *Enumerator B — by directory sweep:* walk the entire tree top-to-bottom
    (`.github/`, `scripts/`, `alembic/`, `src/`, frontend, root configs, `infra/`)
    and list anything with a real runtime/build effect.

  Then a **controller reconcile (deterministic, NOT an agent):** union A+B's
  surfaces, map each onto one of the 7 clusters; the **residual** (surfaces mapping
  to none) answers "do other clusters exist?". If non-empty → it becomes an **8th
  "residual / cross-cutting" cluster** fed into Phase 1 (so the missed surfaces get
  *assessed*, not just noted), and the taxonomy gap is reported to the user.

  Enumerator schema (per surface): `{ surface, provisioned_at /*file:line*/,
  lifecycle_phase, what_it_does, maps_to_cluster?: "C1".."C7"|"NONE" }` (A/B fill
  what they can; the NONE/residual call is the controller's, not the agent's, so the
  reconcile stays independent of agent self-classification).
- **Phase 1 — Find (fan-out, 1 finder per cluster, 7 + any residual clusters, `parallel`/`pipeline`).**
  Each finder gets: the rubric (verbatim), its cluster's provisioned file-list, the
  test-side grep targets, and `read_file`/`grep`/`glob` over the repo. It returns a
  structured list of `{surface, provisioned_at (file:line), status, evidence,
  exercised_by (test:line | "none")}` covering **every** provisioned surface in its
  cluster (exercised ones included — so the synthesizer can see coverage, not just gaps).
- **Phase 2 — Adversarially verify (per claimed gap, `pipeline` stage 2).** Each
  `INDIRECT`/`UNEXERCISED` claim → a skeptic agent told to **refute** it: "find ANY
  test that drives this surface and asserts its effect; default to gap-confirmed only
  if you cannot." Returns `{surface, refuted: bool, found_test?, reasoning}`. A gap
  survives only if `refuted == false`. (This kills the FWK8 trap: dev tests *start*
  Traefik but don't route through it → that's INDIRECT, not EXERCISED.)
- **Phase 3 — Synthesize (1 agent).** Merge surviving gaps, dedup across clusters,
  rank by risk. Returns the inventory.

Models: finders/skeptics/synthesizer on the session model (Opus). Agents reason
over real files (read/grep/glob), not a diff.

### Finder schema (per surface)
```
{ surface: str, cluster: str, provisioned_at: str /*file:line*/,
  status: "EXERCISED"|"INDIRECT"|"UNEXERCISED",
  exercised_by: str /*test:line or "none"*/, evidence: str }
```

### Verifier schema (per claimed gap)
```
{ surface: str, refuted: bool, found_test: str|null, reasoning: str }
```

### Synthesizer output (the inventory entry)
```
{ surface, provisioned_at, status, risk: "high"|"med"|"low", risk_why,
  ci_visible: bool /*false if only an acceptance(local-only) test would cover it*/,
  suggested_test /*concrete: file + what it drives + what it asserts*/ }
```
Risk heuristic: **high** = a silent regression ships to a consumer's `docker build`
or prod/staging runtime (FWK17 class); **med** = breaks a dev/CI workflow caught
slowly; **low** = cosmetic/redundantly-covered-elsewhere.

---

## Run + finalize steps

- [ ] **Step 1 — Author the Workflow script** per the structure above (inline
  `script`; it persists to the session dir for re-runs). Phase 0 `parallel([enumA,
  enumB])` → controller reconcile (plain JS: union, map-to-cluster, residual) →
  build the cluster list (7 + residual). Phase 1 `pipeline(clusters, finder, gaps =>
  parallel(skeptics))` so each cluster's gaps verify as it finishes; Phase 3
  synthesize from the flattened survivors. **Log the residual** so the taxonomy
  outcome is visible even if empty.
- [ ] **Step 2 — Run it.** `Workflow({script})`. On completion, read the returned
  inventory.
- [ ] **Step 3 — Self-validate (controller, NOT an agent).** Before trusting it,
  **spot-check 3–4 claimed gaps by hand** against `tests/` — open the cited
  `provisioned_at`, grep the test side myself, confirm the gap is real (no test
  drives it). Confirm the **known** gap (baseline full-image `docker build`) appears.
  If a "gap" is actually covered, the verify step failed → note it, drop/correct it,
  and tighten before committing. (systematic-debugging if the run misbehaves.)
- [ ] **Step 4 — Write the inventory** to
  `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`: the ranked
  table + a short method note (clusters, agent counts, what was spot-checked) + a
  "follow-on test tasks" section (each high/med gap → a proposed `FWK` id, sketched).
- [ ] **Step 5 — PLAN/ACTION_LOG.** Tick FWK18a → Done with the gap count + the
  headline gaps; append an ACTION_LOG completion entry. Commit (stage PLAN/ACTION_LOG
  + the assessment doc; separate add then commit per the gate hook).
- [ ] **Step 6 — Finish the branch** ([[finishing-a-development-branch]]): one PR,
  confirm `gate`/`build`/`render-complete` green (no source touched → trivially),
  squash-merge. **No tag / no release.** Grep `master` post-merge for the assessment
  filename ([[verify-master-content-after-pr-merge]]). FWK18b is then brainstormed
  from the committed inventory.

---

## Self-Review (plan author)

- **Spec coverage:** rubric (✓ verbatim block) · 7 clusters (✓ all enumerated with
  real file lists matching the spec's search space) · Workflow find→verify→synthesize
  (✓ phases 1–3) · adversarial refute framing (✓ Phase 2) · ranked inventory schema
  (✓ synthesizer output) · output path (✓ Step 4, matches spec) · no release (✓).
- **Cluster completeness:** file lists cross-checked against `find infra -type f` —
  all 8 compose overlays, all Dockerfile stages, the full observability tree, entrypoint,
  Taskfile, traefik are assigned to exactly one cluster. C7 lists the 15 batteries.
- **False-positive guard:** the acceptance suite is large (prometheus/loki/tempo/
  deploy-e2e/root-owned all covered), so Phase 2 adversarial-verify + Step 3 manual
  spot-check are the defense against over-claiming gaps. Both present.
- **No placeholders:** schemas + prompts are concrete; the run is `Workflow`, the
  validation is a named manual check, the finalize is the standard no-release branch close.
- **Taxonomy independence (added on user review):** Phase 0's two blind enumerators +
  controller reconcile independently test whether clusters beyond the 7 exist —
  closing the "no one audits the partition" gap. The reconcile's residual is the
  answer; a non-empty residual becomes a real assessed cluster, not a footnote.

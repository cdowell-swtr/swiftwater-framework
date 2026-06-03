# CI External-Flake Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated-project CI + the framework render-matrix reliably green without re-runs — eliminate the build-time Timescale-packagecloud apt flake (for builders, not just the framework) and the oasdiff first-spec-commit 404.

**Architecture:** Part A — when `timescaledb` is present, base the custom Postgres image on a *pinned* prebuilt `timescale/timescaledb-ha` image (timescaledb preinstalled) instead of `postgres:17` + packagecloud apt, dropping the flaky apt entirely; spike-validated first, with a render-matrix-build-once-reuse fallback if `-ha` is incompatible. Part B — gate the generated `ci.yml` oasdiff step on the base branch actually having `openapi.json`. Validated by the dogfood (all-batteries incl. timescaledb) + a re-run-free render-matrix.

**Tech Stack:** Docker (multi-stage; `timescale/timescaledb-ha`, `apache/age`), Copier/Jinja template, testcontainers, GitHub Actions YAML, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-03-ci-flake-resilience-design.md`

---

## Key facts (verified — do not re-derive)

- The custom image lives in `src/framework_cli/template/infra/docker/{{ 'postgres.Dockerfile' if uses_postgres_extension else '' }}.jinja` — `FROM postgres:17` + conditional blocks: pgvector (PGDG apt `postgresql-17-pgvector`), timescaledb (packagecloud apt — the flaky one), AGE (multi-stage `COPY --from=apache/age:release_PG17_1.6.0` of `age.so` + the `age--1.6.0.sql`/`age.control` into `/usr/{lib,share}/postgresql/17/...`).
- The **compose files tag the built image `postgres:17`** (`build: dockerfile: postgres.Dockerfile` + `image: postgres:17` in dev/test; `image: postgres:17` + `command: ["postgres","-c","shared_preload_libraries={{ _preloads|join(',') }}"]` in test/prod/staging). So the Dockerfile `FROM` is internal — **no compose change** is needed for the base swap; the runtime `shared_preload_libraries` is set via the compose `command`, not baked into the image.
- testcontainers builds the image (`tests/conftest.py` `DockerImage(dockerfile_path="infra/docker/postgres.Dockerfile")` → `PostgresContainer(str(image))` + `.with_command("postgres -c shared_preload_libraries=...")`), wrapped in a 3× build/start retry (v0.1.4).
- Framework tests that must stay green on the new base: `tests/acceptance/test_rendered_project.py::test_rendered_timescaledb_battery_passes` (1279), `::test_rendered_age_battery_passes` (1132), `::test_rendered_pgvector_builds_extension_image_and_migrates` (1255); and `tests/test_copier_runner.py::test_preload_join_in_all_compose_files`.
- The `contract` job (`ci.yml.jinja`) already has the `id: spec` step (Plan 14) emitting `openapi_tracked`; the oasdiff step is gated `if: ${{ github.event_name == 'pull_request' && steps.spec.outputs.openapi_tracked == 'true' }}`.
- Commit-gate: separate `git add` then `git commit` (chained add fails the hook); update CLAUDE.md + write the `.framework/audit/marker.json` skip-marker before each commit. Controller commits; subagents stage + stop. Template `.jinja` is payload — validated by rendering, not linted as framework source.

## File structure

| File | Change |
|---|---|
| `…/infra/docker/{{ 'postgres.Dockerfile' … }}.jinja` | Conditional `-ha` base for timescaledb (Part A; per spike). |
| `…/.github/workflows/ci.yml.jinja` (`contract` job) | `base_has_openapi` probe + extend the oasdiff gate (Part B). |
| `tests/test_copier_runner.py` | Content tests: timescaledb → `-ha` base + no packagecloud; oasdiff `base_has_openapi` wiring. |
| `.github/workflows/render-matrix.yml` | Only if the fallback (build-once-reuse) is taken. |

---

## Task 1: Spike — validate the `timescale/timescaledb-ha` base (controller-driven, investigative)

Discovery, not TDD. Produces the exact `-ha`-branch Dockerfile + a pinned tag + a go/no-go. Run locally (Docker available).

- [ ] **Step 1: Pick a pinned `-ha` tag with timescaledb + pgvector**

```bash
# List recent pg17 -ha tags; pick a specific pg17.x-ts2.x (NOT floating `pg17`).
docker buildx imagetools inspect timescale/timescaledb-ha:pg17 2>/dev/null | head -5 || true
# Pull a concrete candidate (adjust to a real current tag):
docker pull timescale/timescaledb-ha:pg17.6-ts2.18.2
# Confirm timescaledb + pgvector are preinstalled (so their apt/PGDG blocks can be dropped):
docker run --rm timescale/timescaledb-ha:pg17.6-ts2.18.2 bash -lc \
  "ls /usr/lib/postgresql/*/lib/ | grep -E 'timescaledb|vector' ; ls /usr/share/postgresql/*/extension/ | grep -E 'timescaledb|vector' | head"
```
Record the exact tag that exists + bundles both. If pgvector is NOT bundled, note it (the `-ha` branch must keep a pgvector install path — check whether PGDG apt sources exist on `-ha`).

- [ ] **Step 2: Write a candidate `-ha`-based Dockerfile + build it for the key combos**

Render a candidate (hand-write a Dockerfile mirroring the conditional design from Task 2 Step 3, using the chosen tag) and build for: `timescaledb`, `timescaledb+pgvector`, `timescaledb+age`, all-three. Confirm each `docker build` succeeds (no packagecloud apt). Verify the AGE `COPY` paths resolve on the `-ha` base (`/usr/lib/postgresql/17/lib/`, `/usr/share/postgresql/17/extension/` — same Debian PGDG layout).

- [ ] **Step 3: Validate testcontainers + runtime extension loading**

For the all-three image: start it via testcontainers-style `docker run` with the compose command and assert the extensions load:
```bash
docker run -d --name ts-spike -e POSTGRES_PASSWORD=x \
  <built-all-three-image> postgres -c shared_preload_libraries=timescaledb,age
sleep 8
docker exec ts-spike psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS age;" 2>&1 | tail
docker rm -f ts-spike
```
Confirm: container starts (the `-ha` entrypoint honors `POSTGRES_*` + the `-c shared_preload_libraries` override), and all three `CREATE EXTENSION` succeed. This is the testcontainers/compose compatibility check.

- [ ] **Step 4: Decide go/no-go + record findings**

Write `docs/superpowers/eval-scorecards/ci-flake-resilience-spike-<date>.md` with: the pinned tag, whether pgvector is bundled (→ drop PGDG apt) or needs an install path, the AGE-COPY result, the testcontainers/`CREATE EXTENSION` result, and **GO** (proceed to Task 2 with the validated Dockerfile) or **NO-GO** (→ switch to the fallback: amend the plan to "render-matrix builds the image once + reuses across combos via GHCR/GHA-cache"; framework-CI-only, recorded as the deliberate fallback). Stage it.

> Tasks 2 only proceeds on **GO**. The validated Dockerfile body from this spike is what Task 2 ships.

---

## Task 2: Conditional `-ha` base in the template (per spike)

**Files:**
- Modify: `src/framework_cli/template/infra/docker/{{ 'postgres.Dockerfile' if uses_postgres_extension else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing content tests**

```python
# tests/test_copier_runner.py (append)
def test_timescaledb_uses_prebuilt_ha_base_no_packagecloud(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert "timescale/timescaledb-ha:pg17" in df  # prebuilt base, pinned pg17.x-ts2.x
    assert "packagecloud.io" not in df            # the flaky apt is gone
    assert "FROM postgres:17" not in df           # timescaledb branch swaps the base


def test_non_timescaledb_extension_keeps_postgres_base(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
    assert "FROM postgres:17" in df               # unchanged for non-timescaledb
    assert "timescaledb-ha" not in df
    assert "postgresql-17-pgvector" in df          # pgvector PGDG apt retained


def test_age_copy_present_on_both_bases(tmp_path):
    for bats in (["age"], ["timescaledb", "age"]):
        dest = tmp_path / ("p_" + "_".join(bats))
        render_project(dest, {**DATA, "batteries": bats})
        df = (dest / "infra" / "docker" / "postgres.Dockerfile").read_text()
        assert "apache/age:release_PG17_1.6.0" in df
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -q -k "ha_base or postgres_base or age_copy"`
Expected: FAIL (current Dockerfile is always `FROM postgres:17` + packagecloud).

- [ ] **Step 3: Rewrite the Dockerfile `FROM` + drop the timescaledb apt** (apply the spike-validated form)

Replace the leading `FROM postgres:17` + the pgvector and timescaledb blocks with the conditional base. The candidate below is the expected form **if the spike confirms `-ha` bundles timescaledb + pgvector**; use the exact tag + pgvector handling the spike validated:

```jinja
# Custom Postgres image — installs/bundles the active extension batteries so they are available
# on EVERY stack (dev/test/prod compose + testcontainers). Rendered only when an extension
# battery is present.
{%- if "timescaledb" in batteries %}
# timescaledb (+ pgvector) come preinstalled on the official Timescale HA image — pinned, so we
# never depend on the flaky build-time packagecloud apt. (shared_preload_libraries is set at
# runtime via the compose `command:`.)
FROM timescale/timescaledb-ha:pg17.6-ts2.18.2
{%- else %}
FROM postgres:17
{%- endif %}
{%- if "pgvector" in batteries and "timescaledb" not in batteries %}

# pgvector — vector similarity search (PGDG apt). Only needed when NOT on the HA base (which
# bundles pgvector). Acquire::Retries hardens against transient apt hiccups.
RUN apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends postgresql-17-pgvector \
 && rm -rf /var/lib/apt/lists/*
{%- endif %}
{%- if "age" in batteries %}

# Apache AGE — openCypher graph queries (multi-stage COPY of the prebuilt PG17 extension; no apt
# package). Requires shared_preload_libraries=age at runtime.
COPY --from=apache/age:release_PG17_1.6.0 /usr/lib/postgresql/17/lib/age.so /usr/lib/postgresql/17/lib/age.so
COPY --from=apache/age:release_PG17_1.6.0 /usr/share/postgresql/17/extension/age--1.6.0.sql /usr/share/postgresql/17/extension/age--1.6.0.sql
COPY --from=apache/age:release_PG17_1.6.0 /usr/share/postgresql/17/extension/age.control /usr/share/postgresql/17/extension/age.control
{%- endif %}
```
(If the spike found pgvector is NOT bundled on `-ha`, keep a pgvector install path for the timescaledb+pgvector combo per the spike's finding instead of the simple `and "timescaledb" not in batteries` exclusion.)

- [ ] **Step 4: Run content tests + render sanity**

Run:
```bash
uv run pytest tests/test_copier_runner.py -q -k "ha_base or postgres_base or age_copy or preload"
for b in "timescaledb" "timescaledb,pgvector" "timescaledb,age" "pgvector"; do
  uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('/var/tmp/p15_$b'.replace(',','_')), {'project_name':'D','out':'/var/tmp/p15','package_name':'demo','batteries':'$b'.split(','),'alert_channels':['webhook']})" 2>/dev/null
done
```
Expected: tests PASS; rendered Dockerfiles are correct per combo.

- [ ] **Step 5: Re-run the timescaledb/pgvector/age framework acceptance tests** (Docker-gated; the real build/run proof on the new base)

Run: `uv run pytest tests/acceptance/test_rendered_project.py -q -k "timescaledb or pgvector_builds or age_battery"`
Expected: PASS (the custom image builds from `-ha` + testcontainers start + extensions migrate). If a path/entrypoint issue surfaces, fix per the spike findings.

- [ ] **Step 6: Stage** (controller commits)

```bash
git add "src/framework_cli/template/infra/docker/{{ 'postgres.Dockerfile' if uses_postgres_extension else '' }}.jinja" tests/test_copier_runner.py
```

---

## Task 3: Part B — oasdiff base-spec gate

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja` (`contract` job)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing content test**

```python
# tests/test_copier_runner.py (append)
def test_oasdiff_gated_on_base_spec_existence(tmp_path):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": []})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "base_has_openapi=true" in ci and "base_has_openapi=false" in ci
    assert "curl -sfI" in ci  # probes the base branch's openapi.json over HTTP
    assert "steps.spec.outputs.base_has_openapi == 'true'" in ci  # oasdiff gated on it
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -q -k "oasdiff_gated"`
Expected: FAIL (no `base_has_openapi` wiring yet).

- [ ] **Step 3: Implement** — extend the `id: spec` step + the oasdiff gate

In the `id: spec` step's `run:` block (the openapi tracked-vs-untracked logic), after the `git ls-files`/`openapi_tracked` branch, append a base-existence probe:
```yaml
          if curl -sfI "https://raw.githubusercontent.com/{% raw %}${{ github.repository }}/${{ github.base_ref }}{% endraw %}/openapi.json" >/dev/null 2>&1; then
            echo "base_has_openapi=true" >> "$GITHUB_OUTPUT"
          else
            echo "base_has_openapi=false" >> "$GITHUB_OUTPUT"
          fi
```
Then extend the oasdiff step's `if:`:
```yaml
      - name: breaking-change check (oasdiff)
        if: {% raw %}${{ github.event_name == 'pull_request' && steps.spec.outputs.openapi_tracked == 'true' && steps.spec.outputs.base_has_openapi == 'true' }}{% endraw %}
```

- [ ] **Step 4: Run test + render sanity**

Run:
```bash
uv run pytest tests/test_copier_runner.py -q -k "oasdiff_gated or self_seeds or contract"
uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('/var/tmp/p15b'), {'project_name':'D','out':'/var/tmp/p15b','package_name':'demo','batteries':[],'alert_channels':['webhook']})"
uv run python -c "import yaml; yaml.safe_load(open('/var/tmp/p15b/.github/workflows/ci.yml')); print('ci.yml valid YAML')"
```
Expected: tests PASS; valid YAML.

- [ ] **Step 5: Stage**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py
```

---

## Task 4: Live validation (controller — acceptance)

- [ ] **Step 1: Full local gate** (per `[[gate-cadence-framework-slices]]`, ex-acceptance)

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: green.

- [ ] **Step 2: Re-run the live dogfood** (all-batteries includes timescaledb → image now from `-ha`, no packagecloud)

```bash
uv run python scripts/dogfood_e2e.py > /tmp/dogfood-p15.log 2>&1 &
```
Expected: **GREEN** for baseline + all-batteries × push/PR. Crucially, the all-batteries `test`/`build` no longer hit packagecloud — a green run **without** a timescaledb-combo re-run is the proof. (The dogfood tears itself down on green now.)

- [ ] **Step 3: Confirm the framework render-matrix on master goes green without a re-run**

After merge (Task 5), watch the push-triggered `render-matrix.yml`; the timescaledb combos should pass first-try (no packagecloud). If a Docker-Hub-pull flake still hits a combo, re-run that combo (the conftest retry should cover it) — but the packagecloud source must be gone.

- [ ] **Step 4: Record the scorecard** — `docs/superpowers/eval-scorecards/ci-flake-resilience-<date>/` with the dogfood + render-matrix run URLs + "timescaledb image builds from the pinned `-ha` base, no packagecloud". Stage.

---

## Task 5: Branch-end review, merge, release, state (controller)

- [ ] **Step 1: Branch-end review** — `superpowers:requesting-code-review` (Opus whole-branch). Focus: the conditional `-ha` Dockerfile across all extension combos (pgvector handling, AGE COPY, no orphaned packagecloud), the oasdiff `base_has_openapi` gate, and that no compose/integrity assumptions broke. Address findings.
- [ ] **Step 2: Merge FF to `master`** + push (user-authorized).
- [ ] **Step 3: Cut `v0.1.6`** — bump `pyproject.toml` 0.1.5→0.1.6 + `uv lock`; bump `DOGFOOD_COMMIT`→`v0.1.6`; commit `chore(release): v0.1.6`; tag + push; watch `release.yml` green (the broad matrix should now be flake-free for timescaledb).
- [ ] **Step 4: Update state** — meta-plan row 15 → ✅ Done (FF SHA, v0.1.6) + Remaining Sequence/footer → next is **Plan 16**; CLAUDE.md Current State pointer (concise); resolve the timescaledb-flake + oasdiff-edge follow-ups as shipped.

---

## Self-review notes (filled by the plan author)

- **Spec coverage:** Part A → Tasks 1 (spike) + 2 (conditional `-ha` base, drop packagecloud, content + acceptance tests) + the documented fallback (Task 1 Step 4). Part B → Task 3 (`base_has_openapi` gate + content test). Validation → Task 4 (dogfood + render-matrix). Release → Task 5. All spec sections mapped.
- **No placeholders:** the only spike-dependent value is the exact `-ha` tag + pgvector handling — Task 1 produces it, Task 2 ships it with a concrete candidate; this is the inherent shape of a spike-first plan, not a hand-wave. The oasdiff gate (Task 3) is fully specified.
- **Type/identifier consistency:** `base_has_openapi` (Task 3) matches its `steps.spec.outputs.base_has_openapi` gate; the timescaledb-branch base + the `and "timescaledb" not in batteries` pgvector exclusion are consistent across the Dockerfile + the content tests.
- **Risk carried from spec:** if the spike is NO-GO (`-ha` incompatible), Task 2+ pivot to the render-matrix build-once-reuse fallback (framework-CI-only) — Task 1 Step 4 gates this explicitly.

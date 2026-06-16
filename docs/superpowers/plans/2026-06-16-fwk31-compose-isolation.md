# FWK31 — Compose isolation for concurrent stacks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let multiple generated-project stacks (and the framework's own acceptance tier) run on one host simultaneously — distinct compose project namespaces and non-colliding host ports — so a UAT stack stays live in the browser while other stacks/tests run.

**Architecture:** Three template changes (a per-project compose `name:`, every published host port made `${VAR:-default}`, and a `scripts/compose.sh` wrapper that shifts all ports by `PORT_OFFSET`) plus framework acceptance-test changes (ephemeral host ports discovered via `docker compose port`, extending the `_isolate_compose_project` fixture already on this branch). Defaults preserve today's single-project DX; staging/prod deploy is untouched. Ships a patch release.

**Tech Stack:** Copier/Jinja template payload, Docker Compose v2, go-task (`Taskfile.yml`), pytest (`tests/test_copier_runner.py` for render assertions, `tests/acceptance/test_rendered_project.py` for the docker tier).

**Spec:** `docs/superpowers/specs/2026-06-16-fwk31-compose-isolation-design.md`
**Branch:** `fwk31-compose-project-isolation` (already carries the interim `_isolate_compose_project` fixture + the spec; rebased onto FWK32/`tzlocal`).

**Execution notes (read before starting):**
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): the rendered-project tests run in a GENERATED project, not the framework venv. Loop: render → edit the template source → re-render (or mirror) → assert. Most tasks here assert on *rendered text* (`test_copier_runner.py`), which only needs a render — no `uv sync`. The docker-tier tasks (5, 6) need Docker.
- **Hybrid markers** ([[hybrid-region-marker-token-in-prose]]): `.env.example.jinja` has a framework-managed region ending in the closing marker. New port vars go INSIDE that region (before the closing marker). Never write the literal marker token in prose/comments.
- **`ruff format --check`** the framework test files after edits ([[ruff-format-check-after-inline-edits]]).
- **`APP_` prefix is forbidden** for the new env vars (the generated app's pydantic-settings namespace). Use `*_HOST_PORT` / `PORT_OFFSET`.
- Per-task review cadence is the lighter framework-slice one; one branch-end Opus review (this is template payload, validated by render + acceptance).

---

## File Structure

**Template payload (rendered into consumers — ships a release):**
- Modify: `src/framework_cli/template/infra/compose/base.yml.jinja` — add top-level `name: {{ project_slug }}`.
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` — 7 ports → `${*_HOST_PORT:-default}`.
- Modify: `src/framework_cli/template/infra/compose/observability.yml.jinja` — 9 ports → `${*_HOST_PORT:-default}`.
- Create: `src/framework_cli/template/scripts/compose.sh.jinja` — `PORT_OFFSET` → exports all `*_HOST_PORT`, execs `docker compose "$@"`.
- Modify: `src/framework_cli/template/Taskfile.yml.jinja` — `dev`/`dev:lite` call `scripts/compose.sh`.
- Modify: `src/framework_cli/template/.env.example.jinja` — document the port vars + `PORT_OFFSET` inside the framework region.
- Modify: `src/framework_cli/template/infra/README.md.jinja` (or the upgrade-notes doc — confirm the path during Task 7) — upgrade re-seed note.

**Framework (no release):**
- Modify: `tests/test_copier_runner.py` — render assertions for `name:` + parameterized ports.
- Modify: `tests/acceptance/test_rendered_project.py` — ephemeral ports + port discovery + the two-stack co-run test.

---

## Task 1: Per-project compose `name:`

**Files:**
- Modify: `src/framework_cli/template/infra/compose/base.yml.jinja` (top of file)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_copier_runner.py`:

```python
def test_render_base_compose_sets_per_project_name(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    base = (dest / "infra" / "compose" / "base.yml").read_text()
    # A per-project compose name isolates container/network/volume namespaces from any
    # other stack on the host (FWK31). DATA's project_slug is "demo".
    assert "name: demo" in base
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_base_compose_sets_per_project_name -q`
Expected: FAIL — no `name:` in base.yml.

- [ ] **Step 3: Add the name to the template**

In `src/framework_cli/template/infra/compose/base.yml.jinja`, add a top-level `name:` as the FIRST yaml key (before `services:`), after the leading comment block:

```yaml
# Base service definitions, shared by all profiles. Compose merges this with the
# profile overlay: `docker compose -f infra/compose/base.yml -f infra/compose/dev.yml ...`.
# A per-project name isolates this stack's containers/network/volumes from any other stack
# on the host, so two generated projects (or a `task dev` stack and the acceptance tier)
# can coexist. COMPOSE_PROJECT_NAME in the env still overrides this when set.
name: {{ project_slug }}
services:
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_base_compose_sets_per_project_name -q`
Expected: PASS.

- [ ] **Step 5: Sanity-check the rendered compose is still valid**

Run:
```bash
cd /tmp && rm -rf fwk31t && uv run --project "$OLDPWD" python -c "
from pathlib import Path; from framework_cli.copier_runner import render_project
render_project(Path('/tmp/fwk31t/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['workers']})
" && cd /tmp/fwk31t/demo && docker compose -f infra/compose/base.yml -f infra/compose/dev.yml config >/dev/null && echo "compose config OK"
```
Expected: `compose config OK` (the `name:` parses; `config` validates the merged file).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/compose/base.yml.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk31): per-project compose name for namespace isolation"
```
(Update `PLAN.md`/`ACTION_LOG.md` first; separate `git add` then `git commit` per [[commit-gate-hook-timing]].)

---

## Task 2: Parameterize `dev.yml` host ports

**Why:** make every `dev.yml` published host port overridable (`${VAR:-default}`), defaults unchanged. The 7 ports: app `8000`, postgres `5432`, traefik `443`+`80`, mongo `27017`, redis `6379`, frontend `5173`.

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja`
- Modify: `src/framework_cli/template/.env.example.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_copier_runner.py`:

```python
def test_render_dev_compose_parameterizes_host_ports(tmp_path: Path):
    dest = tmp_path / "demo"
    # all-batteries render so mongo/redis/frontend ports are present too
    render_project(dest, {**DATA, "batteries": ["mongodb", "redis", "workers", "react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    # Every published host port is overridable with today's value as the default (FWK31).
    for var, default in [
        ("APP_HOST_PORT", "8000"),
        ("POSTGRES_HOST_PORT", "5432"),
        ("TRAEFIK_HTTPS_PORT", "443"),
        ("TRAEFIK_HTTP_PORT", "80"),
        ("MONGO_HOST_PORT", "27017"),
        ("REDIS_HOST_PORT", "6379"),
        ("FRONTEND_HOST_PORT", "5173"),
    ]:
        assert f"${{{var}:-{default}}}:" in dev, f"{var} not parameterized"
    # No APP_-prefixed host-port var (that namespace is the app's pydantic settings).
    assert "APP_HOST_PORT" in dev  # the app port var is intentionally APP_HOST_PORT? NO:
```

NOTE: the app service's host port var must NOT start with `APP_` (pydantic settings namespace, per the spec). Name it `HTTP_HOST_PORT` instead of `APP_HOST_PORT`. Correct the test to use `HTTP_HOST_PORT` (default `8000`) and drop the contradictory last two lines; the final test is:

```python
def test_render_dev_compose_parameterizes_host_ports(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "redis", "workers", "react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    for var, default in [
        ("HTTP_HOST_PORT", "8000"),
        ("POSTGRES_HOST_PORT", "5432"),
        ("TRAEFIK_HTTPS_PORT", "443"),
        ("TRAEFIK_HTTP_PORT", "80"),
        ("MONGO_HOST_PORT", "27017"),
        ("REDIS_HOST_PORT", "6379"),
        ("FRONTEND_HOST_PORT", "5173"),
    ]:
        assert f"${{{var}:-{default}}}:" in dev, f"{var} not parameterized"
    # Guard the APP_-prefix ban: no host-port var leaks into the app settings namespace.
    assert "APP_HOST_PORT" not in dev and "APP_PORT" not in dev
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dev_compose_parameterizes_host_ports -q`
Expected: FAIL (ports are still hardcoded `8000:8000` etc.).

- [ ] **Step 3: Edit `dev.yml.jinja`** — replace each `ports:` mapping (keep the existing comments/structure; only the host side changes):

```yaml
# app service
      - "${HTTP_HOST_PORT:-8000}:8000"
# postgres service
      - "${POSTGRES_HOST_PORT:-5432}:5432"
# traefik service
      - "${TRAEFIK_HTTPS_PORT:-443}:443"
      - "${TRAEFIK_HTTP_PORT:-80}:80"
# mongo service (mongodb battery)
      - "${MONGO_HOST_PORT:-27017}:27017"
# redis service (workers/redis battery)
      - "${REDIS_HOST_PORT:-6379}:6379"
# frontend service (react battery)
      - "${FRONTEND_HOST_PORT:-5173}:5173"
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_dev_compose_parameterizes_host_ports -q`
Expected: PASS.

- [ ] **Step 5: Document the vars in `.env.example.jinja`** — INSIDE the framework-managed region (before its closing marker; do NOT write the marker token here). Add a block:

```bash
# --- Local dev host ports (FWK31) ---
# Each dev/observability service publishes on these host ports. Override any of them, or
# set PORT_OFFSET to shift ALL of them at once, to run a second stack alongside this one.
# (These are read by `docker compose`, NOT by the app — do not prefix them APP_.)
PORT_OFFSET=0
HTTP_HOST_PORT=8000
POSTGRES_HOST_PORT=5432
TRAEFIK_HTTPS_PORT=443
TRAEFIK_HTTP_PORT=80
{% if "mongodb" in batteries %}MONGO_HOST_PORT=27017
{% endif %}{% if "redis" in batteries or "workers" in batteries %}REDIS_HOST_PORT=6379
{% endif %}{% if "react" in batteries %}FRONTEND_HOST_PORT=5173
{% endif %}
```

VERIFY during this step: render with no batteries + all-batteries and confirm `.env.example` still renders well-formed and that no existing test asserts the framework region contains only `APP_`-prefixed vars (grep the tests for `.env.example` assertions; the existing `DEPLOY_HOST_PORT` comment block shows non-APP vars are already present, but that's outside the region — confirm placement doesn't trip an env-parity/`.env.example` test). If a test requires region vars to be `APP_`/settings-backed, place this block in the user section instead and note it.

- [ ] **Step 6: Render + `compose config` sanity**

Run the render + `docker compose ... config` from Task 1 Step 5 (all-batteries) and confirm it still validates and that `config` shows the default ports (no env set → defaults).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja src/framework_cli/template/.env.example.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk31): parameterize dev.yml host ports (${*_HOST_PORT:-default})"
```

---

## Task 3: Parameterize `observability.yml` host ports

**Why:** the other 9 published ports, same pattern. Services + defaults: prometheus `9090`, grafana `3000`, alertmanager `9093`, loki `3100`, tempo `3200`, postgres-exporter `9187`, mongodb-exporter `9216` (mongodb battery), celery-exporter `9808` (workers battery), redis-exporter `9121` (redis/workers battery). (otel-collector is internal-only — no host port — leave it.)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/observability.yml.jinja`
- Modify: `src/framework_cli/template/.env.example.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_copier_runner.py`:

```python
def test_render_observability_parameterizes_host_ports(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb", "redis", "workers"]})
    obs = (dest / "infra" / "compose" / "observability.yml").read_text()
    for var, default in [
        ("PROMETHEUS_HOST_PORT", "9090"),
        ("GRAFANA_HOST_PORT", "3000"),
        ("ALERTMANAGER_HOST_PORT", "9093"),
        ("LOKI_HOST_PORT", "3100"),
        ("TEMPO_HOST_PORT", "3200"),
        ("POSTGRES_EXPORTER_HOST_PORT", "9187"),
        ("MONGODB_EXPORTER_HOST_PORT", "9216"),
        ("CELERY_EXPORTER_HOST_PORT", "9808"),
        ("REDIS_EXPORTER_HOST_PORT", "9121"),
    ]:
        assert f"${{{var}:-{default}}}:" in obs, f"{var} not parameterized"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_observability_parameterizes_host_ports -q`
Expected: FAIL.

- [ ] **Step 3: Edit `observability.yml.jinja`** — replace each host-port mapping:

```yaml
      - "${PROMETHEUS_HOST_PORT:-9090}:9090"        # prometheus
      - "${GRAFANA_HOST_PORT:-3000}:3000"           # grafana
      - "${ALERTMANAGER_HOST_PORT:-9093}:9093"      # alertmanager
      - "${LOKI_HOST_PORT:-3100}:3100"              # loki
      - "${TEMPO_HOST_PORT:-3200}:3200"             # tempo
      - "${POSTGRES_EXPORTER_HOST_PORT:-9187}:9187" # postgres-exporter
      - "${MONGODB_EXPORTER_HOST_PORT:-9216}:9216"  # mongodb-exporter (mongodb battery)
      - "${CELERY_EXPORTER_HOST_PORT:-9808}:9808"   # celery-exporter (workers battery)
      - "${REDIS_EXPORTER_HOST_PORT:-9121}:9121"    # redis-exporter (redis/workers battery)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_observability_parameterizes_host_ports -q`
Expected: PASS.

- [ ] **Step 5: Add the obs vars to `.env.example.jinja`** — extend the FWK31 block from Task 2 Step 5, inside the framework region, battery-gated to match:

```bash
PROMETHEUS_HOST_PORT=9090
GRAFANA_HOST_PORT=3000
ALERTMANAGER_HOST_PORT=9093
LOKI_HOST_PORT=3100
TEMPO_HOST_PORT=3200
POSTGRES_EXPORTER_HOST_PORT=9187
{% if "mongodb" in batteries %}MONGODB_EXPORTER_HOST_PORT=9216
{% endif %}{% if "workers" in batteries %}CELERY_EXPORTER_HOST_PORT=9808
{% endif %}{% if "redis" in batteries or "workers" in batteries %}REDIS_EXPORTER_HOST_PORT=9121
{% endif %}
```

- [ ] **Step 6: Render + `compose config` sanity (with observability)**

```bash
cd /tmp/fwk31t/demo && docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml config >/dev/null && echo "full dev config OK"
```
(Re-render first if needed.) Expected: `full dev config OK`.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/compose/observability.yml.jinja src/framework_cli/template/.env.example.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk31): parameterize observability.yml host ports"
```

---

## Task 4: `PORT_OFFSET` wrapper + Taskfile wiring

**Why:** the ergonomic one-knob co-run. `scripts/compose.sh` exports every `*_HOST_PORT` as `default + PORT_OFFSET` (unset offset → 0 → defaults), then execs `docker compose "$@"`. `task dev`/`dev:lite` call it. Exporting all 16 unconditionally is safe — compose only interpolates the vars referenced by the active profile/batteries.

**Files:**
- Create: `src/framework_cli/template/scripts/compose.sh.jinja`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py` + a rendered-script behavior check

- [ ] **Step 1: Write the failing test** — append to `tests/test_copier_runner.py`:

```python
def test_render_compose_wrapper_and_taskfile_use_offset(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    wrapper = dest / "scripts" / "compose.sh"
    assert wrapper.is_file()
    body = wrapper.read_text()
    # The wrapper derives host ports from PORT_OFFSET and defaults, then execs compose.
    assert "PORT_OFFSET" in body and "HTTP_HOST_PORT" in body and "exec docker compose" in body
    # Taskfile dev/dev:lite route through the wrapper (so the offset applies).
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "scripts/compose.sh" in taskfile
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_compose_wrapper_and_taskfile_use_offset -q`
Expected: FAIL (no wrapper).

- [ ] **Step 3: Create `src/framework_cli/template/scripts/compose.sh.jinja`** with exactly:

```bash
#!/usr/bin/env bash
# Thin `docker compose` wrapper: shift every published host port by ${PORT_OFFSET:-0} so a
# second stack can run alongside this one (FWK31). Each port also has its own override; this
# only sets a var when it is not already set in the environment. Then exec the compose
# command passed as arguments.
set -euo pipefail
off="${PORT_OFFSET:-0}"
_p() {  # _p VAR DEFAULT  → export VAR=$((DEFAULT+off)) unless already set
  local var="$1" default="$2"
  if [ -z "${!var:-}" ]; then export "$var"="$((default + off))"; fi
}
_p HTTP_HOST_PORT 8000
_p POSTGRES_HOST_PORT 5432
_p TRAEFIK_HTTPS_PORT 443
_p TRAEFIK_HTTP_PORT 80
_p MONGO_HOST_PORT 27017
_p REDIS_HOST_PORT 6379
_p FRONTEND_HOST_PORT 5173
_p PROMETHEUS_HOST_PORT 9090
_p GRAFANA_HOST_PORT 3000
_p ALERTMANAGER_HOST_PORT 9093
_p LOKI_HOST_PORT 3100
_p TEMPO_HOST_PORT 3200
_p POSTGRES_EXPORTER_HOST_PORT 9187
_p MONGODB_EXPORTER_HOST_PORT 9216
_p CELERY_EXPORTER_HOST_PORT 9808
_p REDIS_EXPORTER_HOST_PORT 9121
exec docker compose "$@"
```

This file is NOT jinja-templated content (no `{{ }}`), but keep the `.jinja` extension for consistency with the other `scripts/*.sh.jinja`; confirm the existing scripts use that convention (e.g. `entrypoint.sh.jinja`). If the convention is plain `.sh` for non-interpolated scripts, name it `compose.sh` accordingly.

- [ ] **Step 4: Wire the Taskfile** — in `Taskfile.yml.jinja`, change the `dev` and `dev:lite` `cmds:` to call the wrapper instead of `docker compose` directly:

```yaml
  # dev:
    cmds:
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up --build
  # dev:lite:
    cmds:
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up --build
```

(Leave the `env: {UID, GID}` blocks and preconditions unchanged. The wrapper inherits UID/GID from the task env.)

- [ ] **Step 5: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_compose_wrapper_and_taskfile_use_offset -q`
Expected: PASS.

- [ ] **Step 6: Verify the offset actually shifts ports (rendered, no live bring-up)**

```bash
cd /tmp/fwk31t/demo && chmod +x scripts/compose.sh && \
  PORT_OFFSET=100 ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite config | grep -E "8100|5532" && echo "offset applied"
```
Expected: the merged config shows host ports `8100` (app) and `5532` (postgres) — i.e. base+100. (`compose.sh ... config` runs `docker compose config` with the exported offset ports.)

- [ ] **Step 7: Confirm the rendered project's pre-commit/lint still passes the new script**

The generated project shellchecks its scripts (confirm via `.pre-commit-config`); run `shellcheck` on the rendered `scripts/compose.sh` and fix any warnings. Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/scripts/compose.sh.jinja src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py PLAN.md ACTION_LOG.md
git commit -m "feat(fwk31): scripts/compose.sh PORT_OFFSET wrapper; task dev routes through it"
```

---

## Task 5: Acceptance tests → ephemeral host ports

**Why:** the framework's docker-up tests must bind random host ports (not fixed `:8000`/`:443`/…) so they never collide with a live UAT stack or each other. Build on the `_isolate_compose_project` fixture already on this branch.

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Extend the isolation fixture to set ephemeral ports** — in `_isolate_compose_project`, after the `COMPOSE_PROJECT_NAME` line, also set every `*_HOST_PORT=0` (docker assigns a random free host port):

```python
    # FWK31: bind every published host port to an ephemeral port (0 → docker picks a free
    # one) so a test stack never collides with a live UAT stack or another test. Tests that
    # connect to a service discover the assigned port via `_compose_host_port` below.
    for var in (
        "HTTP_HOST_PORT", "POSTGRES_HOST_PORT", "TRAEFIK_HTTPS_PORT", "TRAEFIK_HTTP_PORT",
        "MONGO_HOST_PORT", "REDIS_HOST_PORT", "FRONTEND_HOST_PORT",
        "PROMETHEUS_HOST_PORT", "GRAFANA_HOST_PORT", "ALERTMANAGER_HOST_PORT",
        "LOKI_HOST_PORT", "TEMPO_HOST_PORT", "POSTGRES_EXPORTER_HOST_PORT",
        "MONGODB_EXPORTER_HOST_PORT", "CELERY_EXPORTER_HOST_PORT", "REDIS_EXPORTER_HOST_PORT",
    ):
        monkeypatch.setenv(var, "0")
```

- [ ] **Step 2: Add a port-discovery helper** — near `_compose_env`:

```python
def _compose_host_port(dest: Path, compose_files: list[str], service: str, container_port: int) -> int:
    """The ephemeral host port docker assigned to <service>:<container_port> for this stack."""
    fargs: list[str] = []
    for f in compose_files:
        fargs += ["-f", f]
    out = subprocess.run(
        ["docker", "compose", *fargs, "port", service, str(container_port)],
        cwd=dest, env=_compose_env(), capture_output=True, text=True, check=True,
    ).stdout.strip()
    # docker prints "0.0.0.0:NNNNN" (or "[::]:NNNNN"); take the trailing port.
    return int(out.rsplit(":", 1)[1])
```

- [ ] **Step 3: Update `test_rendered_project_dev_lite_stack_serves_health`** — replace the hardcoded `http://localhost:8000/health` with the discovered port. After the `up` assert, before the poll loop:

```python
        port = _compose_host_port(
            dest, ["infra/compose/base.yml", "infra/compose/dev.yml"], "app", 8000
        )
        url = f"http://localhost:{port}/health"
```
and change the poll to `urllib.request.urlopen(url, timeout=3)`.

- [ ] **Step 4: Update the other connecting docker-up tests the same way** — apply the discover-then-connect pattern to each test that connects to a fixed host port:
  - `test_rendered_project_dev_stack_routes_through_traefik` (line ~802): discover the traefik HTTPS port (`_compose_host_port(dest, [base, observability, dev], "traefik", 443)`) and connect to `127.0.0.1:<that>` with the `Host: {slug}.localhost` header (replaces hardcoded `:443`).
  - `test_rendered_project_dev_stack_prometheus_scrapes_app` (line ~880): discover the prometheus port (container 9090) and query that.
  - `test_rendered_project_dev_stack_serves_seeded_items` (line ~1295): discover the app/traefik port it connects to.
  The three `*_leaves_no_root_owned_files` tests (1836, 1942, 2027) and `test_frontend_dev_command_uses_npm_ci_not_install` (1923) do NOT connect to a host port — the fixture's `*_HOST_PORT=0` is sufficient; no edit beyond the fixture.

For each: read the test, find the `urlopen`/socket connect to a fixed port, replace with the discovered port. Show the exact before/after in the commit.

- [ ] **Step 5: Run the docker acceptance tests (requires Docker; serial)**

Run:
```bash
TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k "dev_lite_stack_serves_health or routes_through_traefik or prometheus_scrapes or serves_seeded" -p no:cacheprovider
```
Expected: PASS, now on random host ports. (Capture pytest's own exit code; don't pipe through `tail`.) If a test still hardcodes a port, fix it.

- [ ] **Step 6: Commit**

```bash
git add tests/acceptance/test_rendered_project.py PLAN.md ACTION_LOG.md
git commit -m "test(fwk31): acceptance docker tier binds + discovers ephemeral host ports"
```

---

## Task 6: Two-stack co-run acceptance test (the definitive proof)

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the test** — it renders one project and brings up TWO independent stacks of it concurrently under distinct project names + offsets, asserts both serve `/health`, then tears both down (each `down -v` touches only its own volume). Append:

```python
def test_two_dev_lite_stacks_corun_without_collision(tmp_path, monkeypatch):
    """FWK31: two stacks of the same project run at once — distinct compose projects +
    PORT_OFFSET-shifted host ports — and tearing one down leaves the other healthy."""
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    files = ["infra/compose/base.yml", "infra/compose/dev.yml"]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]

    def up(project: str, offset: int) -> int:
        env = {**_compose_env(), "COMPOSE_PROJECT_NAME": project, "HTTP_HOST_PORT": str(8000 + offset),
               "POSTGRES_HOST_PORT": str(5432 + offset)}
        assert subprocess.run(["docker", "compose", *fargs, "--profile", "lite", "up", "-d", "--build"],
                              cwd=dest, env=env).returncode == 0, f"{project} up failed"
        return 8000 + offset

    def down(project: str) -> None:
        subprocess.run(["docker", "compose", *fargs, "--profile", "lite", "down", "-v"],
                       cwd=dest, env={**_compose_env(), "COMPOSE_PROJECT_NAME": project})

    def healthy(port: int) -> bool:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=3) as r:
                    if r.status == 200:
                        return True
            except OSError:
                time.sleep(2)
        return False

    # NOTE: this test sets COMPOSE_PROJECT_NAME/ports explicitly, so it must run with the
    # autouse fixture's values overridden — pass env= explicitly (done above) so the
    # per-stack project/ports win.
    p_a = up("swfwacc-corun-a", 0)
    try:
        p_b = up("swfwacc-corun-b", 100)
        try:
            assert healthy(p_a) and healthy(p_b), "both stacks must serve /health concurrently"
            down("swfwacc-corun-a")  # tear A down...
            assert healthy(p_b), "B stays healthy after A's down -v (isolated volumes)"
        finally:
            down("swfwacc-corun-b")
    finally:
        down("swfwacc-corun-a")
```

NOTE during implementation: the autouse `_isolate_compose_project` sets `COMPOSE_PROJECT_NAME` + `*_HOST_PORT=0` in `os.environ`; this test passes explicit `env=` dicts to each subprocess so those win. Confirm the `up`/`down` env dicts fully specify project + ports (they do). The `:8000+offset` ports are fixed (not ephemeral) here because the test needs to know them to poll; pick offsets unlikely to collide with a real local stack (0 and 100 — or parametrize to ephemeral + discover if 8000 is commonly taken in CI; CI runs this on a clean runner).

- [ ] **Step 2: Run it (Docker; ~3-4 min)**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_two_dev_lite_stacks_corun_without_collision -p no:cacheprovider -v`
Expected: PASS — both stacks healthy at once; B survives A's teardown.

- [ ] **Step 3: Commit**

```bash
git add tests/acceptance/test_rendered_project.py PLAN.md ACTION_LOG.md
git commit -m "test(fwk31): two concurrent dev:lite stacks co-run without collision"
```

---

## Task 7: Upgrade note, full validation, review, release

**Files:** the generated upgrade-notes/README doc + verification only.

- [ ] **Step 1: Add the upgrade re-seed note** — find where the generated project documents upgrades (grep the template for an `infra/README` or upgrade-notes file; confirm the path). Add a short note:

```markdown
### Upgrading past FWK31 (compose project name)

This release sets a per-project `name:` in `infra/compose/base.yml`, so your stack's compose
project changes from `compose` to `<project_slug>`. Your existing `compose_*` volumes
(including the dev Postgres data) are orphaned, not migrated — the new stack starts with a
fresh DB. For local dev, re-seed: `task dev` then `task db:migrate db:seed`. (Production is
unaffected: deploy compositions don't use base.yml.)
```

If there is no such doc, add it to the generated `README.md.jinja` under a "Local development" / upgrade section. Add a `test_copier_runner.py` assertion that the note renders.

- [ ] **Step 2: Render validation across battery sets** — baseline, all-batteries, and a workers+react render; for each, `docker compose ... config` validates (defaults), and `PORT_OFFSET=100 ./scripts/compose.sh ... config` shows shifted ports. Confirm `.env.example` renders well-formed for no-batteries and all-batteries.

- [ ] **Step 3: Full framework gate**

```bash
uv run pytest -q            # (TMPDIR=/var/tmp if running the docker tier)
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. Note the docker acceptance tier needs Docker + `:8000`/`:5432` free for the co-run test (or it runs on a clean CI runner).

- [ ] **Step 4: Branch-end review** — spec-compliance (Sonnet) against the spec, then code-quality (Opus) over `git diff master..HEAD`. Address findings. Controller verifies commits.

- [ ] **Step 5: Finish the branch** — update `PLAN.md` (move FWK31 → Done with a `log:` pointer; this is the full FWK31, superseding the interim line) + `ACTION_LOG.md`. PR #45 becomes the complete FWK31. Required checks: `gate` + `build` + `render-complete`.

- [ ] **Step 6: Cut the release** — this ships template payload, so per [[release-cut-procedure]]: bump pyproject + `uv lock` + DOGFOOD_COMMIT + meta-plan/CLAUDE.md, `chore(release)` commit, tag → `release.yml`. Do this after merge (or as the final commit on the branch per the repo's release convention — confirm whether releases are cut on `master` post-merge). Note in the release notes: consumers get compose isolation; the upgrade re-seed applies.

---

## Self-Review (completed during planning)

- **Spec coverage:** §1 name → Task 1 ✓; §2 dev ports → Task 2 ✓; §2 obs ports → Task 3 ✓; §3 offset knob → Task 4 (`scripts/compose.sh`) ✓; §4 ephemeral test ports → Task 5 ✓; two-stack proof (§6 testing) → Task 6 ✓; §5 upgrade note → Task 7 ✓; release → Task 7 ✓.
- **Placeholder scan:** the only deferred specifics are flagged as explicit VERIFY steps (the `.env.example` region-placement vs an env-parity test; the `.sh.jinja` vs `.sh` naming convention; the upgrade-doc path) — these are "read the existing convention and match it" verifications, not unfilled code. The app-port var name correction (`HTTP_HOST_PORT`, not `APP_HOST_PORT`) is resolved in Task 2.
- **Type/name consistency:** the 16 `*_HOST_PORT` names + `PORT_OFFSET` are identical across the compose edits (Tasks 2–3), the wrapper (Task 4), the `.env.example` (Tasks 2–3), the fixture + discovery (Task 5), and the co-run test (Task 6). `HTTP_HOST_PORT` (app) is used consistently, never `APP_HOST_PORT`.
- **Open verification deferred to implementation (flagged inline):** `.env.example` framework-region placement (Task 2 Step 5); `scripts/*.sh.jinja` naming convention (Task 4 Step 3); shellcheck of the new script (Task 4 Step 7); the upgrade-doc path (Task 7 Step 1).

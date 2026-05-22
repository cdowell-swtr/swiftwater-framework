# Deploy Seam (Plan 5b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects ship a **complete, correct deploy *orchestration*** — `deploy-staging.yml` / `deploy-prod.yml` with the spec §14 build→push→deploy→validate→rollback sequence and all four validation phases (smoke, sniff, staging-E2E, k6 load) — plus an **opinionated deploy-strategy skeleton** that pre-decides every target-independent concern (release versioning, migration-aware rollback, health-gating, runtime secrets), so the builder's only remaining job for their chosen *target* is **configuration + a handful of mechanical `__target_*` hooks (place the image, reach the DB, persist release state)**, never architecture.

**Architecture:** Everything is **template payload** under `src/framework_cli/template/`. The validation tiers (`tests/smoke/`, `tests/sniff/`, `tests/non_functional/`, and a target-aware `tests/e2e/`) are real, runnable software — they hit a target URL via `httpx`/k6 and are validated against the generated project's own live `lite` stack (Docker acceptance), exactly like the existing live-stack tests. The framework's mission is to **offload** architectural decisions, not delegate them ([[offload-architecture-not-delegate]]): the deploy **target** (compose-over-SSH / Fly / Render / k8s) is genuinely the builder's choice, but the **strategy** is *maximally prefigured*. `infra/deploy/strategy.sh` is an **opinionated skeleton** — every operation's correct pattern is written (release id = image tag = git SHA recorded with its Alembic revision in a host state file; `rollback` downgrades migrations to the previous release's revision *and* redeploys the previous image; `await-healthy` reuses the smoke gate; config is validated with a "which var is missing" error) — and only the literal target-specific commands (place image, reach the DB) are marked gaps. `infra/deploy/README.md` + `DEPLOY.md` are **prescriptive** (decision table, the spec §1 antipatterns called out, expand/contract migration discipline, runtime-secrets rule, no-downtime cutover options), so the builder configures and connects rather than architects. A **complete, host-validated concrete reference strategy** (compose-over-SSH + Traefik/ACME blue-green) is a dedicated follow-up (**Plan 5c**) — doing it correctly needs a real host + prod Traefik, and shipping a half-correct one would be the antipattern. GitHub Actions YAML is validated by render + `actionlint` (it cannot be executed locally); the logic it invokes (the suites, `scripts/load.sh`, `strategy.sh`) lives in testable scripts/tests the framework runs.

**Tech Stack:** GitHub Actions, GHCR (`ghcr.io/${{ github.repository }}` via `GITHUB_TOKEN`), Docker Compose (staging/prod topologies), `httpx` (smoke/sniff/remote-e2e — already a dev dep), Grafana **k6** (official Docker image, no local install), `bash` + `shellcheck`, `actionlint`. Builds on Plan 5a (`ci.yml`, `scripts/coverage.sh`, the in-process e2e tier).

**Source spec:** `docs/superpowers/specs/2026-05-20-framework-design.md` §14 (Deployment Contract; CD Staging 4-phase validation; CD Prod), §6 (sniff/NFR coverage), §8 (SLO/recoverability, alert routing), §15 (`task test:sniff`), §21 (concrete strategies designed separately — here, the *target* is the builder's choice; the *strategy patterns* are prefigured). Roadmap row: Plan 5b in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## Scope & Non-Goals

This is **Plan 5b** — the deploy half of Plan 5 (5a shipped the CI pipeline). Single plan (the CD-workflow half is modest once the validation suites exist).

**In scope:**
1. **Smoke tests (Phase 1)** — `tests/smoke/` + `task test:smoke`: hit `/heartbeat` + `/health` against a target, assert no `breached` SLO and round-trip < 2× the p99 threshold.
2. **Sniff tests (Phase 2)** — `tests/sniff/` + `task test:sniff` (`SNIFF_TARGET`): fast stateless probes of `/health` + the core read path (`/items`).
3. **k6 load (Phase 4)** — `tests/non_functional/load.js` + `scripts/load.sh` + `task test:load`: k6 via its Docker image; thresholds map 1:1 to the SLO defs.
4. **Staging-E2E (Phase 3)** — make the 5a `tests/e2e/` tier **target-aware**: in-process (CI, testcontainers) **or** against a real base URL (`E2E_TARGET`).
5. **Production Compose topology** — `infra/compose/staging.yml`, `infra/compose/prod.yml` (the same images, production-equivalent config).
6. **Opinionated deploy-strategy skeleton** — `infra/deploy/strategy.sh` (7-operation contract with every target-independent pattern **pre-written**: config validation, release id + Alembic revision recorded to a host state file, **migration-aware rollback**, health-gating; only the literal "place image"/"reach DB" commands are marked target gaps), `infra/deploy/notify.sh` (notification seam), `infra/deploy/README.md` (prescriptive contract: decision table, antipattern callouts, expand/contract migrations, runtime-secrets/env-on-target rule).
7. **`deploy-staging.yml`** — on merge to `main`: build+push image to GHCR → `strategy deploy` (records release+revision) → `await-healthy` → resolve `endpoints` → Phase 1→2→3→4 → `rollback` on failure (reverses migrations + redeploys prior image) → notify.
8. **`deploy-prod.yml`** — manual approval (GitHub Environment) / tag: reuse the staging image → `strategy deploy` → smoke + sniff (read-only) → rollback → notify.
9. **Docs** — a prescriptive, builder-facing `DEPLOY.md` (required target env vars, antipatterns, migration discipline) + README/CLAUDE.md CI/CD additions; meta-plan + state.

**Non-goals (deliberate):**
- **A complete, validated concrete reference strategy** (compose-over-SSH + Traefik/ACME blue-green) — queued as a dedicated follow-up, **Plan 5c**. A *correct* no-downtime implementation needs a real host + prod Traefik/ACME to validate (not framework CI), and shipping a half-correct one would be exactly the antipattern we're avoiding ([[offload-architecture-not-delegate]]). 5b ships the opinionated skeleton (every target-independent decision pre-made) so a builder configures, not architects; 5c makes one target turnkey.
- **A Python language binding for the strategy** — §14 says the binding is "defined with the first concrete strategy." The seam is a shell contract (operation dispatcher), which is language-agnostic and what GitHub Actions calls directly.
- **An interactive `copier.yml` wizard** for registry/notification (§3) — the registry defaults to GHCR via `github.repository`; notifications are a documented `notify.sh` seam. Adding wizard questions is a separate enhancement; out of scope.
- **Prometheus remote-write of k6 results into Grafana** (§14 Phase 4 detail) — the k6 run gates on SLO thresholds and emits a CI summary/artifact; wiring remote-write into the running Grafana is a follow-up (needs a reachable Prometheus from the deploy runner). Noted in `DEPLOY.md`.
- **Worker / webhook / WebSocket sniff probes** (§14 Phase 2) — those batteries don't exist yet (Plan 8); sniff covers the present surface (health + `/items`) and is documented as the place to add probes per battery.

**Critical conventions (repo CLAUDE.md):** files under `src/framework_cli/template/` are template *payload* (the framework's own `ruff`/`mypy` exclude them); validated by rendering + running the generated project. A payload file gets a `.jinja` suffix **iff** it contains Copier variables (`{{ package_name }}` / `{{ project_slug }}`); otherwise plain. **Deploy workflows + production Compose + the deploy scripts contain NO Copier vars (they use `${{ github.* }}` GitHub expressions and `${VAR}` Compose interpolation, neither of which is Jinja), so they are plain `.yml`/`.sh` — copied verbatim, no `{% raw %}` needed.** Shell scripts must be `shellcheck`-clean (the Plan 5a pre-commit hook lints them); workflows must be `actionlint`-clean.

---

## File Structure

New template-payload files:

| File | Suffix | Responsibility |
|---|---|---|
| `tests/smoke/__init__.py` | `.py` | Package marker. |
| `tests/smoke/conftest.py` | `.py` (no vars) | `target` + `client` fixtures (httpx against `SMOKE_TARGET`). |
| `tests/smoke/test_smoke.py` | `.py` (no vars; HTTP only) | Phase-1 checks: heartbeat/health up, no breached SLO, round-trip < 2× p99. |
| `tests/sniff/__init__.py` | `.py` | Package marker. |
| `tests/sniff/conftest.py` | `.py` (no vars) | `client` fixture (httpx against `SNIFF_TARGET`). |
| `tests/sniff/test_sniff.py` | `.py` (no vars) | Phase-2 probes: `/health` ok, core read path `/items` shape. |
| `tests/non_functional/__init__.py` | `.py` | Package marker. |
| `tests/non_functional/load.js` | `.js` (no vars) | k6 script; SLO-derived thresholds. |
| `scripts/load.sh` | `.sh` (no vars) | Run k6 (Docker image) against `K6_TARGET` with the p99 threshold. |
| `infra/compose/staging.yml` | `.yml` (no vars) | Staging topology (app image + postgres), production-equivalent. |
| `infra/compose/prod.yml` | `.yml` (no vars) | Prod topology (identical shape, `APP_ENVIRONMENT=prod`). |
| `infra/deploy/strategy.sh` | `.sh` (no vars) | Opinionated 7-operation skeleton: target-independent patterns pre-written (config validation, release+revision state file, migration-aware rollback, health-gate); only target commands are marked gaps. |
| `infra/deploy/notify.sh` | `.sh` (no vars) | Deploy-notification seam; logs by default, documents how to wire a channel. |
| `infra/deploy/README.md` | `.md` (no vars) | Prescriptive contract: operations, guarantees, decision table, antipattern callouts, expand/contract migrations, runtime-secrets/env-on-target rule. |
| `.github/workflows/deploy-staging.yml` | `.yml` (no vars) | CD staging: build+push → deploy → 4-phase validate → rollback/notify. |
| `.github/workflows/deploy-prod.yml` | `.yml` (no vars) | CD prod: approval → reuse image → deploy → smoke+sniff → rollback/notify. |
| `DEPLOY.md.jinja` | `.jinja` (uses `{{ project_name }}`) | Builder-facing deploy guide. |
| `scripts/check_migrations.py` | `.py` (no vars) | Migration reversibility guard: fails any migration with a missing/empty/`pass`/`raise` `downgrade()`. |

Modified template-payload files:

| File | Change |
|---|---|
| `src/framework_cli/template/pyproject.toml.jinja` | Narrow `[tool.pytest.ini_options] testpaths` to the three in-process tiers (so bare `pytest` doesn't collect the env-targeted suites). |
| `src/framework_cli/template/tests/conftest.py.jinja` | Make `e2e_client` → `api_client`, target-aware (in-process **or** `E2E_TARGET`); seed the baseline so the happy path holds in both modes. |
| `src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja` | Assert the seeded baseline (works in-process + remote); keep the 404 unhappy path. |
| `src/framework_cli/template/Taskfile.yml.jinja` | Add `test:smoke`, `test:sniff`, `test:load`. |
| `src/framework_cli/template/.pre-commit-config.yaml` | Add the `migrations-reversible` hook (Task 9). |
| `src/framework_cli/template/.github/workflows/ci.yml.jinja` | Add a `check_migrations.py` step to the `lint` job (Task 9). |
| `src/framework_cli/template/README.md.jinja` | Add a "Deploy" subsection pointing at `DEPLOY.md` + the CD workflows. |
| `src/framework_cli/template/CLAUDE.md.jinja` | Add deploy/validation-tier guidance + strengthen the migration convention (reversibility, all paradigms) in the managed block. |

Modified framework-source tests:

| File | Change |
|---|---|
| `tests/test_copier_runner.py` | Render assertions for all the above. |
| `tests/acceptance/test_rendered_project.py` | Docker live-stack tests: smoke + sniff + remote-e2e against the rendered `lite` stack; assert the deploy workflows render + actionlint-clean (folded into `precommit_runs_clean`, which already runs actionlint). |

---

## How to render & run during execution

```bash
uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})"
cd "/tmp/demo" && uv sync
```

Re-render after EVERY template edit. **Docker is available.** The validation suites are exercised against the rendered project's **`lite`** stack (app on `http://localhost:8000`, seeded with `alpha`/`beta`), brought up exactly like the existing `test_rendered_project_dev_lite_stack_serves_health` acceptance test:

```bash
cd "/tmp/demo" && uv lock
docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up -d --build
# ... run suites against http://localhost:8000 ...
docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite down -v
```

### Committing in this repo (a hook will block you otherwise)
A `PreToolUse` hook blocks `git commit` unless `CLAUDE.md` has a **staged change**. Per commit: (1) bump the `**Last updated:**` line in `CLAUDE.md`; (2) `git add <files> CLAUDE.md` in ONE call; (3) `git commit` in a SEPARATE call (the hook checks staged state before the command runs). Avoid the word "commit" in other shell commands (the hook regex is broad).

---

## Task 1: Smoke tests (Phase 1) + testpaths narrowing

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `src/framework_cli/template/tests/smoke/__init__.py`
- Create: `src/framework_cli/template/tests/smoke/conftest.py`
- Create: `src/framework_cli/template/tests/smoke/test_smoke.py`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Narrow `testpaths` so bare `pytest` ignores env-targeted suites**

In `src/framework_cli/template/pyproject.toml.jinja`, change:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

to:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
# Default collection = the in-process tiers only. The env-targeted suites (smoke/sniff/
# non_functional) run explicitly via their own tasks / the deploy workflows against a
# real target — collecting them under a bare `pytest` would fail (no target up).
testpaths = ["tests/unit", "tests/functional", "tests/e2e"]
```

- [ ] **Step 2: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_smoke_suite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    assert (dest / "tests" / "smoke" / "test_smoke.py").is_file()
    smoke = (dest / "tests" / "smoke" / "test_smoke.py").read_text()
    assert "SMOKE_TARGET" in smoke
    assert "/heartbeat" in smoke and "/health" in smoke

    pyproject = (dest / "pyproject.toml").read_text()
    assert '"tests/unit", "tests/functional", "tests/e2e"' in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:smoke:" in taskfile
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_smoke_suite -q`
Expected: FAIL — `tests/smoke/test_smoke.py` does not exist.

- [ ] **Step 4: Create the smoke suite**

Create `src/framework_cli/template/tests/smoke/__init__.py` (empty).

Create `src/framework_cli/template/tests/smoke/conftest.py`:

```python
"""Smoke tests (CD Phase 1) — hit a deployed target's liveness/readiness surface.

Target via SMOKE_TARGET (default the local `lite` stack). These run against a REAL
environment in deploy-staging.yml / deploy-prod.yml, and locally via `task test:smoke`.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

DEFAULT_TARGET = "http://localhost:8000"


@pytest.fixture(scope="session")
def target() -> str:
    return os.environ.get("SMOKE_TARGET", DEFAULT_TARGET).rstrip("/")


@pytest.fixture
def client(target: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=target, timeout=10.0) as c:
        yield c
```

Create `src/framework_cli/template/tests/smoke/test_smoke.py`:

```python
"""Phase 1 — fast, dependency-light checks that a deployment is alive and meeting SLOs."""

import time

import httpx


def test_heartbeat_is_200(client: httpx.Client):
    resp = client.get("/heartbeat")
    assert resp.status_code == 200


def test_health_reports_no_breached_slo(client: httpx.Client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    breached = [k for k, v in body["slos"].items() if v["status"] == "breached"]
    assert not breached, f"SLOs breached on the deployed target: {breached}"


def test_health_round_trip_within_2x_p99(client: httpx.Client):
    # Spec Phase 1: every service responds within 2x its defined p99 latency threshold.
    start = time.perf_counter()
    resp = client.get("/health")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert resp.status_code == 200
    threshold_ms = resp.json()["slos"]["request_latency_p99_ms"]["threshold"]
    assert elapsed_ms < 2 * threshold_ms, (
        f"/health round-trip {elapsed_ms:.0f}ms exceeded 2x p99 ({threshold_ms}ms)"
    )
```

- [ ] **Step 5: Add `task test:smoke`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after the `test:e2e` task:

```yaml
  test:smoke:
    desc: Phase-1 smoke checks against a target (SMOKE_TARGET=url; default localhost:8000).
    cmds:
      - uv run pytest tests/smoke -q
```

- [ ] **Step 6: Run the render assertion + smoke against the live `lite` stack (Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_smoke_suite -q` → PASS.

Then exercise the suite against the rendered project's live stack:
```bash
cd "/tmp/demo" && uv lock
docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up -d --build
# wait for /health, then:
SMOKE_TARGET=http://localhost:8000 uv run pytest tests/smoke -q
docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite down -v
```
Expected: 3 passed (the seeded `lite` app reports healthy SLOs).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja src/framework_cli/template/tests/smoke src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): Phase-1 smoke suite + task test:smoke; narrow default testpaths"
```
(Add `CLAUDE.md` to the `git add`, separate call from commit — see "Committing".)

---

## Task 2: Sniff tests (Phase 2)

**Files:**
- Create: `src/framework_cli/template/tests/sniff/__init__.py`
- Create: `src/framework_cli/template/tests/sniff/conftest.py`
- Create: `src/framework_cli/template/tests/sniff/test_sniff.py`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_sniff_suite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sniff = (dest / "tests" / "sniff" / "test_sniff.py")
    assert sniff.is_file()
    text = sniff.read_text()
    assert "SNIFF_TARGET" in text
    assert "/items" in text

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:sniff:" in taskfile
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_sniff_suite -q`
Expected: FAIL — `tests/sniff/test_sniff.py` does not exist.

- [ ] **Step 3: Create the sniff suite**

Create `src/framework_cli/template/tests/sniff/__init__.py` (empty).

Create `src/framework_cli/template/tests/sniff/conftest.py`:

```python
"""Sniff tests (CD Phase 2) — fast, stateless probes of critical paths against a real env.

Target via SNIFF_TARGET (default the local `lite` stack). Add a probe per critical path as
the project grows (auth, worker heartbeat, webhook ingress, ...) — see DEPLOY.md.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

DEFAULT_TARGET = "http://localhost:8000"


@pytest.fixture(scope="session")
def target() -> str:
    return os.environ.get("SNIFF_TARGET", DEFAULT_TARGET).rstrip("/")


@pytest.fixture
def client(target: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=target, timeout=10.0) as c:
        yield c
```

Create `src/framework_cli/template/tests/sniff/test_sniff.py`:

```python
"""Phase 2 — skeleton probes of the system's critical paths on a real deployment."""

import httpx


def test_health_is_serving(client: httpx.Client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"ok", "degraded"}


def test_core_read_path_returns_expected_shape(client: httpx.Client):
    # Core read path: the primary data surface returns the documented shape.
    resp = client.get("/items")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:  # a deployed env is seeded; an empty store is still a valid shape
        assert set(body[0]) == {"id", "name"}
```

- [ ] **Step 4: Add `task test:sniff`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after `test:smoke`:

```yaml
  test:sniff:
    desc: Phase-2 sniff probes against a target (SNIFF_TARGET=url; default localhost:8000).
    cmds:
      - uv run pytest tests/sniff -q
```

- [ ] **Step 5: Run the render assertion + sniff against the live `lite` stack (Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_sniff_suite -q` → PASS.

Bring up `lite` (as in Task 1 Step 6) and:
```bash
SNIFF_TARGET=http://localhost:8000 uv run pytest tests/sniff -q
```
Expected: 2 passed (`/items` returns the seeded `alpha`/`beta` shape).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/tests/sniff src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): Phase-2 sniff suite + task test:sniff"
```

---

## Task 3: k6 load test (Phase 4)

**Files:**
- Create: `src/framework_cli/template/tests/non_functional/__init__.py`
- Create: `src/framework_cli/template/tests/non_functional/load.js`
- Create: `src/framework_cli/template/scripts/load.sh`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_load_test(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    load_js = (dest / "tests" / "non_functional" / "load.js")
    assert load_js.is_file()
    js = load_js.read_text()
    assert "thresholds" in js
    assert "http_req_duration" in js  # k6 maps this to the p99 SLO

    script = (dest / "scripts" / "load.sh")
    assert script.is_file()
    assert "grafana/k6" in script.read_text()

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:load:" in taskfile
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_load_test -q`
Expected: FAIL — `tests/non_functional/load.js` does not exist.

- [ ] **Step 3: Create the k6 script + runner**

Create `src/framework_cli/template/tests/non_functional/__init__.py` (empty).

Create `src/framework_cli/template/tests/non_functional/load.js`:

```javascript
// k6 load test (CD Phase 4). Thresholds map 1:1 to the framework's SLO definitions — a
// threshold breach IS an SLO breach, expressed once. Run via scripts/load.sh (no local
// k6 install; uses the official Docker image). Target + thresholds come from env vars.
import http from 'k6/http';
import { check } from 'k6';

const TARGET = (__ENV.K6_TARGET || 'http://localhost:8000').replace(/\/$/, '');
const P99_MS = Number(__ENV.SLO_P99_MS || 200);
const ERROR_RATE_PCT = Number(__ENV.SLO_ERROR_RATE_PCT || 1);

export const options = {
  vus: Number(__ENV.K6_VUS || 10),
  duration: __ENV.K6_DURATION || '30s',
  thresholds: {
    // p99 latency SLO (ms) and 5xx error-rate SLO (fraction).
    http_req_duration: [`p(99)<${P99_MS}`],
    http_req_failed: [`rate<${ERROR_RATE_PCT / 100}`],
  },
};

export default function () {
  const res = http.get(`${TARGET}/items`);
  check(res, { 'status is 200': (r) => r.status === 200 });
}
```

Create `src/framework_cli/template/scripts/load.sh`:

```bash
#!/usr/bin/env bash
# CD Phase 4 — SLO load validation via Grafana k6 (official Docker image; no local install).
# k6 thresholds map 1:1 to the SLO definitions, passed in as env vars (defaults match the
# scaffold's settings). Usage: K6_TARGET=https://staging.example.com bash scripts/load.sh
set -euo pipefail

target="${K6_TARGET:-http://localhost:8000}"
p99_ms="${SLO_P99_MS:-200}"
error_rate_pct="${SLO_ERROR_RATE_PCT:-1}"

# --network host lets the container reach a localhost target (e.g. the local `lite` stack).
docker run --rm -i --network host \
  -e "K6_TARGET=${target}" \
  -e "SLO_P99_MS=${p99_ms}" \
  -e "SLO_ERROR_RATE_PCT=${error_rate_pct}" \
  -e "K6_VUS=${K6_VUS:-10}" \
  -e "K6_DURATION=${K6_DURATION:-30s}" \
  grafana/k6:latest run - < tests/non_functional/load.js
```

> **Why `-i ... run -`:** piping the script via stdin avoids a bind-mount (simpler, Windows-safe). `grafana/k6` exits non-zero if any threshold is breached, so the CD step fails on an SLO breach. `--network host` is for the *local* proxy run; against a remote staging URL it's harmless (the URL is absolute).

- [ ] **Step 4: Add `task test:load`**

In `src/framework_cli/template/Taskfile.yml.jinja`, add after `test:sniff`:

```yaml
  test:load:
    desc: Phase-4 k6 load test against a target (K6_TARGET=url). SLO thresholds gate it.
    cmds:
      - bash scripts/load.sh
```

- [ ] **Step 5: Run the render assertion + a short load run against `lite` (Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_load_test -q` → PASS.

Bring up `lite`, then a short run (override duration to keep it quick):
```bash
cd "/tmp/demo" && K6_DURATION=5s K6_VUS=5 K6_TARGET=http://localhost:8000 bash scripts/load.sh
```
Expected: k6 runs, reports `http_req_duration`/`http_req_failed` checks, exits 0 (thresholds hold against the idle local app). (First run pulls `grafana/k6` — allow time.)

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/tests/non_functional src/framework_cli/template/scripts/load.sh src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): Phase-4 k6 load test (SLO thresholds) + task test:load"
```

---

## Task 4: Target-aware E2E (Phase 3)

Make the 5a in-process e2e tier *also* runnable against a real deployment (`E2E_TARGET`), so the same suite serves CI (in-process) and staging validation (remote).

**Files:**
- Modify: `src/framework_cli/template/tests/conftest.py.jinja`
- Modify: `src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja`

- [ ] **Step 1: Rewrite the e2e tests to assert the seeded baseline (works both modes)**

The 5a happy test seeded a one-off row via the DB — impossible against a remote target. Replace `src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja` with:

```python
"""End-to-end (CD Phase 3). Two modes, one suite:

- In-process (CI): the full app over a real testcontainers Postgres, seeded with the baseline.
- Remote (E2E_TARGET set): the same assertions against a real deployed environment, which the
  deploy pipeline has migrated + seeded. No direct DB access in this mode.

Spec obligation: every consumer-facing surface needs at least one unhappy E2E path.
"""


def test_items_lists_seeded_baseline(api_client):
    # Both modes: the store is seeded with the baseline items (alpha, beta).
    resp = api_client.get("/items")
    assert resp.status_code == 200
    names = {row["name"] for row in resp.json()}
    assert {"alpha", "beta"} <= names


def test_unknown_resource_returns_problem_json(api_client):
    # Unhappy path: a request for a resource that doesn't exist is rendered as RFC 7807.
    resp = api_client.get("/items/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2: Run it to confirm it fails**

Re-render, `uv sync`. Run (Docker): `cd "/tmp/demo" && uv run pytest tests/e2e -q`
Expected: FAIL — `fixture 'api_client' not found` (the fixture is renamed/!= `e2e_client`).

- [ ] **Step 3: Make the fixture target-aware in `conftest.py.jinja`**

In `src/framework_cli/template/tests/conftest.py.jinja`, **replace** the existing `e2e_client` fixture (the one that builds the app, overrides `get_session`, and TRUNCATEs on teardown) with the `api_client` fixture below. Keep the `TYPE_CHECKING` import of `TestClient` at the top (already present from 5a); add `import os` is already present; ensure `httpx` is importable (it's a dev dep). The new fixture:

```python
@pytest.fixture
def api_client(request: pytest.FixtureRequest) -> Iterator["TestClient | httpx.Client"]:
    """E2E client. Remote when E2E_TARGET is set (against a real deployment, no DB access);
    otherwise the full app in-process over the testcontainers Postgres, seeded with the
    baseline. The in-process branch requests the `engine` fixture lazily so remote runs need
    no Docker.
    """
    import os

    target = os.environ.get("E2E_TARGET")
    if target:
        import httpx

        with httpx.Client(base_url=target.rstrip("/"), timeout=15.0) as client:
            yield client
        return

    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from {{ package_name }}.db.engine import build_session_factory, get_session
    from {{ package_name }}.db.seed import seed
    from {{ package_name }}.main import create_app

    engine = request.getfixturevalue("engine")
    factory = build_session_factory(engine)
    with factory() as session:
        seed(session)  # load the baseline (alpha, beta) so the happy path holds in-process
        session.commit()

    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE items RESTART IDENTITY CASCADE"))
        conn.commit()
```

Add `import httpx` to the top of `conftest.py.jinja` (with the other stdlib/third-party imports — after `import pytest`) so the type annotation and the runtime import resolve, and add it under the `TYPE_CHECKING` block if needed for the annotation. Concretely, the top of the file becomes:

```python
import os
import subprocess
from collections.abc import Iterator
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import build_engine

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
```

> **Why `seed(session)`:** `db/seed.py` exposes `seed(session)` which loads `seeds/items.json` (the `alpha`/`beta` baseline) idempotently — the same path the container entrypoint runs on first `task dev`. Using it in-process makes the happy assertion (`{"alpha","beta"} <= names`) hold without a bespoke row, and mirrors what a deployed (remote) environment looks like. (Verify the `seed` signature when you render — it's `def seed(session: Session) -> None` per `db/seed.py`; if it differs, adapt the call and report it.)

- [ ] **Step 4: Confirm in-process e2e passes + the 85% gate still holds (Docker)**

Re-render, `uv sync`. Then:
```bash
cd "/tmp/demo" && uv run pytest tests/e2e -q          # in-process, 2 passed
bash scripts/coverage.sh 85 unit functional e2e        # combined gate still >=85%
```
Expected: e2e 2 passed; combined gate exits 0.

Then confirm the **remote** mode against the live `lite` stack:
```bash
# lite stack up (seeded), then:
E2E_TARGET=http://localhost:8000 uv run pytest tests/e2e -q
```
Expected: 2 passed (no Docker container started by the fixture — it used the remote target).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/tests/conftest.py.jinja src/framework_cli/template/tests/e2e/test_items_e2e.py.jinja
git commit -m "feat(template): target-aware e2e (in-process or E2E_TARGET) for staging validation"
```

---

## Task 5: Production Compose topologies

**Files:**
- Create: `src/framework_cli/template/infra/compose/staging.yml`
- Create: `src/framework_cli/template/infra/compose/prod.yml`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_staging_prod_compose(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    for env in ("staging", "prod"):
        path = dest / "infra" / "compose" / f"{env}.yml"
        assert path.is_file(), f"{env}.yml missing"
        compose = yaml.safe_load(path.read_text())
        app = compose["services"]["app"]
        assert "build" not in app, f"{env} must run the pushed image, not build"
        assert "${APP_IMAGE" in app["image"]
        assert app["environment"]["APP_ENVIRONMENT"] == env
        assert app["restart"] == "unless-stopped"
        assert compose["services"]["postgres"]["restart"] == "unless-stopped"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_staging_prod_compose -q`
Expected: FAIL — `staging.yml` does not exist.

- [ ] **Step 3: Create the staging topology**

Create `src/framework_cli/template/infra/compose/staging.yml` (plain `.yml` — no Copier vars; `${VAR}` is Compose interpolation, copied verbatim):

```yaml
# Staging topology — production-equivalent. The configured deploy strategy (infra/deploy/)
# runs the SAME registry image (APP_IMAGE) against this definition on the staging target.
# No bind mounts, no hot reload, no dev tooling. Secrets come from the target's environment.
services:
  app:
    image: ${APP_IMAGE:?set APP_IMAGE to the pushed registry tag}
    restart: unless-stopped
    environment:
      TZ: UTC
      APP_ENVIRONMENT: staging
      APP_DATABASE_URL: "postgresql+psycopg://app:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}@postgres:5432/app"
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in the target environment}
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    volumes:
      - "pgdata:/var/lib/postgresql/data"

volumes:
  pgdata: {}
```

- [ ] **Step 4: Create the prod topology**

Create `src/framework_cli/template/infra/compose/prod.yml` (identical shape; `APP_ENVIRONMENT: prod`):

```yaml
# Production topology — the SAME registry image promoted from staging (no rebuild), run
# against this definition by the configured deploy strategy. Secrets from the target env.
services:
  app:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    environment:
      TZ: UTC
      APP_ENVIRONMENT: prod
      APP_DATABASE_URL: "postgresql+psycopg://app:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}@postgres:5432/app"
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in the target environment}
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    volumes:
      - "pgdata:/var/lib/postgresql/data"

volumes:
  pgdata: {}
```

- [ ] **Step 5: Run the render assertion + validate compose syntax (Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_staging_prod_compose -q` → PASS.

Validate the Compose files parse (config-only, no deploy):
```bash
cd "/tmp/demo" && APP_IMAGE=demo:test POSTGRES_PASSWORD=x docker compose -f infra/compose/staging.yml config -q && echo "staging OK"
APP_IMAGE=demo:test POSTGRES_PASSWORD=x docker compose -f infra/compose/prod.yml config -q && echo "prod OK"
```
Expected: both print OK (valid Compose).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/compose/staging.yml src/framework_cli/template/infra/compose/prod.yml tests/test_copier_runner.py
git commit -m "feat(template): production-equivalent staging/prod Compose topologies"
```

---

## Task 6: Deploy-strategy skeleton (opinionated; migration-aware rollback)

This is the heart of the "offload, don't delegate" principle: the framework pre-decides every target-independent concern; the builder fills only the `__target_*` hooks + config.

**Files:**
- Create: `src/framework_cli/template/infra/deploy/strategy.sh`
- Create: `src/framework_cli/template/infra/deploy/notify.sh`
- Create: `src/framework_cli/template/infra/deploy/README.md`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_deploy_strategy_seam(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    strategy = (dest / "infra" / "deploy" / "strategy.sh")
    assert strategy.is_file()
    text = strategy.read_text()
    for op in ("deploy", "endpoints", "await-healthy", "rollback", "releases", "teardown"):
        assert op in text, f"strategy.sh missing operation {op}"
    # opinionated skeleton: config validated; target hooks fail loudly; rollback reverses migrations
    assert "require_var" in text
    assert "_todo" in text
    assert "downgrade" in text and "__target_migrate" in text  # migration-aware rollback

    assert (dest / "infra" / "deploy" / "notify.sh").is_file()
    readme = (dest / "infra" / "deploy" / "README.md").read_text()
    assert "deploy strategy" in readme.lower()
    assert "rollback" in readme
    assert "expand/contract" in readme  # prescribed migration discipline
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_strategy_seam -q`
Expected: FAIL — `infra/deploy/strategy.sh` does not exist.

- [ ] **Step 3: Create the strategy dispatcher**

Create `src/framework_cli/template/infra/deploy/strategy.sh` (plain `.sh`; must be shellcheck-clean). The framework pre-writes config validation, the health-gate, release/revision tracking, and **migration-aware rollback**; only the `__target_*` hooks are yours:

```bash
#!/usr/bin/env bash
# Deploy strategy (framework spec §14) — OPINIONATED SKELETON.
#
# The framework decides the hard parts (release versioning, MIGRATION-AWARE rollback,
# health-gating, runtime secrets) — implemented below. You implement ONLY the __target_*
# hooks for YOUR target (compose-over-SSH, Fly.io, Render, k8s, ...) and set the config env
# vars. See infra/deploy/README.md for the contract, the required env vars, the migration
# discipline, and antipattern guidance. CD workflows call:
#   bash infra/deploy/strategy.sh <operation> [args...]
set -euo pipefail

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "::error::deploy config '${name}' is not set — see infra/deploy/README.md." >&2
    exit 1
  fi
}

_todo() {
  echo "::error::deploy hook '$1' is not implemented for your target." >&2
  echo "Implement $1() in infra/deploy/strategy.sh — it must: $2 (see infra/deploy/README.md)." >&2
  exit 1
}

# === TARGET HOOKS — the only code you write ==========================================
# Pull APP_IMAGE and run it from infra/compose/${DEPLOY_ENV}.yml on the target. The image
# self-migrates UP on start (its entrypoint runs `alembic upgrade head`); do NOT route traffic
# until healthy. (compose-over-SSH e.g.: scp the compose file, then over ssh
# `APP_IMAGE=$APP_IMAGE POSTGRES_PASSWORD=$POSTGRES_PASSWORD docker compose -f <env>.yml up -d`.)
__target_place_image() { _todo __target_place_image "pull \$APP_IMAGE and start it from infra/compose/\$DEPLOY_ENV.yml without routing traffic until healthy"; }

# Reverse/apply migrations against the target's stores. \$* is the migration command; the
# relational store runs `alembic \$*` using THIS checkout's migrations (so a downgrade has the
# new migration's down-path). When other DB paradigms are added (Plan 8), reverse each store's
# migrations to the recorded state here too — the SAME reversibility discipline applies to all.
__target_migrate() { _todo __target_migrate "run 'alembic \$*' against the target relational DB (and reverse other paradigms' migrations when present)"; }

# Append "\$1<TAB>\$2" (image, alembic revision) to durable per-DEPLOY_ENV release state ON THE
# TARGET, so a later workflow run can roll back.
__target_record_release() { _todo __target_record_release "append \"\$1<TAB>\$2\" to durable release state for \$DEPLOY_ENV on the target"; }

# Print recorded "image<TAB>revision" lines for DEPLOY_ENV, oldest first.
__target_release_history() { _todo __target_release_history "print recorded 'image<TAB>revision' lines (oldest first) for \$DEPLOY_ENV"; }

# Remove a failed/rolled-back release on the target.
__target_teardown() { _todo __target_teardown "remove a failed or rolled-back release on the target"; }

# === PRESCRIBED LOGIC — the framework owns this; configure, don't weaken it ==========
repo_head_revision() { uv run alembic heads 2>/dev/null | awk 'NR==1 {print $1}'; }

endpoints() { require_var DEPLOY_BASE_URL; printf '%s\n' "${DEPLOY_BASE_URL}"; }

await_healthy() {
  require_var DEPLOY_BASE_URL
  local timeout="${1:-120}" deadline body
  deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if body="$(curl -fsS "${DEPLOY_BASE_URL%/}/health" 2>/dev/null)"; then
      # Health-gate: serving AND no breached SLO (the Phase-1 smoke rule).
      case "${body}" in
        *'"breached"'*) ;;     # an SLO is breached — keep waiting
        *) return 0 ;;
      esac
    fi
    sleep 3
  done
  echo "::error::release at ${DEPLOY_BASE_URL} did not become healthy within ${timeout}s." >&2
  exit 1
}

deploy() {
  require_var APP_IMAGE
  require_var DEPLOY_ENV
  # Record BEFORE placing so a rollback target is tracked even if this deploy fails midway.
  __target_record_release "${APP_IMAGE}" "$(repo_head_revision)"
  __target_place_image   # the image entrypoint runs `alembic upgrade head` on start
}

rollback() {
  require_var DEPLOY_ENV
  # Roll back to the release before the current head: REVERSE migrations to ITS revision, THEN
  # redeploy ITS image. The downgrade is essential — the image only ever upgrades, so without it
  # the old code would run against the new schema. (Irreversible migrations cannot be restored;
  # the framework blocks them — see the migration guard + infra/deploy/README.md.)
  local prev image rev
  prev="$(__target_release_history | tail -n 2 | head -n 1)"
  if [ -z "${prev}" ]; then
    echo "::error::no previous release to roll back to (rollback target missing)." >&2
    exit 1
  fi
  image="$(printf '%s' "${prev}" | cut -f1)"
  rev="$(printf '%s' "${prev}" | cut -f2)"
  __target_migrate "downgrade ${rev}"
  APP_IMAGE="${image}" __target_place_image
}

operation="${1:-}"
case "${operation}" in
  deploy)          deploy ;;
  await-healthy)   await_healthy "${2:-120}" ;;
  endpoints)       endpoints ;;
  rollback)        rollback ;;
  releases)        __target_release_history ;;
  current-release) __target_release_history | tail -n 1 | cut -f1 ;;
  teardown)        __target_teardown ;;
  *)
    echo "::error::unknown deploy operation '${operation}'." >&2
    echo "Valid: deploy await-healthy endpoints rollback releases current-release teardown." >&2
    exit 2
    ;;
esac
```

> **Shellcheck:** the `__target_*` bodies use `\$` inside double-quoted messages (literal `$`, not expansion) — keep them as written. `${!name:-}` is intentional indirect expansion. Verify clean with `pre-commit run shellcheck` after rendering (Step 6).

- [ ] **Step 4: Create the notification seam**

Create `src/framework_cli/template/infra/deploy/notify.sh` (plain `.sh`; shellcheck-clean):

```bash
#!/usr/bin/env bash
# Deploy notification seam (spec §8 alert routing). The CD workflows call:
#   bash infra/deploy/notify.sh "<message>"
# By default this logs to the workflow output. Wire your channel (Slack webhook / email /
# PagerDuty) here — reuse the same destination Alertmanager uses
# (infra/observability/alertmanager/alertmanager.yml) so alerts and deploy notices share one
# place. Keep it non-fatal: a notification failure must not fail the deploy.
set -euo pipefail

message="${1:-deploy notification}"
echo "[deploy notify] ${message}"

# Example (uncomment + set SLACK_WEBHOOK_URL as a secret):
# if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
#   curl -sf -X POST -H 'Content-Type: application/json' \
#     --data "{\"text\": \"${message}\"}" "${SLACK_WEBHOOK_URL}" || true
# fi
```

- [ ] **Step 5: Create the contract README (the builder-enablement doc)**

Create `src/framework_cli/template/infra/deploy/README.md`:

```markdown
# Deploy strategy — what the framework decided, and the little you configure

Deployment is a **contract**. The framework owns the orchestration (build → push → deploy →
smoke → sniff → E2E → load) AND the strategic decisions: release versioning, **migration-aware
rollback**, health-gating, and runtime secrets. `strategy.sh` already implements those. You
implement only the `__target_*` hooks for your target and set a few config env vars — you
configure, you do not architect.

## Pick a target

| Target | `__target_place_image` implements |
|---|---|
| Compose-over-SSH (VPS) | scp `infra/compose/<env>.yml` to the host, then over ssh `docker compose -f <env>.yml up -d` (pulls `APP_IMAGE`) |
| Fly.io / Render / Railway | the platform's deploy CLI pointed at `APP_IMAGE` |
| Kubernetes | `kubectl set image` / a Helm release using `APP_IMAGE` |

A turnkey default (compose-over-SSH + Traefik/ACME blue-green) ships as a follow-up; until
then, implement the hooks below for your target.

## What you implement (the only gaps in `strategy.sh`)

| Hook | Must do |
|---|---|
| `__target_place_image` | Pull `$APP_IMAGE` and run it from `infra/compose/$DEPLOY_ENV.yml`; do not route traffic until healthy. |
| `__target_migrate` | Run `alembic <args>` against the target's relational DB using THIS checkout's migrations (rollback's downgrade needs the new migration's down-path). When you add other DB paradigms (document/graph/…), reverse their migrations here too. |
| `__target_record_release` / `__target_release_history` | Persist + read the `(image, revision)` history per env on the target (durable across runs). |
| `__target_teardown` | Remove a failed/rolled-back release. |

## What the framework already did (do not weaken)

- **Release versioning** — each deploy records `(image, alembic-revision)`; `current-release`/`releases` read it.
- **Migration-aware rollback** — `rollback` reverses migrations to the previous release's revision THEN redeploys its image (the image only ever upgrades, so the explicit downgrade is required).
- **Health-gate** — `await-healthy` polls `/health` and refuses any `breached` SLO (the Phase-1 smoke rule).
- **Guarantees:** versioned/addressable releases (a rollback target always exists), runtime secrets (never baked into images), the same image promoted staging → prod (no rebuild). No-downtime cutover is the target's job (blue-green via the bundled Traefik, or the platform's native rolling deploy) — see the turnkey follow-up.

## Config you set (GitHub Environment + the target)

| Var | Where | Purpose |
|---|---|---|
| `DEPLOY_ENV` | workflow (`staging`/`prod`) | selects `infra/compose/<env>.yml` |
| `DEPLOY_BASE_URL` | Environment variable | the deployment's base URL (endpoints + health-gate) |
| `APP_IMAGE` | set by the workflow | the pushed registry tag |
| `POSTGRES_PASSWORD` | **target env + GitHub Environment secret** | DB credential, injected at runtime |
| every var in `.env.example` | **the target's environment** | the app reads config from the target's env — NEVER baked into the image |

Set application config + secrets **in the target's environment** (or the platform's secret
store) and as GitHub Environment secrets — the image carries none of them.

## Migrations: reversible by discipline, across every paradigm

Rollback can only restore a previous release if its migrations can be reversed, so:

- **Write expand/contract migrations.** Add columns/tables (expand) and ship code that works
  with and without them; only remove the old shape (contract) in a later release once nothing
  uses it. A rollback's downgrade is then non-destructive.
- **Irreversible migrations are blocked, not just discouraged.** The migration guard
  (`scripts/check_migrations.py`, run in pre-commit + CI) fails any migration whose `downgrade`
  is empty/`pass`/`raise` — you cannot ship a one-way migration by accident. **Never destroy
  data that cannot be reconstructed**; if a destructive change is truly intended, make it a
  separate, explicitly-reviewed migration and accept that releases across it cannot be rolled
  back through it.
- **This applies to all database paradigms, not just relational.** PostgreSQL uses Alembic
  here; document/key-value/graph/time-series/vector stores (Plan 8) carry their own reversible
  migration tooling and the same discipline + guard. Reverse each active store in
  `__target_migrate`.

## Antipatterns this seam prevents (don't reintroduce them)

- No rollback target → `rollback` errors if there's no previous release.
- Secrets baked into images → config/secrets come from the target env at runtime.
- Skipping staging → prod only deploys an image that passed staging's four phases.
- Mutating prod during validation → prod runs smoke + **read-only** sniff; never E2E/load writes.
- Big-bang / irreversible migrations → expand/contract + the migration guard above.

## Validate a real deploy (no framework help needed)

1. Implement the `__target_*` hooks; set the config above.
2. Merge to `main` → `deploy-staging.yml` builds+pushes, calls your `deploy`, runs the four
   phases against your `endpoints`, and auto-rolls-back (reversing migrations) on any failure.
3. Locally point the tiers at any environment: `SMOKE_TARGET=… task test:smoke`,
   `SNIFF_TARGET=… task test:sniff`, `E2E_TARGET=… uv run pytest tests/e2e`, `K6_TARGET=… task test:load`.

## Notifications

`notify.sh` logs by default. Wire your channel there (reuse the Alertmanager destination).
```

- [ ] **Step 6: Run the render assertion + shellcheck (Docker not needed)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_strategy_seam -q` → PASS.

Confirm the scripts are shellcheck-clean (the Plan 5a hook will gate them):
```bash
cd "/tmp/demo" && git init -q && git add -A && uv sync -q
uv run pre-commit run shellcheck --all-files
```
Expected: shellcheck Passed (over `strategy.sh`, `notify.sh`, `load.sh`, and the pre-existing scripts).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/deploy tests/test_copier_runner.py
git commit -m "feat(template): opinionated deploy-strategy skeleton (migration-aware rollback) + notify + prescriptive README"
```

---

## Task 7: `deploy-staging.yml`

**Files:**
- Create: `src/framework_cli/template/.github/workflows/deploy-staging.yml`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_deploy_staging_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "deploy-staging.yml"
    assert wf.is_file()
    text = wf.read_text()
    # GitHub expressions are preserved verbatim (plain .yml, no Jinja) — NOT escaped/emptied.
    assert "${{ github.repository }}" in text
    assert "ghcr.io" in text and "docker push" in text

    ci = yaml.safe_load(text)
    jobs = ci["jobs"]
    assert "build-push" in jobs and "deploy-staging" in jobs
    deploy_steps = " ".join(str(s.get("run", "")) for s in jobs["deploy-staging"]["steps"])
    for op in ("strategy.sh deploy", "strategy.sh rollback", "strategy.sh endpoints"):
        assert op in deploy_steps, f"deploy-staging missing {op}"
    assert "tests/smoke" in deploy_steps and "tests/sniff" in deploy_steps
    assert "tests/e2e" in deploy_steps and "scripts/load.sh" in deploy_steps
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_staging_workflow -q`
Expected: FAIL — `deploy-staging.yml` does not exist.

- [ ] **Step 3: Create the workflow**

Create `src/framework_cli/template/.github/workflows/deploy-staging.yml` (**plain `.yml`** — no Copier vars; `${{ github.* }}` is preserved verbatim, no `{% raw %}`):

```yaml
# CD — staging (spec §14). On merge to main: build+push the image, then the configured deploy
# strategy (infra/deploy/strategy.sh) places it and the four validation phases run against it.
# Any failure auto-rolls-back and blocks the prod gate. The strategy is YOURS to implement —
# see infra/deploy/README.md; until then the `deploy` step fails loudly (by design).
name: Deploy — staging

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  build-push:
    runs-on: ubuntu-latest
    outputs:
      image: ${{ steps.build.outputs.image }}
    steps:
      - uses: actions/checkout@v4
      - name: log in to GHCR
        run: echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u "${{ github.actor }}" --password-stdin
      - name: build + push image
        id: build
        run: |
          repo="$(echo "${{ github.repository }}" | tr '[:upper:]' '[:lower:]')"
          image="ghcr.io/${repo}:${{ github.sha }}"
          docker build -f infra/docker/Dockerfile -t "$image" .
          docker push "$image"
          echo "image=$image" >> "$GITHUB_OUTPUT"

  deploy-staging:
    needs: build-push
    runs-on: ubuntu-latest
    environment: staging
    env:
      APP_IMAGE: ${{ needs.build-push.outputs.image }}
      DEPLOY_ENV: staging
      DEPLOY_BASE_URL: ${{ vars.STAGING_BASE_URL }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: deploy (your configured strategy)
        run: bash infra/deploy/strategy.sh deploy
      - name: await healthy
        run: bash infra/deploy/strategy.sh await-healthy 120
      - name: resolve endpoint
        id: ep
        run: echo "url=$(bash infra/deploy/strategy.sh endpoints | head -n1)" >> "$GITHUB_OUTPUT"
      - name: Phase 1 — smoke
        run: SMOKE_TARGET="${{ steps.ep.outputs.url }}" uv run pytest tests/smoke -q
      - name: Phase 2 — sniff
        run: SNIFF_TARGET="${{ steps.ep.outputs.url }}" uv run pytest tests/sniff -q
      - name: Phase 3 — E2E against staging
        run: E2E_TARGET="${{ steps.ep.outputs.url }}" uv run pytest tests/e2e -q
      - name: Phase 4 — k6 load (SLO thresholds)
        run: K6_TARGET="${{ steps.ep.outputs.url }}" bash scripts/load.sh
      - name: rollback on any failure
        if: failure()
        run: bash infra/deploy/strategy.sh rollback
      - name: notify
        if: always()
        run: bash infra/deploy/notify.sh "staging deploy ${{ job.status }} (${{ github.sha }})"
```

> **Notes.** Plain `.yml` → `${{ ... }}` preserved verbatim (no Jinja, no `{% raw %}`). The repo name is lowercased for GHCR. `environment: staging` lets the builder attach environment secrets/protection. The `deploy` step fails loudly until `strategy.sh` is implemented — that is the intended, documented state.

- [ ] **Step 4: Render assertion + actionlint (no Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_staging_workflow -q` → PASS.

Then actionlint over the rendered workflow (the load-bearing gate for workflow YAML):
```bash
cd "/tmp/demo" && git init -q && git add -A && uv sync -q
uv run pre-commit run actionlint --all-files
```
Expected: actionlint Passed (over `ci.yml`, `deploy-staging.yml`). If actionlint flags inline-shell (shellcheck) issues in a `run:` block, fix the quoting until clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.github/workflows/deploy-staging.yml tests/test_copier_runner.py
git commit -m "feat(template): deploy-staging.yml — build+push, deploy seam, 4-phase validation, rollback"
```

---

## Task 8: `deploy-prod.yml`

**Files:**
- Create: `src/framework_cli/template/.github/workflows/deploy-prod.yml`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_deploy_prod_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    wf = dest / ".github" / "workflows" / "deploy-prod.yml"
    assert wf.is_file()
    ci = yaml.safe_load(wf.read_text())

    # manual approval gate via a protected GitHub Environment, and a tag trigger
    assert ci["jobs"]["deploy-prod"]["environment"] == "production"
    triggers = ci[True] if True in ci else ci["on"]  # PyYAML parses `on:` as True
    assert "workflow_dispatch" in triggers

    steps = " ".join(str(s.get("run", "")) for s in ci["jobs"]["deploy-prod"]["steps"])
    assert "strategy.sh deploy" in steps and "strategy.sh rollback" in steps
    # prod sniff is read-only; no E2E/load writes against prod
    assert "tests/smoke" in steps and "tests/sniff" in steps
    assert "tests/e2e" not in steps
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_prod_workflow -q`
Expected: FAIL — `deploy-prod.yml` does not exist.

- [ ] **Step 3: Create the workflow**

Create `src/framework_cli/template/.github/workflows/deploy-prod.yml` (plain `.yml`):

```yaml
# CD — production (spec §14). Manual approval (the `production` Environment gate) or a release
# tag. Reuses the SAME image promoted from staging (no rebuild). Post-deploy: smoke + sniff
# (read-only — no writes against prod). Any failure auto-rolls-back. Implement the deploy
# strategy in infra/deploy/strategy.sh — see infra/deploy/README.md.
name: Deploy — production

on:
  workflow_dispatch:
    inputs:
      image:
        description: "Fully-qualified image to promote (e.g. ghcr.io/owner/repo:<sha>). Defaults to the latest staging build for this SHA."
        required: false
        default: ""
  push:
    tags: ["v*"]

permissions:
  contents: read
  packages: read

jobs:
  deploy-prod:
    runs-on: ubuntu-latest
    environment: production
    env:
      APP_IMAGE: ${{ github.event.inputs.image }}
      DEPLOY_ENV: prod
      DEPLOY_BASE_URL: ${{ vars.PROD_BASE_URL }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: resolve image to promote
        run: |
          image="${APP_IMAGE}"
          if [ -z "$image" ]; then
            repo="$(echo "${{ github.repository }}" | tr '[:upper:]' '[:lower:]')"
            image="ghcr.io/${repo}:${{ github.sha }}"
          fi
          echo "APP_IMAGE=$image" >> "$GITHUB_ENV"
      - name: deploy (your configured strategy)
        run: bash infra/deploy/strategy.sh deploy
      - name: await healthy
        run: bash infra/deploy/strategy.sh await-healthy 120
      - name: resolve endpoint
        id: ep
        run: echo "url=$(bash infra/deploy/strategy.sh endpoints | head -n1)" >> "$GITHUB_OUTPUT"
      - name: smoke (prod)
        run: SMOKE_TARGET="${{ steps.ep.outputs.url }}" uv run pytest tests/smoke -q
      - name: sniff (prod, read-only)
        run: SNIFF_TARGET="${{ steps.ep.outputs.url }}" uv run pytest tests/sniff -q
      - name: rollback on any failure
        if: failure()
        run: bash infra/deploy/strategy.sh rollback
      - name: notify
        if: always()
        run: bash infra/deploy/notify.sh "prod deploy ${{ job.status }} (${{ github.sha }})"
```

> **Notes.** `environment: production` is where the builder configures the **required-reviewers** approval gate (GitHub Settings → Environments) — that satisfies §14's "manual approval gate." Prod runs smoke + **read-only** sniff only (no E2E/load writes against prod, per §14). The image is promoted (reused), not rebuilt.

- [ ] **Step 4: Render assertion + actionlint (no Docker)**

Run: `uv run pytest tests/test_copier_runner.py::test_render_deploy_prod_workflow -q` → PASS.

```bash
cd "/tmp/demo" && git init -q && git add -A && uv sync -q
uv run pre-commit run actionlint --all-files
```
Expected: actionlint Passed over all three workflows.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.github/workflows/deploy-prod.yml tests/test_copier_runner.py
git commit -m "feat(template): deploy-prod.yml — approval gate, image promotion, smoke+sniff, rollback"
```

---

## Task 9: Migration reversibility guard (block irreversible migrations)

Rollback (Task 6) reverses migrations to the previous release — so an irreversible migration makes a release un-rollback-able and risks unreconstructable data loss. The framework **prevents** them as a matter of course, not by trusting the builder to remember. This guard fails any migration whose `downgrade()` is missing/empty/`pass`/`raise`.

**Files:**
- Create: `src/framework_cli/template/scripts/check_migrations.py`
- Modify: `src/framework_cli/template/.pre-commit-config.yaml`
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`

- [ ] **Step 1: Write the failing render assertion**

In `tests/test_copier_runner.py`, add:

```python
def test_render_migration_guard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    guard = (dest / "scripts" / "check_migrations.py")
    assert guard.is_file()
    assert "downgrade" in guard.read_text()

    precommit = (dest / ".pre-commit-config.yaml").read_text()
    assert "migrations-reversible" in precommit

    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "check_migrations.py" in ci
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_migration_guard -q`
Expected: FAIL — `scripts/check_migrations.py` does not exist.

- [ ] **Step 3: Create the guard**

Create `src/framework_cli/template/scripts/check_migrations.py` (plain `.py` — no Copier vars):

```python
"""Block irreversible migrations: every migration's downgrade() must really reverse it.

Rollback (infra/deploy/strategy.sh) reverses migrations to the previous release; a migration
with no real downgrade makes that release un-rollback-able and risks unreconstructable data
loss. This guard fails any migration whose downgrade() is missing / empty / just `pass` /
raises. Run in pre-commit and CI. The same discipline applies to every database paradigm
added later (Plan 8) — each carries its own reversible-migration tooling and a guard like this.

This is a structural guard (is there a real reversal?), not a semantic one (does it lose
data?) — semantic data-loss is caught by the data-integrity review agent + the expand/contract
discipline (see infra/deploy/README.md).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

VERSIONS = Path("migrations/versions")


def _is_trivial(func: ast.FunctionDef) -> bool:
    # Drop a leading docstring; what remains is the real body.
    body = [
        node
        for node in func.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    if not body:
        return True
    if all(isinstance(node, ast.Pass) for node in body):
        return True
    return len(body) == 1 and isinstance(body[0], ast.Raise)


def _problem(path: Path) -> str | None:
    tree = ast.parse(path.read_text(), filename=str(path))
    downgrade = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        ),
        None,
    )
    if downgrade is None:
        return f"{path}: no downgrade() function"
    if _is_trivial(downgrade):
        return f"{path}: downgrade() is empty / pass / raise — write a real reversal (expand/contract)"
    return None


def main() -> int:
    if not VERSIONS.is_dir():
        return 0
    failures = [msg for path in sorted(VERSIONS.glob("*.py")) if (msg := _problem(path))]
    for msg in failures:
        print(f"::error::{msg}", file=sys.stderr)
    if failures:
        print(
            f"\n{len(failures)} irreversible migration(s). Every migration must have a real "
            "downgrade(); never destroy unreconstructable data. See infra/deploy/README.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Wire it into pre-commit**

In `src/framework_cli/template/.pre-commit-config.yaml`, add to the `- repo: local` `hooks:` list (after the `mypy` hook, before `coverage-threshold`):

```yaml
      - id: migrations-reversible
        name: migrations are reversible (no irreversible downgrade)
        entry: uv run python scripts/check_migrations.py
        language: system
        pass_filenames: false
        files: ^migrations/versions/.*\.py$
```

- [ ] **Step 5: Wire it into the CI lint job**

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, in the `lint` job's steps, add after the `mypy` step (before the `actionlint + shellcheck` step):

```yaml
      - run: uv run python scripts/check_migrations.py
```

- [ ] **Step 6: Verify (no Docker) — the scaffold passes; an irreversible one fails**

Re-render. Confirm the scaffold's own migration is reversible:
```bash
cd "/tmp/demo" && uv sync -q && uv run python scripts/check_migrations.py && echo "guard: clean"
```
Expected: exit 0 ("guard: clean"). The scaffold's `migrations/versions/0001_initial.py` has a real `downgrade()` (drops the `items` table). **If the guard fails on it, the 0001 downgrade is trivial — fix `0001_initial.py` to actually drop what it creates, then re-render.**

Confirm it CATCHES an irreversible migration (negative check):
```bash
cd "/tmp/demo" && python - <<'PY'
import pathlib
p = pathlib.Path("migrations/versions/9999_bad.py")
p.write_text("def upgrade():\n    pass\n\ndef downgrade():\n    pass\n")
PY
uv run python scripts/check_migrations.py; echo "exit=$?"   # expect ::error:: + exit=1
rm migrations/versions/9999_bad.py
```
Then the render assertion + the no-Docker cleanliness gate (the new pre-commit hook runs against the scaffold's migrations):
```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
uv run pytest tests/test_copier_runner.py::test_render_migration_guard -q   # PASS
uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean" -q   # PASS (guard clean on 0001)
```

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/scripts/check_migrations.py src/framework_cli/template/.pre-commit-config.yaml src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): migration reversibility guard — block irreversible migrations (pre-commit + CI)"
```

---

## Task 10: Docs, acceptance coverage, full verification + roadmap/state

**Files:**
- Create: `src/framework_cli/template/DEPLOY.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Modify: `src/framework_cli/template/CLAUDE.md.jinja`
- Modify: `tests/test_copier_runner.py`
- Modify: `tests/acceptance/test_rendered_project.py`
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create the builder-facing `DEPLOY.md`**

Create `src/framework_cli/template/DEPLOY.md.jinja`:

```markdown
# Deploying {{ project_name }}

The framework ships the full deploy **orchestration**; you implement the deploy **strategy**
for your chosen target. Nothing else is required from the framework.

## The flow (spec §14)

`merge to main` → `deploy-staging.yml`:
1. Build + push the image to GHCR (`ghcr.io/<owner>/<repo>:<sha>`).
2. Your strategy (`infra/deploy/strategy.sh`) deploys it and exposes endpoints.
3. Four validation phases run against the deployment, each gating the next:
   - **Phase 1 — smoke** (`tests/smoke/`): liveness/readiness + no breached SLO.
   - **Phase 2 — sniff** (`tests/sniff/`): critical-path probes.
   - **Phase 3 — E2E** (`tests/e2e/` with `E2E_TARGET`): the full suite against staging.
   - **Phase 4 — load** (`scripts/load.sh` + `tests/non_functional/load.js`): k6 at the SLO thresholds.
4. Any failure → automatic `rollback` + notify; success opens the prod gate.

`deploy-prod.yml` (manual approval via the `production` Environment, or a `v*` tag) promotes
the **same** image and runs smoke + read-only sniff.

## What you implement (configuration, not architecture)

The framework already decided release versioning, migration-aware rollback, and health-gating
(`infra/deploy/strategy.sh`). You implement only the `__target_*` hooks for your target and set
config — **see `infra/deploy/README.md`** for the hook list, the required env vars, and the
migration discipline. In short:

- Set `DEPLOY_BASE_URL` (Environment variable) and `POSTGRES_PASSWORD` + every var in
  `.env.example` **in the target's environment** (and as GitHub Environment secrets) — config
  and secrets are injected at runtime, never baked into the image.
- A turnkey **compose-over-SSH + Traefik/ACME** reference strategy (no-downtime, blue-green)
  ships as a follow-up; until then, implement `__target_place_image` for your target.

## Migrations are reversible (enforced)

Rollback reverses migrations to the previous release, so every migration must be reversible —
the framework **blocks** irreversible ones (`scripts/check_migrations.py`, in pre-commit + CI):
a `downgrade()` may not be empty/`pass`/`raise`. Write **expand/contract** migrations; never
destroy unreconstructable data. The same discipline applies to every database paradigm you add
(Plan 8), not just PostgreSQL.

## Run the validation tiers locally against any environment

```bash
SMOKE_TARGET=https://staging.example.com task test:smoke
SNIFF_TARGET=https://staging.example.com task test:sniff
E2E_TARGET=https://staging.example.com  uv run pytest tests/e2e -q
K6_TARGET=https://staging.example.com   task test:load
```

> Phase-4 results are gated on the SLO thresholds and emitted to the workflow log; wiring k6
> Prometheus remote-write into the running Grafana stack is a later enhancement.
```

- [ ] **Step 2: Add a Deploy subsection to README + CLAUDE.md**

In `src/framework_cli/template/README.md.jinja`, add after the `## CI/CD` section:

```markdown
## Deploy

`deploy-staging.yml` (on merge to `main`) builds+pushes the image, deploys via your strategy,
and runs four validation phases (smoke → sniff → E2E → k6 load) with automatic rollback;
`deploy-prod.yml` promotes the same image behind a manual approval gate. **You implement the
deploy strategy for your target** — see `DEPLOY.md` and `infra/deploy/README.md`. Run any tier
locally against a target: `SMOKE_TARGET=… task test:smoke` (and `test:sniff` / `test:load`,
or `E2E_TARGET=… uv run pytest tests/e2e`).
```

In `src/framework_cli/template/CLAUDE.md.jinja`, inside the `<!-- FRAMEWORK:BEGIN/END -->` block, append to the `## CI/CD` section:

```markdown
- Deploy is a contract: the CD workflows orchestrate build→push→deploy→smoke→sniff→E2E→load→rollback; you implement the deploy *mechanism* in `infra/deploy/strategy.sh` for your target (see `DEPLOY.md`). Validation tiers: `tests/smoke/` (Phase 1), `tests/sniff/` (Phase 2), `tests/e2e/` with `E2E_TARGET` (Phase 3), `tests/non_functional/load.js` (Phase 4). Add a sniff probe per critical path; never run E2E/load writes against prod.
```

Also, in the same managed block's `## Conventions` list, **replace** the existing migration line:

```markdown
- Relational schema changes require a new migration; never edit an existing migration.
```

with (reversibility is enforced, and the discipline spans every paradigm):

```markdown
- Schema changes require a new migration; never edit an applied one. Every migration MUST be reversible — its `downgrade()` must really reverse the `upgrade()` (the migration guard blocks empty/`pass`/`raise` downgrades, in pre-commit and CI, so rollback can always step back). Prefer expand/contract; **never destroy data that cannot be reconstructed.** This applies to every database paradigm, not just the relational one.
```

- [ ] **Step 3: Add render assertions for the docs**

In `tests/test_copier_runner.py`, add:

```python
def test_render_deploy_docs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    deploy_md = (dest / "DEPLOY.md")
    assert deploy_md.is_file()
    text = deploy_md.read_text()
    assert "Demo" in text  # {{ project_name }} interpolated
    assert "infra/deploy/strategy.sh" in text

    assert "## Deploy" in (dest / "README.md").read_text()
    claude = (dest / "CLAUDE.md").read_text()
    assert "deploy" in claude.lower()
    assert "reversible" in claude.lower()  # the strengthened migration convention
```

- [ ] **Step 4: Add Docker acceptance tests (validation tiers against the live `lite` stack)**

In `tests/acceptance/test_rendered_project.py`, add (these mirror the existing live-stack helpers — bring up `lite`, run a tier against `localhost:8000`, tear down):

```python
@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_smoke_and_sniff_against_lite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # wait for /health (seeded lite app)
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as r:
                    if r.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(2)
        assert ready, "lite app did not serve /health within 120s"
        env = {**os.environ, "SMOKE_TARGET": "http://localhost:8000", "SNIFF_TARGET": "http://localhost:8000"}
        smoke = subprocess.run(["uv", "run", "pytest", "tests/smoke", "-q"], cwd=dest, env=env)
        assert smoke.returncode == 0, "smoke suite failed against the live lite stack"
        sniff = subprocess.run(["uv", "run", "pytest", "tests/sniff", "-q"], cwd=dest, env=env)
        assert sniff.returncode == 0, "sniff suite failed against the live lite stack"
        e2e = subprocess.run(
            ["uv", "run", "pytest", "tests/e2e", "-q"],
            cwd=dest, env={**os.environ, "E2E_TARGET": "http://localhost:8000"},
        )
        assert e2e.returncode == 0, "remote-mode e2e failed against the live lite stack"
    finally:
        subprocess.run(down, cwd=dest)
```

- [ ] **Step 5: Framework Layer-A gate (no Docker)**

```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/test_copier_runner.py tests/test_cli.py tests/test_naming.py tests/test_smoke.py -q
uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_precommit_runs_clean" "tests/acceptance/test_rendered_project.py::test_rendered_project_exports_openapi" -q
```
Expected: all PASS. `precommit_runs_clean` now also actionlints `deploy-staging.yml` + `deploy-prod.yml`, shellchecks `strategy.sh`/`notify.sh`/`load.sh`, and runs the `migrations-reversible` guard over the scaffold's `0001_initial.py` — all must be clean. If `ruff format --check` would change any payload `.py`, fix it (`cd /tmp/demo && uv run ruff format --check .`).

- [ ] **Step 6: Generated-project suite + validation tiers (Docker)**

```bash
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_passes_its_own_tests" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_combined_coverage_gate_passes" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_smoke_and_sniff_against_lite" -q
```
Expected: PASS. `passes_its_own_tests` (`pytest -q`, now `testpaths`=unit/functional/e2e) stays green; the 85% combined gate holds; smoke/sniff/remote-e2e pass against the live `lite` stack. Paste actual results.

- [ ] **Step 7: Update the meta-plan + CLAUDE.md state**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`: mark the **5b** row `✅ Done` with this plan's filename + the merge commit (`TBD (FF pending)` — controller fills after merge). Update the "Done so far" prose to mention the deploy seam (CD workflows + 4-phase validation + the opinionated migration-aware deploy-strategy skeleton + staging/prod compose + the migration-reversibility guard). **Add a `5c` row — "CI/CD pipelines — turnkey reference strategy" — `⬜ Not started`: a complete, host-validated compose-over-SSH + Traefik/ACME blue-green strategy that fills the `__target_*` hooks, depends on `5b`.** In CLAUDE.md, update **Last updated**, **Where we are** (5b implemented, green on branch, pending review+merge), and **Next** (Plan 6 — integrity + upskill, the next roadmap item; with Plan 5c — turnkey reference strategy — queued as a deploy follow-up).

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/DEPLOY.md.jinja src/framework_cli/template/README.md.jinja src/framework_cli/template/CLAUDE.md.jinja tests/test_copier_runner.py tests/acceptance/test_rendered_project.py docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md
git commit -m "docs(template): DEPLOY.md + deploy docs; acceptance tiers; mark Plan 5b complete"
```

---

## Self-Review

**Spec coverage (§14 deploy contract + CD staging/prod, §6 sniff/NFR, §8, §15):**
- Deployment contract (build → push → deploy → validate) → Task 7 build-push + strategy `deploy`; the contract documented in Task 6 (`infra/deploy/README.md`). ✅
- Minimum strategy interface (deploy/endpoints/await_healthy/rollback/releases/current_release/teardown) → Task 6 `strategy.sh` — all 7 ops, with the target-independent logic (config validation, release+revision recording, health-gate, **migration-aware rollback**) pre-written; only the `__target_*` hooks are left to configure. ✅
- Guarantees (versioned/addressable releases, runtime secrets, same image promoted) → Task 6 (`rollback` errors when no prior release exists; secrets from the target env; prod reuses the staging image, Task 8). No-downtime cutover is the target's *mechanism*, prescribed in the README and made turnkey by Plan 5c. ✅
- CD staging 4-phase validation (smoke→sniff→E2E→load) → Tasks 1–4 suites, sequenced in Task 7. ✅
- CD prod (approval, reuse image, smoke + read-only sniff, rollback, notify) → Task 8 (`environment: production` gate, no E2E/load, sniff read-only). ✅
- Sniff suite + `task test:sniff` (§15) → Task 2. NFR/k6 (§6 Phase 4) → Task 3. ✅
- **Migration-aware rollback + reversibility** (the recoverability/data-integrity dimension of §1) → Task 6 `rollback` reverses migrations to the previous release's revision before redeploying; Task 9 guard **blocks** irreversible migrations (pre-commit + CI); the CLAUDE.md convention prescribes expand/contract + reversibility across *all* paradigms, not just relational (Task 10). ✅
- Alert routing reuse for CD notify (§8) → Task 6 `notify.sh` seam (documented to reuse the Alertmanager destination). ✅
- Staging/prod Compose (§3 file list) → Task 5. ✅
- **Target** → the builder's choice (§21). The **strategy** is *not* delegated: every target-independent decision is pre-made in the skeleton (Task 6), reducing the builder to config + the `__target_*` commands. A complete turnkey reference (compose-over-SSH + Traefik/ACME) is **Plan 5c**, isolated because a correct no-downtime impl needs a real host to validate. ✅ ([[offload-architecture-not-delegate]])

**Placeholder scan:** No TBD/"add X"/"similar to Task N". Every code step shows full file content or an exact replacement; every run step shows the command + expected result. `strategy.sh` is an opinionated skeleton — its target-independent logic is fully written; the `__target_*` hooks are deliberate, individually-documented configuration points (each `_todo` names exactly what to implement), not vague placeholders. ✅

**Type/name consistency across tasks:**
- Target env vars — `SMOKE_TARGET` (Task 1), `SNIFF_TARGET` (Task 2), `K6_TARGET`/`SLO_P99_MS`/`SLO_ERROR_RATE_PCT` (Task 3), `E2E_TARGET` (Task 4) — used identically in the suites and in `deploy-staging.yml`/`deploy-prod.yml` (Tasks 7–8). ✅
- `api_client` fixture (Task 4) replaces `e2e_client`; the e2e tests (Task 4) use `api_client`. The 5a `e2e_client` name is fully removed (no dangling refs). ✅
- `bash infra/deploy/strategy.sh <op>` — op names (`deploy`, `endpoints`, `await-healthy`, `rollback`, `releases`, `current-release`, `teardown`) consistent between `strategy.sh` (Task 6), the workflows (Tasks 7–8), and the README. ✅
- `__target_*` hooks (`__target_place_image`, `__target_migrate`, `__target_record_release`, `__target_release_history`, `__target_teardown`) — defined in `strategy.sh` (Task 6), named identically in the README's "what you implement" table (Task 6) and the render assertion (`__target_migrate`). ✅
- `DEPLOY_ENV` / `DEPLOY_BASE_URL` — set in both workflows' `env:` (Tasks 7–8) and consumed by `strategy.sh` (`endpoints`, `await_healthy`, compose-file selection, Task 6). ✅
- Migration guard — `scripts/check_migrations.py` (Task 9), referenced by the pre-commit hook id `migrations-reversible`, the CI lint step, the README + rollback comment (Task 6), and the CLAUDE.md convention (Task 10): one mechanism, one name. ✅
- `scripts/load.sh` ↔ `tests/non_functional/load.js` env contract (`K6_TARGET`, `SLO_P99_MS`, `SLO_ERROR_RATE_PCT`, `K6_VUS`, `K6_DURATION`) matches between the runner and the script. ✅
- `${APP_IMAGE}` set by `deploy-staging.yml` (`needs.build-push.outputs.image`) / `deploy-prod.yml` and consumed by `infra/compose/staging.yml`/`prod.yml`. ✅
- `seed(session)` (Task 4) matches `db/seed.py` (verify-on-render note included). ✅

**Render-suffix correctness:** Deploy workflows + production Compose + `strategy.sh`/`notify.sh`/`load.sh`/`check_migrations.py` + the smoke/sniff/non_functional suites contain **no** Copier vars → plain files (verbatim copy preserves `${{ github.* }}` and `${VAR}`). Only `DEPLOY.md.jinja` (uses `{{ project_name }}`) and the modified `conftest.py.jinja`/`e2e/*.jinja`/`README.md.jinja`/`CLAUDE.md.jinja`/`Taskfile.yml.jinja`/`pyproject.toml.jinja` carry `.jinja`. ✅

**Validation-boundary honesty:** GitHub Actions YAML is validated by render + actionlint (the framework can't run a generated project's Actions). All *logic* — the four validation suites, `scripts/load.sh`, `strategy.sh` — is run by the framework (suites against the live `lite` stack; shellcheck on the scripts; actionlint on the workflows). The actual deploy mechanism is the builder's, exercised in their environment per `infra/deploy/README.md`. Stated in Architecture. ✅

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-21-deploy-seam.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (this repo's flow: branch → implementer per task → spec review → code-quality review → final review → merge to `master`).

**2. Inline Execution** — execute in this session with checkpoints.

**Which approach?**

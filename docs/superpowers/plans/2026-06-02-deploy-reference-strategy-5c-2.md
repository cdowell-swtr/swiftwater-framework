# Deploy Reference Strategy (Plan 5c-2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a turnkey **compose-over-SSH 1..N-host** deploy target that fills the 5b `strategy.sh` `__target_*` hooks, plus the multi-container Docker-gated e2e that proves no-downtime rolling + migration-aware rollback.

**Architecture:** A selectable target file (`infra/deploy/targets/compose-ssh.sh`) is sourced by the existing `strategy.sh` only when `DEPLOY_TARGET=compose-ssh` (skeleton byte-identical otherwise). App hosts run an app-only compose (`infra/compose/app-host.yml`, `image:${APP_IMAGE}`, `APP_RUN_MIGRATIONS=false`); the expand migration runs **once** against a shared external Postgres via a one-shot container; hosts roll one-at-a-time behind a builder-provided LB. The proof is a Docker-gated acceptance test: ≥2 `dind`+`sshd` "host" containers + a shared Postgres + a stock-`nginx` draining LB stand-in + a continuous poller asserting zero failed requests across a v1→v2 roll, then a rollback.

**Tech Stack:** Bash (the strategy + target hooks), Copier/Jinja (template payload), Docker + Docker-in-Docker + nginx + Postgres (e2e harness), pytest (framework tests; Docker-gated acceptance tier), `uv` tooling.

**Source specs:** parent `docs/superpowers/specs/2026-05-22-deploy-reference-strategy-design.md` + companion `docs/superpowers/specs/2026-06-02-deploy-e2e-harness-design.md`.

**Conventions that bind this plan:**
- `src/framework_cli/template/` is **template payload**, not framework source. Edit the `.jinja`/`.py`/config there; validate by **rendering** + exercising the generated project (`tests/test_copier_runner.py`, `tests/acceptance/`). Framework `mypy`/`ruff` do not lint payload.
- Fast hook tests render a project and invoke the real `strategy.sh` with **PATH shims** for `ssh`/`scp`/`docker`/`curl` (no Docker, runs in CI). The full dind harness is Docker-gated and skips without Docker.
- Quality gate before any commit: `uv run pytest -q && uv run ruff check . && uv run mypy src`. The PreToolUse hook blocks `git commit` until `CLAUDE.md` is staged — `git add CLAUDE.md` separately, then commit.
- Gate cadence for this branch (per the working agreement for integration slices): lighter per-task review, one full review at branch-end. Subagent implementers stage + pass the commit-gate but stop before `git commit`; the controller verifies and commits.

---

## File Structure

**Shipped template payload (rendered into projects):**
- Create `src/framework_cli/template/infra/compose/app-host.yml.jinja` — app-only host compose.
- Create `src/framework_cli/template/infra/deploy/targets/compose-ssh.sh` — the turnkey target hooks + rolling orchestration.
- Modify `src/framework_cli/template/infra/deploy/strategy.sh` — source `targets/${DEPLOY_TARGET}.sh` when set (the ONLY behavioral change; byte-identical when unset).
- Modify `src/framework_cli/template/infra/deploy/README.md` — add the compose-over-SSH turnkey-target section + config vars.
- Modify `src/framework_cli/template/DEPLOY.md.jinja` — single-host (5b) vs multi-host (5c-2) guidance.
- Modify `src/framework_cli/template/.env.example` (hybrid file — edit inside the framework-owned markers carefully) — document `DEPLOY_TARGET`/`DEPLOY_HOSTS`/`DEPLOY_SSH_USER`/`DEPLOY_PATH`.

**Framework integrity:**
- Modify `src/framework_cli/integrity/classes.py:22` — add the two new locked files to `LOCKED_TRACKED`.

**Framework tests:**
- Create `tests/test_deploy_compose_ssh.py` — fast, shim-based orchestration tests (no Docker).
- Create `tests/test_copier_runner.py` additions OR a focused test for render/interpolation of the new files.
- Create `tests/acceptance/conftest.py` — disk-backed test-temp fixture (the surgical `/tmp` fix).
- Create `tests/acceptance/deploy_e2e/` — the harness: `Dockerfile.host`, `host-entrypoint.sh`, `nginx.conf`, `harness.yml`, plus `__init__.py`.
- Create `tests/acceptance/test_deploy_e2e.py` — the Docker-gated no-downtime + rollback proofs.

---

## Task 1: App-only host compose (`app-host.yml.jinja`)

**Files:**
- Create: `src/framework_cli/template/infra/compose/app-host.yml.jinja`
- Test: `tests/test_copier_runner.py` (add one test)

The app hosts run the app **only** (no Postgres — the DB is the shared external one via `APP_DATABASE_URL`), no Traefik (the LB is the builder's), `APP_RUN_MIGRATIONS=false` (migration runs once centrally), plain HTTP on the private port the LB targets.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:

```python
def test_app_host_compose_renders_app_only(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    compose = dest / "infra/compose/app-host.yml"
    assert compose.exists(), "app-host.yml was not rendered"
    text = compose.read_text()
    # app-only: the app service on image:${APP_IMAGE}, migrations OFF, no postgres service.
    assert "image: ${APP_IMAGE" in text
    assert 'APP_RUN_MIGRATIONS: "false"' in text
    assert "postgres:" not in text, "app-host.yml must not define a Postgres service"
    assert "traefik" not in text.lower(), "app hosts serve plain HTTP behind the builder's LB"
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_app_host_compose_renders_app_only -v`
Expected: FAIL — `app-host.yml was not rendered`.

- [ ] **Step 3: Create the compose file**

`src/framework_cli/template/infra/compose/app-host.yml.jinja`:

```yaml
# App-only host topology (Plan 5c-2 compose-over-SSH target). The deploy strategy
# (infra/deploy/targets/compose-ssh.sh) scp's this to each app host and runs it there.
# NO Postgres (the DB is the single shared external one via APP_DATABASE_URL) and NO Traefik
# (TLS + health-draining is the builder-provided load balancer's job). Plain HTTP on the
# private port the LB targets. The app does NOT self-migrate — the deploy migrates ONCE
# against the shared DB (APP_RUN_MIGRATIONS=false). See infra/deploy/README.md.
services:
  app:
    image: ${APP_IMAGE:?set APP_IMAGE to the pushed registry tag}
    restart: unless-stopped
    environment:
      TZ: UTC
      APP_ENVIRONMENT: ${DEPLOY_ENV:-prod}
      APP_DATABASE_URL: ${APP_DATABASE_URL:?set APP_DATABASE_URL to the shared Postgres}
      APP_RUN_MIGRATIONS: "false"
    ports:
      - "${DEPLOY_HOST_PORT:-8000}:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/heartbeat').status==200 else 1)"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 30s
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_app_host_compose_renders_app_only -v`
Expected: PASS.

- [ ] **Step 5: Commit** (controller; subagent stops after staging + gate)

```bash
git add src/framework_cli/template/infra/compose/app-host.yml.jinja tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(template): app-only host compose for compose-over-SSH deploys"
```

---

## Task 2: `strategy.sh` selectable-target source hook

**Files:**
- Modify: `src/framework_cli/template/infra/deploy/strategy.sh`
- Test: `tests/test_deploy_compose_ssh.py` (create)

`strategy.sh` must source `infra/deploy/targets/${DEPLOY_TARGET}.sh` when `DEPLOY_TARGET` is set, so the target file's hook definitions override the `_todo` stubs. When `DEPLOY_TARGET` is unset, behavior is byte-for-byte unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_compose_ssh.py`:

```python
"""Fast, Docker-free tests for the compose-over-SSH deploy target.

They render a project, then invoke the REAL strategy.sh with PATH shims for
ssh/scp/docker/curl that log their argv to a file, so we can assert the deploy/rollback
orchestration without any real host or Docker.
"""
import os
import stat
import subprocess
from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {"project_name": "Acme API", "package_name": "acme_api", "author_name": "A", "author_email": "a@b.co"}


def _render(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    return dest


def test_strategy_unset_target_is_skeleton_todo(tmp_path: Path):
    """With DEPLOY_TARGET unset, the hooks remain _todo (exit 1 with the skeleton message)."""
    dest = _render(tmp_path)
    proc = subprocess.run(
        ["bash", "infra/deploy/strategy.sh", "releases"],
        cwd=dest, env={**os.environ, "DEPLOY_ENV": "staging"},
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "is not implemented for your target" in proc.stderr


def test_strategy_sources_compose_ssh_target(tmp_path: Path):
    """DEPLOY_TARGET=compose-ssh sources targets/compose-ssh.sh, so 'releases' no longer _todo."""
    dest = _render(tmp_path)
    # compose-ssh's __target_release_history reads from the first host via ssh; shim ssh to echo nothing.
    _install_shims(dest, ssh_stdout="")
    proc = subprocess.run(
        ["bash", "infra/deploy/strategy.sh", "releases"],
        cwd=dest,
        env={**os.environ, "PATH": f"{dest/'shims'}:{os.environ['PATH']}",
             "DEPLOY_ENV": "staging", "DEPLOY_TARGET": "compose-ssh", "DEPLOY_HOSTS": "h1 h2"},
        capture_output=True, text=True,
    )
    assert "is not implemented for your target" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr


def _install_shims(dest: Path, ssh_stdout: str = "") -> Path:
    """Put fake ssh/scp/docker/curl on PATH that append their argv to shims/calls.log."""
    shims = dest / "shims"
    shims.mkdir(exist_ok=True)
    log = shims / "calls.log"
    for name, body in {
        "ssh": f'echo "ssh $*" >> "{log}"\nprintf "%s" "{ssh_stdout}"\n',
        "scp": f'echo "scp $*" >> "{log}"\n',
        "docker": f'echo "docker $*" >> "{log}"\n',
        "curl": f'echo "curl $*" >> "{log}"\nprintf "%s" \'{{"status":"ok"}}\'\n',
    }.items():
        p = shims / name
        p.write_text("#!/usr/bin/env bash\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shims
```

- [ ] **Step 2: Run them, confirm the source-hook test fails**

Run: `uv run pytest tests/test_deploy_compose_ssh.py -v`
Expected: `test_strategy_unset_target_is_skeleton_todo` PASSES (skeleton unchanged); `test_strategy_sources_compose_ssh_target` FAILS (target not sourced / file missing).

- [ ] **Step 3: Add the source hook to `strategy.sh`**

In `src/framework_cli/template/infra/deploy/strategy.sh`, immediately after the `_todo()` function definition and **before** the `# === TARGET HOOKS` comment block, insert:

```bash
# === OPTIONAL TURNKEY TARGET ========================================================
# Set DEPLOY_TARGET to a file under targets/ to use a turnkey implementation of the hooks
# below (the framework ships `compose-ssh`; see infra/deploy/README.md). Unset = implement
# the __target_* hooks yourself for your target. Sourced AFTER the _todo stubs so the target's
# definitions win; the stubs remain the fallback for any hook a target leaves undefined.
if [ -n "${DEPLOY_TARGET:-}" ]; then
  _target_file="$(dirname "$0")/targets/${DEPLOY_TARGET}.sh"
  if [ ! -f "${_target_file}" ]; then
    echo "::error::DEPLOY_TARGET='${DEPLOY_TARGET}' but ${_target_file} does not exist." >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  . "${_target_file}"
fi
```

> Note: the `__target_*` `_todo` stubs are defined *below* this block. Sourcing here means the target file's functions, defined when it is sourced, **redefine** the stubs that follow only if the target is sourced *after* them. To guarantee override regardless of order, move the source block to the **end** of the file, just before the `operation="${1:-}"` dispatch. Put it there instead.

Correct placement — insert this block **directly above** the `operation="${1:-}"` line at the bottom:

```bash
if [ -n "${DEPLOY_TARGET:-}" ]; then
  _target_file="$(dirname "$0")/targets/${DEPLOY_TARGET}.sh"
  if [ ! -f "${_target_file}" ]; then
    echo "::error::DEPLOY_TARGET='${DEPLOY_TARGET}' but ${_target_file} does not exist." >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  . "${_target_file}"
fi
```

- [ ] **Step 4: Run the tests, confirm both pass**

Run: `uv run pytest tests/test_deploy_compose_ssh.py -v`
Expected: both PASS. (`test_strategy_sources_compose_ssh_target` needs Task 3's file — if running Task 2 in isolation, create a stub `targets/compose-ssh.sh` defining `__target_release_history() { :; }`; Task 3 replaces it. Otherwise sequence Task 3 before re-running.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/deploy/strategy.sh tests/test_deploy_compose_ssh.py CLAUDE.md
git commit -m "feat(template): strategy.sh sources DEPLOY_TARGET turnkey target file"
```

---

## Task 3: `targets/compose-ssh.sh` — hooks + rolling orchestration

**Files:**
- Create: `src/framework_cli/template/infra/deploy/targets/compose-ssh.sh`
- Test: `tests/test_deploy_compose_ssh.py` (add orchestration tests)

This implements the five `__target_*` hooks for compose-over-SSH 1..N. Key invariants (from the specs + prescribed `strategy.sh`):
- All hosts run `APP_RUN_MIGRATIONS=false`; the **expand** migration runs **once** against the shared DB via a one-shot container on the first host.
- `__target_place_image` rolls each host in turn (`up -d` → await that host's `/health`).
- The forward expand migration must NOT re-run on the rollback path (where `__target_migrate "downgrade …"` already ran). A `_migrated` shell flag (set by `__target_migrate`) gates it. `strategy.sh` runs both hooks in one process, so the flag is shared.
- `__target_migrate` (rollback) reverses migrations using the **current head image** (it has the down-path).

- [ ] **Step 1: Write the failing orchestration tests**

Add to `tests/test_deploy_compose_ssh.py`:

```python
def _read_calls(dest: Path) -> str:
    log = dest / "shims" / "calls.log"
    return log.read_text() if log.exists() else ""


def test_deploy_migrates_once_then_rolls_each_host(tmp_path: Path):
    dest = _render(tmp_path)
    # release history empty (first deploy); /health returns ok via the curl shim relayed over ssh.
    _install_shims(dest, ssh_stdout='{"status":"ok"}')
    env = {**os.environ, "PATH": f"{dest/'shims'}:{os.environ['PATH']}",
           "DEPLOY_ENV": "prod", "DEPLOY_TARGET": "compose-ssh",
           "DEPLOY_HOSTS": "h1 h2", "DEPLOY_BASE_URL": "http://lb",
           "APP_IMAGE": "reg/app:v2", "APP_DATABASE_URL": "postgresql://shared",
           "POSTGRES_PASSWORD": "x"}
    proc = subprocess.run(["bash", "infra/deploy/strategy.sh", "deploy"],
                          cwd=dest, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    calls = _read_calls(dest)
    # Migrate-once: a single 'alembic upgrade head' one-shot (run --rm) before rolling.
    assert calls.count("alembic upgrade head") == 1, calls
    # Both hosts get a compose up.
    assert "h1" in calls and "h2" in calls
    assert calls.count("compose -f app-host.yml up -d") == 2


def test_rollback_downgrades_once_then_rolls_old_image_without_reupgrade(tmp_path: Path):
    dest = _render(tmp_path)
    # release history has two rows: (old, R1) then (new, R2). __target_release_history reads via ssh.
    history = "reg/app:v1\tR1\nreg/app:v2\tR2\n"
    _install_shims(dest, ssh_stdout=history)
    # Make ssh relay the history for the 'cat releases' call but ok for health — simplest:
    # the shim returns `history` for every ssh; orchestration only greps counts, which is enough here.
    env = {**os.environ, "PATH": f"{dest/'shims'}:{os.environ['PATH']}",
           "DEPLOY_ENV": "prod", "DEPLOY_TARGET": "compose-ssh",
           "DEPLOY_HOSTS": "h1 h2", "DEPLOY_BASE_URL": "http://lb",
           "APP_IMAGE": "reg/app:v2", "APP_DATABASE_URL": "postgresql://shared"}
    proc = subprocess.run(["bash", "infra/deploy/strategy.sh", "rollback"],
                          cwd=dest, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    calls = _read_calls(dest)
    # Exactly one downgrade to R1, and NO forward 'upgrade head' on the rollback path.
    assert "alembic downgrade R1" in calls, calls
    assert "alembic upgrade head" not in calls, calls
```

> The `ssh_stdout` shim returns the same string for every `ssh`, which is adequate because these tests assert call *counts/patterns*, not health-vs-history disambiguation. The Docker e2e (Tasks 7–9) exercises the real behavior.

- [ ] **Step 2: Run them, confirm they fail**

Run: `uv run pytest tests/test_deploy_compose_ssh.py -v`
Expected: the two new tests FAIL (`compose-ssh.sh` not present / hooks not defined).

- [ ] **Step 3: Create `targets/compose-ssh.sh`**

`src/framework_cli/template/infra/deploy/targets/compose-ssh.sh`:

```bash
#!/usr/bin/env bash
# Turnkey deploy target: compose-over-SSH across 1..N app hosts (Plan 5c-2).
# Sourced by ../strategy.sh when DEPLOY_TARGET=compose-ssh. Implements the __target_* hooks.
#
# Topology: each app host runs infra/compose/app-host.yml (app-only, no Postgres, no Traefik).
# A single SHARED external Postgres is referenced by APP_DATABASE_URL. TLS + health-draining is
# the builder-provided load balancer's job (it routes only to hosts whose /health returns 200).
# The expand migration runs ONCE against the shared DB (hosts run APP_RUN_MIGRATIONS=false).
#
# Config (in addition to strategy.sh's APP_IMAGE / DEPLOY_ENV / DEPLOY_BASE_URL):
#   DEPLOY_HOSTS      space-separated app host list, e.g. "10.0.0.1 10.0.0.2"  (required)
#   APP_DATABASE_URL  the shared Postgres URL                                   (required)
#   DEPLOY_SSH_USER   ssh user                                   (default: deploy)
#   DEPLOY_PATH       dir on each host for compose + release state(default: /opt/app)
#   DEPLOY_SSH_PORT   ssh port                                   (default: 22)
#   DEPLOY_HOST_PORT  app port each host exposes to the LB       (default: 8000)
#   DEPLOY_AWAIT_TIMEOUT  per-host health wait, seconds          (default: 120)

: "${DEPLOY_SSH_USER:=deploy}"
: "${DEPLOY_PATH:=/opt/app}"
: "${DEPLOY_SSH_PORT:=22}"
: "${DEPLOY_HOST_PORT:=8000}"
: "${DEPLOY_AWAIT_TIMEOUT:=120}"

_migrated=0  # set by __target_migrate (rollback) so __target_place_image skips the forward expand

_hosts() { require_var DEPLOY_HOSTS; printf '%s\n' ${DEPLOY_HOSTS}; }
_first_host() { _hosts | head -n 1; }

_ssh() {
  local host="$1"; shift
  ssh -p "${DEPLOY_SSH_PORT}" -o StrictHostKeyChecking=accept-new -o BatchMode=yes \
    "${DEPLOY_SSH_USER}@${host}" "$@"
}

_push_compose() {
  local host="$1"
  _ssh "${host}" "mkdir -p ${DEPLOY_PATH}"
  scp -P "${DEPLOY_SSH_PORT}" -o StrictHostKeyChecking=accept-new \
    infra/compose/app-host.yml "${DEPLOY_SSH_USER}@${host}:${DEPLOY_PATH}/app-host.yml"
}

# Run an alembic command ONCE against the shared DB via a one-shot, no-deps container on the
# first host (which can reach APP_DATABASE_URL). $1=image, rest=alembic args.
_migrate_once() {
  local host img; host="$(_first_host)"; img="$1"; shift
  _push_compose "${host}"
  _ssh "${host}" "cd ${DEPLOY_PATH} && APP_IMAGE='${img}' APP_DATABASE_URL='${APP_DATABASE_URL}' \
    docker compose -f app-host.yml run --rm --no-deps app alembic $*"
}

# Bring up APP_IMAGE on one host (app-only, no self-migrate) and wait for ITS /health.
_roll_host() {
  local host="$1"
  _push_compose "${host}"
  _ssh "${host}" "cd ${DEPLOY_PATH} && APP_IMAGE='${APP_IMAGE}' APP_RUN_MIGRATIONS=false \
    APP_DATABASE_URL='${APP_DATABASE_URL}' DEPLOY_ENV='${DEPLOY_ENV}' DEPLOY_HOST_PORT='${DEPLOY_HOST_PORT}' \
    docker compose -f app-host.yml up -d"
  _await_host "${host}"
}

_await_host() {
  local host="$1" deadline body
  deadline=$(( $(date +%s) + DEPLOY_AWAIT_TIMEOUT ))
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if body="$(_ssh "${host}" "curl -fsS http://localhost:${DEPLOY_HOST_PORT}/health" 2>/dev/null)"; then
      case "${body}" in *'"breached"'*) ;; *) return 0 ;; esac
    fi
    sleep 3
  done
  echo "::error::host ${host} did not become healthy within ${DEPLOY_AWAIT_TIMEOUT}s." >&2
  return 1
}

# === hooks ===========================================================================
__target_place_image() {
  require_var APP_IMAGE
  if [ "${_migrated}" = "0" ]; then
    _migrate_once "${APP_IMAGE}" upgrade head   # expand-only; schema leads (forward deploy)
  fi
  local host
  for host in $(_hosts); do
    _roll_host "${host}"
  done
}

__target_migrate() {
  # Rollback: reverse migrations once against the shared DB using the CURRENT head image
  # (it contains the down-path for the migration being reverted). $* e.g. "downgrade <rev>".
  local head_img; head_img="$(__target_release_history | tail -n 1 | cut -f1)"
  _migrate_once "${head_img}" "$@"
  _migrated=1
}

__target_record_release() {
  require_var DEPLOY_ENV
  local host
  for host in $(_hosts); do
    _ssh "${host}" "mkdir -p ${DEPLOY_PATH} && printf '%s\t%s\n' '$1' '$2' >> ${DEPLOY_PATH}/releases-${DEPLOY_ENV}.tsv"
  done
}

__target_release_history() {
  require_var DEPLOY_ENV
  _ssh "$(_first_host)" "cat ${DEPLOY_PATH}/releases-${DEPLOY_ENV}.tsv 2>/dev/null" || true
}

__target_teardown() {
  local host
  for host in $(_hosts); do
    _ssh "${host}" "cd ${DEPLOY_PATH} && docker compose -f app-host.yml down --remove-orphans" || true
  done
}
```

- [ ] **Step 4: Run the full file, confirm green**

Run: `uv run pytest tests/test_deploy_compose_ssh.py -v`
Expected: all PASS.

- [ ] **Step 5: Shellcheck the new script**

Run: `shellcheck -x src/framework_cli/template/infra/deploy/targets/compose-ssh.sh`
Expected: clean (the `printf '%s\n' ${DEPLOY_HOSTS}` word-split is intentional — add `# shellcheck disable=SC2086` on that line in `_hosts` if flagged).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/deploy/targets/compose-ssh.sh tests/test_deploy_compose_ssh.py CLAUDE.md
git commit -m "feat(template): compose-over-SSH 1..N deploy target (migrate-once + rolling + rollback)"
```

---

## Task 4: Integrity-lock the new shipped files

**Files:**
- Modify: `src/framework_cli/integrity/classes.py:22` (`LOCKED_TRACKED`)
- Test: `tests/integrity/` (add a test) or `tests/test_cli.py`

The new `targets/compose-ssh.sh` and `app-host.yml` are framework-prescribed infra — they must be integrity-locked so a builder can't silently weaken them. (`strategy.sh` is already locked.) This is a one-time baseline manifest shift.

- [ ] **Step 1: Write the failing test**

Add to `tests/integrity/test_classes.py` (or wherever `LOCKED_TRACKED` is asserted; grep `LOCKED_TRACKED` in `tests/`):

```python
def test_new_deploy_files_are_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED
    assert "infra/deploy/targets/compose-ssh.sh" in LOCKED_TRACKED
    assert "infra/compose/app-host.yml" in LOCKED_TRACKED
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest tests/integrity/test_classes.py::test_new_deploy_files_are_locked -v`
Expected: FAIL.

- [ ] **Step 3: Register the files**

In `src/framework_cli/integrity/classes.py`, add to the `LOCKED_TRACKED` tuple (next to the other `infra/deploy/` and `infra/compose/` entries):

```python
    "infra/compose/app-host.yml",
    "infra/deploy/targets/compose-ssh.sh",
```

- [ ] **Step 4: Run the integrity suite, confirm green**

Run: `uv run pytest tests/integrity -v`
Expected: PASS. If a manifest-generation test asserts a file count or a golden manifest, update its expectation to include the two new files (the render writes `.framework/integrity.lock` listing them).

- [ ] **Step 5: Verify a fresh render locks them end-to-end**

Run:
```bash
uv run pytest tests/test_cli.py -k integrity -v
```
Expected: PASS — `framework new` records both new files in the lock; `framework integrity` verifies clean on an untouched render.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity CLAUDE.md
git commit -m "feat(integrity): lock app-host.yml + compose-ssh.sh (baseline manifest shift)"
```

---

## Task 5: Docs — README turnkey target, DEPLOY.md, `.env.example`

**Files:**
- Modify: `src/framework_cli/template/infra/deploy/README.md`
- Modify: `src/framework_cli/template/DEPLOY.md.jinja`
- Modify: `src/framework_cli/template/.env.example` (hybrid file — edit *outside* the `FRAMEWORK:BEGIN/END` markers unless the deploy vars belong inside; check `sections.py` rules first)
- Test: `tests/test_copier_runner.py` (assert the README documents the turnkey target + vars)

- [ ] **Step 1: Write the failing doc-content test**

Add to `tests/test_copier_runner.py`:

```python
def test_deploy_readme_documents_compose_ssh_target(tmp_path: Path):
    dest = tmp_path / "proj"
    render_project(dest, DATA)
    readme = (dest / "infra/deploy/README.md").read_text()
    assert "DEPLOY_TARGET=compose-ssh" in readme
    assert "DEPLOY_HOSTS" in readme
    assert "load balancer" in readme.lower()
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_deploy_readme_documents_compose_ssh_target -v`
Expected: FAIL.

- [ ] **Step 3: Add the README section**

Append to `src/framework_cli/template/infra/deploy/README.md` (after `## Pick a target`, before/near `## What you implement`):

```markdown
## Turnkey target: compose-over-SSH (1..N hosts)

Instead of implementing the `__target_*` hooks yourself, set **`DEPLOY_TARGET=compose-ssh`**
(a workflow/Environment variable) to use the framework's shipped reference target,
`infra/deploy/targets/compose-ssh.sh`. It deploys your pushed image across 1..N app hosts,
rolling, with no downtime **given a health-draining load balancer + the app's graceful
shutdown** (the LB is yours to provide — see below).

**Topology.** Each app host runs `infra/compose/app-host.yml` (app-only; **no Postgres**, **no
Traefik**) serving plain HTTP on a private port. A single **shared external Postgres**
(`APP_DATABASE_URL`) is referenced by every host. Your **load balancer** terminates TLS and
**drains a host by health**: route only to hosts whose `/health` returns 200; drain promptly
when one goes unhealthy. The roll is one host at a time, so with ≥2 hosts the LB always has a
healthy target.

**Migration safety.** The deploy runs the **expand** migration **once** against the shared DB
(hosts run `APP_RUN_MIGRATIONS=false`); rollback reverses it once **after** the code is rolled
back. Every per-deploy migration must be backward-compatible (expand-only) — destructive
(contract) changes are a separate later release. This is enforced by the contract-direction
guard (`scripts/check_migrations.py`); see "Migrations" below.

**Config you set (in addition to the table below):**

| Variable | Where | Meaning |
| --- | --- | --- |
| `DEPLOY_TARGET` | Environment variable | `compose-ssh` to use this turnkey target |
| `DEPLOY_HOSTS` | Environment variable | space-separated app host list, e.g. `"10.0.0.1 10.0.0.2"` |
| `APP_DATABASE_URL` | secret | the shared external Postgres |
| `DEPLOY_SSH_USER` | Environment variable | ssh user (default `deploy`); needs an SSH key (secret) + docker access on each host |
| `DEPLOY_PATH` | Environment variable | dir on each host for the compose file + release state (default `/opt/app`) |
| `DEPLOY_HOST_PORT` | Environment variable | private app port the LB targets (default `8000`) |

**Builder responsibilities (not shipped):** TLS at the LB; firewall the app port to the LB
only; provision + back up the shared Postgres.
```

- [ ] **Step 4: Add the single-host vs multi-host note to `DEPLOY.md.jinja`**

Add a short subsection contrasting single-host (5b bundled-Postgres) vs multi-host (this target, external DB), pointing at `infra/deploy/README.md#turnkey-target-compose-over-ssh-1n-hosts`.

- [ ] **Step 5: Document the `DEPLOY_*` vars in `.env.example`**

Add the `DEPLOY_TARGET`/`DEPLOY_HOSTS`/`DEPLOY_SSH_USER`/`DEPLOY_PATH`/`DEPLOY_HOST_PORT` vars with comments. **First** read `src/framework_cli/integrity/sections.py` + the existing `.env.example` markers — `.env.example` is a `hybrid` integrity file; edit only the builder-region unless these belong in the framework section, in which case the section hash updates (and the integrity test will tell you).

- [ ] **Step 6: Run render + integrity, confirm green**

Run: `uv run pytest tests/test_copier_runner.py::test_deploy_readme_documents_compose_ssh_target tests/integrity -v`
Expected: PASS. If `.env.example`'s framework section changed, regenerate/confirm the hybrid manifest expectation.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/deploy/README.md src/framework_cli/template/DEPLOY.md.jinja src/framework_cli/template/.env.example tests/test_copier_runner.py CLAUDE.md
git commit -m "docs(template): document the compose-over-SSH turnkey deploy target"
```

---

## Task 6: Disk-backed test temp (surgical `/tmp` fix) + host-UID note

**Files:**
- Create: `tests/acceptance/conftest.py`
- Test: itself (a fixture-behavior assertion)

The dev `/tmp` is RAM-backed tmpfs (16 GB). Heavy renders + dind layers must land on the 936 GB ext4 disk. This fixture provides a disk-backed working dir for the acceptance tier; it travels to CI (which sets `SWIFTWATER_TEST_TMP` or falls back to `/var/tmp`). The host-UID concern (root-owned `__pycache__`) is handled by reusing the existing `_compose_env()` (UID/GID) in the e2e harness (Task 7).

> **One-time environment insurance (NOT a code step):** on this WSL box, `sudo systemctl mask tmp.mount && wsl.exe --shutdown` reverts `/tmp` to the ext4 root (disk-backed). It needs a WSL restart, so run it from a host terminal between sessions. The conftest fix below is the load-bearing one; this is optional QoL.

- [ ] **Step 1: Write the failing test**

Create `tests/acceptance/conftest.py`:

```python
"""Acceptance-tier fixtures. The dev /tmp is RAM-backed (tmpfs); heavy renders + dind layers
must use a disk-backed dir. `disk_tmp` yields a per-test dir under a disk-backed root."""
import os
import shutil
from pathlib import Path

import pytest

_DISK_ROOT = Path(os.environ.get("SWIFTWATER_TEST_TMP", "/var/tmp/swiftwater-tests"))


@pytest.fixture
def disk_tmp(request) -> Path:
    _DISK_ROOT.mkdir(parents=True, exist_ok=True)
    d = _DISK_ROOT / f"{request.node.name}"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
```

Add a co-located test in `tests/acceptance/test_deploy_e2e.py` (created next task) — or a temporary `tests/acceptance/test_conftest_disk_tmp.py`:

```python
def test_disk_tmp_is_not_under_ram_tmp(disk_tmp):
    assert disk_tmp.exists()
    # The whole point: the dir must NOT live under the RAM-backed /tmp tmpfs.
    assert not str(disk_tmp).startswith("/tmp/"), f"{disk_tmp} is under RAM-backed /tmp"
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `uv run pytest tests/acceptance/test_conftest_disk_tmp.py -v`
Expected: FAIL — `fixture 'disk_tmp' not found`.

- [ ] **Step 3: (conftest already written in Step 1) Run it, confirm pass**

Run: `uv run pytest tests/acceptance/test_conftest_disk_tmp.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/acceptance/conftest.py tests/acceptance/test_conftest_disk_tmp.py CLAUDE.md
git commit -m "test(acceptance): disk-backed temp fixture (keep heavy renders off RAM tmpfs)"
```

---

## Task 7: e2e harness — dind+sshd hosts, nginx LB, shared Postgres

**Files:**
- Create: `tests/acceptance/deploy_e2e/__init__.py`
- Create: `tests/acceptance/deploy_e2e/Dockerfile.host`
- Create: `tests/acceptance/deploy_e2e/host-entrypoint.sh`
- Create: `tests/acceptance/deploy_e2e/nginx.conf`
- Create: `tests/acceptance/deploy_e2e/harness.yml`
- Test: assembled/validated in Task 8 (this task delivers the fixtures + a `docker compose config` validation test)

The harness brings up two privileged `dind`+`sshd` host containers, a stock-nginx draining LB, and a shared Postgres, all on one network. The pytest process renders the project, builds the app image (two tags, v1/v2 — Task 8), loads them into each host's nested docker, then runs the real `strategy.sh` from a controller context that ssh's to `host1`/`host2`.

- [ ] **Step 1: Create the host image (`Dockerfile.host`)**

```dockerfile
# A simulated "app host": Docker-in-Docker (its own dockerd) + sshd, so the real
# compose-over-SSH strategy can ssh in and run `docker compose`. Test-harness only.
FROM docker:27-dind
RUN apk add --no-cache openssh bash curl
# sshd host keys + a 'deploy' user with docker access; key auth only.
RUN ssh-keygen -A \
 && adduser -D -s /bin/bash deploy \
 && addgroup deploy docker \
 && mkdir -p /home/deploy/.ssh && chmod 700 /home/deploy/.ssh
# The public key is provided at build time via the build context (Task 8 generates the pair).
COPY authorized_keys /home/deploy/.ssh/authorized_keys
RUN chown -R deploy:deploy /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
COPY host-entrypoint.sh /usr/local/bin/host-entrypoint.sh
RUN chmod +x /usr/local/bin/host-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/host-entrypoint.sh"]
```

- [ ] **Step 2: Create `host-entrypoint.sh`**

```bash
#!/usr/bin/env bash
# Start the nested dockerd (dind) in the background, then sshd in the foreground.
set -e
# dind's own entrypoint starts dockerd; run it backgrounded via the standard script.
dockerd-entrypoint.sh dockerd >/var/log/dockerd.log 2>&1 &
# Wait for the nested daemon socket.
for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
exec /usr/sbin/sshd -D -e
```

- [ ] **Step 3: Create `nginx.conf` (the draining LB stand-in)**

```nginx
# Stand-in for the builder-provided load balancer. Passive health: drop a host that refuses
# connections (it's updating) and retry the other, so an in-flight request never fails during a
# rolling update. This models "route only to /health-passing hosts; drain on unhealthy".
events {}
http {
  upstream app {
    server host1:8000 max_fails=1 fail_timeout=2s;
    server host2:8000 max_fails=1 fail_timeout=2s;
  }
  server {
    listen 80;
    location / {
      proxy_pass http://app;
      proxy_connect_timeout 1s;
      proxy_next_upstream error timeout http_502 http_503 http_504;
      proxy_next_upstream_tries 2;
    }
  }
}
```

- [ ] **Step 4: Create `harness.yml`**

```yaml
# e2e deploy harness (Plan 5c-2). Brought up by tests/acceptance/test_deploy_e2e.py.
# host1/host2 are privileged dind+sshd "app hosts"; lb is the draining nginx stand-in;
# postgres is the single shared external DB. The pytest process is the deploy controller.
name: swiftwater-deploy-e2e
services:
  host1:
    build: { context: ., dockerfile: Dockerfile.host }
    privileged: true
    ports: ["2201:22", "8001:8000"]   # ssh + app (published from nested docker)
    tmpfs: []                          # dind data stays on the container layer (disk-backed root)
  host2:
    build: { context: ., dockerfile: Dockerfile.host }
    privileged: true
    ports: ["2202:22", "8002:8000"]
  postgres:
    image: postgres:17
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 3s
      timeout: 3s
      retries: 20
  lb:
    image: nginx:1.27-alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    ports: ["8080:80"]
    depends_on: [host1, host2]
```

- [ ] **Step 5: Write a fixtures-valid test**

In `tests/acceptance/test_deploy_e2e.py` (start the file):

```python
import os, shutil, subprocess
from pathlib import Path
import pytest

HARNESS = Path(__file__).parent / "deploy_e2e"


def _docker() -> bool:
    return shutil.which("docker") is not None and \
        subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0


@pytest.mark.skipif(not _docker(), reason="docker required for the deploy e2e harness")
def test_harness_compose_config_is_valid():
    # An authored-key placeholder so `build` context resolves during config validation.
    (HARNESS / "authorized_keys").write_text("# placeholder\n")
    proc = subprocess.run(
        ["docker", "compose", "-f", str(HARNESS / "harness.yml"), "config"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "host1" in proc.stdout and "host2" in proc.stdout and "lb" in proc.stdout
```

- [ ] **Step 6: Run it**

Run: `uv run pytest tests/acceptance/test_deploy_e2e.py::test_harness_compose_config_is_valid -v`
Expected: PASS (or SKIP if Docker absent — acceptable on a no-Docker runner).

- [ ] **Step 7: Commit**

```bash
git add tests/acceptance/deploy_e2e tests/acceptance/test_deploy_e2e.py CLAUDE.md
git commit -m "test(acceptance): dind+sshd+nginx+postgres deploy e2e harness fixtures"
```

---

## Task 8: e2e proof — no-downtime across a v1→v2 roll

**Files:**
- Modify: `tests/acceptance/test_deploy_e2e.py` (add the no-downtime test + shared helpers)

This is the headline proof. Render once; build **two** app image tags that differ by an **expand** migration (a new nullable column) so the roll also exercises migrate-once; load both into each host; run `strategy.sh deploy` for v1 (baseline), start a continuous poller through the LB, then `strategy.sh deploy` for v2; assert **zero failed requests** during the v1→v2 roll.

- [ ] **Step 1: Write the helpers + failing test**

Add to `tests/acceptance/test_deploy_e2e.py`:

```python
import threading, time, urllib.request
from framework_cli.copier_runner import render_project

DATA = {"project_name": "Acme API", "package_name": "acme_api", "author_name": "A", "author_email": "a@b.co"}
LB_URL = "http://localhost:8080/health"


def _run(cmd, cwd=None, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check:
        assert p.returncode == 0, f"{cmd}\nSTDOUT:{p.stdout}\nSTDERR:{p.stderr}"
    return p


class _Poller(threading.Thread):
    """Hammer the LB; record any failure (non-200 or connection error)."""
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_flag = threading.Event(); self.total = 0; self.failures = 0
    def run(self):
        while not self.stop_flag.is_set():
            self.total += 1
            try:
                with urllib.request.urlopen(LB_URL, timeout=2) as r:
                    if r.status != 200:
                        self.failures += 1
            except Exception:
                self.failures += 1
            time.sleep(0.05)


@pytest.mark.skipif(not _docker(), reason="docker required for the deploy e2e harness")
def test_rolling_deploy_has_zero_downtime(disk_tmp):
    """v1 deployed across 2 hosts, poller running, deploy v2 → zero failed requests."""
    # 1. Render + generate an SSH keypair into the harness build context.
    project = disk_tmp / "proj"
    render_project(project, DATA)
    _generate_keypair(HARNESS, disk_tmp)         # writes authorized_keys (context) + id_e2e (controller)
    # 2. Build v1, and v2 = v1 + an expand migration (new nullable column).
    _build_app_image(project, tag="acme:v1")
    _add_expand_migration(project)               # additive, backward-compatible
    _build_app_image(project, tag="acme:v2")
    # 3. Bring up the harness; load both images into each host's nested docker.
    _compose_up()
    try:
        _load_image_into_hosts("acme:v1"); _load_image_into_hosts("acme:v2")
        env = _strategy_env(project)             # DEPLOY_TARGET, DEPLOY_HOSTS=host1 host2, APP_DATABASE_URL=...
        # 4. Baseline deploy v1, wait for the LB to serve.
        _run(["bash", "infra/deploy/strategy.sh", "deploy"], cwd=project, env={**env, "APP_IMAGE": "acme:v1"})
        _await_lb_healthy()
        # 5. Poller on; roll to v2; poller off.
        poller = _Poller(); poller.start()
        time.sleep(1)
        _run(["bash", "infra/deploy/strategy.sh", "deploy"], cwd=project, env={**env, "APP_IMAGE": "acme:v2"})
        time.sleep(1)
        poller.stop_flag.set(); poller.join(timeout=5)
        assert poller.total > 10, f"poller barely ran ({poller.total})"
        assert poller.failures == 0, f"{poller.failures}/{poller.total} requests failed during the roll"
    finally:
        _compose_down()
```

- [ ] **Step 2: Implement the helpers**

Add these to the test module (concrete bodies — no placeholders):

```python
import json

HOSTS = {"host1": 2201, "host2": 2202}
KEY = None  # path to the controller private key, set by _generate_keypair


def _generate_keypair(context: Path, workdir: Path):
    global KEY
    KEY = workdir / "id_e2e"
    _run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(KEY)])
    (context / "authorized_keys").write_text((KEY.with_suffix(".pub")).read_text())


def _build_app_image(project: Path, tag: str):
    _run(["docker", "build", "-f", "infra/docker/Dockerfile", "-t", tag, "."], cwd=project)


def _add_expand_migration(project: Path):
    """Drop in an additive, backward-compatible migration (new nullable column on items)."""
    mig = project / "migrations/versions/0099_e2e_expand.py"
    head = _run(["uv", "run", "alembic", "heads"], cwd=project).stdout.split()[0]
    mig.write_text(f'''"""e2e expand: add nullable note column"""
from alembic import op
import sqlalchemy as sa
revision = "0099_e2e_expand"
down_revision = "{head}"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("items", sa.Column("note", sa.String(), nullable=True))
def downgrade():
    op.drop_column("items", "note")
''')


def _compose_up():
    _run(["docker", "compose", "-f", str(HARNESS / "harness.yml"), "up", "-d", "--build"])
    # wait for sshd on each host + postgres healthy
    for _, port in HOSTS.items():
        _wait_tcp("localhost", port, 60)


def _compose_down():
    subprocess.run(["docker", "compose", "-f", str(HARNESS / "harness.yml"), "down", "-v"],
                   capture_output=True, text=True)


def _load_image_into_hosts(tag: str):
    save = subprocess.run(["docker", "save", tag], capture_output=True)
    for host, port in HOSTS.items():
        subprocess.run(
            ["ssh", "-i", str(KEY), "-p", str(port), "-o", "StrictHostKeyChecking=no",
             f"deploy@localhost", "docker", "load"],
            input=save.stdout, capture_output=True, check=True)


def _strategy_env(project: Path) -> dict:
    # The controller ssh's to host1/host2 by their published localhost ports. We expose a thin
    # ssh wrapper on PATH so DEPLOY_HOSTS can be "host1 host2" while real ssh hits localhost:220x.
    return {
        **os.environ,
        "PATH": f"{_ssh_wrapper_dir(project)}:{os.environ['PATH']}",
        "DEPLOY_TARGET": "compose-ssh",
        "DEPLOY_ENV": "prod",
        "DEPLOY_HOSTS": "host1 host2",
        "DEPLOY_BASE_URL": "http://localhost:8080",
        "DEPLOY_SSH_USER": "deploy",
        "APP_DATABASE_URL": "postgresql+psycopg://app:app@postgres:5432/app",
    }
```

> **Networking note for the controller:** the pytest process runs on the WSL host, but the
> shared Postgres + inter-host references use docker-network names (`postgres`, `host1`,
> `host2`). Two clean options — pick one in Step 3:
> (a) **Run the controller inside a container on the harness network** (add a `controller`
> service to `harness.yml` with the rendered project mounted + the ssh key; `docker compose run
> controller bash infra/deploy/strategy.sh deploy`). Then `DEPLOY_HOSTS="host1 host2"`,
> `APP_DATABASE_URL=...@postgres:...` resolve natively. **Recommended** — no wrapper, no
> port-mapping skew, and it's the most faithful.
> (b) Keep the controller on the host with an `ssh` PATH-wrapper mapping `host1→localhost:2201`
> etc., and publish Postgres to the host. More moving parts.

- [ ] **Step 3: Switch to the controller-in-container model (recommended)**

Add to `harness.yml`:

```yaml
  controller:
    build: { context: ., dockerfile: Dockerfile.host }   # reuse: has ssh + docker + bash + curl
    privileged: true
    volumes:
      - ${E2E_PROJECT_DIR}:/work:ro
      - ${E2E_KEY}:/root/.ssh/id_ed25519:ro
    working_dir: /work
    command: ["sleep", "infinity"]
    depends_on: [host1, host2, postgres]
```

Then the test runs the strategy via `docker compose ... exec -T controller bash infra/deploy/strategy.sh deploy` with the strategy env passed through `-e`, and the poller still hits `localhost:8080` (the LB's published port). Replace `_strategy_env`/`_run`-of-strategy accordingly. This removes the ssh-wrapper helper entirely.

- [ ] **Step 4: Run the proof**

Run: `SWIFTWATER_TEST_TMP=/var/tmp/swiftwater-tests uv run pytest tests/acceptance/test_deploy_e2e.py::test_rolling_deploy_has_zero_downtime -v`
Expected: PASS — `poller.failures == 0`. (First run is slow: builds two images + dind boot. If flaky on timing, raise `_await_lb_healthy` timeout and the post-roll settle sleep.)

- [ ] **Step 5: Confirm no RAM/`/tmp` blowup + clean teardown**

Run: `df -h /tmp /var/tmp && docker ps -a | grep deploy-e2e || true`
Expected: `/tmp` not near full; no leftover harness containers (the `finally: _compose_down()` removed them).

- [ ] **Step 6: Commit**

```bash
git add tests/acceptance/test_deploy_e2e.py tests/acceptance/deploy_e2e/harness.yml CLAUDE.md
git commit -m "test(acceptance): prove zero-downtime rolling deploy across 2 hosts"
```

---

## Task 9: e2e proof — rollback (code-back-then-downgrade)

**Files:**
- Modify: `tests/acceptance/test_deploy_e2e.py` (add the rollback test, reusing Task 8 helpers)

Prove the symmetric inverse: after deploying v2 (expand applied), `strategy.sh rollback` rolls the code back to v1 on all hosts and downgrades the schema once; assert the prior release serves and the expand column is gone.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.skipif(not _docker(), reason="docker required for the deploy e2e harness")
def test_rollback_restores_prior_release_and_schema(disk_tmp):
    project = disk_tmp / "proj"
    render_project(project, DATA)
    _generate_keypair(HARNESS, disk_tmp)
    _build_app_image(project, tag="acme:v1")
    _add_expand_migration(project)
    _build_app_image(project, tag="acme:v2")
    _compose_up()
    try:
        _load_image_into_hosts("acme:v1"); _load_image_into_hosts("acme:v2")
        env = _strategy_env(project)
        _deploy(project, env, "acme:v1"); _await_lb_healthy()
        _deploy(project, env, "acme:v2"); _await_lb_healthy()
        # Expand column present after v2.
        assert _column_exists("items", "note") is True
        # Roll back: code back to v1 on all hosts, then downgrade once.
        _rollback(project, env); _await_lb_healthy()
        # current-release is v1 again; schema reverted (note column gone).
        cur = _current_release(project, env)
        assert cur == "acme:v1", cur
        assert _column_exists("items", "note") is False
    finally:
        _compose_down()


def _column_exists(table: str, col: str) -> bool:
    q = (f"SELECT 1 FROM information_schema.columns "
         f"WHERE table_name='{table}' AND column_name='{col}'")
    out = subprocess.run(
        ["docker", "compose", "-f", str(HARNESS / "harness.yml"), "exec", "-T", "postgres",
         "psql", "-U", "app", "-d", "app", "-tAc", q], capture_output=True, text=True)
    return out.stdout.strip() == "1"
```

- [ ] **Step 2: Implement `_deploy`/`_rollback`/`_current_release`**

Thin wrappers over the controller exec (mirrors Task 8 Step 3):

```python
def _strategy(project, env, op, *args):
    cmd = ["docker", "compose", "-f", str(HARNESS / "harness.yml"), "exec", "-T"]
    for k in ("DEPLOY_TARGET", "DEPLOY_ENV", "DEPLOY_HOSTS", "DEPLOY_BASE_URL",
              "DEPLOY_SSH_USER", "APP_DATABASE_URL", "APP_IMAGE"):
        if k in env:
            cmd += ["-e", f"{k}={env[k]}"]
    cmd += ["controller", "bash", "infra/deploy/strategy.sh", op, *args]
    return _run(cmd)

def _deploy(project, env, image): _strategy(project, {**env, "APP_IMAGE": image}, "deploy")
def _rollback(project, env): _strategy(project, env, "rollback")
def _current_release(project, env): return _strategy(project, env, "current-release").stdout.strip()
```

- [ ] **Step 3: Run it, confirm green**

Run: `SWIFTWATER_TEST_TMP=/var/tmp/swiftwater-tests uv run pytest tests/acceptance/test_deploy_e2e.py::test_rollback_restores_prior_release_and_schema -v`
Expected: PASS — `current-release == acme:v1` and the `note` column is gone.

- [ ] **Step 4: Run the whole e2e module + confirm teardown**

Run: `SWIFTWATER_TEST_TMP=/var/tmp/swiftwater-tests uv run pytest tests/acceptance/test_deploy_e2e.py -v && docker ps -a | grep deploy-e2e || echo "clean"`
Expected: all PASS; `clean`.

- [ ] **Step 5: Commit**

```bash
git add tests/acceptance/test_deploy_e2e.py CLAUDE.md
git commit -m "test(acceptance): prove rollback restores prior release + reverts schema"
```

---

## Task 10: Wire-up, full gate, state, branch-end review

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md` (5c-2 row → status)
- Modify: `CLAUDE.md` (Current State pointer)
- Optionally modify: `src/framework_cli/template/.github/workflows/deploy-staging.yml` / `deploy-prod.yml` (set `DEPLOY_TARGET: compose-ssh` as the documented default, gated so builders can override)

- [ ] **Step 1: Decide the workflow default**

The deploy workflows currently leave the target to the builder. Either (a) leave them target-agnostic and rely on README opt-in (lowest surprise), or (b) set `DEPLOY_TARGET: ${{ vars.DEPLOY_TARGET || '' }}` so a builder enables compose-ssh via a repo variable without editing the workflow. Pick (b) — additive, no forced behavior. Add a render test asserting the workflow references `DEPLOY_TARGET`.

```python
# tests/test_copier_runner.py
def test_deploy_workflows_pass_through_deploy_target(tmp_path: Path):
    dest = tmp_path / "proj"; render_project(dest, DATA)
    wf = (dest / ".github/workflows/deploy-staging.yml").read_text()
    assert "DEPLOY_TARGET" in wf
```

Implement: add `DEPLOY_TARGET: ${{ vars.DEPLOY_TARGET }}` to the `env:` block of both deploy workflows. Run the test green. Commit.

- [ ] **Step 2: Run the full framework gate (ex-acceptance) + the render-matrix lint**

```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check . && uv run ruff format --check . && uv run mypy src
shellcheck -x src/framework_cli/template/infra/deploy/strategy.sh src/framework_cli/template/infra/deploy/targets/compose-ssh.sh
```
Expected: all green. Then render baseline + all-batteries and run each generated project's own `ruff format --check` + `mypy src` (per `[[release-readiness-needs-render-not-local-gate]]`).

- [ ] **Step 3: Run the Docker-gated acceptance e2e once end-to-end**

```bash
SWIFTWATER_TEST_TMP=/var/tmp/swiftwater-tests uv run pytest tests/acceptance/test_deploy_e2e.py -v
sudo rm -rf /tmp/pytest-of-chris/* 2>/dev/null || true
```
Expected: PASS; `/tmp` not wedged.

- [ ] **Step 4: Update state docs**

Set the meta-plan 5c-2 row to ✅ Done (FF SHA after merge) and update the `CLAUDE.md` Current State pointer + `Last updated` datetime. `git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md`.

- [ ] **Step 5: Branch-end review**

Per the working agreement, run one full review at branch-end (Opus whole-branch review for cross-cutting concerns; the 18 app-agents are noise on this framework-internal deploy infra — skip per the established cadence decision). Address findings, then merge FF to `master` and delete the branch.

```bash
git add -A && git commit -m "docs(state): Plan 5c-2 compose-over-SSH turnkey deploy + e2e merged"
```

---

## Self-Review

**1. Spec coverage:**
- Parent §2 packaging (selectable target, not forced) → Tasks 2, 3, 10. ✓
- Parent §3 topology (app-only hosts, shared DB, builder LB) → Task 1 (`app-host.yml`), Task 3 (orchestration), Task 7 (harness). ✓
- Parent §4 orchestration (migrate-once-up; rolling; rollback code-then-downgrade) → Task 3 (`_migrate_once` + `_migrated` flag + rolling), proven in Tasks 8/9. ✓
- Parent §5 migration safety (expand-only; contract guard) → contract guard already shipped in 5c-1; the e2e uses an expand migration (Task 8 `_add_expand_migration`). README documents the discipline (Task 5). ✓
- Parent §6 config/state → Task 3 (`__target_record_release`/`release_history` on each host) + Task 5 (`.env.example`/README vars). ✓
- Companion §4 harness (≥2 dind+sshd hosts, shared PG, nginx LB, continuous poller, rollback) → Tasks 7/8/9. ✓
- Companion §5 host model (dind + real SSH) → Task 7 `Dockerfile.host` + controller exec. ✓
- Companion §6 temp/RAM (surgical disk-backed, host-UID, optional mask) → Task 6 (conftest) + Task 7 (reuse `_compose_env` UID/GID) + Task 6 ops note. ✓
- Companion §2 integrity-lock → Task 4. ✓

**2. Placeholder scan:** the controller networking has two options (Task 8 Step 2/3) with a clear *recommended* choice (controller-in-container) — Step 3 commits to it and removes the wrapper; not a placeholder, a resolved fork. `_await_lb_healthy`, `_wait_tcp`, `_ssh_wrapper_dir` are referenced helpers — **the implementer must add them** (trivial: poll `LB_URL` until 200 / poll a TCP port / unused once Step 3's container model is adopted). Flagged here so they aren't missed.

**3. Type/name consistency:** hook names match `strategy.sh` exactly (`__target_place_image`/`__target_migrate`/`__target_record_release`/`__target_release_history`/`__target_teardown`); `DEPLOY_*` var names consistent across `compose-ssh.sh`, README, `.env.example`, and the e2e env; `_migrate_once(image, *alembic_args)` signature consistent between forward (`upgrade head`) and rollback (`downgrade <rev>`) call sites.

**Note for the implementer:** add the small referenced helpers in Task 8 (`_await_lb_healthy` = poll `http://localhost:8080/health` until 200 within ~90s; `_wait_tcp(host, port, timeout)` = socket-connect retry). Adopt the controller-in-container model (Task 8 Step 3) from the start — it makes `DEPLOY_HOSTS`/`APP_DATABASE_URL` resolve by docker-network name and deletes the ssh-wrapper path entirely.

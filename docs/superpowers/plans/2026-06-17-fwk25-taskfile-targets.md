# FWK25 — Taskfile targets through the `task` runner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#4** of the batch and lands **after
> FWK24, FWK23, and FWK26**. Those plans already added `_traefik_request`, `_traefik_ws_upgrade`,
> `_mkcert_ssl_context`, `_poll_json` — **this plan assumes all four exist and does NOT redefine
> them**. Steps use `- [ ]`.

**Goal:** Close M5 (Taskfile `dev` / `dev:lite` driven through `task` — preconditions,
`-f` merge order, UID/GID env) and M6 (`ci` / `test:cov:ci` / `db:migrate` / `db:seed` through
`task` — ci task-graph chain; `test:cov:ci` 85% args; `framework-integrity` precondition;
`db:` target cwd-from-root behavior).

**Architecture:** Two tests:

- **Test A (M5) — `task dev:lite` drives the whole dev:lite entrypoint.** The existing
  `test_rendered_project_dev_lite_stack_serves_health` calls raw `docker compose … up` directly,
  bypassing `task`. This test substitutes `subprocess.run(["task", "dev:lite"])` so the
  preconditions (docker / uv.lock check), the `-f` merge order, and the UID/GID env shell-outs
  are actually driven. Because `task dev:lite` calls `./scripts/compose.sh` (the FWK31
  PORT_OFFSET wrapper) in ATTACHED mode (not `-d`), it must run as a **background subprocess**;
  the test polls `/health` through the ephemeral host port, asserts the response, then tears down
  via raw `docker compose … down -v` with the same `-f` list and inherited isolation env. A
  **negative precondition case** — remove `uv.lock` before running `task dev:lite`, assert
  non-zero exit with the missing-lock message — proves the precondition machinery fires fast
  without starting the stack.

- **Test B (M6, live half) — `task db:migrate` then `task db:seed`, with Postgres up.** Render a
  baseline project, bring up only `postgres` from the lite profile (raw compose, the cheapest
  bring-up that doesn't require `task dev:lite` to be running), then run `task db:migrate` and
  `task db:seed` sequentially in `cwd=dest`. Assert that after `db:seed` the seeded items are
  queryable via `compose exec -T postgres psql` (the FWK20 pattern), proving seed.py ran
  cwd-from-root. `db:migrate` has no preconditions in the Taskfile; `db:seed` has no
  preconditions either — both just delegate to `uv run`. The M6 risk is `cwd`-from-root: if
  `db:seed` resolves `scripts/seed.py` relative to a wrong working directory, the subprocess
  fails. Catch it with the psql row count assertion.

- **Test C (M6, gate-tier YAML-graph assertion) — extend `test_copier_runner.py` to assert the
  `ci:` target chain.** The only existing assertion (`test_copier_runner.py:752-754`) checks
  `"ci:" in taskfile` but never asserts the sub-task chain or the 85% arg. Parse the rendered
  Taskfile.yml as raw YAML and assert: the `ci.cmds` list contains `task: lint`, `task:
  test:cov:ci`, `task: audit`, `task: openapi:export` in that order; and that the `test:cov:ci`
  target's single cmd contains `85`. This test is **gate-tier** (no Docker, runs in CI) and
  belongs in `tests/test_copier_runner.py`.

**Tech Stack:** Python, pytest, Docker (`_docker_available()`), go-task (`shutil.which("task")`),
the existing acceptance harnesses (`_compose_env`, `_compose_host_port`, `_isolate_compose_project`
autouse fixture), yaml (already imported in test_copier_runner.py).

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add two tests:
  `test_rendered_taskfile_dev_lite_target_drives_stack` (M5, including the negative precondition
  case) and `test_rendered_taskfile_db_targets_seed_rows` (M6 live half). Place them after the
  existing `test_rendered_project_dev_lite_stack_serves_health` (~line 934).
- **Modify** `tests/test_copier_runner.py` — add
  `test_render_ci_task_chain_and_85_percent_gate` (M6 gate-tier YAML-graph assertion). Place it
  after the existing `test_render_docs_battery_adds_taskfile_tasks` (~line 3247).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy — required staged on every
  commit).

**Registry scope.** `tests/runtime_coverage/registry.py` enumerates compose services,
Dockerfile stages, scripts, hooks, and CI workflow jobs — **not** Taskfile targets. The registry
docstring (registry.py:8-10) explicitly puts "in-app code-path surfaces" out of scope. There are
no KNOWN_GAP keys for `dev`, `dev:lite`, `ci`, `db:migrate`, or `db:seed`. Verified:

```bash
grep -n "dev:lite\|db:migrate\|db:seed\|task ci\|FWK25" tests/runtime_coverage/registry.py
# returns: no matches
```

FWK25 adds coverage for Taskfile-target behaviors that are **NOT** enumerated registry surfaces.
**No registry entry flips.** Do NOT invent registry keys for them.

**No template change is expected** (test-only). If a test goes red on a real template defect —
a broken precondition in `dev:lite`, a mis-chained ci sub-task, a `db:seed` cwd failure — STOP
and follow the shared real-bug policy: root-cause → small+scoped fix + CI-visible render guard +
deferred release, OR `@pytest.mark.xfail(reason="FWK<NN>: real bug — <one line>", strict=True)` +
leave registry entry KNOWN_GAP (N/A here — no registry entry) + new `PLAN.md` `Next` FWK id +
`ACTION_LOG` entry + morning-report line.

---

## Task 1: Test C — YAML-graph assertion for `ci:` chain + `test:cov:ci` 85% arg (gate-tier)

**Files:** Modify `tests/test_copier_runner.py`. This task goes first because it is gate-tier
(no Docker, runs in CI) and is the cheapest to write and verify.

The M6 assessment states a ci-graph assertion is "already partially present at :3236". That
existing test (`test_render_docs_battery_adds_taskfile_tasks`, line 3236) asserts only
`"docs:build" in ci_section` — it does NOT assert the baseline sub-task order (`lint`,
`test:cov:ci`, `audit`, `openapi:export`) or the 85% argument in `test:cov:ci`. The only
assertion on `ci:` in the baseline render is `assert "ci:" in taskfile` (line 753) — a string
containment check that passes even if all sub-tasks were stripped.

The Taskfile.yml (lines 222–233) renders:

```yaml
  ci:
    desc: Full local CI pre-flight before `task push` (lint, 85% gate, audit, OpenAPI export).
    preconditions:
      - sh: 'if command -v framework >/dev/null 2>&1; then framework integrity; fi'
        msg: "Framework integrity check failed. ..."
    cmds:
      - task: lint
      - task: test:cov:ci
      - task: audit
      - task: openapi:export
      # - task: docs:build   (only with docs battery)
```

And `test:cov:ci` (lines 92–95) renders:

```yaml
  test:cov:ci:
    desc: Combined coverage gate (unit + functional + e2e, >=85%) — the CI gate.
    cmds:
      - bash scripts/coverage.sh 85 unit functional e2e
```

- [ ] **Step 1: Write the test.** Add immediately after
  `test_render_docs_battery_adds_taskfile_tasks` (~line 3247):

```python
def test_render_ci_task_chain_and_85_percent_gate(tmp_path: Path):
    # M6/FWK25 (gate-tier, no Docker): the existing "ci: in taskfile" assertion (line 753)
    # passes even if all sub-tasks are stripped. Assert that:
    # (a) ci.cmds contains lint / test:cov:ci / audit / openapi:export in that order;
    # (b) test:cov:ci's cmd carries the "85" threshold arg (the CI gate is 85%, not 70%).
    # Also asserts the framework-integrity precondition renders in the ci: block.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    tf = yaml.safe_load((dest / "Taskfile.yml").read_text())

    ci_cmds = tf["tasks"]["ci"]["cmds"]
    # Each element is {"task": "<name>"} in go-task v3 YAML.
    ci_task_names = [
        item["task"] if isinstance(item, dict) else item for item in ci_cmds
    ]
    expected_order = ["lint", "test:cov:ci", "audit", "openapi:export"]
    # Assert each sub-task is present and in the correct relative order
    # (extra entries — e.g. docs:build with the docs battery — are allowed after openapi:export).
    indices = {}
    for name in expected_order:
        assert name in ci_task_names, (
            f"ci: task chain is missing '{name}' — dropped/mis-named sub-task "
            f"(ci.cmds = {ci_task_names})"
        )
        indices[name] = ci_task_names.index(name)
    for i in range(len(expected_order) - 1):
        assert indices[expected_order[i]] < indices[expected_order[i + 1]], (
            f"ci: sub-task order wrong: '{expected_order[i]}' must precede "
            f"'{expected_order[i + 1]}' (found indices {indices})"
        )

    # test:cov:ci must carry the 85% threshold (not the 70% pre-commit gate).
    cov_ci_cmds = tf["tasks"]["test:cov:ci"]["cmds"]
    cov_ci_text = " ".join(
        item if isinstance(item, str) else str(item) for item in cov_ci_cmds
    )
    assert "85" in cov_ci_text, (
        f"test:cov:ci cmd does not carry the 85% threshold (got {cov_ci_text!r})"
    )
    assert "scripts/coverage.sh" in cov_ci_text, (
        f"test:cov:ci cmd does not invoke scripts/coverage.sh (got {cov_ci_text!r})"
    )

    # The ci: block must have the framework-integrity precondition (soft check — only fires
    # when the framework CLI is installed; a missing precondition silently skips integrity).
    ci_preconditions = tf["tasks"]["ci"].get("preconditions", [])
    precond_text = " ".join(
        item.get("sh", "") if isinstance(item, dict) else str(item)
        for item in ci_preconditions
    )
    assert "framework integrity" in precond_text, (
        "ci: task is missing the framework-integrity precondition "
        f"(preconditions = {ci_preconditions})"
    )
```

- [ ] **Step 2: Run — expect GREEN.**

  ```bash
  uv run pytest tests/test_copier_runner.py::test_render_ci_task_chain_and_85_percent_gate -q
  ```

  This is a pure render+parse test; no Docker required. If it goes red immediately, the Taskfile
  template does not render the expected chain — that is a candidate real bug.

- [ ] **Step 3: Bite-proof (non-vacuity — flip a non-existent sub-task → RED, no build).**
  Temporarily change one `expected_order` entry to a name that does NOT exist in the rendered
  Taskfile (e.g. `"nonexistent:task"`) — the assertion `assert name in ci_task_names` fires →
  RED. Revert. This proves the assertion is not vacuously true.

  Alternative cheap flip: change `"85"` to `"99"` in the threshold assertion → RED (the template
  renders `85`). Revert.

- [ ] **Step 4: Lint + commit.**

  ```bash
  uv run ruff check tests/test_copier_runner.py
  uv run ruff format --check tests/test_copier_runner.py
  ```

  Then commit per the shared policy (PLAN/ACTION_LOG staged + skip-marker; `git add` then `git
  commit` as SEPARATE calls per [[commit-gate-hook-timing]]).

---

## Task 2: Test A — `task dev:lite` drives the stack (M5)

**Files:** Modify `tests/acceptance/test_rendered_project.py`. Place after
`test_rendered_project_dev_lite_stack_serves_health` (~line 934).

**Key `dev:lite` facts from the template (Taskfile.yml.jinja:30-43):**

- Preconditions: `command -v docker` and `test -f uv.lock` (exactly two — no cert or integrity
  precondition, unlike `dev:`)
- Env: `UID: {sh: id -u}`, `GID: {sh: id -g}` (shell-outs, evaluated by go-task at runtime)
- Cmd: `./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite
  up --build`

`scripts/compose.sh` is the FWK31 PORT_OFFSET wrapper — it calls `exec docker compose "$@"`, so
the task runs `docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite
up --build` (attached, not `-d`). The `_isolate_compose_project` autouse fixture sets all
`*_HOST_PORT` env vars to `"0"` and sets `COMPOSE_PROJECT_NAME`; `_compose_env()` spreads
`os.environ`, so those isolation vars propagate to the `task` subprocess automatically.

**`_compose_host_port` for `task dev:lite`:** the lite profile uses
`-f infra/compose/base.yml -f infra/compose/dev.yml`. Pass `[base, dev]` to
`_compose_host_port(dest, [base, dev], "app", 8000)` — exactly as the existing raw-compose
dev:lite test (line 917) does.

**Tear-down after `task dev:lite`:** because the task runs attached (foreground), the test runs
it as a background `subprocess.Popen`, polls for readiness, asserts, then tears down via raw
`docker compose -f base -f dev --profile lite down -v` with `env=_compose_env()`. The `task`
process will exit once `down` completes (docker signals the compose up loop).

- [ ] **Step 1: Write the negative precondition sub-test first.**

```python
@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task dev:lite precondition fast-fail",
)
def test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock(tmp_path: Path):
    # M5/FWK25 (negative): the dev:lite precondition `test -f uv.lock` should fail fast
    # (non-zero, without starting any containers) when uv.lock is absent. This covers the
    # precondition machinery that the raw-compose dev:lite test never exercises.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # Do NOT run uv lock — leave uv.lock absent so the precondition fires.
    result = subprocess.run(
        ["task", "dev:lite"],
        cwd=dest,
        env=_compose_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, (
        "task dev:lite should have failed fast with a missing uv.lock precondition, "
        f"but exited 0.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The precondition message (Taskfile.yml.jinja:35) says "Run `uv sync` first".
    combined = result.stdout + result.stderr
    assert "uv sync" in combined or "uv.lock" in combined, (
        "task dev:lite failed (non-zero) but did not emit the expected precondition "
        f"message about uv.lock/uv sync:\n{combined}"
    )
```

- [ ] **Step 2: Run the negative test — expect GREEN.**

  ```bash
  uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock -q
  ```

  Non-zero exit + the uv.lock message. If it exits 0 (precondition silently ignored), that is a
  real bug in the Taskfile precondition wiring.

- [ ] **Step 3: Write the positive `task dev:lite` test.**

```python
@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task dev:lite live-stack exercise",
)
def test_rendered_taskfile_dev_lite_target_drives_stack(tmp_path: Path):
    # M5/FWK25: the existing dev:lite test calls raw `docker compose … up` directly, bypassing
    # `task`. Running `task dev:lite` exercises the preconditions (docker + uv.lock), the
    # -f merge order, and the UID/GID env shell-outs. The target calls ./scripts/compose.sh
    # (FWK31 PORT_OFFSET wrapper) in attached mode — run it as a background subprocess, poll
    # /health over the ephemeral host port, assert up, then tear down.
    import json as _json

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    env = _compose_env()
    # task dev:lite runs compose attached; background it so the test can poll.
    proc = subprocess.Popen(
        ["task", "dev:lite"],
        cwd=dest,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # discover the ephemeral host port the isolate-fixture bound to 0.
        # give docker a moment to bind before querying the port mapping.
        port = None
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                port = _compose_host_port(dest, [base, dev], "app", 8000)
                break
            except (subprocess.CalledProcessError, ValueError):
                time.sleep(3)
        assert port is not None, (
            "could not resolve the app ephemeral host port within 120s — "
            "task dev:lite may not have started docker compose"
        )

        # poll /health until 200 (proves the whole task entrypoint: preconditions passed,
        # compose.sh invoked correctly, stack came up with the right -f merge order,
        # UID/GID env reached the container so the bind mount is host-owned).
        body = None
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body = _json.loads(resp.read())
                        break
            except OSError:
                time.sleep(3)
        assert body is not None, (
            f"app did not serve /health 200 within 120s after `task dev:lite` "
            "(port={port}) — precondition, merge order, or UID/GID env regression"
        )
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        proc.terminate()
        # Tear down via raw compose with the same -f list + isolation env.
        subprocess.run(
            ["docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v"],
            cwd=dest,
            env=env,
        )
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 4: Run the positive test — expect GREEN.**

  ```bash
  TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_taskfile_dev_lite_target_drives_stack -q
  ```

  First build ~3 min. If the precondition fires spuriously (docker not in path inside the task
  subprocess), the proc exits immediately — check `proc.stderr.read()`. If the stack never comes
  up, that is a candidate real bug.

- [ ] **Step 5: Bite-proof (the negative precondition test IS the built-in bite-proof).**
  The negative test (`test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock`) already
  proves the positive test depends on `uv.lock` existing (if the precondition were removed,
  the negative test would go RED). No additional flip needed for the positive test.

  Optionally cheap flip: temporarily remove the `uv lock` call in the positive test
  (`# assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0`) → the `uv.lock`
  precondition fires → proc exits non-zero → `port` never resolves → assertion fires → RED.
  Revert. This ties the positive test's GREEN to the `uv lock` call.

- [ ] **Step 6: Lint + commit.**

  ```bash
  uv run ruff check tests/acceptance/test_rendered_project.py
  uv run ruff format --check tests/acceptance/test_rendered_project.py
  ```

  Commit (PLAN/ACTION_LOG staged + skip-marker; `git add` then `git commit` as SEPARATE calls).

---

## Task 3: Test B — `task db:migrate` + `task db:seed`, assert seed rows (M6 live half)

**Files:** Modify `tests/acceptance/test_rendered_project.py`. Place after Task 2's tests.

**Key `db:migrate` and `db:seed` facts from the template (Taskfile.yml.jinja:142-150):**

```yaml
  db:migrate:
    desc: Apply pending Alembic migrations (target DB via APP_DATABASE_URL; see .env.example).
    cmds:
      - uv run alembic upgrade head

  db:seed:
    desc: Load seed data (idempotent — skips if data already exists).
    cmds:
      - uv run python scripts/seed.py
```

Neither target has preconditions. Both delegate to `uv run`. The M6 risk is that `uv run python
scripts/seed.py` resolves `scripts/seed.py` relative to the shell's CWD when `task` is run —
if `task` changes directory internally (it does NOT by default; go-task runs cmds in the
Taskfile's directory, which is `dest`), seed.py's own relative imports/paths may break. The
acceptance test catches this by asserting seeded rows land in the DB.

**Pattern for asserting seed rows:** use `compose exec -T postgres psql` (the FWK20 pattern,
also used in `test_rendered_project_dev_stack_serves_seeded_items`). After `task db:seed` exits,
query the `items` table for a non-zero row count.

**Postgres bring-up:** bring up only `postgres` from the lite profile (raw `docker compose -f
base -f dev --profile lite up -d postgres`). The `db:migrate` and `db:seed` tasks need
`APP_DATABASE_URL` pointing at the ephemeral host port. The rendered project's `.env.example`
sets `APP_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app` — override with the
ephemeral port via `env` on the subprocess calls.

- [ ] **Step 1: Write the test.**

```python
@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task db:migrate + db:seed live exercise",
)
def test_rendered_taskfile_db_targets_seed_rows(tmp_path: Path):
    # M6/FWK25 (live half): no pytest tier calls `task db:migrate` or `task db:seed` — the
    # acceptance tier calls `bash scripts/coverage.sh` (which runs alembic via conftest) and
    # scripts/seed.py is invoked only via entrypoint.sh in the full dev stack. Run the db:
    # targets via `task` against a live compose Postgres, asserting seed rows land. This catches
    # a broken db:seed cwd-from-root (scripts/seed.py path not resolved from dest) or a
    # mis-wired alembic invocation.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    env = _compose_env()
    up = [
        "docker", "compose", "-f", base, "-f", dev, "--profile", "lite",
        "up", "-d", "postgres",
    ]
    down = [
        "docker", "compose", "-f", base, "-f", dev, "--profile", "lite", "down", "-v",
    ]
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        pg_port = _compose_host_port(dest, [base, dev], "postgres", 5432)
        db_url = f"postgresql+psycopg://app:app@localhost:{pg_port}/app"
        task_env = {**env, "APP_DATABASE_URL": db_url}

        # Wait for postgres to be ready (healthcheck is pg_isready; poll via psql).
        ready = False
        deadline = time.time() + 90
        while time.time() < deadline:
            r = subprocess.run(
                [
                    "docker", "compose", "-f", base, "-f", dev, "--profile", "lite",
                    "exec", "-T", "postgres",
                    "psql", "-U", "app", "-d", "app", "-c", "SELECT 1",
                ],
                cwd=dest, env=env, capture_output=True,
            )
            if r.returncode == 0:
                ready = True
                break
            time.sleep(3)
        assert ready, "compose postgres never accepted a psql connection within 90s"

        # task db:migrate — runs `uv run alembic upgrade head` in dest.
        migrate = subprocess.run(
            ["task", "db:migrate"],
            cwd=dest,
            env=task_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert migrate.returncode == 0, (
            "task db:migrate failed:\n" + migrate.stdout + migrate.stderr
        )

        # task db:seed — runs `uv run python scripts/seed.py` in dest.
        # The M6 risk: if go-task resolves scripts/seed.py from a wrong cwd, it fails here.
        seed = subprocess.run(
            ["task", "db:seed"],
            cwd=dest,
            env=task_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert seed.returncode == 0, (
            "task db:seed failed (cwd-from-root regression: scripts/seed.py not found, "
            "or alembic migrations not applied first):\n" + seed.stdout + seed.stderr
        )

        # Assert seed rows actually landed in the DB (not just exit 0 from a no-op).
        count_result = subprocess.run(
            [
                "docker", "compose", "-f", base, "-f", dev, "--profile", "lite",
                "exec", "-T", "postgres",
                "psql", "-U", "app", "-d", "app", "-t", "-c",
                "SELECT COUNT(*) FROM items;",
            ],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
        )
        assert count_result.returncode == 0, (
            "psql row count query failed:\n" + count_result.stdout + count_result.stderr
        )
        row_count = int(count_result.stdout.strip())
        assert row_count > 0, (
            f"task db:seed exited 0 but left 0 rows in the items table — "
            "seed.py ran in the wrong cwd (scripts/seed.py not found relative to dest) "
            "or is silently idempotent-but-empty on a fresh DB"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
```

- [ ] **Step 2: Run — expect GREEN.**

  ```bash
  TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_taskfile_db_targets_seed_rows -q
  ```

  A non-zero exit from `task db:seed` is a candidate real bug (cwd regression or missing
  migrations). A zero exit but zero rows is also a bug — the seed is supposed to be idempotent
  but non-empty on a fresh DB.

- [ ] **Step 3: Bite-proof (cheap — flip the row count assertion → RED without a rebuild).**
  Temporarily change the assertion to `assert row_count == 0` → the test goes RED because
  `db:seed` DID insert rows → proves the assertion is not vacuously true. Revert.

  Alternative: temporarily change `["task", "db:seed"]` to `["task", "db:migrate"]` (runs
  migrate twice, which is a no-op) → `row_count` stays 0 → `assert row_count > 0` fires → RED.
  Revert.

- [ ] **Step 4: Lint + commit.**

  ```bash
  uv run ruff check tests/acceptance/test_rendered_project.py
  uv run ruff format --check tests/acceptance/test_rendered_project.py
  ```

  Commit (PLAN/ACTION_LOG staged + skip-marker).

---

## Task 4: Close-out

- [ ] **Step 1: Full FWK25 run (laptop, `TMPDIR=/var/tmp`).**

  ```bash
  TMPDIR=/var/tmp uv run pytest \
    tests/acceptance/test_rendered_project.py::test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock \
    tests/acceptance/test_rendered_project.py::test_rendered_taskfile_dev_lite_target_drives_stack \
    tests/acceptance/test_rendered_project.py::test_rendered_taskfile_db_targets_seed_rows \
    tests/test_copier_runner.py::test_render_ci_task_chain_and_85_percent_gate \
    -q
  ```

  Expect 4 passed. The two Docker-gated tests must be run serially (they bring up independent
  stacks; the `_isolate_compose_project` autouse fixture gives each its own project namespace and
  ephemeral ports, so they could run concurrently in principle, but the default pytest run is
  serial unless `-n` is passed).

- [ ] **Step 2: Full gate-tier suite stays green.**

  ```bash
  uv run pytest tests/test_copier_runner.py -q
  ```

  The new YAML-graph assertion must not break any existing tests.

- [ ] **Step 3: Final lint.**

  ```bash
  uv run ruff check tests/
  uv run ruff format --check tests/acceptance/test_rendered_project.py tests/test_copier_runner.py
  ```

- [ ] **Step 4: State + commit.** Per the shared policy this is ONE item on `fwk-coverage-batch`;
  defer the whole-branch Opus review to the end of the batch. Tick FWK25 in `PLAN.md` (or move to
  Done when the batch closes), append `ACTION_LOG.md` entries (per `pi-convention.md`), final
  commit with the skip-marker. **No release** (test-only; any forced template fix is deferred +
  flagged).

- [ ] **Step 5: Morning-report line.** Record: FWK25 green / which (if any) of M5/M6 went xfail
  on a real bug + the new FWK id + the `ACTION_LOG` ref.

---

## Self-Review

- **Spec coverage:** M5 (preconditions, -f merge order, UID/GID env driven through `task
  dev:lite`) → Tasks 2 (negative + positive); M6 live half (`task db:migrate` + `task db:seed`,
  seed rows asserted) → Task 3; M6 gate-tier (ci sub-task chain + 85% arg) → Task 1. ✓
- **Forks honored:** `task dev:lite` as background Popen (attached mode) with raw-compose
  teardown (Task 2); single postgres-only bring-up for db: targets (Task 3); YAML parse
  (not regex) for the chain assertion (Task 1, robust against order-insensitive string search). ✓
- **Ephemeral ports:** every host-port access is via `_compose_host_port(dest, files, service,
  container_port)` — no hardcoded published ports. The `_isolate_compose_project` autouse
  fixture sets all `*_HOST_PORT` to `"0"` and these are spread through `_compose_env()` which
  Task 2 and Task 3 both pass to `task` and `docker compose` subprocesses. FWK31-compliant. ✓
- **Docker-gated + local-only:** Tasks 2 and 3 `skipif not _docker_available() or
  shutil.which("task") is None`; Task 1 is gate-tier (no docker). ✓
- **Non-vacuity:** Task 1 — flip `"nonexistent:task"` → RED; Task 2 — negative precondition test
  IS the built-in bite-proof (plus the optional `uv lock` remove); Task 3 — flip `row_count ==
  0` → RED. All flip RED without a rebuild. ✓
- **Registry correctness:** no registry entries flip. Taskfile targets are explicitly out of
  scope for the FWK29 closed-world registry (registry.py:8-10). Do NOT invent keys. ✓
- **No root-residue:** Task 2 (dev:lite, app runs as the host UID — no root bind-mount writes;
  `down -v` drops volumes). Task 3 (postgres-only, no app bind mount; `down -v` drops volumes).
  Neither test writes to the rendered tree from a root-owned container. ✓
- **No template change:** test-only. Any fix forced by a real bug goes through the shared
  real-bug policy (defer release + new FWK id + ACTION_LOG). ✓

### Genuine design forks for the human (could not be fully resolved from code alone)

1. **`task dev:lite` positive test port-discovery timing.** `task dev:lite` runs `./scripts/
   compose.sh … up --build` attached, and `_compose_host_port` calls `docker compose … port
   app 8000`. There is a window between when `task` spawns the compose up and when docker binds
   the host port. The plan polls `_compose_host_port` in a retry loop (up to 120s). If the
   `compose.sh` PATH resolution fails (go-task's subprocess shell can't find `./scripts/
   compose.sh` from `cwd=dest`), `task` exits immediately — the `port` loop will hit the 120s
   timeout. **If this bites:** the fix is to confirm `scripts/compose.sh` is executable and that
   go-task resolves `./` relative to the Taskfile's directory (it does, per go-task docs), OR to
   fall back to `["task", "--summary", "dev:lite"]` to confirm the task is reachable before
   spawning Popen. The plan does not add that fallback pre-emptively — it would complicate the
   test. Raise as a real bug if the Popen timeout fires with no port binding.

2. **`task db:seed` `APP_DATABASE_URL` injection mechanism.** `db:seed` runs `uv run python
   scripts/seed.py`. `seed.py` likely reads `APP_DATABASE_URL` from the environment via
   `Settings()` (pydantic-settings). Task 3 passes `APP_DATABASE_URL` in `task_env` (the env
   dict) — go-task propagates env to child processes by default. If the generated `seed.py` reads
   the URL from a `.env` file (python-dotenv) and IGNORES the env var, the task will try to
   connect to `localhost:5432` (the .env default) — which MAY accidentally work if the isolation
   fixture has not fully zero'd the port, or MAY fail. **If this bites:** confirm whether the
   rendered `Settings` class precedence (env var overrides .env file) is correct. This is expected
   to work (pydantic-settings prioritizes env vars over .env by default), but it is the M6 risk
   that the live test actually catches.

3. **`task dev` (full stack, with certs) is NOT covered by this plan.** `task dev` has four
   preconditions (docker + cert file + uv.lock + framework-integrity), requires `task certs`
   first, and starts Traefik + observability — a significantly heavier setup than `dev:lite`. The
   M5 assessment names `dev` and `dev:lite` as the gap. This plan covers `dev:lite` only,
   justified by cost (one heavy dev-stack bring-up per test, and `dev` is already exercised by
   `test_rendered_project_dev_stack_routes_through_traefik` which calls raw compose with the same
   `-f` list). **If the human wants `task dev` also covered:** add a third acceptance test that
   calls `task certs` first, then `task dev` as a background Popen, polls the ephemeral HTTPS
   port through Traefik (reusing `_mkcert_ssl_context` from FWK24), and tears down. Accept the
   additional ~5 min test runtime. This plan does not include it to stay within the M5 scope.

### Anticipated real bugs (per the shared real-bug policy)

- **`task dev:lite` precondition over-fires or under-fires.** If `test -f uv.lock` is checked
  relative to go-task's internal working directory rather than `cwd=dest`, the precondition may
  always-pass or always-fail regardless of whether `uv.lock` exists. The negative precondition
  test (Task 2 Step 1) catches this: if the precondition does NOT fire on a missing `uv.lock`,
  the test goes RED. Expected to be correct (go-task runs Taskfile from its directory); flagged
  as a candidate.

- **`task dev:lite` UID/GID env not passed to compose / compose.sh ignores it.** The Taskfile
  sets `env.UID` / `env.GID` via `sh:` shell-outs, evaluated by go-task. If go-task's
  subprocess shell resolves `id -u`/`id -g` differently inside the test runner (e.g., in a
  Docker-in-Docker environment), the containers may start as root instead of the host UID. The
  test does not explicitly assert UID/GID (checking container user requires `docker inspect`
  introspection or a `/whoami` route), but a root-owned bind-mount write on a subsequent `tmp_path`
  cleanup would manifest as a permission error. If that happens, the issue is UID/GID propagation.
  Add a defensive chown-reclaim in `finally` if cleanup errors appear in CI.

- **`ci:` sub-task chain mis-rendered for a non-docs battery render.** The YAML-graph assertion
  (Task 1) uses a baseline render (`DATA`, no docs battery). If the Taskfile.yml.jinja renders
  different cmds for other battery combinations (e.g., if `workers` adds a task to the `ci:` cmds
  list in a non-obvious way), the baseline assertion still holds. If a future template change drops
  `openapi:export` from the ci chain or reorders sub-tasks, Task 1 goes RED — exactly the M6
  silent-failure it is designed to catch.

- **`task db:seed` exits 0 but inserts zero rows.** If `scripts/seed.py` is idempotent and the
  generated project's Alembic baseline creates a pre-populated table, `seed.py` might see rows
  already present and skip. The assertion `row_count > 0` catches this only if the test DB is
  truly empty (fresh compose postgres + fresh `db:migrate` + fresh `db:seed`). The compose
  bring-up is `-d postgres` against a fresh volume (no pre-existing data) so this should not
  occur; flagged as a low-probability edge case if the `items` table is pre-populated by a
  migration.

- **`task db:migrate` fails because `alembic.ini` is not found from `cwd=dest`.** Alembic
  resolves `alembic.ini` from the process CWD. go-task runs `uv run alembic upgrade head` with
  CWD = the Taskfile's directory = `dest`. The rendered `alembic.ini` is at `dest/alembic.ini`.
  This should work; but if a template change moves `alembic.ini` or if `uv run` changes directory,
  the migration fails. Task 3 catches it immediately on `migrate.returncode != 0`.

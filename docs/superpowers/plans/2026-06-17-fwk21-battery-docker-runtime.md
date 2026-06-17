# FWK21 — Battery Docker runtime stages, built + run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close coverage gaps **H5** (claudesubscriptioncli FULL runtime image built + run) and **H6** (react SPA actually served from the runtime image) from `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md` — the "built but only `returncode==0` asserted" shape.

**Architecture:** Approach **A (standalone, DB-less)**. A shared context-manager helper `docker run`s a built image on a free host port with `APP_RUN_MIGRATIONS=false` (so the entrypoint skips alembic/seed and execs uvicorn — the app boots without Postgres; confirmed: every `Settings` field has a default, and `lifespan` "must not require the DB to be reachable"). It polls `/heartbeat` (a DB-less `PlainTextResponse` route) until 200, then the test asserts the battery-specific thing: for H5 a 200 on `/heartbeat` proves the runtime image boots with `litellm-claude-cli` importable (`create_app` calls `register_claude_cli()`); for H6 a GET `/` returning the SPA HTML (`id="root"`) proves `/app/frontend/dist` landed and is served by the StaticFiles mount.

**Tech Stack:** Python, pytest, Docker (BuildKit), `tests/acceptance/test_rendered_project.py` (docker-gated, local-only), FWK29 registry (`tests/runtime_coverage/registry.py`).

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add the shared helper `_run_image_serving`, add the new H5 test, extend the existing H6 test (`test_rendered_react_battery_passes`).
- **Modify** `tests/runtime_coverage/registry.py` — flip `docker-stage:Dockerfile:frontend-build` → EXERCISED; re-point `service:dev.yml:frontend` to FWK24 (the dev Vite-server live-serve is a separate, lower-value gap H6 does not cover).
- **Modify** `PLAN.md` + `ACTION_LOG.md` — per the working agreement (required before commit).

No template-payload change is expected (test-only). If a TDD step surfaces a real template bug (as FWK20/H4 did), stop and treat it per `superpowers:systematic-debugging`; that would add a template fix + a deferred release decision.

---

## Task 1: Shared `_run_image_serving` helper

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py` (imports near top; helper beside `_compose_host_port`)

- [ ] **Step 1: Add imports**

At the top of the file, add (the file already imports `os`, `socket`, `subprocess`, `time`, `urllib.request`):

```python
from collections.abc import Iterator
from contextlib import contextmanager
```

- [ ] **Step 2: Add the helper** (place it after `_compose_host_port`, before the `_isolate_compose_project` fixture)

```python
@contextmanager
def _run_image_serving(
    image: str, *, extra_env: dict[str, str] | None = None, ready_path: str = "/heartbeat"
) -> Iterator[str]:
    """`docker run -d` the built image on a free host port with migrations disabled, poll
    <ready_path> until 200, and yield the base URL. DB-less: APP_RUN_MIGRATIONS=false makes the
    entrypoint skip alembic/seed and exec uvicorn; every Settings field has a default and the
    app's lifespan does not require the DB. Removes the container on exit; on not-ready it raises
    with `docker logs` attached so a boot crash is diagnosable."""
    port = _free_tcp_port()
    env_args = ["-e", "APP_RUN_MIGRATIONS=false"]
    for k, v in (extra_env or {}).items():
        env_args += ["-e", f"{k}={v}"]
    run = subprocess.run(
        ["docker", "run", "-d", "-p", f"{port}:8000", *env_args, image],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run failed for {image}:\n{run.stderr}"
    cid = run.stdout.strip()
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}{ready_path}", timeout=3) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass
            time.sleep(2)
        if not ready:
            logs = subprocess.run(
                ["docker", "logs", cid], capture_output=True, text=True
            )
            raise AssertionError(
                f"{image} did not serve {ready_path} within 60s\n"
                f"--- docker logs ---\n{logs.stdout}\n{logs.stderr}"
            )
        yield base
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
```

- [ ] **Step 3: Lint the helper** (no behavior test yet — it is exercised by Tasks 2–3)

Run: `uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format --check tests/acceptance/test_rendered_project.py`
Expected: PASS (format may reformat — re-run `ruff format` if so).

---

## Task 2: H5 — claudesubscriptioncli FULL runtime image built + run

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py` (new test directly after `test_rendered_claudesubscriptioncli_docker_builder_stage_builds`, ~line 428)

- [ ] **Step 1: Write the test**

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: builds + runs the claudesubscriptioncli FULL runtime image",
)
def test_rendered_claudesubscriptioncli_docker_runtime_serves_heartbeat(tmp_path: Path):
    # H5/FWK21: the builder-stage test above builds only `--target builder`; nothing builds the
    # FULL runtime image or runs it, so a runtime-only break in the litellm-claude-cli git dep
    # (a COPY --from=builder interaction, or a runtime import) ships green. Build the default
    # (runtime) target and run it: create_app calls register_claude_cli(), so a 200 on /heartbeat
    # proves the dep is importable in the runtime image (the app booted past create_app).
    data = {**DATA, "batteries": resolve(["claudesubscriptioncli"])}
    dest = tmp_path / "demo"
    render_project(dest, data)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    image = "fwk-claudesub-runtime-test"
    build = subprocess.run(
        ["docker", "build", "-f", "infra/docker/Dockerfile", "-t", image, "."],
        cwd=dest,
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_BUILDKIT": "1"},
    )
    try:
        assert build.returncode == 0, (
            "claudesubscriptioncli runtime image build failed:\n"
            + build.stdout
            + build.stderr
        )
        with _run_image_serving(image) as base:
            with urllib.request.urlopen(f"{base}/heartbeat", timeout=5) as resp:
                assert resp.status == 200, (
                    f"runtime image did not serve /heartbeat 200 (got {resp.status})"
                )
    finally:
        subprocess.run(["docker", "rmi", "-f", image], capture_output=True)
```

- [ ] **Step 2: Run it — expect GREEN** (the template is correct; this is a coverage test)

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_claudesubscriptioncli_docker_runtime_serves_heartbeat -q`
Expected: PASS (build ~2–4 min first time; cached after). If it FAILS with a boot crash, read the attached `docker logs` and follow systematic-debugging — a real runtime regression would be a genuine find.

- [ ] **Step 3: Bite-proof (cheap, no rebuild): point the ready check at a 404**

Temporarily pass `ready_path="/definitely-not-a-route"` to `_run_image_serving` and re-run.
Expected: FAIL — the helper raises "did not serve … within 60s" with docker logs. This proves the readiness gate truly depends on the served response (the GET isn't vacuous). Revert.

---

## Task 3: H6 — react SPA actually served from the runtime image

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py` (extend `test_rendered_react_battery_passes`, after the existing `assert build.returncode == 0` at ~line 1834)

- [ ] **Step 1: Append the run-and-serve assertion** to the existing test (the image `demo-react:ci` is already built earlier in the test)

```python
    # H6/FWK21: COPY succeeds whenever the source exists, so a wrong dist path or empty build
    # still builds green. Run the built image and request the served SPA to prove /app/frontend/dist
    # landed and is served by the StaticFiles mount (main.py), not merely that the build exited 0.
    with _run_image_serving("demo-react:ci") as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as resp:
            body = resp.read().decode()
            assert resp.status == 200, f"served SPA returned {resp.status}, not 200"
            assert 'id="root"' in body, (
                f"served / is not the SPA shell (no root div):\n{body[:500]}"
            )
```

- [ ] **Step 2: Run it — expect GREEN**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_react_battery_passes -q`
Expected: PASS. (Needs `npm` for the typecheck/test branch; the build + run always execute.)

- [ ] **Step 3: Bite-proof (strong, the point of H6): break the served artifact**

Render react to a scratch dir, build the image, then rebuild with the Dockerfile's react `COPY --from=frontend-build /app/frontend/dist /app/frontend/dist` pointed at a non-existent `dist` subpath (or set `serve_spa=false` via `extra_env={"APP_SERVE_SPA": "false"}`) and confirm the `id="root"` assertion goes RED while the build still exits 0. This proves "build green ≠ SPA served." Use the env variant (`APP_SERVE_SPA=false`) for a no-rebuild proof: the app boots (/heartbeat 200) but `/` no longer serves the shell → the `id="root"` assert fails. Revert.

---

## Task 4: FWK29 registry reconciliation

**Files:**
- Modify: `tests/runtime_coverage/registry.py`

- [ ] **Step 1: Flip `docker-stage:Dockerfile:frontend-build` → EXERCISED**

Replace its `_KG` + evidence with:

```python
        "docker-stage:Dockerfile:frontend-build",
        "infra/docker/Dockerfile:13-22",
        _EX,
        # H6/FWK21: the react runtime image is built AND run; GET / asserts the SPA shell
        # (id="root") served from the COPYd /app/frontend/dist, not just returncode==0.
        "test_rendered_react_battery_passes",
```

- [ ] **Step 2: Re-point `service:dev.yml:frontend`** (H6 covers the *runtime image* SPA serve, NOT the dev Vite-server compose service)

```python
        "service:dev.yml:frontend",
        "infra/compose/dev.yml",
        _KG,
        # H6/FWK21 closed the runtime-image SPA serve (test_rendered_react_battery_passes). The
        # residual is the dev Vite dev-server compose service serving the SPA live over HTTP —
        # lower value, folded into the react live-frontend work.
        "FWK24 dev Vite frontend service never asserted to serve the SPA live over HTTP",
```

- [ ] **Step 3: Note — no registry change for H5.** The generic `docker-stage:Dockerfile:runtime` is already EXERCISED (dev:lite). H5 adds battery-depth on that stage (defense-in-depth), not a new enumerable surface.

- [ ] **Step 4: Run the completeness suite**

Run: `uv run pytest tests/runtime_coverage/ -q`
Expected: PASS (9 tests) — `test_exercised_entries_name_an_existing_test` confirms `test_rendered_react_battery_passes` exists; `test_known_gap_entries_link_a_task` confirms the `FWK24 …` evidence starts with an FWK id.

---

## Task 5: Gates, state, commit, PR

- [ ] **Step 1: Lint/format the changed test files**

Run: `uv run ruff check tests/ && uv run ruff format --check tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py`
Expected: PASS.

- [ ] **Step 2: Confirm the two acceptance tests both green in one run**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -k "claudesubscriptioncli_docker_runtime_serves_heartbeat or test_rendered_react_battery_passes" -q`
Expected: 2 passed.

- [ ] **Step 3: Branch-end review** — dispatch an **Opus** code-quality + spec review of the diff (review-model policy; independent eyes). Address findings.

- [ ] **Step 4: Update `PLAN.md`** (move FWK21 to Done) **and append `ACTION_LOG.md`** entries (per `pi-convention.md`).

- [ ] **Step 5: Commit on a feature branch + open PR** (master is protected; separate `git add` then commit per the commit-gate hook). No release (test-only).

---

## Self-Review

- **Spec coverage:** H5 → Task 2; H6 → Task 3; the "built but not run" shape → both. Helper → Task 1. Registry reconciliation → Task 4. ✓
- **Placeholders:** none — every step has concrete code/commands. ✓
- **Type/name consistency:** `_run_image_serving(image, *, extra_env=None, ready_path="/heartbeat")` is defined in Task 1 and called identically in Tasks 2–3; image tags `fwk-claudesub-runtime-test` / `demo-react:ci` consistent; registry keys match the live `registry.py` entries. ✓
- **Non-vacuity:** H5 asserts a 200 the helper already gated on (boot proves the dep importable); H6 asserts `id="root"` in the *read* body (Step-3 bite-proofs prove both assertions depend on the real response). ✓

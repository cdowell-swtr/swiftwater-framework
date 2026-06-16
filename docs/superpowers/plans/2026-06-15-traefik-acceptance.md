# Traefik Cert+Route Acceptance Test (FWK8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **⚠ Local-only test.** The docker dev-stack acceptance tier is `--ignore`d in CI; this test runs on **this box** (has docker + mkcert + go-task). Branch `fwk8-traefik-acceptance` (already created off master). **No release** — `tests/`-only, not in the wheel.

**Goal:** Add one docker-acceptance test that routes a TLS-verified request **through** Traefik to the app, closing the gap that hid the `traefik v3.1` → Docker-27 break and exercising the real `task certs`/mkcert cert path (the incident's origin).

**Architecture:** A single regression-guard test in `tests/acceptance/test_rendered_project.py`: render → `task certs` (mkcert) → bring up the full `dev` profile → poll `https://{slug}.localhost/health` with TLS verification **on** against the mkcert root CA → assert 200. The bug is already fixed (v3.6), so the test passes immediately; a separate validation step proves it *bites* by temporarily downgrading Traefik.

**Tech Stack:** pytest, docker compose, Traefik (docker provider), mkcert, go-task. Spec: `docs/superpowers/specs/2026-06-15-traefik-docker-provider-acceptance-design.md`.

---

## File Structure

- Modify: `tests/acceptance/test_rendered_project.py` — add `import ssl` + the new test.
- Framework source: `PLAN.md`, `ACTION_LOG.md` (FWK8 → Done).
- No template/CLI/wheel changes → no release.

---

## Task 1: The cert+route regression-guard test

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Add `import ssl`** to the imports block (after `import shutil`, keep alphabetical-ish order — the file already imports json/os/shutil/subprocess/time/urllib.request).

- [ ] **Step 2: Add the test** (place it near the other `dev_stack` tests, e.g. after `test_rendered_project_dev_lite_stack_serves_health`):
```python
@pytest.mark.skipif(
    not _docker_available()
    or shutil.which("mkcert") is None
    or shutil.which("task") is None,
    reason="docker + mkcert + go-task required (local-only dev-stack tier)",
)
def test_rendered_project_dev_stack_routes_through_traefik(tmp_path: Path):
    # Regression guard for the v3.1->Docker-27 break AND the mkcert cert path (the incident's
    # origin). The --profile dev tests START Traefik but never route THROUGH it; this one does.
    # A *verified* 200 proves the whole chain: `task certs`/mkcert issued a valid cert -> it
    # mounted -> tls.yml loaded it -> Traefik served it for *.localhost and the client TRUSTED
    # it -> AND the docker provider discovered the labeled app and proxied to :8000.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    certs = subprocess.run(["task", "certs"], cwd=dest, capture_output=True, text=True)
    assert certs.returncode == 0, "task certs failed:\n" + certs.stdout + certs.stderr

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]

    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    try:
        caroot = subprocess.run(
            ["mkcert", "-CAROOT"], capture_output=True, text=True
        ).stdout.strip()
        ctx = ssl.create_default_context(cafile=str(Path(caroot) / "rootCA.pem"))
        # Route through Traefik's websecure (443). The cert SAN is *.localhost (mkcert),
        # so check_hostname validates {slug}.localhost too. .localhost -> loopback.
        url = f"https://{DATA['project_slug']}.localhost/health"
        deadline = time.time() + 120
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:  # ssl.SSLError (cert-verify) + connection errors, while it settles
                time.sleep(3)
        assert body is not None, (
            "no TLS-verified 200 through Traefik within 120s — docker-provider routing or the "
            "mkcert cert chain (task certs / mount / tls.yml) is broken"
        )
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        subprocess.run(down, cwd=dest, env=_compose_env())
```

- [ ] **Step 3: Lint.** `uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format --check tests/acceptance/test_rendered_project.py` (run `ruff format` if it wants changes).

- [ ] **Step 4: Run it → expect PASS** (the codebase is on Traefik v3.6, which works on Docker 29):
Run: `TMPDIR=/var/tmp uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_stack_routes_through_traefik" -q`
Expected: `1 passed` (in ~1–2 min — full dev stack + build). If it fails, the dev stack or cert chain has a real problem — debug with [[systematic-debugging]] (inspect `docker compose … logs traefik` / `app`), do not weaken the assertion.

- [ ] **Step 5: Commit** (controller; stage with PLAN/ACTION_LOG):
```bash
git add tests/acceptance/test_rendered_project.py PLAN.md ACTION_LOG.md
```
then separately: `git commit -m "test(fwk8): route a TLS-verified request through Traefik (dev stack)"`

---

## Task 2: Prove the guard bites (validation — no committed change)

> A regression test that can't fail is worthless. Demonstrate the test would have caught the incident, then revert. **Nothing here is committed.**

- [ ] **Step 1: Reproduce the routing break.** Temporarily edit the template's Traefik image to a version that fails on Docker 27+: in `src/framework_cli/template/infra/compose/dev.yml.jinja`, change `image: traefik:v3.6` → `image: traefik:v3.5` (memory: v3.2–v3.5 do NOT fix the API-version break; v3.6 does).
Run: `TMPDIR=/var/tmp uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_stack_routes_through_traefik" -q`
Expected: **FAIL** — "no TLS-verified 200 … within 120s" (Traefik starts but its docker provider can't negotiate the Docker API → no route). This proves the test catches the v3.1→Docker-27 class. Confirm the cause: `docker compose … --profile dev logs traefik` shows the `"client version … too old"` / provider error (run the stack manually in a scratch render if you want to see it).

- [ ] **Step 2: Revert** the image back to `traefik:v3.6`. `git diff src/framework_cli/template/infra/compose/dev.yml.jinja` → empty (no change staged/left).

- [ ] **Step 3: (cert-surface bite — by construction)** Note in the report: the cert surface is load-bearing because `urlopen` uses `cafile=mkcert rootCA` with `check_hostname` on — if `task certs` were skipped or the mount/`tls.yml` broke, Traefik would serve a non-mkcert/default cert and every poll would raise `ssl.SSLError` → the test fails at the deadline. (No separate edit needed; the verify-ON design proves it.)

- [ ] **Step 4: Re-run → PASS** to confirm the revert is clean:
Run: `TMPDIR=/var/tmp uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_stack_routes_through_traefik" -q` → `1 passed`.

---

## Task 3: Finalize (no release)

- [ ] **Step 1: Guard against a flaky-on-first-run.** Re-run the test once more clean to confirm it's stable (the dev stack settle time is the main flake risk; 120s deadline should be ample). If it flaked on timing, bump the deadline — do not skip the assertion.
- [ ] **Step 2: Confirm no wider regression.** The change is test-only; `uv run ruff check . && uv run ruff format --check .` clean. (No need to run the full suite — one added test, no source change.)
- [ ] **Step 3: PLAN/ACTION_LOG.** Move FWK8 → Done; append a completion entry noting the bite-validation result (v3.5 → FAIL, v3.6 → PASS). Commit.
- [ ] **Step 4: Finish the branch** ([[finishing-a-development-branch]]): push `fwk8-traefik-acceptance`, open one PR, confirm `gate`/`build`/`render-complete` green (these do **not** run the local-only test — they prove the rest of the repo is unaffected), squash-merge. **No tag / no release** (test-only). Grep `master` post-merge for the new test name ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** the cert+route chain (Task 1 — `task certs` → dev up → verify-on route) · local-only / skipif docker+mkcert+task (Task 1 Step 2 decorator) · verify-ON against the mkcert root CA (Task 1) · the "bite" proof for the routing surface (Task 2) + the cert surface by construction (Task 2 Step 3) · no release (Task 3 Step 4). All spec sections map to a task.
- **Type/name consistency:** `test_rendered_project_dev_stack_routes_through_traefik`; uses existing `DATA`, `_compose_env()`, `_docker_available()`, `render_project`; new `import ssl`; `ssl.create_default_context(cafile=…)` + `urllib.request.urlopen(url, context=ctx)` — consistent.
- **No placeholders:** the test is complete; the bite-validation uses a concrete `v3.6→v3.5` edit + revert.
- **CI note:** the PR's required checks don't run this test (acceptance is CI-ignored); the proof is the local PASS + the local bite-validation, recorded in ACTION_LOG.

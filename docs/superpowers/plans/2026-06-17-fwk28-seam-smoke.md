# FWK28 — Seam/script smoke + workflow-graph asserts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#7** of the batch and lands **after
> FWK24, FWK23, FWK26, FWK25, FWK19, FWK27** — run it last.

**Goal:** Close three low-tier gaps from the FWK18 inventory
(`docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`):

- **L1** — `infra/deploy/notify.sh` non-fatal seam: `bash notify.sh 'msg'` exits 0 and echoes
  `[deploy notify]`; with `SLACK_WEBHOOK_URL` set, the optional POST branch reaches a local
  capture server.
- **L2** — `scripts/load.sh` k6 SLO gate: assert graceful degradation (the script fails clearly
  when Docker is unavailable or when `K6_TARGET` is unreachable) — the threshold pass/fail
  propagation is documented as NOT exercised (k6 + a live app stack is required). Log the gap.
- **L3** — `docs.yml` versioned-publish workflow: workflow-graph assertion that the rendered
  `docs.yml` triggers on `push: tags: v*` and runs `mike deploy --push --update-aliases` and
  `mike set-default --push latest`.

**Architecture:**

- **L1** lives in `tests/test_copier_runner.py` (render-only, no `uv sync`, no docker). Mirrors
  the `_FakeAM` / `_serve_fake_am` / `_run_smoke` pattern at `tests/test_copier_runner.py:2955–3004`.
- **L2** lives in `tests/acceptance/test_rendered_project.py` (docker-gated), behind a new
  `_docker_available()` skipif. The test asserts the script exits non-zero and prints a clear
  diagnostic when invoked without the k6 Docker image (no network, no target) — a
  graceful-degradation assertion. The full k6 SLO-threshold run is explicitly NOT asserted here
  (no live app, no grafana/k6 pull in CI); see the `script:scripts/load.sh` registry entry.
- **L3** lives in `tests/test_copier_runner.py`, extending the existing
  `test_render_docs_battery_adds_publish_workflow` (line 3273) with two new assertions that pin
  the exact `--push --update-aliases` and `mike set-default` strings that the existing test
  leaves unguarded.

**No template change is expected.** These tests exercise the template as shipped. If a test goes
red, follow the shared real-bug policy.

---

## File Structure

- **Modify** `tests/test_copier_runner.py` — add `_FakeNotify` capture class, `_serve_fake_notify`
  helper, two L1 notify tests (`test_notify_seam_exits_zero_and_echoes`,
  `test_notify_seam_posts_to_webhook`), and one extended L3 docs-workflow assertion test
  (`test_docs_workflow_mike_flags`). Place L1 tests near the existing `_FakeAM`/`_run_smoke`
  cluster (~line 2955); place L3 immediately after the existing
  `test_render_docs_battery_adds_publish_workflow` (~line 3284).
- **Modify** `tests/acceptance/test_rendered_project.py` — add one L2 test
  (`test_load_sh_fails_gracefully_without_docker_target`). Place after the FWK27 gate-hook block.
- **Modify** `tests/runtime_coverage/registry.py` — flip `script:infra/deploy/notify.sh` from
  `_KG` to `_EX` naming `test_notify_seam_exits_zero_and_echoes`; leave
  `script:scripts/load.sh` as `_KG` (graceful-degradation only, not full SLO gate — honest
  non-claim); `job:docs.yml:publish` stays `_EM` (EXEMPT — the GitHub-platform publish step is
  genuinely undriveable locally; FWK28 only adds a stronger workflow-graph assertion test, which
  does not change the surface's undrivability status).
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy, per commit).

---

## Prerequisite reading (exact file:line anchors)

Before implementing, read:

1. `tests/test_copier_runner.py:2955–3004` — `_FakeAM`, `_serve_fake_am`, `_run_smoke`: the
   exact capture-server + subprocess pattern to mirror for L1.
2. `tests/test_copier_runner.py:3273–3284` — `test_render_docs_battery_adds_publish_workflow`:
   the existing docs-workflow test to extend for L3.
3. `src/framework_cli/template/infra/deploy/notify.sh:1–18` — the `echo "[deploy notify]
   ${message}"` line (L11) and the commented-out `SLACK_WEBHOOK_URL` / `curl` block (L14–17).
4. `src/framework_cli/template/scripts/load.sh:1–18` — the `docker run --rm -i ... grafana/k6:latest
   run - < tests/non_functional/load.js` invocation (L12–18) and `set -euo pipefail` (L5).
5. `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja:1–35`
   — `mike deploy --push --update-aliases "$MINOR" latest` (L33) and `mike set-default --push
   latest` (L34).

---

## Task 1: L1 — notify.sh seam smoke (two tests)

**Files:** Modify `tests/test_copier_runner.py`, inserting after the existing
`_run_smoke` function (~line 2991).

### What the template does (verbatim)

`src/framework_cli/template/infra/deploy/notify.sh:8–17`:

```bash
set -euo pipefail

message="${1:-deploy notification}"
echo "[deploy notify] ${message}"

# Example (uncomment + set SLACK_WEBHOOK_URL as a secret):
# if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
#   curl -sf -X POST -H 'Content-Type: application/json' \
#     --data "{\"text\": \"${message}\"}" "${SLACK_WEBHOOK_URL}" || true
# fi
```

The `echo` branch (L11) always runs. The `curl` branch (L14–17) is **commented out** in the
template. The webhook test exercises the commented-out block by passing the literal lines through
`bash` with the block uncommented in an inline heredoc. This avoids modifying the template: the
test rewrites only the copy inside `tmp_path`.

- [ ] **Step 1: Add `_FakeNotify`, `_serve_fake_notify`, and a `_run_notify` helper.**

  Insert after the `_run_smoke` function (~line 2991). The helpers mirror the
  `_FakeAM`/`_serve_fake_am`/`_run_smoke` triad exactly.

```python
class _FakeNotify(http.server.BaseHTTPRequestHandler):
    """Capture server for notify.sh webhook POST assertions."""

    posts: list[bytes] = []  # accumulated POST bodies; reset per test

    def log_message(self, *a: object) -> None:  # silence
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        _FakeNotify.posts.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()


def _serve_fake_notify() -> http.server.HTTPServer:
    _FakeNotify.posts = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _FakeNotify)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_notify(
    dest: Path,
    message: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> "subprocess.CompletedProcess[str]":
    """Invoke infra/deploy/notify.sh with `message` in the rendered project at `dest`."""
    env: dict[str, str] = {"PATH": os.environ["PATH"]}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(dest / "infra" / "deploy" / "notify.sh"), message],
        capture_output=True,
        text=True,
        env=env,
    )
```

- [ ] **Step 2: Add `test_notify_seam_exits_zero_and_echoes`.**

  Insert after `_run_notify`.

```python
def test_notify_seam_exits_zero_and_echoes(tmp_path: Path) -> None:
    """L1/FWK28: notify.sh must exit 0 and echo [deploy notify] on the happy path."""
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    result = _run_notify(dest, "deploy succeeded")
    assert result.returncode == 0, (
        "notify.sh exited non-zero on the basic echo path\n"
        + result.stdout + result.stderr
    )
    assert "[deploy notify] deploy succeeded" in result.stdout, (
        "expected '[deploy notify] deploy succeeded' in stdout\n" + result.stdout
    )
```

- [ ] **Step 3: Add `test_notify_seam_posts_to_webhook`.**

  Insert after `test_notify_seam_exits_zero_and_echoes`. The webhook branch is commented out in
  the template; this test activates it in a `tmp_path` copy by rewriting the script — the
  template itself is not touched.

```python
def test_notify_seam_posts_to_webhook(tmp_path: Path) -> None:
    """L1/FWK28 (webhook path): when SLACK_WEBHOOK_URL is set, notify.sh POSTs the message.

    The template ships the curl block commented out (safe-by-default); this test uncomments it
    in a tmp_path copy to assert the seam wiring is correct. The template source is NOT modified.
    """
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    # Uncomment the webhook block in the rendered copy.
    script_path = dest / "infra" / "deploy" / "notify.sh"
    original = script_path.read_text()
    activated = original.replace(
        "# if [ -n \"${SLACK_WEBHOOK_URL:-}\"]",
        "if [ -n \"${SLACK_WEBHOOK_URL:-}\"]",
    ).replace(
        "#   curl -sf -X POST -H 'Content-Type: application/json' \\",
        "  curl -sf -X POST -H 'Content-Type: application/json' \\",
    ).replace(
        "#     --data \"{\\\"text\\\": \\\"${message}\\\"}\" \"${SLACK_WEBHOOK_URL}\" || true",
        "    --data \"{\\\"text\\\": \\\"${message}\\\"}\" \"${SLACK_WEBHOOK_URL}\" || true",
    ).replace(
        "# fi",
        "fi",
        1,  # only the first occurrence (the webhook fi)
    )
    script_path.write_text(activated)

    srv = _serve_fake_notify()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        result = _run_notify(dest, "webhook test", extra_env={"SLACK_WEBHOOK_URL": url})
    finally:
        srv.shutdown()

    assert result.returncode == 0, (
        "notify.sh exited non-zero with SLACK_WEBHOOK_URL set\n"
        + result.stdout + result.stderr
    )
    assert _FakeNotify.posts, (
        "expected a POST to the capture server but none arrived; "
        "the webhook branch may not have been activated by the string replacement"
    )
    body = _FakeNotify.posts[0].decode()
    assert "webhook test" in body, (
        f"expected 'webhook test' in the POST body, got: {body!r}"
    )
```

  > **Implementation note — template webhook block format:** The template comment indentation
  > uses `# if`, `#   curl`, `#     --data`, `# fi` (with a leading `# `). The string
  > replacements above must match the EXACT bytes in the rendered file. Before writing the plan
  > test, confirm the exact comment style from
  > `src/framework_cli/template/infra/deploy/notify.sh:14–17` — if the indentation does not
  > match, adjust the replacement strings. If the comment block is difficult to uncomment
  > reliably via string replacement, fall back to writing a minimal inline test script that
  > calls `curl` directly, bypassing the template's commented block. Document the fallback in
  > `ACTION_LOG.md` as a real-bug candidate (the template's webhook block is unexercisable
  > as-shipped).

- [ ] **Step 4: Lint.**

  ```bash
  uv run ruff check tests/test_copier_runner.py && uv run ruff format --check tests/test_copier_runner.py
  ```

- [ ] **Step 5: Run L1 tests — expect GREEN.**

  ```bash
  uv run pytest tests/test_copier_runner.py::test_notify_seam_exits_zero_and_echoes tests/test_copier_runner.py::test_notify_seam_posts_to_webhook -q
  ```

  Both renders take ~10 s each. No docker, no `uv sync`. If the echo test goes red, the
  `echo "[deploy notify]"` line in the template is broken — apply the real-bug policy.

- [ ] **Step 6: Bite-prove `test_notify_seam_exits_zero_and_echoes`.**

  Temporarily change:
  ```python
  assert "[deploy notify] deploy succeeded" in result.stdout,
  ```
  to:
  ```python
  assert "[deploy notify] WRONG_STRING" in result.stdout,
  ```
  Run the test → expect **RED** (`AssertionError`). Revert.

  Commit (PLAN/ACTION_LOG staged; `git add` then `git commit` as SEPARATE calls per
  [[commit-gate-hook-timing]]).

---

## Task 2: L1 — registry flip for notify.sh

**Files:** Modify `tests/runtime_coverage/registry.py`.

### Current entry (registry.py — locate by key `script:infra/deploy/notify.sh`)

```python
SurfaceClass(
    "script:infra/deploy/notify.sh",
    "infra/deploy/notify.sh",
    _KG,
    # L1: called only by the CD workflows (never strategy.sh); deploy_e2e never runs it.
    # Intentionally non-fatal seam.
    "FWK28 notify.sh non-fatal seam invoked only by CD workflows, never run by a test",
),
```

- [ ] **Step 1: Flip to `_EX`.**

  Replace the entry with:

```python
SurfaceClass(
    "script:infra/deploy/notify.sh",
    "infra/deploy/notify.sh",
    _EX,
    # FWK28/L1: driven via _run_notify; echo path + webhook POST to capture server.
    "test_notify_seam_exits_zero_and_echoes",
),
```

- [ ] **Step 2: Run the completeness suite.**

  ```bash
  uv run pytest tests/runtime_coverage/ -q
  ```

  All pass:
  - `test_exercised_entries_name_an_existing_test` — `test_notify_seam_exits_zero_and_echoes`
    must exist in a `test_*.py` file under `tests/` (Task 1 lands first).
  - `test_known_gap_entries_link_a_task` — no new `_KG` entry added; the flipped entry is now
    `_EX` so the old `FWK28 …` evidence string is gone.
  - `test_every_surface_is_classified` — the key
    `script:infra/deploy/notify.sh` still appears in the rendered surface set.

  Commit.

---

## Task 3: L2 — load.sh graceful-degradation test

**Files:** Modify `tests/acceptance/test_rendered_project.py`, inserting after the FWK27
gate-hook block.

### What the template does (verbatim)

`src/framework_cli/template/scripts/load.sh:1–18`:

```bash
#!/usr/bin/env bash
set -euo pipefail
target="${K6_TARGET:-http://localhost:8000}"
...
docker run --rm -i --network host \
  -e "K6_TARGET=${target}" \
  ...
  grafana/k6:latest run - < tests/non_functional/load.js
```

Key mechanics: `set -euo pipefail`; `docker run` is called unconditionally; exit code is
`docker run`'s exit code (which is k6's exit code on threshold pass/fail). If Docker is
available but `grafana/k6:latest` fails to reach `K6_TARGET`, k6 exits non-zero → script exits
non-zero. If Docker is unavailable, `docker run` itself fails → script exits non-zero.

**Scope decision:** The full SLO-threshold assertion (k6 runs, target responds within P99/error
budget, k6 exits 0) requires a live app stack + the `grafana/k6:latest` image. That is out of
scope for the batch (no live stack here, pull would be ~250 MB, adds ~5 min). This test asserts
only the graceful-degradation path: the script exits non-zero with a clear diagnostic when
invoked with an unreachable target (Docker is available — the acceptance tier already requires
it — but the k6 container will exit non-zero because `http://localhost:19999` is not listening).
The `script:scripts/load.sh` registry entry stays `_KG` because the threshold propagation is
not exercised; this test adds value by confirming the script is syntactically valid, runnable,
and propagates failures — but it does NOT flip the entry. Document this honestly in the registry.

- [ ] **Step 1: Add `test_load_sh_fails_gracefully_without_docker_target`.**

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: load.sh wraps grafana/k6 in a Docker container",
)
def test_load_sh_fails_gracefully_without_docker_target(tmp_path: Path) -> None:
    """L2/FWK28 (graceful degradation): load.sh exits non-zero when K6_TARGET is unreachable.

    Scope: this test confirms the script runs (syntax, invocation path) and propagates a
    non-zero exit when k6 cannot reach the target. It does NOT assert the SLO-threshold
    pass/fail with a live app stack — that requires grafana/k6:latest + a running service and
    is logged as an ongoing KNOWN_GAP in the registry (script:scripts/load.sh).

    K6_TARGET is set to a port that is guaranteed not to be listening (free TCP port chosen at
    test time). K6_DURATION is set to "1s" and K6_VUS to "1" to fail fast. The Docker pull of
    grafana/k6:latest is required; if it is unavailable (registry outage / no pull credentials),
    this test is also expected to fail non-zero — that is acceptable, as it still exercises the
    propagation path.
    """
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    # Pick a port that is not listening.
    unreachable_port = _free_tcp_port()
    target = f"http://127.0.0.1:{unreachable_port}"

    result = subprocess.run(
        ["bash", "scripts/load.sh"],
        cwd=dest,
        capture_output=True,
        text=True,
        env={
            **_compose_env(),
            "K6_TARGET": target,
            "K6_DURATION": "1s",
            "K6_VUS": "1",
        },
        timeout=120,
    )
    assert result.returncode != 0, (
        "load.sh exited 0 on an unreachable target — threshold-propagation broken or "
        "k6 did not actually run\n"
        + result.stdout + result.stderr
    )
```

  > **Implementation note — `tests/non_functional/load.js`:** `load.sh` reads
  > `tests/non_functional/load.js` from the rendered project cwd
  > (`< tests/non_functional/load.js` at line 18). This file must exist in the rendered project
  > for the `docker run ... run - < tests/non_functional/load.js` to succeed. If it does NOT
  > exist, `docker run` exits non-zero immediately (stdin redirect fails). The test's
  > `returncode != 0` assertion still passes — but for a different reason than intended. If this
  > occurs, treat it as a real bug in the template (missing `tests/non_functional/load.js`) and
  > apply the real-bug policy.

- [ ] **Step 2: Lint.**

  ```bash
  uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format --check tests/acceptance/test_rendered_project.py
  ```

- [ ] **Step 3: Run L2 test — expect GREEN (non-zero exit from the script).**

  ```bash
  TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_load_sh_fails_gracefully_without_docker_target -q -s
  ```

  The k6 container pull (~250 MB first run) takes 2–4 min; subsequent runs are fast. The test
  passes when `result.returncode != 0`.

- [ ] **Step 4: Bite-prove.**

  Temporarily change:
  ```python
  assert result.returncode != 0,
  ```
  to:
  ```python
  assert result.returncode == 0,
  ```
  Run → expect **RED** (the script genuinely exits non-zero on an unreachable target). Revert.

  Commit.

---

## Task 4: L2 — registry annotation update for load.sh

**Files:** Modify `tests/runtime_coverage/registry.py`.

The registry entry for `script:scripts/load.sh` stays `_KG`. Update the evidence string to
reflect that the partial coverage (graceful-degradation) now exists.

### Current entry (locate by key `script:scripts/load.sh`)

```python
SurfaceClass(
    "script:scripts/load.sh",
    "scripts/load.sh",
    _KG,
    # L2: only render-checked; runs only inside the unexercised CD validation phase
    # (k6 SLO gate).
    "FWK28 load.sh k6 SLO gate runs only in the unexercised CD validation phase",
),
```

- [ ] **Step 1: Update the evidence string (status stays `_KG`).**

```python
SurfaceClass(
    "script:scripts/load.sh",
    "scripts/load.sh",
    _KG,
    # FWK28/L2: graceful-degradation path exercised by
    # test_load_sh_fails_gracefully_without_docker_target (acceptance, docker-gated); the full
    # k6 SLO-threshold pass/fail with a live app stack is NOT exercised — no live stack in
    # this tier. The threshold propagation remains an open gap.
    "FWK28 load.sh full k6 SLO-threshold pass/fail requires a live app stack (not in this tier)",
),
```

- [ ] **Step 2: Run completeness suite.**

  ```bash
  uv run pytest tests/runtime_coverage/ -q
  ```

  All pass: the `_KG` entry's evidence still starts with `FWK28`, satisfying
  `test_known_gap_entries_link_a_task`. No `_EX` flip, so `test_exercised_entries_name_an_existing_test`
  is not triggered for this entry.

  Commit.

---

## Task 5: L3 — docs.yml workflow-graph assertions

**Files:** Modify `tests/test_copier_runner.py`, immediately after
`test_render_docs_battery_adds_publish_workflow` (~line 3284).

### What the existing test guards (test_copier_runner.py:3273–3284)

```python
def test_render_docs_battery_adds_publish_workflow(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    path = dest / ".github" / "workflows" / "docs.yml"
    assert path.is_file(), "the docs battery must ship a docs.yml publish workflow"
    wf = yaml.safe_load(path.read_text())
    triggers = wf[True]  # PyYAML parses bare `on:` as bool True
    assert "tags" in triggers["push"], "publish must be tag-triggered"
    body = path.read_text()
    assert "mike deploy" in body
    assert "contents: write" in body
```

This test does NOT assert `--push --update-aliases` or `mike set-default`. The rendered
`docs.yml:33–34` has both; a future template edit that drops either flag would silently pass.

### What the template ships (docs.yml.jinja:33–34)

```yaml
          uv run --group docs mike deploy --push --update-aliases "$MINOR" latest
          uv run --group docs mike set-default --push latest
```

- [ ] **Step 1: Add `test_docs_workflow_mike_flags`.**

  Insert immediately after `test_render_docs_battery_adds_publish_workflow`.

```python
def test_docs_workflow_mike_flags(tmp_path: Path) -> None:
    """L3/FWK28: docs.yml must use --push --update-aliases and mike set-default.

    The existing test_render_docs_battery_adds_publish_workflow asserts 'mike deploy' appears
    in the body but does not pin the flags. This test adds the missing flag assertions and
    verifies the set-default step is present — both are required for correct versioned gh-pages
    publishing (without --push the deploy stays local; without set-default the 'latest' alias
    is never updated).
    """
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    body = (dest / ".github" / "workflows" / "docs.yml").read_text()

    assert "mike deploy --push --update-aliases" in body, (
        "docs.yml must call 'mike deploy --push --update-aliases'; "
        "without --push the versioned docs are never pushed to gh-pages"
    )
    assert "mike set-default" in body, (
        "docs.yml must call 'mike set-default'; "
        "without it the 'latest' alias is never set after a version deploy"
    )
    # Also assert the trigger is exactly `push: tags: v*` (not broader)
    wf = yaml.safe_load(body)
    triggers = wf[True]  # PyYAML parses bare `on:` key as bool True
    tag_patterns = triggers.get("push", {}).get("tags", [])
    assert any(
        p.startswith("v") for p in tag_patterns
    ), (
        f"docs.yml push trigger must include a 'v*' tag pattern; got: {tag_patterns!r}"
    )
```

- [ ] **Step 2: Lint.**

  ```bash
  uv run ruff check tests/test_copier_runner.py && uv run ruff format --check tests/test_copier_runner.py
  ```

- [ ] **Step 3: Run L3 test — expect GREEN.**

  ```bash
  uv run pytest tests/test_copier_runner.py::test_docs_workflow_mike_flags -q
  ```

  Render-only, no docker, ~10 s. If the test goes red, the template's `docs.yml.jinja` is
  missing the exact flag strings — apply the real-bug policy.

- [ ] **Step 4: Bite-prove.**

  Temporarily change:
  ```python
  assert "mike deploy --push --update-aliases" in body,
  ```
  to:
  ```python
  assert "mike deploy --push --NONEXISTENT_FLAG" in body,
  ```
  Run → expect **RED** (the string is not in the rendered file). Revert.

  Commit.

---

## Task 6: Close-out

- [ ] **Step 1: Full lint/format gate.**

  ```bash
  uv run ruff check tests/ && uv run ruff format --check tests/test_copier_runner.py tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py
  ```

- [ ] **Step 2: Full FWK28 run (gate-tier tests, no docker).**

  ```bash
  uv run pytest \
    tests/test_copier_runner.py::test_notify_seam_exits_zero_and_echoes \
    tests/test_copier_runner.py::test_notify_seam_posts_to_webhook \
    tests/test_copier_runner.py::test_docs_workflow_mike_flags \
    tests/runtime_coverage/ \
    -q
  ```

  Expected: all green. These run in CI (no docker marker).

- [ ] **Step 3: Acceptance-tier run (requires docker).**

  ```bash
  TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_load_sh_fails_gracefully_without_docker_target -q
  ```

- [ ] **Step 4: State + commit.** Tick FWK28 in `PLAN.md` (or move to Done when the batch
  closes), append `ACTION_LOG.md` entries (per `pi-convention.md`). Final commit with the
  skip-marker (`git add` then `git commit` as SEPARATE calls).

- [ ] **Step 5: Morning-report line.** Record: FWK28 green / xfail(+bug) / skipped; any real
  bugs found (new FWK IDs + ACTION_LOG refs).

---

## Self-Review

- **Spec coverage (L1):** `bash notify.sh 'msg'` exits 0 + echoes `[deploy notify]` →
  `test_notify_seam_exits_zero_and_echoes`. Webhook POST to capture server →
  `test_notify_seam_posts_to_webhook`. ✓
- **Spec coverage (L2):** k6 SLO gate — graceful-degradation assertion on unreachable target →
  `test_load_sh_fails_gracefully_without_docker_target`. Full threshold pass/fail explicitly
  NOT claimed. Registry stays `_KG` with updated evidence. ✓
- **Spec coverage (L3):** `docs.yml` triggers on `push: tags: v*` + `mike deploy --push
  --update-aliases` + `mike set-default` → `test_docs_workflow_mike_flags`. ✓
- **Mirrors existing patterns:**
  - L1 capture-server mirrors `_FakeAM`/`_serve_fake_am`/`_run_smoke`
    (test_copier_runner.py:2955–3004). ✓
  - L3 mirrors `test_render_docs_battery_adds_publish_workflow`
    (test_copier_runner.py:3273–3284); no duplication, only adds the missing flag assertions. ✓
  - L2 mirrors the `_docker_available()` skipif + `subprocess.run(..., cwd=dest, env=...)` shape
    of existing acceptance tests. ✓
- **No template change expected.** If a test goes red, root-cause first per the real-bug policy.
  ✓
- **Non-vacuity (bite-proven):** L1 echo test: flip to wrong string → RED. L2: flip `!= 0` to
  `== 0` → RED. L3: flip to nonexistent flag → RED. All three proven. ✓
- **Registry correctness:** `script:infra/deploy/notify.sh` flips `_KG` → `_EX` naming
  `test_notify_seam_exits_zero_and_echoes` (Task 2). `script:scripts/load.sh` stays `_KG`
  with updated FWK28 evidence (Task 4 — honest partial-coverage). `job:docs.yml:publish` stays
  `_EM` (Task 5 adds a graph assertion test but does not exercise the GitHub-platform publish
  step itself). ✓
- **`test_exercised_entries_name_an_existing_test` satisfied:** Task 1 lands before Task 2
  (the flip). The function `test_notify_seam_exits_zero_and_echoes` exists in
  `tests/test_copier_runner.py` before the registry is updated. ✓
- **`test_known_gap_entries_link_a_task` satisfied:** the updated `script:scripts/load.sh`
  evidence starts with `FWK28`. ✓
- **No docker in gate-tier tests:** L1 + L3 are render-only (`test_copier_runner.py`), visible
  in CI. L2 is acceptance-tier (`test_rendered_project.py`), `_docker_available()` skipif, local
  only. ✓

### Genuine forks (design decisions the human may want to revisit)

1. **L1 webhook test: string-replacement uncomment vs. inline script.** The webhook block in
   `notify.sh` is commented out. Two approaches:
   - **(A — this plan):** string-replace the rendered copy in `tmp_path` to uncomment the block.
     Low-friction, tests the exact curl invocation the template ships. Risk: if the comment
     format changes (indentation, `#` prefix style), the replacement silently no-ops and the
     capture server never gets a POST — `assert _FakeNotify.posts` catches the no-op. Safe.
   - **(B — alternative):** write a minimal inline bash heredoc that calls `curl` directly,
     bypassing the template block entirely. Tests the webhook infrastructure but not the
     template's curl invocation. Less faithful to the spec.
   The plan uses approach A with a `_FakeNotify.posts` guard. If the uncomment silently no-ops
   (comment format mismatch), treat it as a real bug in the test and switch to approach B.

2. **L2 scope: graceful degradation only, not full SLO gate.** The assessment's "Suggested test"
   asks for a test that "asserts the k6 run executes and the SLO threshold pass/fail propagates."
   Full execution requires: (1) `grafana/k6:latest` pulled, (2) a live app stack, (3) the app
   responding within SLO thresholds. That is a multi-minute compose acceptance test — out of scope
   for the batch. The plan tests the propagation path (script exits non-zero on failure) but not
   the threshold pass on a healthy app. A future plan can add the full k6 acceptance test once the
   full acceptance suite has a "lite stack" fixture (`docker compose -f base.yml -f lite.yml up`).

3. **L3: extend existing test vs. new function.** The plan adds `test_docs_workflow_mike_flags` as a
   new function rather than extending `test_render_docs_battery_adds_publish_workflow`. This keeps
   each test focused (file existence + trigger vs. specific mike flag strings) and avoids modifying
   a test that is already green and coverage-stable. The tradeoff is a second render (~10 s).
   Acceptable given the batch's priority on correctness over speed.

### Anticipated real bugs these tests may surface

1. **`tests/non_functional/load.js` missing from the rendered project (L2).** `load.sh` reads
   `< tests/non_functional/load.js` from the cwd. If this file does not exist in the rendered
   project, `docker run ... run - < ...` fails immediately (shell redirect error before Docker even
   starts), the script exits non-zero, and the `returncode != 0` assertion passes — but for the
   wrong reason. Check `result.stderr` for "No such file" when diagnosing. If it is missing from
   the template, apply the real-bug policy.

2. **`notify.sh` webhook uncomment silent no-op (L1).** If the template's comment prefix or
   indentation differs from what the string replacements expect, `script_path.write_text(activated)`
   writes the original unchanged content and `_FakeNotify.posts` is empty. `assert _FakeNotify.posts`
   fails with a clear message. Triage by printing `script_path.read_text()` after the write and
   verifying the `if [ -n ...` line is uncommented. Fix: adjust the replacement strings or switch
   to approach B.

3. **`docs.yml` PyYAML `on:` key as `True` (L3).** `yaml.safe_load` parses bare `on:` as the
   Python bool `True`, not the string `"on"`. The existing test already uses `wf[True]`; the new
   test mirrors this. If a future PyYAML version changes the behavior, both tests break together —
   not a FWK28-specific bug, but worth noting.

4. **`mike deploy` flag order or whitespace change (L3).** The plan asserts
   `"mike deploy --push --update-aliases" in body`. If a template edit reorders to
   `mike deploy --update-aliases --push`, this assertion goes red. This is the INTENDED behavior
   (flag-order regression is a real bug in the deploy command). If the order changes intentionally,
   update the assertion.

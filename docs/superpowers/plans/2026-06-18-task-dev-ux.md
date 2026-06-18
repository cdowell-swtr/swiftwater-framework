# FWK37 — `task dev` detached + "stack is up" summary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `task dev`/`dev:lite` bring the stack up **detached + healthy** and print one clear static "stack is up" summary (derived from the running stack, PORT_OFFSET-aware), and add `task dev:logs` / `task dev:down`.

**Architecture:** The generated `Taskfile.yml` runs `scripts/compose.sh … up -d --wait --build` (detached; Compose blocks only until healthchecks pass), then a new `scripts/dev_summary.sh` that reads `docker compose <-f set> ps --format json`, maps each running service to a label + URL, and prints a comprehensive block. Deriving from `ps` is the single source of truth — no second copy of `compose.sh`'s port map. `task dev:logs`/`dev:down` are project-scoped Taskfile targets (`down` keeps volumes).

**Tech Stack:** Copier `.jinja` template payload (Taskfile + bash); `docker compose ps --format json` parsed by `python3` (already a project dep); pytest render guards (`tests/test_copier_runner.py`) + a live acceptance test (`tests/acceptance/test_rendered_project.py`); `shellcheck`.

**Review-model policy (CLAUDE.md / [[subagent-review-model-pattern]]):** implementers → Sonnet; per-task spec review → Sonnet; code-quality → **Opus**; branch-end → **Opus**. Pass `model` explicitly.

**Conventions:** template payload tests run against a GENERATED project ([[template-payload-tdd-loop]]); commit-gate needs `PLAN.md`/`ACTION_LOG.md` staged, `git add` then `git commit` as **separate** calls ([[commit-gate-hook-timing]]); the acceptance/live tests need the sandbox disabled + `TMPDIR=/var/tmp`. The acceptance `_isolate_compose_project` fixture binds every `*_HOST_PORT=0` (ephemeral), so the summary must read the *actual* published port from `ps` — the live test asserts exactly that.

**Quality gate:** `uv run pytest tests/test_copier_runner.py tests/integrity/ tests/runtime_coverage/ -q` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src`. Live tier (Task 5) under sandbox-off + `TMPDIR=/var/tmp`.

---

## File Structure

**Template payload:**
- `src/framework_cli/template/scripts/dev_summary.sh` — *create:* reads `docker compose <args> ps --format json` (args forwarded from the Taskfile), parses with `python3` (in a `{% raw %}` block so Jinja ignores the Python braces), prints the comprehensive "stack is up" block. The only Jinja in the file is `slug="{{ project_slug }}"` (outside the raw block).
- `src/framework_cli/template/Taskfile.yml.jinja` — *modify:* `dev`/`dev:lite` compose step → `up -d --wait --build`, add a `dev_summary.sh` step; add `dev:logs` + `dev:down` targets.

**Framework source:**
- `src/framework_cli/integrity/classes.py` — *modify:* add `scripts/dev_summary.sh` to `LOCKED_TRACKED`.
- `tests/runtime_coverage/registry.py` — *modify:* classify the new `script:dev_summary.sh` surface.

**Tests:**
- `tests/test_copier_runner.py` — *add* render guards.
- `tests/acceptance/test_rendered_project.py` — *rework* `test_rendered_taskfile_dev_lite_target_drives_stack` (detached + summary + `dev:down` teardown).

---

## Task 1: `scripts/dev_summary.sh` (derive-from-`ps` summary)

**Files:**
- Create: `src/framework_cli/template/scripts/dev_summary.sh`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_dev_summary_script_renders_and_is_shellcheck_clean(tmp_path: Path):
    """FWK37: the stack-is-up summary script renders, is executable bash, and (when shellcheck
    is available) passes it. It derives from `docker compose ps` — no hardcoded port list."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    script = dest / "scripts" / "dev_summary.sh"
    assert script.is_file()
    text = script.read_text()
    assert "docker compose" in text and "ps" in text and "--format json" in text
    assert "python3" in text  # parses ps json
    # no second copy of compose.sh's port map (anti-drift): it must not hardcode the defaults
    assert "8000" not in text and "3000" not in text, "summary must derive ports from ps, not hardcode"
    # bash syntax-valid
    import subprocess as sp
    assert sp.run(["bash", "-n", str(script)]).returncode == 0
    if __import__("shutil").which("shellcheck"):
        r = sp.run(["shellcheck", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: Run it — expect FAIL** (`scripts/dev_summary.sh` missing).

Run: `uv run pytest tests/test_copier_runner.py::test_dev_summary_script_renders_and_is_shellcheck_clean -q`

- [ ] **Step 3: Create `src/framework_cli/template/scripts/dev_summary.sh`**

```bash
#!/usr/bin/env bash
# Print a one-shot "stack is up" summary for the local dev stack: every running service's
# published host port, mapped to a friendly label + URL. Derived entirely from
# `docker compose ps` (the single source of truth) so it auto-reflects dev vs lite, present
# batteries, and any PORT_OFFSET — no second copy of scripts/compose.sh's port map.
# Usage: dev_summary.sh <compose selector args>   e.g.  dev_summary.sh -f a.yml -f b.yml --profile dev
set -euo pipefail
slug="{{ project_slug }}"
offset="${PORT_OFFSET:-0}"
ps_json="$(docker compose "$@" ps --format json 2>/dev/null || true)"
printf '%s' "$ps_json" | SLUG="$slug" OFFSET="$offset" python3 {% raw %}<<'PY'
import json, os, sys

slug = os.environ["SLUG"]
offset = os.environ["OFFSET"]
raw = sys.stdin.read().strip()
svcs = []
if raw:
    try:
        parsed = json.loads(raw)
        svcs = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        svcs = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]

port = {}
running = set()
for s in svcs:
    name = s.get("Service")
    if not name:
        continue
    running.add(name)
    for pub in (s.get("Publishers") or []):
        pp = pub.get("PublishedPort")
        if pp:
            port[name] = pp

def line(label, value):
    print(f"  {label:<13}{value}")

bar = "━" * 50
print(bar)
print(f"  {slug} — stack is up  ✓        (PORT_OFFSET={offset})")
print(bar)

if "app" in port:
    direct = f"http://localhost:{port['app']}"
    if "traefik" in running:
        line("App", f"https://{slug}.localhost  ·  {direct}")
    else:
        line("App", direct)

for name, label in [
    ("grafana", "Grafana"), ("prometheus", "Prometheus"),
    ("alertmanager", "Alertmanager"), ("loki", "Loki"), ("tempo", "Tempo"),
]:
    if name in port:
        line(label, f"http://localhost:{port[name]}")

for name, label in [("postgres", "Postgres"), ("mongo", "Mongo"), ("redis", "Redis")]:
    if name in port:
        line(label, f"localhost:{port[name]}")

exp = [(n, port[n]) for n in
       ("postgres-exporter", "mongodb-exporter", "celery-exporter", "redis-exporter")
       if n in port]
if exp:
    print("  (+ exporters: " + " · ".join(f"{n.split('-')[0]} :{p}" for n, p in exp) + ")")

known = {"app", "traefik", "grafana", "prometheus", "alertmanager", "loki", "tempo",
         "postgres", "mongo", "redis", "postgres-exporter", "mongodb-exporter",
         "celery-exporter", "redis-exporter", "otel-collector", "promtail",
         "worker", "beat", "frontend"}
for name in sorted(port):
    if name not in known:
        line(name, f"localhost:{port[name]}")

print()
print("  logs: task dev:logs   ·   stop: task dev:down   ·   reset: task dev:reset")
print(bar)
PY
{% endraw %}
```

(Notes: the Python heredoc is `{% raw %}`-wrapped so Jinja never touches its braces; `slug`/`offset` reach Python via env, not via Jinja-inside-Python. `worker`/`beat`/`otel-collector`/`promtail`/`frontend` publish no host port in most stacks, so they won't appear — but they're in `known` so an unmapped *future* service still falls through to the raw catch-all rather than being silently dropped.)

- [ ] **Step 4: Run it — expect PASS** (renders, `bash -n` clean, shellcheck clean if present).

- [ ] **Step 5: Stage** (controller commits): `git add src/framework_cli/template/scripts/dev_summary.sh tests/test_copier_runner.py`. Report DONE.

---

## Task 2: Wire `dev`/`dev:lite` to detached + summary

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_dev_targets_run_detached_with_summary(tmp_path: Path):
    """FWK37: dev/dev:lite bring the stack up detached + healthy (`up -d --wait`) and print
    the summary, instead of tailing logs attached."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    tf = (dest / "Taskfile.yml").read_text()
    import yaml as _y
    spec = _y.safe_load(tf)
    for target in ("dev", "dev:lite"):
        cmds = "\n".join(str(c) for c in spec["tasks"][target]["cmds"])
        assert "up -d --wait --build" in cmds, f"{target} must use detached `up -d --wait --build`"
        assert "up --build" not in cmds.replace("up -d --wait --build", ""), (
            f"{target} must not still run attached `up --build`"
        )
        assert "./scripts/dev_summary.sh" in cmds, f"{target} must print the summary"
```

- [ ] **Step 2: Run it — expect FAIL.**

Run: `uv run pytest tests/test_copier_runner.py::test_dev_targets_run_detached_with_summary -q`

- [ ] **Step 3: Edit `Taskfile.yml.jinja` — `dev` cmds**

Replace the `dev` target's single compose line:
```yaml
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up --build
```
with two steps (detached + summary; pass the same selector args to the summary):
```yaml
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up -d --wait --build
      - ./scripts/dev_summary.sh -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev
```

- [ ] **Step 4: Edit `Taskfile.yml.jinja` — `dev:lite` cmds**

Replace:
```yaml
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up --build
```
with:
```yaml
      - ./scripts/compose.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up -d --wait --build
      - ./scripts/dev_summary.sh -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite
```

Update each target's `desc:` to mention it now runs detached (e.g. `dev`: "Full local stack over HTTPS (app + Traefik), detached + healthy, then prints where everything is."). `dev:reset` is unchanged (it calls `task: dev`).

- [ ] **Step 5: Run it — expect PASS.** Then regression: `uv run pytest tests/test_copier_runner.py -q -k "taskfile or dev or compose or render_includes"` — PASS.

- [ ] **Step 6: Stage:** `git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py`. Report DONE.

---

## Task 3: `task dev:logs` + `task dev:down`

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dev_logs_and_down_targets(tmp_path: Path):
    """FWK37: on-demand log-follow + a stop that KEEPS volumes (distinct from dev:reset's -v)."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    import yaml as _y
    spec = _y.safe_load((dest / "Taskfile.yml").read_text())
    logs = "\n".join(str(c) for c in spec["tasks"]["dev:logs"]["cmds"])
    down = "\n".join(str(c) for c in spec["tasks"]["dev:down"]["cmds"])
    assert "logs -f" in logs and "demo" in logs  # project-scoped follow
    assert "down" in down and "-v" not in down, "dev:down must keep volumes (no -v)"
```

- [ ] **Step 2: Run it — expect FAIL.**

- [ ] **Step 3: Add the targets to `Taskfile.yml.jinja`** (place them near `dev:reset`):

```yaml
  dev:logs:
    desc: Follow the dev stack's logs (Ctrl-C stops following; the stack keeps running).
    cmds:
      - docker compose -p {{ project_slug }} logs -f

  dev:down:
    desc: Stop the dev stack but KEEP volumes (data survives). Use dev:reset to wipe + rebuild.
    cmds:
      - docker compose -p {{ project_slug }} down
```

- [ ] **Step 4: Run it — expect PASS.**

- [ ] **Step 5: Stage:** `git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py`. Report DONE.

---

## Task 4: integrity + FWK29 classification for `dev_summary.sh`

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Modify: `tests/runtime_coverage/registry.py`
- Test: `tests/integrity/test_classes.py`, `tests/runtime_coverage/`

- [ ] **Step 1: Write the failing integrity test**

Add to `tests/integrity/test_classes.py`:
```python
def test_dev_summary_script_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED
    assert "scripts/dev_summary.sh" in LOCKED_TRACKED
```

- [ ] **Step 2: Run it — expect FAIL.** `uv run pytest tests/integrity/test_classes.py::test_dev_summary_script_is_locked -q`

- [ ] **Step 3: Add to `LOCKED_TRACKED`** in `src/framework_cli/integrity/classes.py` (alphabetical with the other `scripts/`):
```python
    "scripts/dev_summary.sh",
```

- [ ] **Step 4: Classify the FWK29 surface.** Run `uv run pytest tests/runtime_coverage/ -q` — it FAILS with `script:dev_summary.sh` (or the key `enumerate.py` emits) unclassified. Read the exact key, then add to `tests/runtime_coverage/registry.py` (match the existing `SurfaceClass(...)` style; `script:compose.sh` is the nearest sibling — copy its shape):
```python
    SurfaceClass(
        "script:dev_summary.sh",  # adjust to the exact key the failure prints
        "scripts/dev_summary.sh",
        _EX,
        # FWK37: the dev:lite live test runs `task dev:lite`, which invokes dev_summary.sh,
        # and asserts its printed block (app URL at the ephemeral port).
        "test_rendered_taskfile_dev_lite_target_drives_stack",
    ),
```

- [ ] **Step 5: Run both — expect PASS.** `uv run pytest tests/integrity/ tests/runtime_coverage/ -q` + `uv run mypy src` + `uv run ruff check src tests` clean.

- [ ] **Step 6: Stage:** `git add src/framework_cli/integrity/classes.py tests/runtime_coverage/registry.py tests/integrity/test_classes.py`. Report DONE.

---

## Task 5: Live acceptance — detached `task dev:lite` + summary + clean teardown

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py` (rework `test_rendered_taskfile_dev_lite_target_drives_stack`)

The existing test backgrounds `task dev:lite` (it ran *attached*) and tears down with `proc.terminate()`. Detached `up -d --wait` makes `task dev:lite` **return** (stack stays up), so `proc.terminate()` would **leak the stack**. Rework it to run synchronously, assert /health + the summary, and tear down via `task dev:down`.

- [ ] **Step 1: Rework the test body** (keep the `@pytest.mark.skipif(... task ...)` decorator + signature):

```python
def test_rendered_taskfile_dev_lite_target_drives_stack(tmp_path: Path) -> None:
    # FWK37: `task dev:lite` now runs DETACHED (`up -d --wait`) and prints the stack-is-up
    # summary, then returns. Run it synchronously; assert /health over the ephemeral port AND
    # that the summary names the app at that port; tear down with `task dev:down` (keeps volumes).
    import json as _json

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    env = _compose_env()
    try:
        up = subprocess.run(
            ["task", "dev:lite"], cwd=dest, env=env,
            capture_output=True, text=True, timeout=600,
        )
        assert up.returncode == 0, f"task dev:lite failed:\n{up.stdout}\n{up.stderr}"
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        # stack is actually up (up -d --wait already gated on healthy, but confirm /health)
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5) as resp:
            assert resp.status == 200
            body = _json.loads(resp.read())
        assert body["status"] in {"ok", "degraded"}
        # the summary (printed by dev_summary.sh as the 2nd cmd) named the app at this port
        out = up.stdout
        assert "stack is up" in out
        assert f"http://localhost:{port}" in out, (
            f"summary did not show the app at the ephemeral port {port}:\n{out}"
        )
    finally:
        subprocess.run(["task", "dev:down"], cwd=dest, env=env,
                       capture_output=True, text=True)
```

- [ ] **Step 2: Bite-prove the teardown.** After a green run, confirm no `demo`-project containers remain: `docker compose -p demo ps -q` is empty (the `task dev:down` finally worked). If containers linger, the teardown regressed.

- [ ] **Step 3: Run it (sandbox off, `TMPDIR=/var/tmp`).**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_taskfile_dev_lite_target_drives_stack -q`
Expected: PASS — `task dev:lite` returns after healthy, /health 200, the summary shows `http://localhost:<port>`, teardown leaves no containers.

- [ ] **Step 4: ruff** the test file; **Stage:** `git add tests/acceptance/test_rendered_project.py`. Report DONE.

---

## Branch-end (controller)

- [ ] **Gate:** `uv run pytest tests/test_copier_runner.py tests/integrity/ tests/runtime_coverage/ -q` + `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy src` — all green. (Render the project once and `ruff format --check` the rendered `scripts/dev_summary.sh`? It's bash, not Python — `shellcheck` via Task 1 covers it.)
- [ ] **Reviews:** per-task spec (Sonnet) + code-quality (Opus); branch-end whole-branch (Opus). Reviewer must verify: the `{% raw %}` wraps the Python heredoc (and `slug` reaches it via env, not Jinja-in-Python); the summary hardcodes **no** ports (derives from `ps`); `dev:down` has **no `-v`**; the reworked live test tears down via `dev:down` (no leak).
- [ ] **State + PR:** tick FWK37 in `PLAN.md` → `Done`; final `ACTION_LOG.md` entry. Open a PR against `master` (or fold into the release batch). Template payload, release-deferred.

---

## Self-Review (completed during authoring)

**Spec coverage:** detached `up -d --wait` → Task 2. Comprehensive summary derived from `ps` → Task 1. `dev:logs`/`dev:down` (down keeps volumes) → Task 3. integrity + FWK29 for `dev_summary.sh` → Task 4. Live acceptance (dev:lite, summary, offset-aware port) → Task 5. **No gaps.**

**Placeholder scan:** complete `dev_summary.sh` + Taskfile YAML + test code given. Task 4 Step 4's "adjust to the exact key the failure prints" is a deliberate read-the-red-output step (the FWK29 key string is generated), bounded with the sibling shape — not a TODO.

**Consistency:** `dev_summary.sh` arg contract (forward the `-f … --profile …` selector to `docker compose <args> ps`) is identical in Task 1 (script), Task 2 (Taskfile call), and Task 5 (live test reads its stdout). `dev:down` = `docker compose -p {{slug}} down` (no `-v`) in Task 3 and the Task 5 teardown. The summary's `http://localhost:<port>` form is what Task 5 asserts.

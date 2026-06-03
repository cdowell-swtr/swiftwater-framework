# Plan 12 — Template Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the docker-as-root host-UID gap on the `worker`/`beat`/`frontend` dev services and scrub PII from Celery's built-in failure log surface — both as template-payload TDD slices on one branch.

**Architecture:** Sub-slice A makes `worker`/`beat` run as the host UID (mirroring `app`) and switches the `frontend` dev command to `npm ci` (redirecting all writes into the root-owned `node_modules` named volume so nothing root-owned lands in the host `frontend/` bind), guarded by a worker/beat live test + a frontend static + live test. Sub-slice E installs a deterministic `logging.Filter` on Celery's `celery.app.trace` logger that blanks the four PII-bearing keys of Celery's failure-log context dict, wired via Celery's logger-setup signals and pinned by an eager-mode failure test.

**Tech Stack:** Copier/Jinja template payload, Docker Compose, Celery 5.x, Python `logging`, pytest (framework acceptance tier + generated-project unit tier).

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-02-template-hygiene-design.md`. Read it first.

## File Structure

| File | Responsibility | Sub-slice |
|------|----------------|-----------|
| `src/framework_cli/template/infra/compose/dev.yml.jinja` | `worker`/`beat` `user:` line; `frontend` `npm ci` | A |
| `tests/acceptance/test_rendered_project.py` | worker/beat live guard; frontend static + live guards | A |
| `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/log_redaction.py` | the `RedactCeleryFailureFilter` | E |
| `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja` | wire the filter via setup signals | E |
| `src/framework_cli/template/tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja` | filter unit + wiring + eager-mode coupling tests | E |

**Conventions (critical — see CLAUDE.md):**
- `src/framework_cli/template/` is template *payload*, not framework source — do not lint/mypy it as framework code.
- The brace/`{% if %}` path segments are intentional Copier path templating — leave them.
- The `tasks/` dir path segment is `{% if "workers" in batteries %}tasks{% endif %}` — files there render only under `--with workers`. `log_redaction.py` is a plain `.py` (no Jinja vars, like `base.py`/`dead_letter.py`).

## Working loop (template-payload TDD)

Generated-project tests need the *rendered* project's deps (celery, etc.), which the framework venv lacks. So iterate in a render. Set up once:

```bash
export FW_ROOT="$PWD"                       # the framework repo root
rm -rf /tmp/wk && mkdir -p /tmp/wk
uv run python - <<'PY'
from pathlib import Path
from framework_cli.copier_runner import render_project
render_project(Path("/tmp/wk/demo"), {
    "project_name": "Demo", "project_slug": "demo", "package_name": "demo",
    "python_version": "3.12", "batteries": ["workers"],
})
PY
cd /tmp/wk/demo && uv sync && cd "$FW_ROOT"
```

Then per edit: mirror the changed template file into the render and run the rendered test.
- Plain `.py` (e.g. `log_redaction.py`): `cp "$FW_ROOT/src/.../tasks/log_redaction.py" /tmp/wk/demo/src/demo/tasks/log_redaction.py`
- `.jinja` (e.g. `app.py.jinja`, the test file): render it through Copier (the render command above re-renders everything) **or** hand-substitute `{{ package_name }}`→`demo`. Simplest: re-run the render block above (it overwrites `/tmp/wk/demo`) after each `.jinja` edit, then `uv sync` only if deps changed.
- Run a rendered unit test: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v && cd "$FW_ROOT"`
- After edits, format-check the rendered output: `cd /tmp/wk/demo && uv run ruff format --check . ; cd "$FW_ROOT"` (see [[ruff-format-check-after-inline-edits]]).

The framework-side acceptance guards (Tasks 4–6) run from `$FW_ROOT` via `uv run pytest tests/acceptance/...` (they render internally).

---

## Sub-slice E — DLQ-PII log-surface scrubbing

### Task 1: The redaction filter + hermetic unit test

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/log_redaction.py`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing test**

Create the test file `tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja` with:

```python
"""Celery failure-log PII scrubbing: a deterministic filter on celery.app.trace (hermetic)."""

import logging

from {{ package_name }}.tasks.log_redaction import RedactCeleryFailureFilter


def _trace_record(context: dict) -> logging.LogRecord:
    # Mirrors Celery's celery.app.trace call: logger.log(severity, FORMAT, context_dict).
    return logging.LogRecord(
        "celery.app.trace", logging.ERROR, __file__, 0, "%(exc)s", context, None
    )


def test_filter_redacts_pii_keys_and_keeps_identity():
    rec = _trace_record(
        {
            "id": "task-1",
            "name": "demo.tasks.tasks.charge",
            "description": "raised unexpected",
            "exc": "ValueError('alice@example.com')",
            "traceback": "Traceback ... alice@example.com ...",
            "args": "('alice@example.com',)",
            "kwargs": "{'ssn': '123'}",
        }
    )
    assert RedactCeleryFailureFilter().filter(rec) is True
    ctx = rec.args
    assert ctx["exc"] == "<redacted>"
    assert ctx["traceback"] == "<redacted>"
    assert ctx["args"] == "<redacted>"
    assert ctx["kwargs"] == "<redacted>"
    # Operational/identity fields survive — the failure stays observable.
    assert ctx["id"] == "task-1"
    assert ctx["name"] == "demo.tasks.tasks.charge"
    assert ctx["description"] == "raised unexpected"
    # Rendered message carries no PII.
    assert "alice@example.com" not in rec.getMessage()


def test_filter_leaves_non_trace_records_untouched():
    rec = logging.LogRecord(
        "demo", logging.INFO, __file__, 0, "hello %s", ("world",), None
    )
    assert RedactCeleryFailureFilter().filter(rec) is True
    assert rec.args == ("world",)
```

- [ ] **Step 2: Run it; verify it fails**

Re-render `/tmp/wk/demo` (the render block above) so the new test file appears, then:
Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v ; cd "$FW_ROOT"`
Expected: FAIL — `ModuleNotFoundError: No module named 'demo.tasks.log_redaction'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/.../{% if "workers" in batteries %}tasks{% endif %}/log_redaction.py`:

```python
"""Redact PII from Celery's built-in task-failure logs.

Celery logs terminal failures via the `celery.app.trace` logger, calling
`logger.log(severity, FORMAT, context)` where `context` is a dict that becomes the
LogRecord's `args`. The PII (exception repr, traceback, call args/kwargs) lives in four
known keys. This filter blanks those keys and passes the record through, preserving the
task name/id/description so the failure stays observable. Deterministic — keyed on
Celery's own dict keys, no regex over content, no replacement logger.
"""

from __future__ import annotations

import logging


class RedactCeleryFailureFilter(logging.Filter):
    _PII_KEYS = ("exc", "traceback", "args", "kwargs")

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = record.args
        if isinstance(ctx, dict) and "id" in ctx and any(
            k in ctx for k in self._PII_KEYS
        ):
            record.args = {
                **ctx,
                **{k: "<redacted>" for k in self._PII_KEYS if k in ctx},
            }
        return True  # always pass — we mutate, never drop
```

- [ ] **Step 4: Run it; verify it passes**

Mirror: `cp "$FW_ROOT/src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/log_redaction.py" /tmp/wk/demo/src/demo/tasks/log_redaction.py`
Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v ; cd "$FW_ROOT"`
Expected: PASS (2 tests).

- [ ] **Step 5: Stage (controller commits — see [[subagent-implementers-stop-before-commit]])**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/log_redaction.py" \
        "src/framework_cli/template/tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja"
```

### Task 2: Wire the filter into the Celery app via setup signals

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja`
- Modify: the Task-1 test file (add wiring tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_dlq_log_redaction.py.jinja`:

```python
def test_setup_signal_installs_filter_on_trace_logger():
    import logging

    from celery.signals import after_setup_task_logger

    from {{ package_name }}.tasks import app as app_mod

    trace = logging.getLogger("celery.app.trace")
    trace.filters = [
        f for f in trace.filters if not isinstance(f, RedactCeleryFailureFilter)
    ]
    after_setup_task_logger.send(sender=None)  # fire the wiring
    assert any(isinstance(f, RedactCeleryFailureFilter) for f in trace.filters)


def test_install_is_idempotent():
    import logging

    from {{ package_name }}.tasks.app import install_failure_log_redaction

    trace = logging.getLogger("celery.app.trace")
    trace.filters = [
        f for f in trace.filters if not isinstance(f, RedactCeleryFailureFilter)
    ]
    install_failure_log_redaction()
    install_failure_log_redaction()
    count = sum(isinstance(f, RedactCeleryFailureFilter) for f in trace.filters)
    assert count == 1  # shared instance ⇒ addFilter dedupes
```

- [ ] **Step 2: Run; verify failure**

Re-render `/tmp/wk/demo`, then:
Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v ; cd "$FW_ROOT"`
Expected: FAIL — `ImportError: cannot import name 'install_failure_log_redaction'` (and the signal test finds no filter).

- [ ] **Step 3: Wire it in `app.py.jinja`**

Add `import logging` to the top-of-file imports (after `from __future__ import annotations`):

```python
import logging
```

Add to the existing `from celery...` import group:

```python
from celery.signals import after_setup_logger, after_setup_task_logger, worker_process_init
```

(Replace the existing `from celery.signals import worker_process_init` line with the line above.)

Add this import alongside the other local imports:

```python
from .log_redaction import RedactCeleryFailureFilter
```

Then, after the `app.conf.update(...)` block, add:

```python
_FAILURE_LOG_REDACTION = RedactCeleryFailureFilter()  # one shared instance ⇒ addFilter dedupes


def install_failure_log_redaction(**_kwargs: object) -> None:
    """Attach the PII-redacting filter to Celery's failure logger (celery.app.trace).

    Connected to both logger-setup signals so it installs whichever logging path a worker
    takes; the shared instance makes a double-attach a no-op.
    """
    logging.getLogger("celery.app.trace").addFilter(_FAILURE_LOG_REDACTION)


after_setup_logger.connect(install_failure_log_redaction)
after_setup_task_logger.connect(install_failure_log_redaction)
```

- [ ] **Step 4: Run; verify pass**

Re-render `/tmp/wk/demo` (re-renders `app.py.jinja` + the test):
Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v ; cd "$FW_ROOT"`
Expected: PASS (4 tests).

- [ ] **Step 5: Stage**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja" \
        "src/framework_cli/template/tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja"
```

### Task 3: Eager-mode coupling test (pins Celery's record shape)

**Files:**
- Modify: the Task-1 test file (add the end-to-end eager test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_dlq_log_redaction.py.jinja`:

```python
def test_celery_failure_log_is_redacted_end_to_end():
    """Trigger a real eager task failure and assert celery.app.trace logs no PII.

    Pins the Celery-internal coupling: that terminal failures route through
    celery.app.trace with the context dict our filter targets. If a future Celery
    changes the log policy, this fails loudly instead of silently leaking.
    """
    import logging

    from {{ package_name }}.tasks.app import app as celery_app
    from {{ package_name }}.tasks.app import install_failure_log_redaction

    install_failure_log_redaction()
    # The autouse eager fixture sets task_eager_propagates=True (re-raise); for the LOG
    # path we want eager mode to catch + log the failure instead.
    celery_app.conf.task_eager_propagates = False

    @celery_app.task(name="demo._pii_boom", bind=False)
    def _boom(secret):
        raise ValueError(f"leak {secret}")

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    trace = logging.getLogger("celery.app.trace")
    handler = _Capture()
    trace.addHandler(handler)
    trace.setLevel(logging.ERROR)
    try:
        _boom.apply(args=("alice@example.com",))
    finally:
        trace.removeHandler(handler)
        celery_app.conf.task_eager_propagates = True  # restore the fixture default

    rendered = " ".join(r.getMessage() for r in records)
    assert records, "expected a celery.app.trace failure log to be emitted"
    assert "alice@example.com" not in rendered
    assert "<redacted>" in rendered
```

- [ ] **Step 2: Run; verify it passes (coupling already wired in Task 2)**

Re-render `/tmp/wk/demo`, then:
Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py::test_celery_failure_log_is_redacted_end_to_end -v ; cd "$FW_ROOT"`
Expected: PASS.

> Note: this is the one E test whose green state depends on Tasks 1–2 (filter + wiring), so it is not red-first in isolation — it is the *integration* proof that pins the coupling. To see it genuinely red, temporarily comment out the `install_failure_log_redaction()` call: the assertion `"alice@example.com" not in rendered` fails because Celery's raw log carries the message. Re-enable before continuing.

- [ ] **Step 3: Full E suite green + format-check**

Run: `cd /tmp/wk/demo && uv run pytest tests/unit/test_dlq_log_redaction.py -v && uv run ruff format --check src/demo/tasks/log_redaction.py tests/unit/test_dlq_log_redaction.py ; cd "$FW_ROOT"`
Expected: 5 tests PASS; format-check clean.

- [ ] **Step 4: Stage**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if "workers" in batteries %}tasks{% endif %}/app.py.jinja" \
        "src/framework_cli/template/tests/unit/{{ 'test_dlq_log_redaction.py' if 'workers' in batteries else '' }}.jinja"
```

---

## Sub-slice A — docker-as-root host-UID

### Task 4: worker/beat run as host UID + live guard

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (worker + beat blocks)
- Test: `tests/acceptance/test_rendered_project.py` (new guard)

- [ ] **Step 1: Write the failing guard test**

Append to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: brings up the workers dev stack to check file ownership",
)
def test_rendered_workers_dev_stack_leaves_no_root_owned_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev",
          "up", "-d", "--build", "worker", "beat"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    # Liveness signal: the worker imports the package on startup, writing __pycache__ into
    # the bind-mounted /app/src. Wait for that to appear (proves the scan is non-vacuous).
    pycache = dest / "src" / "demo" / "tasks" / "__pycache__"
    ran = False
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        deadline = time.time() + 120
        while time.time() < deadline:
            if pycache.exists():
                ran = True
                break
            time.sleep(2)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # Reclaim any root-owned residue (the red state) so pytest can clean tmp_path.
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{dest}:/work", "alpine",
             "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work"]
        )
    assert ran, "worker never wrote __pycache__ within 120s — ownership check would be vacuous"
    me = os.getuid()
    bad = [p for p in (dest / "src").rglob("*") if p.stat().st_uid != me]
    assert not bad, f"root/non-host-owned files left behind by worker/beat: {bad[:5]}"
```

- [ ] **Step 2: Run; verify it fails (red — worker writes root-owned __pycache__)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_workers_dev_stack_leaves_no_root_owned_files -v`
Expected: FAIL — `bad` is non-empty (root-owned `__pycache__` under `src/demo/tasks/`). The `chown` teardown reclaims it so the next run is clean.

- [ ] **Step 3: Add `user:` to worker and beat in `dev.yml.jinja`**

In the `worker:` block, immediately after the `profiles: ["dev"]` line (currently line 132), insert:

```yaml
    # Run as the invoking host user so bind-mounted /app/src writes (__pycache__) are
    # host-owned, not root-owned (mirrors the app service). :-1000 keeps raw `compose` working.
    user: "${UID:-1000}:${GID:-1000}"
```

In the `beat:` block, immediately after its `profiles: ["dev"]` line (currently line 162), insert the identical three lines.

- [ ] **Step 4: Run; verify it passes (green — host-owned)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_workers_dev_stack_leaves_no_root_owned_files -v`
Expected: PASS — `__pycache__` is host-owned, `bad` is empty.

- [ ] **Step 5: Stage**

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja tests/acceptance/test_rendered_project.py
```

### Task 5: frontend uses `npm ci` + static guard

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (frontend command)
- Test: `tests/acceptance/test_rendered_project.py` (static guard)

- [ ] **Step 1: Write the failing static guard test**

Append to `tests/acceptance/test_rendered_project.py` (no Docker needed — pure render-content):

```python
def test_frontend_dev_command_uses_npm_ci_not_install(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "npm ci" in dev, "frontend dev command must use `npm ci` (frozen lockfile, no host-bind write)"
    assert "npm install" not in dev, (
        "frontend must not use `npm install` — it rewrites package-lock.json into the host "
        "bind as root"
    )
    # node_modules must stay a named volume so npm's writes never land on the host.
    assert "frontend_node_modules:/app/frontend/node_modules" in dev
```

- [ ] **Step 2: Run; verify it fails**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_frontend_dev_command_uses_npm_ci_not_install -v`
Expected: FAIL — `"npm install" not in dev` assertion fails (the current command is `npm install`).

- [ ] **Step 3: Switch the frontend command in `dev.yml.jinja`**

In the `frontend:` block, change line 116 from:

```yaml
    command: ["sh", "-c", "npm install && npm run dev -- --host"]
```

to:

```yaml
    command: ["sh", "-c", "npm ci && npm run dev -- --host"]
```

- [ ] **Step 4: Run; verify it passes**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_frontend_dev_command_uses_npm_ci_not_install -v`
Expected: PASS.

- [ ] **Step 5: Stage**

```bash
git add src/framework_cli/template/infra/compose/dev.yml.jinja tests/acceptance/test_rendered_project.py
```

### Task 6: frontend live guard (defense-in-depth tripwire)

**Files:**
- Test: `tests/acceptance/test_rendered_project.py` (live guard)

> This guard enforces the property empirically — it trips on root-owned residue in `frontend/` from *any* source, including a future toolchain regression that `npm ci` alone wouldn't catch. Its red state under the old `npm install` is not guaranteed (npm only rewrites the lockfile when it drifts), so it is added after the Task-5 fix and verified green; the static guard (Task 5) is the red-first anchor for the decision.

- [ ] **Step 1: Write the guard test**

Append to `tests/acceptance/test_rendered_project.py`:

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker (+ network for npm ci) required: brings up the frontend dev service",
)
def test_rendered_frontend_dev_stack_leaves_no_root_owned_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev",
          "up", "-d", "--build", "frontend"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    served = False
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        # npm ci over the network + vite startup; wait for the dev server (non-vacuous).
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:5173", timeout=3) as resp:
                    if resp.status == 200:
                        served = True
                        break
            except OSError:
                time.sleep(3)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        subprocess.run(
            ["docker", "run", "--rm", "-v", f"{dest}:/work", "alpine",
             "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/work"]
        )
    assert served, "frontend dev server did not serve on :5173 within 180s — scan would be vacuous"
    me = os.getuid()
    bad = [p for p in (dest / "frontend").rglob("*") if p.stat().st_uid != me]
    assert not bad, f"root/non-host-owned files left in frontend/: {bad[:5]}"
```

- [ ] **Step 2: Run; verify it passes (green — npm ci writes only the named volume)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_frontend_dev_stack_leaves_no_root_owned_files -v`
Expected: PASS — host `frontend/` has only host-owned render files; npm's writes went to the `node_modules` named volume.

- [ ] **Step 3: Stage**

```bash
git add tests/acceptance/test_rendered_project.py
```

---

## Task 7: Integration sweep + state + branch-end

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`
- Modify: `docs/superpowers/specs/2026-06-02-template-hygiene-design.md` (one-line integrity correction)

- [ ] **Step 1: Baseline byte-identity — no manifest shift**

Confirm the no-battery baseline `dev.yml` is unchanged (the edits are all inside `{% if workers %}`/`{% if react %}` blocks):

Run:
```bash
uv run python - <<'PY'
from pathlib import Path
from framework_cli.copier_runner import render_project
render_project(Path("/tmp/wk_base/demo"), {
    "project_name": "Demo", "project_slug": "demo", "package_name": "demo",
    "python_version": "3.12",
})
print((Path("/tmp/wk_base/demo/infra/compose/dev.yml")).read_text().count("user:"))
PY
```
Expected: `1` (only the `app` service has `user:` in the baseline render). If >1, the edits leaked outside the conditional blocks — fix.

- [ ] **Step 2: Integrity green across combos (new + downskill)**

Run: `uv run pytest tests/test_integrity_workers.py tests/integrity -q`
Expected: PASS. (`dev.yml` is LOCKED and regenerated per render; no committed hash to hand-edit. The conditional edits change only the `--with workers`/`--with react` manifests, which self-check.)

- [ ] **Step 3: Generated-project suites green across the touched battery combos**

Run (Docker required):
```bash
uv run pytest \
  "tests/acceptance/test_rendered_project.py::test_rendered_workers_dev_stack_leaves_no_root_owned_files" \
  "tests/acceptance/test_rendered_project.py::test_frontend_dev_command_uses_npm_ci_not_install" \
  "tests/acceptance/test_rendered_project.py::test_rendered_frontend_dev_stack_leaves_no_root_owned_files" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_dev_lite_stack_leaves_no_root_owned_files" \
  "tests/acceptance/test_rendered_project.py::test_rendered_project_with_workers_battery_passes" -v
```
Expected: all PASS (incl. the pre-existing dev:lite + workers-battery guards, confirming no regression).

- [ ] **Step 4: workers+react combo render + its own unit tier**

Run:
```bash
rm -rf /tmp/wk_combo && uv run python - <<'PY'
from pathlib import Path
from framework_cli.copier_runner import render_project
render_project(Path("/tmp/wk_combo/demo"), {
    "project_name": "Demo", "project_slug": "demo", "package_name": "demo",
    "python_version": "3.12", "batteries": ["workers", "react"],
})
PY
cd /tmp/wk_combo/demo && uv sync && uv run pytest tests/unit/test_dlq_log_redaction.py -q \
  && uv run ruff format --check . ; cd "$FW_ROOT"
```
Expected: log-redaction tests PASS; rendered output format-clean.

- [ ] **Step 5: Framework gate (ex-acceptance)**

Run: `uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all green. (No framework-source change, so mypy/ruff cover only the unchanged CLI; the template payload is excluded by config.)

- [ ] **Step 6: Correct the spec's integrity note + update state**

In `docs/superpowers/specs/2026-06-02-template-hygiene-design.md`, replace the "one-time baseline integrity manifest bump" sentence with: the edits live inside the `workers`/`react` conditional blocks, so the **baseline `dev.yml` is byte-identical and there is NO baseline manifest shift**; only the `--with workers`/`--with react` renders change, and those manifests regenerate per render.

Update `CLAUDE.md` Current State (`Last updated` datetime + note Plan 12 merged) and the meta-plan Plan 12 row → ✅ Done with the FF SHA (set during merge). `git add CLAUDE.md` (the commit-gate hook requires it).

- [ ] **Step 7: Branch-end review + merge**

Per the framework cadence ([[gate-cadence-framework-slices]]): one branch-end full review, then FF-merge to `master`. Record the FF SHA in CLAUDE.md + the meta-plan row.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- A / worker+beat `user:` → Task 4. ✅
- A / frontend `npm ci` (no entrypoint) → Task 5. ✅
- A / guards: existing dev:lite (Task 7 Step 3 re-runs it) + worker/beat live (Task 4) + frontend static (Task 5) + frontend live (Task 6). ✅
- E / deterministic context-dict filter → Task 1. ✅
- E / wired via `after_setup_logger`/`after_setup_task_logger`, idempotent shared instance → Task 2. ✅
- E / eager-mode coupling test → Task 3. ✅
- Integrity / combos / no framework dep change → Task 7. ✅ (spec's "baseline bump" corrected to "no baseline shift" — Task 7 Step 6.)

**Placeholder scan:** none — every code/command step is concrete.

**Type/name consistency:** `RedactCeleryFailureFilter`, `install_failure_log_redaction`, `_FAILURE_LOG_REDACTION`, `_PII_KEYS` used identically across Tasks 1–3. Compose service/volume names (`worker`/`beat`/`frontend`/`frontend_node_modules`) match `dev.yml.jinja`. Test names referenced in Task 7 match their definitions in Tasks 4–6.

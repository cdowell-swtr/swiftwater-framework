# Plan 12 — Template hygiene: docker-as-root host-UID gap + DLQ-PII log-surface scrubbing — Design

**Date:** 2026-06-02
**Status:** Design (brainstormed, approved) — ready for writing-plans
**Plan:** Plan 12 in the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`)
**Spec:** `docs/superpowers/specs/2026-05-20-framework-design.md` (§5 observability/§19 recoverability surfaces)

## Summary

Two independent template-payload hygiene fixes on the workers/react surface, bundled into one
branch + one render/acceptance cycle:

- **Sub-slice A — docker-as-root host-UID gap.** Plan 9 made only the dev `app` service run as
  the host UID. The `worker`/`beat` (workers battery) and `frontend` (react battery, `node:22`)
  dev services still run as **root** over writable bind-mounts and leave root-owned residue —
  the exact `/tmp`-wedging class Plan 9 claimed to resolve. Close the gap and widen the guard so
  it can no longer slip.
- **Sub-slice E — DLQ-PII log-surface scrubbing.** The lone deferred DLQ-PII follow-up. The
  dead-letter row is already redact-by-default, but Celery's built-in `celery.app.trace` logger
  emits the raw exception message + full traceback + task args at ERROR to stdout → Promtail →
  Loki, bypassing the redaction seams. Scrub that log surface deterministically.

Both are TDD template-payload slices. No framework-source change, no new framework dependency.

## Background — why each gap exists

### A — docker-as-root

`infra/compose/dev.yml.jinja` carries exactly **one** `user:` line, on the `app` service
(added by Plan 9 so `--reload` `__pycache__` writes are host-owned). Three other
`profiles: ["dev"]` services bind-mount **writable** host paths with no `user:` line, so they
run as root:

| Service | Battery | Writable bind | Root writes |
|---------|---------|---------------|-------------|
| `worker` | `workers` | `../../src:/app/src` | `__pycache__` into host `src/` |
| `beat` | `workers` | `../../src:/app/src` | `__pycache__` into host `src/` |
| `frontend` | `react` (`node:22`) | `../../frontend:/app/frontend` | `package-lock.json` rewrite into host `frontend/` (from `npm install`) |

The existing guard `test_rendered_project_dev_lite_stack_leaves_no_root_owned_files` is
structurally blind to all three: it brings up `--profile lite` (which is `app`-only, so
worker/beat/frontend never start) and scans only `dest/src` (never `dest/frontend`). So it
reports green while covering only the already-fixed path.

The failure mode this regresses to (from SVC-PROD): root-owned artifacts accumulate under the
acceptance tier's render dir, the host user can't clear them, and a full `/tmp` wedges the
sandbox (every shell command fails). Prevention — never write the root-owned files — is the fix,
not cleanup.

### E — DLQ-PII log-surface scrubbing

`BaseTask.on_failure` (`tasks/base.py`) is already clean: it persists a dead-letter row using
the redact-by-default `dlq_args_json` (arg *shapes*, not values) and `dlq_traceback` (frame
locations + exception type, message redacted). But that only governs the **DLQ row**. Celery
itself logs terminal task failures through its `celery.app.trace` logger, calling
`logger.log(severity, FORMAT, context)` where `context` is a dict carrying `exc` (the
`safe_repr` of the exception, including its message), `traceback` (the full `safe_str`
traceback), and `args`/`kwargs` (the `safe_repr` of the call) — all PII-bearing, none touched
by our seams. Worker stdout is shipped to Loki by Promtail (Docker SD), so that raw text lands
in the log store. This is the one DLQ-PII follow-up deferred from the compliance-posture work.

## Sub-slice A — design

### worker + beat

Add the same line the `app` service already has:

```yaml
user: "${UID:-1000}:${GID:-1000}"
```

They share the app image (`build.context ../..`, `infra/docker/Dockerfile`) and bind the same
`../../src`, so this is a direct mirror — `__pycache__` writes become host-owned. The `:-1000`
default keeps a raw `docker compose up` (no `UID`/`GID` in env) working, exactly as the app
service does. `APP_RUN_MIGRATIONS: "false"` is unchanged.

**Assumption to confirm at TDD:** Celery worker/beat as an arbitrary non-root UID needs no
writable `HOME` (the app already runs unprivileged via the same mechanism without one). If a
`HOME`/permission issue surfaces, the minimal fix is an `environment:` `HOME=/tmp` — but the
expectation is none is needed.

### frontend

The frontend stays running as **root** (no `user:`, no entrypoint) — we close the leak by
**redirecting the writes**, not by changing ownership:

- Change the dev command from `npm install && npm run dev -- --host` to
  `npm ci && npm run dev -- --host`.

`npm ci` is contractually frozen with respect to the manifests: it **never writes
`package.json` or `package-lock.json`** (it errors if they drift instead of updating), and it
removes/repopulates `node_modules` — which is shadowed by the `frontend_node_modules` **named
volume** (root-owned, never on the host, reaped by `down -v`). Vite's dev cache defaults to
`node_modules/.vite` (the volume). Net: the frontend container writes nothing to the host
`frontend/` bind.

**Decision recorded (YAGNI):** a host-UID + `chown`-then-drop entrypoint (`setpriv`) was
considered and **rejected** as asymmetric and heavier than the problem — `npm ci` prevents the
host-bind write at the source, and the named volume is throwaway. The residual risk (a *future*
toolchain change or builder config writing root-owned files to the project root, which npm ci
does not guard) is covered by the **live guard** below rather than by config, so the property is
*verified each run* rather than *assumed*.

### Guards (sub-slice A)

Three layers, keeping the existing dev:lite guard:

1. **Existing** — `test_rendered_project_dev_lite_stack_leaves_no_root_owned_files` (app /
   `--profile lite`, scans `dest/src`). Unchanged.
2. **worker/beat — live, Docker-gated.** A no-root-owned-files guard on a `--with workers`
   render: bring up the `dev` profile, wait for the `worker` healthcheck (so it imports the
   package and writes `__pycache__`), scan `dest/src` for any file whose `st_uid` != the host
   uid. Python-only, no network. This is the direct regression catch.
3. **frontend — static + live.**
   - **Static** (fast, no-Docker): a render-content assertion that the frontend dev command is
     `npm ci` (not `npm install`) and that `node_modules` is a named volume. Fails loudly if
     anyone reverts the command — locks the decision cheaply.
   - **Live** (Docker-gated, network): a `--with react` render, bring the `frontend` service up
     (real `npm ci`, ~30–90s), wait for the dev server, scan `dest/frontend` for non-host-owned
     files. This is the empirical tripwire that catches *any* future root-write path, not just a
     reverted command. Gated to the Docker acceptance tier (network assumed there).

The live guards assert the actual property; the static guard is the fast canary.

## Sub-slice E — design

A workers-gated logging filter that deterministically mutates Celery's failure log record —
keyed on Celery's own trace **context dict** (no regex over content, no replacement logger).

New module `src/{{package_name}}/tasks/log_redaction.py`:

```python
import logging


class RedactCeleryFailureFilter(logging.Filter):
    """Redact PII from celery.app.trace failure/retry logs.

    Celery logs task failures via logger.log(severity, FORMAT, context) where `context`
    is a dict (record.args). The PII lives in four known keys; we blank them and pass the
    record through, preserving task name/id/description so the failure stays observable.
    """

    _PII_KEYS = ("exc", "traceback", "args", "kwargs")

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = record.args
        if isinstance(ctx, dict) and "id" in ctx and any(k in ctx for k in self._PII_KEYS):
            record.args = {
                **ctx,
                **{k: "<redacted>" for k in self._PII_KEYS if k in ctx},
            }
        return True  # always pass — we mutate, never drop
```

The redacted line stays useful: `Task foo[<id>] raised unexpected: <redacted>` with
name/id/hostname/description intact.

**Wiring** — attach the filter to the `celery.app.trace` logger in `app.py.jinja` via Celery's
logging-setup signals so it survives Celery's logger configuration:

```python
from celery.signals import after_setup_logger, after_setup_task_logger
from .log_redaction import RedactCeleryFailureFilter

_REDACTION_FILTER = RedactCeleryFailureFilter()  # one shared instance ⇒ addFilter dedupes

def _install_redaction(**_kwargs):
    logging.getLogger("celery.app.trace").addFilter(_REDACTION_FILTER)

after_setup_logger.connect(_install_redaction)
after_setup_task_logger.connect(_install_redaction)
```

Both signals are connected because Celery configures a worker logger and a task logger and we
want the filter installed whichever path runs. Using a single **shared filter instance** makes
the double-attach a true no-op: `Logger.addFilter` skips a filter already in `self.filters`.

**Test (E)** — hermetic, Celery **eager mode** (`task_always_eager=True`, no broker): define a
task that raises an exception whose message + args carry a PII marker, trigger it, capture logs
(`caplog` / a handler), assert the four context keys render as `<redacted>` and that
`name`/`id` survive. This test *pins the Celery-internal record shape* (the `context`-dict
logging contract) against the pinned `celery>=5.4` — the correct place for that coupling.

**Assumption to confirm at TDD:** the exact `celery.app.trace` `context` keys and that
`record.args` is the dict (validated empirically by the eager-mode test, not by reading Celery
source). If a future Celery changes the log policy, this test fails loudly rather than silently
leaking.

## Testing strategy (overall)

- TDD throughout, via the template-payload loop (render → `uv sync` → edit framework source →
  mirror into the render [`cp` `.py`, render+`cp` `.jinja`] → run the rendered project's tests in
  `/tmp/work` → `ruff format --check` the rendered output).
- Sub-slice E: the eager-mode redaction test (hermetic, no Docker).
- Sub-slice A: the worker/beat live guard + the frontend static guard (no Docker) + the frontend
  live guard (Docker + network).
- Bundled render + acceptance covers `--with workers`, `--with react`, and the `workers,react`
  combo; rendered project makes a clean first `pre-commit` pass across combos.

## Integrity / manifest impact

`infra/compose/dev.yml.jinja` is already **LOCKED** (Plan 9 shifted it). The worker/beat `user:`
edits and the frontend command edit change that LOCKED file → a **one-time baseline integrity
manifest bump**, the same class and handling as Plan 9. No new files are added to the locked set
(the entrypoint was dropped). The new `tasks/log_redaction.py` renders only under `--with
workers`; confirm it does **not** force a manifest shift for the baseline (no-workers) render
(it is conditional payload, like the rest of `tasks/`). Integrity must stay green across battery
combos both ways (new + downskill).

## Non-goals

- No host-UID/chown/`setpriv` entrypoint for the frontend (rejected above).
- No change to the DLQ row redaction, retention, or the `redacted` flag (all shipped).
- No new framework dependency; no framework-source change.
- No prod/staging compose change — these are **dev**-profile services only (prod runs the app
  image via `services.yml`, already root-by-design but on named volumes, out of scope).
- No `PYTHONDONTWRITEBYTECODE` alternative for worker/beat (we mirror the app's `user:` approach
  for consistency rather than introduce a second mechanism).

## Open assumptions to validate during implementation

1. Celery worker/beat run cleanly as an arbitrary non-root UID with no writable `HOME` (the app
   already does via the same mechanism; minimal fallback is `environment: HOME=/tmp`).
2. The `celery.app.trace` failure log passes its `context` as `record.args` (dict) with the four
   PII keys — pinned by the eager-mode test against `celery>=5.4`.
3. The new `log_redaction.py` is conditional (workers-gated) payload and does not shift the
   baseline manifest.

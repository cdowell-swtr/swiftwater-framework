---
name: template-payload-tdd-loop
description: "How to TDD template-payload changes — render to /tmp + uv sync, edit source, mirror, run the test in the GENERATED project (framework venv can't run them)."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: 49f13a1d-7e1e-4c24-8e52-b50a128128c4
---

Template-payload tests (anything under `src/framework_cli/template/.../tests/`) run **in a generated project**, not the framework venv — the framework venv lacks celery/opentelemetry/pymongo/etc. So the fast in-session TDD loop (avoid the Docker acceptance tier — see `[[reviewers-tune-pytest-tmp-accumulation]]`) is:

1. **One-time:** `rm -rf /tmp/work && uv run framework template-render --out /tmp/work >/dev/null && (cd /tmp/work && uv sync --quiet)`. Render with NO `--batteries` flag = ALL batteries (so every gated file is present). `uv sync` is the slow part; do it once.
2. **Edit the TEMPLATE SOURCE** under `src/framework_cli/template/` (not the rendered copy).
3. **Mirror into /tmp/work:** plain `.py` files (no jinja in body, e.g. `metrics.py`, `db/repository.py`, `tasks/base.py`) → `cp "<template path>" /tmp/work/src/<pkg>/<rel>`. `.jinja` files (or any file with `{{ }}`/`{% %}`, incl. test `.jinja`s with battery-conditional bodies) → **re-render** to a throwaway dir and `cp` the rendered file (NEVER hand-substitute jinja): `uv run framework template-render --out /tmp/render >/dev/null; cp /tmp/render/<rel> /tmp/work/<rel>`.
4. **Run:** `(cd /tmp/work && uv run pytest tests/unit/<file> -q)`.

Hermetic vs not: most unit tests are hermetic (TestClient / in-memory SQLite via `Model.__table__.create(engine)` + tz-aware timestamps / monkeypatched collaborators) and run instantly. DB-backed tests (the `db_session`/`engine`/`pg_url` fixtures, webhook inbox, graphql functional) need a **testcontainers Postgres** (Docker) — slower and risk the `/tmp` wedge; run sparingly.

Per-fixture format check matters: after editing, `uv run ruff format --check <rendered files>` — long lines pass `ruff check` but fail `ruff format` (`[[ruff-format-check-after-inline-edits]]`); fix the wrapping in the TEMPLATE source and re-render. Final clean render + the framework gate (`uv run pytest -q --ignore=tests/acceptance && ruff check . && mypy src`) is the real gate.

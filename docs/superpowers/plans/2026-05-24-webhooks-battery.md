# Webhooks Battery (Plan 8b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `webhooks` battery — a thin HMAC-signed ingress with a DB transactional-inbox for idempotency and a builder dispatch seam — and the integrity-consistency fix its first managed-section injection requires.

**Architecture:** A `webhooks/` package (signature verify, inbox, model, builder `handle_event` seam) + an autodiscovered `routes/webhooks.py`, all conditionally rendered on `"webhooks" in batteries`. The signing secret injects into `.env.example`'s checksummed managed section + a `settings.py` field; the inbox table ships as a conditional Alembic migration. Because the `.env.example` section checksum is now battery-dependent, `framework upskill --with` regenerates the integrity manifest and `framework restore` becomes battery-set-aware.

**Tech Stack:** Python 3.12, FastAPI (`APIRouter`, `Request`, WebSocket-free), `hmac`/`hashlib`, SQLAlchemy + Alembic, pydantic-settings, Copier conditional rendering, pytest (+ testcontainers Postgres for the generated functional tests).

**Source spec:** `docs/superpowers/specs/2026-05-24-webhooks-battery-design.md`

> **Grounding corrections vs. the spec's shorthand:** the env var is **`APP_WEBHOOK_SIGNING_SECRET`** (settings `env_prefix="APP_"`), field `webhook_signing_secret`, read in the route via `request.app.state.settings`. `.env.example` is currently a **verbatim** file → it becomes `.env.example.jinja`. The `webhooks/` package files use **relative imports**, so they are plain `.py` (verbatim) inside the conditional dir; only the route, the migration, and the generated test use templated `.jinja` names.

---

## Standing rules for every task

- **TDD** where the artifact is framework source or render-observable: failing test → red → minimum → green → commit. The battery's *runtime behavior* (signature/dedup/route) is **template payload**, so it's verified by the **generated functional test** (shipped in the battery, run under the acceptance suite, Task 6) + the **render tests** — not by framework-level unit tests.
- **Commit-gate hook:** bump the `**Last updated:**` line in `CLAUDE.md` (datetime + `PDT` + one-clause note) and `git add CLAUDE.md` in every commit step. `git add` and `git commit` are SEPARATE Bash calls; avoid the literal word "commit" in Bash `description` fields.
- Run only targeted tests per task; clear `/tmp/pytest-of-chris/*` before any Docker acceptance run (Task 6).
- Per-task gate: `uv run pytest -q <touched>`, `uv run ruff check .`, `uv run mypy src`.
- `src/framework_cli/template/` is payload (not linted/typed as framework source) — validated by rendering + acceptance.
- **Conditional-path idioms (8a-1, spike-proven):** a templated filename that renders empty is skipped (`{{ 'x.py' if 'webhooks' in batteries else '' }}.jinja`); a templated dir name `{% if "webhooks" in batteries %}webhooks{% endif %}` is included/skipped. When creating brace/percent-named files, write the exact literal path and verify with `ls`.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/framework_cli/batteries.py` (modify) | Register the `webhooks` `BatterySpec`. | 1 |
| `template/.../{% if "webhooks" in batteries %}webhooks{% endif %}/{signature,inbox,models,handler,__init__}.py` (create) | The battery package: HMAC verify, inbox record, `WebhookEvent` model, the `handle_event` seam. Relative imports → plain `.py`. | 2 |
| `template/.../routes/{{ 'webhooks.py' if 'webhooks' in batteries else '' }}.jinja` (create) | Autodiscovered `POST /webhooks` ingress route. | 2 |
| `template/tests/functional/{{ 'test_webhooks.py' if 'webhooks' in batteries else '' }}.jinja` (create) | Generated functional test (signature/dedup/route) — runs in the rendered project. | 2 |
| `template/.env.example` → `.env.example.jinja` (rename+modify) | Inject `APP_WEBHOOK_SIGNING_SECRET=` into the managed section. | 3 |
| `template/.../config/settings.py.jinja` (modify) | Conditional `webhook_signing_secret` field. | 3 |
| `template/migrations/versions/{{ '0002_webhook_events.py' if ... }}.jinja` (create) | Conditional inbox-table migration. | 3 |
| `template/migrations/env.py.jinja` (modify) | Conditional import of the battery model (for autogenerate correctness). | 3 |
| `src/framework_cli/integrity/restore.py` (modify) | `_answers()` preserves the `batteries` list (battery-aware restore). | 4 |
| `src/framework_cli/upskill.py` (modify) | Regenerate the manifest after `run_update`. | 5 |
| `tests/test_copier_runner.py`, `tests/test_cli.py`, `tests/integrity/...`, `tests/test_upskill.py`, `tests/acceptance/test_rendered_project.py` (modify) | Render + CLI + integrity + acceptance tests. | 1–6 |

---

## Task 1: Register the `webhooks` battery

**Files:** Modify `src/framework_cli/batteries.py`; Test `tests/test_batteries.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_batteries.py`:

```python
def test_webhooks_is_registered():
    from framework_cli.batteries import get_battery

    spec = get_battery("webhooks")
    assert spec.name == "webhooks" and spec.requires == () and spec.gates_agent is None
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_batteries.py -k webhooks -q` → FAIL (`unknown battery: webhooks`).

- [ ] **Step 3: Register it** — in `src/framework_cli/batteries.py`, add to `_BATTERIES`:

```python
    "webhooks": BatterySpec(
        "webhooks", "Signed inbound webhook ingress (HMAC) with an idempotent inbox"
    ),
```

- [ ] **Step 4: Run green** — `uv run pytest tests/test_batteries.py -q` → PASS.

- [ ] **Step 5: Gate + commit** — ruff + mypy clean; bump CLAUDE.md (`8b Task 1: register webhooks battery`):
```bash
git add src/framework_cli/batteries.py tests/test_batteries.py CLAUDE.md
```
```bash
git commit -m "feat(batteries): register the webhooks battery

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: The webhooks battery package + route + generated test

**Files:** Create the `webhooks/` package, `routes/webhooks.py`, `tests/functional/test_webhooks.py` (all conditional template payload); Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render test** — add to `tests/test_copier_runner.py`:

```python
def test_render_without_webhooks_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "src" / "demo" / "routes" / "webhooks.py").exists()
    assert not (dest / "src" / "demo" / "webhooks").exists()


def test_render_with_webhooks_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    pkg = dest / "src" / "demo" / "webhooks"
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").is_file()
    assert (pkg / "signature.py").is_file() and (pkg / "inbox.py").is_file()
    assert (pkg / "models.py").is_file() and (pkg / "handler.py").is_file()
    assert (dest / "tests" / "functional" / "test_webhooks.py").is_file()
    assert "router" in (dest / "src" / "demo" / "routes" / "webhooks.py").read_text()
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_copier_runner.py -k webhooks -q` → FAIL.

- [ ] **Step 3: Create the `webhooks/` package** (under the conditional dir `src/framework_cli/template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/`; all plain `.py`, relative imports):

`__init__.py` — empty.

`signature.py`:
```python
"""HMAC-SHA256 signature verification for inbound webhooks."""

from __future__ import annotations

import hashlib
import hmac


def verify(raw_body: bytes, signature: str, secret: str) -> bool:
    """True iff `signature` is the hex HMAC-SHA256 of `raw_body` under `secret`.

    An empty secret (unconfigured) rejects everything. Comparison is constant-time.
    """
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

`models.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class WebhookEvent(Base):
    """Idempotency inbox: one row per processed webhook (transactional dedup)."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processed")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`inbox.py`:
```python
"""The transactional inbox: dedup by inserting a row keyed on the webhook's idempotency key."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import WebhookEvent


def record(session: Session, key: str) -> None:
    """Insert the inbox row; flush so the UNIQUE constraint fires now (duplicate → IntegrityError)."""
    session.add(WebhookEvent(idempotency_key=key))
    session.flush()
```

`handler.py`:
```python
"""The builder seam: replace `handle_event` with your webhook logic.

Keep it FAST — this runs inline in the request. Heavy or slow work (external calls, big
writes) belongs behind the `workers` battery (`framework upskill --with workers`); add it
and dispatch from here to a Celery task instead of processing inline.
"""

from __future__ import annotations

from ..logging_config import get_logger


def handle_event(event: dict) -> None:
    """Process a verified, de-duplicated webhook event. REPLACE THIS with your logic."""
    get_logger().info("webhook_event", event_type=event.get("type", "unknown"))
```

- [ ] **Step 4: Create the route** `src/framework_cli/template/src/{{package_name}}/routes/{{ 'webhooks.py' if 'webhooks' in batteries else '' }}.jinja`:

```python
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.engine import get_session
from ..webhooks.handler import handle_event
from ..webhooks.inbox import record
from ..webhooks.signature import verify

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
_SIGNATURE_HEADER = "X-Webhook-Signature"


@router.post("/webhooks")
async def receive_webhook(request: Request, session: SessionDep) -> Response:
    """Verify the HMAC signature, dedup via the inbox, dispatch inline, return fast.

    A redelivered event (same body) is a no-op 200. Heavy processing belongs behind the
    workers battery — see webhooks/handler.py.
    """
    raw = await request.body()
    secret = request.app.state.settings.webhook_signing_secret
    if not verify(raw, request.headers.get(_SIGNATURE_HEADER, ""), secret):
        return Response(status_code=401)
    key = hashlib.sha256(raw).hexdigest()
    try:
        record(session, key)
        handle_event(await request.json())
        session.commit()
    except IntegrityError:
        session.rollback()
        return Response(status_code=200)  # duplicate delivery — already processed
    return Response(status_code=200)
```

- [ ] **Step 5: Create the generated functional test** `src/framework_cli/template/tests/functional/{{ 'test_webhooks.py' if 'webhooks' in batteries else '' }}.jinja`:

```python
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.db.engine import build_session_factory, get_session
from {{ package_name }}.main import create_app

_SECRET = "test-signing-secret"


def _sign(body: bytes) -> str:
    return hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(engine: Engine):
    factory = build_session_factory(engine)

    def override():
        with factory() as session:
            yield session

    app = create_app(Settings(webhook_signing_secret=_SECRET, database_url=str(engine.url)))

    def _override_session():
        yield from override()

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as c:
        yield c
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE webhook_events RESTART IDENTITY CASCADE"))
        conn.commit()


def test_valid_signature_is_accepted(client: TestClient):
    body = json.dumps({"type": "ping"}).encode()
    r = client.post("/webhooks", content=body, headers={"X-Webhook-Signature": _sign(body)})
    assert r.status_code == 200


def test_bad_signature_is_rejected(client: TestClient):
    body = json.dumps({"type": "ping"}).encode()
    r = client.post("/webhooks", content=body, headers={"X-Webhook-Signature": "bad"})
    assert r.status_code == 401


def test_duplicate_delivery_is_deduped(client: TestClient):
    body = json.dumps({"type": "ping", "id": "evt_1"}).encode()
    headers = {"X-Webhook-Signature": _sign(body)}
    assert client.post("/webhooks", content=body, headers=headers).status_code == 200
    assert client.post("/webhooks", content=body, headers=headers).status_code == 200  # no-op
```

> **Note (implementer):** confirm `create_app` accepts a `Settings` and stores it on `app.state.settings` (it does — `main.py:31`/`:36`). The `engine` fixture (Alembic-migrated test Postgres) comes from the project's `tests/conftest.py`; with the webhooks battery the `0002` migration creates `webhook_events`, so `alembic upgrade head` provisions it. The `_override_session` indirection avoids the generator-typing issue; if the existing conftest's override style differs, match it.

- [ ] **Step 6: Run green + full render suite** — `uv run pytest tests/test_copier_runner.py -q` → PASS (with/without-webhooks + all existing). ruff + mypy clean.

- [ ] **Step 7: Commit** — bump CLAUDE.md (`8b Task 2: webhooks package + route + generated test`):
```bash
git add -A src/framework_cli/template
git add tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(template): webhooks battery package, ingress route, and generated functional test

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: The injection surface (secret, settings field, migration)

**Files:** Rename `template/.env.example` → `.env.example.jinja` (+ inject); modify `config/settings.py.jinja`, `migrations/env.py.jinja`; create the conditional migration; Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Failing render tests** — add to `tests/test_copier_runner.py`:

```python
def test_render_webhooks_secret_in_env_managed_section(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    env = (dest / ".env.example").read_text()
    begin, end = env.index("# FRAMEWORK:BEGIN"), env.index("# FRAMEWORK:END")
    assert "APP_WEBHOOK_SIGNING_SECRET=" in env[begin:end]  # inside the managed section
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "webhook_signing_secret" in settings
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").is_file()


def test_render_no_webhooks_secret_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "WEBHOOK_SIGNING_SECRET" not in (dest / ".env.example").read_text()
    assert "webhook_signing_secret" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert not (dest / "migrations" / "versions" / "0002_webhook_events.py").exists()
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_copier_runner.py -k "webhooks_secret or no_webhooks_secret" -q` → FAIL.

- [ ] **Step 3: `.env.example` → `.env.example.jinja` + inject** — `git mv src/framework_cli/template/.env.example src/framework_cli/template/.env.example.jinja`, then inject the secret inside the managed section (just before `# FRAMEWORK:END`). The block (mind Jinja whitespace — verify the rendered section has no stray blank lines breaking it):

```
APP_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app
{% if "webhooks" in batteries %}# Webhook signing secret — HMAC-SHA256 verification of inbound webhooks (set per environment).
APP_WEBHOOK_SIGNING_SECRET=
{% endif %}# FRAMEWORK:END
```

(The file has no other `{{ }}`/`{% %}`, so renaming to `.jinja` is otherwise a no-op render. `.env.example` stays in `HYBRID_TRACKED`; it renders to the same path.)

- [ ] **Step 4: settings field** — in `config/settings.py.jinja`, after the `database_url` field, add:

```python
{% if "webhooks" in batteries %}
    # Webhook ingress: HMAC-SHA256 signing secret (read from APP_WEBHOOK_SIGNING_SECRET).
    webhook_signing_secret: str = ""
{% endif %}
```

- [ ] **Step 5: conditional migration** — create `src/framework_cli/template/migrations/versions/{{ '0002_webhook_events.py' if 'webhooks' in batteries else '' }}.jinja`:

```python
"""webhook idempotency inbox

Revision ID: 0002
Revises: 0001

"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_webhook_events_idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
```

- [ ] **Step 6: env.py model import** — in `migrations/env.py.jinja`, after the `from {{ package_name }}.db import models` line, add (so autogenerate sees the battery table when active):

```python
{% if "webhooks" in batteries %}from {{ package_name }}.webhooks import models as _webhook_models  # noqa: F401
{% endif %}
```

- [ ] **Step 7: Run green + full render suite** — `uv run pytest tests/test_copier_runner.py -q` → PASS. Render once and eyeball the `.env.example` managed section is intact (markers + the secret line, no broken blank lines). ruff + mypy clean.

- [ ] **Step 8: Commit** — bump CLAUDE.md (`8b Task 3: webhooks injection — secret, settings, migration`):
```bash
git add -A src/framework_cli/template
git add tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(template): inject webhook secret/settings/migration (first managed-section injection)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Battery-aware `restore`

**Files:** Modify `src/framework_cli/integrity/restore.py`; Test `tests/test_cli.py` (or `tests/integrity/`).

- [ ] **Step 1: Failing test** — add to `tests/test_cli.py`:

```python
def test_restore_env_example_preserves_webhooks_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    project = tmp_path / "my-app"
    env = project / ".env.example"
    env.write_text(env.read_text().replace("APP_WEBHOOK_SIGNING_SECRET=", "APP_WEBHOOK_SIGNING_SECRET=tampered"))
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["restore", ".env.example"]).exit_code == 0
    # restore re-renders WITH the recorded batteries -> the secret line is back, integrity green
    assert "APP_WEBHOOK_SIGNING_SECRET=" in (project / ".env.example").read_text()
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_cli.py -k restore_env_example_preserves -q` → FAIL: `_answers()` `str(v)`-coerces `batteries` to a string, so the battery-conditional re-render drops/garbles the secret line (and/or integrity mismatches).

- [ ] **Step 3: Fix `_answers`** — in `src/framework_cli/integrity/restore.py`, change `_answers` to preserve non-string answer values (notably the `batteries` list):

```python
def _answers(project: Path) -> dict[str, object]:
    answers = project / _ANSWERS_REL
    if not answers.is_file():
        raise ValueError(
            f"{_ANSWERS_REL} is missing — cannot determine which template version to restore from"
        )
    data = yaml.safe_load(answers.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}
```

(Update the return-type annotation to `dict[str, object]`; `render_project` already accepts `Mapping[str, object]` since 8a-1. Any caller that passed this dict to `render_project` is unaffected — string answers stay strings; `batteries` stays a list.)

- [ ] **Step 4: Run green** — `uv run pytest tests/test_cli.py -k restore -q` + the existing restore test → PASS. ruff + mypy clean.

- [ ] **Step 5: Commit** — bump CLAUDE.md (`8b Task 4: battery-aware restore`):
```bash
git add src/framework_cli/integrity/restore.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "fix(integrity): restore re-renders with the recorded batteries (preserve the list answer)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: `upskill` regenerates the manifest (+ new-integrity test)

**Files:** Modify `src/framework_cli/upskill.py`; Test `tests/test_upskill.py`, `tests/test_cli.py`.

- [ ] **Step 1: Failing test** — add to `tests/test_upskill.py` (monkeypatch the heavy bits; assert the manifest is regenerated after the update):

```python
def test_upskill_regenerates_the_manifest(tmp_path, monkeypatch):
    import framework_cli.upskill as up

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".copier-answers.yml").write_text("project_name: demo\nbatteries: []\n")

    monkeypatch.setattr(up, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(up, "run_update", lambda *a, **k: None)
    monkeypatch.setattr(up.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    captured = {}
    monkeypatch.setattr(up, "write_manifest", lambda project, version: captured.update(project=project))

    assert up.upskill_project(proj) is True
    assert captured["project"] == proj  # manifest regenerated after the update
```

- [ ] **Step 2: Run red** — `uv run pytest tests/test_upskill.py -k regenerates_the_manifest -q` → FAIL (`upskill` doesn't import/call `write_manifest`).

- [ ] **Step 3: Regenerate the manifest in `upskill_project`** — in `src/framework_cli/upskill.py`, import the manifest helpers and call `write_manifest` after `run_update` (after `record_batteries`, before `task test`):

```python
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
```

In `upskill_project`, after the `record_batteries(project, effective)` line and before the `task test` block:

```python
    # The update may have changed managed sections / locked files (incl. battery-conditional
    # lines like the webhooks secret in .env.example). Re-record the integrity manifest so
    # `framework integrity` reflects the upgraded state.
    write_manifest(project, installed_framework_version())
```

- [ ] **Step 4: new-integrity test (bundled, no Docker)** — add to `tests/test_cli.py`:

```python
def test_new_with_webhooks_passes_integrity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App", "--with", "webhooks"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "my-app")
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 0, result.output  # the battery-active .env.example checksum matches
```

- [ ] **Step 5: Run green** — `uv run pytest tests/test_upskill.py tests/test_cli.py -q` → PASS (incl. the existing real-upskill round-trip tests, which now also regenerate the manifest harmlessly). ruff + mypy clean.

- [ ] **Step 6: Commit** — bump CLAUDE.md (`8b Task 5: upskill regenerates the manifest`):
```bash
git add src/framework_cli/upskill.py tests/test_upskill.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "fix(integrity): upskill regenerates the manifest (managed sections can change on update)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: With-webhooks acceptance variant (Docker)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Read the existing acceptance helpers** — confirm the render helper, `_docker_available` skipif, and the `uv sync` + `bash scripts/coverage.sh 70 unit functional` invocation used by the sibling `test_rendered_project_with_websockets_battery_passes` (8a-1). Mirror it.

- [ ] **Step 2: Add the variant** — render with `{**DATA, "batteries": ["webhooks"]}`, assert the battery files exist, then run the generated suite so `tests/functional/test_webhooks.py` is collected (it needs the testcontainers Postgres + the `0002` migration). Assert returncode 0 and that the webhook functional tests were exercised — key on `webhooks` reaching real coverage (e.g. `routes/webhooks.py` not at import-only %), mirroring the websockets variant's coverage assertion. Follow the sibling's exact structure/skipif.

- [ ] **Step 3: Run it** — `rm -rf /tmp/pytest-of-chris/*` then `uv run pytest tests/acceptance/test_rendered_project.py -k webhooks -q` → PASS (the generated webhook functional tests pass against real Postgres; the `0002` migration creates `webhook_events`).

- [ ] **Step 4: Commit** — bump CLAUDE.md (`8b Task 6: with-webhooks acceptance variant`):
```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
```
```bash
git commit -m "test(acceptance): rendered project with the webhooks battery is green

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Final whole-branch review (controller, after all tasks)

- [ ] `uv run pytest -q` — full suite incl. the Docker acceptance suite (both the websockets + webhooks variants), all green. Clear `/tmp/pytest-of-chris/*` first.
- [ ] `uv run ruff check .`, `uv run mypy src`, `uv lock --check` — clean (no new runtime deps; `hmac`/`hashlib` are stdlib).
- [ ] **Render both ways** and confirm the no-webhooks render is byte-identical to today except the intended additions appear only with the battery; the `.env.example` managed section is well-formed in both.
- [ ] **The two integrity properties, end to end:** `framework new --with webhooks` → `framework integrity --ci` green; and `framework restore .env.example` on that project keeps the secret + stays green.
- [ ] **A real `upskill --with webhooks` round-trip** (extend the 8a-1 `_battery_source_repo` harness with a hybrid `.env`-style managed file + a manifest, or run against the bundled source): confirm the secret is injected, `read_batteries` returns `["webhooks"]`, AND the regenerated manifest makes `framework integrity` pass. If a faithful harness is impractical, state what was verified vs. inferred (the regen is unit-tested in Task 5; the bundled `new` path is integration-tested).
- [ ] Wheel: `uv build` ships `batteries.py` (and `webhooks` battery files are template payload, not in the wheel — confirm fixtures/payload are excluded as in 7d/8a-1).

Then **superpowers:finishing-a-development-branch**: finalize the CLAUDE.md narrative + the meta-plan 8b row (→ ✅ merged), FF-merge to `master`, push.

---

## Self-review (against the spec)

**Spec coverage:** §1 scope (thin signed ingress, standalone, composes-later) — Tasks 1-2; §2 architecture (route/signature/inbox/model/handler seam) — Task 2; §3 injection (`.env.example` secret, settings field, migration, env.py import) — Task 3; §4 integrity consistency (new ✓ via existing write-after-render + the Task-5 new-integrity test; upskill regen — Task 5; restore battery-aware — Task 4; downskill inverse — recorded for 8a-2, not built here); §5 testing — render (2,3), generated functional (2), integrity (4,5), acceptance (6); §6 deferrals (workers, review heuristic, SECRETS.md) — untouched, recorded. ✔

**Placeholder scan:** concrete code/commands throughout. Task 6 defers to the sibling acceptance helper (a read step, not a placeholder) since it must mirror the file's exact harness.

**Type consistency:** `verify(raw_body: bytes, signature: str, secret: str) -> bool`; `record(session, key)`; `WebhookEvent(idempotency_key UNIQUE)`; `handle_event(event: dict)`; the route reads `request.app.state.settings.webhook_signing_secret`; `_answers(project) -> dict[str, object]`; `upskill_project` calls `write_manifest(project, installed_framework_version())`. The env var is `APP_WEBHOOK_SIGNING_SECRET` end-to-end (prefix-correct), the field `webhook_signing_secret`. Names align across tasks.

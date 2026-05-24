# Webhooks Battery (Plan 8b) — Design Spec

**Date:** 2026-05-24
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8a-1 (the battery mechanism: `batteries.py` registry, `--with`, conditional rendering, router autodiscovery, the framework-owned `batteries` record), Plan 6a-2 (the `FRAMEWORK:BEGIN/END` hybrid managed sections + checksums), Plan 3c (the DB layer: models/repository/migrations). Second battery of Plan 8 (after the websockets vehicle).

---

## 1. Purpose & scope

The `webhooks` battery scaffolds a **thin, signed ingress** for inbound webhooks: signature verification + idempotent receipt + a hand-off seam the builder fills with their logic. It is the first battery to **inject into a checksummed managed section** (`.env.example`), so it also builds the managed-section-injection mechanism 8a-1 deferred — and the integrity-consistency handling that injection requires.

**Settled architecture (brainstorm): a lightweight standalone path that composes with workers later.**
- **Standalone (this battery):** verify → dedup via a DB **transactional inbox** → call the builder's handler **inline** in one transaction → return `2xx` fast. Correct and crash-safe for small/medium volume.
- **Composed with workers (future, 8c):** the same **dispatch seam** instead enqueues a Celery task and returns immediately; the worker consumes idempotently with the DLQ. Out of scope here, but the seam is shaped so workers drops in with no route change.

**In scope:**
- `routes/webhooks.py` (autodiscovered) + a `webhooks/` package (`signature.py`, `inbox.py`, `models.py`, `handler.py`).
- HMAC-SHA256 signature verification against `WEBHOOK_SIGNING_SECRET`.
- A DB transactional inbox (a `webhook_events` table + a conditional Alembic migration) keyed on `sha256(raw_body)`.
- The **dispatch seam** (`handle_event`), builder-overridable.
- **Managed-section / shared-file injection:** the secret into `.env.example` (checksummed hybrid section) + a `settings.py` field.
- **Integrity consistency:** `upskill --with` regenerates the manifest; `restore` becomes battery-set-aware (the §4 coupling).

**Out of scope (deferred):**
- The **workers composition** (enqueue instead of inline) → **Plan 8c**; the seam is designed for it.
- A `review-architecture` **battery-aware heuristic** that flags a callback/simplistic-webhook handler doing heavy/blocking work inline and recommends `--with workers` — **deferred (lands ~8c when workers is the recommendation target); recorded as related future work.** Keys on "heavy work inline," not "any inline handler" (the lightweight case is legitimate).
- The canonical **`SECRETS.md`** → **Plan 9**; this battery documents `WEBHOOK_SIGNING_SECRET` in `.env.example` for now.
- **`--downskill`** (incl. the manifest inverse + the migration-removal wrinkle) → **Plan 8a-2** (this design records both as explicit 8a-2 requirements).

## 2. Architecture & data flow

- **`routes/webhooks.py`** — autodiscovered `APIRouter` exposing `POST /webhooks`. Reads the **raw body** (`await request.body()`), reads the signature header (`X-Webhook-Signature`), verifies HMAC-SHA256 (constant-time) → `401` on mismatch. On valid signature: `key = sha256(raw_body).hexdigest()`; open one DB transaction: insert the inbox row → on duplicate (`IntegrityError`) return `200` (already processed, no re-dispatch); else parse the JSON event and call `handle_event(event)` inline → commit → `200`.
- **`webhooks/signature.py`** — `verify(raw_body: bytes, signature: str, secret: str) -> bool` (HMAC-SHA256 hex digest, `hmac.compare_digest`).
- **`webhooks/inbox.py`** — `record(session, key) -> None` inserts a `WebhookEvent`; the UNIQUE constraint on `idempotency_key` makes a duplicate raise `IntegrityError` (caught by the route → dedup). The idempotency key defaults to `sha256(raw_body)` (provider-agnostic; a docstring notes builders with a stable provider event id should key on that instead).
- **`webhooks/models.py`** — `WebhookEvent(id, idempotency_key UNIQUE, received_at, status)`, a SQLAlchemy model on the project's `Base`, imported by `inbox.py`.
- **`webhooks/handler.py`** — `handle_event(event: dict) -> None`, the **builder-overridable seam**. Ships a stub that structured-logs the event and is clearly marked "replace with your logic." Its docstring states the fast-return discipline: heavy/slow/blocking work belongs behind the **workers** battery (`--with workers`), not inline — so the lightweight default stays correct under sender timeouts.

## 3. The injection surface & persistence

- **`.env.example`** (a 6a-2 hybrid `FRAMEWORK:BEGIN/END` file): inject `WEBHOOK_SIGNING_SECRET=` into the managed section, gated `{% if "webhooks" in batteries %}`. **First battery-conditional line inside a checksummed managed section** — this builds the managed-section-injection mechanism 8a-1 specified but deferred.
- **`settings.py`** (builder-extendable app source — **not** in `LOCKED_TRACKED`, so it does *not* affect the manifest): a `webhook_signing_secret: str` pydantic-settings field, gated `{% if "webhooks" in batteries %}`.
- **DB transactional inbox:** the `WebhookEvent` model lives in the battery package; a **conditional Alembic migration** (`migrations/versions/0002_webhook_events.py`, `down_revision = "0001"`) creates the table, rendered only when the battery is active.
  - **Known composition wrinkle (record for later):** a per-battery migration that chains off `0001` does not compose if a *second* migration-shipping battery is added (two heads off `0001`). Fine for webhooks-alone (the only migration-shipping battery today); the general solution (merge migrations / dynamic head) is deferred until a second one exists. This also feeds 8a-2: **you can't remove an applied migration by deleting its file** — removal needs a down-migration, so battery migrations are a genuine `--downskill` hard case.

## 4. Integrity consistency (the manifest ↔ battery coupling)

Because the `.env.example` managed-section checksum now **depends on the active battery set**, every battery-set-changing op must re-record it. Scope is narrow: only `.env.example` is affected (it is the one `HYBRID_TRACKED` file webhooks injects into; `settings.py` is not checksummed).

1. **`framework new --with webhooks`** — already correct: `write_manifest` runs *after* render, checksumming the battery-active section. No change.
2. **`framework upskill --with webhooks`** — must **regenerate the manifest** (`write_manifest`) after `run_update`, so the injected secret line is reflected in the recorded checksum. **This also closes a latent gap**: `upskill` does not regenerate the manifest today, so any framework-version change to a managed section would fail `framework integrity` — webhooks forces the fix. (A plain `upskill` regenerating the manifest is correct and harmless.)
3. **`framework restore .env.example`** — must re-render with the project's **real battery set**. `restore`'s `_answers()` currently does `str(v)` on every answer, coercing the `batteries` list to a string (it only "works" by accidental substring match). Fix `_answers()` to pass `batteries` as the actual list (via `read_batteries`), so restore reproduces the battery-active section and matches the recorded checksum.
4. **`--downskill` (Plan 8a-2)** — the inverse: after removing the battery, regenerate the manifest so `integrity` passes and `restore` reproduces the post-removal (battery-absent) section. **Recorded here as an explicit 8a-2 requirement.**

**The rule webhooks establishes:** any op that changes the battery set re-records the affected managed-section checksums — `new` (already), `upskill --with` (this plan, + the latent plain-upskill fix), `--downskill` (8a-2).

## 5. Testing

- **`signature.verify`** (unit, hermetic): a correct HMAC passes; a tampered body/signature/secret fails; constant-time path exercised.
- **inbox dedup** (functional, real Postgres): two posts of the same signed body → first processes (`handle_event` called once), second is a `200` no-op (the UNIQUE constraint dedups); distinct bodies both process.
- **route** (functional, real Postgres): valid signature → `200` + handler invoked; invalid/missing signature → `401`; malformed JSON after a valid signature → a clean `4xx` (not a 500). Lands in `tests/functional/` (collected by the project's `testpaths`).
- **render (`tests/test_copier_runner.py`):** with `batteries=["webhooks"]` → the route, `webhooks/` package, the migration, the `.env.example` secret line (inside the managed markers), and the `settings.py` field all render; without it → none do and `.env.example`/`settings.py` are unchanged.
- **integrity consistency:**
  - `framework new --with webhooks` → `framework integrity --ci` passes (the recorded `.env.example` section checksum matches the battery-active content).
  - `framework upskill --with webhooks` (real `run_update` round-trip, the 8a-1 harness extended) → the secret line is injected AND `framework integrity --ci` passes (manifest regenerated).
  - `framework restore .env.example` on a `--with webhooks` project reproduces the secret line (battery-aware re-render) and leaves `integrity` green.
- **acceptance (Docker):** a with-webhooks rendered variant whose generated suite is green (the functional webhook tests run against the testcontainers Postgres), mirroring the 8a-1 with-websockets variant.

## 6. Self-review

- **Placeholders:** none — the route flow, the HMAC scheme, the transactional-inbox dedup, the seam, the managed-section injection, the integrity-consistency handling, and the tests are concrete. The workers composition, the review-architecture heuristic, `SECRETS.md`, and `--downskill` are explicitly deferred (not hand-waved), each with where it lands.
- **Internal consistency:** the dispatch seam is the single swap point for the future workers path; the transactional inbox makes dedup + effect atomic (no marked-but-unprocessed window); the integrity rule (re-record on battery-set change) is applied to every op and matches 8a-1's framework-owned `batteries` record.
- **Scope:** one cohesive battery (ingress + verify + inbox + seam) plus the integrity-consistency fix it necessitates (small, agreed to coexist). Heavier concerns deferred to 8c/8a-2/9.
- **Ambiguity:** "idempotency" is pinned to a DB transactional inbox keyed on `sha256(raw_body)` (builder-overridable to a provider event id); "signature" to HMAC-SHA256 with a constant-time compare; the migration-chain + migration-removal limitations are stated as known wrinkles feeding 8a-2.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8b.*

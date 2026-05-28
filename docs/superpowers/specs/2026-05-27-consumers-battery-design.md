# 8h — `consumers` Battery (Pact contract testing)

**Date:** 2026-05-27
**Status:** Design approved — ready for implementation plan
**Plan 8 slice:** 8h (consumers / Pact)
**Predecessors:** 5a (the generated-project CI pipeline + the OpenAPI schema-contract job, which this complements), 3c (the baseline `/items` provider API + seed), 8a-1 (battery mechanism), the `dependency` review agent (already triggers on `pyproject.toml`)

---

## 1. Summary & Motivation

Adds the `consumers` battery: **consumer-driven contract testing with `pact-python` (v3)**, demonstrating the **full Pact loop** in the generated service — the app as a Pact **consumer** of a downstream service, and as a Pact **provider** of its own `/items` API.

The framework already ships **schema** contract testing (the CI `contract` job: `openapi.json` staleness + `oasdiff` breaking-change). Pact is complementary and different: **example-/expectation-based, consumer-driven** contracts that catch integration breakage a schema diff can't (a consumer relying on a specific shape/value; a provider quietly dropping a field a consumer needs). This battery teaches both halves.

Pacts are **local JSON files** (`pacts/`); a real **Pact Broker** is an opt-in env-var escape hatch (no broker service is shipped) — matching the framework's minimize-services / managed-escape-hatch ethos.

### Scope

**In scope:** a gated downstream client (`clients/inventory.py`) + a consumer Pact test (generates a pact against a mock server); a committed example consumer pact for `/items` + a provider verification test (replays it against the running app); pact storage in `pacts/` + documented broker hooks; conditional `pact-python` test dep + `inventory_url` setting; gated CI; registration + battery tests.

**Deferred (named):** a running Pact Broker service; a `review-contracts` review agent; `pact-broker can-i-deploy` deploy-gating; message/async (non-HTTP) pacts; wiring the inventory client into a live `/items` route (the client + its consumer test is the demonstration — no route wiring needed).

---

## 2. Archetype

A **testing/contract** battery, `requires=()`, no `gates_agents`. It adds test-only tooling (`pact-python`), a small app-side client + a settings field, contract tests, an example pact fixture, and gated CI — **no new runtime service, no new framework Python dependency, no migration**.

---

## 3. Consumer Flow — the app consumes a downstream service

The baseline app makes no outbound HTTP calls, so the battery introduces an example downstream dependency (a fictional **inventory** service) to demonstrate the consumer-driven flow.

- **`src/{{package_name}}/{% if "consumers" in batteries %}clients{% endif %}/inventory.py`** — a typed httpx client:
  - `get_stock(item_id: int) -> int`: `GET {settings.inventory_url}/inventory/{item_id}` → parses `{"item_id": int, "in_stock": int}` → returns `in_stock`; raises on non-2xx.
  - Uses `httpx` (already an available dep — it's in the dev group for tests; the client needs it at runtime, so add `httpx` to the project's runtime deps gated on `consumers`, OR confirm it's already a runtime dep). The plan resolves the exact dep placement.
- **`settings.py`** (gated field): `inventory_url: str = "http://inventory:8080"` (an in-network default; overridable per env).
- **`tests/contract/{% if "consumers" in batteries %}test_consumer_inventory.py{% endif %}`** — the consumer Pact test (FAST, mocked, no DB/network → functional tier):
  - Define the expected interaction: given "item 1 is in stock", `GET /inventory/1` → `200` `{"item_id": 1, "in_stock": 5}`.
  - Start the Pact **mock server**, point the client at its URL, call `get_stock(1)`, assert it returns `5`.
  - On success Pact **writes** `pacts/<app>-inventory.json` (the consumer's contract with the inventory provider).

This is the signature consumer-driven flow: the consumer's real client code, run against a mock that records expectations into a shareable contract.

## 4. Provider Flow — the app's `/items` API is verified against a consumer pact

- **`pacts/examplewebapp-{{package_name}}.json`** — a **committed example consumer pact** (a fixture representing an example web-app consumer of this service): one interaction, given provider state `"items exist"`, `GET /items` → `200`, body a JSON array of `{"id": int, "name": str}` (Pact matchers: type-match the list elements, not exact values). This gives provider verification something concrete to replay in a single repo.
- **`tests/contract/{% if "consumers" in batteries %}test_provider_items.py{% endif %}`** — the provider verification test (ACCEPTANCE-tier — needs the app running over a real DB):
  - Bring up the app over the testcontainers Postgres (reuse the existing `engine`/`api_client` harness pattern), seeded with the baseline items (alpha/beta) to satisfy the `"items exist"` provider state.
  - Use Pact's `Verifier` to replay `pacts/examplewebapp-{{package_name}}.json` against the running app's base URL; assert all interactions verify.
  - **Provider states:** map `"items exist"` to a setup that ensures seeded items are present (the baseline seed already loads alpha/beta; the test wires a provider-state handler or relies on the seeded fixture).

Provider verification needs a real HTTP server + DB, so it lives in the acceptance/contract tier (not fast-tier), alongside the other Docker-gated acceptance tests.

## 5. Pact storage + broker hooks

- **`pacts/`** holds contracts. The **example consumer pact** (`pacts/examplewebapp-{{package_name}}.json`) is **committed** (provider verification replays it). **Generated** pacts (the consumer test's `pacts/<app>-inventory.json`) are **gitignored** (a `pacts/*.json` ignore with a `!pacts/examplewebapp-*.json` un-ignore for the committed fixture, or an equivalent precise rule).
- **Broker (opt-in, no service):** a `scripts/pact-publish.sh` + documented CI steps gated on `PACT_BROKER_URL` (+ `PACT_BROKER_TOKEN`): publish the generated consumer pact; verify the provider against broker-hosted pacts. Absent the env vars, the in-repo local-file flow is the whole demo. The generated `README`/`CLAUDE.md` convention documents the real multi-repo broker workflow (consumer publishes → provider verifies → `can-i-deploy`).

## 6. CI + test tiers

- The consumer Pact test rides the existing Python tiers (functional) via `coverage.sh` — it's fast + mocked.
- Provider verification is acceptance/contract-tier (app + DB). A gated `consumers` addition to the LOCKED `.github/workflows/ci.yml` (byte-identical without the battery — the graphql/react precedent for conditional `{%- if %}` blocks) runs the provider verification (bring up the app + DB, replay the example pact) and the env-gated broker publish/verify. The existing `contract` job (OpenAPI) is unchanged; the pact steps are additive + gated.

## 7. Dependencies, settings, registration, integrity

- **`pyproject.toml`:** conditional `pact-python>=3.4` (a **test** dependency — gated `consumers`; it ships a Rust core as a wheel). If the inventory client needs `httpx` at runtime and `httpx` is currently dev-only, add `httpx` to runtime deps gated on `consumers` (the plan confirms current `httpx` placement and does the minimal correct thing). **No new framework Python dependency.**
- **`settings.py`:** gated `inventory_url`.
- **`batteries.py`:** register `consumers` (`requires=()`, no `gates_agents`).
- **No migration** (`MIGRATION_ORDER` untouched). **No new `LOCKED_TRACKED` entries** — the conditionally-edited LOCKED files (`ci.yml`, `.gitignore`) stay byte-identical without the battery → **no baseline manifest shift**. The `clients/` package, the two contract tests, the example pact, and `scripts/pact-publish.sh` are conditional template payload.
- **downskill `consumers`:** owned files (`clients/`, `tests/contract/*`, the example pact, `pact-publish.sh`) deleted; the gated `ci.yml`/`.gitignore`/`settings.py`/`pyproject.toml` edits revert via the two-render diff (no `--force` expected — the 8b-1 byte-identity exclusion covers gated shared files).

## 8. Testing the Battery

- **Render/unit (`tests/test_copier_runner.py`):** `["consumers"]` renders `clients/inventory.py`, both contract tests, `pacts/examplewebapp-<app>.json`, the gated `ci.yml` pact steps, `inventory_url` in settings, `pact-python` in pyproject, the `pacts/` gitignore rule, `scripts/pact-publish.sh`. `[]` baseline byte-identical (no consumers strings in `ci.yml`/`.gitignore`/`settings.py`/`pyproject.toml`; no `clients/`/`tests/contract/`/`pacts/`). A freshly rendered `["consumers"]` project passes its first `pre-commit` clean.
- **Integrity:** parametrized green across `[]`, `["consumers"]`, and combinations (e.g. `["consumers","graphql"]`, `["consumers","workers"]`); no baseline manifest shift.
- **downskill `consumers`** (force=False): owned files gone, gated edits reverted, integrity green.
- **Live acceptance (`tests/acceptance/test_rendered_project.py`):** render `--with consumers`; (a) run the **consumer** Pact test (generates `pacts/<app>-inventory.json` against the Pact mock server — fast, no DB); (b) run the **provider** verification (the app over testcontainers Postgres, seeded; `Verifier` replays the committed example pact → all interactions pass). Mind the Docker-acceptance `/tmp` caveat (run sparingly, clean up). The `pact-python` v3 Rust core ships as a wheel; the plan pins the exact v3 API (`Pact`/mock-server/`Verifier`/provider-state) against 3.4.0 (the 3.x API has churned — verify at implementation).

## 9. Components & File Map

**Framework CLI (`src/framework_cli/`):**
- `batteries.py` — register `consumers`.
- (No review agent, no `migrations.py`/`LOCKED_TRACKED` change.)

**Framework tests:** `tests/test_copier_runner.py` (render + byte-identity + integrity + downskill), `tests/test_batteries.py` (registration), `tests/acceptance/test_rendered_project.py` (live consumer + provider).

**Template payload (`src/framework_cli/template/`):**
- Create: `src/{{package_name}}/{% if "consumers" in batteries %}clients{% endif %}/{__init__.py,inventory.py}`; `tests/contract/{% if "consumers" in batteries %}test_consumer_inventory.py{% endif %}` + `…/test_provider_items.py` (gated); `pacts/{% if "consumers" in batteries %}examplewebapp{% endif %}…json` (gated example pact — exact gated path per the template's conventions); `scripts/{% if "consumers" in batteries %}pact-publish.sh{% endif %}` (gated).
- Modify: `.github/workflows/ci.yml.jinja` (gated pact steps), `src/{{package_name}}/config/settings.py.jinja` (`inventory_url`), `pyproject.toml.jinja` (conditional `pact-python` + httpx-if-needed), the project `.gitignore.jinja` (`pacts/` rule), `Taskfile.yml.jinja` (gated `contract:pact` task), `README`/`CLAUDE.md` convention (broker workflow).

**Framework docs:** `CLAUDE.md` Current State + meta-plan 8h row.

---

## 10. Risks & Mitigations

- **`pact-python` v3 API churn.** The 3.x line (Rust-core rewrite) changed its consumer/provider API across releases. *Mitigation:* the plan pins the exact API against the installed `3.4.0` (consumer `Pact` + mock server context manager; `Verifier` for provider) and verifies it in a spike/early task; the live acceptance test is the proof.
- **Provider verification needs the app + DB running.** *Mitigation:* it's acceptance-tier, reusing the existing testcontainers-Postgres + app-startup harness; provider-state `"items exist"` is satisfied by the baseline seed. Not a fast-tier test.
- **`httpx` runtime placement.** The inventory client needs `httpx` at runtime; it may currently be dev-only. *Mitigation:* the plan checks and, if needed, adds `httpx` to runtime deps gated on `consumers` (no change for other batteries).
- **`.gitignore` precision for `pacts/`.** Generated pacts ignored, the example pact committed. *Mitigation:* a precise rule (`pacts/*.json` + `!pacts/examplewebapp-*.json`) verified by a render test; and the `.gitignore` baseline byte-identity (the 8g `.gitignore.jinja` is already templated).
- **Byte-identity of gated LOCKED `ci.yml`** (the 8c regression class). *Mitigation:* Jinja whitespace control + the `[]` integrity render test.
- **In-sandbox feasibility.** `pact-python`'s Rust core + the provider verification (app+DB) may be heavy/limited in-sandbox (cf. the react CI-gated caveat). *Mitigation:* scope the in-sandbox acceptance to what's tractable (the consumer test at minimum); the full loop is the CI gate — report what runs where.

---

## 11. Out of Scope / Follow-ups

- A running **Pact Broker** service (the opt-in env-var hooks cover real broker use without shipping one).
- A **`review-contracts`** review agent (flagging uncompensated provider breaking-changes / missing provider states / consumer over-coupling) — a natural addition to the review-agent set; not in 8h scope.
- `pact-broker can-i-deploy` **deploy-gating** (wire into the deploy strategy).
- **Message/async pacts** (the app's webhooks/workers are async surfaces a future message-pact battery could contract-test).
- Wiring the inventory client into a live route.

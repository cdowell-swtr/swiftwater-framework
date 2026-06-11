# Your project's interfaces

The surfaces your project exposes to the outside world — other services, browsers, partners — deserve a published, machine-readable contract wherever one exists. A scaffolded project generates and maintains those contracts for you, and CI checks them for staleness and breaking changes. This page maps each interface a project can expose, where its contract lives, and how it's kept honest.

Which interfaces you have depends on the batteries you chose at `framework new`. The REST surface is always present; the rest appear with their battery.

A note on what is **not** an interface: the `workers` battery (Celery worker + beat) is **internal background processing**, not a third-party-facing surface. It consumes a broker and runs your task code; it has no externally published contract. For how it runs, see [Run locally](run-locally.md) and [Project structure](structure.md), not this page.

## REST → OpenAPI / Swagger

The base project is a FastAPI application, so its REST surface comes with a machine-readable contract for free. FastAPI derives an OpenAPI document from your route signatures and Pydantic response models and serves three endpoints out of the box:

| URL | What it serves |
|---|---|
| `/docs` | Swagger UI — an interactive, try-it-out API explorer |
| `/redoc` | ReDoc — a clean, reference-style rendering of the same spec |
| `/openapi.json` | the raw OpenAPI document (the machine-readable contract) |

To see them, run your project and open `https://<project-slug>.localhost/docs` (or `/redoc`). The app is created with a plain `FastAPI(title=...)` in `src/<package>/main.py`, which keeps all three default routes enabled.

Beyond the live endpoints, the spec is **committed and version-controlled**. A helper exports it to a file:

```bash
task openapi:export      # → writes openapi.json
# (runs scripts/export-openapi.sh, which calls create_app().openapi())
```

The export writes the JSON straight to `openapi.json` from Python (not a stdout redirect) so stray startup log lines can't pollute the committed spec. CI then enforces it:

- If `openapi.json` is committed, CI re-exports it and **fails if it's out of date** ("Run `task openapi:export` and commit it").
- On a pull request, CI runs an [`oasdiff`](https://github.com/oasdiff/oasdiff) breaking-change check against the spec on the base branch and fails on a breaking (`ERR`) change.
- If `openapi.json` isn't committed yet, CI generates it for the run and posts a notice nudging you to commit it to start tracking the contract.

So the REST contract is generated from your code, published as Swagger/ReDoc, committed as `openapi.json`, and gated for staleness and breaking changes — no manual spec authoring.

## GraphQL → SDL + introspection

With the `graphql` battery, the project mounts a [Strawberry](https://strawberry.rocks/) code-first GraphQL endpoint at `/graphql` (see `src/<package>/routes/graphql.py`). The schema is defined in Python under `src/<package>/graphql/`, and its contract is the **SDL** (Schema Definition Language) that Strawberry generates from it.

Two ways consumers and tooling read the contract:

- **Introspection** — when the GraphQL IDE is enabled, the endpoint answers introspection queries and serves GraphiQL for interactive exploration. This is gated by a setting (`resolved_graphql_ide`): the router builds the schema with `disable_introspection=not ide`, and the decision is logged (`graphql_ide_configured`) so a prod that accidentally leaves the schema exposed is auditable. Typically introspection/IDE is on in dev and off in prod.
- **Committed SDL** — exactly like OpenAPI, the SDL is exported to a committed file:

  ```bash
  bash scripts/export-graphql-schema.sh   # → writes schema.graphql
  ```

  CI checks `schema.graphql` is current (fails if stale) and, on a PR, runs a GraphQL breaking-change diff against the base branch's schema.

So the GraphQL contract is the generated SDL — explorable live via introspection/GraphiQL, committed as `schema.graphql`, and gated the same way the OpenAPI spec is.

## Webhooks (inbound event ingress)

The `webhooks` battery adds a signed inbound webhook endpoint at `POST /webhooks` (`src/<package>/routes/webhooks.py`). It is a real, hardened ingress contract:

- **Signature verification** — every request must carry an `X-Webhook-Signature` HMAC computed with `APP_WEBHOOK_SIGNING_SECRET`; an unsigned or wrong-signature request is rejected with `401`.
- **Idempotent inbox** — the raw body is hashed (SHA-256) and recorded; a redelivery of the same event is a no-op `200` rather than double-processing. A malformed body is a `400` and is not recorded.
- **Fast acknowledgement** — the route verifies, dedups, dispatches, and returns quickly; heavy processing is meant to move behind the `workers` battery.

The handler in `src/<package>/webhooks/handler.py` is where you define what each event type means — that's your event contract.

!!! note "Known gap: no auto-generated webhook spec"
    Today there is **no machine-readable contract document** auto-generated for the webhook surface — the event shapes live in your handler code and tests, not a published schema. The standard for documenting event-driven/asynchronous APIs is [**AsyncAPI**](https://www.asyncapi.com/) (the OpenAPI analogue for messages). Emitting and gating an AsyncAPI document for webhooks the way `openapi.json` is gated for REST is a known limitation and a candidate future enhancement, not a current feature.

## WebSockets (bidirectional messaging)

The `websockets` battery adds a WebSocket route at `/ws` (`src/<package>/routes/websockets.py`) backed by a `ConnectionManager`. The scaffold's protocol is a simple echo/broadcast: each text message received is broadcast to all connected clients, connections are reaped on any disconnect, and message throughput is metered. You replace the broadcast logic with your own message protocol; the connection lifecycle and observability are already wired.

!!! note "Known gap: no auto-generated WebSocket spec"
    As with webhooks, there is **no auto-generated machine-readable contract** for the WebSocket message protocol — the message shapes are defined in your code and tests. [**AsyncAPI**](https://www.asyncapi.com/) is again the relevant standard (it covers WebSocket channels and message payloads). Publishing and gating an AsyncAPI document for the `/ws` protocol is a known limitation / future enhancement, not something the scaffold does today.

## Consumer / provider contracts → Pact

The `consumers` battery adds [Pact](https://docs.pact.io/) consumer-driven contract testing, which covers the *other* side of integration: the HTTP dependencies your project calls and the consumers that call you. It exercises both roles:

- **As a consumer** — `src/<package>/clients/inventory.py` is an example downstream client (`get_stock(base_url, item_id)`); the consumer Pact test runs it against a Pact mock server and writes the resulting contract to a pact file under `pacts/` (e.g. `pacts/<package>-inventory.json`).
- **As a provider** — `tests/contract/test_provider_pact.py` starts the **real app** over a throwaway Postgres, seeds the required provider state ("items exist"), and verifies the live `/items` API actually satisfies the committed example pact. This is the gate that catches a provider drifting away from what consumers expect.

Run both sides locally with:

```bash
task contract:pact      # consumer + provider verification
```

For a multi-repo flow, `scripts/pact-publish.sh` publishes generated pacts to a [Pact Broker](https://docs.pact.io/pact_broker) when `PACT_BROKER_URL` is set (and no-ops otherwise), so consumers publish contracts and providers verify against broker pacts. The example pact ships as a Pact v4 (`pactSpecification` 4.0) file.

## In short

| Interface | Battery | Contract | Live surface | Gated in CI |
|---|---|---|---|---|
| REST | baseline | `openapi.json` (OpenAPI) | `/docs`, `/redoc`, `/openapi.json` | staleness + `oasdiff` breaking-change |
| GraphQL | `graphql` | `schema.graphql` (SDL) | `/graphql` + introspection/GraphiQL | staleness + breaking-change diff |
| Webhooks | `webhooks` | event shapes in handler/tests (no auto spec — AsyncAPI gap) | `POST /webhooks` | signature + idempotency tests |
| WebSockets | `websockets` | message protocol in code/tests (no auto spec — AsyncAPI gap) | `/ws` | functional + unit tests |
| Consumer/provider | `consumers` | Pact files under `pacts/` | n/a (test-time) | consumer + provider verification |

REST and GraphQL ship a generated, committed, breaking-change-gated machine-readable contract. Pact covers your HTTP integrations from both sides. Webhooks and WebSockets are hardened and observable, but their *machine-readable* contract is a known gap — AsyncAPI is the standard a future enhancement would adopt.

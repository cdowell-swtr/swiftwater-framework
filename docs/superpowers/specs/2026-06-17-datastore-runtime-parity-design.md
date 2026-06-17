# FWK6 — Data-store runtime parity (design)

> Status: approved design (2026-06-17). Next: writing-plans → implementation plan.
> Goal: remove the hardcoded co-located-container assumption from the generated
> project's compose stack, so a data store can be a co-located container **or** an
> external endpoint (managed / self-operated / native-on-host / tunneled / proxied)
> without hand-editing — and without foreclosing the TLS / auth / failover topologies
> an ambitious consumer will need as it scales. Deferred from Plan 28 (meta-plan).

## Problem

The generated project's compose stack hardcodes the assumption that every data store
is a container in the *same* stack, reachable by its compose service name. Three
concrete manifestations:

1. **Literal URLs in `environment:` shadow the env.** `dev.yml`, `prod.yml`, and
   `services.yml` set e.g. `APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"`
   as a *literal*. A literal in compose `environment:` is always set, so it **overrides
   anything the operator puts in their shell env / `.env`**. The managed-store escape
   hatch documented in `services.yml`'s own header comment ("point `APP_MONGO_URL` /
   `APP_REDIS_URL` at a managed instance and omit the data-store services") therefore
   **does not work** — the literal wins.
2. **Hard `depends_on`.** `app`/`worker`/`beat` declare
   `depends_on: { <store>: { condition: service_healthy } }` against the co-located
   container. Point at an external store and drop the container and the `depends_on`
   references a service that no longer exists → the stack breaks.
3. **No symmetry across runtimes.** Container / managed / self-operated-managed /
   native-on-host / LAN / WAN-tunneled / proxied are not interchangeable, even though
   from the app's point of view all of the non-container shapes are identical: *"an
   endpoint URL the framework didn't generate, and no co-located container."*

Note the **Python layer is not the problem**: `Settings` (`config/settings.py.jinja`)
defaults `database_url` / `redis_url` / `celery_broker_url` / `celery_result_backend` /
`mongo_url` to container DSNs, but pydantic-settings auto-binds `APP_*_URL`, so the app
already reads an override from the env when one is present. The foreclosure is entirely
in the compose `environment:` literals + the hard `depends_on`.

## Scope (what this is, and deliberately is not)

This was scoped by mapping the full landscape of data-store connection topologies that
exist in the world (embedded; native daemon; co-located container; container→host;
sidecar; LAN; WAN/tunneled; proxy/pooler; self-operated managed; genuine managed;
serverless/data-API) against the orthogonal dimensions that cut across them (transport;
endpoint cardinality; auth model; TLS posture).

The decisive realization: the **locality** spectrum *collapses* — managed / native /
tunneled / proxied all reduce, from the app's view, to a single opaque external URL with
no co-located container. The variation that *survives* the collapse lives in the other
dimensions (cardinality, auth, TLS), **most of which a single opaque DSN already
expresses** (multi-host failover strings; `?sslmode=verify-full&sslrootcert=…`).

So the right design for an ambitious-but-early consumer (per the FWK6 discussion: a
system aiming at multi-GB ingest, multiple datastores, DR/failover/BC at all layers,
confidential/trade-secret data, per-client segregation) is **optionality, not premature
capability**: remove every assumption that would force a rewrite, and pull forward only
the one item whose retrofit is genuinely infra-painful.

**In scope:**

- **(A) The URL seam** — make every `APP_*_URL` env-overridable in compose; the DSN is
  opaque and operator-owned (the framework never parses it).
- **(B) Conditional container + `depends_on`** — so an external store cleanly omits the
  co-located container with no dangling dependency edge.
- **(C) CA-bundle mount slot** — an off-by-default, documented convention so TLS
  `verify-full` to a managed store does not require hand-editing every service later.
  This is the one column-B item pulled forward because (a) trade-secret-in-transit puts
  it on the critical path and (b) getting a CA *file* into a container is the
  infra-painful retrofit; a DSN query param alone is free.
- **(D) Resolve the `services.yml` lock decision** (the meta-plan assigns this to FWK6).

**Explicitly out — but the design must *not foreclose* (proven by the opaque seam):**

- **IAM / OIDC / token auth** — provider-specific (RDS ≠ Cloud SQL ≠ Atlas), a real
  driver change; addable later as a connect-time token-fetch or an auth-proxy sidecar
  *behind the same opaque DSN*. Not foreclosed.
- **Per-tenant / per-client routing** — application architecture (tenant→store), not a
  compose/runtime concern. Out of frame.
- **Redis Sentinel / cluster-seed** — the one failover shape that does not fit a single
  DSN. Documented as a known extension point; not built.
- **`mode` enum / proxy / tunnel / native ergonomics** (the rejected "first-class runtime
  modes" option) — would gold-plate the *collapsing* (cheap) axis while leaving the axis
  that actually defines enterprise-grade (auth/TLS) at the framework's current tier,
  shipping a selector that promises parity it does not deliver. Per-store independence
  (below) already delivers per-store switching with no enum.

## Design

### A. The URL seam (env-overridable, opaque DSN)

In every compose file, each hardcoded `APP_*_URL: "<container-dsn>"` becomes the
established FWK31 host-port pattern lifted to URLs:

```yaml
APP_DATABASE_URL: "${APP_DATABASE_URL:-postgresql+psycopg://app:app@postgres:5432/app}"
```

- Operator sets `APP_DATABASE_URL` in env / `.env` → compose interpolates → **wins**.
- Unset → falls back to the container DSN → today's behavior is byte-for-byte preserved.
- The DSN is **opaque** — never parsed by the framework. Multi-host failover strings,
  `?sslmode=verify-full&sslrootcert=…`, and managed endpoints all ride this for free.
- Python `Settings` defaults are unchanged (they remain the out-of-compose fallback for
  host tooling / tests). Precedence (env > compose default-literal > `Settings` default)
  is documented in `settings.py` and `.env.example`.

Surfaces: `APP_DATABASE_URL`, `APP_REDIS_URL`, `APP_MONGO_URL`, `APP_CELERY_BROKER_URL`,
`APP_CELERY_RESULT_BACKEND` across `dev.yml`, `prod.yml`, `services.yml`.

### B. Conditional container + `depends_on` (the load-bearing decision)

Runtime mode is **per-(store × environment)**, and dev vs. prod are already separate
files. So the conditioning is split by environment rather than expressed as a global
mode enum:

- **dev (`dev.yml`): unchanged.** Container + `depends_on` stay the default; `task dev`
  stays zero-config. A dev who points `APP_*_URL` at an external store still spins the
  (now idle) container — mildly wasteful, harmless, not worth machinery to suppress.
  (`dev:lite` already exists for the leaner case.)
- **prod / staging: the co-located store + its `app → store` `depends_on` edge become
  opt-in via overlay.** The store container *and* the dependency edge move out of the
  always-rendered base into the includable self-hosted overlay (this is exactly what
  `services.yml` already is for the battery stores; postgres joins the same model).
  - **self-hosted:** include the overlay → container + ordering present, as today.
  - **managed / external:** omit the overlay + set `APP_*_URL` → no container, no dangling
    `depends_on`, no breakage.

Because each store has its own `APP_*_URL` and its own overlay membership, stores switch
**independently** (e.g. postgres → managed RDS for DR while redis/graph stay
containerized) with no `mode` enum and no per-store ergonomics surface.

**Compose-semantics caveat (verify first, do not assume).** This relies on (1)
`depends_on` long-form maps **merging additively** across overlay files, and (2) profiles
**not** silently re-activating a depended-on service. Compose's behavior here is exactly
the class the project's working agreement says to verify empirically. The implementation
plan's **first** step pins it with a `docker compose config` assertion before anything is
built on it. **Fallback if merge-additive does not hold:** render-time omission via a
per-store Copier answer (more invasive); this is why B is the design's decision point.

### C. CA-bundle mount (the pulled-forward TLS item)

An **off-by-default**, documented convention so `verify-full` to a managed store does not
require hand-editing every service later:

- A conventional in-container path (e.g. `/etc/ssl/app-ca/`) available as an optional
  mount on `app` / `worker` / `beat`, carried by the managed-store side of the overlay
  story.
- The operator drops their CA bundle there and references it in the opaque DSN
  (`?sslrootcert=/etc/ssl/app-ca/ca.pem`). The framework provides the **slot + the
  documented convention**, nothing more — no DSN rewriting, no cert management.
- Off by default → zero impact on existing renders.

### D. The `services.yml` lock decision

`services.yml` is currently a candidate for `LOCKED`. This design makes it the file
operators *edit* (managed URLs, CA mounts, omitting stores), so it is resolved to a
**composition seam: `INTENTIONALLY_UNLOCKED`** (the Plan-28 mechanism in
`integrity/classes.py`), with a header comment stating the contract ("this is yours to
edit; here is what the deploy expects"). Locking it would re-create the foreclosure at a
different layer.

## Testing

- **Render tests:** an external-mode render emits **no** co-located store service and
  **no** `depends_on`; a self-hosted render is unchanged from today (byte-drift guard).
- **`docker compose config` merge assertion:** pins the Section-B caveat *first* —
  proves `depends_on` merges additively and the managed-mode merge produces no dangling
  dependency.
- **Live acceptance test (the real proof):** bring the app up pointed at a store that is
  **not** in its compose stack and **not** depended-on (a separately-started container
  reached purely by the injected `APP_*_URL`), and assert a round-trip — mirroring the
  FWK20 / FWK24 live-exercise pattern. This is what proves the seam end-to-end (a render
  diff cannot).
- **Env-override unit test:** `${APP_*_URL}` set in the env beats the compose default.
- **CA-mount test:** with the convention exercised, the mount is present and the DSN can
  reference the mounted path (no live TLS handshake required — presence + wiring).

## FWK29 runtime-coverage impact

The new overlay membership / mount surfaces are classified in
`tests/runtime_coverage/registry.py` (EXERCISED via the live acceptance test), per the
FWK29 closed-world ratchet (`test_every_surface_is_classified`).

## Release

Template-payload change. Defaults preserve today's behavior byte-for-byte, so existing
consumers are unaffected until they opt into an external URL. Folds into the next batched
template-payload release (alongside the release-deferred FWK36 / FWK37 items).

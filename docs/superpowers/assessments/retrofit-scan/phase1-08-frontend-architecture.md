# Phase 1 Retrofit Scan — 08: Frontend Architecture & Rendering

**Agent:** frontend-architecture
**Area:** rendering strategy, routing, server-state/data-fetching, forms/validation, bundle/perf budgets, real-time/optimistic-UI, micro-frontends
**Date:** 2026-06-22

## What the framework ships today (the baseline this scan is measured against)

The `react` battery (`src/framework_cli/batteries.py:93`) renders a **React 18 + Vite client-side-rendered SPA served as static files by FastAPI**, with Vitest/Playwright/axe and three review agents (`accessibility`, `usability`, `observability-fe`), plus RUM via `web-vitals`. Inspecting the payload:

- `frontend/src/api.ts` — a hand-written `fetch("/items")` wrapper. No generated client, no typed contract with the Pydantic backend.
- `frontend/src/Items.tsx` — data is loaded with raw `useEffect` + `useState` (`items`, `error`, manual loading state). No cache, no dedup, no refetch, no race-condition guard.
- No router (`react-router`/TanStack Router absent), no client-state manager, no form/validation library, no SSR/streaming runtime, no bundle-budget gate.
- `vite.config.ts` builds a static `dist/`; the production serving path serves it from FastAPI. (A Node vite server runs in *dev* via `dev.yml`, but it is a dev-only dev-server.) **There is no Node runtime in the production serving path / deploy contract**, which silently forecloses SSR/RSC.

This baseline is precisely the "painted-into-a-corner" CSR SPA. The findings below target the seams that are cheap to bake in now and brutal to retrofit once a product has real content, users, and traffic. Critically, the top three (rendering, server-state, perf budget) are **interdependent, not siloed**: rendering strategy constrains routing and the data layer, so the early-scaffold move for rendering is partly "structure routing + data-fetching to be SSR-portable."

---

## Seam 1 — Rendering strategy (CSR vs SSR/SSG/streaming/RSC) — `retrofit_cost: H`

### The seam
Choosing CSR isn't just a default — the **FastAPI-serves-static-SPA architecture has foreclosed SSR**. There is no Node/JS server runtime in the production serving path / deploy contract (the dev vite server is dev-only), so the moment a product needs server rendering (SEO for public/marketing/content pages, fast First Contentful Paint on slow mobile, personalized above-the-fold content, social-card meta tags), it requires introducing a **new server runtime and a new deploy target** — not flipping a config flag.

### Why late is expensive (the retrofit story, with evidence)
The canonical taxonomy ([web.dev, "Rendering on the Web," Jason Miller & Addy Osmani](https://web.dev/articles/rendering-on-the-web)) frames the trap directly. CSR's weakness: "JavaScript bundle grows with application complexity, harming INP." The hydration "uncanny valley": *"Server-side rendered pages can appear to be loaded and interactive, but can't actually respond to input until the client-side scripts for components are executed and event handlers have been attached… On mobile, this can take minutes, confusing and frustrating the user."* web.dev's explicit guidance: *"We encourage developers to consider server-side rendering or static rendering over a full rehydration approach."*

The retrofit isn't a swap — it's a rewrite, and the real-world post-mortems are blunt. A React team's [Next.js App Router / RSC migration write-up (Flightcontrol)](https://www.flightcontrol.dev/blog/nextjs-app-router-migration-the-good-bad-and-ugly) reports: *"It took almost a year after it was called production-ready for it to really be usable in production,"* and *"We have certainly wasted a lot of company money wrestling with it."* The data layer fights you specifically: *"You have to add client side data fetching for this. And we want this for almost everything in our UI. This results in a lot of duplication"* — i.e., adopting SSR/RSC didn't remove the client data layer, it forced maintaining **both**. The [WorkOS zero-downtime migration](https://workos.com/blog/migrating-to-next-js-app-router-with-zero-downtime) confirms it could only be done incrementally and route-by-route, because "migrating to the /app router in one big push… risked disrupting ongoing product work… when multiple teams have pending PRs." That coordination cost is the High-retrofit signature: it touches every route and every data-fetch site and changes the deploy runtime.

### What early scaffolding looks like
This is a **`framework new`-time fork**, because the rendering runtime determines the deploy contract:
- Keep the static-SPA default for app-shell/dashboard products (correct for behind-auth tools — CSR is fine there), but **make the choice explicit and recorded** rather than implicit.
- Offer an **SSR-capable variant** (a Node sidecar service in compose + the deploy contract — e.g. a Next.js or Remix/React-Router-framework service alongside FastAPI-as-API) selectable at scaffold time.
- Even within the CSR default, structure the routing and data layers (Seams 2 & 4) so they are **SSR-portable**: data-fetching declared per-route, no fetch logic welded into render bodies. This is the cheap insurance that lowers a later SSR migration from H toward M.

### Proposed disposition
**concern** (rendering runtime is a posture chosen once at `framework new`, and it dictates the deploy contract) **with a `battery` facet** (the SSR-capable Node-sidecar variant). The tension is real and should be surfaced to the board rather than forced — the *choice* is a concern; the *SSR runtime* is a battery-shaped capability surface.

### Overlaps
New seam. The deploy-contract/runtime angle touches the **already-covered deploy contract + per-project compose isolation** (an SSR variant adds a service to that contract). Not the same as the shipped `react` battery, which is CSR-only.

---

## Seam 2 — Server-state / data-fetching & cache layer — `retrofit_cost: H`

### The seam
The scaffold's `useEffect` + `useState` fetch in `Items.tsx` is the textbook antipattern, shipped as the reference pattern. There is no cache, no request dedup, no background refetch, no stale-while-revalidate, no race-condition handling. Every new data-touching component will copy this shape, and consolidating onto a server-state library later means rewriting **every** data-fetch site.

### Why late is expensive (the retrofit story, with evidence)
The high-signal framing is Tanner Linsley's **"server state is not client state"** ([TanStack Query](https://tanstack.com/query/latest)): server state "is persisted remotely in a location you may not control or own, requires asynchronous APIs for fetching and updating, implies shared ownership and can be changed by other people without your knowledge, and can potentially become 'out of date'." Manual fetching forces you to hand-build a state machine per request: the [TanStack docs](https://tanstack.com/query/latest/docs/framework/react/overview) enumerate the responsibilities you silently inherit — caching, deduping identical requests, background updates, knowing when data is stale, structural sharing/memoization, pagination/lazy-loading, and garbage-collecting unused server state. The scaffold's `Items.tsx` handles **none** of these.

The retrofit cost is High not because adding a library is hard, but because the antipattern **scatters**: loading/error/refetch/invalidation logic gets embedded in dozens of component bodies, each subtly different (the [Silversky write-up](https://medium.com/@silverskytechnology/stop-using-useeffect-blindly-understand-server-state-and-why-tanstack-query-exists-256fb51f5b95) notes the manual pattern "doesn't account for caching, background refetching, deduplication, or stale data" and races on "component unmounting before the fetch finishes"). Once mutations exist, cache invalidation has to be reasoned about per-component because there's no central cache. Converting later is a per-site rewrite across the whole app *plus* re-deriving invalidation rules that were never written down.

### What early scaffolding looks like
Cheap and squarely a hardening of the **existing `react` battery default**:
- Ship a `QueryClient` provider and convert `Items.tsx` to a `useQuery` reference (TanStack Query as the bundled default), so the **scaffolded example demonstrates the right pattern** instead of the antipattern.
- Pair with a thin client-state lib (Zustand) only for genuine UI state (modals, sidebars) — and document the server/client-state split so builders don't reach for Redux to hold server data.
- Set sane defaults (staleTime, refetch-on-focus) in one place.

### Proposed disposition
**battery** (specifically: harden the **existing `react` battery's** shipped default — flip the reference component from the antipattern to a cached `useQuery`). This is the lowest-cost, highest-leverage finding in the area.

### Overlaps
Directly overlaps the **shipped `react` battery** — this is a quality upgrade to it, not a net-new battery. Interlocks with Seam 4 (a generated typed client is what `useQuery` should call).

---

## Seam 3 — Performance / bundle budget as a CI ratchet — `retrofit_cost: H (retrofit) / L (scaffold)` — the asymmetry IS the finding

### The seam
There is no bundle-size budget or Lighthouse gate in the rendered project's CI. A SPA's JS bundle grows monotonically with features; without a ratchet, regressions land invisibly and the bundle bloats until perf is a crisis. The asymmetry is the whole point: holding a budget from day one is a few lines of config; clawing back a 2 MB bundle after launch is a multi-sprint excavation across code you've already shipped.

### Why late is expensive (the evidence)
[web.dev, "Incorporate performance budgets into your build process"](https://web.dev/articles/incorporate-performance-budgets-into-your-build-tools): *"You may have a fast app today, but adding new code can often change this"* — and the enforcement model that works is automatic, not advisory: *"If bundlesize test fails, that pull request is not merged."* Concrete numbers exist to anchor a default: webpack's built-in asset hint is **250 KB uncompressed**; bundlesize examples use **~170 KB gzipped** per bundle; Lighthouse budget.json examples cap "100 kB for all scripts, 300 kB for all images, 500 kB for all resources, 25 total network requests" ([web.dev](https://web.dev/articles/incorporate-performance-budgets-into-your-build-tools); [Lighthouse CI budgets](https://unlighthouse.dev/learn-lighthouse/lighthouse-ci/budgets)). [Alex Russell's research](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Performance_budgets) puts ~**365 KB of JS** as the ceiling for sub-3-second loads on typical mobile — and notes the 75th-percentile site already blows past **650 KB**. The recommended operational model is a **ratchet**: "start with budgets that reflect today's reality, wire them into pull requests, and ratchet them down slowly."

The retrofit cost is High because perf debt compounds with every shipped feature and there's no automated signal to stop it; by the time someone notices, the fix touches code-splitting, dependency choices, and render paths across the whole app — exactly the work that was free to prevent.

### What early scaffolding looks like
This fits the framework's existing CI-gate philosophy (coverage/ruff/mypy gates) perfectly:
- Add a **`size-limit` (or bundlesize) check to the generated frontend CI** with a baseline ceiling (e.g. gzipped JS budget ~170–250 KB) that **fails the build** on regression.
- Optionally a Lighthouse-CI `budget.json` (resource-count + size budgets) wired into the rendered project's CI as an advisory-to-blocking gate.
- Ship it pre-wired so the budget exists from commit #1 and the team ratchets it down, never up.

### Proposed disposition
**concern** scaffolded as a CI gate (posture: "perf is a ratcheted gate, like coverage"). Mechanically it rides the **existing CI-gate machinery**; it is not a feature library, it is a guardrail.

### Overlaps
Adjacent to the **already-covered load/perf testing (k6)** — but distinct: k6 tests *server* load/latency; this is a *client* bundle/render budget enforced per-PR. Complements, doesn't duplicate. Same enforcement philosophy as the framework's existing coverage/ruff/mypy gates.

---

## Seam 4 — Typed client↔server contract (OpenAPI → TS client generation) — `retrofit_cost: M/H`

### The seam
The scaffold's `api.ts` hand-writes the `Item` type and the `fetch` call. The backend is FastAPI/Pydantic — it already emits a precise OpenAPI schema at `/openapi.json` (the vite proxy even forwards it). Hand-written types **drift silently** from the Pydantic models: rename a field server-side and the frontend keeps compiling against a stale shape until it breaks at runtime in front of a user. Every endpoint added by hand multiplies the surface that can drift.

### Why late is expensive (the evidence)
FastAPI's **own official docs** recommend generated clients precisely to kill drift ([FastAPI, "Generate Clients/SDKs"](https://fastapi.tiangolo.com/advanced/generate-clients/)): *"if something changed, it will be reflected on the client code automatically. And if you build the client, it will error out if you have any mismatch in the data used. So, you would detect many errors very early in the development cycle instead of having to wait for the errors to show up to your final users in production."* The official **full-stack-fastapi-template** (Tiangolo's own reference) regenerates the TS client and "when backend API routes change, the TypeScript client is automatically regenerated during pre-commit, preventing frontend-backend contract mismatches" ([DeepWiki on full-stack-fastapi-template](https://deepwiki.com/fastapi/full-stack-fastapi-template/5.3-openapi-client-generation)). FastAPI recommends **Hey API** (`@hey-api/openapi-ts`) for TS.

The retrofit cost is M/H: once a hand-written `api.ts` has grown dozens of endpoints and types, swapping to a generated client means rewriting every call site to the generated method names/shapes and rebuilding the trust that the types are correct — and you've already paid for every drift bug that shipped in the meantime. Cheap to start generated; painful to convert a large hand-rolled surface.

### What early scaffolding looks like
- Wire `@hey-api/openapi-ts` (or `openapi-typescript`) against the backend's `/openapi.json` into the generated project, output to `frontend/src/client/`.
- Make the scaffolded `Items.tsx` call the **generated** client (which `useQuery` from Seam 2 wraps), not a hand-written fetch.
- Add a **generated-client-is-current check to CI/pre-commit** (regenerate and fail on diff) — exactly the drift-guard the full-stack-fastapi-template uses. This mirrors the framework's existing "regenerate-and-check-in-CI" muscle (e.g. `gen_reviewer_reference.py` + `test_reviewer_reference.py`).

### Proposed disposition
**concern** scaffolded as a generation+drift-gate (posture: "the frontend type contract is generated from the backend, never hand-written"), folded into the **existing `react` battery**.

### Overlaps
Overlaps the **already-covered Pact consumer-driven contract testing** — but is **distinct**: Pact verifies *runtime request/response behavior* between services; this is *compile-time type generation* from a single backend's schema. Say so explicitly: codegen catches shape/type drift at build time; Pact catches behavioral contract breaks. They are complementary layers, not substitutes. Also the natural home for the "shared validation" idea (below).

---

## Seam 5 — Routing (history/data-router seam) — `retrofit_cost: M`

### The seam
No router is scaffolded. The first builder will reach for `react-router` and likely wire it ad hoc. Routing choice is largely **downstream of Seam 1**: an SSR-capable variant constrains the router (file-system routing / framework router), while a pure CSR SPA is freer.

### Why late is expensive
Routing is genuinely retrofittable — adding a router to a small SPA is mechanical. The cost rises to Medium (not High) when route-level data-loading, code-splitting boundaries, and auth-guard placement have already been hand-scattered and must be reorganized around a data-router's loader model. The cleaner the data layer (Seam 2/4), the cheaper this is. Per the migration post-mortems, routing type-safety gaps and dual-router "two unrelated apps" states ([Flightcontrol](https://www.flightcontrol.dev/blog/nextjs-app-router-migration-the-good-bad-and-ugly); [WorkOS](https://workos.com/blog/migrating-to-next-js-app-router-with-zero-downtime)) are real but are mostly *consequences* of the rendering choice, not an independent seam.

### What early scaffolding looks like
Ship a minimal data-router (TanStack Router or React Router data APIs) with **one** example route that loads via the Seam-2 cache and the Seam-4 generated client — so route-level data-loading and code-splitting have a correct pattern to copy.

### Proposed disposition
**park** (largely downstream of Seam 1; honest Medium cost, low independent pull). Fold into whichever rendering variant ships.

### Overlaps
Subordinate to Seam 1. No board overlap.

---

## Seam 6 — Forms & shared validation — `retrofit_cost: M / L`

### The seam
No form/validation library is scaffolded. Forms are the most common new-feature surface, and ad-hoc validation duplicates the backend's Pydantic rules in JS by hand, drifting over time.

### Why late is expensive
Largely **mechanical per-form** — swapping to React Hook Form + a resolver is form-by-form, hence Medium-to-Low. The genuinely valuable, harder-to-retrofit slice is a **single source of validation truth**. In a Node-only stack the pattern is one Zod schema shared front/back ([Medium: "One Zod Schema for All Layers"](https://medium.com/@tambatvibhor/syncing-frontend-backend-validations-one-zod-schema-for-all-layers-1fa42356e779)). **But this framework's backend is Pydantic, not Zod** — so the equivalent single-source move is **not** a shared Zod schema; it's deriving frontend validation/types from the backend's OpenAPI schema (Seam 4). That reframes "shared validation" as a *facet of Seam 4*, not a standalone concern.

### What early scaffolding looks like
Bundle React Hook Form + a Zod resolver for client-side ergonomics, but source the field shapes/types from the generated client (Seam 4) so the backend Pydantic models remain the single source of truth. Avoid hand-maintaining a second Zod copy of the backend schema.

### Proposed disposition
**park**, folded into Seam 4 (the higher-value contract-generation seam). Honest cost: Medium-to-Low; mechanical.

### Overlaps
Folds into Seam 4. No new board item.

---

## Seam 7 — Real-time / optimistic-UI / collaborative sync (local-first) — `retrofit_cost: H (only if needed) → otherwise park`

### The seam
Real-time collaboration, offline-first, and optimistic UI with conflict resolution are **foundational data-model decisions**, not features you bolt on. The scaffold is correctly server-authoritative (FastAPI is the source of truth); that is the right default for the products this framework targets.

### Why late is expensive (the evidence)
[Ink & Switch, "Local-first software"](https://www.inkandswitch.com/essay/local-first/) is unambiguous that this is an architectural inversion, not an add-on: *"In cloud apps, the data on the server is treated as the primary, authoritative copy of the data; if a client has a copy… it is merely a cache subordinate to the server. In local-first applications we swap these roles."* That role-swap "cannot be bolted on — it requires redesigning the entire data layer." CRDTs (Yjs, Automerge, Loro — powering Excalidraw, Linear) are "data structures where collaboration semantics are inherent," i.e. the conflict model must be designed in from the start. Linear's poster-child Sync engine loads all issues into IndexedDB on startup for 0 ms search — a ground-up architecture, not a retrofit ([sync-engines overview](https://shivekkhurana.com/blog/sync-engines/)). So when a product *truly* needs this, the retrofit cost is genuinely High (a data-layer rewrite).

**But the honest call is to resist treating this as High-pull just because the task lists it.** The framework targets server-authoritative FastAPI products; the population that needs CRDT/local-first sync is small. For most products this is over-engineering. The High cost only bites the minority who need it.

### What early scaffolding looks like
Do **not** scaffold a sync engine by default. If pursued, it is a clearly-scoped **opt-in battery** (a Yjs/Automerge document-sync surface + a websocket relay), explicitly chosen at scaffold time — never a default. Lighter-weight optimistic-UI (mutation-level `onMutate`/rollback) rides on Seam 2's TanStack Query and needs no special architecture.

### Proposed disposition
**park** (genuinely High retrofit cost, but low immediate pull for this framework's target products; promote to an opt-in **battery** only if a real consumer needs collaborative/offline sync). Optimistic-UI-via-mutations is already enabled for free by Seam 2.

### Overlaps
Overlaps the board's **composability** theme tangentially (a sync engine is a major capability surface). No direct duplication.

---

## Micro-frontends / module federation — folded, not a standalone finding

The task lists micro-frontends / module federation. **Honest assessment: park, overlapping the board's composability/shapes item.** The framework renders a *single FastAPI backend with one bundled SPA*; the organizational pressure that justifies module federation (many teams shipping into one shell, independent deploy cadences) does not exist for a single-service scaffold. Retrofitting module federation later is real work, but the pull is low and it is the frontend face of the **already-in-flight composability/shapes/shared-auth** board item. Resist rating it High just because it appears in the brief. **Disposition: park; overlaps composability.**

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Key board overlap |
|---|------|---------------|-------------|-------------------|
| 1 | Rendering strategy (CSR/SSR/SSG/RSC) | **H** | concern (+ battery facet) | deploy contract / compose isolation |
| 2 | Server-state / data-fetching cache | **H** | battery (harden existing `react` battery default) | shipped `react` battery |
| 3 | Perf / bundle budget CI ratchet | **H** retrofit / **L** scaffold | concern (CI gate) | k6 load testing (distinct); CI-gate philosophy |
| 4 | Typed client↔server contract (OpenAPI→TS) | **M/H** | concern (gen + drift-gate) | Pact (distinct: types vs behavior) |
| 5 | Routing (data-router seam) | **M** | park (downstream of #1) | — |
| 6 | Forms / shared validation | **M/L** | park (folds into #4) | — |
| 7 | Real-time / optimistic / local-first sync | **H** (if needed) | park → opt-in battery | composability (tangential) |
| — | Micro-frontends / module federation | M | park | composability/shapes (in flight) |

**Headline:** the three independent High-retrofit seams are **#1 rendering** (foreclosed by the static-SPA deploy contract — the headline), **#2 server-state cache** (the scaffold currently ships the antipattern as its reference pattern — the cheapest, highest-leverage fix), and **#3 perf budget** (the scaffold-cheap / retrofit-brutal asymmetry, a natural fit for the existing CI-gate machinery). #4 (typed OpenAPI→TS contract) is the strongest FastAPI-specific seam and the home for shared-validation. These four interlock: a generated typed client (#4), wrapped in a cached server-state hook (#2), called from SSR-portable route loaders (#5), is the structure that keeps a future SSR migration (#1) from being a full rewrite.

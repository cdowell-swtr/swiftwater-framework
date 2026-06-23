# Phase 1 retrofit scan — Comparative: frontend-first scaffolds

**Agent:** compare-frontend
**Area:** Comparative scan of FE-first scaffolds (create-next-app/Next.js, Remix, Astro, TanStack Start, full-stack-fastapi-template, shadcn/ui starters) vs. swiftwater's `react` battery.
**Date:** 2026-06-22

## Baseline: what swiftwater's `react` battery ships today

The `react` battery (`template/{% if "react" in batteries %}frontend{% endif %}/`) is a **Vite + React 18 SPA**, hand-rolled:

- **Data layer:** raw `fetch` in `api.ts` + `useEffect`/`useState` in `Items.tsx` — the exact server-state antipattern. Types (`Item`) are hand-written, not derived from the backend.
- **No router** (single page), **no design system / tokens** (bare elements), **no FE auth** integration, **no rendering-strategy choice** (SPA only), **no FE perf budget in CI**.
- It *does* ship: `web-vitals` RUM (`observability/rum.ts`, beacons to `/internal/rum`), one `@axe-core/playwright` a11y assertion in e2e, Vitest + coverage, Playwright, ESLint + Prettier + tsc.

The canonical peer — **fastapi/full-stack-fastapi-template** — ships, by default: Vite SPA **+ TanStack Query + an auto-generated OpenAPI TypeScript client + TanStack Router + shadcn/ui + Tailwind + JWT auth**, TypeScript at 70.5% of the repo. ([deepwiki / repo](https://github.com/fastapi/full-stack-fastapi-template)) That gap *is* this scan.

The reframe that governs the dispositions below: **a scaffold's shipped example sets the convention that gets copied N times.** `Items.tsx` is not expensive because TanStack Query is hard to add — it is expensive because every builder copies the `useEffect`-fetch pattern, so by the time anyone retrofits, the debt is in every component. That pushes the data-layer / type-safety / token seams toward **concern** (scaffold sets the pattern early) rather than **battery** (bolt-on later).

---

## Seam 1 — Typed server-state data layer (generated OpenAPI client + query cache)

**The seam.** Replace `fetch` + `useEffect` + hand-written types with (a) a **TypeScript client generated from the FastAPI OpenAPI spec** and (b) a **server-state cache** (TanStack Query) owning fetching/caching/invalidation. This is one seam because the peer scaffold ships them as one combo and they reinforce each other (generated types feed typed query hooks).

**Why late is expensive.** Two compounding debts:

1. *Contract drift.* With hand-written types, a backend field rename ships green on the FE and explodes at runtime in front of users. FastAPI's own docs recommend generating the client (`npx @hey-api/openapi-ts -i .../openapi.json -o src/client`) precisely so that *"whenever you update the backend code, and regenerate the frontend, it would have any new path operations available as methods, the old ones removed… if you build the client, it will error out if you have any mismatch"* — so *"you would detect many errors very early in the development cycle instead of having to wait for the errors to show up to your final users in production and then trying to debug where the problem is."* ([FastAPI: Generating SDKs](https://fastapi.tiangolo.com/advanced/generate-clients/))
2. *Reinvented state machine.* `useEffect` fetching means *"manually building a small state machine for every request… reimplementing infrastructure that every data-driven application needs"* (loading/error/stale/refetch/dedupe). TanStack Query replaces it with a declarative cache where mutations call `invalidateQueries` to mark data stale and refetch only what's on screen. ([TanStack: Query Invalidation](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation))

**retrofit_cost: M.** Honest answer: *adding* the layer later is mechanically incremental — per-component, no data migration, no architectural lock-in. What makes it more than L is the **convention-propagation** cost: the shipped `useEffect` example gets copied into every feature, so retrofitting means touching all of them, and the drift bugs in the meantime ship to prod. Tool-install cheap; accumulated-debt M.

**Early scaffolding looks like.** Ship the generated-client step wired into the toolchain (a `task fe:client` / pre-commit hook that regenerates `src/client` from the live/served `openapi.json`), the generated types committed, a `QueryClientProvider` at the root, and rewrite `Items.tsx` to a `useQuery(itemsQueryOptions)` hook calling a generated method — so the **copied example is the right pattern**. Add a CI check that the committed client matches a fresh generation (drift guard), mirroring the framework's existing expand-only/migration drift guards.

**Disposition: concern** (scaffold sets the data-fetching pattern early; not a bolt-on capability).

**Overlaps:** Sharpens the FE side of board "composability/shapes/shared-auth (in flight)" — the typed client *is* the shared shape crossing the FastAPI↔React seam. Adjacent to already-covered "Pact consumer-driven contract testing" (Pact verifies behavior at runtime; the generated client closes the gap at *build* time in the editor).

---

## Seam 2 — Design tokens (semantic theming layer), distinct from component sourcing

**The seam.** A **semantic CSS-variable token layer** (`--background`, `--foreground`, `--primary`, `--muted`, `--border` — meaning, not literal colors) that components consume, so themes/dark-mode/brand swaps change one layer, not every component. shadcn/ui *"uses CSS variables as design tokens instead of hard-coded values… allowing the same components to work across different themes without changing JSX or Tailwind classes."* ([Vercel Academy: Why shadcn/ui is different](https://vercel.com/academy/shadcn-ui/why-shadcn-ui-is-different); [RedMonk on copy-paste libraries](https://redmonk.com/kholterhoff/2025/04/22/ui-component-libraries-shadcn-ui-and-the-revenge-of-copypasta/))

**Why late is expensive.** Once hardcoded hex/spacing values are sprinkled across a mature component tree, introducing a token layer means finding and rewriting every literal — a brutal mechanical retrofit precisely because the values are *everywhere*. The token indirection is nearly free if introduced before the first component is styled; it is one of the classic "cheap early, brutal late" frontend layers.

**Note on sourcing (rated separately, M-at-most).** *How* you source components — shadcn's copy-paste-into-your-repo ("ownership relationship… components become your code, no vendor lock-in") vs. an npm library ("dependency relationship") — is a swappable choice you can change later. The **token layer** is the high-retrofit part; component sourcing is not.

**retrofit_cost: H** (for the token layer specifically — the indirection must exist before styling proliferates). Component sourcing alone would be M.

**Early scaffolding looks like.** Ship a minimal semantic-token CSS-variable file + Tailwind config wired to it, dark-mode via a class/attribute toggle, and style the example component(s) through tokens — so builders copy token-consuming markup, never literal colors. Do **not** mandate a heavy component library; ship the token contract + a couple of primitives (Button, Input) as owned source.

**Disposition: concern** (posture-level styling foundation scaffolded early).

**Overlaps:** New seam — no current board item covers a FE design-system / token layer. Distinct from board "CMS + admin/CRUD UI" battery (that's content management, not the styling primitive layer).

---

## Seam 3 — Accessibility as an enforced gate (jsx-a11y lint + axe), not a single smoke check

**The seam.** First-class a11y enforcement in the FE toolchain: `eslint-plugin-jsx-a11y` in the lint config (static AST checks: missing `alt`, bad ARIA, non-semantic interactives) **plus** the existing axe e2e check, both **blocking in CI**. Next.js bundles jsx-a11y by default via `eslint-config-next/core-web-vitals*. ([eslint-plugin-jsx-a11y](https://github.com/jsx-eslint/eslint-plugin-jsx-a11y); [Next.js accessibility architecture](https://nextjs.org/docs/architecture/accessibility))

**Why late is expensive.** This is the seam I initially under-rated. *Installing the rule* is trivial (cheap), but the **accumulated debt is famously brutal**: retrofitting accessibility across a mature component tree means auditing and remediating every component (labels, focus order, roles, contrast, keyboard traps) — and a11y bugs are a legal/compliance exposure, not just UX. The rule must be present *before* inaccessible patterns proliferate, because each one becomes a separate remediation. The plugin's own guidance: *"include eslint-plugin-jsx-a11y as part of your CI test strategy… ensures there are no accessibility issues being introduced to your code repository."*

**retrofit_cost: H** (debt-driven, not tool-driven). Tool install is L; the debt of retrofitting an a11y-careless codebase is H.

**Early scaffolding looks like.** Add `eslint-plugin-jsx-a11y` (recommended ruleset) to the shipped `eslint.config.js` and make `fe:lint` blocking in the generated CI; keep the axe Playwright check; ensure the shipped example components pass both. The current single axe assertion in `items.spec.ts` is necessary but catches only what's rendered in one e2e path — static lint catches the rest at author time.

**Disposition: concern** (posture scaffolded early). Partly **reviewer-enforced** as well: a FE-aware reviewer can flag a11y regressions the static rules miss (dynamic ARIA, focus management).

**Overlaps:** Extends the framework's existing axe-in-e2e a11y check — this is a *gap within* current FE testing, not a wholly new capability.

---

## Seam 4 — Rendering-strategy posture (SPA boundary made explicit, with an escape hatch)

**The seam.** Make the **rendering boundary a deliberate, documented decision** rather than an implicit default. Today the battery is SPA-only with no articulated posture. The FE-first frameworks treat rendering as the foundational choice: Astro's islands render *"mostly static HTML with isolated islands of interactive JavaScript"* (Jason Miller: render *"HTML pages on the server, and inject placeholders or slots around highly dynamic regions [that get] hydrated on the client into small self-contained widgets"*), because JS is *"the slowest asset you can load per-byte"* and a monolithic SPA must hydrate the whole page before any interactivity. ([Astro: Islands architecture](https://docs.astro.build/en/concepts/islands/))

**Why late is expensive — with an honest caveat.** Rendering strategy is *the* genuinely architecture-locked seam: *"switching from SPA to islands—or vice versa—requires reimagining component boundaries, data flow, and deployment infrastructure."* For SEO-critical or first-paint-critical surfaces, retrofitting SSR/SSG onto a CSR SPA is a near-rewrite, and teams are advised to *"implement SSR at least for highest-value landing pages… even if your entire application doesn't require it."* ([Astro islands](https://docs.astro.build/en/concepts/islands/); [SPA→SSR migration cost](https://dev.to/nik-bogachenkov/dive-into-nextjs-server-side-rendering-ssr-from-spa-to-isr-11o2)) **Caveat (lowers the pull):** a FastAPI + proxied-React-SPA scaffold mostly targets **authed dashboards / internal tools**, where SEO and first-paint-from-HTML are largely irrelevant. So for *this* framework's product shape, the pull is M, not H — and the answer is emphatically **not** "bolt a Node SSR server onto a Python-first scaffold."

**retrofit_cost: H in general / M for this framework's product shape** (most consumers are authed apps where SPA is the right default and stays it).

**Early scaffolding looks like.** Not new infra — a **documented posture**: "SPA-by-default; here is the rendering boundary; here is the escape hatch." Concretely: a short ADR-style note in the rendered project explaining SPA-by-default and how to carve out a static/prerendered surface (e.g. a Vite static prerender for a marketing/landing route, or pointing SEO-critical surfaces at a separate static-site path) without rewriting the app. Keep the proxied-SPA default; just make the boundary explicit so a builder who later needs a public, indexable page isn't blindsided.

**Disposition: concern** (posture-level decision scaffolded — as documentation + boundary, not runtime).

**Overlaps:** New — no board item covers rendering posture. Adjacent to board "CDN + blob/static assets" battery (a static/prerendered surface wants CDN delivery).

---

## Seam 5 — Frontend auth posture: token-storage model on the FE seam

**The seam.** The FE side of auth: **how the browser holds and refreshes credentials.** The battery has no FE auth at all; the peer template ships JWT end-to-end. The decision that's expensive to get wrong is the **token-storage model**: the hardened pattern is *"HttpOnly cookies for refresh tokens and in-memory storage for access tokens… the strongest protection against both XSS and CSRF,"* with a silent refresh on page load (the browser auto-sends the HttpOnly refresh cookie). `localStorage` tokens are readable by any XSS-injected JS. ([Wisp: token storage](https://www.wisp.blog/blog/understanding-token-storage-local-storage-vs-httponly-cookies); [Cotter/DEV: storing JWT securely](https://dev.to/cotter/localstorage-vs-cookies-all-you-need-to-know-about-storing-jwt-tokens-securely-in-the-front-end-15id))

**Why late is expensive.** Token storage is woven through every authed request, the refresh interceptor, logout, and CSRF posture. Shipping `localStorage` JWTs first (the easy default builders reach for) and later moving to HttpOnly-cookie + in-memory means re-plumbing the entire auth flow *and* adding CSRF defenses (SameSite + anti-CSRF token) that weren't needed before — a security-sensitive retrofit done under XSS-exposure pressure. The trade-off doc notes *"the complexity often lies in coordinating between frontend and backend"* — exactly the seam a scaffold should pre-decide.

**retrofit_cost: M** (re-plumbing the auth flow is contained but touches a security-critical path; not architecturally locked, but unpleasant and risky to change post-launch).

**Early scaffolding looks like.** When auth lands, ship the **secure default**: access token in memory, refresh token in an HttpOnly + Secure + SameSite cookie, a silent-refresh-on-load handler, and a generated-client interceptor that attaches the access token + handles 401→refresh. Don't ship `localStorage` tokens as the example.

**Disposition: concern** (security posture scaffolded early), with a **reviewer-enforced** complement: a reviewer should flag `localStorage`/`sessionStorage` token writes and missing SameSite/CSRF posture.

**Overlaps:** **Board "composability/shapes/shared-auth (in flight)"** — this is the FE-specific posture *within* that item, not a new seam. Surface it as a sharpening: when shared-auth is designed, fix the FE token-storage model at the same time.

---

## Folded / demoted (recorded, not headline seams)

**RUM → backend-trace correlation (gap within already-covered observability).** The battery's `rum.ts` collects web-vitals and beacons them to `/internal/rum`, but does **not** inject `traceparent` on outbound fetches — so a slow LCP can't be tied to the backend span/DB query that caused it. The OTel pattern: *"when the browser makes fetch requests, the OpenTelemetry SDK automatically injects traceparent headers, so a slow LCP caused by a slow API call shows up as a single connected trace from the browser to the database query."* ([Elastic: web frontend OTel](https://www.elastic.co/observability-labs/blog/web-frontend-instrumentation-with-opentelemetry); [OneUptime: CWV↔OTel backend traces](https://oneuptime.com/blog/post/2026-02-06-core-web-vitals-otel-backend-traces/view)) This is a **gap inside already-covered "full observability stack (OTel/Tempo/Loki)"**, not a new battery. **Disposition: reviewer-enforced** (a reviewer flags FE fetches that don't propagate trace context) / small sharpening of the existing RUM. retrofit_cost: **L** — the beacon plumbing already exists; adding propagation is a contained change.

**Frontend perf budgets in CI (distinct from k6, but low pull).** Lighthouse-CI / `budget.json` fails the build when CWV thresholds (LCP/CLS/INP) or bundle sizes regress. ([Unlighthouse: LHCI budgets](https://unlighthouse.dev/learn-lighthouse/lighthouse-ci/budgets); [web.dev: vitals tools](https://web.dev/articles/vitals-tools)) This **is** genuinely distinct from already-covered **k6** (k6 = backend HTTP load/latency under concurrency; Lighthouse = client-side rendering/CWV/bundle weight — different layer entirely). But the gate is trivial to add at any time and never-regress is a nice-to-have, not a brutal retrofit. **Disposition: park** (real, distinct from k6, but low immediate pull). retrofit_cost: **L**.

**Content schema / type-safe frontmatter (Astro content collections).** Astro validates Markdown/MDX frontmatter via Zod and auto-generates TS types, catching *"typos in frontmatter fields at build time, not at runtime."* ([Astro content collections](https://docs.astro.build/en/guides/content-collections/)) High-signal for *content-first* sites, but swiftwater targets app backends. **Overlaps board "CMS + admin/CRUD UI" battery** — fold the type-safe-content-schema idea into that battery's design rather than surface separately. **Disposition: park** (subsumed by the CMS battery).

# 8g — `react` Battery (React SPA frontend)

**Date:** 2026-05-27
**Status:** Design approved — ready for implementation plan
**Plan 8 slice:** 8g (react)
**Predecessors:** 8d graphql (`gates_agent` review-gating machinery + the `api-design` battery-agent pattern), 7a–7d (the review-agent system + eval harness), 5a (the generated-project CI pipeline + LOCKED `ci.yml`), 3a (the Docker/Compose/Traefik serving stack)

---

## 1. Summary & Motivation

Adds the `react` battery: a **React + TypeScript single-page app**, served by the existing FastAPI backend, with a full frontend toolchain (Vite, ESLint/Prettier, `tsc`, Vitest, Playwright + axe) wired into the generated project's CI — and two new battery-gated review agents (`review-accessibility`, `review-usability`).

This is the framework's **first frontend / Node toolchain**. The guiding constraints, consistent with the framework's ethos: prod stays **self-hosted and simple** (one container, no Node at runtime), dev keeps **full HMR**, dev↔prod **parity** holds, and the toolchain integrates into the *existing* CI/quality machinery rather than bolting on a parallel one.

### Scope

**In scope:** a gated `frontend/` Vite+React+TS SPA (a minimal-but-real Items page over the baseline `GET /items`), the full frontend toolchain + test tiers, FastAPI static-serving of the built SPA (prod) + a Vite dev service (dev), gated CI steps, the two review agents (+ eval fixtures) and the `gates_agent`→plural machinery extension, registration, and battery tests.

**Deferred (named):** frontend RUM/web-vitals observability (the meta-plan's "fe obs reviewer domain"); SSR/Next.js; auth/session UI; any second page or router beyond a minimal shell.

---

## 2. Archetype

A **frontend** battery, `requires=()`. It adds a Node build-time toolchain and a `frontend/` source tree, but **no new prod runtime service** and **no new prod runtime dependency** (Node is confined to a Docker build stage; the runtime image stays python-only). It is the first battery to gate **two** review agents (driving a small machinery change, §6).

---

## 3. Serving Model — FastAPI serves the built SPA

The SPA and API are **same-origin** in both dev and prod, so there is **no CORS** anywhere and **no `/api` prefix** (the SPA uses same-origin relative paths to the existing routes `/items`, `/health`, etc.).

### 3.1 Dev (Vite dev server + proxy)

A dev-profile-only `frontend` service in `infra/compose/dev.yml.jinja` (gated `{% if "react" in batteries %}`):
- `node:22` image, `command: ["npm", "run", "dev", "--", "--host"]` (Vite on `:5173`), `frontend/` bind-mounted for HMR, `frontend/node_modules` kept container-side (an anonymous/named volume so the host mount doesn't shadow it), published `5173:5173`, `profiles: ["dev"]`.
- Vite's dev proxy (`vite.config.ts`) forwards backend paths to `app:8000`: `/items`, `/health`, `/heartbeat`, `/metrics`, `/docs`, `/openapi.json` (and `/graphql` when present is out of scope — the proxy list covers the baseline). The browser hits Vite (`:5173`); Vite proxies API calls server-side → no CORS.

### 3.2 Prod (Node build stage → FastAPI static serving)

- **`infra/docker/Dockerfile.jinja`:** a gated `frontend-build` stage (`FROM node:22 AS frontend-build`; `COPY frontend/package*.json`; `npm ci`; `COPY frontend/`; `RUN npm run build` → `frontend/dist/`). The runtime stage adds `COPY --from=frontend-build /app/frontend/dist /app/frontend/dist` (gated). The runtime image gains **no Node** — only the built static assets.
- **`main.py.jinja`:** after `include_routers(app)` (so specific API routes are registered first and aren't shadowed), a gated block mounts the SPA **only if the build output exists**:
  ```python
  {% if "react" in batteries %}
      from pathlib import Path
      _dist = Path("frontend/dist")
      if _dist.exists():
          from fastapi.staticfiles import StaticFiles
          app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
  {% endif %}
  ```
  `html=True` serves `index.html` at `/` and falls back to it for unknown paths under the mount (SPA client-side routing). The `_dist.exists()` guard means **dev** (no build; Vite serves the SPA) skips the mount, **prod** (built image) mounts it — a clean dev/prod split with **no environment flag**. (The plan verifies `StaticFiles(html=True)` covers the SPA-fallback need; if deep-link fallback to `index.html` requires an explicit catch-all route, the plan adds one that excludes the API paths.)

This keeps prod **one container** serving both the SPA (`/`) and the API (`/items`, `/health`, `/metrics`, `/docs`), reusing the existing app image + deploy unchanged.

---

## 4. Frontend Source (`frontend/`)

A gated directory `frontend/` (rendered only with the react battery; via a brace-templated dir or per-file gating consistent with the template's conventions). Contents:
- `package.json` (React 18, Vite 5, TypeScript 5, Vitest, Playwright + `@axe-core/playwright`, ESLint + Prettier + the React/TS plugins) with scripts: `dev`, `build` (`tsc -b && vite build`), `preview`, `test` (`vitest run --coverage`), `test:e2e` (`playwright test`), `lint` (`eslint .`), `format:check` (`prettier --check .`), `typecheck` (`tsc --noEmit`).
- `vite.config.ts` (React plugin + the dev proxy from §3.1 + Vitest config: jsdom env, coverage), `tsconfig.json`(+`tsconfig.node.json`), `index.html`, `.eslintrc`/`eslint.config.js` + `.prettierrc`, `playwright.config.ts`.
- `src/main.tsx` (React root), `src/App.tsx`, `src/Items.tsx` (a component that `fetch`es `/items` and renders the list with accessible markup — a labelled list/table), `src/api.ts` (a tiny typed fetch helper).
- Tests: `src/Items.test.tsx` (Vitest: mocks fetch, asserts the list renders + handles loading/error), `e2e/items.spec.ts` (Playwright: loads the served app, asserts the items render, runs an axe scan asserting no violations).

The SPA is intentionally minimal but exercises the full real path: typed fetch of a real backend endpoint, an accessible component, a unit test, an e2e+a11y test.

---

## 5. CI Integration (gated edits to the LOCKED `ci.yml`)

The generated `ci.yml` is LOCKED; the react edits are **byte-identical without the battery** (the graphql/8d precedent for conditional `{%- if %}` blocks in `ci.yml`).

- A new **`frontend` job** (gated `{% if "react" in batteries %}`): `actions/setup-node` → `npm ci` (in `frontend/`) → `eslint` + `prettier --check` + `tsc --noEmit` + `vitest run --coverage`, then **Playwright + axe** against a built+served app (`npm run build` + serve `dist/` — via `vite preview` or a static server — then `playwright test`; Playwright installs its browsers in CI). `needs: lint` (mirrors the other test jobs).
- The existing **`build` job** already runs `docker build`, which now also exercises the `frontend-build` stage — validating the SPA builds as part of image build.
- **Review agents auto-wire with NO `ci.yml` change:** the `review-plan` job calls `framework review-agents --event <event>`, which reads the project's batteries and emits the matrix; registering the two agents + gating them on react (§6) makes them appear automatically.

(The Python `scripts/coverage.sh` gate is unchanged — the frontend has its own Vitest coverage, a separate language/tier.)

---

## 6. Review Agents + `gates_agent`→plural Machinery

### 6.1 The machinery extension

`BatterySpec.gates_agent: str | None` becomes `gates_agents: tuple[str, ...] = ()` (a battery may gate **multiple** review agents). `framework_cli/review/registry.py::active_agents` builds the gated set from the union across present batteries' `gates_agents`. Existing single-agent batteries migrate (`graphql` → `gates_agents=("api-design",)`). This is the only change to the review machinery; everything else (the `active_when="battery"` flow, the CI matrix, the eval harness) is reused verbatim.

### 6.2 The two agents (framework source, mirroring `api-design`)

- `src/framework_cli/review/agents/accessibility.md` → `review-accessibility`, `block_threshold="high"`, `active_when="battery"`. Reviews the generated project's frontend diffs for: missing form labels / `alt` text / accessible names, non-semantic interactive elements (`<div onClick>` vs `<button>`), missing keyboard handling, color-contrast/ARIA issues, and the axe-rule class — the objective a11y lens.
- `src/framework_cli/review/agents/usability.md` → `review-usability`, `block_threshold=None` (advisory), `active_when="battery"`. Heuristic lens: unhandled loading/empty/error states, confusing flows, inconsistent affordances, missing feedback on actions.
- Both registered in `_SPECS`. `react` sets `gates_agents=("accessibility","usability")`.
- **Eval fixtures** (the 7d harness is registry/convention-driven): for each agent, bad fixtures (a11y violation / usability smell that should be detected) + a good fixture (clean) under `tests/eval/fixtures/`, following the `api-design` fixture layout, so set-level recall/precision is measured. Provisional thresholds consistent with the other agents (tuned by the real eval run, per the 7d follow-up).

The `dependency` review agent already triggers on `package.json`/`package-lock.json`, so frontend dependency review is already covered (no change).

---

## 7. Registration, Integrity, Deps

- **`batteries.py`:** register `react` (`BatterySpec("react", "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability review", gates_agents=("accessibility","usability"))`).
- **No `MIGRATION_ORDER` change** (no migration). **No new framework Python dependency** (the toolchain is Node/template; the agents are markdown prompts; no `uv.lock`/root `pyproject.toml` change).
- **No new `LOCKED_TRACKED` entries.** `ci.yml`/`dev.yml`/`Dockerfile`/`main.py` are conditionally **edited**; their no-react render is **byte-identical** (the 8c/8d precedent). The `frontend/` tree is conditional template payload; the agent prompts + eval fixtures are framework source.
- **No baseline manifest shift** — every new artifact is react-gated; a no-react render is byte-identical.
- **`.gitignore`** (generated project): gated entries for `frontend/node_modules/` and `frontend/dist/`.
- **`Taskfile.yml.jinja`:** gated `fe:dev`, `fe:build`, `fe:test`, `fe:lint` tasks (thin wrappers over `npm --prefix frontend run …`).
- **downskill `react`:** owned files = the `frontend/` tree (deleted); the gated `ci.yml`/`dev.yml`/`Dockerfile`/`main.py`/`.gitignore`/`Taskfile` edits revert via the two-render diff + byte-identity exclusion (no `--force` expected); `record_batteries` drops react so its agents de-activate.

---

## 8. Testing the Battery

- **Render/unit (`tests/test_copier_runner.py`):**
  - `["react"]` renders `frontend/` (package.json, vite.config.ts, src/App.tsx, src/Items.tsx, the unit + e2e tests), the gated `frontend` CI job, the `frontend` dev service, the Dockerfile `frontend-build` stage, the `main.py` static-mount block, the `.gitignore` + Taskfile entries.
  - `[]` baseline byte-identical — no `frontend/`, no react strings in `ci.yml`/`dev.yml`/`Dockerfile`/`main.py`.
  - A freshly rendered `["react"]` project passes its first `pre-commit` clean (the Python-side files — the 8c regression class; the frontend has its own lint, not in pre-commit by default).
- **Review-machinery tests (`tests/`):** `gates_agents` is a tuple; `active_agents("pull_request", ["react"])` includes `review-accessibility` + `review-usability`; `active_agents("push", ["react"])` excludes them (battery agents off-push unless `on_push`); the graphql migration (`gates_agents=("api-design",)`) still works.
- **Eval (`tests/eval/`):** the two agents' fixtures are registered + score within thresholds (hermetic, as 7d).
- **Live acceptance (`tests/acceptance/test_rendered_project.py`):** render `--with react`; (a) build the SPA + run the frontend suite — `npm ci` + `tsc` + `vitest run` (+ a Playwright+axe smoke against the served build if feasible in CI/sandbox); (b) build the prod image and confirm it serves the SPA `index.html` at `/` while `/items` returns JSON (the static-mount + route-ordering proof). (Mind the Docker-acceptance `/tmp` hygiene caveat — run sparingly, clean up. Node + Playwright browsers are heavy; the plan scopes the acceptance to what's tractable in-sandbox, with the full suite as the CI gate.)

---

## 9. Components & File Map

**Framework CLI (`src/framework_cli/`):**
- `batteries.py` — `gates_agent`→`gates_agents` field; register `react`; migrate `graphql`.
- `review/registry.py` — `active_agents` reads `gates_agents` (union); register `accessibility` + `usability` in `_SPECS`.
- Create `review/agents/accessibility.md`, `review/agents/usability.md`.
- (Any other reader of `gates_agent` — grep + migrate.)

**Framework tests:**
- `tests/test_copier_runner.py` (render + byte-identity), `tests/test_batteries.py` (react registration + `gates_agents`), review-registry tests (active_agents), `tests/eval/fixtures/` (the two agents' fixtures), `tests/acceptance/test_rendered_project.py` (live).

**Template payload (`src/framework_cli/template/`):**
- Create `frontend/` (gated): `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `index.html`, `eslint`/`prettier` configs, `playwright.config.ts`, `src/{main.tsx,App.tsx,Items.tsx,api.ts}`, `src/Items.test.tsx`, `e2e/items.spec.ts`.
- Modify: `infra/compose/dev.yml.jinja` (frontend service), `infra/docker/Dockerfile.jinja` (frontend-build stage + COPY), `src/{{package_name}}/main.py.jinja` (static mount), `.github/workflows/ci.yml.jinja` (frontend job), `.gitignore` (or its template), `Taskfile.yml.jinja` (fe:* tasks).

**Framework docs:** `CLAUDE.md` Current State + meta-plan 8g row.

---

## 10. Risks & Mitigations

- **`gates_agent`→plural touches shared review machinery** (batteries.py + registry.py + the graphql battery). *Mitigation:* migrate `graphql` in the same change; a review-registry test asserts both graphql (api-design) and react (accessibility+usability) gate correctly; full suite + a graphql render/acceptance confirm no regression.
- **Playwright in CI/sandbox is heavy** (browser downloads, a served app). *Mitigation:* the CI `frontend` job installs browsers explicitly; the in-sandbox **acceptance** scopes to the tractable subset (build + vitest + image-serves-SPA proof), leaving the full Playwright+axe run to CI. Report honestly what runs where.
- **`main.py` static mount in dev** (no `dist/`) — *Mitigation:* the `Path("frontend/dist").exists()` guard; a render+import test that a react project's `create_app()` succeeds with no `dist/` (dev shape) and serves the SPA when `dist/` exists.
- **Route shadowing** (catch-all SPA mount swallowing `/items`). *Mitigation:* mount static **after** `include_routers`; an acceptance assertion that `/items` returns JSON and `/` returns the SPA on the built image.
- **Byte-identity of the gated LOCKED `ci.yml`/`Dockerfile`/`main.py`/`dev.yml`** (the 8c regression class). *Mitigation:* Jinja whitespace control + the `[]` byte-identity render test + integrity green at baseline.
- **Largest battery; scope creep risk.** *Mitigation:* the SPA stays one Items page; obs/SSR/auth/2nd-page explicitly deferred (§1).

---

## 11. Out of Scope / Follow-ups

- **Frontend RUM/web-vitals observability** (web-vitals reporter → backend ingest → `/metrics` + dashboard) — the meta-plan's fe-obs reviewer domain.
- **The `review-observability` inf/db/app/fe split** (existing Known follow-up) — react adds the *fe* domain data point.
- **`8f-w` wizard** remains the last Plan-8 db item (unrelated to react).
- SSR/Next.js, auth/session UI, multi-page routing, a component library.

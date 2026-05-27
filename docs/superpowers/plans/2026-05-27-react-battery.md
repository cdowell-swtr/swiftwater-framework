# 8g — `react` Battery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `react` battery — a React+TypeScript SPA served by FastAPI, with a Vite/Vitest/Playwright/axe toolchain wired into CI, plus two battery-gated review agents (`review-accessibility`, `review-usability`).

**Architecture:** A gated `frontend/` Vite SPA. Dev: a Vite dev server (compose `frontend` service, HMR, proxies backend paths → same-origin, no CORS). Prod: a Node build stage in the app Dockerfile produces `frontend/dist/`, copied into the python runtime image; `main.py` mounts it via `StaticFiles(html=True)` only if `dist/` exists (one prod container, no Node at runtime). Two new review agents wire via a `gates_agent`→`gates_agents` (tuple) machinery extension.

**Tech Stack:** Copier/Jinja templates, Vite + React 18 + TypeScript 5, Vitest, Playwright + `@axe-core/playwright`, ESLint + Prettier, Docker multi-stage, FastAPI StaticFiles, the framework review-agent registry + eval harness.

**Spec:** `docs/superpowers/specs/2026-05-27-react-battery-design.md`

**Conventions (read before starting):**
- `src/framework_cli/template/` is **template payload** (rendered into projects) — don't lint/type-check it as framework code. `src/framework_cli/` (incl. `review/agents/*.md`, `review/registry.py`, `batteries.py`) IS framework source. The frontend toolchain is **Node/template-only** — do NOT add Node deps to the framework's `pyproject.toml`/`uv.lock`.
- Framework fast gate (green before each commit): `uv run --frozen pytest -q --ignore=tests/acceptance && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`. Run `ruff format --check .` as its OWN command (a pipe to `tail` masks its exit code).
- **⚠ /tmp HAZARD:** the Docker `tests/acceptance` tier renders into `/tmp` as root + can fill it, wedging the sandbox. Run AT MOST the named acceptance test, then `rm -rf /tmp/pytest-of-chris/* 2>/dev/null` + `df -h /tmp`. Never the full acceptance tier. Node/Playwright are heavy — scope in-sandbox runs (the plan says where).
- **COMMIT-GATE HOOK:** `git commit` is blocked unless `CLAUDE.md` is staged. The hook greps the **entire tool-input JSON incl. your Bash `description`** — NEVER put the literal word c-o-m-m-i-t in a description or anywhere in a git command except the actual `git commit`. Use SEPARATE `git add` then `git commit` calls (combined trips the hook). Each task: edit the `CLAUDE.md` `- **Last updated:**` marker (e.g. `[8g Tn]`) and stage it.
- `render_project(dest, {**DATA, "batteries":[...]})`, `DATA={"project_name":"Demo","project_slug":"demo","package_name":"demo","python_version":"3.12"}` (top of `tests/test_copier_runner.py`).

---

## File Structure

**Framework CLI (`src/framework_cli/`):**
- `batteries.py` — `gates_agent: str|None` → `gates_agents: tuple[str,...]=()`; migrate `graphql`; register `react`.
- `review/registry.py` — `active_agents` reads `gates_agents` (union); register `accessibility` + `usability` in `_SPECS`.
- Create `review/agents/accessibility.md`, `review/agents/usability.md`.

**Framework tests:** `tests/test_batteries.py`, `tests/review/test_registry.py`, `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`; `tests/eval/fixtures/{accessibility,usability}/{bad,good}/`.

**Template payload (`src/framework_cli/template/`):** a gated `frontend/` tree; modify `infra/compose/dev.yml.jinja`, `infra/docker/Dockerfile.jinja`, `src/{{package_name}}/main.py.jinja`, `.github/workflows/ci.yml.jinja`, `Taskfile.yml.jinja`, and the project `.gitignore`.

---

## Task 1: `gates_agents` machinery extension + register `react` + migrate `graphql`

**Files:** `src/framework_cli/batteries.py`, `src/framework_cli/review/registry.py`, `tests/test_batteries.py`, `tests/review/test_registry.py`.

- [ ] **Step 1: Update the failing tests first (TDD)**

In `tests/test_batteries.py`, change the two `gates_agent is None` assertions (lines ~10, ~31) to `gates_agents == ()`. Add a react registration test:
```python
def test_react_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "react" in battery_names()
    assert get_battery("react").requires == ()
    assert get_battery("react").gates_agents == ("accessibility", "usability")
    assert resolve(["react"]) == ["react"]
```
In `tests/review/test_registry.py`: change `gates_agent=` kwargs (lines ~97, ~99) to `gates_agents=(...)` (e.g. `gates_agents=("_demo-agent",)`, `gates_agents=("_demo-push-agent",)`); change the graphql assertion (line ~135) `get_battery("graphql").gates_agent == "api-design"` → `get_battery("graphql").gates_agents == ("api-design",)`. Add:
```python
def test_active_agents_battery_can_gate_multiple(monkeypatch):
    import framework_cli.batteries as bat
    from framework_cli.review.registry import active_agents

    monkeypatch.setitem(bat._BATTERIES, "_multi", bat.BatterySpec("_multi", "x", gates_agents=("api-design", "documentation")))
    out = active_agents("pull_request", ["_multi"])
    assert "api-design" in out and "documentation" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest tests/test_batteries.py tests/review/test_registry.py -q`
Expected: FAIL (`gates_agents` doesn't exist; react unregistered).

- [ ] **Step 3: Change the `BatterySpec` field**

In `src/framework_cli/batteries.py`, replace the `gates_agent` field:
```python
    gates_agents: tuple[str, ...] = ()  # review agents activated when this battery is present (8d/8g)
```
Migrate graphql: `gates_agent="api-design"` → `gates_agents=("api-design",)`. Register react (after `redis`):
```python
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability review",
        gates_agents=("accessibility", "usability"),
    ),
```

- [ ] **Step 4: Update the registry reader**

In `src/framework_cli/review/registry.py`, in `active_agents`, replace line ~123:
```python
    gated = {a for b in batteries for a in get_battery(b).gates_agents}
```
(Update the docstring mention of `gates_agent` → `gates_agents`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --frozen pytest tests/test_batteries.py tests/review/test_registry.py -q`
Expected: PASS. (`active_agents(["react"])` won't add the two agents yet — they're not in `_SPECS` until Task 2 — and that's fine; this task only proves the machinery + registration.)

- [ ] **Step 6: Fast gate + commit**

Fast gate. Stage `batteries.py`, `registry.py`, the two test files + a `CLAUDE.md` `[8g T1]` marker. `git commit -m "feat(react): gates_agents tuple machinery + register react + migrate graphql"`.

---

## Task 2: the two review agents + eval fixtures

**Files:** create `src/framework_cli/review/agents/accessibility.md`, `.../usability.md`; modify `src/framework_cli/review/registry.py`; create `tests/eval/fixtures/{accessibility,usability}/{bad,good}/*`; modify `tests/review/test_registry.py`.

- [ ] **Step 1: Write the failing registry test**

Add to `tests/review/test_registry.py`:
```python
def test_react_agents_active_on_pr_not_push():
    from framework_cli.review.registry import active_agents

    pr = active_agents("pull_request", ["react"])
    assert "accessibility" in pr and "usability" in pr
    push = active_agents("push", ["react"])  # battery agents are off-push unless on_push
    assert "accessibility" not in push and "usability" not in push
```

- [ ] **Step 2: Run it → FAIL** (`accessibility`/`usability` not in `_SPECS`).

Run: `uv run --frozen pytest tests/review/test_registry.py::test_react_agents_active_on_pr_not_push -q`

- [ ] **Step 3: Create the agent prompts** (mirror `review/agents/api-design.md`'s focused style)

`src/framework_cli/review/agents/accessibility.md`:
```markdown
You are `review-accessibility`. Review ONLY the unified diff of a frontend change (React/TSX).
Flag accessibility defects and cite the changed line:

- Non-semantic interactive elements: a `<div>`/`<span>` with `onClick` (or similar) used as a
  button/link instead of `<button>`/`<a>`, with no `role` + keyboard handler. "high".
- Missing accessible names: an `<img>` without `alt`, an icon-only button with no `aria-label`,
  a form `<input>` with no associated `<label>`/`aria-label`. "high".
- Keyboard inaccessibility: a custom interactive control with no keyboard handling (onKeyDown)
  or not focusable (missing `tabIndex`). "high".
- ARIA/contrast smells: misused/invalid `aria-*`, or hardcoded low-contrast colors. "info".

Do NOT flag backend/Python changes, or purely stylistic CSS with no a11y impact.

Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none.
A non-semantic interactive element, a missing accessible name, or keyboard inaccessibility is "high".
```
`src/framework_cli/review/agents/usability.md`:
```markdown
You are `review-usability`. Review ONLY the unified diff of a frontend change (React/TSX).
Flag usability defects (heuristic — advisory) and cite the changed line:

- Unhandled async states: a fetch/await with no loading indicator, no error branch, or no
  empty-state handling (the user sees a blank/frozen UI on slow/failed/empty responses). "info".
- No feedback on actions: a mutating action (submit/delete) with no success/error feedback or
  disabled-while-pending state. "info".
- Confusing flow: dead-end states, irreversible actions with no confirmation, inconsistent
  affordances. "info".

Do NOT flag accessibility issues (covered by review-accessibility) or backend changes.

Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none.
This agent is advisory (never blocks).
```

- [ ] **Step 4: Register both in `_SPECS`**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (after `api-design`):
```python
    "accessibility": AgentSpec(
        "review-accessibility", _prompt("accessibility"), "high", "battery", DEFAULT_MODEL
    ),
    "usability": AgentSpec(
        "review-usability", _prompt("usability"), None, "battery", DEFAULT_MODEL
    ),
```

- [ ] **Step 5: Create eval fixtures** (format: `tests/eval/fixtures/<agent>/{bad,good}/<slug>.diff`; each bad fixture needs `<slug>.expect.json` = `{"file": "<seeded path>"}`)

`tests/eval/fixtures/accessibility/bad/div-onclick.diff`:
```diff
--- a/frontend/src/Items.tsx
+++ b/frontend/src/Items.tsx
@@ -10,3 +10,5 @@ export function Items() {
   return (
     <ul>{items.map((i) => <li key={i.id}>{i.name}</li>)}</ul>
   );
+  // a clickable row with no button semantics / keyboard support
+  return <div onClick={() => select(i)}>{i.name}</div>;
 }
```
`tests/eval/fixtures/accessibility/bad/div-onclick.expect.json`: `{"file": "frontend/src/Items.tsx"}`
`tests/eval/fixtures/accessibility/bad/img-no-alt.diff`:
```diff
--- a/frontend/src/Logo.tsx
+++ b/frontend/src/Logo.tsx
@@ -1,2 +1,3 @@ export function Logo() {
-  return <span>brand</span>;
+  return <img src="/logo.png" />;
 }
```
`tests/eval/fixtures/accessibility/bad/img-no-alt.expect.json`: `{"file": "frontend/src/Logo.tsx"}`
`tests/eval/fixtures/accessibility/good/semantic-button.diff`:
```diff
--- a/frontend/src/Items.tsx
+++ b/frontend/src/Items.tsx
@@ -10,3 +10,4 @@ export function Items() {
   return (
     <ul>{items.map((i) => <li key={i.id}><button onClick={() => select(i)}>{i.name}</button></li>)}</ul>
   );
 }
```
`tests/eval/fixtures/usability/bad/no-loading-error.diff`:
```diff
--- a/frontend/src/Items.tsx
+++ b/frontend/src/Items.tsx
@@ -3,4 +3,7 @@ export function Items() {
-  const { data } = useItems();
-  return <ul>{data.map((i) => <li key={i.id}>{i.name}</li>)}</ul>;
+  // no loading or error handling — blank/crash on slow or failed fetch
+  const [items, setItems] = useState<Item[]>([]);
+  useEffect(() => { fetch("/items").then((r) => r.json()).then(setItems); }, []);
+  return <ul>{items.map((i) => <li key={i.id}>{i.name}</li>)}</ul>;
 }
```
`tests/eval/fixtures/usability/bad/no-loading-error.expect.json`: `{"file": "frontend/src/Items.tsx"}`
`tests/eval/fixtures/usability/good/handled-states.diff`:
```diff
--- a/frontend/src/Items.tsx
+++ b/frontend/src/Items.tsx
@@ -3,4 +3,8 @@ export function Items() {
   const { data, isLoading, error } = useItems();
+  if (isLoading) return <p>Loading…</p>;
+  if (error) return <p role="alert">Failed to load items.</p>;
+  if (data.length === 0) return <p>No items yet.</p>;
   return <ul>{data.map((i) => <li key={i.id}>{i.name}</li>)}</ul>;
 }
```

- [ ] **Step 6: Run the registry test + the eval-fixture well-formedness check**

Run: `uv run --frozen pytest tests/review/test_registry.py::test_react_agents_active_on_pr_not_push -q` → PASS.
Run the eval harness fixture loader / the existing eval well-formedness test (grep `tests/` for the test that calls `load_fixtures` or runs `framework eval --offline`/a hermetic fixture check, and confirm the new `accessibility`/`usability` fixtures load — bad fixtures have valid `.expect.json`). If there's a hermetic "every bad fixture has a seeded file" test, it must stay green.

- [ ] **Step 7: Fast gate + commit**

Fast gate. Stage the two agent `.md` files, `registry.py`, the eval fixtures, `tests/review/test_registry.py` + `CLAUDE.md` `[8g T2]`. `git commit -m "feat(react): review-accessibility + review-usability agents + eval fixtures"`.

---

## Task 3: the `frontend/` SPA scaffold

**Files:** create the gated `frontend/` tree under `src/framework_cli/template/`; modify `tests/test_copier_runner.py`.

NOTE on gating: render `frontend/` only with the react battery. Use the brace-templated-directory convention the template already uses for gated packages (e.g. a top-level dir `{% if "react" in batteries %}frontend{% endif %}/...`). Files inside that are plain (Vite/TS configs are NOT `.jinja` unless they need interpolation; `package.json` may interpolate `{{ project_slug }}` for the name — if so make it `.jinja`). Verify the rendered output strips the brace dir to `frontend/`.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:
```python
def test_render_react_frontend_scaffold(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    fe = dest / "frontend"
    assert (fe / "package.json").exists()
    assert (fe / "vite.config.ts").exists()
    assert (fe / "src" / "Items.tsx").exists()
    assert (fe / "src" / "Items.test.tsx").exists()
    assert (fe / "e2e" / "items.spec.ts").exists()
    pkg = (fe / "package.json").read_text()
    assert "vite" in pkg and "vitest" in pkg and "@axe-core/playwright" in pkg
    # baseline omits the frontend entirely
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "frontend").exists()
```

- [ ] **Step 2: Run it → FAIL.**

- [ ] **Step 3: Create the frontend files** (under the gated dir). Minimal-but-real:

`frontend/package.json` (interpolates the project name — make it `package.json.jinja` if needed; otherwise a static name is fine):
```json
{
  "name": "frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview --port 5173",
    "test": "vitest run --coverage",
    "test:e2e": "playwright test",
    "lint": "eslint .",
    "format:check": "prettier --check .",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": {
    "@axe-core/playwright": "^4.10.0",
    "@playwright/test": "^1.48.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/jest-dom": "^6.5.0",
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "@vitest/coverage-v8": "^2.1.3",
    "eslint": "^9.12.0",
    "jsdom": "^25.0.1",
    "prettier": "^3.3.3",
    "typescript": "^5.6.3",
    "typescript-eslint": "^8.8.1",
    "vite": "^5.4.9",
    "vitest": "^2.1.3"
  }
}
```
`frontend/vite.config.ts` (React + the dev proxy + Vitest config):
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://app:8000";
const apiPaths = ["/items", "/health", "/heartbeat", "/metrics", "/docs", "/openapi.json"];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: backend, changeOrigin: true }])),
  },
  build: { outDir: "dist" },
  test: { environment: "jsdom", globals: true, setupFiles: "./src/setupTests.ts", coverage: { provider: "v8" } },
});
```
`frontend/tsconfig.json` + `frontend/tsconfig.node.json` (standard Vite React TS config — `target: ES2020`, `jsx: react-jsx`, `strict: true`, `moduleResolution: bundler`, include `src`).
`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>Demo</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```
`frontend/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
```
`frontend/src/api.ts`:
```ts
export type Item = { id: number; name: string };

export async function fetchItems(): Promise<Item[]> {
  const res = await fetch("/items");
  if (!res.ok) throw new Error(`items request failed: ${res.status}`);
  return (await res.json()) as Item[];
}
```
`frontend/src/App.tsx`:
```tsx
import { Items } from "./Items";

export function App() {
  return (
    <main>
      <h1>Items</h1>
      <Items />
    </main>
  );
}
```
`frontend/src/Items.tsx` (accessible + handles loading/error/empty — so it passes both review lenses):
```tsx
import { useEffect, useState } from "react";
import { fetchItems, type Item } from "./api";

export function Items() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchItems().then(setItems).catch(() => setError(true));
  }, []);

  if (error) return <p role="alert">Failed to load items.</p>;
  if (items === null) return <p>Loading…</p>;
  if (items.length === 0) return <p>No items yet.</p>;
  return (
    <ul aria-label="items">
      {items.map((i) => <li key={i.id}>{i.name}</li>)}
    </ul>
  );
}
```
`frontend/src/setupTests.ts`: `import "@testing-library/jest-dom";`
`frontend/src/Items.test.tsx` (Vitest component test — mocks fetch):
```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Items } from "./Items";

afterEach(() => vi.restoreAllMocks());

test("renders fetched items", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify([{ id: 1, name: "alpha" }]), { status: 200 }),
  );
  render(<Items />);
  await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
});

test("shows an error state on failure", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 500 }));
  render(<Items />);
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
});
```
`frontend/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173" },
});
```
`frontend/e2e/items.spec.ts` (Playwright + axe):
```ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("items page renders and has no axe violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Items" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```
`frontend/eslint.config.js` + `frontend/.prettierrc` (standard React+TS flat ESLint config + Prettier defaults).

- [ ] **Step 4: Run the render test → PASS.** Verify the gated dir renders to `frontend/` and is absent at baseline.

- [ ] **Step 5: Fast gate + commit**

Fast gate. Stage the `frontend/` tree + `tests/test_copier_runner.py` + `CLAUDE.md` `[8g T3]`. `git commit -m "feat(react): frontend/ Vite+React+TS SPA scaffold (Items page + Vitest + Playwright/axe)"`.

---

## Task 4: serving — dev compose service + Dockerfile build stage + main.py static mount + .gitignore + Taskfile

**Files:** modify `infra/compose/dev.yml.jinja`, `infra/docker/Dockerfile.jinja`, `src/{{package_name}}/main.py.jinja`, the project `.gitignore` (template), `Taskfile.yml.jinja`; modify `tests/test_copier_runner.py`.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:
```python
def test_render_react_serving_wiring(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "\n  frontend:\n" in dev and "node:" in dev
    dockerfile = (dest / "infra" / "docker" / "Dockerfile").read_text()
    assert "frontend-build" in dockerfile and "npm run build" in dockerfile
    main = (dest / "src" / "demo" / "main.py").read_text()
    assert "StaticFiles" in main and "frontend/dist" in main
    assert "frontend/dist" in (dest / ".gitignore").read_text()
    # baseline: none of it
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "frontend" not in (base / "infra" / "compose" / "dev.yml").read_text()
    assert "StaticFiles" not in (base / "src" / "demo" / "main.py").read_text()
    assert "frontend-build" not in (base / "infra" / "docker" / "Dockerfile").read_text()
```

- [ ] **Step 2: Run it → FAIL.**

- [ ] **Step 3: dev compose `frontend` service.** In `dev.yml.jinja`, add (gated, dev-profile; place after the existing dev services, before the `volumes:` block — match the file's whitespace-control style):
```jinja
{%- if "react" in batteries %}

  frontend:
    image: node:22
    profiles: ["dev"]
    working_dir: /app/frontend
    command: ["sh", "-c", "npm install && npm run dev -- --host"]
    ports:
      - "5173:5173"
    volumes:
      - ../../frontend:/app/frontend
      - frontend_node_modules:/app/frontend/node_modules
    depends_on:
      app:
        condition: service_healthy
{%- endif %}
```
And add the named volume to the `volumes:` block (gated, mirroring how `mongodata`/`redisdata` are added): `frontend_node_modules: {}`.

- [ ] **Step 4: Dockerfile `frontend-build` stage.** In `Dockerfile.jinja`, add a gated build stage BEFORE the `runtime` stage and a gated COPY into runtime:
```jinja
{%- if "react" in batteries %}
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
{%- endif %}
```
(Place this after the python `builder` stage. Then in the `runtime` stage, after `COPY --from=builder /app /app`, add:)
```jinja
{%- if "react" in batteries %}
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
{%- endif %}
```
The runtime image gains no Node — only `frontend/dist`.

- [ ] **Step 5: main.py static mount.** In `main.py.jinja`, in `create_app`, AFTER `include_routers(app)` and before `configure_tracing`/`return`, add (gated):
```jinja
{% if "react" in batteries %}
    from pathlib import Path

    _dist = Path("frontend/dist")
    if _dist.exists():
        from fastapi.staticfiles import StaticFiles

        # Serve the built SPA at / (index.html fallback for client-side routing). Mounted last so
        # the API routes above take precedence; only when the build output exists (prod image) —
        # in dev the Vite server serves the SPA, so this is skipped.
        app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
{% endif %}
```
(Confirm `StaticFiles(html=True)` serves `index.html` for `/`; if deep-link client routes need an explicit fallback, the acceptance test in Task 5 will reveal it — if so, add a catch-all GET route returning `index.html` that excludes the API path prefixes. Keep route order: mount AFTER `include_routers`.)

- [ ] **Step 6: .gitignore + Taskfile.** In the template's project `.gitignore`, add gated entries:
```jinja
{% if "react" in batteries %}frontend/node_modules/
frontend/dist/
{% endif %}
```
In `Taskfile.yml.jinja`, add gated tasks (thin npm wrappers, mirroring the existing task style):
```jinja
{% if "react" in batteries %}
  fe:dev:
    desc: Run the Vite dev server (frontend).
    cmds: ["npm --prefix frontend install", "npm --prefix frontend run dev"]
  fe:build:
    desc: Build the frontend (dist/).
    cmds: ["npm --prefix frontend run build"]
  fe:test:
    desc: Frontend unit tests (Vitest).
    cmds: ["npm --prefix frontend run test"]
  fe:lint:
    desc: Frontend lint + typecheck.
    cmds: ["npm --prefix frontend run lint", "npm --prefix frontend run typecheck"]
{% endif %}
```
(Verify the Taskfile `{% if %}` nesting + indentation match the existing gated-task blocks like `mongo:shell`.)

- [ ] **Step 7: Run the render test → PASS.** Render `["react"]` and `[]`; confirm `docker compose -f infra/compose/dev.yml --profile dev config` (react) exits 0 with the `frontend` service, and the `[]` renders are byte-identical (no react strings). Also: render `["react"]`, then in that project confirm `create_app()` imports cleanly with NO `frontend/dist` present (dev shape — the mount is skipped): `cd <dest> && uv run --frozen python -c "import sys; sys.path.insert(0,'src'); from demo.main import create_app; create_app()"` (needs the project's deps; if not synced, at least assert the gated block is guarded by `_dist.exists()` so it can't fail at import).

- [ ] **Step 8: Fast gate + commit**

Fast gate. Stage dev.yml/Dockerfile/main.py/.gitignore/Taskfile + test + `CLAUDE.md` `[8g T4]`. `git commit -m "feat(react): serve the SPA — Vite dev service, Dockerfile build stage, FastAPI static mount"`.

---

## Task 5: CI `frontend` job (gated LOCKED ci.yml) + live acceptance

**Files:** modify `.github/workflows/ci.yml.jinja`; modify `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:
```python
def test_render_react_ci_job(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["react"]})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "frontend:" in ci and "setup-node" in ci and "vitest" in ci.lower()
    import yaml
    yaml.safe_load(ci)  # valid YAML
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "setup-node" not in (base / ".github" / "workflows" / "ci.yml").read_text()
```

- [ ] **Step 2: Run it → FAIL.**

- [ ] **Step 3: Add the gated `frontend` CI job.** In `ci.yml.jinja`, add (gated, after the `build` job — match whitespace control so the `[]` render is byte-identical):
```jinja
{%- if "react" in batteries %}

  frontend:
    needs: integrity
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - name: install Playwright browsers
        run: npx playwright install --with-deps chromium
      - name: build + e2e (Playwright + axe)
        run: |
          npm run build
          npm run preview &
          npx wait-on http://localhost:5173
          E2E_BASE_URL=http://localhost:5173 npm run test:e2e
{%- endif %}
```
(NOTE: `wait-on` — either add it to devDependencies or replace with a shell poll loop. The e2e runs against `vite preview` serving the built `dist/`. The review-agent matrix needs NO ci.yml change — it's registry-driven.)

- [ ] **Step 4: Run the render test → PASS.** Confirm the `["react"]` ci.yml is valid YAML and the `[]` render is byte-identical (no `setup-node`).

- [ ] **Step 5: Add the live acceptance test** (scoped to what's tractable in-sandbox: render → npm ci + typecheck + vitest, then build the prod image and prove it serves the SPA). Add to `tests/acceptance/test_rendered_project.py`:
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the react frontend + the prod image",
)
def test_rendered_react_battery_passes(tmp_path: Path):
    import shutil
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert (dest / "frontend" / "package.json").exists()
    if shutil.which("npm"):
        assert subprocess.run(["npm", "ci"], cwd=dest / "frontend").returncode == 0
        assert subprocess.run(["npm", "run", "typecheck"], cwd=dest / "frontend").returncode == 0
        assert subprocess.run(["npm", "run", "test"], cwd=dest / "frontend").returncode == 0
    # the prod image builds (incl. the frontend-build stage) and serves the SPA at / while /items is JSON
    build = subprocess.run(
        ["docker", "build", "-f", "infra/docker/Dockerfile", "-t", "demo-react:ci", "."],
        cwd=dest, capture_output=True, text=True,
    )
    assert build.returncode == 0, "react app image build failed:\n" + build.stdout + build.stderr
```
(If `docker build` of the runtime that serves the SPA needs a running container to assert `/` returns HTML and `/items` returns JSON, extend with a `docker run` + `curl` against `/` and `/items` — but mind the DB dependency for `/items`; asserting `/` returns the SPA `index.html` and `/heartbeat` returns 200 is sufficient and DB-free. Keep it DB-free if possible.)

- [ ] **Step 6: Run the acceptance test, then CLEAN /tmp.** Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_react_battery_passes" -q`; then `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`. If `npm`/Playwright isn't available in-sandbox, the test still proves the image build (frontend-build stage) + scaffold; report what ran. If the build fails on the frontend stage, investigate + report.

- [ ] **Step 7: Fast gate + commit**

Fast gate. Stage ci.yml + tests + `CLAUDE.md` `[8g T5]`. `git commit -m "feat(react): gated frontend CI job + live acceptance (image builds + serves the SPA)"`.

---

## Task 6: integrity, downskill, and combinations

**Files:** `tests/test_copier_runner.py`.

- [ ] **Step 1: Integrity across combos.** Add (match the existing `test_integrity_*` imports/shape):
```python
import pytest


@pytest.mark.parametrize("batteries", [[], ["react"], ["react", "graphql"], ["react", "workers", "redis"]])
def test_integrity_green_for_react_combos(tmp_path, batteries):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []
```
Run it. `[]` MUST be green (no baseline manifest shift). If a combo fails, fix the Jinja whitespace in the gated LOCKED files (`ci.yml`/`dev.yml`/`Dockerfile`/`main.py`) until baseline + every combo is green.

- [ ] **Step 2: Downskill (force=False).** Add (reuse the existing `_git_init_commit` helper + `remove_battery` shape):
```python
def test_downskill_react_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["react"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "react", force=False)
    assert not (dest / "frontend").exists()
    assert "StaticFiles" not in (dest / "src" / "demo" / "main.py").read_text()
    assert "setup-node" not in (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert check(dest, ci=True) == []
```
Run it. If `--force` is demanded, confirm the 8b-1 byte-identity exclusion covers the gated shared files (`ci.yml`/`dev.yml`/`Dockerfile`/`main.py`/`.gitignore`/`Taskfile`); report rather than forcing if a genuine builder-shared file trips it.

- [ ] **Step 3: Run the new fast-tier tests → green.** `uv run --frozen pytest tests/test_copier_runner.py -k "integrity_green_for_react or downskill_react" -q`

- [ ] **Step 4: Full fast gate + commit.** Run the full fast gate. Stage tests + `CLAUDE.md` `[8g T6]`. `git commit -m "test(react): integrity across react combos + downskill"`.

---

## Final Review (controller, after all tasks)

Dispatch an opus whole-branch reviewer that RUNS the tooling. It must:
- Fast gate (`pytest -q --ignore=tests/acceptance`, ruff check, ruff format --check standalone, mypy src) with counts; `uv lock --check` (NO new framework dep — the Node toolchain is template-only) + `uv build`.
- Empirically: render `["react"]`/`[]`; the `frontend/` tree present for react, absent baseline; gated `ci.yml`/`dev.yml`/`Dockerfile`/`main.py` byte-identical without react (integrity `[]` green = no manifest shift); `active_agents("pull_request", ["react"])` includes accessibility+usability, `("push", ["react"])` excludes them; `graphql` still gates api-design (the `gates_agents` migration).
- `docker compose -f infra/compose/dev.yml --profile dev config` (react) exit 0 with the `frontend` service.
- Run ONLY `test_rendered_react_battery_passes` (heavy — /tmp-careful, clean after): the image builds (frontend-build stage) + (if npm available) the frontend suite passes.
- **OBS/SVC live-stack lesson:** confirm the gated edits don't break baseline live-stack acceptance tests (baseline renders no react → unaffected; read, don't run).
- Verdict: READY TO MERGE or NOT READY + severity-tagged blockers + fix.

Then proceed to `superpowers:finishing-a-development-branch`.

---

## Notes & Risks
- **No CORS / same-origin:** the SPA uses relative paths; Vite proxies backend paths in dev; prod is same-origin (FastAPI serves both). No `/api` prefix, no baseline-API change.
- **`main.py` mount only if `dist/` exists** — clean dev/prod split, no env flag; a react project's `create_app()` must not fail at import with no `dist/`.
- **`gates_agents` migration** touches shared review machinery + graphql — migrate graphql in Task 1, keep its api-design gating tested.
- **Node/Playwright heavy in-sandbox** — CI runs the full frontend job; the acceptance scopes to image-build + (if npm present) vitest. Report what runs where.
- **Byte-identity of gated LOCKED files** (`ci.yml`/`dev.yml`/`Dockerfile`/`main.py`) is the #1 regression class — Jinja whitespace control + the `[]` integrity guard (Task 6).
- **No new framework Python dep**; never touch the root `pyproject.toml`/`uv.lock` (the testcontainers-pollution lesson from the redis slice).

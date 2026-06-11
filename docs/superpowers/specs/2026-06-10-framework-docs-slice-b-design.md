# Framework Docs — Slice 22b: Per-Project Docs Battery — Design

> **Status:** brainstormed 2026-06-10. Successor to Slice 22a (framework's own published
> docs site, merged `513fa8e`). This slice is **template payload**: a `docs` battery that
> renders a self-contained, versioning-ready MkDocs+Material site *into* generated projects.

## Context

Slice 22a shipped the framework's **own** published docs site (`documentation/` docs_dir,
MkDocs+Material, GH Pages via `mkdocs gh-deploy`, no `mike`). It is framework-only — no
template payload — and is now live.

Slice 22b is the deferred other half: the **per-project docs scaffold dogfooded into
generated projects**, plus `mike` per-version docs and the project's OpenAPI embedded in the
site. Unlike 22a, every file here is template payload and is therefore governed by the
template conventions: render + acceptance tests, a clean first `pre-commit` pass, node24-pinned
workflow actions, and obs-completeness declarations.

A generated project already ships rich flat operational docs (`README/SECRETS/DEPLOY/
SERVICES/CLAUDE.md`) and live API docs at FastAPI's `/docs` + a committed `openapi.json`
(exported and drift-checked by the existing `task openapi:export`). This slice does **not**
replace any of those — it adds a *publishable, versioned* docs surface and cross-links to the
flat docs as the operational source of truth.

## Decisions (resolved during brainstorm)

1. **Delivery model = a `docs` battery (opt-in), not always-on.** A published docs site is
   genuinely optional for a backend service in a way that secrets/deploy docs are not, and an
   opt-in battery matches how every other optional capability is modeled (`--with docs`). This
   is the **first "tooling/meta" battery** — its whole job is rendering files conditionally; it
   adds no runtime/infra surface.

2. **`mike` is in — for the *versioning capability*, decoupled from any *deployment target*.**
   mike conflates two things; we keep one and reject the other:
   - **Versioning capability (keep):** multiple doc versions side-by-side, a Material
     version-selector dropdown, `latest` pointing at the newest. mike is the standard here
     (Material's native versioning *is* mike).
   - **Deployment-target assumption (reject):** mike does **not** require GitHub Pages.
     `mike deploy` commits built versioned HTML into a *branch* (default `gh-pages`) — a
     **portable artifact**. A team may enable GitHub Pages on it, rsync it to any static host,
     or just run `mike serve` locally with zero hosting. The framework provides a default
     `gh-pages`-branch publish as **one option**, never a lock-in.

3. **Tag-driven versioning.** On a release tag `vX.Y.Z`, publish `X.Y` and update the `latest`
   alias; `latest` is the default the site opens to. (Continuous `dev`/`latest`-on-every-push
   was considered and rejected — unneeded machinery for a generated service.)

4. **OpenAPI embedded as a *static* render.** The docs build renders the already-committed
   `openapi.json` (kept fresh + drift-checked by the existing `openapi:export` task/CI) via a
   swagger-render plugin — browsable in the static site with **no running app**. Preferred over
   linking to the live `/docs`, which needs a server.

5. **Build-strict on PR + portable publish on tag.** `docs.yml` runs `mkdocs build --strict` on
   every PR (always safe, no hosting assumption) and a mike publish to the `gh-pages` branch on
   a release tag. Nothing is *served* until the team opts in.

## Scope

### In scope (v1)

- **`docs` `BatterySpec`** in `src/framework_cli/batteries.py`: `obs="rides-existing"`, no
  `gates_agents` (the `documentation` reviewer remains advisory-on globally, independent of this
  battery). Selected via `framework new --with docs` / `upskill docs`.
- **`documentation/` docs_dir + `mkdocs.yml.jinja`**, rendered only when `docs` is active
  (`{% if "docs" in batteries %}` path/content guards). Material theme, version selector
  configured for mike. Seeded pages:
  - `index.md` — project overview / entry point.
  - **Architecture / how-it-works** — seeded for *this* project (links up to the framework
    site for cross-cutting concepts rather than restating them).
  - **API reference** — (a) static swagger render of the committed `openapi.json`, and (b)
    **mkdocstrings** Python API over `src/{{package_name}}`.
  - **See also** — links *out* to the project's flat `SECRETS/DEPLOY/SERVICES/README.md` (the
    operational source; no duplication) and *up* to the framework's published site.
- **`mike` versioning** wired tag-driven: `vX.Y.Z` → `mike deploy --push --update-aliases X.Y
  latest`; `latest` is the default version.
- **`docs.yml.jinja`** workflow (template payload): `mkdocs build --strict` on PR + mike
  publish to the `gh-pages` branch on release tag. node24-pinned actions
  (`actions/checkout@v5`, `astral-sh/setup-uv@v7` — already in `APPROVED_ACTIONS`).
- **Taskfile tasks** (rendered only with the battery): `docs:serve` (`mike serve`),
  `docs:build` (`mkdocs build --strict`), `docs:deploy` (tag-driven mike publish).
- **`docs` dependency-group** in the project `pyproject.toml.jinja` (mkdocs-material, mike,
  swagger-render plugin, `mkdocstrings[python]`), mirroring the framework's own `--group docs`.
- **Render-matrix coverage:** add `"docs"` → a strict docs-build job to
  `BATTERY_JOBS` in `dogfood.py` (alongside `react`→`frontend`, `consumers`→`contracts`) so the
  render-matrix actually exercises the generated docs build — the only thing that catches
  generated-docs-only breakage.

### Out of scope (v1 — YAGNI / deferred)

- **Battery-specific doc pages** — `graphql`/`react`/`websockets`/etc. get **no** dedicated
  doc pages yet; the seed is generic. (Future enhancement.)
- **Any forced hosting** — no assumption the project deploys to GitHub Pages; the publish is a
  portable branch artifact, opt-in to serve.
- **Continuous (per-push) doc publishing** — tag-driven only.

## Testing strategy (template-payload conventions)

- **Render** (`tests/test_copier_runner.py`): docs files render + interpolate **iff** `docs` is
  in `batteries`, and are **absent** when it is not (both directions asserted).
- **Acceptance** (`tests/acceptance/test_rendered_project.py`): in a rendered project with the
  battery, `mkdocs build --strict` is clean and the first `pre-commit` pass is clean.
- **node24** (`tests/test_workflow_node24.py`): every action in `docs.yml.jinja` is in
  `APPROVED_ACTIONS`.
- **obs-completeness** (`tests/test_obs_completeness.py`): the `docs` battery declares
  `rides-existing` (no new scrape/alert/dashboard surface).

## Open questions for the implementation plan

- **Swagger-render plugin choice** — pick the concrete plugin (e.g. `mkdocs-render-swagger-plugin`
  vs a swagger-ui-tag extension) during planning; the render-strict acceptance test is the gate.
- **mike + `gh-pages` interaction with the existing `release.yml`** — confirm the tag trigger in
  `docs.yml` composes cleanly with the project's release flow (ordering, permissions:
  `contents: write` for the branch push).
- **`mike serve` vs `mkdocs serve` in `docs:serve`** — `mike serve` shows the versioned site;
  confirm it's the right local DX default.

## Relationship to other plans

- **Deps:** Slice 22a (merged). Shares structure/lessons but no files.
- **Plan 23** (agent self-improvement) and **Plan 24** (`framework upgrade`) are unaffected;
  22b's versioned per-project docs are a natural consumer of a future `framework upgrade` UX but
  do not depend on it.

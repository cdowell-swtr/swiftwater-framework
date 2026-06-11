# Framework docs site (Slice 22a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the framework's canonical, self-contained, publicly-consumable documentation site (MkDocs + Material) — readable before any commitment — covering the framework and its rendered-project *concepts*, excluding the in-flight reviewer detail and the per-project scaffold (Slice 22b).

**Architecture:** A new MkDocs site rooted at `documentation/` (the `docs_dir`), config in `mkdocs.yml`, dev deps in a `uv` `docs` group. Reference pages auto-generate from the code (`mkdocs-typer` for the CLI, `mkdocstrings` for the `framework_cli` Python API). Content is hand-authored from the design spec (`docs/superpowers/specs/2026-05-20-framework-design.md`, §1–21) + the actual code/template, kept self-contained (no "see the in-project SECRETS.md" deferrals). `mkdocs build --strict` (MkDocs 1.6+ native nav/link/anchor validation) is the gate after every task; a `docs.yml` workflow runs it on PRs and `mkdocs gh-deploy`s on merge to `master`.

**Tech Stack:** MkDocs + Material, `mkdocstrings[python]`, `mkdocs-typer`, `uv`, GitHub Pages (gh-pages branch), GitHub Actions.

---

## Execution conventions (read before starting)

**Branch:** `plan-22-docs` (already created off `master`; the spec is already committed there). Do NOT branch again.

**Review-model policy (RESTATED per CLAUDE.md):** implementers → **Sonnet** (Haiku for trivial); spec-compliance review → **Sonnet**; doc-quality / code-quality review → **Opus**; final whole-branch review → **Opus**. Pass `model` explicitly per role.

**The gate is `mkdocs build --strict`** — MkDocs 1.6+ fails on any broken nav entry, missing page, unresolved `mkdocstrings`/`mkdocs-typer` reference, broken internal link, or bad anchor. Run it after every content task. All mkdocs commands run through the docs group: **`uv run --group docs mkdocs <cmd>`**.

**Commit cadence:** this is docs-only (no `src/` changes), so the per-commit reviewers-gate hook skip-neutrals (no backend configured). Standard commits. Per CLAUDE.md, **update CLAUDE.md's Current State + `git add CLAUDE.md` before each commit** (the PreToolUse hook blocks otherwise); keep those edits minimal (this branch shares CLAUDE.md + the meta-plan with `plan-21-reviewer-tuning`, so minor merge resolution is expected at integration). Per [[commit-gate-hook-timing]]: `git add` then `git commit` as **separate** Bash calls; keep "commit" out of Bash command descriptions.

**Content source map (per design spec section):** Overview→§1/§2/§20; Quickstart→README + `framework new`; Using→§3 + the CLI; Upgrading(planned)→§16; Working/structure→§3; run-locally→§15; observability→§8; deploy→§14 + `DEPLOY.md.jinja`; services→`SERVICES.md.jinja` + batteries; secrets/env-parity→§9/§10 + `SECRETS.md.jinja`; quality-gates→§5/§6; interfaces→§11/§13 + batteries; review-concept→§4/§7; design-principles→§1/§2/§20. **Self-contained rule:** write the full story on the page; reference in-project docs only as "your generated project also ships a `SECRETS.md` with your specific values," never as the place to go *learn* it.

---

## Phase 1 — Site scaffold + tooling (the site builds & deploys)

### Task 1: MkDocs scaffold that builds strict

**Files:**
- Modify: `pyproject.toml` (add a `docs` dependency group)
- Create: `mkdocs.yml`
- Create: `documentation/index.md`
- Modify: `.gitignore` (ignore `site/`)

- [ ] **Step 1: Add the docs dependency group**

```bash
uv add --group docs mkdocs-material "mkdocstrings[python]" mkdocs-typer
```
Expected: `pyproject.toml` gains `[dependency-groups] docs = [...]` and `uv.lock` updates.

- [ ] **Step 2: Create `mkdocs.yml`** (theme, plugins, strict validation, minimal nav)

```yaml
site_name: swiftwater-framework
site_description: An opinionated Python scaffold framework with TDD, quality gates, observability, and environment parity built in.
repo_url: https://github.com/cdowell-swtr/swiftwater-framework
docs_dir: documentation

theme:
  name: material
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
    - toc.follow

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [src]
          options:
            show_source: false
            docstring_style: google

# MkDocs 1.6+ native validation — `--strict` turns these into build failures.
validation:
  nav:
    omitted_files: warn
  links:
    not_found: warn
    anchors: warn
    unrecognized_links: warn

nav:
  - Home: index.md
```

- [ ] **Step 3: Create `documentation/index.md`** (placeholder, replaced in Task 4)

```markdown
# swiftwater-framework

Documentation site — under construction.
```

- [ ] **Step 4: Ignore the build output**

Add to `.gitignore`:
```
# MkDocs build output
site/
```

- [ ] **Step 5: Verify the site builds strict**

Run: `uv run --group docs mkdocs build --strict`
Expected: `INFO - Documentation built in …` with **no warnings** (exit 0). If it errors on an unknown plugin, confirm Step 1 installed it.

- [ ] **Step 6: Commit** (update CLAUDE.md Current State first, then:)

```bash
git add pyproject.toml uv.lock mkdocs.yml documentation/index.md .gitignore CLAUDE.md
```
```bash
git commit -m "docs(22a): MkDocs + Material scaffold that builds --strict"
```

### Task 2: Auto-generated reference (CLI + Python API)

**Files:**
- Create: `documentation/reference/cli.md`
- Create: `documentation/reference/api.md`
- Modify: `mkdocs.yml` (nav + ensure `mkdocs-typer` is enabled)

- [ ] **Step 1: CLI reference page** — `documentation/reference/cli.md`

`mkdocs-typer` renders the Typer app. The framework's app object is `framework_cli.cli:app`:
```markdown
# CLI reference

::: mkdocs-typer
    :module: framework_cli.cli
    :command: app
    :prog_name: framework
```
(If the directive name differs in the installed `mkdocs-typer` version, use the form in its README; the target is always `framework_cli.cli:app`.)

- [ ] **Step 2: Python API reference page** — `documentation/reference/api.md`

`mkdocstrings` renders docstrings. Scope to the **public** `framework_cli` modules — **never `framework_cli.template`** (that's payload, not API):
```markdown
# Python API

::: framework_cli.naming

::: framework_cli.copier_runner
```
(Add other public modules as useful; do NOT add `framework_cli.template.*`.)

- [ ] **Step 3: Wire nav + enable the typer plugin in `mkdocs.yml`**

Add `mkdocs-typer` to `plugins:` (above `mkdocstrings`) and extend `nav:`:
```yaml
plugins:
  - search
  - mkdocs-typer
  - mkdocstrings:
      # … (unchanged from Task 1)
nav:
  - Home: index.md
  - Reference:
      - CLI: reference/cli.md
      - Python API: reference/api.md
```

- [ ] **Step 4: Verify the reference resolves under strict**

Run: `uv run --group docs mkdocs build --strict`
Expected: build succeeds; the CLI page shows the `framework` commands and the API page shows the module docs. A FAIL here means the plugin can't import `framework_cli` — confirm `paths: [src]` (mkdocstrings) and that `uv sync` installed the package.

- [ ] **Step 5: Commit**

```bash
git add documentation/reference mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): auto CLI (mkdocs-typer) + Python API (mkdocstrings) reference"
```

### Task 3: CI workflow — build on PR, deploy on merge

**Files:**
- Create: `.github/workflows/docs.yml`
- Modify: `tests/test_workflow_node24.py` ONLY if it flags `docs.yml` (it shouldn't — see Step 2)

- [ ] **Step 1: Create `.github/workflows/docs.yml`**

Uses only already-approved actions (`actions/checkout@v5`, `astral-sh/setup-uv@v7`); `mkdocs gh-deploy` pushes the built site to the `gh-pages` branch, so no GitHub-Pages actions need adding to the node24 allow-list:
```yaml
name: docs

on:
  pull_request:
  push:
    branches: [master]

permissions:
  contents: write   # gh-deploy pushes to the gh-pages branch

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv run --group docs mkdocs build --strict

  deploy:
    needs: build
    if: github.ref == 'refs/heads/master' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv run --group docs mkdocs gh-deploy --force
```

- [ ] **Step 2: Confirm the Node-24 workflow guard still passes**

Run: `uv run pytest tests/test_workflow_node24.py -q`
Expected: PASS (both actions are already in `APPROVED_ACTIONS`). If it FAILS naming an action in `docs.yml`, that action isn't approved — switch to an approved equivalent rather than loosening the guard.

- [ ] **Step 3: One-time repo note (not a code change)**

Record in the PR description: after merge, set **GitHub repo → Settings → Pages → Source = `gh-pages` branch** so the deployed site serves. (Cannot be done from the workflow; it's a repo setting.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/docs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): docs.yml — build --strict on PR, gh-deploy on master"
```

---

## Phase 2 — Content authoring

Each task creates a nav group of hand-authored pages, draws content from the mapped spec sections + the real code/template, keeps every page **self-contained**, and ends green under `mkdocs build --strict`. The *prose* is authored at execution (it IS the work); each step below fixes the page's **required outline, sources, and cross-links** so the author can't drift scope.

### Task 4: Overview group (the evaluator's entry)

**Files:**
- Replace: `documentation/index.md`
- Create: `documentation/overview/why.md`, `documentation/overview/what-you-get.md`, `documentation/overview/quickstart.md`
- Modify: `mkdocs.yml` (nav)

- [ ] **Step 1: Author the pages to these outlines**

- `index.md` — one-screen landing: what the framework is (1 paragraph from §1), the 3 audiences, and links into the two journeys + Quickstart.
- `overview/why.md` — the value proposition + a *brief* of the design philosophy (full version is the design-principles page); source §1 (Purpose/Goals) + §2 (Core Architecture) + §20 (dogfooding). Link to `working-in-your-project/design-principles.md`.
- `overview/what-you-get.md` — concrete enumeration of what a scaffolded project ships (TDD, quality gates, observability, env-parity, batteries) from §2/§3/§8/§9; each item links to its deep-dive page.
- `overview/quickstart.md` — the shortest path: install the CLI → `framework new` → run it → see it work. Source: README + `framework new` (CLI). Self-contained (don't defer to README).

- [ ] **Step 2: Wire nav**

```yaml
nav:
  - Home: index.md
  - Overview:
      - Why this framework: overview/why.md
      - What you get: overview/what-you-get.md
      - Quickstart: overview/quickstart.md
  - Reference: …   # (existing)
```

- [ ] **Step 3: Verify + commit**

Run: `uv run --group docs mkdocs build --strict` → PASS (no broken links/anchors).
```bash
git add documentation/index.md documentation/overview mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): Overview group (why / what-you-get / quickstart)"
```

### Task 5: "Using the framework" group

**Files:**
- Create: `documentation/using/install.md`, `using/new-and-batteries.md`, `using/batteries-add-remove.md`, `using/upgrading.md`, `using/the-cli.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Author to these outlines**

- `install.md` — install the `framework` CLI + prerequisites (`uv`); source README + pyproject. Self-contained.
- `new-and-batteries.md` — `framework new`, the wizard, choosing batteries, what rendering produces; source §3 + the CLI + the battery system.
- `batteries-add-remove.md` — upskill/downskill (add/remove batteries on an existing project); source the `upskill`/`downskill` CLI commands. **Be explicit that this is *batteries*, not framework-version upgrades** (which is the next page).
- `upgrading.md` — **the *planned* `framework upgrade` flow** (pull a project onto a newer framework release): the intended UX (Copier `copier update` re-render against the new tag; rollback via the project's git history); source §16. **Mark clearly as planned/forthcoming** (a callout admonition) so readers don't try a command that doesn't exist; link to the Plan-24 intent.
- `the-cli.md` — orientation to the CLI as a tool (what the commands are for); link down to the auto-generated `reference/cli.md` for the exhaustive list.

- [ ] **Step 2: Wire nav** (a `Using the framework:` section before `Working in your project`).

- [ ] **Step 3: Verify + commit**

Run: `uv run --group docs mkdocs build --strict` → PASS.
```bash
git add documentation/using mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): Using the framework group (install/new/batteries/upgrading-planned/cli)"
```

### Task 6: "Working in your project" — operations

**Files:**
- Create: `documentation/working/structure.md`, `working/run-locally.md`, `working/observability.md`, `working/deploy.md`, `working/services.md`, `working/secrets-and-env-parity.md`, `working/quality-gates.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Author to these outlines** (each self-contained; cross-link siblings)

- `structure.md` — the rendered project layout + what each part is; source §3.
- `run-locally.md` — the local dev experience (compose profiles, `task`/tooling); source §15.
- `observability.md` — the obs stack (metrics/logs/traces, auto-instrumentation, the dev↔prod parity, obs-infra-scaling guidance); source §8. *(This is also the canonical home for the OBS-COMPLETE Facet-3 obs-infra-scaling guidance per the meta-plan.)*
- `deploy.md` — the deploy model + CI/CD; source §14 + `DEPLOY.md.jinja`. Reference (don't defer to) the in-project `DEPLOY.md`.
- `services.md` — battery services (postgres/redis/mongo/worker/beat) across dev/prod; source `SERVICES.md.jinja` + the services overlay.
- `secrets-and-env-parity.md` — **the canonical home for the API-key/secret-naming convention** (per the meta-plan) + the environment model (dev→ci→stage→prod parity); source §9 + §10 + `SECRETS.md.jinja`.
- `quality-gates.md` — the gate (pytest/ruff/mypy/pre-commit) + the coverage model; source §5 + §6.

- [ ] **Step 2: Wire nav** (a `Working in your project:` section; these pages first, the interfaces/review/principles group from Task 7 after).

- [ ] **Step 3: Verify + commit**

Run: `uv run --group docs mkdocs build --strict` → PASS.
```bash
git add documentation/working mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): Working in your project — operations (structure/run/obs/deploy/services/secrets/gates)"
```

### Task 7: "Working in your project" — interfaces, review concept, principles

**Files:**
- Create: `documentation/working/interfaces.md` (+ optionally one page per interface), `working/review-system.md`, `working/design-principles.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Author to these outlines**

- `interfaces.md` — the "Your project's interfaces" group: one section each for **REST/OpenAPI** (auto `/docs`,`/redoc`,`/openapi.json`), **GraphQL/SDL** (graphql battery), **Webhooks**, **WebSockets**, **Consumer/provider contracts/Pact** (consumers battery). For webhooks + websockets, **name the AsyncAPI gap honestly** (no auto machine-readable spec today; future enhancement). Note Workers is *not* an interface (internal background processing). Source §11 + §13 + the batteries. A static snippet/screenshot of the baseline `/docs` is fine; **do NOT render a project at docs-build**.
- `review-system.md` — **concept only**: the Layer-3 review agents, the commit/CI gate, the eval harness, why it exists; source §4 + §7. **No per-agent/prompt/threshold detail.** One line: "the detailed per-agent reference is published after the Plan-21 reviewer re-tuning lands."
- `design-principles.md` — the anti-antipattern philosophy: separation-of-concerns, expose-capability-not-policy, offload-architecture-from-the-builder, env-parity by construction, dogfooding; source §1/§2/§20. This is the spine the Overview/why page summarizes.

- [ ] **Step 2: Wire nav** (append to the `Working in your project:` section).

- [ ] **Step 3: Verify + commit**

Run: `uv run --group docs mkdocs build --strict` → PASS.
```bash
git add documentation/working mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): interfaces group + review-system (concept) + design principles"
```

### Task 8: Contributing group

**Files:**
- Create: `documentation/contributing/index.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Author** — thin: dev setup (`uv sync`, the gate `uv run pytest/ruff/mypy`), how docs are built/served (`uv run --group docs mkdocs serve`), and where the specs/plans/meta-plan live; source §17 + §20 + CLAUDE.md (summarize; don't copy the working agreement verbatim).

- [ ] **Step 2: Wire nav** (a `Contributing:` section last).

- [ ] **Step 3: Verify + commit**

Run: `uv run --group docs mkdocs build --strict` → PASS.
```bash
git add documentation/contributing mkdocs.yml CLAUDE.md
```
```bash
git commit -m "docs(22a): Contributing group + dev/docs workflow"
```

---

## Phase 3 — Finalize

### Task 9: Whole-site verification + branch-end review

- [ ] **Step 1: Full strict build + link/anchor integrity**

Run: `uv run --group docs mkdocs build --strict`
Expected: clean build; every nav entry resolves; no broken internal links or anchors (MkDocs validation). Manually confirm the nav matches the spec IA (Overview / Using / Working in / Reference / Contributing) and that no page defers learning to an in-project doc the reader can't see.

- [ ] **Step 2: Confirm nothing else regressed**

Run: `uv run pytest tests/test_workflow_node24.py -q && uv run ruff format --check documentation 2>/dev/null || true`
Expected: node24 guard PASS. (No `src/` changed, so the main gate is unaffected; docs markdown isn't linted by ruff.)

- [ ] **Step 3: Branch-end Opus review** (superpowers:requesting-code-review)

Scope: self-containment (no page requires the repo to be understood), accuracy against the code/spec, the bounded sections honored (review concept-only; upgrading marked planned; AsyncAPI gap named), nav/IA matches the spec, no scope creep into Slice 22b or reviewer detail. Address findings (receiving-code-review).

- [ ] **Step 4: Finish the branch** (superpowers:finishing-a-development-branch)

Present merge options to the user. On merge to `master`: the `docs.yml` deploy job runs `mkdocs gh-deploy`; then set repo Pages source = `gh-pages` (Task 3 Step 3). Update the meta-plan row to ✅ 22a done; resolve the expected CLAUDE.md/meta-plan overlap with `plan-21` at merge time.

---

## Self-review notes (author)

- **Spec coverage:** tooling/Material/mkdocstrings/mkdocs-typer/`documentation/`/GH-Pages/no-mike → Tasks 1–3; self-containment discipline → enforced in every Phase-2 task's outline + Task 9 Step 1; IA (Overview/Using/Working-in/Reference/Contributing) → Tasks 2,4–8; bounded sections (review-concept, upgrading-planned, interfaces+AsyncAPI-gap, design-principles) → Tasks 5,7; verification (build --strict, no renders) → every task + Task 9. All spec sections mapped.
- **Data-driven content:** Phase-2 prose is authored at execution (it is the deliverable); each task fixes the outline + sources + cross-links + the `--strict` gate, so the procedure is concrete even though the prose isn't pre-written — not a placeholder.
- **Consistency:** the gate command `uv run --group docs mkdocs build --strict` and the Typer target `framework_cli.cli:app` are identical across tasks; deploy is `mkdocs gh-deploy` (gh-pages) throughout, using only pre-approved actions.

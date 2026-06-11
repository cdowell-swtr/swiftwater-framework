# Framework documentation — Slice A (the framework docs site) — Design

**Date:** 2026-06-10
**Status:** Design (brainstormed). First slice of **Plan 22** (the end-to-end documentation pack).
**Branch:** `plan-22-docs` (off `master`; deliberately excludes the in-flight Plan 21 reviewer work).

> Plan 22 is **sliced**: **Slice A (this spec)** = the framework's own published docs site;
> **Slice B (later, own spec)** = a docs scaffold dogfooded *into* generated projects (with
> `mike` per-version docs + embedded per-project OpenAPI). Slice A is framework-only and touches
> no template payload.

## Problem

The framework ships no published documentation. A prospective adopter — public or internal —
has nothing to read to evaluate it; an existing user has no canonical reference. The only docs
today are (a) internal dev artifacts under `docs/superpowers/` + `docs/maintenance/`, and (b)
per-project operational docs (`SECRETS/DEPLOY/SERVICES/README.md`) that live **inside a rendered
project's repo** — invisible to anyone who hasn't already scaffolded a project.

## Goal

A **comprehensive, self-contained, publicly (or internally) consumable** documentation site for
the framework and its rendered-project *concepts* — fully readable **before any commitment**: no
repo checkout, no scaffolded project required.

## Audiences (in priority order)

1. **Evaluator** — deciding *whether* to adopt the framework. Needs the value proposition, the
   design philosophy, what you get, and a quickstart, all without scaffolding anything.
2. **Framework user** — scaffolding and operating projects via the `framework` CLI.
3. **In-project builder** — working day-to-day inside a generated project.

## The self-containment discipline (the load-bearing principle)

The published pack is **canonical, comprehensive, and self-contained.** Concepts *and*
how-it-works *and* operational guidance are all readable on the site itself. It does **not** defer
"down" to the per-project `SECRETS/DEPLOY/SERVICES.md` (which a reader without a project can't
see). In-project docs are the *targeted, in-context* companions ("here are *your project's*
specific secrets/services") and link **up** to the pack for the full story. Reconciling those
in-project docs to be thinner pointers touches **template payload**, so it is a **follow-up out of
Slice A** (a Slice-B / payload pass); Slice A writes the comprehensive pack and leaves the
in-project docs as they are.

The trade-off accepted: the pack carries the full operational story (more authoring) rather than
offloading it — the correct cost for docs that must stand alone.

## Information architecture (nav)

**0. Overview** *(serves the evaluator)*
- What the framework is · Why (design philosophy in brief, what you get) · **Quickstart**.

**1. Using the framework** *(the path to a project)*
- Install (the `framework` CLI + `uv` / prerequisites) · `framework new` & choosing batteries ·
  what gets rendered · adding/removing batteries (upskill/downskill) · **Upgrading (planned)** ·
  the CLI as a tool.

**2. Working in your project** *(life inside a generated project)*
- Project structure · run locally (compose/dev) · observability · deploy · services · secrets &
  env-parity · quality gates · **your project's interfaces** (group, see below) · **the review
  system (concept)** · **anti-antipattern design principles**.

**3. Reference** *(auto-generated)*
- **CLI reference** (`mkdocs-typer`, from the Typer app) · **Python API** (`mkdocstrings`, scoped
  to `framework_cli` public modules — **excluding `framework_cli/template/`**). *The detailed
  per-agent reviewer reference slots in here post-Plan-21.*

**4. Contributing** *(thin)*
- Dev setup · the quality gate · where the plans/specs live.

### "Your project's interfaces" topic group (under §2)

One topic per third-party-facing interface, documenting the capability + the spec artifact it
produces, and **honestly naming gaps**:
- **REST → OpenAPI/Swagger** — auto, baseline (FastAPI `/docs`, `/redoc`, `/openapi.json`).
- **GraphQL → SDL + introspection** — auto, graphql battery.
- **Webhooks** — event/payload contracts; **no auto machine-readable spec today** (the standard
  would be AsyncAPI — named as a known gap / future enhancement).
- **WebSockets** — message protocol; same AsyncAPI gap.
- **Consumer/provider contracts → Pact** — consumers battery.

(Workers/Celery is **not** here — it is internal background processing, not a published contract;
it is documented under §2 "background processing".)

### Bounded sections (write now, with explicit edges)

- **Review system — concept only.** What it is (Layer-3 review agents, the commit/CI gate, the
  eval harness), why it exists, how the gate behaves — **no** per-agent/prompt/threshold detail
  (Plan 21 is rewriting those). A one-liner notes the detailed reference lands post-Plan-21.
- **Upgrading — documented as the *intended* flow, marked *planned*.** The target UX (`framework
  upgrade` ≈ Copier `copier update` re-render against the new template tag; rollback via the
  project's own git history). Clearly flagged so the site never implies a phantom command works.
  Authoring this section doubles as (a) a stress-test that the docs IA cleanly expresses an
  evolving, version-aware capability, and (b) the de-facto UX spec for the separate `framework
  upgrade` plan.
- **Anti-antipattern design principles.** A curated page on *why* the scaffold is shaped as it is
  — separation-of-concerns, expose-capability-not-policy, offload-architecture-from-the-builder,
  env-parity by construction, dogfooding. The philosophical spine tying the two journeys together;
  summarised in the Overview for evaluators.

## Tooling

- **MkDocs + Material**, Markdown source.
- **`mkdocstrings[python]`** — Python API reference (scoped to `framework_cli` public modules;
  `framework_cli/template/` excluded as payload).
- **`mkdocs-typer`** — CLI reference rendered from the Typer app.
- A **link-check** (e.g. `mkdocs build --strict` covers nav/ref integrity; add a link-check plugin
  or `lychee` step for cross/external links).
- Dev deps live in a **`uv` `docs` dependency group**, isolated from runtime deps.
- **No `mike`** in Slice A (single live "latest" site). Per-version docs belong to Slice B
  (projects upgrade across framework releases; the *framework* itself doesn't need versioned docs).

## Repository structure

- **`documentation/`** at repo root = the MkDocs `docs_dir` (public-site source). Keeps the
  existing `docs/` tree (internal `superpowers/` + `maintenance/`) untouched — clean separation:
  `docs/` = internal/dev, `documentation/` = the published site.
- **`mkdocs.yml`** at repo root.
- MkDocs output dir (`site/`) is gitignored.

## CI / deploy

- A **`.github/workflows/docs.yml`** (Node-24-pinned actions per the repo convention):
  - **On PR:** `uv run mkdocs build --strict` + the link-check (fail the build on any broken
    nav/ref/link).
  - **On merge to `master`:** deploy to **GitHub Pages**.
- **Dev loop:** `uv run mkdocs serve` for live preview.

## Verification

- **`mkdocs build --strict`** is the gate — fails on any broken nav entry, missing page, or
  unresolved `mkdocstrings`/`mkdocs-typer` reference. This doubles as a check that `framework_cli`
  still imports cleanly (the auto-ref build imports it).
- **Link-check** catches dead cross-links.
- **No generated-project renders** — Slice A is framework-only; interface examples are
  static/conceptual (a screenshot/snippet of the baseline `/docs`, not a live render).

## Non-goals (Slice A)

- The **per-project docs scaffold** (dogfooded into generated projects) — Slice B.
- The **detailed reviewer reference** (per-agent prompts/thresholds) — post-Plan-21.
- **Building** `framework upgrade` — its own plan; Slice A only documents the intended UX.
- **AsyncAPI emission** / an **API portal** — future battery work.
- **Thinning the in-project docs** to point up — a template-payload follow-up.
- `mike` per-version docs — Slice B.

## Deferred / related work (to record in the meta-plan)

- **Plan 22 Slice B** — per-project docs scaffold (MkDocs into generated projects) + `mike` +
  embedded per-project OpenAPI. *(deps: Slice A)*
- **`framework upgrade` + rollback** — new CLI capability (Copier `copier update` basis; git-revert
  rollback). Own brainstorm → plan; the Slice-A "Upgrading (planned)" page is its UX seed.
- **AsyncAPI emission for the webhooks/websockets batteries** — fold the spec into each interface
  battery (cohesion), not a standalone docs battery.
- **Public API portal (speculative)** — a slim cross-cutting battery aggregating active interfaces'
  specs for third parties; YAGNI until a real external-portal need appears.
- **Docs-pack reviewer / coverage check** → **Plan 23+** (with the other self-improvement
  reviewers; `review-documentation` already exists as an advisory agent).

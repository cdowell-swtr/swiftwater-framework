# FWK9 — Propagate the patterns convention roster into generated projects

*Design spec. 2026-06-18. Status: approved (brainstorming → writing-plans).*

## Summary

Make every project produced by `framework new` **born adopting** the full
[`cdowell-swtr/patterns`](https://github.com/cdowell-swtr/patterns) convention
roster — all five live conventions:

| Convention | Tag | Marker | Pointer lives in | Enforcement |
|---|---|---|---|---|
| Planning Instrument | `pi/v2` | `PI-convention: v2` | `AGENTS.md` | agent-upheld |
| Committed Memory | `memory/v1` | `MEMORY-convention: v1` | `CLAUDE.md` | agent-upheld + gitleaks |
| Docs layout | `docs-layout/v1` | `DOCS-convention: v1` | `AGENTS.md` | pre-commit validator |
| Git | `git/v1` | `GIT-convention: v1` | `AGENTS.md` | conventional-pre-commit + gitleaks |
| Superpowers model routing | `superpowers-model-routing/v1` | `SUPERPOWERS-MODEL-ROUTING-convention: v1` | `CLAUDE.md` | agent-upheld |

The generated project consumes these as **template payload**: pointer blocks +
seeded stateful files + public/vendored validators. It does **not** vendor the
convention doc bodies and does **not** fetch anything at runtime.

## Goals / non-goals

**Goals**
- A fresh render is born adopted: pointer blocks present, stateful PI/MEMORY
  files seeded, both convention validators wired and green.
- **Zero runtime dependency on the private `patterns` repo.** The framework is
  public; `patterns` is private. Nothing a consumer runs (pre-commit, the agent
  at session start) may require `patterns` access.
- **Future-proof against doc drift:** cite `patterns` as the spec authority
  rather than vendoring the ~6 KB doc bodies (the part that goes stale).
- Stateful files survive `framework upgrade`/`restore` — a consumer's `PLAN.md`
  is never clobbered.
- The chosen task-ID prefix is captured once and stable across upgrades.

**Non-goals**
- No auto-registration of generated projects in patterns' implementer
  registries (would flood them with throwaways; nothing to register at render
  time). Documented as an optional consumer step only.
- No change to the framework's **own** (non-)adoption of docs-layout / git /
  model-routing — out of scope for FWK9.
- No vendored convention doc bodies; no live fetch of `patterns`.

## Why this shape (decisions)

1. **Full roster, not just PI+MEMORY.** FWK9 predated the roster's growth from 2
   to 5 conventions. The `CONVENTIONS-INDEX.md` "adopt-all (new project, from
   zero)" path *is* exactly what a generated project should do.
2. **Born-adopted + patterns-cited, not "adopt live."** A directive telling the
   project to pull conventions live from `patterns` would bake a **private-repo
   runtime dependency into a public artifact** — only the owner could satisfy
   it, it would leak `patterns` into public history, and it would break the
   framework's render-and-exercise quality model (nothing rendered to test).
   Rejected. The future-proofing it sought is recovered by **citing** patterns
   instead of vendoring doc bodies.
3. **Vendor the docs-layout validator script.** The convention wires its
   validator by pulling it from `patterns` at `rev: docs-layout/v1`; pre-commit
   would clone that **private** repo. To stay public-safe the 30-line zero-dep
   bash validator is vendored into the template as a `local` hook instead.
   (Git's hooks — gitleaks + conventional-pre-commit — are **public** repos, so
   they are referenced normally.)
4. **Prefix via a copier question.** Each PI repo needs a short uppercase
   task-ID prefix. A `pi_prefix` copier question (derived default, overridable),
   persisted in `.copier-answers.yml`, puts the "choose once" decision where the
   convention wants it and keeps it stable across upgrades.
5. **PI stays agent-upheld in generated projects.** The framework's own bespoke
   `PreToolUse` commit-gate hook is a framework-dev choice, not part of the
   convention; imposing it on every consumer is heavier than the convention
   asks. The pointer block tells the agent to maintain the trail.

## What gets added to the template

All paths below are under `src/framework_cli/template/`.

### A. Copier question — `pi_prefix`

Add to `copier.yml`:

```yaml
pi_prefix:
  type: str
  help: PI task-ID prefix (short uppercase tag, e.g. FWK, MDN)
  default: "{{ (project_slug | upper | replace('-', '') | replace('_', ''))[:4] }}"
```

- Derivation: uppercase the slug, drop separators, take the first 4 alphanumerics
  (`meridian` → `MERI`, `my-app` → `MYAP`). Overridable at the prompt.
- Persisted in `.copier-answers.yml`; re-render at `upgrade` reproduces the same
  prefix, so the managed AGENTS.md PI block stays stable.

### B. Managed (framework-owned) — pointer blocks + validator

Re-rendered on `upgrade`/`restore` to stay current. Each block carries its
`<NAME>-convention: vN` marker and **cites** the authoritative doc in `patterns`
(`full convention: cdowell-swtr/patterns/<doc> @ <tag>`) — no vendored body.

- **NEW `AGENTS.md.jinja`** → `integrity/classes.py: HYBRID_TRACKED`.
  A `FRAMEWORK:BEGIN/END` managed region holds the three **portable** pointer
  blocks, with a consumer area below the closing marker:
  - **PI** block, interpolating `{{ pi_prefix }}` for the task-ID prefix.
  - **docs-layout** block (internal `_docs/` vs external `documentation/`;
    superpowers specs/plans → `_docs/<ns>/<tool>/{specs,plans}/`, dated, with a
    `.tool` marker — *not* the skill's default `docs/superpowers/...`).
  - **git** block (branch/commit/tag practice; conventional commits).
  - Reuse the existing FRAMEWORK-managed-region marker convention; per the
    repo's hybrid-marker rule, never name the marker token in surrounding prose.

- **`CLAUDE.md.jinja`** (already `HYBRID_TRACKED`) — into the managed region add:
  - `@AGENTS.md` import (so the portable AGENTS.md blocks autoload in CC) and
    `@MEMORY.md` import (committed-memory index).
  - **MEMORY** pointer block (the public-safety boundary one-liner + marker).
  - **model-routing** pointer block (per-role model floors + marker).

- **`.pre-commit-config.yaml`** (already `HYBRID_TRACKED`) — into the managed
  region add:
  - `conventional-pre-commit` (`compilerla/conventional-pre-commit`, pinned)
    at `stages: [commit-msg]`.
  - top-level `default_install_hook_types: [pre-commit, commit-msg]`.
  - the vendored docs-layout **local** hook entry (calls
    `scripts/docs_layout_check.sh`).

- **NEW `scripts/docs_layout_check.sh`** → `LOCKED_TRACKED`. Vendored zero-dep
  validator with a provenance comment
  (`vendored from cdowell-swtr/patterns hooks/docs-layout-check.sh @ docs-layout/v1`).
  Public-safe; runs offline.

- **`Taskfile.yml`** (already `HYBRID_TRACKED`): ensure `task hooks` installs
  both hook stages (`pre-commit install --install-hooks` already runs; add the
  `commit-msg` stage so the conventional check is active).

### C. Seed-once stateful (consumer-owned)

Rendered once at `new`, **never overwritten** by `upgrade`/`restore`. Mechanism:
copier `_skip_if_exists` (so update never re-renders them) **and**
`integrity/classes.py: INTENTIONALLY_UNLOCKED` (so the reverse-coverage machinery
records the unlock as deliberate, not an escaped classification).

- `PLAN.md` — PI header + empty `Next` and `Done` sections.
- `ACTION_LOG.md` — header + a single seeded entry
  `#0001 · note · 2026-…`: "adopted PI/MEMORY/docs-layout/git/model-routing
  conventions via swiftwater-framework". (Date is the render date; templated.)
- `MEMORY.md` — empty committed-memory index + the boundary one-liner + the
  `MEMORY-convention: v1` marker.
- `_memory/.gitkeep` — keeps the empty dir tracked.
- `_archive/ARCHIVED_PLAN.md`, `_archive/ARCHIVED_ACTION_LOG.md` — header stubs.

`_skip_if_exists` glob entries in `copier.yml` cover exactly these paths.

## Integrity & coverage bookkeeping

- `src/framework_cli/integrity/classes.py`:
  - `HYBRID_TRACKED` += `AGENTS.md`.
  - `LOCKED_TRACKED` += `scripts/docs_layout_check.sh`.
  - `INTENTIONALLY_UNLOCKED` += `PLAN.md`, `ACTION_LOG.md`, `MEMORY.md`,
    `_archive/ARCHIVED_PLAN.md`, `_archive/ARCHIVED_ACTION_LOG.md`.
    (`_memory/.gitkeep` is a tracked keeper, not a managed surface — classify if
    the integrity tests require it; otherwise leave unmanaged.)
- FWK29 `tests/runtime_coverage/registry.py`: classify the new operational
  surfaces (the `docs-layout` local hook + the `conventional-pre-commit`
  commit-msg hook + `scripts/docs_layout_check.sh`) as EXERCISED (covered by the
  acceptance test below) — else `test_every_surface_is_classified` fails.

## Testing

**Render-level (`tests/test_copier_runner.py`)**
- `pi_prefix` interpolates into the AGENTS.md PI block (render with a known
  prefix → assert it appears; default-derivation case).
- AGENTS.md managed region contains all three portable markers (`PI-`, `DOCS-`,
  `GIT-convention:`); CLAUDE.md contains `@AGENTS.md`, `@MEMORY.md`, the MEMORY
  and model-routing markers.
- Seed files exist with expected headers; `ACTION_LOG.md` has `#0001 · note`.
- `.pre-commit-config.yaml` has the conventional hook at `commit-msg`,
  `default_install_hook_types` includes `commit-msg`, and the docs-layout local
  hook entry.

**Acceptance (rendered project; `tests/acceptance/`)**
- `pre-commit run --all-files` is green on a fresh render (docs-layout passes on
  the born layout; conventional/gitleaks installed).
- A conventional commit message passes the `commit-msg` hook; a malformed one is
  rejected (red→green non-vacuity).
- **Upgrade-idempotence:** render → edit `PLAN.md` (add a task) → `framework
  upgrade` → the edit is preserved and `pi_prefix` is unchanged (the seed-once
  seam holds).

**Format**
- ruff-format the rendered Python output (long-line / format-cleanliness class).

## Open implementation notes (resolved in the plan)

- Exact pointer-block wording is copied from each convention's published
  "AGENTS.md/CLAUDE.md block," adapted only to add the patterns citation line.
- Confirm `_skip_if_exists` is honored by the framework's `upgrade` path (copier
  update) — the upgrade-idempotence test is the proof.
- The generated README gets a one-paragraph "this project adopts the patterns
  conventions; to register it, append a row per each convention's runbook"
  optional note.

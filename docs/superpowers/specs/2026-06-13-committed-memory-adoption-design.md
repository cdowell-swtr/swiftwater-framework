# Plan 26 — Adopt the Committed Memory Convention

**Date:** 2026-06-13
**Status:** Design (brainstorm approved; pending spec review → plan)
**Convention adopted:** `../../patterns/memory-convention.md` (`MEMORY-convention: v1`)
**Meta-plan / PI ref:** Plan 26 = `PLAN.md` `T2` (deps `T1`, satisfied — Plan 25 merged `db5cdb9`)

## Purpose

Give the framework a committed, project-scoped agent memory that autoloads into
every session **on every machine** — alongside the existing native, machine-local
store, split by a public-safety boundary. The native store doesn't travel to
other machines, teammates, or fresh clones; project knowledge that everyone
working this repo should start with does. The Committed Memory convention —
shipped by the sibling `patterns` repo as a copy-by-hand markdown convention
(git + markdown + Claude Code's `CLAUDE.md` `@`-import; no tool/validator) — is
the MEMORY sibling to the PI work adopted in Plan 25. The framework is a
**consumer**.

This is a content + config migration, not feature code.

## Scope

**In scope:**
- **Wire gitleaks in the framework's *own* repo FIRST** (before any memory is
  committed): a root `.pre-commit-config.yaml` pinning the gitleaks hook +
  `pre-commit install`, AND a `security` job in the framework's own `ci.yml`
  running a full-repo scan. *(Corrected 2026-06-13: the framework's own repo has
  NO secret scanning — verified no root `.pre-commit-config.yaml` and no
  gitleaks in `.github/workflows/`. The v0.2.4 gitleaks fix was in the **template
  payload** (`src/framework_cli/template/.pre-commit-config.yaml` + the template's
  locked `ci.yml`), shipped to consumers — the framework ships a secret backstop
  it does not run on itself. The convention requires gitleaks before committing
  any memory, so this is in-scope work.)*
- Scaffold `MEMORY.md` (index) + `_memory/` at the repo root.
- Add the convention's `<!-- MEMORY-convention: v1 -->` block + `@MEMORY.md`
  import to CLAUDE.md.
- **Copy** the public-safe, project-scoped subset of the native store into
  `_memory/` (near-copy + `scope: project`).
- Self-register in patterns `_docs/committed-memory/implementers.md`.

**Out of scope (YAGNI):**
- **No template payload** — generated projects get no memory store; that is the
  recorded `PLAN.md` `T9` (propagate PI + MEMORY into generated projects).
- **No rewording, no client-referencing memories** (conservative curation):
  machine/personal, Meridian-naming, and session-only memories stay native.
- **No edits to the native store** — no deletes, no pruning of the native index.
  The user prunes native duplicates manually later.

## Decisions (from the approved brainstorm)

1. **Curation — conservative (option A).** Migrate only the clearly-safe
   framework-internal memories, verbatim (near-copy + `scope: project`). No
   rewording. Anything naming the client (Meridian), exposing machine/personal
   paths, or session-only stays native. "When in doubt, native."
2. **Move vs copy — copy (option B).** Migrated memories are *copied*; the native
   store is left entirely untouched (no deletes, no index pruning). Accepts
   transitional duplication (a migrated fact loads from both stores when working
   in this repo on this machine); the user prunes native later.
3. **gitleaks — wire it properly (option A): local pre-commit + framework CI
   job.** Closes the "ships a secret backstop it doesn't run on itself" gap. The
   framework's first root pre-commit config (gitleaks only, to stay minimal +
   non-disruptive — the framework otherwise gates via PreToolUse hooks + CI, not
   pre-commit) plus a `security` job in the framework's own `ci.yml`.

## Design

### Store structure & autoload

At the repo root, per the convention:
- **`MEMORY.md`** — the index: one line per memory,
  `- [Title](_memory/slug.md) — hook`. Autoloaded into every session via a
  committed `@MEMORY.md` import in CLAUDE.md.
- **`_memory/<slug>.md`** — one durable fact per file: native frontmatter +
  `scope: project` (the only delta from the native format) + body; `[[slug]]`
  resolves to `_memory/<slug>.md`.
- **CLAUDE.md** gains the `<!-- MEMORY-convention: v1 -->` block (boundary
  one-liner + never-commit pointer) and `@MEMORY.md` at the end. No bespoke hook
  — the committed CLAUDE.md `@`-import is the only mechanism, so it travels to
  every clone/machine with zero setup.

**Dual-load consequence of copy (acknowledged).** When working in this repo on
this machine, CLAUDE.md's `@MEMORY.md` loads the committed index **and** the
native `SessionStart` loads the native index — migrated facts appear in both
until native is pruned. On other machines/clones only the committed store loads
(the point of the convention).

### Curation rule (applied per-file during execution)

A native memory is copied **only if all three hold**: (1) about *the project*
(not you / your machine / one session), (2) useful on *any* machine, (3) safe to
publish (the repo is PUBLIC — a commit is an irreversible publish; git history
persists after deletion). Any failure → stays native.

- **Include** (~35–40 of 56) — framework/codebase gotchas and conventions:
  e.g. `hybrid-region-marker-token-in-prose`, `eval-fixture-patch-truncation`,
  `template-payload-tdd-loop`, `gate-cadence-framework-slices`,
  `release-cut-procedure`, `subagent-review-model-pattern`,
  `commit-gate-hook-false-matches-git-commit-substring`.
- **Exclude → native** — machine/personal (`laptop-dev-parity`,
  `full-suite-exhausts-tmp`, `subscription-quota-shared-across-projects`,
  `prefer-sandboxed-execution`, anything exposing `/home/chris` paths);
  client-naming (the 4 that name Meridian, incl.
  `meridian-is-the-de-facto-integration-test`); personal-preference feedback
  (`feedback_secrets-in-files`, `key-label-convention`); session-only.

**The exact set is decided in the implementation plan** — a per-file verdict
table (read each of the 56 native files, classify). The spec fixes the *rule*,
not the list.

### Link handling (one-directional, native untouched)

In each committed copy: a `[[slug]]` pointing to **another migrated** memory
stays `[[slug]]` (resolves in the committed store); a `[[slug]]` to a
**non-migrated** (native-only) memory is reworded to prose (the convention bars
cross-store committed→native links). Native files keep their links unchanged.

### Index

Build `MEMORY.md` from the migrated set. Verify bidirectional completeness: every
`_memory/*.md` is listed, and every index line points at a real file.

## Sequencing & registration

- **Branch** `plan-26-committed-memory` off `master` (Plan 25 merged, so CLAUDE.md
  is already slimmed with the PI pointer and a clean home for `@MEMORY.md`).
- **Registration (cross-repo).** Append the framework row to patterns
  `_docs/committed-memory/implementers.md`; tick patterns' `T8` + log it there.
  This hits the gate gotcha learned in Plan 25 — the session commit-gate hook
  checks *this* repo's staged files and fires before the `cd`, so a framework
  `PLAN.md`/`ACTION_LOG.md` change must be staged before the patterns commit.
- **PI tracking.** Tick `PLAN.md` `T2` through `Done` on completion; append
  `ACTION_LOG.md` entries at task grain — the adoption logs itself into the store
  PI provided.

## Verification

1. **gitleaks** — wired in this plan (local pre-commit + CI), gitleaks pinned
   `v8.21.2` (matching the template). Run a full-repo scan to confirm clean
   *before* the first memory commit; confirm `pre-commit install` wired the local
   hook. Backstop, not a substitute for the boundary rule.
2. **Autoload** — confirm `@MEMORY.md` resolves (CLAUDE.md imports the index).
3. **Convention invariants (manual)** — index ↔ files bidirectionally complete;
   every committed `[[slug]]` resolves to a real `_memory/` file (no dangling
   cross-store links); required frontmatter (`name`, `scope: project`) present;
   one fact per file.
4. **Boundary self-audit** — a final human re-read of every migrated file for
   leaked client names / machine paths / secrets before merge (judgment gitleaks
   can't do).
5. Full gate (`ruff` / `ruff format --check` / `mypy src`) stays green; no
   template payload touched.

## Risks & notes

- **Public repo = irreversible publish.** The conservative rule + the boundary
  self-audit + gitleaks are three independent layers; the asymmetry (a
  wrongly-native memory is merely unshared; a wrongly-published one is leaked
  forever) justifies defaulting to native.
- **Cross-repo commit.** Registration writes to the patterns repo — a separate,
  deliberate commit, with the gate gotcha handled as above.
- **Transitional duplication** is expected and accepted under the copy decision.

# Plan 25 — Adopt the Planning Instrument (PI) Convention

**Date:** 2026-06-12
**Status:** Design (brainstorm approved; pending spec review → plan)
**Convention adopted:** `../../patterns/pi-convention.md` (`PI-convention: v1`)
**Meta-plan row:** Plan 25 (forward sequence)

## Purpose

The framework's live planning state has accreted into two bloated, stale-prone
places: the CLAUDE.md "Current State" essay (a screenful of running "Last
updated" narrative) and the 177-line dated meta-plan
(`docs/superpowers/plans/2026-05-20-meta-plan.md`). The Planning Instrument (PI)
convention — shipped by the now-independent `../../patterns/` repo as a
copy-by-hand markdown convention, **not** an installed tool — bounds the
always-loaded context: current state in a lean `PLAN.md`, the event narrative in
an append-only `ACTION_LOG.md`, full historical detail in a cold `_archive/`,
and CLAUDE.md reduced to a stable Working-Agreement doc plus a lean pointer.

The framework is a **consumer** of the convention. This plan does not own,
implement, or version PI; it adopts v1 and migrates our state onto it.

## Scope

**In scope** — the framework's *own* planning state:
- Scaffold the four PI artifacts at the framework repo root.
- Migrate live planning state into them (archive-wholesale + fresh log).
- Slim CLAUDE.md to the Working Agreement + a PI pointer.
- Re-target the commit-gate hook.
- Self-register as a PI adopter in the patterns repo.

**Out of scope (YAGNI):**
- **No template payload.** Generated projects do not get a `PLAN.md` scaffold.
  Propagating PI (and MEMORY) into rendered projects is recorded as a new
  forward plan (below), not executed here.
- **No MEMORY work** — that is Plan 26 (Committed Memory adoption), next.
- **No history reconstruction** — we archive the meta-plan wholesale and start
  the log fresh; git already holds the true history.
- **No template-payload propagation, no per-project dogfood** in this plan.

## New forward plan recorded by this work

A new `Next` item is added to `PLAN.md` (and noted on the frozen meta-plan):

> **Propagate the PI + MEMORY conventions into generated projects (template
> payload).** A builder-facing dogfood of both conventions, scaffolded into
> rendered projects (the 22b-style sibling to the framework-only Plans 25/26).
> Deferred; recorded so it is not lost.

## Design

### Decisions (from the approved brainstorm)

1. **History strategy — archive-wholesale + fresh log.** Move the dated
   meta-plan's forward sequence into `PLAN.md`; seed `ACTION_LOG.md` fresh
   (`#0001 · note · adopted PI`). No back-dated reconstruction of historical log
   entries — pre-adoption history lives in git + the archived meta-plan.
2. **Task IDs — fresh monotonic `T`-IDs for open work only; preserve "Plan N"
   in titles.** Open items get clean new IDs (e.g. `T1 — Plan 22c: …`). The
   legacy "Plan N" label stays in the title for continuity and grep. Completed
   plans get no `T`-IDs — they are archived history. New post-adoption work
   continues the monotonic sequence.
3. **Commit-gate hook — re-target, lenient.** Block `git commit` unless
   `PLAN.md` **or** `ACTION_LOG.md` is staged (was: CLAUDE.md).
4. **Meta-plan file — freeze in place + point to it.** Leave
   `docs/superpowers/plans/2026-05-20-meta-plan.md` physically where it is, stop
   updating it, add a header tombstone. `_archive/ARCHIVED_PLAN.md` is a thin
   pointer to it (no 177-line copy — honors PI "relocation, not duplication").
   Every existing reference to the dated filename stays valid.
5. **Verification — agent-upheld only.** No PI structural validator test (the
   convention is deliberately agent-upheld, "no validator does it for you").

### The four artifacts (framework repo root)

| File | Seeded content | Read temperature |
|---|---|---|
| `PLAN.md` | **Next:** open work as fresh `T`-IDs — Plan 22c, 23, 25, 26, 27, 29, 30, the Traefik-acceptance follow-up, **+ the new PI/MEMORY-into-templates plan** — each with legacy "Plan N" in the title, `deps:`, and a relative link out to its spec/plan doc. **Done:** recently-merged plans (24, 28) + Plan 25 on completion. | hot |
| `ACTION_LOG.md` | Fresh: `#0001 · note · 2026-06-12` "adopted PI convention." Append-only thereafter. | warm |
| `_archive/ARCHIVED_PLAN.md` | Thin pointer to the frozen `docs/superpowers/plans/2026-05-20-meta-plan.md`. | cold |
| `_archive/ARCHIVED_ACTION_LOG.md` | Header-only stub. | cold |

`PLAN.md` `Next` entries may link *out* to their spec/plan docs for detail
(PI rule 7 — context, not evidence). All per-plan docs under
`docs/superpowers/` stay put as referenced planning-process artifacts.

### CLAUDE.md slimming

CLAUDE.md **keeps** the durable Working Agreement: the intro, "How we build
here," the review-model policy, the quality gate, and the critical conventions.
It **sheds**:
- The "Current State" essay → `PLAN.md`.
- The "Keeping state current (required before every commit)" section is reworded
  to point at `PLAN.md`/`ACTION_LOG.md` instead of CLAUDE.md/meta-plan.

It **gains** the PI pointer block (the `<!-- PI-convention: v1 -->` marker +
"Read `PLAN.md` first" block from the convention). The "Source of truth" pointer
gains `PLAN.md` as the primary live-state reference; the design-spec pointer
stays. Net effect: CLAUDE.md becomes a stable working-agreement doc rather than a
running narrative.

### Commit-gate hook

In `.claude/settings.json`, the `PreToolUse` gate that blocks `git commit`
re-targets from "CLAUDE.md staged" to "`PLAN.md` **or** `ACTION_LOG.md` staged."
Its block message updates to name the new files. If a test asserts the old
behavior, it is re-pointed (see Verification).

### Self-registration (cross-repo)

Append one row to `_docs/planning-instrument/implementers.md` in the **patterns
repo** (a separate git repo):

```
swiftwater-framework | ~/Claude Code/Projects/framework/swiftwater-framework | v1 | 2026-06-12
```

This is a small, isolated commit in the patterns repo, called out explicitly.
Optionally tick `T4` in the patterns `PLAN.md` to close their loop.

## Verification

PI is agent-upheld, so there is no rich test surface. We verify:

1. **Hook change works.** If an existing test asserts the gate blocks a commit
   without CLAUDE.md staged, re-point it to `PLAN.md`/`ACTION_LOG.md`; otherwise
   a manual confirm that the lenient gate fires. Check for such a test during
   implementation.
2. **No stale references break.** Grep the suite and docs for assertions on the
   old CLAUDE.md "Current State" structure; the full gate
   (`uv run pytest -q`, `ruff check`, `ruff format --check`, `mypy src`) stays
   green.
3. **PI invariants hold at adoption (manual):** IDs unique + monotonic, each
   task in PLAN xor archive, log IDs contiguous, every `deps:`/`log:#`/link
   resolves, event types in the closed taxonomy.

## Risks & notes

- **The meta-plan is "record of record" today.** Freezing it (decision 4) with a
  tombstone preserves it intact; nothing is lost and references stay valid.
- **Cross-repo commit.** Self-registration writes to the patterns repo — a
  separate, deliberate commit, not bundled with framework changes.
- **Hook regression.** The gate is enforcement we rely on across machine-hops;
  the re-target must be verified to actually fire, not silently no-op.
```

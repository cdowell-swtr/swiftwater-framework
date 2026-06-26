<!-- vendored from cdowell-swtr/patterns pi-convention-v3.md @ feb84ec0082b7ea48ce2657881942779244b1c04 (tag pi/v3) on 2026-06-25; re-vendor when a later pi/v tag supersedes -->

<!-- PI-convention: v3 -->
# Planning Instrument (PI) — Convention

*Authoritative definition. Version: `PI-convention: v3`. Portable — depends on nothing but git + markdown. **v2** changed the task-ID scheme from a fixed `T` to a per-repo prefix. **v3** (a) forbids a free-text resume/status pointer in `PLAN.md` — it can't be ID-keyed, append-only, or single-writer-safe, so it drifts and breaks under federation (rule 8); and (b) registers adopters by **GitHub slug `<owner>/<repo>`**, not a machine-local path. v1→v2 and v2→v3 migrations are **advisory** — see the adoption runbook's migration section.*

## Purpose
Give a repo a durable, self-governing record of *what was done and what's next*, tuned for coding agents but useful to humans. **Bound the always-loaded context**: keep "what's next / what we did / why" out of the always-loaded agent file, leaving only a lean pointer. PI records the **pragmatic execution trail** — not strategic decision rationale (that belongs in a separate decision store, if one exists).

## The four artifacts
| File | Holds | Read temperature |
|---|---|---|
| `PLAN.md` (root) | Current state only: `Next` (ordered, with deps) + recent `Done`. **No resume/status pointer** (rule 8). | hot — every session, first |
| `ACTION_LOG.md` (root) | Append-only event narrative: completions + deviations + operational reasons | warm — on demand |
| `_archive/ARCHIVED_PLAN.md` | Full preserved content of items that left the plan | cold |
| `_archive/ARCHIVED_ACTION_LOG.md` | Overflow for old log sections (stub until needed) | cold |

## Core rules
1. **Monotonic, never-reused task IDs `<PFX>1, <PFX>2, …`** — the join key across every file. `<PFX>` is the repo's short uppercase tag, chosen once and recorded in the implementer registry (this repo: `PAT`). The prefix disambiguates task IDs across a multi-repo PI deployment — a bare `T5` is ambiguous when several repos run PI; `PAT5` / `MRDN5` is not. Log entries keep their own monotonic IDs (`#0001, …`) — a separate, **unprefixed** namespace.
2. **PLAN = current state only.** No history, no reasons. As `Done` grows, older items roll off to the archive (keep recent `Done` + all `Next`).
3. **LOG = append-only, task grain.** Record every completion and every plan change with a one-line **operational** reason. Not every commit or micro-step — git already has those. Signal, not volume.
4. **Relocation, not duplication.** An item's full content lives in exactly one of PLAN *or* ARCHIVE. When superseded/discarded, its full definition *moves* to the archive; the reason lives once — in the LOG, referenced by ID.
5. **Closed event taxonomy:** `completed · inserted · reordered · dep-found · amended · superseded · discarded · milestone · note`.
6. **PLAN holds the plan, not the process that produced it.** Planning-process outputs (brainstorms, specs, design docs) stay separate documents the tasks *reference*; never mirror their in-transit state into PLAN. When a process concludes, its full task breakdown enters PLAN (every concluded task, not a hand-picked subset), re-keyed to PLAN's own IDs.
7. **PLAN may point *out* for context, never for evidence.** A task may carry a relative link to its source (spec/brainstorm/design doc) for context and detail — that does not make PLAN an epistemic store.
8. **No mutable resume/status pointer in PLAN (anti-pattern).** Do not add a free-text "resume" / "you-are-here" / "status" line to `PLAN.md`. Orientation at session start is `Next` (ordered, with deps) + recent `Done` + the `ACTION_LOG` tail; under the **Federation convention**, the live locus across parallel instances is the claim-ref snapshot (`git ls-remote origin 'refs/federation/claims/*'`). A free-text pointer is the one shape in PI with **no task ID, not append-only, and not single-writer-safe** — so it drifts (goes stale) and collides under parallel writers, and in practice accretes into narrative (the observed failure: a `RESUME HERE` line that grew into a multi-paragraph status blob, duplicating LOG content in PLAN). "Where we are" is the LOG tail; "what's next" is `Next`; "what's active across instances" is the claim refs. Nothing belongs on a mutable singleton line.

## File formats (plain, parseable markdown)
```
PLAN — Next:   - [ ] <PFX>42 — <title>  deps: <PFX>40, <PFX>41
PLAN — Done:   - [x] <PFX>41 — <title>  → log:#0007

LOG (append at bottom):
  #### #0008 · superseded · <PFX>39→<PFX>44 · <date>
  <terse what + operational why>
  commit: <sha>

ARCHIVE (full content preserved, never truncated):
  ### <PFX>39 — <title> · superseded-by <PFX>44 · log:#0008
  deps: … / <full original task definition>
```

## Operating model
Read `PLAN.md` at session start. As you work: tick tasks and append a LOG entry on every completion and **every deviation**, with a one-line operational reason. The instrument is the cross-session source of truth that survives context compaction — distinct from any ephemeral in-session todo list.

## Invariants you must uphold (no validator does it for you)
Before finishing any session that touched the instrument, confirm:
- Task IDs unique + monotonic; never reused; all share the repo's `<PFX>`.
- Each task in **exactly one** of PLAN xor ARCHIVE.
- Log IDs unique + contiguous.
- Referential integrity: every `deps:`, `superseded-by`, `log:#` resolves to a real ID.
- Every event `type` is in the closed taxonomy.
- LOG is append-only — never edit or truncate existing entries.
- **PLAN carries no resume/status pointer** (rule 8) — orientation is `Next` + recent `Done` + the LOG tail (+ claim refs under federation).

## Adopt PI in a repo (from zero)
1. **Choose your prefix** — a short uppercase tag (e.g. `PAT`, `FWK`, `MRDN`) — and record it in the implementer registry. Every task ID in this repo is `<PFX>N`.
2. Create `PLAN.md` + `ACTION_LOG.md` at the repo root, and `_archive/ARCHIVED_PLAN.md` + `_archive/ARCHIVED_ACTION_LOG.md` — headers only, no items.
3. Add the lean pointer to `AGENTS.md` (block below), including the `PI-convention: v3` marker. **Then make your agent autoload it:** Claude Code autoloads `CLAUDE.md`, *not* `AGENTS.md` — so in a CC repo add `@AGENTS.md` to `CLAUDE.md` (create it if absent). Without this, the pointer never reaches the agent at session start and "read `PLAN.md` first" never fires. (`AGENTS.md` stays canonical for portability; `CLAUDE.md` just imports it.)
4. Seed item zero: log `#0001 · note · <date>` "adopted PI convention"; put the next real task (`<PFX>1`) in `PLAN.md` `Next`.
5. **Register yourself** — append a row to `_docs/planning-instrument/implementers.md` in the PI home repo (`patterns`): `<owner>/<repo> | v3 | <PFX> | <date>` — the **GitHub slug** (e.g. `cdowell-swtr/your-repo`), the portable identity, **not** a machine-local path.

To find the registry, every adopter, or check synced versions — the `PI-convention:` marker is in the convention doc and in every adopter's `AGENTS.md`:
```
grep -rIn "PI-convention:" <your projects root>
```

Migrating an existing v1 (`T`-prefixed) or v2 instrument → see the adoption runbook's **advisory migration** section.

### AGENTS.md pointer (copy this block)
```
<!-- PI-convention: v3 -->
## Planning Instrument
Read `PLAN.md` first. Maintain `PLAN.md` + `ACTION_LOG.md` at task grain as you work
(tick tasks; append a log entry on every completion and every deviation), per `pi-convention.md`.
Task IDs use this repo's prefix (see the implementer registry).
```

# Reviewer Decisions Log — Design Spec

**Date:** 2026-06-01
**Status:** Approved (brainstorm) — not yet planned/implemented
**Scope:** framework repo only (dogfood first); generated-project / dual-target deferred.
**Related:** the context-aware review spine (Plan 11 — `ContextPolicy`/`Bundle`/`assemble`/`run_agent`), the gate (`/reviewers:gate`, `_finalize_gate`), [[flags-is-dual-use-gate-skips-advisory]]. Motivating episode: the v0.1.0 release-fix, where the pre-commit gate re-litigated already-merged DLQ-PII design (the by-design internal commit; the deliberate opt-in redaction seam) because the diff touched those files.

---

## 1. Purpose

Give the review agents a machine-consumable record of **design decisions already made and consciously accepted**, so they don't re-raise known-and-decided concerns on every edit that touches the surrounding code — while keeping enough autonomy that a reviewer can declare a decision **stale** when the code diverges from what the decision assumed.

The reviewers are diff/bundle-scoped and stateless across runs, so any edit touching sensitive code re-surfaces the same decided concerns (and the panel's severity is nondeterministic). The framework already records decisions in prose (spec, CLAUDE.md, meta-plan, memories) — the gap is that the reviewers can't *see* them. This closes that gap for the framework's own review surfaces.

## 2. Scope & non-goals

**In scope (v1):** the framework repo's own reviewers — `/reviewers:gate`, `/reviewers:audit`, and `framework review --target framework`.

**Non-goals (deliberate, deferred):**
- **Generated projects / `--target project` / dual-target.** The loader simply finds no decisions directory in a generated project, so project reviews are unchanged — a clean seam for a future "ship the convention to builders" follow-up.
- **Eval/tune scoring.** `framework eval` / `/reviewers:tune` must NOT see decisions (§5).
- **Inline code markers** and **fingerprint/baseline suppression** — rejected approaches (can't express the premise / judge staleness; defeated by reviewer nondeterminism).
- **Same-commit guard / meta-reviewer on decisions** — considered, not adopted for v1; trust is plain-files + human review of the decisions diff.

## 3. Decision record: format & location

One markdown file with YAML frontmatter per decision, under **`docs/superpowers/decisions/`** (consistent with the repo's `docs/superpowers/{specs,plans}` convention; git-native, reviewable as a plain diff).

```markdown
---
id: DEC-0001
status: accepted            # active (honored): accepted | deferred. inactive (not honored): retired | invalidated | superseded | void | …
agents: [data-integrity]    # which reviewer(s) this speaks to (scopes injection)
concern: "prune_expired commits its own session internally"
premise: >                  # the revisit-if: what must remain true for this to hold.
  The only caller is the prune_expired_records beat task, which scopes a dedicated
  session. If a caller invokes prune_expired inside an outer transaction, STALE.
date: 2026-06-01
---

Rationale (free prose): why this is accepted, links to the spec/commit/follow-up.
```

Rules:
- **`premise` is required.** A decision without a non-empty premise is rejected at load (it's the explicit revisit-if the reviewer checks for staleness; no premise → can't judge staleness).
- **`agents`** scopes which reviewers receive the decision, keeping per-agent context lean.
- **Status is active-allowlist, fail-closed.** The code recognizes exactly two **active** (honored) statuses — **`accepted`** (by-design; stands until something changes) and **`deferred`** (acknowledged debt; honored now but explicitly tracked for revisit — its rationale SHOULD link the tracking follow-up). **Any other value is inactive → not honored** (matching findings block normally). The loader checks membership in the active set and treats everything else — including future reasons *and* typos — as inactive. We deliberately do **not** enumerate the inactive reasons in code; the recommended (non-exhaustive) vocabulary, for human/audit clarity only, splits along *why* the decision stopped standing:
  - **Context-driven** (reasons *outside the code itself* — changed NFRs, a new understanding of failure modes, shifted priorities): `retired` (no longer stands, no replacement) and `superseded` (no longer stands, but a newer decision now covers the same code — optionally add `superseded_by: DEC-XXXX`). These two are causally similar; they differ only in whether a replacement exists.
  - **Code-grounded** (the artifact changed): `invalidated` (the code moved out from under the `premise`, so it no longer holds) and `void` (the referenced code no longer exists).

  New reasons can be added freely without code changes — the active allowlist is the only thing the code keys on.
- **Inactive decisions are tombstoned, not deleted** — they stay in the repo so the history of what was decided (and why it stopped standing) remains auditable.

## 4. Context injection & reviewer protocol

- A loader `relevant_decisions(agent, root)` reads `docs/superpowers/decisions/`, keeps **active** (`accepted`/`deferred`) entries whose `agents` includes the agent, and attaches them to the assembled context via a new field **`Bundle.decisions`** (populated in `assemble`).
- `run_agent` / `run_agent_agentic` render the decisions as **one extra system block**, in the per-agent cache region. Block order: `diff` (shared cache prefix across agents) → `context_files` → **`decisions`** → `prompt`.
- The decisions block carries the records **and** a standing **protocol preamble**:

  > For each finding, consult the Active Decisions. If it matches a decision's `concern` **and** the `premise` still holds given the code → emit the finding with `acknowledged: <id>`. If it matches but the premise no longer holds → emit a normal finding with `stale: <id>`, naming which premise clause broke. Otherwise → a normal finding.

  The reviewer only *flags* staleness (the `stale` signal); a human then sets the decision's terminal status (`invalidated` / `superseded` / `retired` / `void`) or fixes the code — the reviewer never edits the record.

- **Inert until used:** when an agent has no relevant active decisions, **no block is injected** and its context + prompt are **byte-identical to today**. The feature ships dormant; it changes behavior only where a decision exists. This avoids editing any of the 18 agent prompts and protects the calibrated agents until a decision is authored.

## 5. Findings schema & verdict integration

The finding schema gains two optional fields: **`acknowledged: <id>`** and **`stale: <id>`** (`stale` names a matched decision whose premise the reviewer judges broken — distinct from the `superseded` *status* a human sets when a newer decision replaces an old one).

Verdict logic (`_finalize_gate` and the audit verdict path):
- A finding with **`acknowledged`** → **non-blocking** regardless of severity. Filtered out *before* the `block_threshold` computation, but **kept in the report** under an "Acknowledged (covered by decisions)" section — visible, never silent.
- A finding with **`stale`** (or untagged) → treated normally; blocks per the agent's `block_threshold`. Rendered as a normal blocker flagged "flags DEC-XXXX stale — premise broke," prompting a human to set the decision's terminal status or fix the code.

**Integrity guard:** an `acknowledged` tag is honored **only if** its id resolves to a loaded **active** (`accepted`/`deferred`) decision. A tag citing an unknown or inactive (`retired`/`invalidated`/`superseded`/`void`/…) id is **ignored** — the finding blocks normally. This prevents waving a finding through with an invented or no-longer-standing id and complements the plain-files-human-reviewed trust model.

Acknowledged findings stay in the report (full visibility) — over-suppression cannot hide.

## 6. Consumers & eval exclusion

**Consumers (v1):** `/reviewers:gate` (primary — the v0.1.0 pain), `/reviewers:audit`, `framework review --target framework`. All load decisions from `docs/superpowers/decisions/`.

**Eval/tune excluded:** the eval/tune assembly path **never loads decisions**. They describe real repo code, not synthetic fixtures; injecting them would corrupt recall/precision (an agent could `acknowledge` a fixture's injected defect on a spurious match) and let a decision quietly lower a measured score. Scorecards keep measuring raw agent behavior, and authoring a decision can't game calibration.

## 7. Testing

Hermetic (fake client; real decision files in a tmp dir):
- `relevant_decisions` filters by `agents` + **active status**: `accepted` and `deferred` are honored; `retired`/`invalidated`/`superseded`/`void` **and an unrecognized status string** are all excluded (fail-closed). A decision missing `premise` is rejected at load.
- Injection: a relevant decision adds the block; **zero relevant active decisions → byte-identical context** (regression guard for "inert until used").
- Verdict: `acknowledged` + valid active id → non-blocking; `acknowledged` + unknown/inactive id → blocks normally (integrity guard); `stale`/untagged → blocks.
- Report: acknowledged findings appear in their own section, not in the blocking set.

## 8. Seed decisions

Author the first real records from the v0.1.0 episode, proving the mechanism on the exact cases that motivated it:
- **DEC-0001 (data-integrity):** `prune_expired` internal commit is by-design. *Premise: the only caller is the `prune_expired_records` beat task with a dedicated session.*
- **DEC-0002 (compliance), `status: deferred`:** the DLQ `args_json` opt-in-redaction default is intentional **pending** the DLQ-PII compliance-posture follow-up — `deferred` (not `accepted`) marks it as tracked debt, machine-visibly. *Premise: the `BaseTask.dlq_args_json` override seam exists; the follow-up tracks the default-redact question.*

## 9. Self-review

- **No placeholders.** All sections concrete.
- **Consistency:** the inert-until-used property (§4) and eval-exclusion (§6) jointly guarantee zero change to existing scorecards/calibration until a decision is authored.
- **Scope:** single implementation plan (loader + Bundle field + render block + schema fields + verdict filter + seed decisions + tests). Framework-only keeps it bounded.
- **Ambiguity:** "match" is intentionally LLM-judged (§3/§4) — the integrity guard (§5) and acknowledge-don't-silence bound the downside of a mis-match.
- **Status taxonomy:** the code keys only on an active allowlist (`accepted`/`deferred`); every other value — the open, non-exhaustive "no longer stands" family (`retired`/`invalidated`/`superseded`/`void`/…) and any typo — is inactive, fail-closed. New reasons need no code change. The reviewer's `stale` finding-signal is kept distinct from the human-set `superseded` status to avoid conflation.

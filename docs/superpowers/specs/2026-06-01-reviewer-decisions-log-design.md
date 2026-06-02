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
status: accepted            # accepted | retired
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
- **`status: retired`** tombstones a decision without deleting history (superseded decisions stay auditable; retired decisions are not honored).
- "Deferred-pending-followup" decisions use `status: accepted` and say so in the rationale prose (no separate status for v1).

## 4. Context injection & reviewer protocol

- A loader `relevant_decisions(agent, root)` reads `docs/superpowers/decisions/`, keeps `accepted` entries whose `agents` includes the agent, and attaches them to the assembled context via a new field **`Bundle.decisions`** (populated in `assemble`).
- `run_agent` / `run_agent_agentic` render the decisions as **one extra system block**, in the per-agent cache region. Block order: `diff` (shared cache prefix across agents) → `context_files` → **`decisions`** → `prompt`.
- The decisions block carries the records **and** a standing **protocol preamble**:

  > For each finding, consult the Accepted Decisions. If it matches a decision's `concern` **and** the `premise` still holds given the code → emit the finding with `acknowledged: <id>`. If it matches but the premise no longer holds → emit a normal finding with `supersedes: <id>`, naming which premise clause broke. Otherwise → a normal finding.

- **Inert until used:** when an agent has no relevant accepted decisions, **no block is injected** and its context + prompt are **byte-identical to today**. The feature ships dormant; it changes behavior only where a decision exists. This avoids editing any of the 18 agent prompts and protects the calibrated agents until a decision is authored.

## 5. Findings schema & verdict integration

The finding schema gains two optional fields: **`acknowledged: <id>`** and **`supersedes: <id>`**.

Verdict logic (`_finalize_gate` and the audit verdict path):
- A finding with **`acknowledged`** → **non-blocking** regardless of severity. Filtered out *before* the `block_threshold` computation, but **kept in the report** under an "Acknowledged (covered by decisions)" section — visible, never silent.
- A finding with **`supersedes`** (or untagged) → treated normally; blocks per the agent's `block_threshold`. Rendered as a normal blocker flagged "supersedes DEC-XXXX — premise broke."

**Integrity guard:** an `acknowledged` tag is honored **only if** its id resolves to a loaded, `accepted` decision. A tag citing an unknown or `retired` id is **ignored** — the finding blocks normally. This prevents waving a finding through with an invented/stale id and complements the plain-files-human-reviewed trust model.

Acknowledged findings stay in the report (full visibility) — over-suppression cannot hide.

## 6. Consumers & eval exclusion

**Consumers (v1):** `/reviewers:gate` (primary — the v0.1.0 pain), `/reviewers:audit`, `framework review --target framework`. All load decisions from `docs/superpowers/decisions/`.

**Eval/tune excluded:** the eval/tune assembly path **never loads decisions**. They describe real repo code, not synthetic fixtures; injecting them would corrupt recall/precision (an agent could `acknowledge` a fixture's injected defect on a spurious match) and let a decision quietly lower a measured score. Scorecards keep measuring raw agent behavior, and authoring a decision can't game calibration.

## 7. Testing

Hermetic (fake client; real decision files in a tmp dir):
- `relevant_decisions` filters by `agents` + `status` (accepted only; retired excluded); a decision missing `premise` is rejected at load.
- Injection: a relevant decision adds the block; **zero relevant decisions → byte-identical context** (regression guard for "inert until used").
- Verdict: `acknowledged` + valid accepted id → non-blocking; `acknowledged` + unknown/retired id → blocks normally (integrity guard); `supersedes`/untagged → blocks.
- Report: acknowledged findings appear in their own section, not in the blocking set.

## 8. Seed decisions

Author the first real records from the v0.1.0 episode, proving the mechanism on the exact cases that motivated it:
- **DEC-0001 (data-integrity):** `prune_expired` internal commit is by-design. *Premise: the only caller is the `prune_expired_records` beat task with a dedicated session.*
- **DEC-0002 (compliance):** the DLQ `args_json` opt-in-redaction default is intentional **pending** the DLQ-PII compliance-posture follow-up. *Premise: the `BaseTask.dlq_args_json` override seam exists; the follow-up tracks the default-redact question.*

## 9. Self-review

- **No placeholders.** All sections concrete.
- **Consistency:** the inert-until-used property (§4) and eval-exclusion (§6) jointly guarantee zero change to existing scorecards/calibration until a decision is authored.
- **Scope:** single implementation plan (loader + Bundle field + render block + schema fields + verdict filter + seed decisions + tests). Framework-only keeps it bounded.
- **Ambiguity:** "match" is intentionally LLM-judged (§3/§4) — the integrity guard (§5) and acknowledge-don't-silence bound the downside of a mis-match.

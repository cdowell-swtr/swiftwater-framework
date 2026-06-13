---
name: subagent-review-model-pattern
description: "In subagent-driven development here, dispatch reviewers by role-specific model: spec-compliance reviewer = Sonnet, code-quality reviewer = Opus, implementers = Sonnet (Haiku for trivial). Not the skill's blanket 'least powerful' / 'reviews = most capable'."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c9002363-27bb-4f03-b690-5224c0833806
---

This is the long-standing **"review-model policy"** (stated e.g. in
`docs/superpowers/plans/2026-05-21-database-lifecycle.md`: *"Sonnet implementer + first/spec
check, Opus for the subjective code-quality review and the final review"*). When executing
plans via **superpowers:subagent-driven-development** (or otherwise dispatching review), set the
subagent model **per role**:

- **Spec-compliance reviewer → Sonnet.** Mechanical: read the code, compare to the spec, flag
  missing/extra/misread requirements. Sonnet is sufficient.
- **Code-quality reviewer → Opus.** The deep-judgment stage — subtle correctness bugs, design
  smells, test adequacy, false-confidence in a passing test. Use the most capable model; this is
  NOT where to economize. (In Plan 20a, Opus code-quality reviews caught a `json.loads`
  prose-intolerance bug and a duplicate-instruction-string drift a passing parity test + a Sonnet
  review missed.)
- **Final / branch-end whole-branch review → Opus** (see [[gate-cadence-framework-slices]]).
- **Implementers → Sonnet** (Haiku for trivial verbatim-from-plan tasks).

**Why:** the spec/quality stages have different cognitive loads; matching model to load gets the
rigor where it matters (quality) without overpaying where it doesn't (spec). This is the
established pattern from prior sessions.

**How to apply:** in each `Agent`/dispatch call, pass `model` explicitly per role above, AND
restate the policy in every new plan's "Execution" section. The drift (Plan 20a) happened because
the policy had only ever been persisted *in per-plan execution sections* (durable across ~20
sessions because each plan restated it) — never in a memory or CLAUDE.md. When the freshly-written
20a/20b plans used the writing-plans skill's generic execution boilerplate and omitted the policy,
nothing recalled it and the skill's generic guidance ("least powerful model" / "reviews → most
capable") filled the vacuum, collapsing both reviewers to Sonnet. Now it lives here (always
recalled) + CLAUDE.md "How we build here". Also: a passing test (even a parity/contract test the
implementer wrote) is **not** a substitute for the code-quality review — it's a deliverable being
reviewed. Related: [[gate-cadence-framework-slices]].

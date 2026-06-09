# Reviewer path parity — design (Plan 20)

**Date:** 2026-06-09
**Status:** ✅ Design approved (brainstorm) — ready for `writing-plans`. Supersedes the
pre-brainstorm stub `docs/superpowers/plans/2026-06-09-reviewer-path-parity-refactor.md`.
**Spike:** transport verified — see "Spike results" below.

## Problem

The review system has **two separate code paths** that are supposed to be equivalent
but are not. The paid path is what builders actually run; the free path is a dev-time
cost cheat — and the free path is *more robust than production*, so it **hides the bugs
builders hit**.

- **Paid path** (`framework review` / `framework eval`): pure Python →
  `run_agent` / `run_agent_agentic` (`review/runner.py`, `review/agentic.py`) → real
  Anthropic client → **raw model text** → `parse_findings`. Agentic agents explore via
  Python `read_file`/`grep`/`glob` (root-confined) in a Python turn loop with `max_turns`.
- **Free path** (`/reviewers:{audit,gate,tune}`): `audit-prepare` re-assembles the prompt
  in `cli.py::_build_work_item` (duplicate of the runner assembly) → split-manifest →
  Workflow JS `agent()` → CC subagents, wrapped in a **meta-prompt** ("act as this
  reviewer, read this JSON, concatenate blocks…"), forced into a **StructuredOutput
  schema** (always well-formed JSON). Agentic agents explore via the subagent's **own**
  Read/Grep/Glob, and the **subagent owns its loop**.

### Five concrete divergences

| Axis | Paid | Free |
|---|---|---|
| Dispatch | pure Python → Anthropic SDK | `audit-prepare` → Workflow JS → CC subagents |
| System-block assembly | `runner.py`/`agentic.py` (inline) | re-built in `cli.py::_build_work_item` (dup) |
| Prompt framing | reviewer prompt **is** the system prompt | reviewer prompt **wrapped** in a meta-prompt |
| Output | raw text → `parse_findings` | **forced** schema (always well-formed) |
| Agentic tools + loop | Python tools, Python-owned loop, `max_turns` | CC's own tools, subagent-owned loop |

### Evidence (Plan 18 paid anchor, 2026-06-09)

- The forced-JSON guard **masked real paid-path crashes**: trailing prose after the array
  (`0527d07`) and a code snippet in the `line` field (`bdfb647`). The free path can never
  produce these, so a week of free-path calibration never exercised them.
- Rate-limit reality exists only on the paid path → backoff work (`88eb3cd`).
- **8/20 agents failed** their free-calibrated thresholds on the full paid run
  (`27222994607`) — dominated by good-fixture over-flagging the free path reported as clean.

See `[[paid-path-operative-for-builders]]`, `[[reviewer-dev-prod-parity-gap]]`,
`[[reviewer-tuning-is-prompts-not-thresholds]]`.

## Goal & non-goals

**Goal:** one review code path; the only swappable piece is the model-call backend.
Dev (free) predicts prod (paid) **by construction**, so every robustness/prompt fix lands
once. This unblocks Plan 21 (prompt + threshold tuning), which must be done against a path
that matches production.

**Non-goals:** prompt content changes, threshold re-derivation, fixture-quality fixes —
all Plan 21. This plan changes *architecture*, not calibration. The agent prompts under
`review/agents/*.md`, `thresholds.yaml`, and fixtures are touched only as needed to keep
the refactor green; their re-tuning is explicitly deferred.

## Architecture

A three-stage pipeline. **Prep and synthesis are dispatch-agnostic; only dispatch swaps,
and even it is constrained to produce indistinguishable artifacts.**

```
PREP  (shared; gate/audit/tune differ ONLY in what they select to review)
  build_review_request(bundle, spec) → ReviewRequest
        { model, system_blocks, user_message, tools_allowed, root_dir }
        └─ replaces cli.py::_build_work_item; one assembler, both backends

DISPATCH  (swappable backend behind ONE messages.create-shaped seam)
  • ApiBackend       → anthropic.Anthropic()                  [paid: local + CI]
  • SubagentBackend  → claude -p (subscription/free)          [free: local dev]
  run_agent / run_agent_agentic — the SAME Python loop drives both:
    owns max_turns, runs tools via the SAME _run_tool, force-finalizes,
    feeds raw text to the SAME parse_findings.

SYNTHESIS  (shared)
  parse_findings(raw_text) → aggregate → finalize / scorecard / gate decision
```

### Component 1 — Shared prep (`build_review_request`)

A single function builds the canonical per-item request from a `Bundle` + `AgentSpec`,
used by **all** of gate/audit/tune/eval and by **both** backends. It subsumes the system-
block assembly currently duplicated between `runner.py`/`agentic.py` (inline) and
`cli.py::_build_work_item`. gate/audit/tune become thin front-ends that differ only in
*selection* (affected-only diff / current-state snapshot / fixtures).

### Component 2 — Backend seam

A minimal `messages.create`-shaped interface both backends implement:

```python
class Backend(Protocol):
    def create(self, *, model, max_tokens, system, messages, tools=None) -> Response: ...
```

- **`ApiBackend`** — wraps `anthropic.Anthropic()` (today's code, including the
  `_max_retries()` backoff from `88eb3cd`). Returns the SDK response unchanged.
- **`SubagentBackend`** — shells out to `claude -p` and adapts its JSON output into the
  same `Response` shape (`.content` text block(s), `.usage`, `.stop_reason`). **Required
  flags** (these are what make parity real, not optional):
  - `--system-prompt <assembled system>` — the reviewer prompt + diff/context occupy the
    **system** channel exactly as the API receives them (closes the channel gap entirely).
  - `--exclude-dynamic-system-prompt-sections` — strips the harness preamble.
  - `--disallowed-tools …` (all of Bash/Read/Edit/Write/Grep/Glob/WebFetch/WebSearch/Task)
    — guarantees a **single** model turn (no internal agentic loop). Python owns the loop.
  - `--output-format json` — yields `usage`/`stop_reason`/`num_turns` for a faithful
    `report{}`.
  - `--model <spec.model>`.
  The `Response` adapter strips a leading ```json fence if present (CC may fence output);
  the contract test asserts `parse_findings` handles fenced and unfenced identically.

### Component 3 — The unified loop (single-turn oracle + text tool protocol)

`run_agent` (bundle tier) and `run_agent_agentic` (agentic tier) are unchanged in shape
and run for **both** backends. The agentic loop stays Python-owned: it calls
`backend.create(...)` per turn, parses the response, runs tools via the existing
`_run_tool`, enforces `max_turns`, and force-finalizes.

Because `SubagentBackend` produces a single turn and cannot emit native `tool_use` blocks,
agentic free turns use a **one-line text tool protocol** that the Python loop parses:

- A tool turn: the model responds with ONLY `{"tool_calls":[{"name":…,"input":{…}}, …]}`
  (a JSON **object**). Python runs each via the same `_run_tool` and feeds results back.
- A final turn: the model responds with ONLY the findings JSON **array** `[…]` — raw,
  possibly malformed (intended), straight into `parse_findings`.
- Disambiguation is structural (object = tools, array = final), mirroring the API's
  `tool_use`-vs-`text` distinction. Unparseable-as-tools and not-valid-findings → treated
  as final raw text → `parse_findings` hardening / recorded parse failure.

The per-turn protocol instruction lives where `_INITIAL_INSTRUCTION`/`_FINALIZE_INSTRUCTION`
already live. The **only** paid-vs-free delta inside the loop is native `tool_use` blocks
(paid) vs. this text protocol (free); loop control, tools, finalization, and parsing are
byte-identical.

### Component 4 — Shared synthesis

Both backends write the same on-disk record (`raw_text` + `usage`/`turns`/`tool_calls`/
`stop_reason`). One synthesis stage (`parse_findings` → aggregate → finalize / scorecard /
gate decision) consumes it, identical for both. The paid path already writes a results
file; this standardizes the record so finalize is dispatch-agnostic.

### Component 5 — Backend resolution & cost-safety policy

The review system **ships in the rendered template**; builders run it in their own repos,
mostly *not* through Claude Code, often right after `framework new` before any keys exist.
The backend must degrade across what they actually have, and must **never spend money or
burn quota the builder did not intend**.

**Resolution** (`resolve_backend(intent, env, context)`):

1. **Intent** = `--backend` flag > `FRAMEWORK_REVIEW_BACKEND` env > repo config
   `.framework/review.toml` (`backend = "api" | "subagent"`).
2. Invariants:
   - **R1 — no spend without intent.** Mere presence of a key or of `claude` is **not**
     consent. No intent → no backend resolves.
   - **R2 — chosen-but-unavailable = clear skip/error, never silent fallback.** `api`
     chosen with no key → say so; do **not** use an available `claude`. `subagent` chosen
     with no authed `claude` → say so; do **not** spend a key. Cross-backend fallback is
     itself an unexpected-cost event — forbidden.
   - **R3 — opt-in is informed.** `framework new` asks once — *"Enable AI code review?
     [API key (paid per use) / Claude subscription (free within limits; may use overage) /
     not now]"* — and records the choice in repo config, since the gate fires when nobody
     is at the keyboard.
3. **`subagent` cost caveat:** `claude -p` may run in extra-usage/overage mode, which
   drains far faster than subscription limits and is not reliably detectable. The opt-in
   prompt and the first run warn once.
4. **R4 — the choice is mutable post-render.** The `framework new` decision is a default,
   not a lock-in. A `framework review config` surface lets the builder change it at any
   time: `show` (current resolved backend + its source), `set-backend api|subagent` (re-runs
   the **same informed prompt** with cost caveats, so a switch *into* a spending backend is
   informed too, then rewrites `.framework/review.toml`), and `clear` (removes the persisted
   choice → returns the gate to the no-intent **skip-neutral** default — the opt-*out* path
   for bill-shock or CI-only setups). Per-invocation `--backend` / `FRAMEWORK_REVIEW_BACKEND`
   still take precedence over the persisted layer (resolution chain unchanged); this command
   mutates only the persisted layer.

**No-backend-resolved outcome is context-dependent** (the resolution rule above is the
same for all three; only this terminal behavior differs):

- **gate** (the only non-interactive/auto trigger): **skip-neutral, exit 0** — never
  blocks the commit. A freshly-rendered repo commits freely; AI review is advisory until
  opt-in. CI adds `--require-backend` to *fail* instead of skip once a secret is set.
- **audit / tune** (always human-invoked): **actionable error, exit non-zero** — "pass
  `--backend api|subagent` or set `FRAMEWORK_REVIEW_BACKEND`". They never run on a default
  schedule, so skip-neutral (a silent "skipped") would be confusing. They inherit the same
  resolution chain, so an opted-in builder needn't re-specify.

**Builder capability matrix** (default column = no opt-in):

| # | Scenario | Default | Opt-in `subagent` | Opt-in `api` |
|---|----------|---------|-------------------|--------------|
| 1 | inside CC | skip-neutral | nested `claude -p`, free* | needs key (→4/5) |
| 2 | outside CC, `claude` installed | skip-neutral | `claude -p`, free* | needs key |
| 3 | outside CC, no claude, no key | skip-neutral | skip+msg "no claude" | skip+msg "no key" |
| 4 | inside CC, wants `api`, no key | skip-neutral | (n/a) | skip+msg; does NOT use in-CC claude |
| 5 | inside CC, wants `api`, key exists | skip-neutral | — | paid SDK (hint: subagent is free here) |
| 6 | outside CC, no claude, key exists | skip-neutral | skip+msg "no claude" | paid SDK |

\* *free within subscription; warns once that overage mode, if active, consumes faster.*

Inside-vs-outside CC **never** changes the backend — that is the parity guarantee
restated. The paid backend is available in dev too: `framework review --backend api`
runs the real SDK locally for spot-checks and Plan-21's final confirmation pass.

### Component 6 — Interruption, exhaustion & resume (checkpointing)

A multi-item run (audit/tune especially — tune sweeps are large; see
`[[reviewers-tune-quota-throttling]]`) must never lose completed work to a mid-run stop,
and must never hang. This is **backend-agnostic** machinery plus a backend-specific abort
reason.

**Incremental checkpoint.** Dispatch writes each item's result record to disk *the moment
it completes* (Component 4's synthesis already reads written-out records — this just writes
them as they finish, not in a final batch), alongside a `run-state.json` manifest: the full
planned item list, which are done, the run's git SHA + a working-tree dirty-hash, and the
selected backend.

**Abort taxonomy** (distinct from a per-item failure, which is recorded and the run
continues):

- *Transient* — `api` 429 burst → `ApiBackend` backoff (existing). Not an abort.
- *Hard stop — subscription exhausted* (`subagent`): `claude -p --output-format json`
  returns a usage-limit error; the backend detects that specific subtype and raises
  `BackendExhausted(reset_hint)` — **not** a generic failure, so we never sit retrying a
  cap that won't clear for hours. The dispatch loop catches it, **stops scheduling new
  items**, finalizes the checkpoint, reports, and exits without hanging.
- *Hard stop — `api` retries exhausted / sustained outage*: `ApiBackend` raises after
  `_max_retries()`; same checkpoint-and-report handling.

**Reporting** (never a hang):
- *Outside CC:* "Subscription limit reached after N/M items. Progress checkpointed at
  `<path>`. Resume with `framework <cmd> --resume` once your limit resets" + the reset time
  if `claude -p`'s error carries one.
- *Inside CC:* the main CC thread independently surfaces the native exhaustion error and is
  itself blocked until reset, so resume is only useful post-reset. Our run still detects,
  checkpoints, reports, and exits cleanly (no hang); the same `--resume` continues later.

**Resume.** `framework {review,audit,tune} --resume` reads `run-state.json`, runs only
`planned − done`, then finalizes — idempotent. It **validates the recorded SHA/dirty-hash**
against the current tree; on mismatch (code changed since the abort) it warns the checkpoint
is stale and recommends `--fresh` rather than mixing reviews of two code states. A bare
re-run while an incomplete checkpoint exists **warns** and suggests `--resume` (it does not
auto-resume — explicit — nor silently discard progress). The gate, being small and
affected-only, simply goes skip-neutral on exhaustion rather than checkpointing.

## What gets retired

- The Workflow JS scripts `reviewers-{audit,gate,tune}.js` (framework **and** the template
  copies under `template/.claude/workflows/`).
- The slash commands `/reviewers:{audit,gate,tune}`. At most a one-line `/reviewers:audit`
  alias that shells out to `framework audit` verbatim — forbidden from adding behavior;
  the bash command is the single source of truth, identical inside or outside CC.
- The split-manifest apparatus, the meta-prompt wrapper, the forced `FINDINGS_SCHEMA`, and
  `cli.py::_build_work_item` (folded into `build_review_request`).

## Error handling

- The free backend now returns **raw** text, so the Plan-18 parse hardening
  (`0527d07`/`bdfb647`) is exercised in dev, not bypassed. Verify it is not a band-aid the
  new architecture obviates — keep it as the shared backstop.
- A one-off `claude -p` non-zero exit / timeout (or an API error) on a *single* item is
  recorded for that item; the run continues; the gate stays skip-neutral if no item could
  run; audit/tune report the failure.
- A **subscription-exhaustion** error is different — a hard stop handled by Component 6
  (detect → `BackendExhausted` → checkpoint + report + resume), never a retry loop.
- `--max-retries` backoff (`88eb3cd`) lives on `ApiBackend` and absorbs only *transient*
  429 bursts; sustained exhaustion still escalates to the Component-6 hard-stop path.

## Testing / parity proof

- **Hermetic suite:** `uv run pytest` uses the existing stub backend and requires **no**
  live key and **no** `claude` on either tier. Live-backend runs are only the explicit
  `framework {review,audit,tune}` flows and CI.
- **Backend contract test:** run one fixture through both backends and assert the
  `ReviewRequest` each sees is identical — system blocks, user message, tool schema vs.
  text-protocol equivalence, `max_turns`. This is the executable statement of parity.
- **Fence/raw-text test:** `parse_findings` handles fenced and unfenced output identically.
- **Resume / exhaustion test:** a faked `claude -p` usage-limit error mid-run aborts to
  `BackendExhausted`, checkpoints `done` items, and exits non-hanging; `--resume` then runs
  exactly `planned − done` and finalizes an identical result to an uninterrupted run; a
  stale-tree checkpoint warns and recommends `--fresh`.
- **Eval re-run:** the eval scorecards re-run on `--backend subagent` and are spot-confirmed
  against a small `--backend api` run (Plan 21 owns the actual re-derivation).

## CI

CI runs the **same** Python engine with `--backend api` (`ANTHROPIC_FRAMEWORK_CI_RUNTIME`)
— the correct credential and the operative builder experience. No `claude -p` in CI
(subscription OAuth is not a legitimate CI credential). The unification means the local
free run predicts the CI/builder paid run by construction. CI stays skip-neutral without
the secret; `--require-backend` opts a repo into hard-fail.

## Spike results (2026-06-09, verified)

`claude -p` v2.1.157 on PATH. A real headless call with all `ANTHROPIC_*` keys unset:

```
claude -p "<prompt>" --system-prompt "<sys>" --disallowed-tools … \
  --output-format json --model claude-haiku-4-5-20251001
→ {"num_turns":1,"stop_reason":"end_turn","result":"```json\n[…]\n```","usage":{…}}
```

Confirms: (1) **free** — ran on subscription OAuth with no API key in env; the
`total_cost_usd` field is CC's informational estimate, not a paid bill; (2) **single turn**
with tools disabled; (3) `--system-prompt` + `--exclude-dynamic-system-prompt-sections`
give full system-channel control (channel gap closed); (4) `--output-format json` supplies
faithful telemetry; (5) output may be ```json-fenced → adapter strips it.

## Risks & fallback

- **`claude -p` regression / nesting limits.** If a future CC version blocks nested
  headless invocation or changes auth, the fallback is a **Workflow co-process**: keep JS
  as a dumb per-turn transport pump while Python still owns the loop logic via a state
  file. Option B (Python-owned loop) holds either way; only the transport changes. The
  contract test pins the behavior so a transport swap is verifiable.
- **Overage-mode spend on `subagent`.** Mitigated by R1 (explicit intent) + the one-time
  warning; not fully detectable.
- **Per-turn dispatch cost (agentic).** `subagent` agentic reviews issue N sequential
  `claude -p` calls (one per turn). Acceptable for dev iteration; `ApiBackend` is unchanged.

## Decomposition

- **Plan 20 (this):** the parity refactor — unify prep/loop/synthesis, swappable backend,
  retire the Workflow/slash path, ship the cost-safe resolution policy.
- **Plan 21:** prompt + threshold re-tuning + fixture quality, on the now-representative
  path (cheap `subagent` iteration, final `api` confirmation).
</content>
</invoke>

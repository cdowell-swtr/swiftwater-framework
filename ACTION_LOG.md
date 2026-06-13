# ACTION_LOG — swiftwater-framework

> Append-only event narrative, task grain. Never edit or truncate existing
> entries. Closed taxonomy: completed · inserted · reordered · dep-found ·
> amended · superseded · discarded · milestone · note.
> Maintained per `pi-convention.md` (PI-convention: v2).

#### #0001 · note · 2026-06-12
Adopted the Planning Instrument convention (PI-convention: v1). Scaffolded
`PLAN.md` + `ACTION_LOG.md` + `_archive/`; migrated live planning state out of
CLAUDE.md's Current State essay and the dated meta-plan into `PLAN.md` (current
state only) and slimmed CLAUDE.md to the Working Agreement + a PI pointer.
Archive-wholesale + fresh log — no back-dated reconstruction; pre-adoption
history stays in git + the frozen meta-plan. Open work re-keyed to fresh
monotonic T-IDs (T1–T9), with the legacy "Plan N" preserved in each title.

#### #0002 · note · 2026-06-12
Froze the dated meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) in
place with a tombstone header and repointed CLAUDE.md's "Source of truth" at
`PLAN.md`. `_archive/ARCHIVED_PLAN.md` points to the frozen file rather than
copying it (relocation, not duplication).

#### #0003 · amended · 2026-06-12
Re-targeted the commit-gate PreToolUse hook in `.claude/settings.json` from
"CLAUDE.md staged" to the lenient "PLAN.md or ACTION_LOG.md staged", and reworded
CLAUDE.md's "Keeping state current" section to match. Note: settings.json hook
edits do not reload mid-session, so the new gate governs future sessions.
(Correction observed during execution: the hook re-reads settings.json per
invocation, so the new gate went live immediately; it checks the session cwd's
repo, so cross-repo commits need this repo's PLAN.md/ACTION_LOG.md staged.)

#### #0004 · note · 2026-06-12
Self-registered swiftwater-framework as a PI adopter: appended the adopter row to
the patterns repo's `_docs/planning-instrument/implementers.md` and ticked its T4.
Cross-repo commit made from this session.

#### #0005 · completed · T1 · 2026-06-12
Plan 25 complete: PI convention adopted — four artifacts scaffolded, CLAUDE.md
slimmed, meta-plan frozen, commit-gate hook re-targeted, framework registered as
a PI adopter. Quality gate green (ruff/format/mypy); PI invariants confirmed.
Plan 26 (Committed Memory) is next.

#### #0006 · note · 2026-06-13
T2 (Plan 26, Committed Memory) brainstormed; spec written
(`docs/superpowers/specs/2026-06-13-committed-memory-adoption-design.md`).
Decisions: conservative curation (clearly-safe framework memories only, no
rewording) + copy-not-move (native store untouched). Branch
`plan-26-committed-memory` off master (Plan 25 merged, `db5cdb9`).

#### #0007 · completed · T2 · 2026-06-13
Wired gitleaks in the framework's own repo (it previously shipped a backstop to
consumers but ran none itself): root `.pre-commit-config.yaml` (gitleaks v8.21.2)
+ `pre-commit install` + a `security` job in `ci.yml` (pinned binary, full-repo
scan). Full-repo scan clean before any memory was committed.

#### #0008 · note · 2026-06-13
Scaffolded the committed memory store: empty `MEMORY.md` index + `_memory/`, and
added the MEMORY-convention block + `@MEMORY.md` autoload import to CLAUDE.md.

#### #0009 · completed · T2 · 2026-06-13
Copied the 43 public-safe project memories into `_memory/` (+ `scope: project`);
native store untouched (copy, not move). 13 excluded (3 name Meridian, the rest
machine/personal/preference). Boundary spot-check clean (no Meridian / no
private paths in the copies).

#### #0010 · completed · T2 · 2026-06-13
Repaired 11 migrated memories whose `[[links]]` pointed at non-committed
(excluded/nonexistent) slugs — reworded those references to prose per the
convention's cross-store rule. All 25 distinct committed `[[slug]]` targets now
resolve within `_memory/`. Native links untouched (copy approach).

#### #0011 · completed · T2 · 2026-06-13
Built `MEMORY.md` (43 entries, reusing the native index's curated titles/hooks,
paths rewritten to `_memory/`). Index ↔ files bidirectionally complete (43 ↔ 43).

#### #0012 · note · 2026-06-13
Self-registered swiftwater-framework as a Committed Memory adopter in the patterns
registry (`_docs/committed-memory/implementers.md`); ticked its T8 (patterns log
`#0010`). Cross-repo commit; the framework session gate is satisfied by staging
this entry.

#### #0013 · completed · T2 · 2026-06-13
Plan 26 complete: Committed Memory convention adopted — gitleaks wired in the
framework's own repo, store scaffolded, 43 public-safe memories migrated (copy,
not move), 11 cross-store links reworded to prose, 43-entry index built, framework
registered as an adopter. gitleaks clean (with memories present); boundary
self-audit clean (only self-referential public `cdowell-swtr` repo coordinates,
which are safe to publish); convention invariants hold; gate green.

#### #0014 · amended · T2 · 2026-06-13
The CI `security` job (full-history `gitleaks detect`) surfaced 2 findings the
local hook missed — both are the intentional fake AWS key in
`tests/eval/fixtures/security/bad/hardcoded-secret.diff` (the payload the security
reviewer is meant to flag), not real secrets. The pre-commit gitleaks hook scans
staged diffs only; CI's full-history `detect` is the authoritative scan. Added
`.gitleaks.toml` allowlisting `tests/eval/fixtures/security/`; full-history scan
now clean — which also re-confirms the 43 migrated memories are clean under the
authoritative scan (it flagged only the fixtures, nothing in `_memory/`).

#### #0015 · note · 2026-06-13
First organic additions to the committed memory store (now 45): two gotchas
learned this session — `gitleaks-staged-vs-history-and-fixture-allowlist` and
`cross-repo-commit-needs-local-plan-staged`. Both public-safe project facts.
gitleaks clean; invariants hold (45 ↔ 45).

#### #0016 · note · 2026-06-13
Migrated task IDs T→FWK (PI v1→v2). Remap: T1=FWK1, T2=FWK2, T3=FWK3, T4=FWK4,
T5=FWK5, T6=FWK6, T7=FWK7, T8=FWK8, T9=FWK9, T10=FWK10. Historical log entries
above keep their T-form (append-only — never rewritten); the join holds via this
remap. New entries use FWK. (FWK10 = this migration; see
`docs/superpowers/plans/2026-06-13-pi-v2-migration.md`.)

#### #0017 · completed · FWK10 · 2026-06-13
PI v2 migration complete: vendored pi-convention.md (patterns main HEAD, @2c88543)
+ memory-convention.md (memory/v1) and re-pointed all references; adopted the FWK
prefix (T→FWK, numbers kept; remap #0016); relocated the PI pointer to AGENTS.md
with @AGENTS.md autoloaded by CLAUDE.md; registered v2/FWK by PR to
cdowell-swtr/patterns (PR #3). Runbook compliance self-check all-OK; gate green.

#### #0018 · note · 2026-06-13
Promoted the gh-only vendoring/registration learning into the committed store
(`framework-consumes-patterns-via-github-vendoring`, now 46) — public-safe +
project-useful, so the committed store is its proper home (travels to every
machine). gitleaks clean; invariants 46↔46. (Native duplicates pruned separately.)

#### #0019 · note · FWK5 · 2026-06-13
Brainstormed + wrote the Plan 27 (FWK5) LiteLLM-backend-foundation design spec and
implementation plan. Key decisions: (1) decomposed the "agentic-backend swap" into
a 5-row roadmap — this plan is row 1 (foundation, ships nothing external); rows 2–4
externalize the claude-cli plugin + add `--with Agents`/`--with HotSwapAgents`
batteries for Meridian; row 5 (adapter removal) is CONDITIONAL. (2) Keep the
`messages.create`/`Message` seam; swap only the backends' innards onto LiteLLM.
(3) The LiteLLM input-surface choice (`anthropic_messages` vs `completion`) is
GATED on a live go/no-go spike (Task 1), NOT assumed — explicitly avoiding the
circular justification "use the Anthropic surface because step 7 removes the
adapter" (step 7 only exists if an adapter is assumed). Plan written GO-primary
(anthropic_messages → ~zero adapter, row 5 evaporates) with a documented
`completion`+translator fallback. Spike S1 (real-API caching passthrough) is
BLOCKED pending `ANTHROPIC_EVAL_API_KEY`; S2 (custom-provider routing) is runnable
in-process. Executing via subagent-driven-development on branch
`plan-27-litellm-backend-foundation`.

#### #0020 · completed · FWK5 · 2026-06-13
Task 1 (interface spike) — **GO** on `anthropic_messages`. litellm 1.88.1 confirmed:
all assumed symbols exist (`anthropic_messages`, `CustomLLM`, `custom_provider_map`,
`RateLimitError`, `modify_params`). **S2 (the architecture gate) PASSED in-process,
no key:** `anthropic_messages(model="claude-cli/<m>")` dispatches to a
`custom_provider_map` handler via `acompletion` (async-native → seam drives it with
`asyncio.run`); litellm auto-strips the `claude-cli/` prefix; `cache_control`
survives into the handler input (system list folded into a `role:system` message);
boundary response is a `dict`. `CustomLLM.completion/acompletion` are handed a
`model_response` to populate and receive OpenAI-shaped `messages`. **Refinement of
the committed plan's "both S1+S2 needed for GO":** S2 alone is the gate (routing/
shape); **S1 (real-API caching) is a cost-lever confirmation, NOT a fallback
trigger** — caching failure would mean investigate `cache_control` placement, not
switch to `completion`. So the architecture is locked: anthropic_messages, near-zero
adapter, **roadmap row 5 (adapter removal) is dropped.** S1 + the Task 7 live smoke
remain BLOCKED on `ANTHROPIC_EVAL_API_KEY` (unset); proceeding with Tasks 2–6 (unit-
tested, no key) on the strong S2 signal. S2 kept as a permanent routing-regression
guard (`tests/review/test_litellm_spike.py`).

#### #0021 · completed · FWK5 · 2026-06-13
Task 2 — self-contained `claude-cli` CustomLLM plugin
(`src/framework_cli/review/litellm_provider.py`), ZERO `framework_cli` imports
(extraction-ready for roadmap row 2). Ports the `claude -p` mechanics verbatim
(0o600 system temp file + `--system-prompt-file`, stdin prompt, `_DISABLED_TOOLS`,
JSON parse, `_EXHAUSTION_MARKERS` → module-local `ClaudeExhausted(reset_hint=…)`).
`completion`/`acompletion` use `(*args, **kwargs)` to serve both litellm dispatch
(which hands a `model_response` to populate + OpenAI-shaped messages) and direct
unit calls; `_render_messages_to_prompt` flattens the OpenAI shape (system folded
in, `tool_calls`, `role:tool`) to the claude-text protocol. 17 unit tests incl. the
MAX_ARG_STRLEN guard; gate clean. Also fixed a Task-1 slip: `test_litellm_spike.py`
was committed format-dirty (hand-written, no `ruff format`) — reformatted here.
Controller-review nit deferred to branch-end: `_flatten_content` joins multi-block
content with a space vs the original `\n\n` (cosmetic; findings-parity unaffected).

#### #0022 · completed · FWK5 · 2026-06-13
Task 3 — `_anthropic_messages` seam helper in `backend.py`: the ONE call site for
litellm (`_litellm_anthropic_messages` = `asyncio.run(litellm.anthropic_messages(…))`,
lazy-imported, conditional `tools`/`api_key`/`num_retries` kwargs). Extended
`_normalize_content`/`_normalize_usage` to read litellm's **dict-shaped** content
blocks + usage (verified boundary shape: `content=[{"type":"text","text":…}]`,
`usage={input_tokens,output_tokens,cache_read_input_tokens,…}`, top-level
`stop_reason`) while keeping the object-shaped path for existing tests
(`_block_get`/`_resp_get` dict-or-object getters). 16 tests; gate clean. Backend
classes untouched (Tasks 4/5).

#### #0023 · completed · FWK5 · 2026-06-13
Tasks 4+5 (combined — both rewrite the two backend classes + re-point the same test
files) — both backends now route through `_anthropic_messages`. `ApiBackend(api_key,
num_retries)` → `anthropic/` prefix, maps `litellm.RateLimitError` → `BackendExhausted`.
`SubagentBackend(runner=None)` registers a `ClaudeCliLLM` (runner-injectable) in
`custom_provider_map` → `claude-cli/` prefix. **Exhaustion key fact (probed):** litellm
WRAPS the handler's `ClaudeExhausted` as `APIConnectionError` with the original on
`__cause__`; `_SubagentMessages.create` recovers it via the cause chain (preserving
`reset_hint`). Deleted the relocated `claude -p` mechanics from `backend.py` (now in
`litellm_provider.py`); trimmed dead imports (`anthropic`/`subprocess`/`tempfile`/…).
Updated `cli._make_backend` + `_review_run`/`_eval_run` fallbacks; dropped stale
`default_client` monkeypatches in test_agentic/test_framework_target/test_cli.
Re-pointed parity tests to mock `_litellm_anthropic_messages` (engine+normalization
now SHARED, so parity asserts both classes feed the engine identically + use the right
provider prefix; real transport divergence is covered by test_litellm_provider + the
Task-7 live smoke). 446 passed / 1 skipped; ruff+format+mypy clean. Branch-end
cleanup candidates: `default_client` is now dead prod code (kept only by its own
test); the `anthropic` dep may be droppable; `_SubagentMessages.__init__` mutates
global `custom_provider_map` per construction.

#### #0024 · completed · FWK5 · 2026-06-13
Task 7 (live smoke) + Task 8 partial. **Critical live verification PASSED:**
`test_live_subagent_large_input` drove the FULL real path
(`anthropic_messages(model="claude-cli/…")` → `asyncio.run` → litellm dispatch →
`ClaudeCliLLM.acompletion` → `claude -p` subprocess) with a >128 KB diff over the
subscription and returned parseable findings — the `MAX_ARG_STRLEN`/large-input
class that mocks can't catch, confirming the architecture end-to-end. Task 6 is
satisfied (retry tests pass; rate-limit→BackendExhausted mapping added in #0023).
Pinned `litellm>=1.88.1` (lock = 1.88.1); mypy-override step moot (targeted ignores
in the plugin suffice — `mypy src` clean with no global override). Offline gate
green: review+eval 326 passed/1 skipped, backend suites 446 passed, ruff+format+mypy
clean. **Still BLOCKED for final close:** S1 (API-path caching cost-lever, NOT an
architecture gate) needs `ANTHROPIC_EVAL_API_KEY` — `test_live_api_caching` is
written + skipped, one command from confirming once a key is present. FWK5 left
open pending that + the branch-end Opus review.

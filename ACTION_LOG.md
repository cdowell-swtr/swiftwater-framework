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

#### #0019 · note · 2026-06-14
Hotfix (standalone, off master): the render matrix went red on every **graphql**
combo — `fastapi==0.137.0` now raises `FastAPIError: Prefix and path cannot be both
empty` for Strawberry's GraphiQL GET route (empty path), which surfaces at
`app.include_router` during `create_app`. Upstream drift (latest strawberry 0.316.0
+ fastapi 0.137 are incompatible), NOT caused by any in-flight work — master is
equally affected; the FWK5 PR was just the first render run after the bump. Fix:
mount the GraphQL endpoint via the `GraphQLRouter`'s own `path="/graphql"` instead of
an `include_router(prefix="/graphql")` over an empty child path (endpoint URL
unchanged at `/graphql`). Verified by re-render: `create_app` builds, 108/108
generated-project tests pass across graphql+react. Updated the copier assertion
(`path="/graphql"` not `prefix="/graphql"`). gate green. Lands before FWK5 so its
render-complete goes green on rebase.

#### #0020 · note · FWK5 · 2026-06-13
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

#### #0021 · completed · FWK5 · 2026-06-13
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

#### #0022 · completed · FWK5 · 2026-06-13
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

#### #0023 · completed · FWK5 · 2026-06-13
Task 3 — `_anthropic_messages` seam helper in `backend.py`: the ONE call site for
litellm (`_litellm_anthropic_messages` = `asyncio.run(litellm.anthropic_messages(…))`,
lazy-imported, conditional `tools`/`api_key`/`num_retries` kwargs). Extended
`_normalize_content`/`_normalize_usage` to read litellm's **dict-shaped** content
blocks + usage (verified boundary shape: `content=[{"type":"text","text":…}]`,
`usage={input_tokens,output_tokens,cache_read_input_tokens,…}`, top-level
`stop_reason`) while keeping the object-shaped path for existing tests
(`_block_get`/`_resp_get` dict-or-object getters). 16 tests; gate clean. Backend
classes untouched (Tasks 4/5).

#### #0024 · completed · FWK5 · 2026-06-13
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

#### #0025 · completed · FWK5 · 2026-06-13
Task 7 (live smoke) + Task 8 partial. **Critical live verification PASSED:**
`test_live_subagent_large_input` drove the FULL real path
(`anthropic_messages(model="claude-cli/…")` → `asyncio.run` → litellm dispatch →
`ClaudeCliLLM.acompletion` → `claude -p` subprocess) with a >128 KB diff over the
subscription and returned parseable findings — the `MAX_ARG_STRLEN`/large-input
class that mocks can't catch, confirming the architecture end-to-end. Task 6 is
satisfied (retry tests pass; rate-limit→BackendExhausted mapping added in #0024).
Pinned `litellm>=1.88.1` (lock = 1.88.1); mypy-override step moot (targeted ignores
in the plugin suffice — `mypy src` clean with no global override). Offline gate
green: review+eval 326 passed/1 skipped, backend suites 446 passed, ruff+format+mypy
clean. **Still BLOCKED for final close:** S1 (API-path caching cost-lever, NOT an
architecture gate) needs `ANTHROPIC_EVAL_API_KEY` — `test_live_api_caching` is
written + skipped, one command from confirming once a key is present. FWK5 left
open pending that + the branch-end Opus review.

#### #0026 · completed · FWK5 · 2026-06-13
Branch-end Opus whole-branch review: **APPROVE-WITH-NITS** (gate re-verified green).
Fixed its two actionable findings: (Important) the eval loop's `except
anthropic.APIError` Exit(3) abort was partly dead post-migration — litellm errors
don't subclass `anthropic.APIError`. Probed the hierarchy: litellm's error types
(`AuthenticationError`/`RateLimitError`/`APIConnectionError`/`BadRequestError`/…) all
derive from **`openai.APIError`** (litellm builds on the openai SDK tree;
`litellm.exceptions.APIError` is only a sibling, NOT the ancestor — a first attempt
catching it failed the new test). Broadened the catch to `(anthropic.APIError,
openai.APIError)` + added `test_eval_aborts_loudly_on_litellm_api_error`. (Nit)
`_flatten_content` now joins multi-block content with `\n\n` (was a space) to match
the original system rendering. Deferred (reviewer-agreed) to a follow-up/row-2:
remove dead `runner.default_client` + its tests and assess dropping the `anthropic`
dep. 447 passed / 3 skipped; ruff+format+mypy clean.

#### #0027 · completed · FWK5 · 2026-06-13
**FWK5 / Plan 27 foundation DONE.** S1 (the last blocked check) ran with the eval key
(`~/.swiftwater-framework-keys.env`) and PASSED: `cache_read_input_tokens > 0` on the
repeat `anthropic/` call — Anthropic prompt caching survives the `anthropic_messages`
seam, so the cost lever holds. Full verification matrix green: S1 caching, S2 routing,
the live subagent `claude -p` MAX_ARG_STRLEN smoke, 447 offline tests, Opus
APPROVE-WITH-NITS (both findings fixed). Architecture as designed: near-zero adapter,
engine untouched, both backends behind one litellm seam; **roadmap row 5 (adapter
removal) dropped** — there is no adapter to remove. Opened downstream Next items:
FWK11 (externalize the claude-cli plugin + deferred cleanup), FWK12 (`--with Agents`
battery), FWK13 (`--with HotSwapAgents` battery). New follow-up folded into FWK11: a
benign litellm `coroutine … was never awaited` RuntimeWarning under `asyncio.run`
(cosmetic; silence later). Branch `plan-27-litellm-backend-foundation`, 8 commits;
ready for PR (master protected).

#### #0028 · completed · FWK5 · 2026-06-14
Folded the FWK11 cleanup into this PR (user request). (1) Removed dead
`runner.default_client` (no `src/` caller post-migration) and retargeted its 5 tests
to exercise `_max_retries()` directly (retry-budget coverage preserved). (2) **Dropped
the `anthropic` dependency** — assessment was clean: its only live uses were
`default_client` + the now-unreachable `except anthropic.APIError` belt-and-suspenders
(the API path is 100% litellm, whose errors derive from `openai.APIError`). Narrowed
the eval abort to `except openai.APIError`, removed the superseded
`test_eval_aborts_loudly_on_api_error`, and declared `openai>=2.0` as a direct dep
(it was already imported directly + is litellm's base). `anthropic` is now fully
absent from the lock (litellm doesn't require it). (3) Silenced the litellm
`async_success_handler` "coroutine never awaited" RuntimeWarning via a persistent,
narrowly-scoped module filter in `backend.py` (a call-scoped filter can't catch it —
it fires at GC time after `asyncio.run` closes the loop); verified gone on a live
subagent smoke run. Gate: 446 passed / 3 skipped, ruff+format+mypy clean. FWK11 is now
just the externalization.

#### #0029 · note · FWK11 · 2026-06-14
Brainstormed + wrote the FWK11 design spec + implementation plan: extract the in-tree
`claude -p` LiteLLM provider into a standalone git-tag package
(`cdowell-swtr/litellm-claude-cli`, public) that the framework depends on and FWK13
ships to projects. Decisions: external package (not template-payload duplication);
**git-tag** distribution (no PyPI, matches the gh-only posture); the framework deletes
its in-tree copy and depends on the package; entry-point auto-registration is
**spike-gated** (Task 1 — unverified in litellm 1.88.1) with explicit `register()` as
the guaranteed fallback; three test layers with the **litellm-dispatch integration
test** (FWK5's S2 probe made a kept, stronger test) as the critical one; package
carries its own gated live smoke (it can't borrow the framework's). Two-phase plan: A
= stand up the package repo + cut a real v0.1.0 tag, B = framework cutover. Executing
via subagent-driven-development on branch `fwk11-litellm-claude-cli-extraction`.

#### #0030 · completed · FWK11 · 2026-06-14
Task 1 (entry-point spike) — **NO-GO**. Source-conclusive: litellm 1.88.1 inits
`custom_provider_map` as an empty list (`litellm/__init__.py:1382`) and has **no**
entry-point loading that populates it (the `importlib.metadata` usages are all version
lookups); PR #15881 isn't in this release. So the package ships explicit `register()`
only — no `pyproject` entry point, no auto-registration test. The framework already
registers explicitly in its seam; FWK13 will add a one-line `register()` call to
generated projects. Task 5 takes its NO-GO path (README documents `register()`);
everything else in the plan is unaffected.

#### #0031 · completed · FWK11 · 2026-06-14
Phase A Tasks 2–6 — stood up the `litellm-claude-cli` package repo (public,
`cdowell-swtr/litellm-claude-cli`). Scaffolded pyproject (hatchling, `litellm>=1.88.1`,
NO entry point per the spike) + `.gitignore`/`.python-version`/README (documents
explicit `register()`). Moved the provider module verbatim → `src/litellm_claude_cli/
__init__.py` (only change: the module docstring reworded to drop two `framework_cli`
mentions — verified by diff to be docstring-only, zero functional change; `grep -c
framework_cli` = 0) and its 17 unit tests → `tests/test_provider.py` (one import line
re-pointed). Added the critical **litellm-dispatch integration test**
(`test_litellm_dispatch.py` — `anthropic_messages(model="claude-cli/…")` round-trips
through the real provider, offline) and the gated live smoke. Package gate: 18 passed
/ 1 skipped, ruff+format+mypy clean. Note: the package's own `uv sync` resolved
litellm **1.89.0** (floor `>=1.88.1`) and the integration test passes on it — watch
for a 1.88.1→1.89.0 bump when the framework re-locks in Phase B.

#### #0032 · completed · FWK11 · 2026-06-14
Phase A Task 7 — package CI + release. Added `.github/workflows/ci.yml` (Node-24-pinned
`checkout@v5` + `setup-uv@v7`; ruff/format/mypy/pytest, no framework tiers), pushed
`master`, set light branch protection (required `ci` check), and cut the real `v0.1.0`
tag. The package is now installable via
`git+https://github.com/cdowell-swtr/litellm-claude-cli@v0.1.0` — unblocks Phase B.

#### #0033 · completed · FWK11 · 2026-06-14
Phase B — framework cutover. Added `litellm-claude-cli` to deps via `[tool.uv.sources]`
(git tag), repointed `backend.py`'s two seam imports to `from litellm_claude_cli import
…`, `git rm`'d the in-tree `litellm_provider.py` + `test_litellm_provider.py`. uv lock
kept litellm at **1.88.1** (no bump). Framework gate green: 429 passed / 3 skipped
(seam tests — incl. the real-litellm wrapped-exhaustion cause-chain test — unchanged =
behavior preserved), ruff+format+mypy clean. **Packaging fix folded in:** the package
lacked a `py.typed` marker (mypy needed an `ignore_missing_imports` override, and every
future consumer would too), so shipped `py.typed` → cut **v0.1.1**, repointed the
framework to v0.1.1, and dropped the override (mypy clean on the package's own types).
Package now properly typed for all consumers.

#### #0034 · note · FWK11 · 2026-06-14
Branch-end Opus review (post-merge, for apparatus-parity): **APPROVE-WITH-NITS**;
verified clean — extraction fidelity (docstring-only diff), cutover completeness (no
dangling refs), packaging (py.typed in wheel), tags, seam binding. Two Important
findings handled: **I1** — the package README pinned `@v0.1.0` (pre-`py.typed`) while
the release/framework pin is v0.1.1; fixed both README snippets → v0.1.1 (pushed to the
package repo). **I2** — the framework's `[tool.uv.sources]` git dep is **uv-only**; a
plain-`pip` install would miss it. Acceptable for the uv-native framework (CLAUDE.md
mandates uv), but it matters for **FWK13**: generated projects may be pip-installed, so
the HotSwapAgents battery must write the dep as a **PEP 508 direct reference**
(`litellm-claude-cli @ git+…@vX.Y.Z`), not `[tool.uv.sources]` — recorded as a ⚠ on the
FWK13 plan line. Nits (entry-point-absence regression test; dispatch-level exhaustion
test) noted as optional, acceptable as-is.

#### #0035 · note · FWK12 · 2026-06-14
Brainstormed the `--with agents` battery (row 3 of the LiteLLM agent-capability
roadmap). Design spec written + self-reviewed:
`docs/superpowers/specs/2026-06-14-agents-battery-design.md`. Decisions: plain
LiteLLM over an API key (subscription hot-swap stays FWK13); split into two
mergeable slices — **FWK12** runtime core (config + completion/structured-output
service + one `/agents/complete` route + in-process obs + tests) then **FWK14**
agentic loop (tool registry + bounded run loop + read-only `Item` DB tool +
`/agents/run` + loop/tool obs). Avoided an `a/b` sub-key (PI IDs are flat ints) —
filed slice 2 as fresh **FWK14** (deps: FWK12). Config flows through the central
`APP_`-prefixed `Settings` with `agent_api_key: SecretStr` passed explicitly to
LiteLLM (the `provider` field is the FWK13 hot-swap seam); obs is `in-process`
(calls/latency/tokens/cost + error-rate alert + dashboard). PLAN.md: FWK12 line
re-scoped to slice 1, FWK14 added, FWK13 unchanged.

#### #0036 · note · FWK12 · 2026-06-14
Wrote the implementation plans for the agents battery (both slices), TDD/bite-sized,
no-placeholder, grounded in a thorough wiring recon of the template (route
autodiscovery, hand-rolled metrics exposition, the `in-process` obs-completeness
contract, the Item repo): `docs/superpowers/plans/2026-06-14-agents-battery-core.md`
(FWK12) and `…-agents-battery-loop.md` (FWK14, executes post-FWK12-merge). Two
plan-time refinements folded back into the spec for consistency: latency is realized
as a **p99 gauge** (house metrics style), not a histogram; metric series are
**label-light** (dropped the `model` label per the house cardinality doctrine). Plans
restate the review-model policy (Opus code-quality/branch-end), the framework-slice
gate cadence (skip-marker commits + one branch-end review), and the template-payload
TDD loop. No DB migration needed (completion is stateless; FWK14 tools read the
existing `items` table).

#### #0037 · amended · FWK12 · 2026-06-14
Pinned the plans' render-for-TDD helper to a direct `render_project(dest, {...,
package_name:'demo', batteries:['agents']})` call (the entrypoint the test suite uses)
instead of `framework new` — the CLI derives the package name from NAME and can't pin
`demo`, which the plans' `src/demo/…` paths + `from demo.…` imports require. Resolves
the one helper placeholder flagged at plan handoff.

#### #0038 · amended · FWK12 · 2026-06-14
Fixed a task-ordering bug in the FWK12 plan: the `litellm` dependency (Task 7) must be
applied before the service/route tasks (5–6), which `import litellm` in their
render-based tests — otherwise `uv sync` in the render omits litellm and the tests fail
at import. Added an execution-order note (1→2→3→4→7→5→6→8→9); task numbers unchanged.

#### #0039 · completed · FWK12 · 2026-06-14
Tasks 1+2 — registered the `agents` BatterySpec (`obs="in-process"`, no gated review
agents) and shipped its obs artifacts (Prometheus `HighAgentCallFailureRate` alert +
4-panel Grafana dashboard) as path-conditional `.jinja` files. obs-completeness suite
green (14 passed, agents case included); batteries + copier-runner green (271).
Implementer staged; controller committed.

#### #0040 · completed · FWK12 · 2026-06-14
Tasks 3+7 (litellm dep pulled ahead of the service task per the ordering fix) — added
the guarded agent settings block (`agent_provider/model/max_tokens/temperature` +
`agent_api_key: SecretStr`, the framework's first SecretStr field) and the guarded
`litellm>=1.88.1` generated-project dep. Render checks green: settings parse +
SecretStr round-trip, litellm resolves (to **1.89.0**, floor 1.88.1), ruff
format+check clean on the render, and a baseline (no-agents) render leaks neither
SecretStr nor litellm. Noted: litellm ships no type stubs → the service task owes a
targeted mypy override under the agents guard.

#### #0041 · completed · FWK12 · 2026-06-14
Task 4 — agent `errors` (AgentError/AgentExhausted) + in-process `metrics` modules
(hand-rolled Prometheus exposition singleton, house pattern: thread-safe, label-light,
p99 gauge). TDD red→green, 7 unit tests. Opus code-quality review = APPROVE-WITH-NITS;
applied the substantive nit (fixed-precision `:.6f` cost rendering to kill scientific
notation / float-accumulation noise — matters for FWK14 cost dashboards) plus a
tiny-cost test, a reset() test, and a comment on the intentional `_p99` divergence from
observability/metrics.py. ruff format+check clean on the render.

#### #0042 · completed · FWK12 · 2026-06-14
Task 5 — `AgentService` (LiteLLM completion + structured output): explicit api_key
pass-through (SecretStr), provider/model prefix, usage→metrics, lazy litellm import,
error→AgentExhausted/AgentError mapping; + a litellm `[[tool.mypy.overrides]]`
(no PEP 561 stubs). TDD, 13 unit tests, mypy+ruff clean. Opus review = APPROVE-WITH-NITS
with two empirically-verified fixes applied: (1) removed dead `except
litellm.exceptions.APIError` (litellm's concrete errors don't subclass it — real base is
the undeclared `openai.OpenAIError`; now RateLimitError→exhausted, broad→error w/ noqa +
comment); (2) cache-read tokens now read the real nested `usage.prompt_tokens_details.
cached_tokens` (the flat `cache_read_input_tokens` field doesn't exist → metric would
silently always be 0). Also wrapped structured-parse failures in AgentError + added
no-system/parse-failure tests.

#### #0043 · completed · FWK12 · 2026-06-14
Task 6 — `POST /agents/complete` demo route (auto-registered via include_routers; no
main.py edit) + wired `agent_metrics.render_prometheus()` into the `/metrics` endpoint
under the agents guard. Error→HTTP mapping: AgentExhausted→503 (caught first),
everything else→502. TDD functional test (mocked litellm, no DB): text/usage response,
503 exhaustion, 502 provider error, /metrics carries the agent series — 4 green.
ruff+mypy clean. Controller-level quality check (simple plumbing; deep service logic
already Opus-reviewed); branch-end Opus review will cover the whole branch.

#### #0044 · completed · FWK12 · 2026-06-14
Task 8 — verification + acceptance coverage. Framework gate green (ruff check + format,
mypy src = 45 files clean) and the full non-acceptance suite = 889 passed / 3 skipped
(no regression). Found a gap: the acceptance suite had per-battery tests for
websockets/webhooks/workers/etc. but NONE for agents — added two: (1)
`test_rendered_project_with_agents_battery_passes` (renders agents, asserts the battery
files, runs the 70% unit+functional gate, and proves test_agents.py actually ran via
100% coverage of routes/agents.py) — green in 58s; (2)
`test_rendered_project_precommit_clean_with_agents_battery` (a fresh agents render makes
a clean first pre-commit pass — exercises the generated project's mypy accepting
`import litellm` via the override, ruff, gitleaks) — green in 44s. Eval-fixture coupling
check: none (thresholds.yaml hits were the words "review agents", not change.patch
anchors).

#### #0045 · completed · FWK12 · 2026-06-14
Task 9 — branch-end whole-branch Opus review = **APPROVE / merge** (no Critical or
Important findings). Verified empirically: SecretStr key never logged/serialized/echoed
(route returns generic detail strings); Jinja guard isolation both ways (rendered
['agents'] vs [] and diffed — nothing leaks into a no-agents render; agents render wires
route autodiscovery + /metrics + settings + obs; agents+workers coexist); metric names
consistent across metrics.py → agents_alerts.yml → agents.json (no dead series); FWK14
seams (`_call(**extra)`, `_with_system`) clean. Two minors: (1) spec listed an
`agents/config.py` that was correctly folded into `AgentService._model` (YAGNI — a module
for a one-line provider/model f-string would be over-built); recording the deviation
here. (2) no fail-fast on an empty `agent_api_key` (unset key → 502 on first call) —
deferred to FWK14 (noted on its PLAN line). FWK12 complete; moving to Done and finishing
the branch.

#### #0046 · completed · release · 2026-06-14
Cut **v0.2.5** — bundles everything on master since v0.2.4: the **agents battery**
(FWK12, headline builder-facing capability + new `litellm` generated-project dep), the
LiteLLM review-engine foundation (FWK5), the externalized `litellm-claude-cli` package
(FWK11), and the GraphQL mount fix (#29). Patch bump (user choice; consistent with the
0.2.x per-plan cadence). Bumped pyproject `0.2.4→0.2.5`, `uv lock` (framework-cli→0.2.5),
`DOGFOOD_COMMIT→"v0.2.5"`. Validated: ruff+mypy(dogfood) clean, `uv lock --check` clean,
`uv build` → framework_cli-0.2.5.{whl,tar.gz}, 27 release/dogfood/version tests green.
**Deviation from the literal release-cut procedure:** did NOT bump the "FROZEN through
v0.2.4" markers in CLAUDE.md/meta-plan — the meta-plan is genuinely frozen at v0.2.4
(Plan 28); the v0.2.5 work (FWK5/11/12) is tracked in PLAN.md, so bumping the marker
would falsely claim the meta-plan covers it. Release goes via a `chore(release)` PR
(master is protected), then a lightweight `v0.2.5` tag → release.yml. Enables the Meridian
upgrade to pull the agents battery from a real tag.

#### #0047 · completed · FWK15 · 2026-06-15
Renamed the shipped `agents`-core battery → **`--with llm`** (it's an LLM runtime, not
an agent; the tool loop is the future `agents` battery). `git mv`'d the 6 brace-named
paths (module dir, alert, dashboard, route, 2 test files) + scripted the content rename
(token/module/`LLMService`/`LLM*`/`app_llm_*`/`/llm/complete`/`APP_LLM_*`/obs files),
then a prose pass + grep-driven straggler cleanup. **Caught by verification (not the
script):** pathlib-join path checks + a variable name in the acceptance test still
pointed at `agents/`/`routes/agents.py` (would have failed at runtime) — fixed; grep the
RENDERED project, not just source, since a stray `app_agent_*` silently orphans the
alert/dashboard. Verified: llm render clean (structure + zero residual agent in app
code + baseline leaks nothing), generated llm tests 17 green, ruff+format+mypy clean;
framework obs-completeness/copier/batteries 285 green (obs guard now validates the `llm`
surface); both llm acceptance tests green. Updated spec (re-taxonomy note + mapping),
PLAN (FWK12 superseded; added FWK15; **re-scoped FWK13 → `hotswapllm` as a transport
extension of `llm` that PRECEDES FWK14 `agents`** per user), committed taxonomy memory
[[llm-vs-agents-battery-taxonomy]]. Re-releases as v0.2.6 so Meridian upgrades onto the
honest name. (v0.2.5's `--with agents` stays a brief unconsumed blip.)

#### #0048 · completed · release · 2026-06-15
Cut **v0.2.6** (bundled into the FWK15 rename PR, v0.2.4-style — one PR, one
render-matrix). Bumped pyproject `0.2.5→0.2.6`, `uv lock`, `DOGFOOD_COMMIT→"v0.2.6"`;
ruff+mypy(dogfood) clean, `uv lock --check` clean, `uv build` → framework_cli-0.2.6.
{whl,tar.gz}, version-consistency tests green. Ships the `--with llm` rename so Meridian
upgrades onto the honest battery name. (Frozen-through markers left at v0.2.4 as before.)

#### #0049 · note · FWK13 · 2026-06-15
Brainstormed the per-task LLM selection capability. User pivoted from a single
API↔subscription hot-swap to **named LLM profiles** (different provider/model/backend
per task) + per-call overrides for spikes — which subsumes hot-swap (API vs sub = two
profiles). Design spec written + self-reviewed: `docs/superpowers/specs/
2026-06-15-llm-profiles-and-subscription-design.md`. Restructured into two slices:
**FWK13** = profiles in the base `--with llm` (named profiles via `APP_LLM_PROFILES`
JSON, `default` back-compat, per-call provider/model override, per-profile cost
metrics, key fail-fast, duck-typed `reset_hint` exhaustion = subscription-ready);
**FWK16** = `--with claudesubscriptioncli` (`requires` llm; adds the litellm-claude-cli
PEP-508 dep + claude-cli registration so `provider: claude-cli` is a valid keyless
profile). Renamed `hotswapllm`→`claudesubscriptioncli` (provider+channel+interface) per
user. Key seam: base llm stays plugin-free — exhaustion is detected duck-typed (any
cause-chain exception with a `reset_hint` attr → LLMExhausted), keyless-by-default via a
`KEY_REQUIRING_PROVIDERS` allowlist. FWK16 is the first battery with `requires` → the
obs/acceptance per-battery render tests must resolve requires. Also moved FWK15 (the llm
rename, v0.2.6) to Done.

#### #0050 · note · FWK13 · 2026-06-15
Wrote the FWK13 (Slice 1: LLM profiles) implementation plan, TDD/bite-sized, grounded in
the current post-rename llm battery code: `docs/superpowers/plans/2026-06-15-llm-profiles.md`.
9 tasks: LLMExhausted.reset_hint → LLMProfile/settings → profiles.py resolution →
per-profile metrics → profile-aware service (key fail-fast + duck-typed exhaustion) →
route profile → per-profile obs → render/acceptance → branch-end review + v0.2.7 release
(bundled). Key seam locked: base llm stays plugin-free (duck-typed `reset_hint` exhaustion,
`KEY_REQUIRING_PROVIDERS` keyless-by-default). FWK16 (claude-cli provider + the requires
test handling) is the next slice, not this plan.

#### #0051 · completed · FWK13 · 2026-06-15
Tasks 1+2 — `LLMExhausted` gains a keyword `reset_hint` attribute (enables the service's
duck-typed exhaustion); added `LLMProfile(BaseModel)` + `llm_profiles: dict[str,
LLMProfile]` (env `APP_LLM_PROFILES` JSON) to settings, all guarded by `"llm" in
batteries`. Forward-ref resolves without model_rebuild (same-module order). 15 unit tests
green, ruff+mypy clean, baseline render leaks neither symbol. Implementer staged;
controller committed.

#### #0052 · completed · FWK13 · 2026-06-15
Task 3 — `llm/profiles.py`: `resolve_profile` (default ← named overlay ← per-call
override) → `ResolvedProfile` (`.model_id`, `.requires_key`) + `KEY_REQUIRING_PROVIDERS
= {anthropic, openai}` (keyless-by-default so the base llm battery needs zero knowledge
of claude-cli). TDD, 24 unit tests. Opus review = APPROVE-WITH-NITS; applied: **api_key
`field(repr=False)`** (the dataclass auto-repr leaked the plaintext key — closed while
still inert, before Task 5 wires it live), case-insensitive `requires_key`, an
or-vs-is-not-None comment, + 4 locking tests (own-key inheritance, per-call+named compose,
temperature=0.0/max_tokens=0 kept, repr hides key). mypy+ruff clean.

#### #0053 · completed · FWK13 · 2026-06-15
Tasks 4+5 (coupled — the metric signature change ripples into the service) — profile
labels on the LLM spend series (`app_llm_calls_total{profile,outcome}` / tokens / cost;
latency stays an unlabeled p99 gauge) + a profile-aware `LLMService`: `resolve_profile`
per call, key fail-fast (`KEY_REQUIRING` provider + empty key → LLMError before the
network call), duck-typed exhaustion (any cause-chain exception with a `reset_hint` attr
→ LLMExhausted, `_NO_HINT` sentinel distinguishes absent-vs-None). Relabeled 8 existing
metric/service tests; added profile/fail-fast/keyless/exhaustion tests. 31 unit + 4
functional green, mypy+ruff clean. Opus review = APPROVE-WITH-NITS (no must-fix); applied
the cosmetic docstring rewrap. Empirically verified by the reviewer: `reset_hint` name is
collision-free in vendored litellm/openai, and `profile` is config-bounded (per-call
provider/model overrides change model_id but NOT the profile label → no cardinality
inflation). Recorded an FWK16 watch-out (keep ClaudeExhausted off the RateLimitError
lineage) on its PLAN line.

#### #0054 · completed · FWK13 · 2026-06-15
Tasks 6+7 — `/llm/complete` accepts an optional `profile` (defaults "default"; unknown →
LLMError → existing broad except → 502); per-profile obs: alert is now per-profile
failure rate (`sum by (profile)`), dashboard panels group calls/tokens/cost by profile
(latency p99 unchanged). Functional 5 green, obs-completeness[llm] green, valid JSON,
ruff+mypy clean. Controller review (simple wiring).

#### #0055 · completed · FWK13 · 2026-06-15
Task 8 verify + Task 9 branch-end. Framework gate green (ruff+format+mypy), full
non-acceptance suite 889 passed/3 skipped, both llm acceptance tests green, rendered-
project straggler grep clean (no `._model`, all obs series by-profile), no eval-fixture
coupling. Branch-end Opus review = APPROVE-WITH-NITS / MERGE (empirically verified:
secret masking end-to-end incl. profile keys, guard isolation both ways, backward-compat
of the default profile, obs-series<->metrics-name consistency, FWK16 seam ready). Applied
2 nits: token dashboard panel `sum by (profile, kind)` (keep both dimensions) + stale
alert comment. Deferred (noted): unknown-profile currently -> 502 (could be 400-class) on
the demo route. FWK13 -> Done.

#### #0056 · completed · release · 2026-06-15
Cut **v0.2.7** (bundled into the FWK13 PR). Bumped pyproject `0.2.6->0.2.7`, `uv lock`,
dogfood tag pin -> `v0.2.7`; ruff+mypy(dogfood) clean, `uv lock --check` clean, `uv build`
-> framework_cli-0.2.7.{whl,tar.gz}, 27 version-consistency tests green. Ships LLM
profiles (per-task selection) to builders — Meridian can define profiles now; the
claude-cli subscription profile lands with FWK16.

#### #0057 · note · FWK16 · 2026-06-15
Wrote the FWK16 (`--with claudesubscriptioncli`) plan: `docs/superpowers/plans/
2026-06-15-claudesubscriptioncli.md`. Slice 2 of the subscription design. Simplified at
plan time after inspecting the installed package: `litellm_claude_cli.register()` is an
idempotent public helper (no custom register module needed — call it in create_app's
startup guard), and `ClaudeExhausted` carries `reset_hint` and is NOT a RateLimitError →
caught by FWK13's duck-typed exhaustion seam → **zero base-llm service changes**. Also:
no claudesubscriptioncli-guarded file lives in the `llm/` dir, so the battery renders
clean alone → obs-completeness passes UNMODIFIED (the spec-anticipated obs-test requires
change is unnecessary; only the acceptance test needs `requires` resolution). 8 tasks;
dep is a PEP 508 git ref (`@v0.1.1`, pip-installable). Branched off the merged v0.2.7
master.

#### #0058 · completed · FWK16 · 2026-06-15
Tasks 1+2 — registered the `claudesubscriptioncli` BatterySpec (`requires=("llm",)`,
`obs="rides-existing"`, no gated review agents) + added the `litellm-claude-cli` dep as a
PEP 508 git ref (`@v0.1.1`). **Discovery:** hatchling rejects `@ git+...` direct refs
unless `[tool.hatch.metadata] allow-direct-references = true` — added that, gated on the
same battery (without it `uv sync`'s build step errors). resolve closure
`['claudesubscriptioncli','llm']`; obs-completeness passes UNMODIFIED (rides-existing,
renders clean alone — confirms the plan's call that the spec-anticipated obs-test change
is unnecessary); 272 framework tests green; dep installs (cached); baseline + llm-only
renders omit the dep AND the hatch stanza (guard isolation verified — both renders valid
TOML + format-clean).

#### #0059 · completed · FWK16 · 2026-06-15
Tasks 3+4 — wired the claude-cli subscription provider: `create_app` startup guard calls
the package's idempotent `litellm_claude_cli.register()` (lazy function-local import →
package off the import path when the battery is off); runtime-caveat docs in SECRETS.md
(keyless, needs an authenticated `claude` on PATH, not baked into the image); unit tests
(register install/idempotent, create_app registers, keyless `claude-cli/<model>` routing
with no api_key, real `ClaudeExhausted`→`LLMExhausted` through a wrapped cause chain) +
a gated live smoke. **Base llm service untouched** — the FWK13 keyless + duck-typed
exhaustion seam handles claude-cli transparently. No mypy override needed (function-local
import). Opus review = APPROVE; folded in 2 nits: an autouse fixture snapshotting
`litellm.custom_provider_map` (structural test isolation) + a clarifying comment. 5
pass/1 skip, ruff+mypy clean.

#### #0060 · completed · FWK16 · 2026-06-15
Task 5 — acceptance test `test_rendered_project_with_claudesubscriptioncli_battery_passes`:
renders the dependency-closed set (`resolve(['claudesubscriptioncli'])` → +llm, as the CLI
does), asserts the unit test + PEP 508 dep rendered, `uv sync` (fetches the git dep), runs
the 70% unit+functional gate. Green in 46s. This is the only test that needs `requires`
resolution (the obs test passes on the battery alone).

#### #0061 · completed · FWK16 · 2026-06-15
Task 6 verify + Task 7 branch-end. Framework gate green (ruff+format+mypy), no eval
coupling, full non-acceptance suite 890 passed/3 skipped (obs-completeness gained the
claudesubscriptioncli case), claudesubscriptioncli acceptance green (46s). Branch-end
controller whole-branch review (the core wiring already got a deep Opus review in Unit B
= APPROVE): clean small diff, all claude refs behind the battery guard in main.py, **base
llm core untouched**, guard isolation verified both renders. Captured the hatchling
gotcha as a committed memory [[pep508-git-dep-needs-hatch-allow-direct-references]]. FWK16
-> Done.

#### #0062 · completed · release · 2026-06-15
Cut **v0.2.8** (bundled into the FWK16 PR). Bumped pyproject `0.2.7->0.2.8`, `uv lock`,
dogfood tag pin -> `v0.2.8`; ruff+mypy(dogfood) clean, `uv lock --check` clean, `uv build`
-> framework_cli-0.2.8.{whl,tar.gz}, 27 version-consistency tests green. Ships the
claude-cli subscription provider — Meridian can now route a profile through the
subscription (the thing that unblocks heavy use without per-token API cost).

#### #0063 · note · FWK14 · 2026-06-15
Brainstormed the modern FWK14 (`--with agents` tool loop). The stale
`2026-06-14-agents-battery-loop.md` plan is superseded — it predated the llm rename,
profiles, and the separate-battery taxonomy. New design spec:
`docs/superpowers/specs/2026-06-15-agents-tool-loop-design.md`. Key decision (seam): the
agent loop is a SEPARATE `agents` battery (`requires=("llm",)`, `obs="in-process"`) with
an `AgentRunner` that delegates model calls to `LLMService` via ONE new public method,
`respond()` (raw tool-capable completion; `complete()` refactored onto it) — so the agent
inherits profiles + the subscription backend for free (`run(profile="sub")` = on the
Claude subscription). agents/ module = tools.py (read-only Item tools) + runner.py
(bounded loop, `agent_max_iterations` cap) + metrics.py (`app_agent_tool_calls_total` /
`app_agent_runs_total`) + `POST /agents/run`. Like claudesubscriptioncli, only the
acceptance test needs `requires` resolution; obs test passes on the battery alone.

#### #0064 · note · FWK14 · 2026-06-15
Wrote the FWK14 (agents tool loop) plan: `docs/superpowers/plans/2026-06-15-agents-tool-loop.md`.
9 tasks: BatterySpec + obs → `LLMService.respond()` seam (+ behavior-preserving `complete()`
refactor) → agent_max_iterations → tools.py (read-only Item tools) → agent metrics →
runner.py (bounded loop, Opus) → `POST /agents/run` + /metrics → render/acceptance
(resolved set) → branch-end + v0.2.9. Grounded in the current llm service/repo. Only the
acceptance test needs `requires` resolution (obs test passes on the battery alone).

#### #0065 · completed · FWK14 · 2026-06-15
Task 1 — registered the `agents` BatterySpec (`requires=("llm",)`, `obs="in-process"`) +
its obs alert (`HighAgentRunFailureRate` over `app_agent_runs_total`) + 2-panel dashboard
(tool calls, run outcomes). resolve closure `['agents','llm']`; obs-completeness passes
UNMODIFIED (agents adds its own alert+dashboard, renders clean alone); 272 tests green;
dashboard JSON valid.

#### #0066 · completed · FWK14 · 2026-06-15
Task 2 — added `LLMService.respond()` (raw tool-capable completion: returns the litellm
response so the agent loop sees content + tool_calls; adds `tools`/`tool_choice="auto"`
only when tools given) and refactored `complete()` onto it. The ONLY llm-battery change.
`complete_structured` untouched (response_format ≠ tools). Behavior-preserving: full llm
suite green (33 unit + 5 functional). Opus review = APPROVE (traced: resolve once, `_call`
once, same response to `_usage_dict` — no double-call/metric; empty-list tools edge
correct). Minors deferred (Any return + raw-shape coupling — acceptable for the
intra-battery seam).

#### #0067 · completed · FWK14 · 2026-06-15
Tasks 3+4+5 — agent-module building blocks: `agent_max_iterations` setting (agents guard,
default 5); `agents/tools.py` (`ToolContext`/`Tool`/`ToolRegistry`/`default_registry` with
read-only `get_item`/`search_items` over the existing Item repo — no write tools);
`agents/metrics.py` (`app_agent_tool_calls_total{tool,outcome}` / `app_agent_runs_total
{outcome}` hand-rolled singleton). TDD: 3 hermetic unit + 3 functional (Postgres) green,
mypy+ruff clean. Controller review (mirrors proven llm patterns; the runner gets Opus).

#### #0068 · completed · FWK14 · 2026-06-15
Task 6 — `agents/runner.py`: the bounded tool-calling loop over `LLMService.respond()`.
Dispatch tool_calls (correlated by `tool_call_id`), append the serialized assistant turn
(OpenAI wire shape — implementer's improvement over the plan's raw-object append) + tool
results, repeat until the model stops or `max_iterations` (counted outcome, not raised);
`LLMError`/`LLMExhausted` → `run="error"` once + re-raise. Profiles pass through
(`run(profile="sub")`). TDD, hermetic stub-service tests. Opus review = APPROVE
(empirically verified bound/correlation/serialization/error-accounting/read-only); folded
in 3 nits: removed a dead `if tool_calls:` guard, commented the error-string convention,
+ 2 hardening tests (multi-tool-call correlation, exact call-count at the cap). 9 unit
green, mypy+ruff clean.

#### #0069 · completed · FWK14 · 2026-06-15
Task 7 — `POST /agents/run` route (auto-discovered; builds `AgentRunner(LLMService(settings),
max_iterations=settings.agent_max_iterations)` over `default_registry()` + a `SessionDep`
ToolContext; LLMExhausted→503, other→502) + wired `agent_metrics` into `/metrics` under
the agents guard. TDD functional test (seeded items, mocked litellm tool-round→answer):
outcome=completed, text + tool_calls correct, /metrics carries the agent series. 2 green,
ruff+mypy clean. Controller review (plumbing).

#### #0070 · completed · FWK14 · 2026-06-15
Task 8 — agents acceptance test (renders `resolve(['agents'])` + runs the 70% gate incl.
all agents unit/functional tests) green in 52s. Full verification: ruff+format+mypy clean,
no eval coupling, full non-acceptance suite 891 passed/3 skipped, obs series consistency
exact (metrics emit app_agent_runs_total + app_agent_tool_calls_total; alert+dashboard
reference exactly those — no orphans).

#### #0071 · completed · FWK14 · 2026-06-15
Task 9 branch-end. Controller whole-branch review (the respond seam + runner already got
deep Opus reviews): 6 code commits; the llm-battery change is ONLY service.py (`respond()`
+ the behavior-preserving `complete()` refactor) — verified; guard isolation clean (no
agents symbols leak into an llm-only render); obs series consistent. Full suite 891
passed/3 skipped + agents acceptance green. FWK14 -> Done. The full agent arc
(FWK11→5→12→15→13→16→14) is complete.

#### #0072 · completed · release · 2026-06-15
Cut **v0.2.9** (bundled into the FWK14 PR). Bumped pyproject `0.2.8->0.2.9`, `uv lock`,
dogfood tag pin -> `v0.2.9`; ruff+mypy(dogfood) clean, `uv lock --check` clean, `uv build`
-> framework_cli-0.2.9.{whl,tar.gz}, 27 version-consistency tests green. Ships the
`--with agents` tool loop — the capstone of the agent arc (llm → claudesubscriptioncli →
agents). Meridian can now run a tool-using agent on its subscription via `run(profile="sub")`.

#### #0073 · completed · FWK17 · 2026-06-15
Fixed a consumer-blocking Docker build bug surfaced by Meridian's brief
(`meridian/_docs/.../2026-06-15-framework-llm-battery-dockerfile-git.md`): the
`claudesubscriptioncli` git dep (`litellm-claude-cli @ git+…`) can't be cloned in the
generated project's Docker builder stage because the uv image (`uv:python3.12-bookworm-slim`)
has no `git` → `"Git executable not found"`. **Invisible to our acceptance tier** (it runs
`uv sync` on the host, which has git; never `docker build`) — a Meridian-as-integration-test
catch. TDD: wrote a `--target builder` docker-build regression test that reproduced the exact
failure (red), then added a **battery-gated** `apt-get install git` to the builder stage of
`infra/docker/Dockerfile.jinja` (non-subscription images stay lean) → green (65s). Guard
isolation verified (llm-only Dockerfile unchanged). No Dockerfile lint hook in the template
pre-commit. Updated [[pep508-git-dep-needs-hatch-allow-direct-references]] with the
docker-builder-git + testing-gap lessons. Deferred (per user): Option 2 (PyPI-publish
litellm-claude-cli) + private-dep BuildKit secret. Releasing v0.2.10; Meridian then re-runs
`framework upgrade` + drops its `--allow-drift` (their MDN26).

#### #0074 · completed · release · 2026-06-15
Cut **v0.2.10** (bundled into the FWK17 PR). Bumped pyproject `0.2.9->0.2.10`, `uv lock`,
dogfood tag pin -> `v0.2.10`; ruff+mypy(dogfood) clean, `uv lock --check` clean, `uv build`
-> framework_cli-0.2.10.{whl,tar.gz}, 27 version-consistency tests green. Ships the
Docker-builder git fix so claudesubscriptioncli consumers' `docker build` works.

#### #0075 · note · FWK8 · 2026-06-15
Brainstormed FWK8 (Traefik docker-provider acceptance coverage). Key finding: the 10
`--profile dev` acceptance tests already START Traefik but NEVER route through it (they
hit prometheus/seeded-items/app:8000 directly) — Traefik with a broken docker provider
still starts (`up -d` doesn't wait), so the v3.1→Docker-27 break was invisible. Design
(approved): a dedicated test that ROUTES `https://{slug}.localhost/health` through Traefik
(dev profile, TLS-verify-off, app already labeled) → 200 proves the docker provider
connected + discovered + proxied. Spec: `docs/superpowers/specs/2026-06-15-traefik-docker-
provider-acceptance-design.md`. Test-only → NO release (not in the wheel). User expanded
scope into the broader CLASS → spun off **FWK18** (agentic assessment of all
provisioned-but-unexercised real-runtime surfaces → conditional framework-native
coverage-gap reviewer); sequenced after FWK8.

#### #0076 · amended · FWK8 · 2026-06-15
Revised the FWK8 spec per user: the mkcert/`task certs` cert path is the incident's
ORIGIN (a WSL/Windows cert inconsistency) — verify-off + Traefik's default cert left it
uncovered. Found `task certs` issues a `*.localhost` mkcert cert that `dynamic/tls.yml`
loads. Found `ci.yml` runs `pytest --ignore=tests/acceptance` → the docker dev-stack tier
is LOCAL-ONLY (this box has docker+mkcert+go-task), so no mkcert-availability obstacle.
Revised test: render → `task certs` → up dev → route `https://{slug}.localhost/health`
with TLS verify ON against the mkcert root CA → 200. Verify-ON makes the cert path
load-bearing (cert-gen/mount/tls.yml regression fails the handshake; docker-provider
regression fails the route) — both surfaces, one assertion. Corrected the proof note
(local execution, not render-matrix).

#### #0077 · note · FWK8 · 2026-06-15
Wrote the FWK8 plan: `docs/superpowers/plans/2026-06-15-traefik-acceptance.md`. 3 tasks:
(1) the cert+route regression-guard test (render → `task certs` → up dev → TLS-verified
200 through Traefik); (2) **prove it bites** — temp-downgrade Traefik v3.6→v3.5 → test
FAILS (reproduces the Docker-27 break), revert → PASS (the TDD-analog, since the bug is
already fixed); the cert surface bites by construction (verify-ON). (3) finalize, NO
release (test-only, not in the wheel; local-only since acceptance is CI-ignored).

#### #0078 · completed · FWK8 · 2026-06-15
Implemented + debugged the Traefik route-through test. First run FAILED on the fixed
(v3.6) codebase — systematic-debugging found TWO test-design bugs (NOT framework bugs):
(1) `{slug}.localhost` doesn't resolve in Python here (`/etc/nsswitch.conf` = `files dns`,
no nss-myhostname; getaddrinfo fails — browsers resolve `*.localhost` internally, glibc
doesn't) → connect to `127.0.0.1:443` + `Host` header for routing; (2) OpenSSL's
`X509_check_host` won't match the cert's `*.localhost` wildcard SAN to `{slug}.localhost`
(single-label parent — browser-valid, OpenSSL stricter) → `check_hostname=False` + chain-
verify against the mkcert-ONLY CA (still proves Traefik served the real mkcert cert, not a
default). Validated the fix against a live stack (served cert issuer = mkcert CA, SAN
*.localhost, HTTP 200). Bite-proven: v3.5 → FAIL (`HTTP 404` — docker provider broken,
cert/file-provider fine), v3.6 → PASS (stable, ~45s, twice). Synced the spec to the impl;
captured [[testing-traefik-tls-route-from-python]]. Test-only → NO release.

#### #0079 · note · FWK18 · 2026-06-15
Brainstormed + re-keyed FWK18 → **FWK18** (assessment now) + **FWK29** (durable mechanism,
designed from FWK18's evidence). Wrote the FWK18 design spec:
`docs/superpowers/specs/2026-06-15-runtime-coverage-assessment-design.md` — a multi-agent
`Workflow` sweep over 7 provisioned-surface clusters (Docker image build, base/dev stack,
observability, data+services, entrypoint/certs/tasks, non-dev overlays, per-battery live
wiring); per-cluster finders classify exercised/indirect/unexercised with file:line evidence
both sides → adversarial-verify each gap (refute it) → synthesize a ranked inventory. Shared
"exercised = a test DRIVES it and asserts its effect" heuristic. Recon already shows ≥1 gap
(baseline `docker build` never run — only the claudesubscriptioncli builder stage is built).
Output: `docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`; each gap → a
follow-on test task. Process note: FWK18's "implementation" is RUNNING the Workflow, not a
TDD code plan, so it skips writing-plans. NO release (analysis + docs). Branch
`fwk18a-coverage-assessment`.

#### #0080 · note · FWK18 · 2026-06-15
On user pushback ("no need for a plan?"), wrote a plan after all — not a TDD code plan but
the executable design of the Workflow: `docs/superpowers/plans/2026-06-15-coverage-assessment.md`.
Mapped the 7 clusters to REAL template file-lists (cross-checked vs `find infra -type f`: all
8 compose overlays, every Dockerfile stage, full observability tree, entrypoint, Taskfile,
traefik) + the test-side grep targets + the finder/verifier/synthesizer schemas + prompts.
Highest-leverage review point flagged = a finder pointed at an incomplete file-list reads a
surface as "covered". Recon showed the acceptance suite is LARGE (prometheus/loki/tempo/
deploy-e2e/root-owned all covered) → Phase-2 adversarial-verify + a controller manual
spot-check (Step 3) are the over-claim defense. Awaiting user review of the cluster file-lists
before running.

#### #0081 · amended · FWK18 · 2026-06-15
User caught a real design gap: the finders give independent analysis WITHIN each cluster, but
nothing independently checks whether the 7-cluster TAXONOMY is complete (a forgotten category
→ no finder surfaces it; the assessment's own blind spot). The 7 were infra-centric, missing
provisioned execution surfaces outside `infra/` (`.github/workflows/*`, `.pre-commit-config`,
`alembic/`, `seed.py`, frontend build). Added **Phase 0 — independent surface census**: 2
enumerators BLIND to the clusters (orthogonal lenses: by-lifecycle, by-directory) catalogue
all provisioned runtime/build surfaces over the whole template → controller reconcile (plain
JS) maps each to a seed cluster → the residual answers "do other clusters exist?" and becomes
an 8th assessed cluster if non-empty. Updated spec + plan; the spec's old "no discovery agent
needed" line was exactly the flawed assumption.

#### #0082 · completed · FWK18 · 2026-06-15
Ran the assessment Workflow (65 agents, 2.77M tokens, ~20 min; 5 overturned gaps). Two
script bugs first: a missing closing paren in the Find-phase parallel (node --check on a
/tmp copy pinpointed it — `return` at top level is a node-check false-positive the harness
allows), and the nested-backtick-escape risk → rewrote prompts with `.join('\n')` arrays,
no backticks inside strings. RESULTS: census 130 surfaces; the independent Phase-0 taxonomy
check (user's catch) PAID OFF — 84 fell outside the 7 seed clusters, 51 were true residual
CATEGORIES the infra-centric partition missed (app-bootstrap/create_app/lifespan, the whole
CI-time lifecycle, pre-commit/.claude hooks, deploy orchestration) → assessed as an 8th
cluster. Find: 116 surfaces, 63 EXERCISED, 53 candidate gaps; adversarial verify killed 5
(incl. my own pre-assessment "baseline docker build never run" headline — the dev:lite test
builds the runtime image at test_rendered_project.py:720). Synth → 27 ranked entries (8 high
/ 15 med / 4 low). Controller hand-validated 4 highs (prod.yml config-only; workers eager;
claudesubscriptioncli --target builder only; lite runtime build) — all held. Wrote the
inventory + 10 grouped follow-on tasks (FWK19–28) + 4 recurring-shape seeds for FWK29 to
`docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`. No release.

#### #0083 · amended · FWK18 · 2026-06-15
Naming fix (user-flagged): the `a/b` suffixes FWK18a/FWK18b violate the PI convention — task
IDs are monotonic, never-reused `<PFX>N` integers, no suffixes (pi-convention.md §1). Renamed
**FWK18a → FWK18** (the assessment IS the original FWK18 plan) and **FWK18b → FWK29** (the
durable mechanism is a separate plan; takes the next free monotonic id — FWK19–28 were already
allocated to the follow-on tests, so allocation order gives it 29; priority lives in PLAN
ordering, not the number). Swept the rename across PLAN, this log (entries #0079–#0082
corrected in place, same-day), the spec/plan/assessment docs. Also removed a leftover DUPLICATE
FWK29 line in PLAN (two near-identical durable-mechanism entries from the two-pass re-key) —
kept the evidence-grounded one. Docs-only; branch `fwk18-rename-convention`; no release.

#### #0084 · amended · FWK18 · 2026-06-16
Deploy-model re-rank (user challenge: "do FWK19/FWK22 stand with no staging/prod deploy
target defined?"). Verified the template: the ONLY shipped deploy target (compose-ssh.sh)
brings up `app-host.yml` (app-only) — NOT prod.yml/staging.yml; `strategy.sh`'s `__target_*`
hooks are intentional `_todo` stubs (exit 1) until a consumer wires a target; the orchestration
+ compose-ssh→app-host path are already covered by test_deploy_compose_ssh.py + test_deploy_e2e.py.
The finders flagged "prod.yml never brought up" correctly but INFLATED the risk — they didn't
model that no shipped path consumes prod/staging/services.yml (they're consumer-target
scaffolding). Corrections: **H8/FWK22 DROPPED** (tombstone, id not reused — deploy is
consumer-implemented by design; only a thin workflow-graph assert remained, actionlint covers
the YAML). **H1/H2/H7 DEMOTED high→low** (guard = `compose config` merge-validation, not live
bring-up). **FWK19 re-scoped high→med**: staging/services.yml merge-validation (CI-visible) +
`test.yml` live (the one shipped+used overlay, via `task test:stack`); dropped the prod/staging
live bring-up. Revised counts 4 high / 15 med / 7 low + 1 dropped. Standing highs unaffected:
FWK20 (workers/beat live), FWK21 (battery Docker runtime). Inventory Correction section + inline
entry markers + PLAN updated. Docs-only; branch `fwk19-22-deploy-rescope`; no release.

#### #0085 · note · FWK29 · 2026-06-16
Brainstormed the durable mechanism. Key reframe (user): a deterministic check is CLOSED-WORLD
(only finds what it's wired for) — a good ratchet but NOT a reviewer, which was the original
intention (open-world: find surfaces outside the scan's purview). So the mechanism is TWO
complementary subsystems with a graduation loop: **FWK29 = deterministic completeness check +
classification registry** (closed-world ratchet, gates CI, carries the re-rank) and **FWK30 =
agentic framework-native coverage-gap reviewer** (open-world discovery, advisory, defers to
FWK29's registry; recurring findings graduate into FWK29's rules). Decomposed foundation-first
(reviewer needs the registry to defer to). FWK29 design: a `gate`-tier test renders all-batteries
→ 6 enumeration rules (compose overlays/services, Dockerfile stages, scripts, workflow jobs,
hooks; ~50–60 keys) → asserts each is classified EXERCISED|EXEMPT|KNOWN_GAP(FWK id) in a typed
`tests/runtime_coverage/registry.py`; set-equality + reference-integrity, à la integrity/test_classes.
THREE statuses (KNOWN_GAP lets it ship without blocking on FWK19–28; ratchet still stops NEW
unclassified surfaces). In-app code paths explicitly OUT (FWK30's domain — the honest closed-world
edge). Seeding = the rigorous re-rank + reconcile the FWK18 inventory. Spec written:
`docs/superpowers/specs/2026-06-16-runtime-coverage-completeness-check-design.md`. Test-only →
no release. Branch `fwk29-coverage-completeness-check`.

#### #0086 · note · FWK29 · 2026-06-16
Wrote the FWK29 plan: `docs/superpowers/plans/2026-06-16-runtime-coverage-completeness-check.md`.
4 tasks: (1) the six enumeration rules (`tests/runtime_coverage/enumerate.py`) + unit tests
against an all-batteries render; (2) the typed registry scaffold + the completeness test
(`test_completeness.py`, 6 assertions: set-equality, no-stale, unique-keys, exercised-names-
existing-test, known-gap-links-FWK, exempt-has-reason) → RED (empty registry); (3) seed the
registry to GREEN = the rigorous re-rank (10 worked entries from the FWK18 inventory + a rubric
for the rest); (4) reconcile the inventory + finalize. Grounded the code in real repo patterns
(`render_project` + `resolve(battery_names())`, the `test_obs_completeness` yaml-parse shape).
Two execution-time unknowns flagged with remedies: all-batteries co-render (fallback to the
matrix `full` set) and rendered service/job-name drift (print + correct the representative).
Test-only → no release.

#### #0087 · completed · FWK29 · 2026-06-16
Task 1 (subagent-driven): the six enumeration rules `tests/runtime_coverage/enumerate.py` +
unit tests. All-batteries render co-renders cleanly → **91 surface keys** (more exhaustive than
the ~50–60 estimate). One representative corrected: the rendered project's ci.yml lint job is
`lint`, not `gate` (that's the framework's own job name). Spec review (Sonnet) ✓; code-quality
(Opus) ✓ APPROVE — folded in its suggestion: an exact-set assertion pinning the 3 Dockerfile
stages (multiplicity, not just presence). 3 tests pass. Controller commits (implementer staged).

#### #0088 · completed · FWK29 · 2026-06-16
Tasks 2+3 (subagent-driven, Opus implementer): the typed registry + completeness test, seeded.
All 91 surfaces classified — **41 EXERCISED / 22 EXEMPT / 28 KNOWN_GAP**; all 6 completeness
tests pass. Spec review (Sonnet) ✓. Code-quality + CLASSIFICATION-ACCURACY review (Opus) ✓
APPROVE, no critical findings — spot-checked ~15 entries across all statuses against the real
tests: exporter split correct (prometheus/loki/tempo EXERCISED, postgres/redis/celery/mongodb
KNOWN_GAP FWK23 — the scrape test hard-filters job==app); worker/beat correctly KNOWN_GAP FWK20
(the one test that ups them asserts only __pycache__/UID, never the live broker); builder
EXERCISED-transitively (runtime serves /health through COPY --from=builder) vs frontend-build
KNOWN_GAP (SPA built-not-served, H6). Implementer flagged 4 inventory disagreements/extensions
for Task 4 reconciliation (gen_observability.py not in inventory→EXEMPT; dev.yml:frontend→FWK21
by analogy to H6; services.yml split FWK19/FWK20; coverage-threshold EXERCISED-via-command nuance).

#### #0089 · completed · FWK29 · 2026-06-16
Task 4 (controller): reconciled the FWK18 inventory — added a "Correction (2026-06-16b):
registry-seeding reconciliation" subsection capturing the 4 finer-grained items (none reclassified
a ranked gap as covered — no inflation) + a successor-pointer naming `tests/runtime_coverage/registry.py`
as the authoritative current view. Gate green: 9 runtime_coverage tests pass, ruff check + format
clean, mypy src clean (unaffected — tests/-only). FWK29 → Done. Next: finish the branch (PR, no
release) then FWK30 (the open-world reviewer) is unblocked — the registry it defers to now exists.

#### #0090 · completed · FWK30 · 2026-06-16
Brainstorm → design spec for the open-world coverage-gap reviewer (FWK29 registry now exists,
unblocking it). Decisions: **scope = both halves** (A new-kind/unclassified enumerable surface +
B in-app code-path surfaces), prompt draws a hard coverage-lens boundary vs `architecture`
(design soundness) and `observability*` (instrumentation); **B is diff-anchored (B-i)** not a
whole-tree audit; **defers to `registry.py` by reading the source directly** (no generated
manifest); **full repo diff seed** via a per-agent diff scope (resolves the target-scope wrinkle —
the other 5 framework agents keep template-excluding `framework_diff()`); **glob-gated activation**
(`template/**`, `tests/runtime_coverage/**`) — needs the framework-target dispatch to honor
`active_when`/`trigger_globs`; **advisory** (`block_threshold=None`). Eval fixture pair (positive
flag + negative defer-to-same-PR-registry) for calibration. Spec:
`docs/superpowers/specs/2026-06-16-fwk30-coverage-gap-reviewer-design.md`. Next: writing-plans.

#### #0091 · completed · FWK30 · 2026-06-16
Implementation plan written (7 tasks, TDD/bite-sized). Planning surfaced one spec gap and
resolved it with the user: the eval harness is generated-project-shaped (`realize_*` renders
a project), but coverage-gap reviews framework SOURCE (template jinja + `tests/runtime_coverage/
registry.py`) — none of which exists in a render → **E1: a framework-shaped realize** (copy the
template + runtime_coverage subtrees into a temp git repo, apply patch, diff; production-faithful).
Also pinned the per-agent diff mechanism: glob-gating already exists at `cli.py:1804`, but matches
against template-EXCLUDING `framework_diff()` → coverage-gap would always skip; fix = a
`reviews_template` AgentSpec flag → `pr_diff()` on the framework target. And `framework_only` flag
→ excluded from `active_agents()` (the generated-project set) so it doesn't leak into the 15-agent
PR matrix / break `test_full_active_sets`. Plan:
`docs/superpowers/plans/2026-06-16-fwk30-coverage-gap-reviewer.md`. Next: execute (subagent-driven).

#### #0092 · completed · FWK30 · 2026-06-16
Task 1 (Sonnet impl, controller-verified): `AgentSpec` gains `framework_only` + `reviews_template`
(both default False); `active_agents()` excludes `framework_only` agents from both push + PR base
sets (battery_extra untouched). New `tests/review/test_coverage_gap.py` (2 tests). 41 review tests
green, ruff+mypy clean. No agent registered framework_only yet → active sets unchanged.

#### #0093 · completed · FWK30 · 2026-06-16
Task 2 (Sonnet impl, controller-verified): authored `src/framework_cli/review/agents/coverage-gap.md`
(76 lines) — coverage lens, hard boundaries vs review-architecture/observability/env-parity, strict
"exercised" definition, two diff-anchored gaps (new-kind + in-app), defer-to-registry by reading
registry.py/enumerate.py, JSON-only output. +2 prompt tests (4 total in test_coverage_gap.py). Green.

#### #0094 · completed · FWK30 · 2026-06-16
Task 3 (Sonnet impl, controller-verified): registered `coverage-gap` in `_SPECS` (review-coverage-gap,
advisory/None, file-trigger, AGENTIC_MODEL/Opus, agentic, framework_only+reviews_template,
trigger_globs template/** + runtime_coverage/**) + `FRAMEWORK_AGENTS` (alphabetical, 6→7) + context.py
exception comment. Updated test_framework_target (7-tuple), test_context_policy (agentic set), +3 spec
tests. Glob form `**` confirmed (fnmatch `*` spans `/`). 60 targeted tests green; test_full_active_sets
still green (framework_only keeps it out of the 15-agent PR set). KNOWN TRANSIENT RED:
test_evals::test_every_registered_agent_has_fixtures (coverage-gap has no fixtures yet) — restored
green by Task 6.

#### #0095 · completed · FWK30 · 2026-06-16
Task 5 (Sonnet impl, controller-verified): framework-shaped eval realize. `realize_cached` branches
on `fx.agent in _FRAMEWORK_SHAPED_AGENTS` ({coverage-gap}) → copies `src/framework_cli/template` +
`tests/runtime_coverage` into a temp git repo (gc.auto=0 race guard), applies the patch, diffs —
instead of rendering a project (coverage-gap reviews framework SOURCE, not generated output;
production-faithful). `_framework_repo_root()` = evals.py parents[3]. Render path byte-unchanged for
all other agents (28 harness tests green). Impl learning for Task 6: `git apply` needs >=3 context
lines at file top → fixtures must be generated from real `git diff`, never hand-counted 1-context hunks.

#### #0096 · completed · FWK30 · 2026-06-16
Task 6 (Sonnet impl, controller-verified) + plan-design correction. Eval fixture pair:
**bad/unexercised-k8s-manifest** — adds a k8s Deployment at `template/infra/k8s/deployment.yaml.jinja`
(a NEW KIND: enumerate.py scans compose/docker/scripts/workflows/hooks, NOT infra/k8s) + a tracked
README breadcrumb so the realized seed-diff is non-empty (agentic agent then globs the new file) →
must FLAG; **good/classified-cache-overlay** — adds a compose overlay (ENUMERABLE → FWK29's job) +
the matching registry.py SurfaceClass in the same diff → must DEFER (silent). CORRECTED the plan's
original bad-fixture design (a new compose overlay) which was wrong — overlays are enumerable and
coverage-gap defers them; the bad case must be a kind outside the six rules. Patches generated from
real `git diff --staged` (validate_patch_hunks []). thresholds.yaml: coverage-gap 0.67/0.34. Full
review suite GREEN (319 passed) — test_every_registered_agent_has_fixtures restored.

#### #0097 · completed · FWK30 · 2026-06-16
Task 4 (Sonnet impl, controller-verified): per-agent diff scope in the live `review` command. On the
framework target a `reviews_template` agent (coverage-gap) now sources the template-INCLUSIVE
`pr_diff()`; the five general framework agents keep template-excluding `framework_diff()`. Resolves
the target-scope wrinkle so coverage-gap's template/registry trigger-globs match the gate at
cli.py:1804 (else it always skipped) and it sees same-PR registry classification. `pr_diff` already
imported; no new type-ignore. 17 targeted/framework-target tests green.

#### #0098 · completed · FWK30 · 2026-06-16
Branch-end reviews: spec-compliance (Sonnet) ✓ all 9 reqs met, no extra; code-quality (Opus) ✓
APPROVE WITH NITS (gating only on the live eval). Applied 3 review fixes (Sonnet impl): (1) evals.py
framework-shaped realize now `git add -A` + `git diff --cached` so NEW surface files appear in the
seed diff — production-faithful (pr_diff shows committed new files), replacing the fragile
breadcrumb-inference path; (2) regenerated the bad fixture to the k8s manifest ALONE (dropped the
now-unneeded README breadcrumb); (3) defense-in-depth — `active_agents` battery_extra sets also filter
framework_only (+ a battery-gated framework_only exclusion test). Seed now carries each surface
directly (bad→k8s; good→overlay+registry). 69 review/eval tests green; ruff+mypy clean. Remaining:
live eval calibration (Issue #1) — needs the eval key/backend.

#### #0099 · completed · FWK30 · 2026-06-16
Engine bugfix (FWK30-surfaced, controller TDD): the agentic tool-loop stored backend response
blocks (`backend.TextBlock`/`ToolUseBlock` dataclasses) directly into `messages`; on a multi-turn
(tool-using) call litellm serializes the replayed messages → `TypeError: TextBlock is not JSON
serializable`. Latent because every other agentic agent is calibrated via the free subagent backend
and the scripted unit-test client never serialized; coverage-gap is the framework's first ALWAYS-
multi-turn agentic agent (must read registry.py/enumerate.py) run on the paid api backend. Fix:
`_assistant_turn()` converts blocks to Anthropic wire-format dicts (`{"type":"text"...}` /
`{"type":"tool_use"...}`, empty text dropped) at both append sites in agentic.py. Regression test
adds a `_SerializingClient` that json.dumps messages each turn (the scripted client didn't). 322
review tests green. Also fixes the same crash on the production review runtime path.

#### #0100 · completed · FWK30 · 2026-06-16
Live calibration (paid api backend, Opus, repeat 3): **recall 1.00 / fp 0.00 PASS**. First run scored
fp 1.00 — the agent (correctly!) flagged the "good" fixture because my registry classification used
the TEMPLATE key `overlay:cache.yml.jinja` while enumerate.py emits RENDERED keys (`overlay:cache.yml`
+ the service `service:cache.yml:cache`), so the classification wouldn't satisfy FWK29. Regenerated the
good fixture with both correct rendered keys → agent defers (0 findings ×3). Bad fixture: flags the
k8s manifest as NEW-KIND ×3 with accurate reasoning. Annotated thresholds.yaml (recall_min 0.90 /
fp_max 0.10, observed 1.00/0.00 per the -0.10/+0.10 convention); wrote scorecard
docs/superpowers/eval-scorecards/2026-06-16-coverage-gap.md. 95 review/eval tests green.

#### #0101 · completed · FWK30 · 2026-06-16
Final whole-branch Opus review = **APPROVE** (merge-ready). Applied its one Minor (optional,
pre-existing) hardening: the agentic recovery path now replays the model's raw text with a
non-empty fallback (`text or "(no parseable content)"`) instead of routing through `_assistant_turn`
(which could yield an API-invalid empty content list when the sole block is empty) + a regression
test. 323 review tests green, ruff/format/mypy clean. PLAN.md: FWK30 → Done. Full suite earlier =
961 pass / 2 docker dev:lite acceptance failures (CI-ignored tier; pre-existing, template untouched
by FWK30 — flagged separately for investigation, `serves_health` reproduces independent of branch).
Next: finish the branch (PR; no release — review-infra only).

#### #0102 · completed · FWK32 · 2026-06-16
Born-red dependency drift (like FWK17). render-matrix went green→red between FWK29 (17:07Z) and
FWK30 (20:21Z) with FWK30 touching no template/workers code → external: celery's beat scheduler
imports `tzlocal` (get_localzone) but celery no longer declares it; the render-matrix resolves
fresh (no --frozen) so a fresh `uv sync` dropped tzlocal → `import <pkg>.tasks` fails → workers
projects' own suites fail to collect (`test_dlq_redaction`), and any consumer on workers is broken.
Fix: declared `tzlocal>=5.2` in the workers deps (`pyproject.toml.jinja`) + extended
`test_render_with_workers_battery_adds_celery_dep` to assert it. Verified end-to-end: workers render
→ uv lock+sync → `import demo.tasks` OK + `test_dlq_redaction` collects (7 tests). Master CI green on
merge (renders HEAD); ships a patch release so consumers get it via `framework upgrade`. Unblocks PR
#45 (FWK31) once it rebases onto this.

#### #0103 · completed · FWK31 · 2026-06-16
Diagnosed + interim-fixed the docker dev:lite acceptance collision (surfaced by Meridian's local
`task dev`). ROOT CAUSE: generated projects set no compose `name:`, so `docker compose -f
infra/compose/base.yml` derives project name from the dir → `compose` for EVERY project; the
acceptance tier and a consumer's `task dev` thus share container/network/volume names + host :8000.
The `test_…dev_lite_stack_serves_health` failure was its app booting against Meridian's reused
`compose-postgres-1` (never healthy → 90s timeout); worse, the test's `down -v` would DELETE the
shared `compose_pgdata` volume = Meridian's DB. Interim fix (no release): `_isolate_compose_project`
autouse fixture sets a unique `COMPOSE_PROJECT_NAME` (`swfwacc-<testname>`) per acceptance test —
picked up by `up` (`_compose_env` spreads os.environ) AND the bare `down` calls (inherited env), so
`down -v` is scoped to the test's own volume. Verified: serves_health now PASSES (32s, isolated
`swfwacc-…` stack). Opened FWK31 for the template-side fix (per-slug project name + parameterized
host port so two generated projects co-run; ships a release).

#### #0104 · completed · FWK31 · 2026-06-16
Brainstorm → design spec for the template-side compose isolation (scope confirmed: full
concurrency, two+ live stacks at once — UAT-in-browser + tests). Design: (1) `name: {{ project_slug }}`
in base.yml; (2) all 16 published host ports → `${<SERVICE>_HOST_PORT:-default}` (dev.yml 7 +
observability.yml 9); (3) a single `PORT_OFFSET` applied by `task dev` to shift all ports (one-knob
co-run); (4) acceptance tests set `*_HOST_PORT=0` + discover via `docker compose port` (ephemeral,
collide with nothing); (5) upgrade re-seed accepted (small seed DB; documented not migrated).
Constraint: NO `APP_` prefix on the port vars (app pydantic settings namespace). staging/prod deploy
untouched. Ships a patch release. Spec:
`docs/superpowers/specs/2026-06-16-fwk31-compose-isolation-design.md`. Next: writing-plans.

#### #0105 · completed · FWK31 · 2026-06-16
Implementation plan written (7 tasks, TDD). Design refinement during planning: the PORT_OFFSET knob
is a single `scripts/compose.sh` wrapper (exports all 16 `*_HOST_PORT` as default+offset unless set,
then execs `docker compose "$@"`) rather than 16+ arithmetic entries in the Taskfile — `task dev`
routes through it; tests bypass it by setting the env directly. App-port var is `HTTP_HOST_PORT` (NOT
`APP_HOST_PORT` — the pydantic settings namespace). Tasks: 1 name, 2 dev.yml ports, 3 observability
ports (9th is celery-exporter:9808, not otel-collector), 4 wrapper+Taskfile, 5 acceptance ephemeral
ports + `docker compose port` discovery, 6 two-stack co-run proof, 7 upgrade note + gate + review +
release. Plan: `docs/superpowers/plans/2026-06-16-fwk31-compose-isolation.md`. Next: execute.

#### #0106 · completed · FWK31 · 2026-06-16
Task 1 of 7 complete: added `name: {{ project_slug }}` as the first YAML key in
`src/framework_cli/template/infra/compose/base.yml.jinja` (after the leading comment block),
with a comment explaining the isolation benefit and that `COMPOSE_PROJECT_NAME` overrides it.
TDD: test wrote red (`name: demo` absent), template edit made it green (1 passed 1.43s).
Rendered compose validates (`compose config OK`). Ruff format+lint clean.

#### #0107 · completed · FWK31 · 2026-06-16
Task 2 of 7 complete: parameterized all 7 host-side ports in
`src/framework_cli/template/infra/compose/dev.yml.jinja` with `${VAR:-default}` form.
Vars: `HTTP_HOST_PORT:-8000`, `POSTGRES_HOST_PORT:-5432`, `TRAEFIK_HTTPS_PORT:-443`,
`TRAEFIK_HTTP_PORT:-80`, `MONGO_HOST_PORT:-27017`, `REDIS_HOST_PORT:-6379`,
`FRONTEND_HOST_PORT:-5173`. APP_-prefix ban confirmed (no `APP_HOST_PORT` or `APP_PORT` leaks).
Documented all 7 vars (+ `PORT_OFFSET`) in the FRAMEWORK region of
`src/framework_cli/template/.env.example.jinja`, battery-gated (`mongodb`/`redis|workers`/`react`
conditional vars). Placement: inside the framework region (consistent with existing non-APP vars
like `GRAFANA_ADMIN_PASSWORD`; no test forbids non-APP vars in that region).
TDD: test red → green (1 passed 1.59s). `docker compose config` validates. Ruff clean.

#### #0108 · completed · FWK31 · 2026-06-16
Task 3 of 7 complete: parameterized all 9 published host-side ports in
`src/framework_cli/template/infra/compose/observability.yml.jinja` with `${VAR:-default}` form.
Vars: `PROMETHEUS_HOST_PORT:-9090`, `GRAFANA_HOST_PORT:-3000`, `ALERTMANAGER_HOST_PORT:-9093`,
`LOKI_HOST_PORT:-3100`, `TEMPO_HOST_PORT:-3200`, `POSTGRES_EXPORTER_HOST_PORT:-9187`,
`MONGODB_EXPORTER_HOST_PORT:-9216` (mongodb battery), `CELERY_EXPORTER_HOST_PORT:-9808`
(workers battery), `REDIS_EXPORTER_HOST_PORT:-9121` (redis|workers battery). otel-collector
(internal, no host port) left unchanged. Extended the FWK31 block in
`src/framework_cli/template/.env.example.jinja` with the 9 obs vars (battery-gated where
applicable), placed adjacent to the dev port vars within the framework region. `docker compose
--profile dev config` validates cleanly; cross-file `depends_on` errors (pre-existing, caused by
splitof battery services across overlay+dev files) still occur without `--profile`. TDD: test
red → green (1 passed 1.57s). Full quality gate clean.

#### #0109 · completed · FWK31 · 2026-06-16
Task 4 of 7 complete: PORT_OFFSET wrapper (`scripts/compose.sh`) + Taskfile wiring.
Created `src/framework_cli/template/scripts/compose.sh` (plain `.sh`, no Jinja interpolation —
matches the `coverage.sh`/`load.sh` convention for static scripts). Wrapper exports all 16
`*_HOST_PORT` vars as `default+PORT_OFFSET` unless already set in the environment, then
`exec docker compose "$@"`. Unset `PORT_OFFSET` defaults to 0 (today's ports unchanged).
Modified `src/framework_cli/template/Taskfile.yml.jinja`: `dev` and `dev:lite` cmds now
call `./scripts/compose.sh` instead of `docker compose` directly; file-set, profiles, flags,
env (UID/GID), and preconditions unchanged. Offset proof: `PORT_OFFSET=100` produces
`published: "8100"` (HTTP) + `published: "5532"` (postgres) in `docker compose config`.
shellcheck clean. TDD: test red → green (1 passed). Full quality gate clean.

#### #0110 · completed · FWK31 · 2026-06-16
Follow-up fix to Task 4: `src/framework_cli/template/scripts/compose.sh` was stored in git as
mode 100644 (not executable). Copier preserves the source git file mode, so every rendered
project received a non-executable `scripts/compose.sh`, making `task dev` / `task dev:lite` fail
with "permission denied". Fixed via `git update-index --chmod=+x`. Added regression guard to
`tests/test_copier_runner.py::test_render_compose_wrapper_and_taskfile_use_offset`:
`assert os.access(wrapper, os.X_OK)`. Rendered mode now `-rwxr-xr-x` (confirmed). Test green.

#### #0111 · completed · FWK31 · 2026-06-16
Task 5: the acceptance docker-up tier (`tests/acceptance/test_rendered_project.py`) now binds
RANDOM host ports and discovers the assigned port at connect time, so a test stack never
collides with a live UAT/`task dev` stack or another test. Extended the autouse
`_isolate_compose_project` fixture to set all 16 `*_HOST_PORT=0` (docker → ephemeral) and
refreshed its docstring (FWK31 is now IMPLEMENTED). Added a `_compose_host_port(dest, files,
service, container_port)` helper that runs `docker compose <-f…> port <svc> <cport>` (under
`_compose_env()`, so it resolves the SAME monkeypatched COMPOSE_PROJECT_NAME stack) and parses
the trailing port from `0.0.0.0:NNNNN` / `[::]:NNNNN`.
Deviation — plan under-enumerated the affected tests: it claimed only 4 connect and that the
`*_leaves_no_root_owned_files` tests "do not connect." A grep audit found NINE connecting tests
that needed the port-discovery rewire (the blanket `=0` breaks every fixed `localhost:<port>`):
dev_lite_stack_serves_health (app:8000), dev_stack_routes_through_traefik (traefik:443 — only
the port swapped; TLS chain-verify + Host header untouched), dev_stack_prometheus_scrapes_app
(prometheus:9090), app_logs_reach_loki (app:8000 + loki:3100 — two discoveries),
traces_reach_tempo (app:8000 + tempo:3200), smoke_and_sniff_against_lite (app:8000 →
SMOKE/SNIFF/E2E_TARGET), dev_stack_serves_seeded_items (app:8000), dev_lite_stack_leaves_no_root
(app:8000 /health readiness — DOES connect, contra the plan), frontend_dev_stack_leaves_no_root
(frontend:5173 readiness — DOES connect). Only `test_rendered_workers_dev_stack_leaves_no_root`
needed NO edit: it waits on a filesystem path (`__pycache__` appearing in the bind mount), never
opens a socket. Verified by the real docker tier: `pytest -k "dev_lite_stack_serves_health or
routes_through_traefik or prometheus_scrapes or serves_seeded or logs_reach_loki or
traces_reach_tempo or smoke_and_sniff or leaves_no_root"` → 10 passed, 0 skipped (345s), all on
random host ports. ruff format + check clean.

#### #0112 · completed · FWK31 · 2026-06-16
Task 6: the end-to-end isolation proof. New acceptance test
`test_two_dev_lite_stacks_corun_without_collision` brings up TWO `dev:lite` stacks of the SAME
generated project concurrently under distinct compose project names (`swfwacc-corun-a`/`-b`),
asserts both serve `/health` at once, tears A down with `down -v`, and asserts B stays healthy
(isolated postgres volume). This is the definitive proof of the FWK31 claim: a per-slug compose
`name:` + parameterized `${VAR:-default}` host ports let two stacks of one project co-run on one
host without container/network/volume or port collision.
Refinement vs the plan's draft — the plan used FIXED host ports (8000/8100, 5432/5532). On this
dev box (and on a developer's box generally) a live consumer / `task dev` stack may already hold
8000/5432 — the very scenario FWK31 exists to solve — so fixed ports would flake. Instead added a
`_free_tcp_port()` helper (bind `:0`, read the OS-assigned port back, release) and gave each
stack its own OS-picked free HTTP + postgres ports, polling those. Collision-proof on both the
dev box and CI, and still proves the claim (distinct project names + distinct, non-colliding
host ports). The `lite` profile publishes BOTH the app (`${HTTP_HOST_PORT:-8000}:8000`) and
postgres (`${POSTGRES_HOST_PORT:-5432}:5432`), so both env overrides are live. The autouse
`_isolate_compose_project` fixture's `*_HOST_PORT=0` + COMPOSE_PROJECT_NAME are overridden by the
explicit per-stack `env=` dicts. Teardown is bulletproof: both `up` calls live inside the `try`
and the `finally` tears down both projects (an idempotent no-op on an already-removed / never-
created project), so A and B are always cleaned up on every exit path.
Verified by the real docker tier: `pytest ::test_two_dev_lite_stacks_corun_without_collision` →
1 passed (54s); post-run `docker ps -a`/`volume ls --filter name=swfwacc-corun` both empty (no
leaks). ruff format + check clean.

#### #0113 · completed · FWK31 · 2026-06-16
Task 7 Step 1: consumer-facing docs + upgrade re-seed note in generated README, with TDD guard.
Verified the deploy claim by reading staging.yml.jinja and prod.yml.jinja — both are
self-contained and do NOT reference infra/compose/base.yml (claim is accurate and safe).
Added `test_render_readme_documents_compose_isolation_and_upgrade` to tests/test_copier_runner.py;
confirmed RED (`PORT_OFFSET` not in rendered readme), then added two blocks to README.md.jinja:
(1) "Running a second stack" note in the Local stack section (PORT_OFFSET usage, per-project name
isolation, link to .env.example for full var list); (2) "Upgrading from an earlier release"
subsection explaining the base.yml compose name change from `compose` → `{{ project_slug }}`,
orphaned volumes, and re-seed steps (`task dev` + `task db:seed`). Confirmed GREEN (1 passed).
Render sanity: `{{ project_slug }}` interpolated correctly to `demo`, markdown headings intact.
ruff format --check + check clean. Files changed: src/framework_cli/template/README.md.jinja,
tests/test_copier_runner.py.

#### #0114 · completed · FWK31 · 2026-06-16
Fix review finding C1 (gate failure) + I1 (coverage-honesty gap) for scripts/compose.sh.
C1: `test_every_surface_is_classified` was failing because `script:scripts/compose.sh` was
unclassified in the FWK29 registry. I1: the existing wrapper test only did static string
checks, so the wrapper could not be classified EXERCISED.

Three changes: (1) Added `test_compose_wrapper_shifts_host_ports_by_offset` to
tests/test_copier_runner.py — renders the project, shims `docker` on PATH with a script that
dumps `env` to a capture file, then drives `./scripts/compose.sh up` three ways: PORT_OFFSET=100
(asserts HTTP_HOST_PORT=8100, POSTGRES_HOST_PORT=5532, GRAFANA_HOST_PORT=3100), PORT_OFFSET=100
with HTTP_HOST_PORT=9999 override (asserts override respected), and no offset (asserts
HTTP_HOST_PORT=8000). Test passes in 1.93s — the wrapper already worked. (2) Added
`script:scripts/compose.sh` to tests/runtime_coverage/registry.py as EXERCISED, evidence
= `test_compose_wrapper_shifts_host_ports_by_offset`, inserted before `script:scripts/coverage.sh`
(alphabetical). (3) Added a one-line overflow note to `src/framework_cli/template/scripts/compose.sh`
near the _p function noting that PORT_OFFSET pushing a port past 65535 will fail at bind time.

Verified: `pytest tests/runtime_coverage/ tests/test_copier_runner.py::test_compose_wrapper_shifts_host_ports_by_offset -q`
→ 10 passed (5.11s), EXIT=0; `test_every_surface_is_classified` now green. Shellcheck on the
rendered compose.sh: CLEAN. ruff format --check + check: CLEAN.
Files changed: tests/test_copier_runner.py, tests/runtime_coverage/registry.py,
src/framework_cli/template/scripts/compose.sh.

#### #0115 · completed · FWK31 · 2026-06-16
Cut release **v0.2.11** for the FWK31 compose-isolation template payload (per
release-cut-procedure, folded into PR #45 per the repo convention of shipping feature+release
in one PR). Bumped pyproject `0.2.10 → 0.2.11`, `DOGFOOD_COMMIT v0.2.10 → v0.2.11`
(src/framework_cli/dogfood.py), regenerated uv.lock (`framework-cli v0.2.10 → v0.2.11`).
Meta-plan/CLAUDE.md untouched (frozen — matches the v0.2.10 release commit's file set). Moved
FWK31 to PLAN Done. Pre-release gate green: ruff check + ruff format --check + mypy src clean;
full non-acceptance suite 920 passed / 3 skipped / 0 failed; docker acceptance tier (ephemeral
ports + two-stack co-run) green locally; render validation across baseline/all-batteries/
workers+react (default `compose config` OK, PORT_OFFSET=100 shifts to 8100). render-matrix
(`render-complete`) on the PR is the authoritative proof. Tag v0.2.11 → release.yml publishes
the GitHub Release; consumers re-seed local dev on upgrade (per-project compose name orphans
old `compose_*` volumes — documented in the generated README).

#### #0116 · completed · FWK33 · 2026-06-16
Durable fix for the recurring coverage-gap fixture GC race (the flake that failed the v0.2.11
release run's gate job: `test_realize_cached_builds_framework_shaped_base_for_coverage_gap`
raised `shutil.Error: .../.git/objects/XX: No such file or directory`). Root cause:
`realize_cached` copytrees a cached base once per fixture, and each cached base
(`_framework_base` for the framework-shaped coverage-gap path; the rendered base for the
others) was left with ~342 LOOSE git objects. A loose object that git packs/prunes mid-copy
makes copytree fail. `gc.auto=0` alone (already present on `_framework_base`) did not prevent it.

Fix (src/framework_cli/review/evals.py): added `_freeze_git_base(repo)` = gc.auto=0 +
`git repack -adq`, invoked after the base is built in BOTH cached-base sites. The copytree
source is then a stable packfile with zero loose objects. Deterministic guard
(tests/review/test_coverage_gap.py): `test_framework_base_is_packed_with_no_loose_objects`
asserts the loose-object count is 0 and in-pack > 0 (RED before fix: 342 loose; GREEN after).

Verified: flaky test looped 15x then all green; `tests/review/` 324 passed; ruff check + format
+ mypy src clean. Test/eval-infra only, no release. Branch `fwk33-coverage-gap-fixture-gc-race`
→ PR #47. Also updated the committed memory `_memory/flaky-realize-cached-copytree-git-gc-race.md`
(+ its MEMORY.md pointer): the earlier `gc.auto 0`-only guess was insufficient; record the
durable pack-the-base fix. See [[flaky-realize-cached-copytree-git-gc-race]].

#### #0117 · in-progress · FWK34 · 2026-06-16
Design spec for CLI/project version-sync, surfaced by Meridian (MDN26). Root cause traced this
session: `restore`/`integrity` render the canonical from the BUNDLED installed-CLI template
(`copier_runner.render_project`→`template_path()`), while `upgrade` renders from the git TAG
(`run_update(vcs_ref=…)`); correct only when `version_tag(installed)==project _commit`. Meridian
hit it (CLI v0.2.8, project upgraded to v0.2.11, git-Dockerfile fix shipped v0.2.10 → restore
renders no-git `bc8d37` ≠ lock `856fec`). Empirically disproved the initial "battery-unaware"
framing (`_answers` carries batteries; restore-equiv render reproduces the git Dockerfile
byte-for-byte). Brainstormed design (A out — rejected; C+B+`--version`): shared skew helper,
both-direction guard erroring in restore/integrity, `upgrade` assisted self-bump (uv-tool +
TTY → prompt → `uv tool install …@target` + re-exec; else refuse; `--bump-cli` forces),
`framework --version`. CI unaffected (generated `ci.yml` already pins `…@${_commit}`). Ships
v0.2.12. Spec committed: `docs/superpowers/specs/2026-06-16-fwk34-cli-version-sync-design.md`.
Branch `fwk34-cli-version-sync`.

Plan-time refinement (spec updated): `integrity` runs from generated Taskfile preconditions
(`task dev`/`task ci`) with the dev's GLOBAL CLI (only GitHub-CI pins `…@${_commit}`), so a
hard skew-error there would newly block `task dev` on benign cross-project skew. Resolved:
`restore` keeps the hard guard (it WRITES a wrong-version file), but `integrity` becomes
skew-aware ADVISORY — warns + exits 0 (never blocks) on skew, unchanged + authoritative when
in-sync/`--ci`. Implementation plan written (7 tasks, TDD, full code):
`docs/superpowers/plans/2026-06-16-fwk34-cli-version-sync.md`. Next: subagent-driven execution.

#### #0118 · completed · FWK34 · 2026-06-16
Task 1 — `framework --version`. Added an eager `--version` option on the Typer app callback
(`cli.py` `_version_callback` → `installed_framework_version()` + exit) + test
`test_version_flag_prints_installed_version`. Red→green; full `tests/test_cli.py` 121 passed;
ruff + mypy clean. (Implementer subagent hit a transient 529 after the edits but before the
commit; controller verified the work and finished the commit.)

#### #0119 · completed · FWK34 · 2026-06-16
Task 2 — `src/framework_cli/version_sync.py`: the pure skew helper (`VersionSkew`
IN_SYNC/CLI_BEHIND/CLI_AHEAD, `VersionSkewError`, `parse_version`, `project_version_skew`,
`skew_remedy`, `require_version_sync`) comparing `version_tag(installed_framework_version())`
to the project's `_commit`. 8 tests (truth table + missing-`_commit` + directional remedies +
parse). Red→green; ruff + mypy clean. (API overloaded for subagent dispatch — 529s — so the
controller implemented this fully-specified module directly per the plan; branch-end Opus
review still covers it.)

#### #0120 · completed · FWK34 · 2026-06-16
Task 3 — `restore` hard-guards on skew. `restore_file` calls `require_version_sync(project)`
right AFTER the integrity.lock existence check (so "not a framework project" keeps precedence)
and before any render; `cli.restore` adds `VersionSkewError` to its except. New test
`tests/integrity/test_restore_version_guard.py` (refuses + no render on CLI_BEHIND). Plan's
deferred verification resolved: the existing `_new_project` fixture renders from the LOCAL
template (Copier records no `_commit`), so the guard raised "no _commit"; fixed `_new_project`
to also `record_portable_source(dest, installed_framework_version())` (what `framework new`
does), making the fixtures in-sync. `tests/integrity/` + `tests/test_cli.py` = 166 passed;
ruff + mypy clean.

#### #0121 · completed · FWK34 · 2026-06-16
Task 4 — `integrity` is skew-aware ADVISORY (non-blocking). The `integrity` command computes
`project_version_skew` after the allow-drift path; on a skew (either direction) it prints a
warning naming the CLI/_commit mismatch + directional remedy and exits 0 (never blocks
`task dev`/`task ci`); unchanged + authoritative when in-sync and under `--ci` (CI pins the
CLI). A missing `_commit` surfaces as an error (exit 1). Two new tests in `tests/test_cli.py`
(non-fatal warning + `check_integrity` not run under skew; in-sync still runs the real check).
Verified no regression across integrity-command callers: test_cli + integrity_workers +
integrity/ = 170 passed; dogfood + downskill + review registry/framework_target = 75 passed;
ruff + mypy clean.

#### #0122 · completed · FWK34 · 2026-06-16
Task 5 — `src/framework_cli/self_bump.py`: the pure `decide_bump` policy (proceed when target
not newer / refuse non-uv-tool / bump on --flag / prompt on TTY / refuse non-interactive) +
`BumpDecision` + `BumpRefused`, and the I/O seams `is_uv_tool_install` (resolves the running
console-script under `uv tool dir`, fail-safe False on uncertainty), `run_uv_tool_install`,
`reexec`. 5 truth-table tests. Red→green; ruff + mypy clean. (Orchestrator `maybe_self_bump`
+ `_interactive`/`_confirm` land in Task 6 with the upgrade wiring.)

#### #0123 · completed · FWK34 · 2026-06-16
Task 6 — wired assisted self-bump into the `upgrade` command. Added `maybe_self_bump` +
`_interactive`/`_confirm` to `self_bump.py` (early-returns when target ≤ installed before any
I/O seam; prompt→confirm→install→reexec) and `installed_version_tag()` to `version_sync.py`.
The `upgrade` command gains `--bump-cli`, resolves the target up front (`to` or
`latest_release()`), builds an explicit re-exec argv (`[sys.argv[0], "upgrade", name, …]` —
CliRunner's sys.argv is pytest's), and calls `maybe_self_bump`; `BumpRefused` → exit 1.
Plan-vs-test reconciliations: the command reads the installed version THROUGH
`version_sync.installed_version_tag()` so the test's `vs.installed_framework_version`
monkeypatch lands; error assertions use `result.output` (repo convention mixes stderr).
3 new command tests (bump+reexec / refuse-non-uv / proceed-not-newer) + all 9 `test_upgrade.py`
green; existing tests call `upgrade_project` directly so no regression; ruff + mypy clean.

#### #0124 · completed · FWK34 · 2026-06-16
Branch-end reviews: spec-compliance (Sonnet) = all 8 points met, 190 passed; code-quality
(Opus) = APPROVE-WITH-NITS. Addressed the one Important finding + worthwhile nits:
(1) `version_sync.project_version_skew` now wraps `parse_version(commit_tag)` in
try/except→`VersionSkewError` — a non-tag `_commit` (copier-native SHA) previously raised a
raw `ValueError` that `integrity` (a `task dev` precondition) didn't catch → traceback,
violating "never blocks task dev"; (2) DRY: uses `installed_version_tag()`; (3)
`is_uv_tool_install` prefers the running `sys.argv[0]` over `which` (correct install
detection with two installs on PATH). + 4 regression tests (non-tag `_commit` → VersionSkewError;
integrity exits 1 cleanly on SHA `_commit`; integrity warns on CLI_AHEAD; upgrade errors when
`latest_release()` is None). FWK34 suites 194 passed; full non-acceptance suite (pre-fix) 941
passed/3 skipped; ruff + format + mypy clean.

#### #0125 · completed · FWK34 · 2026-06-16
Cut release **v0.2.12** for FWK34 (folded into the PR per convention). Bumped pyproject
`0.2.11 → 0.2.12`, `DOGFOOD_COMMIT v0.2.11 → v0.2.12`, regenerated uv.lock. Moved FWK34 to PLAN
Done. Verified the render-matrix interaction is safe: render-matrix scaffolds via `framework
new` (records `_commit = installed version`), so the new integrity guard sees IN_SYNC and
`framework integrity --ci` + `task ci` pass; the guard compares version strings, not tag
existence. Next: push → PR → required checks (gate/build/render-complete) → squash-merge → tag
v0.2.12 → release.yml.

#### #0126 · completed · FWK20 · 2026-06-17
New docker-gated acceptance test `test_rendered_workers_live_broker_dlq_and_beat`
(closes assessment H3+H4). Brings `postgres+redis+worker+beat` up `--profile dev`
(base+observability+dev merge, mirroring the no-root worker test) and proves the two
live round-trips the `task_always_eager` workers tests structurally can't:
(1) **DLQ** — injects a `@app.task(base=BaseTask, max_retries=0)` failing task into the
rendered `tasks.py` *before build* (baked into the image, registered via app.py's
`include`), enqueues it through the REAL redis broker from inside the worker container
(`compose exec worker python -c "...delay()"`), then polls `dead_letter_tasks` via
`compose exec postgres psql` until a row lands — exercising broker→worker→`on_failure`→DB.
(2) **beat** — polls `compose exec redis redis-cli GET demo:worker:heartbeat` (the liveness
marker the scheduled `heartbeat` task writes), proving beat→broker→worker, not just "beat
booted". Migrations: `APP_RUN_MIGRATIONS=false` on worker/beat, so the table is created by
`compose exec worker alembic upgrade head` (we don't start `app`). DB/redis queried via
`compose exec` (no host driver deps). FWK29 registry: `dev.yml:{worker,beat,redis}` →
EXERCISED naming this test; `services.yml:{worker,beat}` re-pointed FWK20→FWK19 (the
staging/prod overlay is consumer-target scaffolding no shipped target brings up; Correction
2026-06-16). `tests/runtime_coverage/` 9 passed.

#### #0127 · completed · FWK20 · 2026-06-17
The test went RED on a **real latent template bug** (systematic-debugging): beat exited (1)
on start with `[Errno 13] Permission denied: 'celerybeat-schedule'`. Root cause —
`PersistentScheduler` writes its schedule db to CWD `/app` (root-owned from the image's
`COPY --from=builder`), but dev `beat` runs as the host UID (`user: ${UID:-1000}…`, the
override that keeps bind-mounted `__pycache__` host-owned) → can't write → crash → **no
scheduled task ever fires in `task dev`** for any workers consumer. The old no-root test
missed it (only asserts the *worker's* `__pycache__`). Isolation confirmed it's beat-only: a
manual `heartbeat.delay()` set the redis key fine. Fix (dev-scoped, minimal): dev `beat`
command gains `--schedule=/tmp/celerybeat-schedule` (writable; schedule rebuilt from
schedule.py each boot, only last-run timestamps are ephemeral). prod/staging `services.yml`
beat runs as root → unaffected, left as-is. Added a CI-visible render guard to
`test_render_workers_compose_services` (the acceptance test is local-only/CI-ignored). Re-run
GREEN in 74s — the RED→GREEN on a real crash is the test's non-vacuity proof (à la FWK8); the
DLQ half is non-vacuous by construction (`dlq_count` init −1, only a real row sets it ≥1).
Verified: targeted render/parity/coverage 51 passed; ruff check + format clean.

#### #0128 · completed · FWK20 · 2026-06-17
Scope call (user): the dev-beat fix is template payload that ships to consumers, but **no
release** — there are no current celery consumers, so the patch release is deferred (lands in
a future template-change batch). Landed test + fix + registry on branch
`fwk20-workers-live-broker-dlq-beat`. Branch-end review + PR next.

#### #0129 · completed · FWK21 · 2026-06-17
Closed coverage gaps H5 + H6 (the "Docker target built but only returncode==0
asserted" shape) via Approach A (standalone, DB-less). Brainstormed (user picked A +
extend-react/new-claudesub structure) → plan doc `docs/superpowers/plans/2026-06-17-fwk21-battery-docker-runtime.md`
→ inline execution. Shared helper `_run_image_serving(image, *, extra_env=None,
ready_path="/heartbeat")` in test_rendered_project.py: `docker run -d` on a `_free_tcp_port()`
host port with `APP_RUN_MIGRATIONS=false` (entrypoint skips alembic/seed → uvicorn boots
DB-less; verified every Settings field defaults + lifespan "must not require the DB"), polls
ready_path until 200, yields the base URL, `docker rm -f` in finally, raises with `docker logs`
on not-ready. **H5** new `test_rendered_claudesubscriptioncli_docker_runtime_serves_heartbeat`:
build DEFAULT (runtime) target + run → /heartbeat 200 proves the runtime image boots with
litellm-claude-cli importable (create_app calls register_claude_cli(); the git dep reaches
runtime only via COPY --from=builder, distinct from the builder-stage test). **H6** extends
test_rendered_react_battery_passes: run demo-react:ci → GET / asserts `id="root"` in the served
body (Vite preserves the root div in dist/index.html), proving /app/frontend/dist landed + is
served by the StaticFiles mount. Both green (H5 55s, H6 43s, together 54s).

#### #0130 · completed · FWK21 · 2026-06-17
Bite-proofs (non-vacuity). H5: temp `ready_path="/definitely-not-a-route"` → RED ("did not
serve … within 60s" + docker logs), proving the readiness gate depends on the real response;
reverted. H6: temp `extra_env={"APP_SERVE_SPA": "false"}` (settings gate
`serve_spa and _dist.exists()` in main.py) → app boots (/heartbeat 200, vitest 5 passed) but
GET / → HTTP 404 → RED, proving the assert depends on the SPA actually being SERVED (build
green ≠ served); reverted. FWK29 registry: `docker-stage:Dockerfile:frontend-build` → EXERCISED
(test_rendered_react_battery_passes); `service:dev.yml:frontend` re-pointed KNOWN_GAP → FWK24
(the standalone runtime-image run exercises the prod StaticFiles mount, NOT the dev Vite
dev-server compose service — a different surface; the dev-server live-serve folds into the react
live-frontend work). H5 flips no entry (runtime stage already EXERCISED; litellm-claude-cli is a
Python dep, not an enumerable operational surface). runtime_coverage 9 passed; ruff + format clean.

#### #0131 · completed · FWK21 · 2026-06-17
Branch-end Opus review (code-quality + spec): APPROVE-WITH-NITS. Source-level trace confirmed
both checks non-vacuous (H5: runtime installs no git, dep arrives only via COPY --from=builder,
/heartbeat dep-free, APP_RUN_MIGRATIONS=false skips entrypoint.sh DB work; H6: SPA mount gated on
serve_spa+_dist.exists, id="root" Vite-preserved) and all four registry decisions correct. Nits:
the inner `assert resp.status == 200` lines are dead (urllib raises HTTPError on non-2xx first) —
accepted as defensive/symmetry per the reviewer. Landed on branch `fwk21-battery-docker-runtime`.
No release (test-only). PR next.

#### #0132 · completed · FWK19/23/24/25/26/27/28 · 2026-06-17
Authored the remaining coverage-batch plans (the med/low half of the FWK18 inventory) for an
unattended overnight run on the laptop. A shared execution-policy doc
(`2026-06-17-coverage-batch-execution-policy.md`) encodes the operating rules settled with the
user: hardest-first order (FWK24→23→26→25→19→27→28); ONE batch branch `fwk-coverage-batch`,
≥1 commit/item (commit-often for safety), controller skip-marker per commit + one branch-end
Opus review; real-bug policy = root-cause → small+obvious+scoped fix inline (+CI guard) else
`xfail(strict=True)` + keep registry KNOWN_GAP, and EVERY real bug also gets an ACTION_LOG entry
+ a NEW PLAN.md Next entry + a morning-report line; NO release (test-only; any forced template
fix deferred — no consumers); laptop docker-parity + TMPDIR notes; no real API keys by default
(fork 2A). Per-item plans (each a placeholder-free spec+plan matching the FWK21 doc shape,
authored inline + via sequential subagents, controller-reviewed): FWK24 (per-battery live routes
through Traefik via a new `_traefik_request`/`_traefik_ws_upgrade`; forks 1A combined-render +
2A reachability+error+metric; `/ws`=101-upgrade, graphql=assert-dev-behavior, webhook-secret via
merge-override), FWK23 (obs live: self-scrape/rules/grafana in one bring-up, battery-variant
exporters, alertmanager→capture-server, worker OTEL→Tempo by span-name; 8 registry flips),
FWK26 (M1 redirect+M2 mongo health one stack, M4 hot-reload via /heartbeat literal, M14
framework-side engine pre-ping/dispose — no template change), FWK25 (gate-tier ci-graph assert +
`task dev:lite`/`db:migrate`/`db:seed` live), FWK19 (CI-visible staging/services config-validation
+ test.yml live tmpfs-reset; ~11 registry flips), FWK27 (.claude gate hook via PATH-stub +
PreToolUse payload, mirrors `_run_hook`), FWK28 (notify.sh smoke + load.sh graceful-degradation
+ docs.yml mike workflow-graph assert). Keys location recorded in native memory. Registry-key
cross-check: the keys each plan flips all exist. Delivering as a planning PR for review; the
laptop run executes from these. Stopped after the plans per the user.

#### #0133 · completed · FWK19/23/24/25/26/27/28 · 2026-06-17
Adversarial hands-free verification pass (7 parallel read-only agents, one per plan) cross-checking
every plan against the actual code: registry keys exist + EXERCISED evidence names a test the plan
defines; referenced helpers/anchors exist; no step needs an absent tool/key/interactive input. Found
**3 BLOCKERS** (would have stalled the unattended run) + warns; all fixed in the plan docs:
(1) **FWK24** Task-2 `skipif` only gated docker → on a non-parity laptop the `mkcert`/`task` calls
ERROR (not skip) → added `shutil.which("mkcert")/("task") is None` guards (mirrors the existing
Traefik test). (2) **FWK27** `render_project` does NOT git-init, so the hook's `git rev-parse
--show-toplevel` resolves to the framework repo (vacuous pass) or `|| exit 0` fires (FAIL case never
hits exit 2 → RED) → `_run_gate_hook` now `git init`+add+commit's `dest`; prose corrected. (3)
**FWK28** webhook test's `.replace()` chain had 2 strings not matching `notify.sh` → produced a bash
syntax error → replaced with a robust line-based uncommenter (strip leading `# ` across the block) +
a sanity-assert. Warns fixed: FWK24 WS nonce → 16 bytes; FWK27 dropped redundant in-func `import os`;
FWK25 port-poll `except` += `IndexError`; FWK26 corrected a misstated helper precondition; FWK28
placement note + the false-alarm `load.js` anticipated-bug (verified present). Net: FWK23/25/26/19
verifiers returned READY; FWK24/27/28 NEEDS-FIX → now fixed. Plans are hands-free-ready. PR #51 updated.

#### #0134 · completed · coverage-batch · 2026-06-17
Added an explicit "escape hatch — NEVER block on the human (park-and-continue)" section to the
shared execution-policy doc (per user): if a step would need my *permission* (outward-facing /
hard-to-reverse) or my *input* (an unresolvable design fork / ambiguous real-bug fix), the run does
NOT ask or wait — it parks ONLY that unit (xfail(strict)/skip + reason "PARKED: …", registry stays
KNOWN_GAP), commits what's done, finishes the rest of the current item that doesn't need me, and
moves to the next. Generalizes the real-bug rule (now cross-references it); the sole intended
permission gate is the terminal batch-PR-for-review. Morning report gains a dedicated "PARKED —
needs my decision/permission" to-do list. PR #51 updated.

#### #0135 · completed · coverage-batch · 2026-06-17
Added a "Transient Claude API / safety-classifier unavailability — RETRY, never fail" rule to the
shared policy (per user): a Claude API / auto-mode error ("auto mode cannot determine the safety of
Bash … <model> temporarily unavailable") is transient infrastructure, NOT a decision point — the run
does NOT fail/park/skip; it waits ~60s and retries the same action at 1-minute intervals
indefinitely until it works, then resumes. No give-up timeout. Kept distinct from the escape hatch
(human-decision park) and noted the separate full-quota-outage case (cron, not in-session sleep). PR #51 updated.

#### #0136 · completed · FWK35 · 2026-06-17
`task doctor works for templates, but not for the framework` (user). The template ships every
generated project a `task doctor` host-tool preflight (`scripts/doctor.sh.jinja`), but the
framework repo's own `Taskfile.yml` had only `test`/`lint`. Added `scripts/doctor.sh` +
a `doctor:` target mirroring the template's pattern (presence-only, advisory, set -uo pipefail,
✓/✗, exit 1 on any miss) but checking the framework's FULL host tool set — confirmed via
`grep` that the suite shells out to docker ×75 / node ×8 / npm ×4 / mkcert ×3 / task ×2 /
shellcheck ×2 — so: docker, docker compose, docker buildx, uv, git, task, mkcert, node, npm,
shellcheck (superset of the template's, which gates node on the react battery). Wired as the
laptop overnight-run preflight in the coverage-batch policy ("Preflight first: run `task doctor`")
+ a callout in `laptop-dev-parity.md` (that doc was scoped to the minimal reviewer-eval path;
the full acceptance/coverage-batch run needs the whole set). Regression test
`tests/test_framework_doctor.py` (target present + `doctor.sh` bash-n-clean + checks each tool).
Verified: `shellcheck scripts/doctor.sh` clean, `task doctor` 10/10 green on this box, test 2
passed, ruff clean. Framework dev tooling only → no release, no template payload, no FWK29 surface
(enumerate runs on a rendered project, not the framework's own scripts/). Branch fwk35-framework-doctor.

#### #0137 · completed · coverage-batch · 2026-06-17
**FWK24** (item 1/7 of `fwk-coverage-batch`) — per-battery live routes through Traefik +
react RUM. Three docker-gated acceptance tests in `test_rendered_project.py`, all GREEN +
bite-proven: `test_rendered_per_battery_routes_through_traefik` (M8 — all-6-battery render up on
`--profile dev`, asserts WS /ws 101, webhook HMAC 200/401, graphql 200, llm/agents 502 + metric
series through Traefik; bite: flip bad-sig→200 RED), `test_rendered_react_rum_round_trip` (M9 —
runs the shipped `test_frontend_rum.py`; bite: bogus path→exit4 RED), and
`test_rendered_frontend_dev_server_serves_spa` (Vite dev server serves `id="root"`; bite:
impossible marker RED). Added shared Traefik helpers `_mkcert_ssl_context`/`_traefik_request`/
`_traefik_ws_upgrade` (FWK8 TLS recipe) reused by later items. FWK29 registry:
`service:dev.yml:frontend` → EXERCISED.
**Real bug found + FIXED (defer release → FWK36):** the `websockets` battery `/ws` route 404s
live — `uvicorn` installed without a WebSocket lib (`No supported WebSocket library detected`).
Fix: conditional `websockets>=14` in `pyproject.toml.jinja` + a CI-visible render guard
(`test_render_with_websockets_battery` asserts the dep; new negative guard for the no-battery
case). Bite-proven RED→GREEN by stashing the template fix. Small/obvious/scoped → applied per the
real-bug policy; release deferred (no consumers gated in this run). Subagent-driven (Sonnet
implementer; controller review + commit). No release.

#### #0138 · completed · coverage-batch · 2026-06-17
**FWK23** (item 2/7) — observability live exercise. Four docker-gated acceptance tests in
`test_rendered_project.py`, all GREEN + bite-proven, + a `_poll_json(url,*,timeout,predicate)`
helper: `test_rendered_obs_stack_self_scrape_rules_and_grafana` (M10-baseline prometheus +
otel-collector self-scrape up==1, M11 5 rule groups loaded, M13 Grafana health + datasources
{prometheus,loki,tempo} provisioned + dashboards; bite: phantom job → poll timeout RED),
`test_rendered_obs_exporter_targets_up` (M10 postgres/redis/celery/mongodb exporters up==1 in one
workers+redis+mongodb bring-up; bite: phantom job RED), `test_rendered_alertmanager_routes_webhook`
(M12 firing alert → in-process webhook receiver; bite: wrong receiver RED),
`test_rendered_worker_span_reaches_tempo` (M7 CeleryInstrumentor span `run/demo.tasks.tasks.heartbeat`
reaches Tempo via TraceQL `{ name =~ "run/.*heartbeat.*" }`, strictly narrower than the app
service.name; bite: nonexistent-route filter → poll timeout RED). FWK29 registry: 8 KNOWN_GAP →
EXERCISED (otel-collector, postgres/redis/celery/mongodb-exporter, alertmanager, grafana ×2).
Two **test-design adjustments** (NOT template bugs, no fix/release): Grafana 11.3.0's Tempo
datasource plugin doesn't implement the `/health` API (404 "Method not implemented") → probe
Tempo's own `/ready`; and `base+observability` without `dev.yml` fails compose dep-validation
(postgres is dev.yml-profile-gated by design) → include `dev.yml --profile dev`. Subagent-driven
(Sonnet; controller review + commit). No release.

#### #0139 · completed · coverage-batch · 2026-06-17
**FWK26** (item 3/7) — dev-loop / service-health. Three docker-gated acceptance tests in
`test_rendered_project.py`, all GREEN + bite-proven, no template bugs:
`test_rendered_dev_stack_http_redirect_and_mongo_health` (M1 Traefik :80 → https redirect; M2 mongo
compose service polled to `healthy` + mongosh ping through the running service; bites: redirect
`http://`→RED, `not healthy`→RED), `test_rendered_dev_lite_hot_reload_picks_up_edit` (M4 edit
rendered `health.py` on the bind mount → `--reload`+WATCHFILES polling serves the sentinel within
90s; bite: poll for an unwritten sentinel → timeout RED — the naive "still OK" bite was caught as a
false-pass and replaced), `test_rendered_db_engine_pool_pre_ping_and_dispose` (M14 drives the
shipped module-level `demo.db.engine` in the project venv: SELECT 1 → `pg_terminate_backend` the
pooled backend → pre-ping recovers → `dispose_engine()` replaces the pool; kept the
`engine.pool is not pool_before` assertion form — `dispose(close=True)` swaps in a fresh pool; bite:
skip `dispose_engine()` → RED). Driver care: open the killer connection while the first is still
checked out so the pool allocates a distinct backend (else it reuses the pid and kills itself).
FWK29 registry: `service:dev.yml:mongo` → EXERCISED. M1/M4/M14 have no registry keys. Subagent-driven
(Sonnet; controller review + commit). No release.

#### #0140 · completed · coverage-batch · 2026-06-17
**FWK25** (item 4/7) — Taskfile targets through the `task` runner. Four tests, all GREEN +
bite-proven, no template bugs. Gate-tier (`test_copier_runner.py`):
`test_render_ci_task_chain_and_85_percent_gate` — YAML-parses the rendered Taskfile, asserts
`ci.cmds` order (lint → test:cov:ci → audit → openapi:export) + the 85 coverage threshold + the
`framework integrity` precondition (bite: `85`→`99` RED). Docker-gated (`test_rendered_project.py`):
`test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock` (M5 negative — no uv.lock →
`task dev:lite` exits non-zero with the uv-sync message; this IS the positive test's bite-proof),
`test_rendered_taskfile_dev_lite_target_drives_stack` (M5 positive — `task dev:lite` Popen → poll
/health 200 on the ephemeral port → `docker compose down -v`),
`test_rendered_taskfile_db_targets_seed_rows` (M6 — postgres up, `task db:migrate` rc0, `task db:seed`
rc0 with `APP_DATABASE_URL` injected via env, `items` row count > 0 via `compose exec psql`; bite:
`>0`→`==0` RED). Neither fork bit: `_compose_host_port` resolved the dev:lite port promptly, and
pydantic-settings env-precedence carried `APP_DATABASE_URL` into `db:seed`. No registry flips (Taskfile
targets are out of FWK29 scope). Subagent-driven (Sonnet; controller review + commit). No release.

#### #0141 · completed · coverage-batch · 2026-06-17
**FWK19** (item 5/7) — non-dev compose overlays config-validated + test.yml live. Three tests, all
GREEN + bite-proven, no template bugs. Gate-tier (`test_copier_runner.py`, CI-visible,
`skipif docker absent`): `test_staging_standalone_merges` (H7 — staging.yml `docker compose config`
for baseline + timescaledb; bite: assert a nonexistent service → RED) and
`test_staging_plus_services_overlay_merges` (H2 — staging+services batteries-on merge validates;
bite: `worker in` the bare no-battery merge → RED). Acceptance (`test_rendered_project.py`):
`test_rendered_test_profile_stack_serves_and_resets_db` (M3 — test.yml `--profile test` up→/health,
capture postgres-test container ID; `down -v`; re-up → assert a NEW container ID proves the tmpfs
ephemeral DB reset; PICKED forks: ephemeral `fwk19.override.yml` port file + container-ID-delta
proof; bite: `cid2\!=cid1`→`==`→RED). FWK29 registry: 11 KNOWN_GAP → EXERCISED (overlay:{services,
staging,test}.yml; services.yml:{beat,mongo,redis,worker}; staging.yml:{app,postgres};
test.yml:{app,postgres-test}); completeness guard green. Confirmed celery-exporter present,
staging `${POSTGRES_PASSWORD:?}` + services battery-conditional YAML well-formed. Subagent-driven
(Sonnet; controller review + Half-A re-run + commit). No release.

#### #0142 · completed · coverage-batch · 2026-06-17
**FWK27** (item 6/7) — generated-project `.claude` review-gate hook. Three acceptance tests in
`test_rendered_project.py` (no docker / no uv-sync / no API key — PATH-stubs the `framework` binary,
pipes PreToolUse JSON into the hook), all GREEN + bite-proven, via a `_run_gate_hook(dest, payload,
stub_exit_code, marker_verdict=None)` helper that git-inits `dest` first (mandatory — the hook's
toplevel resolution must point at `dest` for marker.json):
`test_rendered_gate_hook_blocks_on_fail_marker` (M15 — commit-payload + FAIL stub → hook exits 2;
bite: `==2`→`==0` RED), `test_rendered_gate_hook_passes_on_pass_marker` (PASS stub → exit 0),
`test_rendered_gate_hook_skips_non_commit` (`ls` payload → grep guard short-circuits → exit 0; bite:
`==0`→`==2` RED). The plan's flagged candidate bug (grep guard vs the JSON-embedded payload on stdin)
is NOT a bug — the guard matches the `"`-preceded token correctly. FWK29 registry:
`hook:.claude:reviewers-gate-check.sh` → EXERCISED. Subagent-driven (Sonnet; controller re-ran all
3 + finished). No release.

#### #0143 · completed · coverage-batch · 2026-06-17
**FWK28** (item 7/7) — seam/script smoke + workflow-graph asserts. Four tests, all GREEN +
bite-proven, no template bugs. Gate-tier (`test_copier_runner.py`, no docker):
`test_notify_seam_exits_zero_and_echoes` (L1 — `notify.sh` exits 0 + echoes `[deploy notify]…`;
bite: wrong string RED), `test_notify_seam_posts_to_webhook` (L1 — string-replace-uncomment
approach A activates the webhook block, POSTs to an in-process capture server; `assert
_FakeNotify.posts` guards a silent no-op), `test_docs_workflow_mike_flags` (L3 — `yaml.safe_load`
docs.yml asserts `mike deploy --push --update-aliases` + `mike set-default` + the `v`-prefixed tag
trigger; bite: nonexistent flag RED). Acceptance (`test_rendered_project.py`, docker + grafana/k6
image): `test_load_sh_fails_gracefully_without_docker_target` (L2 — unreachable `K6_TARGET` on a free
port, `K6_DURATION=1s`/`K6_VUS=1`; asserts non-zero exit via `set -euo pipefail` — graceful
degradation ONLY, NOT full SLO pass; bite: `\!=0`→`==0` RED). FWK29 registry: `script:infra/deploy/
notify.sh` → EXERCISED; `script:scripts/load.sh` stays KNOWN_GAP with honest evidence (full k6 SLO
pass/fail needs a live app stack); `job:docs.yml:publish` untouched (exempt). Subagent-driven
(Sonnet; controller review + gate-tier re-run + finish). No release.

#### #0144 · completed · coverage-batch · 2026-06-17
**Branch-end review + PR** for `fwk-coverage-batch`. One Opus whole-branch code-quality +
spec-compliance review (review-model policy): verdict **APPROVE-WITH-NITS**, no blocking findings —
confirmed no false-EXERCISED flips (all 21 KNOWN_GAP→EXERCISED name a real test that genuinely
exercises the surface live; load.sh correctly stays KNOWN_GAP; docs.yml:publish untouched), tests
non-vacuous, teardown sound, the websockets fix + CI guard correct, and the two FWK23 test-design
adjustments legitimately not masking template bugs (M13 datasource provisioning still asserted).
Applied nit #1: hardened `test_load_sh_fails_gracefully_without_docker_target` to assert a k6 run
marker (`connection refused`/`http_req` in output) so a docker-pull failure can't pass for the
wrong reason. Nits #2 (cosmetic conjunction assertion) and #3 (inherent first-boot timeout flake)
accepted as-is. Full verification: gate-tier pytest 954 passed / 3 env-skips; all new batch tests
run together = 25 passed + 1 transient ghcr.io TLS-handshake pull flake on
`test_rendered_worker_span_reaches_tempo` (re-ran → GREEN; [[render-matrix-dockerhub-flake-triage]]);
ruff/format/mypy clean. No release (test-only; the websockets template fix is deferred → FWK36).

#### #0145 · amended · 2026-06-17
Reconciled the CLAUDE.md "Operating environment" bullet with reality, found during the
fwk-coverage-batch overnight run (#53). The doc claimed this box ships native Node 22 + docker
buildx + shellcheck in `~/.local/bin` and a 16 GB `/tmp`; in fact only `uv`/`claude` were
preinstalled, and the acceptance toolchain had to be apt-installed (docker.io 29.x + compose-v2 +
buildx, node 22/npm, mkcert + libnss3-tools, shellcheck) plus go-task 3.51.1 to `/usr/local/bin`.
Corrected: distro Ubuntu 26.04/WSL2/systemd; no host k6 (grafana/k6 image); docker-group needs a
fresh login; `/tmp` is a ~4 GB tmpfs → `TMPDIR=/var/tmp`; sandbox must be disabled for
docker/acceptance; `task doctor` is the preflight; ghcr.io/Hub pull timeouts are flakes. Doc-only.

#### #0145 · completed · housekeeping · 2026-06-17
Post-batch tidy. PLAN.md: removed the now-complete `FWK19–FWK28` umbrella line from `Next` and
added a consolidated `Done` entry for the coverage batch (all 7 items GREEN, 21 registry flips,
the websockets bug → FWK36, Opus APPROVE-WITH-NITS, merged #53 `f1ac8b9`); re-pointed FWK36's
"shipped on fwk-coverage-batch" → "on master (merged #53)" since the branch is gone. Pruned the
two stale remote branches (`fwk-coverage-batch`, `fwk20-workers-live-broker-dlq-beat`) — both
PRs confirmed MERGED (squash, so not literal ancestors) before deleting; origin now has only
`master` + `gh-pages`. Docs/state only → no release.

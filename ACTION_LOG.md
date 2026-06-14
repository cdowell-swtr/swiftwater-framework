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

# Review-Agent Eval Harness (Plan 7d) — Design Spec

**Date:** 2026-05-23
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 7a (the `run_agent(diff, spec, client)` runner + `Finding`/`Severity`/`severity_rank` contract + `default_client()`), 7b (the full agent registry + `AgentSpec.block_threshold` + `agent_names()`), 7c (the aggregator). Realizes framework design spec §20 "The Review Agents — Eval Tests". Fourth and final sub-project of Plan 7.

---

## 1. Purpose & scope

The review agents are exercised in tests only with a **mocked** client — nothing yet runs a real Anthropic call or asserts that an agent actually *catches a planted defect*. Plan 7d adds the eval harness §20 calls for: each agent gets **golden fixtures** — known-bad diffs it must flag (true positives) and known-good diffs it must pass (no false positives) — and, because LLM output is non-deterministic, evals assert **detection against a pass threshold**, not exact match. Evals run **on a schedule and whenever an agent's prompt or logic changes**.

**In scope:**
- A pure, hermetically-tested **scorer** (`src/framework_cli/review/evals.py`): fixture discovery, the detection rule, set-level recall/precision scoring against thresholds.
- A **`framework eval`** CLI command that runs fixtures through the real `run_agent`, scores them, prints a per-agent scorecard, and exits non-zero on a threshold miss.
- **Golden fixtures** for all 12 current agents: 2-3 known-bad + 1-2 known-good each.
- A framework-repo **`agent-evals.yml`** workflow (schedule + on agent/logic change).
- **Extensibility**: the harness is registry + convention driven, so adding an agent (core or battery) needs no harness code change.

**Out of scope (deferred):**
- The 3 battery agents' fixtures (`api-design`/`accessibility`/`usability`) → **Plan 8**, when those agents land (they'll be auto-evaluated once registered + given fixtures — no harness change).
- Wiring evals into the framework's *full* dogfooding CI alongside lint/CLI-tests/render-matrix → **Plan 9**.

## 2. Decisions (settled in brainstorm)

- **Scoring = set-level recall/precision** (one real call per fixture; per agent, recall over its bad fixtures must be ≥ `RECALL_MIN`, false-positive rate over its good fixtures must be ≤ `FP_MAX`). Cheapest, measures real quality, tolerant of a single flaky miss.
- **Detection = file + blocking severity.** A bad fixture is *detected* when the agent returns a finding on the seeded file at/above its `block_threshold`; a good fixture *passes* when the agent produces no blocking finding.
- **CLI + scorer + workflow** — a `framework eval` command over a pure scorer module, plus a scheduled/on-change workflow in the framework repo.
- **All 12 agents, 2-3 bad + 1-2 good fixtures each.**
- **Registry + convention driven** — `framework eval` iterates the registry (`agent_names()`); an agent is evaluated when it has a fixtures directory. No hardcoded agent list; adding an agent = register it + author fixtures.

## 3. Fixtures

**Layout** (the agent is the parent directory, the kind is the subdirectory):
```
tests/eval/fixtures/<agent>/bad/<slug>.diff          # known-bad: the agent MUST flag
tests/eval/fixtures/<agent>/bad/<slug>.expect.json   # {"file": "path/seeded/in/the/diff.py"}
tests/eval/fixtures/<agent>/good/<slug>.diff         # known-good: the agent must NOT block
tests/eval/fixtures/thresholds.yaml                  # optional per-agent overrides (see §4)
```
- `<agent>` is the registry key (`security`, `data-integrity`, …), not the `review-` prefixed name.
- Each `.diff` is a real unified diff (the `+++ b/<path>` shape `run_agent` consumes — `diff.changed_files` parses it).
- A **bad** fixture's sidecar `<slug>.expect.json` names the **seeded file** (the path the detection rule matches against). Good fixtures need no sidecar.
- Fixtures are framework-internal dogfooding content under `tests/` — **not shipped in the wheel** (the wheel packages only `src/framework_cli`).

**Authoring guidance (for the plan):** each bad fixture seeds exactly one defect in the agent's domain, severe enough to clear the agent's block threshold (e.g. `data-integrity`: a write without a transaction; `security`: a string-formatted SQL query; `observability`: a new code path with no log/span). Each good fixture is a clean diff in the same domain that should *not* trip the agent (so it exercises false-positive resistance).

## 4. The scorer — `src/framework_cli/review/evals.py`

Pure, no I/O beyond reading fixture files in `load_fixtures`; **no network**. Reuses `Finding`, `severity_rank` (findings.py) and `AgentSpec.block_threshold` (registry.py).

- **`Fixture`** (frozen dataclass): `agent: str`, `kind: Literal["bad", "good"]`, `name: str`, `diff: str`, `seeded_file: str | None` (set for `bad`).
- **`load_fixtures(root: Path) -> list[Fixture]`** — discover `<root>/<agent>/bad/*.diff` and `<root>/<agent>/good/*.diff`; for each bad diff read its sibling `<slug>.expect.json` for `seeded_file`. A malformed/missing sidecar on a bad fixture, or an unreadable diff, is **skipped with a warning** (never crashes). Returns fixtures sorted by (agent, kind, name) for determinism.
- **`flags(findings: list[Finding], spec: AgentSpec, *, file: str | None = None) -> bool`** — the single shared notion of "the agent raised a blocking concern": for a blocking agent (`block_threshold` set), True iff some finding (optionally restricted to `file`) has `severity_rank(f.severity) >= severity_rank(block_threshold)`; for an **advisory** agent (`block_threshold is None` — `documentation`, `dependency`), True iff some finding exists (any severity) on that scope. (Advisory agents never block in production, so their evals score on *surfacing* rather than blocking.)
  - **bad fixture detected** = `flags(findings, spec, file=fixture.seeded_file)`.
  - **good fixture passes** = `not flags(findings, spec)` (no file restriction).
- **`Thresholds`** (frozen dataclass): `recall_min: float`, `fp_max: float`. `DEFAULT_THRESHOLDS = Thresholds(recall_min=0.67, fp_max=0.34)`.
- **`load_thresholds(path: Path | None) -> dict[str, Thresholds]`** — parse the optional `thresholds.yaml` (`{<agent>: {recall_min: .., fp_max: ..}}`); missing file → `{}`. Agents absent from it use `DEFAULT_THRESHOLDS`.
- **`AgentScore`** (frozen dataclass): `agent: str`, `recall: float`, `fp_rate: float`, `bad_total: int`, `good_total: int`, `passed: bool`, `reason: str` (empty when passed, else e.g. `"recall 0.33 < 0.67"`).
- **`score_agent(agent: str, bad_detect_rates: list[float], good_block_rates: list[float], thr: Thresholds) -> AgentScore`** — `recall = mean(bad_detect_rates)` (1.0 if the agent has no bad fixtures), `fp_rate = mean(good_block_rates)` (0.0 if none); `passed = recall >= thr.recall_min and fp_rate <= thr.fp_max`. Pure — the per-fixture *rates* are computed by the command (running the agent, see §5); the scorer only does the arithmetic + threshold comparison.

With `--repeat 1` (default), each per-fixture rate is 0.0 or 1.0, so `recall` is exactly "fraction of bad fixtures detected" and `fp_rate` is "fraction of good fixtures that blocked" — the set-level rates. `--repeat N` makes each rate `hits/N`, smoothing non-determinism.

## 5. The `framework eval` command (`cli.py`)

`@app.command(name="eval")` → `eval_agents(agent: str = Argument("", ...), fixtures: str = Option("tests/eval/fixtures", "--fixtures"), repeat: int = Option(1, "--repeat"), require_fixtures: bool = Option(False, "--require-fixtures"), require_key: bool = Option(False, "--require-key"))`.

Flow:
1. If no `ANTHROPIC_API_KEY`: if `--require-key` → error + exit 1 (CI misconfiguration must be loud); else print `eval: skipped (no ANTHROPIC_API_KEY)` + exit 0 (mirrors `review`).
2. `load_fixtures(Path(fixtures))`, group by agent.
3. The agent set to evaluate = `agent_names()` (the registry) — or just `[agent]` when the positional `agent` is given (used on a single-prompt change). For each agent **with fixtures**: for each fixture, call `_eval_run(fixture.diff, spec)` (a module-level seam wrapping `run_agent(diff, spec, default_client())`, monkeypatchable in tests) `repeat` times, compute the per-fixture detect-rate (bad) / block-rate (good) via `flags`, then `score_agent(...)` with the agent's thresholds.
4. **Coverage reporting:** a registered agent with **no** fixtures → listed as `no fixtures (skipped)` (warning, not a failure) unless `--require-fixtures` (then it's a failure). A fixtures directory with no matching registry agent → warning (typo guard).
5. Print a scorecard (one line per agent) + a summary; **exit 1** if any evaluated agent failed its thresholds (or any coverage failure under `--require-fixtures`), else exit 0.

Scorecard:
```
review-security        recall 3/3 (1.00)  fp 0/2 (0.00)   PASS
review-data-integrity  recall 1/3 (0.33)  fp 0/2 (0.00)   FAIL (recall 0.33 < 0.67)
review-api-design      no fixtures (skipped)
...
12 agents · 1 failing · 1 without fixtures
```

An infra error from a single `run_agent` call (network/parse) is caught per fixture and counted as a non-detection for that run (so flakiness lowers the score rather than crashing the command) — consistent with "evals measure detection rate."

## 6. Extensibility (adding agents needs no harness change)

The **registry is the single source of truth**; the harness is driven by it plus the fixtures-directory convention:
- **New core agent** = register in `registry.py` + write the prompt + add `tests/eval/fixtures/<agent>/`. It is then auto-evaluated, and the workflow's generic path filters (`agents/**`, `review/**.py`) already cover it. No `evals.py` or workflow edit.
- **New battery agent (Plan 8)** = the same: register with `active_when="battery"`, author fixtures. Auto-evaluated. Plan 8's only eval work is configuring the agent + authoring fixtures.
- **Coverage visibility, not silent gaps:** a registered agent without fixtures shows as `no fixtures (skipped)` (visible) but doesn't fail a normal run; `--require-fixtures` (Plan 9 CI can flip it on) escalates that to a failure once enforcement is wanted. The reverse check (fixtures dir with no registry agent) warns.
- **Thresholds** are global by default; `thresholds.yaml` holds optional per-agent overrides — new agents inherit the defaults until tuned.

There is no separate agent manifest to maintain: the registry you already keep *is* the manifest.

## 7. CI workflow — `.github/workflows/agent-evals.yml` (framework repo)

- **Triggers:** `schedule` (a weekly cron) + `push`/`pull_request` whose `paths` match `src/framework_cli/review/agents/**` or `src/framework_cli/review/**.py` (prompt or logic changes).
- **Steps:** checkout → `astral-sh/setup-uv@v5` → `uv sync` → `uv run framework eval tests/eval/fixtures --require-key` with `env: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}`.
- `--require-key` makes a missing secret fail loudly (a misconfigured workflow can't silently "pass"). The job's non-zero exit on a threshold miss surfaces a regressed agent.
- This is the framework repo's *own* CI (dogfooding, §20) — distinct from the generated-project `ci.yml`. Plan 9 folds it into the broader dogfooding CI; 7d ships it standalone.

## 8. Testing (all hermetic — no API key, no network; stays in the default `uv run pytest` gate)

- **`load_fixtures`** — a `tmp_path` tree with bad+good across two agents → correct `Fixture` list; a bad fixture missing its sidecar, and an orphaned `.expect.json`, are skipped with a warning.
- **`flags` / detection rule** — synthetic `Finding` lists: a blocking finding on the seeded file → detected; a finding on a *different* file → not detected; a below-threshold finding → not detected; an advisory agent (`block_threshold=None`) with any-severity finding on the file → detected; a good-fixture finding that blocks → counts toward fp.
- **`load_thresholds`** — parses overrides; missing file → `{}`; an agent absent from the file → `DEFAULT_THRESHOLDS`.
- **`score_agent`** — recall/fp arithmetic and pass/fail vs. thresholds, incl. a per-agent override and the `--repeat`-style fractional rates; the no-bad-fixtures (vacuous recall) and no-good-fixtures edges.
- **`framework eval` command** — monkeypatch the `_eval_run` seam (same pattern as the `review` tests' `_review_run`): a scripted agent that catches its bad fixtures and stays clean on good → scorecard `PASS`, exit 0; a scripted agent that misses → exit 1; a registered agent with no fixtures → `no fixtures (skipped)`, and exit 1 only under `--require-fixtures`; no `ANTHROPIC_API_KEY` → `skipped` exit 0, but exit 1 under `--require-key`.
- **The real Anthropic call is never made in the suite** — only by `framework eval` at runtime (the workflow or a manual run). The suite proves the plumbing + scoring; the fixtures + workflow measure real quality.
- **Workflow render/lint:** `agent-evals.yml` is a static framework-repo file (not templated) — assert it parses as YAML in a small test, and it's covered by the repo's existing actionlint pre-commit.

## 9. Self-review

- **Placeholders:** none — fixture layout, the detection rule, the scoring math, the command flags, the scorecard, the workflow triggers, and the tests are all concrete. Battery-agent fixtures are explicitly deferred (Plan 8), with the mechanism (registry + convention) that makes them a no-harness-change add.
- **Internal consistency:** the detection rule reuses the production `block_threshold` + `severity_rank`, so "detected = would block" matches what CI actually gates on; advisory agents are handled by one branch in `flags`; set-level rates fall out of `--repeat 1`. The harness iterates `agent_names()` (the registry) — consistent with 7b's "the registry is the single source of truth for the matrix".
- **Scope:** one cohesive subsystem (fixtures → scorer → command → workflow). Full dogfooding CI integration and battery fixtures are deferred to 9 and 8.
- **Ambiguity:** "detection against a pass threshold" is pinned to set-level recall/precision with file+blocking-severity matching; "each agent has fixtures" is realized as registry-driven discovery with visible coverage gaps rather than a hardcoded list.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 7d.*

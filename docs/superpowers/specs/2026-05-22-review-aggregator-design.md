# Cross-Agent Interactions + Aggregator (Plan 7c) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 7a (the `framework review <agent>` runner + `Finding` contract + Check Runs) and Plan 7b (the full agent set + the `review-plan`→`review` CI matrix). Realizes the §7 "Agent Interactions" + "Aggregator" sections. Third sub-project of Plan 7.

---

## 1. Purpose & scope

The agents run as a parallel matrix, each posting its own `review-*` Check Run — a builder must hunt across 12 checks. Plan 7c adds **one consolidated PR summary** and surfaces **cross-agent relationships** among findings.

**In scope:**
- A findings-collection mechanism: `framework review <agent>` writes its result to a JSON file (`--findings-out`); each matrix job uploads it as a per-agent artifact.
- `framework review-aggregate <dir>`: reads all per-agent findings, computes a pass/fail + per-severity summary + cross-agent relationships, and posts a **single sticky PR comment**.
- The generated `ci.yml`: per-agent artifact upload + a `review-aggregate` job.

**Out of scope (deferred):**
- LLM-based / semantic cross-agent re-evaluation (the chosen interactions model is deterministic *surfacing*, not re-invoking agents — see §2).
- The eval harness / real review-quality assertions → **Plan 7d**.
- The 3 battery agents → **Plan 8**.

## 2. Decisions (settled in brainstorm)

- **Interactions = the aggregator surfaces relationships** (deterministic), not agent re-invocation. It detects, among the already-collected findings, (a) the same file/line flagged by ≥2 agents and (b) known related-domain co-occurrence, and reports them. No extra LLM calls; matches §7's "the aggregator surfaces these cross-agent relationships"; deterministically testable.
- **Findings collection = per-agent artifacts.** Each `review` matrix job writes lossless structured findings to a file + uploads it; the `review-aggregate` job downloads them all. (Not re-reading the lossy Check Run annotations.)
- The aggregator + runner stay framework-owned (in the installed CLI), consistent with 7a/7b.

## 3. Findings collection

- **`framework review <agent>` gains `--findings-out <path>`** (default unset → write nothing, so local runs and the 7a/7b behavior are unchanged). When set, at **every** terminal path (no-key skip, not-triggered, infra-error→neutral, normal), the command writes JSON:
  ```json
  {"agent": "review-<name>", "conclusion": "success|neutral|failure", "findings": [<Finding dicts>]}
  ```
  (`findings` is `[]` on the skip/not-triggered/error paths.) A small helper writes this just before each `typer.Exit`. `Finding` → dict via `dataclasses.asdict`.
- **CI:** each `review` matrix job runs `framework review <agent> --findings-out findings/<agent>.json`, then an `actions/upload-artifact@v4` step with **`if: always()`** (name `review-findings-<agent>`, path `findings/`) — so the artifact uploads even when a blocking finding made the review step exit 1 (the file is written before that exit).

## 4. The aggregator

**`src/framework_cli/review/aggregate.py`** — a pure core + an I/O wrapper:

- `AggregateResult` (dataclass): `overall: "pass" | "fail"`, `severity_counts: dict[str,int]`, `relationships: list[str]`, `markdown: str`.
- `aggregate(results: list[dict]) -> AggregateResult` (pure, no I/O — `results` are the parsed per-agent JSONs):
  - **overall** = `"fail"` if any result's `conclusion == "failure"`, else `"pass"`.
  - **severity_counts** across all findings.
  - **relationships** (deterministic): (a) any `path` (optionally `path:line`) appearing in findings from ≥2 distinct agents → "Multiple agents flagged `<path>`: <agents>"; (b) known related-domain pairs co-occurring on an overlapping file — `_RELATED_PAIRS = {(lineage,privacy),(lineage,compliance),(performance,data-integrity)}` → "`<a>` + `<b>` both flagged `<path>` — related concern."
  - **markdown**: a ✅/❌ header with overall + counts; findings grouped by severity (`<agent> · path:line · message`); a "Cross-agent relationships" section (or "none"); the affected-files list. Carries a hidden marker line `<!-- framework-review-summary -->` for stickiness.
- **`framework review-aggregate <dir>` command:** read every `*.json` in `<dir>` (tolerate a malformed/missing file — skip it), call `aggregate`, then **post a single sticky PR comment**: list the PR's comments (`gh api repos/{repo}/issues/{pr}/comments`), find the one containing the marker → `PATCH` it, else `POST` a new one. The PR number comes from `--pr` / `GITHUB_PR_NUMBER` env; if absent (a push build), print the markdown to stdout instead. Posting failure is non-fatal (never crashes the job).

## 5. CI wiring (`ci.yml.jinja`)

- The `review` matrix job: the agent step becomes `framework review {agent} --findings-out findings/{agent}.json`; add an `upload-artifact@v4` step (`if: always()`, name `review-findings-{agent}`, path `findings/`).
- A new **`review-aggregate`** job: `needs: review`, **`if: always()`** (summarize even if agents failed/skipped); `permissions: {contents: read, pull-requests: write}`; steps: checkout → setup-uv → install the framework at the recorded `_commit` → `actions/download-artifact@v4` (`pattern: review-findings-*`, `merge-multiple: true`, into `all-findings/`) → `framework review-aggregate all-findings` with env `GITHUB_TOKEN` + `GITHUB_PR_NUMBER: ${{ github.event.pull_request.number }}`.

## 6. Testing (all hermetic — no network)

- **`aggregate` (pure):** overall fail iff any `failure`; per-severity counts; same-file relationship (≥2 agents, same path); related-pair relationship (e.g. lineage+privacy on an overlapping file); the markdown contains the header, severity groups, the relationships section, the affected files, and the sticky marker.
- **`review --findings-out`:** the normal path (mocked client → findings) writes `{agent, conclusion, findings}`; the not-triggered/skip path writes `conclusion` neutral + `findings: []`.
- **`review-aggregate` command:** a `tmp_path` dir of findings JSONs → prints the markdown when no PR number; the sticky find-or-create logic tested with a stubbed `gh` (existing-marker → update; none → create); a malformed JSON file is skipped, not fatal.
- **`ci.yml` render (`tests/test_copier_runner.py`):** the `review` job has `--findings-out` + the `if: always()` upload-artifact; a `review-aggregate` job exists with `needs: review`, `if: always()`, the `download-artifact` pattern, and `framework review-aggregate`. Rendered YAML parses.
- **Generated-project cleanliness:** only `ci.yml` changes ship into projects → the acceptance suite stays green by construction.

## 7. Self-review

- **Placeholders:** none — the findings-out contract, the `aggregate` rules, the sticky-comment logic, the CI jobs, and the tests are concrete. Semantic/LLM relationships are explicitly deferred (YAGNI), not hand-waved.
- **Internal consistency:** interactions are surfaced *by* the aggregator from the collected findings (matching the chosen deterministic model); artifacts (not annotations) preserve the structured `Finding`s the relationship rules need; the `if: always()` on both the upload and the aggregate job is what lets the summary appear even when agents block.
- **Scope:** one cohesive subsystem (collect → aggregate → comment); evals (7d) and battery agents (8) deferred.
- **Ambiguity:** "agent interactions" is pinned to deterministic surfacing (same-file + the explicit `_RELATED_PAIRS`); the no-PR (push) path prints instead of commenting.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 7c. Then 7d (eval harness).*

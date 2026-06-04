# Environment-Parity Reviewer (`review-env-parity`, Plan 17) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new agentic, blocking-`high` review agent `review-env-parity` that flags the *dev-only-not-prod* antipattern — a runtime service or environment variable present in one environment but not reaching another across the env→overlay chain.

**Architecture:** Framework-side only. A prompt file (`agents/env-parity.md`) + one `AgentSpec` in the registry + 3-bad/1-good rendered-project eval fixtures + a recall-first `thresholds.yaml` row + a decisions-log integration test. It rides the Plan 11 agentic spine (root-confined `read_file`/`grep`/`glob`, Opus) and the existing decisions-log suppression (no new code). No template payload changes → no integrity/manifest shift.

**Tech Stack:** Python 3.12, `uv`, pytest, the existing `framework_cli.review` registry/eval harness, `/reviewers:tune` slash command for calibration.

**Spec:** `docs/superpowers/specs/2026-06-04-environment-parity-reviewer-design.md`

---

## File Structure

- Create: `src/framework_cli/review/agents/env-parity.md` — the agent prompt (greedy service parity + env-var parity + the env→overlay composition oracle; JSON-only output).
- Modify: `src/framework_cli/review/registry.py` — add the `"env-parity"` `AgentSpec` to `_SPECS`.
- Modify: `tests/review/test_registry.py` — add `"env-parity"` to `_EXPECTED_PR`; add a focused `test_env_parity_agent_spec`.
- Create: `tests/eval/fixtures/env-parity/bad/service-dev-only/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/env-parity/bad/env-var-consumed-not-declared/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/env-parity/bad/compose-var-not-declared/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/env-parity/good/parity-preserved/{fixture.yaml,change.patch}`
- Create: `tests/review/test_env_parity_decisions.py` — decisions-log integration test (acknowledge + stale).
- Modify: `tests/eval/fixtures/thresholds.yaml` — add the calibrated `env-parity` row (recall-first).
- Modify: `CLAUDE.md` + `docs/superpowers/plans/2026-05-20-meta-plan.md` — status update (final task).

**Decision — NOT added to `FRAMEWORK_AGENTS`:** `review-env-parity` is a *project-target* agent (it guards generated projects' `infra/compose/*` + `.env.example` + `config/settings.py`). The framework's own repo has no deploy-infra surface to guard, so the dogfood roster (`FRAMEWORK_AGENTS` in `src/framework_cli/review/context.py`) is left unchanged. (See memory: check-agent-prompt-fit-before-adding-to-target.)

---

## Task 1: Eval fixtures (3 bad + 1 good)

Fixtures are **rendered-project** fixtures: each `change.patch` is a unified diff that applies to a fresh baseline render (package `demo`). Author them by rendering, editing, and capturing the diff — this is the only reliable way to get correct line numbers. The structural gate (`test_fixtures_are_wellformed`, `test_every_registered_agent_has_fixtures`) is the failing-first test.

**Files:**
- Test (gate): `tests/review/test_evals.py::test_fixtures_are_wellformed`, `::test_every_registered_agent_has_fixtures`
- Create: the four fixture directories listed above.

- [ ] **Step 1: Render a baseline `demo` project to author patches against**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
rm -rf /tmp/envparity-fx && mkdir -p /tmp/envparity-fx
uv run python -c "
from framework_cli.copier_runner import render_project
from pathlib import Path
render_project(Path('/tmp/envparity-fx'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','batteries':[]})
"
cd /tmp/envparity-fx/demo && git init -q && git add -A && git commit -qm base
```
Expected: a generated project at `/tmp/envparity-fx/demo` with a clean git baseline.

- [ ] **Step 2: Author `bad/service-dev-only` — a service only in `dev.yml`**

Edit `/tmp/envparity-fx/demo/infra/compose/dev.yml`: add a new service `widgetizer` under `services:` (e.g. directly after the `app:` block), present ONLY in the dev overlay (never in `base.yml`/`services.yml`), so it cannot reach staging/prod:

```yaml
  widgetizer:
    image: ghcr.io/acme/widgetizer:1.4.0
    profiles: ["dev"]
    environment:
      WIDGETIZER_DB_URL: "postgresql+psycopg://app:app@postgres:5432/app"
    depends_on:
      postgres:
        condition: service_healthy
```

Capture the patch and write the sidecars:

```bash
cd /tmp/envparity-fx/demo
mkdir -p "$OLDPWD"/tests/eval/fixtures/env-parity/bad/service-dev-only 2>/dev/null
FX="/home/chris/Claude Code/Projects/framework/swiftwater-framework/tests/eval/fixtures/env-parity/bad/service-dev-only"
mkdir -p "$FX"
git diff > "$FX/change.patch"
printf 'batteries: []\n' > "$FX/fixture.yaml"
printf '{"file": "infra/compose/dev.yml"}\n' > "$FX/expect.json"
git checkout -- .
```
Expected: `change.patch` is a non-empty unified diff touching `infra/compose/dev.yml`.

- [ ] **Step 3: Author `bad/env-var-consumed-not-declared` — `settings.py` reads an undeclared var**

Edit `/tmp/envparity-fx/demo/src/demo/config/settings.py`: add a field that pydantic maps to `APP_WIDGET_TIMEOUT` (env_prefix `APP_`), WITHOUT adding it to `.env.example`. Insert after the `slo_error_rate_pct` field:

```python
    # Widget service call timeout (seconds).
    widget_timeout_s: float = 5.0
```

```bash
cd /tmp/envparity-fx/demo
FX="/home/chris/Claude Code/Projects/framework/swiftwater-framework/tests/eval/fixtures/env-parity/bad/env-var-consumed-not-declared"
mkdir -p "$FX"
git diff > "$FX/change.patch"
printf 'batteries: []\n' > "$FX/fixture.yaml"
printf '{"file": "src/demo/config/settings.py"}\n' > "$FX/expect.json"
git checkout -- .
```
Expected: `change.patch` touches `src/demo/config/settings.py`; `.env.example` is untouched (that's the defect).

- [ ] **Step 4: Author `bad/compose-var-not-declared` — a compose overlay references an undeclared `${APP_*}`**

Edit `/tmp/envparity-fx/demo/infra/compose/base.yml`: add an env var interpolation to the `app` service's `environment:` that `.env.example` never declares:

```yaml
      APP_WIDGET_API_URL: "${APP_WIDGET_API_URL}"
```

```bash
cd /tmp/envparity-fx/demo
FX="/home/chris/Claude Code/Projects/framework/swiftwater-framework/tests/eval/fixtures/env-parity/bad/compose-var-not-declared"
mkdir -p "$FX"
git diff > "$FX/change.patch"
printf 'batteries: []\n' > "$FX/fixture.yaml"
printf '{"file": "infra/compose/base.yml"}\n' > "$FX/expect.json"
git checkout -- .
```
Expected: `change.patch` touches `infra/compose/base.yml`; `${APP_WIDGET_API_URL}` is undeclared in `.env.example`.

- [ ] **Step 5: Author `good/parity-preserved` — a fully parity-complete change (no finding expected)**

Add a new service to `base.yml` (reaches every env), declare its var in `.env.example` within the managed region, and consume it in `settings.py` — all three surfaces consistent.

Edit `base.yml` `app` `environment:`:
```yaml
      APP_WIDGET_API_URL: "${APP_WIDGET_API_URL}"
```
Edit `.env.example` (inside `# FRAMEWORK:BEGIN`/`END`, before the closing marker):
```
# Widget service base URL (set per environment).
APP_WIDGET_API_URL=http://widget:9000
```
Edit `settings.py` (after `slo_error_rate_pct`):
```python
    # Widget service base URL.
    widget_api_url: str = "http://widget:9000"
```

```bash
cd /tmp/envparity-fx/demo
FX="/home/chris/Claude Code/Projects/framework/swiftwater-framework/tests/eval/fixtures/env-parity/good/parity-preserved"
mkdir -p "$FX"
git diff > "$FX/change.patch"
printf 'batteries: []\n' > "$FX/fixture.yaml"
git checkout -- .
```
Expected: `change.patch` is non-empty and touches `base.yml`, `.env.example`, and `settings.py`. Good fixtures have NO `expect.json`.

- [ ] **Step 6: Run the structural gate**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
uv run pytest tests/review/test_evals.py::test_fixtures_are_wellformed -v
```
Expected: PASS — all four `env-parity` fixtures are well-formed (each bad case has a non-empty `change.patch` + an `expect.json` naming a `file`; the good case parses). `test_every_registered_agent_has_fixtures` is not yet affected (the agent registers in Task 2).

- [ ] **Step 7: Commit**

```bash
git add tests/eval/fixtures/env-parity
git add CLAUDE.md   # see note: CLAUDE.md must be staged for the commit gate; update it in the final task — for intermediate task commits, re-stage the already-updated file or touch the Last-updated line
git commit -m "test(review): env-parity eval fixtures (3 bad + 1 good)"
```
Note on the commit gate: the PreToolUse hook blocks `git commit` unless `CLAUDE.md` is staged (see memory: commit-gate-hook-timing — separate `git add` then `git commit`; keep the word "commit" out of Bash tool descriptions). The controller bumps the `CLAUDE.md` **Last updated** line once at the start of the branch and re-stages it on each task commit.

---

## Task 2: Agent prompt + registry registration

**Files:**
- Create: `src/framework_cli/review/agents/env-parity.md`
- Modify: `src/framework_cli/review/registry.py` (add to `_SPECS`)
- Test: `tests/review/test_registry.py` (`_EXPECTED_PR` + `test_env_parity_agent_spec`)

- [ ] **Step 1: Write the failing tests**

In `tests/review/test_registry.py`, add `"env-parity"` to the `_EXPECTED_PR` list (keep it a `sorted([...])` literal), and add this focused test:

```python
def test_env_parity_agent_spec():
    from framework_cli.review.registry import AGENTIC_MODEL

    spec = get_agent("env-parity")
    assert spec.name == "review-env-parity"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    assert spec.model == AGENTIC_MODEL
    assert spec.on_push is False
    assert spec.context.strategy == "agentic"
    assert spec.trigger_globs is not None
    assert set(spec.trigger_globs) == {
        "infra/*",
        ".env.example",
        "src/*/config/settings.py",
    }
    # Prompt embodies the spec: greedy service parity + env-var parity + JSON output.
    assert "JSON" in spec.prompt
    assert "dev-only" in spec.prompt.lower() or "parity" in spec.prompt.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/review/test_registry.py::test_env_parity_agent_spec tests/review/test_registry.py::test_full_active_sets -v
```
Expected: FAIL — `test_env_parity_agent_spec` raises `KeyError: unknown review agent: env-parity` (registry has no entry; the prompt import would also fail once referenced).

- [ ] **Step 3: Write the agent prompt**

Create `src/framework_cli/review/agents/env-parity.md`:

```markdown
You are `review-env-parity`. Review a change to a project's environment surface for
DEV→CI→STAGE→PROD parity. You own NON-OBSERVABILITY parity only: runtime services and
environment variables. You are NOT an observability reviewer (scrape jobs / exporters /
alerts / dashboards belong to review-observability-infra) and NOT a privacy/security
reviewer (PII or secret *content* belongs to review-privacy / review-security).

An environment is a COMPOSITION of overlays, not a single file. Determine which overlays
each environment composes by reading the authoritative sources with your tools:
- `Taskfile.yml` — dev = base.yml + observability.yml + dev.yml; dev:lite = base.yml + dev.yml
  (the deliberate obs opt-out); test = base.yml + test.yml.
- `infra/deploy/strategy.sh` + `infra/deploy/README.md` — staging/prod = base.yml + <env>.yml
  + services.yml + observability.yml.
A service/variable REACHES an environment iff it is defined in an overlay that environment
composes. Never reduce this to a naive file-vs-file diff.

Flag, citing the changed line:
- SERVICE PARITY (be GREEDY — the repeated, costly defect is MISSING a dev-only thing, not a
  false alarm): a runtime service defined only in a dev-scoped overlay (`dev.yml`) so it does
  not reach staging/prod. The correct home for a prod-reaching service is `base.yml`, or
  `services.yml` for battery data-stores/worker/beat. Treat ANY dev-only service as a finding
  UNLESS it is unmistakably local-developer-experience tooling (TLS termination for local HTTPS
  such as Traefik/mkcert, a mail catcher, a DB admin UI). Even then, prefer a finding that can
  be acknowledged via the decisions log over silent omission.
- ENV-VAR PARITY: a variable consumed in `src/*/config/settings.py` (a pydantic field under the
  `APP_` prefix) but absent from `.env.example`; a `${APP_*}` interpolation in a compose overlay
  with no `.env.example` declaration; or a name that diverges between `.env.example` and the
  `settings.py` field it should map to.

Do NOT flag: config VALUE divergence across environments (different values per overlay are the
intended purpose of overlays); observability surfaces; PII/secret content.

If a finding matches an accepted decision whose premise still holds, still emit it with
`acknowledged: "<id>"`; if the premise no longer holds, emit it with `stale: "<id>"`.

Return JSON ONLY — a single array, no prose, no code fences. Each element:
{"path","line","severity","message","suggestion"}. [] if none. A service that won't reach prod
or a consumed-but-undeclared variable is "high".
```

- [ ] **Step 4: Register the agent**

In `src/framework_cli/review/registry.py`, add this entry to `_SPECS` (place it next to the other `observability-*` file-trigger agentic agents for readability):

```python
    "env-parity": AgentSpec(
        "review-env-parity",
        _prompt("env-parity"),
        "high",
        "file-trigger",
        AGENTIC_MODEL,
        trigger_globs=("infra/*", ".env.example", "src/*/config/settings.py"),
        context=ContextPolicy("agentic"),
    ),
```

- [ ] **Step 5: Run the registry + coverage tests**

```bash
uv run pytest tests/review/test_registry.py tests/review/test_evals.py -q
```
Expected: PASS — `test_env_parity_agent_spec`, `test_full_active_sets` (env-parity now in the PR set), `test_every_agent_prompt_loads_and_demands_json[env-parity]`, and `test_every_registered_agent_has_fixtures` (fixtures from Task 1) all green.

- [ ] **Step 6: Confirm the prompt ships in the wheel + no template/manifest shift**

```bash
uv run pytest tests/ -q -k "manifest or integrity or copier_runner" 
git status --porcelain src/framework_cli/template   # expect: no changes
```
Expected: template untouched; no baseline manifest shift (the prompt is packaged like every other `agents/*.md`).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/agents/env-parity.md src/framework_cli/review/registry.py tests/review/test_registry.py CLAUDE.md
git commit -m "feat(review): register review-env-parity agentic reviewer"
```

---

## Task 3: Decisions-log integration test (acknowledge + self-heal)

Prove `review-env-parity` rides the existing agent-agnostic decisions mechanism with no new code: an `accepted` decision targeting it is matched; the acknowledged-finding path is non-blocking; a finding tagged `acknowledged` is segregated by `analyze`.

**Files:**
- Create: `tests/review/test_env_parity_decisions.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from framework_cli.review.decisions import (
    relevant_decisions,
    render_decisions_block,
)


_DECISION = """---
id: DEC-ENVPARITY-EX
status: accepted
agents: [review-env-parity]
concern: "traefik is intentionally dev-only"
premise: >
  Prod TLS is terminated by the platform load balancer, not an in-stack reverse proxy,
  so the app needs no traefik service in staging/prod. STALE if the app gains a runtime
  dependency on traefik in a deployed environment.
date: 2026-06-04
---

Traefik runs only in the dev overlay to provide local HTTPS via mkcert. Reviewed and accepted.
"""


def _write_decision(root: Path) -> None:
    d = root / "docs" / "superpowers" / "decisions"
    d.mkdir(parents=True)
    (d / "DEC-ENVPARITY-EX.md").write_text(_DECISION)


def test_env_parity_decision_is_relevant_and_renders(tmp_path):
    _write_decision(tmp_path)
    decs = relevant_decisions("review-env-parity", tmp_path)
    assert [d.id for d in decs] == ["DEC-ENVPARITY-EX"]
    block = render_decisions_block(decs)
    assert block is not None
    assert "DEC-ENVPARITY-EX" in block
    assert "acknowledged" in block  # the protocol preamble instructs the ack/stale tagging


def test_env_parity_decision_not_visible_to_other_agents(tmp_path):
    _write_decision(tmp_path)
    assert relevant_decisions("review-security", tmp_path) == []


def test_acknowledged_finding_is_segregated(tmp_path):
    from framework_cli.review.analyze import acknowledged_findings

    records = [
        {
            "agent": "review-env-parity",
            "findings": [
                {
                    "path": "infra/compose/dev.yml",
                    "line": 40,
                    "severity": "high",
                    "message": "traefik is dev-only",
                    "acknowledged": "DEC-ENVPARITY-EX",
                }
            ],
        }
    ]
    acked = acknowledged_findings(records, {"DEC-ENVPARITY-EX"})
    assert any(item["acknowledged"] == "DEC-ENVPARITY-EX" for item in acked)
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/review/test_env_parity_decisions.py -v
```
Expected: PASS — the decisions mechanism is already implemented (`decisions.py`/`analyze.py`); this test documents and locks the integration. If `acknowledged_findings`' signature differs, read `src/framework_cli/review/analyze.py:309` and adjust the call (it accepts `(records, active_ids)`).

- [ ] **Step 3: Commit**

```bash
git add tests/review/test_env_parity_decisions.py CLAUDE.md
git commit -m "test(review): env-parity rides the decisions-log acknowledge/stale path"
```

---

## Task 4: Calibrate thresholds via `/reviewers:tune` (controller step)

This is a calibration task, not a code-TDD task: run the local-subagent tuner against the four fixtures, read the scorecard, and commit a recall-first `thresholds.yaml` row. Numbers come from the run (we do not invent them). See memory: reviewers-tune-quota-throttling (check `len(results)` vs the index; re-dispatch silent drops) and reviewers-tune-pytest-tmp-accumulation (clean `/tmp/pytest-of-chris/*` if a run looks spuriously broken).

**Files:**
- Modify: `tests/eval/fixtures/thresholds.yaml`
- Create: a dated scorecard under `docs/superpowers/eval-scorecards/` (written by the tuner).

- [ ] **Step 1: Run the tuner for the single agent**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
# Slash command (controller runs it): /reviewers:tune env-parity
```
Expected: a scorecard for `env-parity` with per-fixture recall (3 bad detected on the correct file) and false-positive rate (the good fixture stays clean). Target shape: recall 1.00 / fp 0.00, consistent with the other recently-added agents.

- [ ] **Step 2: Add the recall-first threshold row**

Append to `tests/eval/fixtures/thresholds.yaml`, using the calibration policy `recall_min = observed − 0.10`, `fp_max = observed + 0.10`, with the observed values in comments. Protect recall (this agent's whole purpose is not to miss), allowing a higher `fp_max` ceiling like `observability-infra`'s `0.43`:

```yaml
env-parity:
  recall_min: 0.90  # observed 1.00 — recall-first: a missed parity gap is the twice-shipped defect
  fp_max: 0.10  # observed 0.00 — raise toward 0.43 if the greedy posture trips the good fixture under variance
```
(If the observed numbers differ, set the floor/ceiling from them per the policy; never let `recall_min` drop below what the agent honestly achieves.)

- [ ] **Step 3: Verify scoring passes against the committed threshold**

```bash
uv run pytest tests/review/test_evals.py -q
# plus re-run /reviewers:tune env-parity once more to confirm the row makes the agent PASS with margin
```
Expected: the eval harness loads the new threshold; the agent PASSes.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/fixtures/thresholds.yaml docs/superpowers/eval-scorecards CLAUDE.md
git commit -m "test(review): calibrate review-env-parity thresholds (recall-first)"
```

---

## Task 5: Finalize — full gate, state docs, branch-end review

**Files:**
- Modify: `CLAUDE.md` (Current State), `docs/superpowers/plans/2026-05-20-meta-plan.md` (Plan 17 row → ✅ Done)

- [ ] **Step 1: Run the full quality gate**

```bash
cd "/home/chris/Claude Code/Projects/framework/swiftwater-framework"
TMPDIR=/var/tmp uv run pytest -q       # full suite — use /var/tmp (memory: tmp tmpfs exhaustion)
uv run ruff check .
uv run ruff format --check .            # memory: ruff-format-check-after-inline-edits
uv run mypy src
```
Expected: all green. (If a render-coupled fixture patch fails to apply, re-author it against a fresh render — the template may have shifted line numbers.)

- [ ] **Step 2: Update the state docs**

- `CLAUDE.md` Current State: flip the Plan 17 pointer to ✅ Done with the agent summary + FF SHA placeholder, bump **Last updated** (datetime + tz).
- Meta-plan status table row 17: `⬜ Not started` → `✅ Done`, add plan-doc names + the merge ref; update the compact "Remaining Sequence" forward pointer (next = Plan 18).

- [ ] **Step 3: Commit the state docs**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md
git commit -m "docs(state): Plan 17 ✅ done — review-env-parity environment-parity reviewer"
```

- [ ] **Step 4: Branch-end review + merge**

Run the superpowers:requesting-code-review flow (Opus whole-branch review). Address findings, then FF-merge the branch to `master` per the project's subagent-driven flow. Record the FF SHA in `CLAUDE.md` + the meta-plan row.

---

## Self-Review (against the spec)

- **§1 boundary / domain split** → Task 2 prompt explicitly cedes obs to `review-observability-infra`; `observability-infra` is untouched (File Structure note). ✔
- **§2 service parity (greedy)** → prompt's SERVICE PARITY clause + `bad/service-dev-only` fixture + recall-first threshold (Task 4). ✔
- **§2 env-var parity** → prompt's ENV-VAR PARITY clause + `bad/env-var-consumed-not-declared` + `bad/compose-var-not-declared` fixtures. ✔
- **§2 config-value divergence OUT** → prompt's explicit "Do NOT flag config VALUE divergence". ✔
- **§3 parity oracle** → prompt names `Taskfile.yml` + `infra/deploy/strategy.sh`/`README.md` as composition sources; `context=ContextPolicy("agentic")` gives the tools to follow them. ✔
- **§4 registration** (file-trigger globs, agentic/Opus, block high, not on_push) → Task 2 registry entry + `test_env_parity_agent_spec`. ✔
- **§5 decisions log** → Task 3 integration test (acknowledge + relevance + segregation); no new code. ✔
- **§6 fixtures + recall-first thresholds** → Tasks 1 + 4. ✔
- **§7 tests/guards + no manifest shift** → coverage gate (Task 1/2), Task 2 Step 6 template/manifest check, Task 5 full gate. ✔
- **§8 separation of concerns** → prompt's "NOT an observability/privacy/security reviewer" framing. ✔
- **NOT in `FRAMEWORK_AGENTS`** → File Structure decision note. ✔

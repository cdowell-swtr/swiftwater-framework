# Full Review Agent Set + Triggering Matrix (Plan 7b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 10 remaining "always" review agents + `review-dependency` (file-trigger) and the triggering matrix (`framework review-agents` → dynamic parallel CI matrix, with the §7 push-to-main subset, advisory agents, and a file-trigger self-skip).

**Architecture:** Extends the Plan 7a runner. `AgentSpec` gains `block_threshold: Severity | None` (None=advisory), `on_push`, `trigger_globs`; the registry adds 11 agents (each a bundled `agents/<name>.md` prompt). `active_agents(event)` + a `framework review-agents` command feed a GitHub matrix in the generated `ci.yml` (`review-plan` job computes the list, `review` job fans out). `review-dependency` self-skips when no dependency file changed. All deterministic plumbing is unit-tested with a mocked client; real review quality is Plan 7d.

**Tech Stack:** Python 3.12, Typer, the 7a `review/` package, GitHub Actions matrix, pytest. Design: `docs/superpowers/specs/2026-05-22-review-agent-set-design.md`.

---

## Scope

**In scope:** the `AgentSpec` extensions; the 11 new agents (`data-integrity`, `data-lineage`, `application-logic`, `observability`, `test-quality`, `architecture`, `performance`, `compliance`, `privacy`, `documentation`, `dependency`) + prompts; `active_agents`; the `framework review-agents` command; `diff.changed_files`/`matches_globs`; the file-trigger self-skip; the advisory `to_check_run` tweak; the generated `ci.yml` matrix.

**Out of scope:** the 3 battery agents (api-design/accessibility/usability) → Plan 8; cross-agent interactions + aggregator → 7c; the eval harness / real-quality tests → 7d. No real Anthropic call in tests (mocked).

## Repo working agreement for EVERY commit

The `PreToolUse` hook blocks `git commit` unless `CLAUDE.md` has a staged change. Each "Commit" step: (1) bump `CLAUDE.md` Current State → Last updated (datetime + `PDT`); (2) `git add <files> CLAUDE.md` as ONE call; (3) `git commit` as a SEPARATE call. End the body with:
```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
> Tests build throwaway git repos in `tmp_path` (for `diff`/file-trigger) — fine, unrelated to this repo's hook; run them via `uv run pytest`.

## File Structure

**Modified (framework source):**
- `src/framework_cli/review/registry.py` — `AgentSpec` fields; `security.on_push=True`; 11 new entries; `active_agents`.
- `src/framework_cli/review/checks.py` — `to_check_run` advisory branch.
- `src/framework_cli/review/diff.py` — `changed_files`, `matches_globs`.
- `src/framework_cli/cli.py` — `review-agents` command; file-trigger self-skip in `review`.

**New (framework source — package data):**
- `src/framework_cli/review/agents/{data-integrity,data-lineage,application-logic,observability,test-quality,architecture,performance,compliance,privacy,documentation,dependency}.md`

**Modified (template payload):** `src/framework_cli/template/.github/workflows/ci.yml.jinja` — the review matrix.

**New/extended tests:** `tests/review/test_registry.py`, `test_checks.py`, `test_diff.py`, `tests/test_cli.py`, `tests/test_copier_runner.py`.

---

### Task 1: Extend `AgentSpec` + `active_agents`

**Files:** Modify `src/framework_cli/review/registry.py`; Test `tests/review/test_registry.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/review/test_registry.py`:

```python
def test_security_is_on_push():
    assert get_agent("security").on_push is True


def test_active_agents_push_is_subset_of_pull_request():
    pr = active_agents("pull_request")
    push = active_agents("push")
    assert "security" in pr and "security" in push
    assert set(push).issubset(set(pr))


def test_active_agents_excludes_battery_and_is_sorted():
    pr = active_agents("pull_request")
    assert pr == sorted(pr)
```

(Add `active_agents` to the existing `from framework_cli.review.registry import ...` line.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_registry.py -k "on_push or active_agents" -q`
Expected: FAIL — `active_agents` undefined; `AgentSpec` has no `on_push`.

- [ ] **Step 3: Implement** — in `src/framework_cli/review/registry.py`:

Change `from framework_cli.review.findings import Severity` consumers — update `AgentSpec` and add `active_agents`. Replace the `AgentSpec` dataclass with:

```python
@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    block_threshold: Severity | None  # None = advisory (never blocks)
    active_when: ActiveWhen
    model: str
    on_push: bool = False
    trigger_globs: tuple[str, ...] | None = None
```

Update the existing `security` entry to add `on_push=True` (after `model=DEFAULT_MODEL`):

```python
    "security": AgentSpec(
        name="review-security",
        prompt=_prompt("security"),
        block_threshold="high",
        active_when="always",
        model=DEFAULT_MODEL,
        on_push=True,
    ),
```

Add `active_agents` after `agent_names`:

```python
def active_agents(event: str) -> list[str]:
    """Agent names active for a CI event: on push, the always-on-main subset; otherwise
    all non-battery agents."""
    if event == "push":
        return sorted(k for k, s in _SPECS.items() if s.on_push)
    return sorted(
        k for k, s in _SPECS.items() if s.active_when in ("always", "file-trigger")
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_registry.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean. (`block_threshold: Severity | None` — confirm `mypy` is happy; `to_check_run` still passes a non-None for security until Task 2.)

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/registry.py tests/review/test_registry.py CLAUDE.md
```
```bash
git commit -m "feat(review): AgentSpec on_push/trigger_globs/advisory + active_agents(event)"
```

---

### Task 2: Advisory `to_check_run` (None threshold never blocks)

**Files:** Modify `src/framework_cli/review/checks.py`; Test `tests/review/test_checks.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/review/test_checks.py`:

```python
from dataclasses import replace


def test_advisory_agent_never_fails():
    advisory = replace(_SPEC, block_threshold=None)
    assert to_check_run(advisory, [Finding("a.py", 1, "critical", "x")]).conclusion == "neutral"
    assert to_check_run(advisory, []).conclusion == "success"
```

(`_SPEC` already exists in the test file from 7a; `Finding`/`to_check_run` are already imported. Add `from dataclasses import replace` if not present.)

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_checks.py -k advisory -q`
Expected: FAIL — `severity_rank(None)` raises `KeyError`.

- [ ] **Step 3: Implement** — in `src/framework_cli/review/checks.py`, replace the first two lines of `to_check_run` (the `threshold = ...` and `blocking = ...` lines) with:

```python
    if spec.block_threshold is None:
        blocking: list[Finding] = []  # advisory agent: annotate only, never fail
    else:
        threshold = severity_rank(spec.block_threshold)
        blocking = [f for f in findings if severity_rank(f.severity) >= threshold]
```

(The `conclusion`/`annotations`/`summary` lines below are unchanged.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_checks.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (advisory + the 7a checks tests); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/checks.py tests/review/test_checks.py CLAUDE.md
```
```bash
git commit -m "feat(review): advisory agents (None block_threshold) never fail the check"
```

---

### Task 3: Diff change-detection (`changed_files`, `matches_globs`)

**Files:** Modify `src/framework_cli/review/diff.py`; Test `tests/review/test_diff.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/review/test_diff.py`:

```python
from framework_cli.review.diff import changed_files, matches_globs

_DIFF = (
    "diff --git a/pyproject.toml b/pyproject.toml\n"
    "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1 +1 @@\n-x\n+y\n"
    "diff --git a/src/app/main.py b/src/app/main.py\n"
    "--- a/src/app/main.py\n+++ b/src/app/main.py\n@@ -1 +1 @@\n-a\n+b\n"
)


def test_changed_files_extracts_new_paths():
    assert changed_files(_DIFF) == ["pyproject.toml", "src/app/main.py"]


def test_changed_files_skips_deletions():
    deletion = "--- a/gone.txt\n+++ /dev/null\n"
    assert changed_files(deletion) == []


def test_matches_globs_basename_and_path():
    assert matches_globs(["frontend/package.json"], ("package.json",)) is True
    assert matches_globs(["pyproject.toml"], ("uv.lock", "pyproject.toml")) is True
    assert matches_globs(["src/app/main.py"], ("pyproject.toml", "uv.lock")) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_diff.py -k "changed_files or matches_globs" -q`
Expected: FAIL — names undefined.

- [ ] **Step 3: Implement** — in `src/framework_cli/review/diff.py`, add the imports + functions:

```python
import fnmatch
import os
import re

_NEW_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def changed_files(diff: str) -> list[str]:
    """The new-side paths of files changed in a unified diff (deletions → /dev/null are skipped)."""
    return _NEW_PATH_RE.findall(diff)


def matches_globs(paths: list[str], globs: tuple[str, ...]) -> bool:
    """True if any path matches any glob, by full path or basename."""
    return any(
        fnmatch.fnmatch(p, g) or fnmatch.fnmatch(os.path.basename(p), g)
        for p in paths
        for g in globs
    )
```

(`os` may already be imported in `diff.py` — if so, don't duplicate it; keep one import.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/review/test_diff.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/review/diff.py tests/review/test_diff.py CLAUDE.md
```
```bash
git commit -m "feat(review): changed_files + matches_globs (for file-trigger agents)"
```

---

### Task 4: The 11 agents (prompts + registry entries)

**Files:** Create `src/framework_cli/review/agents/<name>.md` (×11); Modify `src/framework_cli/review/registry.py`; Test `tests/review/test_registry.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/review/test_registry.py`:

```python
import pytest

_EXPECTED_PR = sorted(
    [
        "security", "data-integrity", "data-lineage", "application-logic", "observability",
        "test-quality", "architecture", "performance", "compliance", "privacy",
        "documentation", "dependency",
    ]
)
_EXPECTED_PUSH = sorted(["security", "data-integrity", "data-lineage", "observability"])


def test_full_active_sets():
    assert active_agents("pull_request") == _EXPECTED_PR
    assert active_agents("push") == _EXPECTED_PUSH


@pytest.mark.parametrize("name", _EXPECTED_PR)
def test_every_agent_prompt_loads_and_demands_json(name):
    spec = get_agent(name)
    assert spec.name == f"review-{name}"
    assert spec.prompt.strip()
    assert "JSON" in spec.prompt


def test_advisory_and_filetrigger_config():
    assert get_agent("documentation").block_threshold is None
    dep = get_agent("dependency")
    assert dep.block_threshold is None and dep.active_when == "file-trigger"
    assert dep.trigger_globs and "pyproject.toml" in dep.trigger_globs
    assert get_agent("data-integrity").block_threshold == "info"  # any finding blocks
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/review/test_registry.py -k "full_active_sets or agent_prompt or advisory_and" -q`
Expected: FAIL — the new agents aren't registered.

- [ ] **Step 3: Create the 11 prompt files** — each in `src/framework_cli/review/agents/`. Use exactly this content (one file per agent):

`data-integrity.md`:
```markdown
You are `review-data-integrity`. Review ONLY the unified diff. Flag data-model and persistence
risks: missing/incorrect validation, nullable/constraint mistakes, migrations that lose or
corrupt data or are not backward-compatible, broken store invariants, and inconsistent writes
across stores. Cite the specific changed line. Return JSON ONLY — a single array of
{"path","line","severity","message","suggestion"} (suggestion optional); [] if none. Any genuine
data-integrity risk is at least "high".
```

`data-lineage.md`:
```markdown
You are `review-data-lineage`. Review ONLY the unified diff. Trace data flow: PII reaching
undocumented stores/logs/external calls, deletion/erasure paths that miss a store, cross-paradigm
writes with no consistency strategy, and missing audit trails for sensitive operations. Cite the
changed line. Return JSON ONLY — an array of {"path","line","severity","message","suggestion"};
[] if none. PII to an undocumented location or a deletion gap is "high".
```

`application-logic.md`:
```markdown
You are `review-application-logic`. Review ONLY the unified diff. Find correctness bugs:
unhandled edge cases (empty/null/boundary/concurrent), incorrect conditionals, missing error
handling, swallowed exceptions, and recovery paths that don't actually recover. Cite the changed
line. Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if
none. Report only concrete bugs you can point to, not style.
```

`observability.md`:
```markdown
You are `review-observability`. Review ONLY the unified diff. Flag new code paths with no
metric/log/trace, error paths not logged with the correlation id, missing or undefined SLO
thresholds for new endpoints, and broken context propagation. Cite the changed line. Return JSON
ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none. A new
untraced/unmetered code path is "high".
```

`test-quality.md`:
```markdown
You are `review-test-quality`. Review ONLY the unified diff. Flag tests that could pass
regardless of the code's behaviour (asserting on mocks, tautologies, no meaningful assertion),
mocks that don't match the real interface, unhappy paths that don't assert failure behaviour, and
NFR heuristics left unaddressed. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. A test that can't fail is "high".
```

`architecture.md`:
```markdown
You are `review-architecture`. Review ONLY the unified diff. Flag layering violations (e.g.
routes calling the database directly), circular dependencies, and inappropriate coupling across
module boundaries. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. A layering violation or circular
dependency is "high".
```

`performance.md`:
```markdown
You are `review-performance`. Review ONLY the unified diff. Flag N+1 queries, accidentally
quadratic algorithms on unbounded inputs, allocation in hot paths, missed obvious caching, and
connection-pool exhaustion. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. A clear regression against a
defined SLO is "high"; speculative micro-optimisation is "low".
```

`compliance.md`:
```markdown
You are `review-compliance`. Review ONLY the unified diff. Flag GDPR/retention/audit gaps:
personal data kept with no retention or deletion path, right-to-erasure not covered, and
sensitive operations with no audit log. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. A clear regulatory violation is
"high".
```

`privacy.md`:
```markdown
You are `review-privacy`. Review ONLY the unified diff. Flag PII logged or echoed, collection of
PII not needed for the stated purpose, and retention beyond purpose. Cite the changed line.
Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none. PII
in logs or unnecessary PII collection is "high".
```

`documentation.md`:
```markdown
You are `review-documentation` (advisory). Review ONLY the unified diff. Note undocumented public
interfaces, new config vars missing from `.env.example`, complex logic without explanation, and a
stale API spec. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. These are advisory: use "low"/"info".
```

`dependency.md`:
```markdown
You are `review-dependency` (advisory). Review ONLY the unified diff, which touches dependency
manifests. For each added/changed dependency, note: whether it is justified, maintenance health
and supply-chain risk, and whether an existing dependency already covers the need. Cite the
changed line in the manifest. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. These are advisory: use "low"/"info".
```

- [ ] **Step 4: Register the agents** — in `src/framework_cli/review/registry.py`, add these entries to `_SPECS` (after `security`). To keep it DRY, you may instead build them from a table, but explicit entries are fine:

```python
    "data-integrity": AgentSpec("review-data-integrity", _prompt("data-integrity"), "info", "always", DEFAULT_MODEL, on_push=True),
    "data-lineage": AgentSpec("review-data-lineage", _prompt("data-lineage"), "high", "always", DEFAULT_MODEL, on_push=True),
    "application-logic": AgentSpec("review-application-logic", _prompt("application-logic"), "info", "always", DEFAULT_MODEL),
    "observability": AgentSpec("review-observability", _prompt("observability"), "high", "always", DEFAULT_MODEL, on_push=True),
    "test-quality": AgentSpec("review-test-quality", _prompt("test-quality"), "high", "always", DEFAULT_MODEL),
    "architecture": AgentSpec("review-architecture", _prompt("architecture"), "high", "always", DEFAULT_MODEL),
    "performance": AgentSpec("review-performance", _prompt("performance"), "high", "always", DEFAULT_MODEL),
    "compliance": AgentSpec("review-compliance", _prompt("compliance"), "high", "always", DEFAULT_MODEL),
    "privacy": AgentSpec("review-privacy", _prompt("privacy"), "high", "always", DEFAULT_MODEL),
    "documentation": AgentSpec("review-documentation", _prompt("documentation"), None, "always", DEFAULT_MODEL),
    "dependency": AgentSpec(
        "review-dependency", _prompt("dependency"), None, "file-trigger", DEFAULT_MODEL,
        trigger_globs=("pyproject.toml", "uv.lock", "package.json", "package-lock.json"),
    ),
```

(These use positional args matching `AgentSpec(name, prompt, block_threshold, active_when, model, ...)`.)

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/review -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS — `active_agents("pull_request")` = 12 names (the 11 here + security), `active_agents("push")` = 4; every prompt loads. mypy + ruff clean.

> Note: gitleaks runs in this repo's pre-commit/CI — the prompts are prose (no secrets); keep them so.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/agents/ src/framework_cli/review/registry.py tests/review/test_registry.py CLAUDE.md
```
```bash
git commit -m "feat(review): the 10 always agents + review-dependency (prompts + registry)"
```

---

### Task 5: The `review-agents` command + file-trigger self-skip

**Files:** Modify `src/framework_cli/cli.py`; Test `tests/test_cli.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_cli.py`:

```python
import json as _json


def test_review_agents_lists_pr_and_push(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    pr = _json.loads(runner.invoke(app, ["review-agents", "--event", "pull_request"]).output)
    push = _json.loads(runner.invoke(app, ["review-agents", "--event", "push"]).output)
    assert "security" in pr and "documentation" in pr
    assert set(push) == {"security", "data-integrity", "data-lineage", "observability"}


def test_review_dependency_skips_when_no_dep_files(monkeypatch):
    import framework_cli.cli as cli_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/src/app/main.py\n")

    def _should_not_run(diff, spec):
        raise AssertionError("LLM must not run when not triggered")

    monkeypatch.setattr(cli_mod, "_review_run", _should_not_run)
    result = runner.invoke(app, ["review", "dependency"])
    assert result.exit_code == 0
    assert "not triggered" in result.output


def test_review_dependency_runs_when_dep_file_changed(monkeypatch):
    import framework_cli.cli as cli_mod
    from framework_cli.review.findings import Finding

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_mod, "_review_diff", lambda: "+++ b/pyproject.toml\n")
    monkeypatch.setattr(cli_mod, "_review_run", lambda diff, spec: [Finding("pyproject.toml", 1, "low", "m")])
    result = runner.invoke(app, ["review", "dependency"])
    assert result.exit_code == 0  # advisory → neutral, never blocks
    assert "neutral" in result.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "review_agents or review_dependency" -q`
Expected: FAIL — no `review-agents` command; `review` has no file-trigger skip (the LLM seam would be called).

- [ ] **Step 3: Implement** — in `src/framework_cli/cli.py`:

Add to the review imports:
```python
from framework_cli.review.diff import changed_files, matches_globs
from framework_cli.review.registry import active_agents
```

Add the `review-agents` command (near the `review` command):
```python
@app.command(name="review-agents")
def review_agents(
    event: str = typer.Option("", "--event", help="GitHub event name (default: $GITHUB_EVENT_NAME)."),
) -> None:
    """Print the JSON array of review agents active for the event (drives the CI matrix)."""
    import json

    resolved = event or os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    typer.echo(json.dumps(active_agents(resolved)))
```

In the `review` command, insert the file-trigger self-skip **inside** the existing `try` block, right after `findings = _review_run(...)` is currently called — restructure that try block to compute the diff once and skip before the LLM call. Replace the current try/except block (the one that does `findings = _review_run(_review_diff(), spec)` … `to_check_run`) with:

```python
    try:
        diff = _review_diff()
        if spec.trigger_globs and not matches_globs(changed_files(diff), spec.trigger_globs):
            payload = neutral_payload(
                spec.name, f"not triggered (no {', '.join(spec.trigger_globs)} change)"
            )
            post_or_skip(payload, token=token, repo=repo, sha=sha)
            typer.echo(f"{spec.name}: skipped (not triggered)")
            raise typer.Exit(0)
        findings = _review_run(diff, spec)
        payload = to_check_run(spec, findings)
    except typer.Exit:
        raise  # the not-triggered skip (and any Exit) must propagate, not become neutral
    except Exception as exc:  # noqa: BLE001 - infra failure must not block CI
        payload = neutral_payload(spec.name, f"review could not run: {exc}")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        typer.echo(f"{spec.name}: neutral (could not run: {exc})", err=True)
        raise typer.Exit(0) from exc
```

(The `except typer.Exit: raise` is essential: `typer.Exit` subclasses `RuntimeError`, so without it the broad `except Exception` would swallow the not-triggered `Exit(0)`.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (the new tests + all 7a CLI/review tests, incl. the non-triggered-skip and the security-path tests unchanged); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(review): review-agents command + file-trigger self-skip"
```

---

### Task 6: Generated `ci.yml` review matrix

**Files:** Modify `src/framework_cli/template/.github/workflows/ci.yml.jinja`; Test `tests/test_copier_runner.py`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_copier_runner.py`:

```python
def test_ci_review_matrix(tmp_path: Path):
    import yaml

    dest = tmp_path / "proj"
    render_project(
        dest,
        {"project_name": "Demo", "project_slug": "demo", "package_name": "demo", "python_version": "3.12"},
    )
    text = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "framework review-agents" in text
    assert "fromJSON(needs.review-plan.outputs.agents)" in text
    doc = yaml.safe_load(text)
    assert "review-plan" in doc["jobs"] and "review" in doc["jobs"]
    assert doc["jobs"]["review"]["needs"] == ["test", "contract", "review-plan"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_ci_review_matrix -q`
Expected: FAIL — the current `review` job runs a single `framework review security`, no `review-plan`/matrix.

- [ ] **Step 3: Implement** — in `src/framework_cli/template/.github/workflows/ci.yml.jinja`, replace the entire `review` job (the comment + the `review:` job) with:

```yaml
  # Steps 9-10: Layer-3 AI review agents (spec §7). Opt-in: set the ANTHROPIC_API_KEY secret to
  # enable. `review-plan` lists the agents active for this event (all on a PR; the security/
  # data-integrity/data-lineage/observability subset on a push to main); `review` runs them in
  # parallel, each posting a `review-*` GitHub Check Run. Require those checks in branch
  # protection to gate merges. A missing key / API error / untriggered agent → a neutral check
  # (never a spurious CI failure).
  review-plan:
    needs: [test, contract]
    runs-on: ubuntu-latest
    outputs:
      agents: {% raw %}${{ steps.list.outputs.agents }}{% endraw %}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: install the framework CLI at the recorded version
        run: |
          ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"
          uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"
      - id: list
        run: echo "agents=$(framework review-agents --event {% raw %}${{ github.event_name }}{% endraw %})" >> "$GITHUB_OUTPUT"

  review:
    needs: [test, contract, review-plan]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      checks: write
      pull-requests: read
    strategy:
      fail-fast: false
      matrix:
        agent: {% raw %}${{ fromJSON(needs.review-plan.outputs.agents) }}{% endraw %}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - name: install the framework CLI at the recorded version
        run: |
          ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"
          uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"
      - name: review {% raw %}${{ matrix.agent }}{% endraw %}
        env:
          ANTHROPIC_API_KEY: {% raw %}${{ secrets.ANTHROPIC_API_KEY }}{% endraw %}
          GITHUB_TOKEN: {% raw %}${{ github.token }}{% endraw %}
        run: framework review {% raw %}${{ matrix.agent }}{% endraw %}
```

- [ ] **Step 4: Run it to verify it passes + valid YAML**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS. Then confirm the rendered workflow parses and the matrix wiring is right:
```bash
uv run python -c "
import tempfile, pathlib, yaml
from framework_cli.copier_runner import render_project
d = pathlib.Path(tempfile.mkdtemp())/'p'
render_project(d, {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})
doc = yaml.safe_load((d/'.github/workflows/ci.yml').read_text())
print('jobs:', sorted(doc['jobs']))
print('review-plan outputs:', doc['jobs']['review-plan'].get('outputs'))
print('review matrix:', doc['jobs']['review']['strategy']['matrix'])
"
```
Report the output (expect a `review-plan` job with an `agents` output and a `review` job whose `matrix.agent` is the `fromJSON(...)` expression).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(review): generated ci.yml runs the agent matrix (review-plan -> review)"
```

---

## Self-Review

**1. Spec coverage (`docs/superpowers/specs/2026-05-22-review-agent-set-design.md`):**
- §3 `AgentSpec` extensions + the 12-agent table → Tasks 1 (schema + on_push + active_agents) and 4 (the 11 agents + prompts + per-agent thresholds/on_push/trigger_globs).
- §4 `review-agents` command + `changed_files` + file-trigger self-skip + advisory `to_check_run` → Tasks 3 (diff helpers), 2 (advisory), 5 (command + self-skip).
- §5 CI matrix (`review-plan`→`review`, push subset via the event, `fromJSON`) → Task 6.
- §6 testing: active sets (Tasks 1, 4), advisory (2), changed_files/matches_globs (3), file-trigger skip+fire + the command (5), the render (6); all hermetic.
- Battery agents deferred (Plan 8) — none registered here; `active_agents` excludes `active_when=="battery"`.

**2. Placeholder scan:** none — every prompt is spelled out; every code edit shows the exact replacement; every test is complete. The `# noqa: BLE001` + the `except typer.Exit: raise` are explicit, intentional.

**3. Type consistency:** `AgentSpec(name, prompt, block_threshold: Severity|None, active_when, model, on_push=False, trigger_globs=None)` is used consistently in Tasks 1 and 4 (positional entries match the field order). `active_agents(event)`, `changed_files(diff)`, `matches_globs(paths, globs)`, the advisory `to_check_run` branch, and the `review`/`review-agents` commands all line up with their tests. The `review` command reuses the existing `_review_diff`/`_review_run` seams (now called with the single fetched `diff`).

**Sequencing note:** Task 1 ships the schema + `active_agents` exercised against `security` alone; Task 4 expands the registry and tightens the active-set tests to the full expected names. The file-trigger logic (Task 5) depends on `dependency` being registered (Task 4) and the diff helpers (Task 3).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-review-agent-set.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.

**2. Inline Execution** — execute here with checkpoints.

Which approach?

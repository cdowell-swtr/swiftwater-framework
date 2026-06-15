# `--with claudesubscriptioncli` (FWK16, Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠ Execute only after FWK13 (LLM profiles) has merged to `master` (v0.2.7).** This builds on the profile-aware `llm` service and its duck-typed `reset_hint` exhaustion seam. Start a fresh branch `fwk16-claudesubscriptioncli` off the merged `master`.

**Goal:** Add the `--with claudesubscriptioncli` battery — the Claude **subscription** provider (via the `claude` CLI / `litellm-claude-cli` plugin) — so a generated project can name `provider: "claude-cli"` in an LLM profile and route that profile through the subscription instead of the paid API.

**Architecture:** `requires=("llm",)`, `obs="rides-existing"`. Adds the `litellm-claude-cli` dep as a PEP 508 git ref + a startup call to the plugin's idempotent `register()` (which installs the `claude-cli` custom provider into `litellm.custom_provider_map`). The base `llm` service is unchanged — a `claude-cli` profile is keyless (outside `KEY_REQUIRING_PROVIDERS`) and `ClaudeExhausted` (carrying `reset_hint`, not a `RateLimitError`) is caught by the existing duck-typed exhaustion seam.

**Tech Stack:** Python 3.12, Copier/Jinja template payload, LiteLLM + `litellm-claude-cli` (`@v0.1.1`), FastAPI, pytest. Spec: `docs/superpowers/specs/2026-06-15-llm-profiles-and-subscription-design.md` (§Slice 2).

---

## Execution notes

- **Review-model policy** ([[subagent-review-model-pattern]]): Sonnet implementers; **Opus** on the registration/wiring task + branch-end. **Implementers stage, controller commits** ([[subagent-implementers-stop-before-commit]], [[commit-gate-hook-timing]] — separate `git add` then `git commit`; if a `git add` is blocked by the gate, stage `PLAN.md`/`ACTION_LOG.md` first, then the rest).
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): render the **resolved** set and `uv sync` (this fetches `litellm-claude-cli` from GitHub — network needed). Grep the RENDERED project, not just source.
- This slice re-touches builder-facing payload → **release v0.2.8** after merge (Task 8).
- **No base-`llm` service change** — if you find yourself editing `llm/service.py`, stop: the duck-typed exhaustion + keyless-by-default seam already handles `claude-cli`.

### Helper: render the resolved claudesubscriptioncli project (run from repo root)
```bash
export TMPDIR=/var/tmp
rm -rf /tmp/subwork
uv run python -c "from pathlib import Path; from framework_cli.batteries import resolve; from framework_cli.copier_runner import render_project; render_project(Path('/tmp/subwork'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':resolve(['claudesubscriptioncli'])})"
cd /tmp/subwork && uv sync && cd -
```
`resolve(['claudesubscriptioncli'])` → `['claudesubscriptioncli','llm']` (dependency closure), so `llm/` renders too. `uv sync` fetches `litellm-claude-cli` from the git ref.

---

## File Structure

- Modify: `src/framework_cli/batteries.py` — register the `claudesubscriptioncli` BatterySpec (framework source).
- Modify: `src/framework_cli/template/pyproject.toml.jinja` — `litellm-claude-cli` PEP 508 dep under the guard.
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja` — startup `register()` call under the guard.
- Modify: `src/framework_cli/template/SECRETS.md.jinja` (or README) — the runtime caveat.
- Create: `src/framework_cli/template/tests/unit/{{ 'test_claudesubscriptioncli.py' if 'claudesubscriptioncli' in batteries else '' }}.jinja` — register + routing + exhaustion (mocked CLI) + a gated live smoke.
- Modify: `tests/acceptance/test_rendered_project.py` — a `claudesubscriptioncli` acceptance test rendering the **resolved** set.
- Framework source: `PLAN.md`, `ACTION_LOG.md` per commit; release files (Task 8).

---

## Task 1: Register the `claudesubscriptioncli` BatterySpec

**Files:** Modify `src/framework_cli/batteries.py`; Test: `tests/test_batteries.py`, `tests/test_obs_completeness.py` (existing, parametrized).

- [ ] **Step 1: Add the spec.** In the `_BATTERIES` dict (after the `"llm"` entry):
```python
    "claudesubscriptioncli": BatterySpec(
        "claudesubscriptioncli",
        "Route an LLM profile through your Claude subscription via the claude CLI "
        "(litellm-claude-cli). requires the llm battery; needs an authenticated `claude` on PATH",
        requires=("llm",),
        obs="rides-existing",
    ),
```

- [ ] **Step 2: Confirm `requires` closure works.**
Run: `uv run python -c "from framework_cli.batteries import resolve; print(resolve(['claudesubscriptioncli']))"`
Expected: `['claudesubscriptioncli', 'llm']` (sorted dependency-closed set).

- [ ] **Step 3: Confirm the registry + obs tests pass.**
Run: `uv run pytest tests/test_batteries.py "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[claudesubscriptioncli]" -q`
Expected: PASS. (Rendered alone, the battery adds no obs files and no claudesubscriptioncli-guarded file lives in the `llm/` dir, so the render is clean and `rides-existing` holds — no obs-test change needed.)

- [ ] **Step 4: Lint + commit.** `uv run ruff check src/framework_cli/batteries.py`. Stage `batteries.py` + `PLAN.md`/`ACTION_LOG.md`; commit `feat(fwk16): register claudesubscriptioncli BatterySpec`.

---

## Task 2: Add the `litellm-claude-cli` dependency (PEP 508 git ref)

**Files:** Modify `src/framework_cli/template/pyproject.toml.jinja`.

- [ ] **Step 1: Add the guarded dep.** In the `dependencies = [` list, after the `{% if "llm" in batteries %}    "litellm>=1.88.1",` entry:
```jinja
{% endif %}{% if "claudesubscriptioncli" in batteries %}    "litellm-claude-cli @ git+https://github.com/cdowell-swtr/litellm-claude-cli@v0.1.1",
{% endif %}
```
(Match the surrounding `{% endif %}{% if ... %}    "<dep>",\n` chaining exactly — the llm entry currently ends the chain before `{% endif %}]`, so insert this between them.)

- [ ] **Step 2: Render the resolved set + confirm the dep + that it resolves.**
Render via the helper, then:
Run: `grep -n "litellm-claude-cli" /tmp/subwork/pyproject.toml`
Expected: shows the `@ git+…@v0.1.1` PEP 508 ref.
Run: `cd /tmp/subwork && uv lock && uv sync` → succeeds (fetches the package from GitHub).

- [ ] **Step 3: Confirm a no-battery baseline omits it.** Render `/tmp/subbase` with `batteries: []`; `grep -c "litellm-claude-cli" /tmp/subbase/pyproject.toml` → `0`. And an `llm`-only render (`['llm']`) also omits it (`grep -c` → `0`) — the dep is gated on `claudesubscriptioncli`, not `llm`.

- [ ] **Step 4: Format-check + commit.** `cd /tmp/subwork && uv run ruff format --check pyproject.toml`. Stage `pyproject.toml.jinja` + PLAN/ACTION_LOG; `feat(fwk16): litellm-claude-cli PEP 508 dep under the guard`.

---

## Task 3: Wire `register()` at app startup + the runtime-caveat docs (Opus review)

**Files:** Modify `main.py.jinja`, `SECRETS.md.jinja`; Create the unit test file (register/routing/exhaustion).

- [ ] **Step 1: Write the failing unit tests.**
Path: `src/framework_cli/template/tests/unit/{{ 'test_claudesubscriptioncli.py' if 'claudesubscriptioncli' in batteries else '' }}.jinja`
```python
"""claudesubscriptioncli battery — registration + keyless routing + exhaustion (mocked CLI)."""

import litellm


def test_register_installs_claude_cli_provider():
    import litellm_claude_cli

    litellm.custom_provider_map = []
    litellm_claude_cli.register()
    providers = [p["provider"] for p in litellm.custom_provider_map]
    assert "claude-cli" in providers


def test_register_is_idempotent():
    import litellm_claude_cli

    litellm.custom_provider_map = []
    litellm_claude_cli.register()
    litellm_claude_cli.register()
    assert [p["provider"] for p in litellm.custom_provider_map].count("claude-cli") == 1


def test_create_app_registers_claude_cli_when_battery_active():
    # The startup guard calls register() during create_app.
    litellm.custom_provider_map = []
    from {{ package_name }}.config.settings import Settings
    from {{ package_name }}.main import create_app

    create_app(Settings(llm_api_key="k", serve_spa=False))
    assert "claude-cli" in [p["provider"] for p in (litellm.custom_provider_map or [])]


def test_claude_cli_profile_routes_keyless(monkeypatch):
    # A profile with provider=claude-cli routes to claude-cli/<model> with no api_key.
    from {{ package_name }}.config.settings import LLMProfile, Settings
    from {{ package_name }}.llm.metrics import LLMMetrics
    from {{ package_name }}.llm.service import LLMService

    captured = {}

    class _Msg:
        content = "hi"
        tool_calls = None

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]
        usage = None

    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp())
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    s = Settings(
        llm_api_key="",
        llm_profiles={"sub": LLMProfile(provider="claude-cli", model="claude-sonnet-4-6")},
    )
    LLMService(s, metrics=LLMMetrics()).complete([{"role": "user", "content": "x"}], profile="sub")
    assert captured["model"] == "claude-cli/claude-sonnet-4-6"
    assert "api_key" not in captured


def test_claude_exhausted_maps_to_llm_exhausted(monkeypatch):
    # The real ClaudeExhausted (carries reset_hint, not a RateLimitError) is caught by the
    # service's duck-typed exhaustion seam -> LLMExhausted, with the hint preserved.
    from litellm_claude_cli import ClaudeExhausted

    from {{ package_name }}.config.settings import LLMProfile, Settings
    from {{ package_name }}.llm.errors import LLMExhausted
    from {{ package_name }}.llm.metrics import LLMMetrics
    from {{ package_name }}.llm.service import LLMService

    def boom(**_):
        try:
            raise ClaudeExhausted("subscription used up", reset_hint="resets 11:30am")
        except ClaudeExhausted as inner:
            raise RuntimeError("litellm wrapped it") from inner

    monkeypatch.setattr(litellm, "completion", boom)
    s = Settings(
        llm_api_key="",
        llm_profiles={"sub": LLMProfile(provider="claude-cli", model="m")},
    )
    import pytest

    with pytest.raises(LLMExhausted) as ei:
        LLMService(s, metrics=LLMMetrics()).complete(
            [{"role": "user", "content": "x"}], profile="sub"
        )
    assert ei.value.reset_hint == "resets 11:30am"
```
> Confirm `ClaudeExhausted("...", reset_hint=...)` constructs in the installed `litellm-claude-cli` (it does — verified `reset_hint` is in its `__init__`). If the kwarg differs, adapt the test minimally.

Render the resolved set, mirror/copy the test, run → confirm RED on the `create_app`-registers test (startup guard not yet added).

- [ ] **Step 2: Add the startup guard** in `main.py.jinja`. After the `{%- if "react" in batteries %}...{%- endif %}` block in `create_app` (before `configure_tracing`):
```jinja
{%- if "claudesubscriptioncli" in batteries %}

    # Register the claude-cli subscription provider so an LLM profile may set
    # provider="claude-cli". Idempotent; needs an authenticated `claude` CLI on PATH at runtime.
    from litellm_claude_cli import register as register_claude_cli

    register_claude_cli()
{%- endif %}
```

- [ ] **Step 3: Add the runtime-caveat docs.** In `SECRETS.md.jinja`, add a guarded note (place it near the other key/secret guidance):
```jinja
{%- if "claudesubscriptioncli" in batteries %}

## Claude subscription provider (claudesubscriptioncli)

A profile with `provider: "claude-cli"` (set via `APP_LLM_PROFILES`) routes through your
**Claude subscription** using the `claude` CLI — **no API key**. It works only where the
`claude` CLI is **installed and authenticated** (run `claude login`) on PATH at runtime.
It is deliberately NOT baked into the container image (auth-bound, personal). Use it for
local/dev or an environment where you have provisioned an authenticated `claude`.
{%- endif %}
```

- [ ] **Step 4: Re-render + run green.**
Run: `cd /tmp/subwork && uv run pytest tests/unit/test_claudesubscriptioncli.py -q` → all PASS.
Run: `uv run mypy src/demo` (or at least `src/demo/main.py`) + `uv run ruff check`/`ruff format --check` on the changed rendered files → clean. (If mypy flags `litellm_claude_cli` missing stubs, add a targeted `[[tool.mypy.overrides]]` for `litellm_claude_cli.*` under the claudesubscriptioncli guard in `pyproject.toml.jinja`, mirroring the litellm override.)

- [ ] **Step 5: Stage** `main.py.jinja`, `SECRETS.md.jinja`, the unit test (+ `pyproject.toml.jinja` if a mypy override was added) + PLAN/ACTION_LOG; commit `feat(fwk16): register claude-cli at startup + runtime-caveat docs`. (Opus code-quality review after this task.)

---

## Task 4: Gated live smoke (real `claude` CLI)

**Files:** Modify the unit test file (add a gated smoke).

- [ ] **Step 1: Add a gated live smoke** to the test file:
```python
import os

import pytest


@pytest.mark.skipif(
    os.environ.get("LLM_SUBSCRIPTION_SMOKE") != "1",
    reason="set LLM_SUBSCRIPTION_SMOKE=1 with an authenticated `claude` CLI to run",
)
def test_live_subscription_completion():
    from {{ package_name }}.config.settings import LLMProfile, Settings
    from {{ package_name }}.llm.metrics import LLMMetrics
    from {{ package_name }}.llm.service import LLMService
    from {{ package_name }}.main import create_app

    create_app(Settings(llm_api_key="", serve_spa=False))  # registers claude-cli
    s = Settings(
        llm_api_key="",
        llm_profiles={"sub": LLMProfile(provider="claude-cli", model="claude-sonnet-4-6")},
    )
    result = LLMService(s, metrics=LLMMetrics()).complete(
        [{"role": "user", "content": "Reply with the single word: ok"}], profile="sub"
    )
    assert result.text.strip()
```

- [ ] **Step 2: Confirm it SKIPS by default.** Run: `cd /tmp/subwork && uv run pytest tests/unit/test_claudesubscriptioncli.py -q` → the smoke is skipped (`s` in the summary), others pass. (Optionally, if you have an authenticated `claude`, run with `LLM_SUBSCRIPTION_SMOKE=1` once and confirm a real completion — record the result in the report.)

- [ ] **Step 3: Format-check + stage** the test file + PLAN/ACTION_LOG; `test(fwk16): gated live subscription smoke`.

---

## Task 5: Acceptance test (render the resolved set + run)

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Add the acceptance test** (mirror `test_rendered_project_with_llm_battery_passes`, but render the **resolved** set so `llm` is present). Add `from framework_cli.batteries import resolve` to the imports if not present, then:
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_claudesubscriptioncli_battery_passes(tmp_path: Path):
    # claudesubscriptioncli requires llm, so render the dependency-closed set (as the CLI does).
    # Confirms the litellm-claude-cli git dep installs, register() wires at startup, and the
    # battery's unit tests (registration + keyless routing + ClaudeExhausted mapping) run.
    data = {**DATA, "batteries": resolve(["claudesubscriptioncli"])}
    dest = tmp_path / "demo"
    render_project(dest, data)

    assert (dest / "tests" / "unit" / "test_claudesubscriptioncli.py").exists(), (
        "the claudesubscriptioncli unit test was not rendered"
    )
    assert "litellm-claude-cli @ git+" in (dest / "pyproject.toml").read_text(), (
        "the litellm-claude-cli PEP 508 dep was not rendered"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed (could not fetch litellm-claude-cli?)"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the claudesubscriptioncli project:\n"
        + result.stdout
        + result.stderr
    )
```

- [ ] **Step 2: Run it.** `TMPDIR=/var/tmp uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_with_claudesubscriptioncli_battery_passes" -q` → PASS (needs Docker + network for the git dep).

- [ ] **Step 3: Format-check + stage** the acceptance file + PLAN/ACTION_LOG; `test(fwk16): acceptance for the claudesubscriptioncli battery`.

---

## Task 6: Full render + acceptance + obs-completeness + eval coupling

- [ ] **Step 1: Source gate.** `uv run pytest -q -k "not acceptance" && uv run ruff check . && uv run ruff format --check . && uv run mypy src` → green.
- [ ] **Step 2: obs + copier + battery tests.** `uv run pytest tests/test_obs_completeness.py tests/test_copier_runner.py tests/test_batteries.py -q` → PASS (claudesubscriptioncli `rides-existing` holds; it renders cleanly alone).
- [ ] **Step 3: Render the resolved project, grep stragglers.** Confirm no broken `llm`-less references; confirm `register_claude_cli` appears in the rendered `main.py` only when the battery is active (and NOT in an `llm`-only render).
- [ ] **Step 4: Eval-fixture coupling** ([[eval-fixtures-coupled-to-template]]): `git grep -l "claude-cli\|litellm-claude-cli\|claudesubscriptioncli" tests/eval/fixtures/ || echo "no coupling"`. Re-anchor if any.
- [ ] **Step 5: Commit** any fixups (skip if none) with PLAN/ACTION_LOG.

---

## Task 7: Branch-end review

- [ ] **Step 1: Branch-end Opus review** ([[subagent-review-model-pattern]]) over the full branch diff. Focus: the dep is a PEP 508 ref (pip-installable, not uv-sources); `register()` is wired once and idempotent; guard isolation (no claude-cli symbols in an `llm`-only or no-battery render; the dep gated on `claudesubscriptioncli` not `llm`); the base `llm` service is genuinely unchanged; the keyless-routing + `ClaudeExhausted`→`LLMExhausted` behavior; the runtime caveat is documented; the `requires` closure is exercised by the acceptance test. Address findings; re-run Task 6.
- [ ] **Step 2: Verify subagent commits landed** ([[subagent-implementers-stop-before-commit]]): `git status --short && git log --oneline master..HEAD`.

---

## Task 8: PLAN/ACTION_LOG + release v0.2.8 + finish

- [ ] **Step 1: PLAN/ACTION_LOG.** Move FWK16 → Done; append completion entry. Commit.
- [ ] **Step 2: Cut v0.2.8** ([[release-cut-procedure]]): bump `pyproject` 0.2.7→0.2.8, `uv lock`, `DOGFOOD_COMMIT`→`"v0.2.8"`; `uv build` → 0.2.8 artifacts; version-consistency tests; commit `chore(release): v0.2.8`. Bundle into the FWK16 PR.
- [ ] **Step 3: Finish the branch** ([[finishing-a-development-branch]]): push `fwk16-claudesubscriptioncli`, open one PR, confirm `gate`/`build`/`render-complete` green (the render-matrix `full` combo now installs the git dep — watch for a network flake), squash-merge, tag `v0.2.8` → `release.yml`, verify the published Release (2 assets), grep `master` for a marker ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** battery + `requires` + `rides-existing` (Task 1) · PEP 508 dep (Task 2) · `register()` startup wiring (Task 3) · keyless routing + `ClaudeExhausted`→`LLMExhausted` via the existing seam, no service change (Task 3 tests) · runtime caveat docs (Task 3) · gated live smoke (Task 4) · acceptance with `requires` resolved (Task 5) · obs-completeness unchanged-but-passing + eval coupling (Task 6) · release (Task 8). The `obs`-test `requires` change the spec anticipated turned out **unnecessary** (no claudesubscriptioncli-guarded file in the `llm/` dir → renders clean alone → `rides-existing` holds); only the acceptance test needs resolution — noted in Task 1 Step 3 and Task 5.
- **Type/name consistency:** uses `litellm_claude_cli.register()` and `ClaudeExhausted(msg, *, reset_hint=…)` (verified against the installed package); profile `provider="claude-cli"` → `ResolvedProfile.model_id == "claude-cli/<model>"`, `requires_key False` (FWK13). No new framework symbols.
- **No placeholders:** every code/jinja/test block is complete.

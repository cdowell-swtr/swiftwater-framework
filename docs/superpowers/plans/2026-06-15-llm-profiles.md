# LLM Profiles (FWK13, Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the `--with llm` battery from a single configured model to **named LLM profiles** — selectable per call with per-call overrides — with per-profile cost metrics, a profile-aware key fail-fast, and duck-typed exhaustion that makes the base runtime subscription-ready without importing any subscription plugin.

**Architecture:** Add `LLMProfile` to settings + an `llm_profiles` JSON map; a new `llm/profiles.py` resolves `(default profile ← named overlay ← per-call override)` to a `ResolvedProfile`; `LLMService` takes a resolved profile per call, fails fast on a missing key for key-requiring providers, and maps any cause-chain exception carrying a `reset_hint` attribute to `LLMExhausted`. Metrics gain a bounded `profile` label on the spend series.

**Tech Stack:** Python 3.12, Copier/Jinja template payload, LiteLLM, pydantic-settings, FastAPI, pytest. Spec: `docs/superpowers/specs/2026-06-15-llm-profiles-and-subscription-design.md`.

---

## Execution notes (read before starting)

- **Review-model policy** ([[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for trivial); code-quality review → **Opus**; branch-end whole-branch review → **Opus**. Pass `model` explicitly.
- **Gate cadence** ([[gate-cadence-framework-slices]]): do not run the full `framework gate` per commit. Controller finishes commits; light per-task review + dispatched Opus review on the substantive code tasks (profiles, metrics, service) + one branch-end Opus review.
- **Implementers stage, controller commits** ([[subagent-implementers-stop-before-commit]]). Each commit needs a `PLAN.md`/`ACTION_LOG.md` change staged ([[commit-gate-hook-timing]]: separate `git add` then `git commit`, keep "commit" out of Bash *descriptions*).
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): tests run inside a *generated* project. **Grep the RENDERED project for stragglers, not just source** (the rename slice's lesson — a label or path can be missed in source review yet break the render).
- **This slice re-touches the released `llm` battery → it warrants a release (v0.2.7)** after merge (Task 9), per [[release-cut-procedure]].

### Helper: render the llm project for the TDD loop (run from repo root)
```bash
export TMPDIR=/var/tmp
rm -rf /tmp/llmwork
uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('/tmp/llmwork'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['llm']})"
cd /tmp/llmwork && uv sync && cd -
```
(Generated project uses `[dependency-groups]` → plain `uv sync`, NOT `--extra dev`.) Re-render after each template edit; run tests with `cd /tmp/llmwork && uv run pytest tests/unit/test_llm_unit.py tests/functional/test_llm.py -q`.

---

## File Structure

All paths are template payload unless noted. The `llm` module dir is the brace-named
`src/framework_cli/template/src/{{package_name}}/{% if "llm" in batteries %}llm{% endif %}/`.

- Modify: `.../config/settings.py.jinja` — `LLMProfile` model + `llm_profiles` field.
- Create: `<llm-dir>/profiles.py` — `KEY_REQUIRING_PROVIDERS`, `ResolvedProfile`, `resolve_profile`.
- Modify: `<llm-dir>/errors.py` — `LLMExhausted.reset_hint`.
- Modify: `<llm-dir>/metrics.py` — `profile` label on calls/tokens/cost.
- Modify: `<llm-dir>/service.py` — profile-aware calls, key fail-fast, duck-typed exhaustion.
- Modify: `.../routes/{{ 'llm.py' ... }}.jinja` — optional `profile` in the demo route.
- Modify: `infra/observability/prometheus/alerts/{{ 'llm_alerts.yml' ... }}.jinja` — per-profile alert.
- Modify: `infra/observability/grafana/dashboards/{{ 'llm.json' ... }}.jinja` — per-profile panels.
- Modify: `tests/unit/{{ 'test_llm_unit.py' ... }}.jinja`, `tests/functional/{{ 'test_llm.py' ... }}.jinja`.
- Framework source: `PLAN.md`, `ACTION_LOG.md` per commit; `pyproject.toml`/`uv.lock`/`dogfood.py` at release (Task 9).

---

## Task 1: `LLMExhausted.reset_hint` (enables duck-typed exhaustion)

**Files:** Modify `<llm-dir>/errors.py`; Modify `tests/unit/{{ 'test_llm_unit.py' ... }}.jinja`.

- [ ] **Step 1: Append a failing test**
```python
def test_exhausted_carries_reset_hint():
    from {{ package_name }}.llm.errors import LLMExhausted

    exc = LLMExhausted("slow down", reset_hint="resets 11:30am")
    assert exc.reset_hint == "resets 11:30am"
    assert str(exc) == "slow down"


def test_exhausted_reset_hint_defaults_none():
    from {{ package_name }}.llm.errors import LLMExhausted

    assert LLMExhausted("x").reset_hint is None
```

- [ ] **Step 2: Render + run → confirm red** (`TypeError: ... unexpected keyword argument 'reset_hint'`).
Run: `cd /tmp/llmwork && uv run pytest tests/unit/test_llm_unit.py -k reset_hint -q`

- [ ] **Step 3: Implement** — replace the `LLMExhausted` class body in `errors.py`:
```python
class LLMExhausted(LLMError):
    """The provider rejected the call for rate-limit / quota reasons (retry later).

    `reset_hint` is an optional human string (e.g. "resets 11:30am") surfaced by
    providers that know when capacity returns — e.g. the claude-cli subscription
    backend's ClaudeExhausted. Any cause-chain exception exposing a `reset_hint`
    attribute is treated as exhaustion by the service (duck-typed, no plugin import).
    """

    def __init__(self, message: str, *, reset_hint: str | None = None) -> None:
        super().__init__(message)
        self.reset_hint = reset_hint
```

- [ ] **Step 4: Re-render + run green.** Run: `cd /tmp/llmwork && uv run pytest tests/unit/test_llm_unit.py -k reset_hint -q` → PASS. Then `uv run ruff format --check src/demo/llm/errors.py`.

- [ ] **Step 5: Stage** (`git add` the two files; controller commits): `feat(fwk13): LLMExhausted carries reset_hint`.

---

## Task 2: `LLMProfile` model + `llm_profiles` setting

**Files:** Modify `.../config/settings.py.jinja`.

> `LLMProfile` lives in `settings.py` (not `profiles.py`) to avoid a cycle: `profiles.py` imports `Settings`, so `Settings` must not import from `profiles.py`.

- [ ] **Step 1: Add the `LLMProfile` model + field.** In `settings.py.jinja`, the existing `{%- if "llm" in batteries %}` import block adds `from pydantic import SecretStr`. Change it to also import `BaseModel`, and define the model above the `Settings` class (still guarded):
```jinja
{%- if "llm" in batteries %}
from pydantic import BaseModel, SecretStr
{%- endif %}
```
Then, immediately before `class Settings(BaseSettings):`, add (guarded):
```jinja
{%- if "llm" in batteries %}


class LLMProfile(BaseModel):
    """One named LLM config. Unset fields inherit the `default` profile (the llm_* settings).

    Defined as a JSON map in APP_LLM_PROFILES, e.g.
    APP_LLM_PROFILES='{"smart":{"provider":"anthropic","model":"claude-opus-4-8"},
                       "cheap":{"model":"claude-haiku-4-5-20251001"}}'
    """

    provider: str | None = None
    model: str | None = None
    api_key: SecretStr | None = None
    max_tokens: int | None = None
    temperature: float | None = None
{%- endif %}
```
Add the field inside the existing llm settings block (after `llm_api_key`):
```jinja
    llm_api_key: SecretStr = SecretStr("")
    # Additional named profiles (JSON in APP_LLM_PROFILES). "default" is reserved — it is
    # the llm_* fields above, not a key here. Each profile's unset fields inherit default.
    llm_profiles: dict[str, "LLMProfile"] = {}
{%- endif %}
```

- [ ] **Step 2: Render + verify parse.** Render the helper, then:
Run: `cd /tmp/llmwork && APP_LLM_PROFILES='{"smart":{"model":"claude-opus-4-8"}}' uv run python -c "from demo.config.settings import Settings; s=Settings(llm_api_key='k'); print(s.llm_profiles['smart'].model, s.llm_profiles['smart'].provider)"`
Expected: `claude-opus-4-8 None` (JSON parsed into the typed map; unset provider is None).

- [ ] **Step 3: Verify baseline (no-llm) render omits it.** Render `/tmp/llmbase` with `batteries: []`, then `grep -c "LLMProfile\|llm_profiles" /tmp/llmbase/src/demo/config/settings.py` → `0`.

- [ ] **Step 4: Format-check** the rendered settings; **Stage**: `feat(fwk13): LLMProfile model + llm_profiles setting`.

---

## Task 3: `llm/profiles.py` — profile resolution (TDD)

**Files:** Create `<llm-dir>/profiles.py`; Modify the unit test file.

- [ ] **Step 1: Failing tests**
```python
def _settings(**over):
    from {{ package_name }}.config.settings import Settings

    base = dict(llm_provider="anthropic", llm_model="claude-sonnet-4-6",
                llm_api_key="defkey", llm_max_tokens=4096, llm_temperature=0.0)
    base.update(over)
    return Settings(**base)


def test_resolve_default_profile_uses_llm_fields():
    from {{ package_name }}.llm.profiles import resolve_profile

    r = resolve_profile(_settings())
    assert r.name == "default"
    assert r.model_id == "anthropic/claude-sonnet-4-6"
    assert r.api_key == "defkey"
    assert r.requires_key is True


def test_named_profile_overlays_default():
    from {{ package_name }}.config.settings import LLMProfile
    from {{ package_name }}.llm.profiles import resolve_profile

    s = _settings(llm_profiles={"cheap": LLMProfile(model="claude-haiku-4-5-20251001")})
    r = resolve_profile(s, "cheap")
    # model overridden; provider + key inherited from default
    assert r.model_id == "anthropic/claude-haiku-4-5-20251001"
    assert r.api_key == "defkey"


def test_profile_with_own_key_and_provider():
    from {{ package_name }}.config.settings import LLMProfile
    from {{ package_name }}.llm.profiles import resolve_profile

    s = _settings(llm_profiles={"sub": LLMProfile(provider="claude-cli", model="claude-sonnet-4-6")})
    r = resolve_profile(s, "sub")
    assert r.model_id == "claude-cli/claude-sonnet-4-6"
    assert r.requires_key is False  # claude-cli is keyless (not in KEY_REQUIRING_PROVIDERS)


def test_per_call_overrides_layer_on_top():
    from {{ package_name }}.llm.profiles import resolve_profile

    r = resolve_profile(_settings(), "default", provider="openai", model="gpt-x")
    assert r.model_id == "openai/gpt-x"


def test_unknown_profile_raises_llm_error():
    import pytest

    from {{ package_name }}.llm.errors import LLMError
    from {{ package_name }}.llm.profiles import resolve_profile

    with pytest.raises(LLMError):
        resolve_profile(_settings(), "nope")
```

- [ ] **Step 2: Render + run → confirm red** (`No module named 'demo.llm.profiles'`).

- [ ] **Step 3: Implement `profiles.py`**
```python
"""LLM profile resolution: (default profile <- named overlay <- per-call override)."""

from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import Settings
from .errors import LLMError

# Providers that require an API key. Anything else (e.g. the claude-cli subscription
# provider added by the claudesubscriptioncli battery) is keyless by default, so the
# base llm battery needs no knowledge of it. Extend as key-requiring providers are added.
KEY_REQUIRING_PROVIDERS = {"anthropic", "openai"}


@dataclass
class ResolvedProfile:
    name: str
    provider: str
    model: str
    api_key: str  # plaintext; "" when none configured
    max_tokens: int
    temperature: float

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.model}"

    @property
    def requires_key(self) -> bool:
        return self.provider in KEY_REQUIRING_PROVIDERS


def resolve_profile(
    settings: Settings,
    name: str = "default",
    *,
    provider: str | None = None,
    model: str | None = None,
) -> ResolvedProfile:
    """Resolve a profile name + per-call overrides to a concrete config.

    "default" is the llm_* settings. Any other name must exist in settings.llm_profiles
    (unknown -> LLMError); its unset fields inherit default. Per-call provider/model win last.
    """
    eff_provider = settings.llm_provider
    eff_model = settings.llm_model
    eff_key = settings.llm_api_key
    eff_max = settings.llm_max_tokens
    eff_temp = settings.llm_temperature

    if name != "default":
        prof = settings.llm_profiles.get(name)
        if prof is None:
            raise LLMError(f"unknown llm profile: {name!r}")
        eff_provider = prof.provider or eff_provider
        eff_model = prof.model or eff_model
        eff_key = prof.api_key if prof.api_key is not None else eff_key
        eff_max = prof.max_tokens if prof.max_tokens is not None else eff_max
        eff_temp = prof.temperature if prof.temperature is not None else eff_temp

    if provider is not None:
        eff_provider = provider
    if model is not None:
        eff_model = model

    return ResolvedProfile(
        name=name,
        provider=eff_provider,
        model=eff_model,
        api_key=eff_key.get_secret_value(),
        max_tokens=eff_max,
        temperature=eff_temp,
    )
```

- [ ] **Step 4: Re-render + run green** (`-k profile or resolve`). Then `uv run mypy src/demo/llm` + `ruff check`/`format --check` on `src/demo/llm/profiles.py`.

- [ ] **Step 5: Stage**: `feat(fwk13): llm profile resolution`. (Opus code-quality review after this task.)

---

## Task 4: `profile` label on the spend metrics (TDD)

**Files:** Modify `<llm-dir>/metrics.py`; Modify the unit test file (existing metric asserts change).

- [ ] **Step 1: Update/extend the metric tests.** Replace the existing call/token/cost asserts (which used unlabeled series) and add profile cases:
```python
def test_metrics_label_by_profile():
    from {{ package_name }}.llm.metrics import LLMMetrics

    m = LLMMetrics()
    m.record_call("success", "default")
    m.record_call("success", "cheap")
    m.record_call("error", "cheap")
    m.record_tokens("cheap", input=10, output=5, cache_read=3)
    m.record_cost("cheap", 0.0021)
    out = m.render_prometheus()
    assert 'app_llm_calls_total{profile="default",outcome="success"} 1' in out
    assert 'app_llm_calls_total{profile="cheap",outcome="success"} 1' in out
    assert 'app_llm_calls_total{profile="cheap",outcome="error"} 1' in out
    assert 'app_llm_tokens_total{profile="cheap",kind="input"} 10' in out
    assert 'app_llm_cost_usd_total{profile="cheap"} 0.002100' in out
    assert "# TYPE app_llm_calls_total counter" in out


def test_metrics_latency_gauge_unlabeled():
    from {{ package_name }}.llm.metrics import LLMMetrics

    m = LLMMetrics()
    m.record_latency_ms(12.0)
    out = m.render_prometheus()
    assert "# TYPE app_llm_call_latency_p99_ms gauge" in out
    assert "app_llm_call_latency_p99_ms " in out


def test_metrics_reset_clears_all():
    from {{ package_name }}.llm.metrics import LLMMetrics

    m = LLMMetrics()
    m.record_call("success", "cheap")
    m.record_cost("cheap", 0.01)
    m.reset()
    assert m.render_prometheus().count('app_llm_calls_total{') == 0
    assert "app_llm_call_latency_p99_ms 0" in m.render_prometheus()
```
(Remove the now-obsolete unlabeled-series asserts from the earlier metric tests.)

- [ ] **Step 2: Render + run → confirm red.**

- [ ] **Step 3: Rewrite `metrics.py`** to key the spend series by profile (latency stays global). Full file:
```python
"""Process-wide LLM metrics — hand-rolled Prometheus exposition (no client lib).

Mirrors the house pattern: thread-safe module-level singleton, label-light. `outcome`
and `kind` are bounded enums; `profile` is bounded by the named-profile config set
(gives per-profile cost/usage visibility). The model id is deliberately NOT a label.
"""

from __future__ import annotations

import threading

CALL_OUTCOMES = ("success", "error", "exhausted")
TOKEN_KINDS = ("input", "output", "cache_read")


# Nearest-rank p99 (spec formula); intentionally differs by up to one rank from
# observability/metrics.py's ceil-based p99 — both valid; kept separate to avoid coupling.
def _p99(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, round(0.99 * (len(ordered) - 1)))
    return ordered[idx]


class LLMMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[tuple[str, str], int] = {}   # (profile, outcome) -> count
        self._tokens: dict[tuple[str, str], int] = {}  # (profile, kind) -> count
        self._cost_usd: dict[str, float] = {}          # profile -> usd
        self._latencies_ms: list[float] = []

    def record_call(self, outcome: str, profile: str = "default") -> None:
        if outcome not in CALL_OUTCOMES:
            return
        with self._lock:
            key = (profile, outcome)
            self._calls[key] = self._calls.get(key, 0) + 1

    def record_tokens(
        self, profile: str, *, input: int = 0, output: int = 0, cache_read: int = 0
    ) -> None:
        with self._lock:
            for kind, value in (("input", input), ("output", output), ("cache_read", cache_read)):
                key = (profile, kind)
                self._tokens[key] = self._tokens.get(key, 0) + max(0, value)

    def record_cost(self, profile: str, usd: float) -> None:
        with self._lock:
            self._cost_usd[profile] = self._cost_usd.get(profile, 0.0) + max(0.0, usd)

    def record_latency_ms(self, ms: float) -> None:
        with self._lock:
            self._latencies_ms.append(ms)

    def render_prometheus(self) -> str:
        with self._lock:
            calls = "".join(
                f'app_llm_calls_total{{profile="{p}",outcome="{o}"}} {n}\n'
                for (p, o), n in sorted(self._calls.items())
            )
            tokens = "".join(
                f'app_llm_tokens_total{{profile="{p}",kind="{k}"}} {n}\n'
                for (p, k), n in sorted(self._tokens.items())
            )
            cost = "".join(
                f'app_llm_cost_usd_total{{profile="{p}"}} {c:.6f}\n'
                for p, c in sorted(self._cost_usd.items())
            )
            p99 = _p99(self._latencies_ms)
        return (
            "# HELP app_llm_calls_total LLM calls by profile and outcome\n"
            "# TYPE app_llm_calls_total counter\n"
            f"{calls}"
            "# HELP app_llm_tokens_total LLM tokens consumed by profile and kind\n"
            "# TYPE app_llm_tokens_total counter\n"
            f"{tokens}"
            "# HELP app_llm_cost_usd_total Cumulative LLM spend in USD by profile\n"
            "# TYPE app_llm_cost_usd_total counter\n"
            f"{cost}"
            "# HELP app_llm_call_latency_p99_ms p99 LLM-call latency in ms\n"
            "# TYPE app_llm_call_latency_p99_ms gauge\n"
            f"app_llm_call_latency_p99_ms {p99}\n"
        )

    def reset(self) -> None:
        with self._lock:
            self._calls = {}
            self._tokens = {}
            self._cost_usd = {}
            self._latencies_ms = []


llm_metrics = LLMMetrics()
"""Process-wide singleton imported by the llm service and the /metrics route."""
```

- [ ] **Step 4: Re-render + run green** (all unit metric tests). `ruff format --check` + `ruff check` the render.

- [ ] **Step 5: Stage**: `feat(fwk13): per-profile labels on llm spend metrics`. (Opus code-quality review after.)

---

## Task 5: Profile-aware `LLMService` — key fail-fast + duck-typed exhaustion (TDD)

**Files:** Modify `<llm-dir>/service.py`; Modify the unit test file.

- [ ] **Step 1: Failing tests** (append; the `_settings`/`_Resp`/`_Usage` helpers from earlier tests are reused — keep them):
```python
def test_complete_uses_named_profile_and_labels_metrics(monkeypatch):
    import litellm

    from {{ package_name }}.config.settings import LLMProfile
    from {{ package_name }}.llm.metrics import LLMMetrics
    from {{ package_name }}.llm.service import LLMService

    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return _Resp("hi")

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    s = _settings(llm_profiles={"cheap": LLMProfile(model="claude-haiku-4-5-20251001")})
    m = LLMMetrics()
    LLMService(s, metrics=m).complete([{"role": "user", "content": "x"}], profile="cheap")
    assert captured["model"] == "anthropic/claude-haiku-4-5-20251001"
    assert 'app_llm_calls_total{profile="cheap",outcome="success"} 1' in m.render_prometheus()


def test_complete_per_call_override(monkeypatch):
    import litellm

    from {{ package_name }}.llm.service import LLMService

    captured = {}
    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp("h"))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    LLMService(_settings(), metrics=_new_metrics()).complete(
        [{"role": "user", "content": "x"}], provider="openai", model="gpt-x"
    )
    assert captured["model"] == "openai/gpt-x"


def test_keyless_provider_passes_no_api_key(monkeypatch):
    import litellm

    from {{ package_name }}.config.settings import LLMProfile
    from {{ package_name }}.llm.service import LLMService

    captured = {}
    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp("h"))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    s = _settings(llm_api_key="", llm_profiles={"sub": LLMProfile(provider="claude-cli", model="m")})
    LLMService(s, metrics=_new_metrics()).complete([{"role": "user", "content": "x"}], profile="sub")
    assert "api_key" not in captured  # keyless provider: no key passed, no fail-fast


def test_empty_key_for_key_requiring_provider_fails_fast():
    import pytest

    from {{ package_name }}.llm.errors import LLMError
    from {{ package_name }}.llm.service import LLMService

    s = _settings(llm_api_key="")  # default profile, anthropic, no key
    with pytest.raises(LLMError, match="no API key"):
        LLMService(s, metrics=_new_metrics()).complete([{"role": "user", "content": "x"}])


def test_reset_hint_exception_maps_to_exhausted(monkeypatch):
    import litellm

    from {{ package_name }}.llm.errors import LLMExhausted
    from {{ package_name }}.llm.service import LLMService

    class _Sub(Exception):
        def __init__(self):
            super().__init__("subscription used up")
            self.reset_hint = "resets 11:30am"

    def boom(**_):
        try:
            raise _Sub()
        except _Sub as inner:
            raise RuntimeError("litellm wrapped it") from inner

    monkeypatch.setattr(litellm, "completion", boom)
    import pytest

    with pytest.raises(LLMExhausted) as ei:
        LLMService(_settings(), metrics=_new_metrics()).complete([{"role": "user", "content": "x"}])
    assert ei.value.reset_hint == "resets 11:30am"
```
Add a tiny helper near the top of the test file (so each test gets a fresh metrics instance):
```python
def _new_metrics():
    from {{ package_name }}.llm.metrics import LLMMetrics

    return LLMMetrics()
```

- [ ] **Step 2: Render + run → confirm red.**

- [ ] **Step 3: Rewrite the relevant parts of `service.py`.** Add the exhaustion helper + sentinel at module level (after the imports):
```python
from .profiles import ResolvedProfile, resolve_profile

_NO_HINT: object = object()


def _exhaustion_reset_hint(exc: BaseException) -> object:
    """Return the reset_hint of any exception in the cause/context chain, else _NO_HINT.

    Duck-typed so the base llm battery never imports a provider plugin: a subscription
    backend signals exhaustion by raising an exception carrying a `reset_hint` attribute.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if hasattr(cur, "reset_hint"):
            return cur.reset_hint
        cur = cur.__cause__ or cur.__context__
    return _NO_HINT
```
Replace `_model` (delete the property) and rewrite `_call`, `_record_usage`, `complete`, `complete_structured`:
```python
    def _call(
        self, messages: list[Message], resolved: ResolvedProfile, **extra: Any
    ) -> Any:
        import litellm

        if resolved.requires_key and not resolved.api_key:
            self._metrics.record_call("error", resolved.name)
            raise LLMError(f"no API key configured for profile '{resolved.name}'")

        kwargs: dict[str, Any] = {
            "model": resolved.model_id,
            "max_tokens": resolved.max_tokens,
            "temperature": resolved.temperature,
            "messages": messages,
            **extra,
        }
        if resolved.api_key:
            kwargs["api_key"] = resolved.api_key

        started = perf_counter()
        try:
            response = litellm.completion(**kwargs)
        except litellm.exceptions.RateLimitError as exc:
            self._metrics.record_call("exhausted", resolved.name)
            raise LLMExhausted(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001  # see exhaustion duck-typing below
            hint = _exhaustion_reset_hint(exc)
            if hint is not _NO_HINT:
                self._metrics.record_call("exhausted", resolved.name)
                raise LLMExhausted(str(exc), reset_hint=hint if isinstance(hint, str) else None) from exc
            self._metrics.record_call("error", resolved.name)
            raise LLMError(str(exc)) from exc

        self._metrics.record_latency_ms((perf_counter() - started) * 1000)
        self._metrics.record_call("success", resolved.name)
        self._record_usage(response, resolved.name)
        return response

    def _record_usage(self, response: Any, profile: str) -> None:
        import litellm

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._metrics.record_tokens(
                profile,
                input=getattr(usage, "prompt_tokens", 0) or 0,
                output=getattr(usage, "completion_tokens", 0) or 0,
                cache_read=self._cache_read_tokens(usage),
            )
        try:
            self._metrics.record_cost(
                profile, litellm.completion_cost(completion_response=response)
            )
        except Exception:
            pass  # cost is best-effort; never fail a call over accounting

    def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        *,
        profile: str = "default",
        provider: str | None = None,
        model: str | None = None,
    ) -> CompletionResult:
        resolved = resolve_profile(
            self._settings, profile, provider=provider, model=model
        )
        response = self._call(self._with_system(messages, system), resolved)
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, usage=self._usage_dict(response))

    def complete_structured(
        self,
        messages: list[Message],
        schema: type[T],
        system: str | None = None,
        *,
        profile: str = "default",
        provider: str | None = None,
        model: str | None = None,
    ) -> T:
        from pydantic import ValidationError

        resolved = resolve_profile(
            self._settings, profile, provider=provider, model=model
        )
        response = self._call(
            self._with_system(messages, system), resolved, response_format=schema
        )
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise LLMError(f"structured output did not match schema: {exc}") from exc
```
Update the module docstring's stale "HotSwapLLM ... swaps the provider/model prefix" line to: "Profiles select the provider/model per call (see profiles.py); the claudesubscriptioncli battery adds the keyless claude-cli provider."

- [ ] **Step 4: Re-render + run green** (full unit file). `uv run mypy src/demo/llm` + ruff clean.

- [ ] **Step 5: Stage**: `feat(fwk13): profile-aware LLMService + key fail-fast + duck-typed exhaustion`. (Opus code-quality review after — this is the core task.)

---

## Task 6: Demo route accepts an optional `profile` (TDD)

**Files:** Modify `.../routes/{{ 'llm.py' ... }}.jinja`; Modify `tests/functional/{{ 'test_llm.py' ... }}.jinja`.

- [ ] **Step 1: Failing functional test** (append):
```python
def test_complete_route_passes_profile(monkeypatch):
    import litellm

    captured = {}
    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp())
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    from {{ package_name }}.config.settings import Settings
    from {{ package_name }}.main import create_app

    profiles = '{"cheap":{"model":"claude-haiku-4-5-20251001"}}'
    app = create_app(Settings(llm_api_key="k", serve_spa=False, llm_profiles=__import__("json").loads(profiles)))
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        r = c.post("/llm/complete", json={"prompt": "hi", "profile": "cheap"})
    assert r.status_code == 200
    assert captured["model"] == "anthropic/claude-haiku-4-5-20251001"
```
(The `_Resp`/`_Usage` stubs already exist in this functional file from the llm battery.)

- [ ] **Step 2: Render + run → confirm red** (profile ignored → model is the default).

- [ ] **Step 3: Implement.** In the route file, add `profile` to the request model and pass it:
```python
class CompleteRequest(BaseModel):
    prompt: str
    system: str | None = None
    profile: str = "default"
```
and in the handler change the call to:
```python
        result = service.complete(
            [{"role": "user", "content": body.prompt}],
            system=body.system,
            profile=body.profile,
        )
```
(An unknown profile raises `LLMError` → caught by the existing broad `except` → 502. That's acceptable; the demo route stays simple.)

- [ ] **Step 4: Re-render + run green.** ruff format/check + mypy on `src/demo/routes/llm.py`.

- [ ] **Step 5: Stage**: `feat(fwk13): /llm/complete accepts a profile`.

---

## Task 7: Per-profile obs (alert + dashboard)

**Files:** Modify the `llm_alerts.yml` + `llm.json` brace-named jinja files.

- [ ] **Step 1: Update the alert** to per-profile failure rate. Replace the rule expr:
```yaml
    expr: sum by (profile) (rate(app_llm_calls_total{outcome=~"error|exhausted"}[5m])) / clamp_min(sum by (profile) (rate(app_llm_calls_total[5m])), 1) > 0.1
```
(and reword the summary to "...for an LLM profile...").

- [ ] **Step 2: Update the dashboard** panel exprs to group by profile:
  - panel 1 (calls): `sum by (profile, outcome) (rate(app_llm_calls_total[5m]))`
  - panel 3 (tokens): `sum by (profile) (rate(app_llm_tokens_total[5m]))`
  - panel 4 (cost): `sum by (profile) (app_llm_cost_usd_total)`
  - panel 2 (latency): unchanged (`app_llm_call_latency_p99_ms`).

- [ ] **Step 3: Validate.** Render llm, then `python -c "import json; json.load(open('/tmp/llmwork/infra/observability/grafana/dashboards/llm.json'))"` and `uv run pytest "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[llm]" -q` → PASS.

- [ ] **Step 4: Stage**: `feat(fwk13): per-profile llm alert + dashboard`.

---

## Task 8: Full render + acceptance + eval coupling

**Files:** Run-only (framework tests); possibly eval fixtures.

- [ ] **Step 1: Source gate.** `uv run pytest -q -k "not acceptance" && uv run ruff check . && uv run ruff format --check . && uv run mypy src` → all green.
- [ ] **Step 2: Render + obs + acceptance.** `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py tests/test_obs_completeness.py tests/acceptance/test_rendered_project.py -k "llm or copier or obs" -q` → PASS, including `test_rendered_project_with_llm_battery_passes` (still 100% route coverage) and `test_rendered_project_precommit_clean_with_llm_battery`.
- [ ] **Step 3: Grep the RENDERED llm project** for stragglers: render `/tmp/llmwork`, then `grep -rn "_model\b" src/demo/llm || true` (the deleted property) and confirm no leftover unlabeled `app_llm_*` series in obs vs metrics. Fix any mismatch.
- [ ] **Step 4: Eval-fixture coupling** ([[eval-fixtures-coupled-to-template]]): `git grep -l "app_llm_\|llm_profiles\|/llm/complete" tests/eval/fixtures/ || echo "no coupling"`. Re-anchor if any.
- [ ] **Step 5: Stage** any fixture changes: `test(fwk13): re-anchor eval fixtures` (skip if none).

---

## Task 9: Branch-end review + release v0.2.7

**Files:** `PLAN.md` (FWK13 → Done), `ACTION_LOG.md`; release files (Task 9b).

- [ ] **Step 1: Branch-end Opus review** ([[subagent-review-model-pattern]]) over the full branch diff. Focus: profile resolution correctness (inheritance + override precedence), secret handling (`api_key` only passed when present, never logged), the key fail-fast for key-requiring providers, duck-typed exhaustion (cycle-safe chain walk; `reset_hint=None` vs absent), metric cardinality (profile bounded), and obs series ↔ metrics name consistency. Address findings; re-run Tasks 8.
- [ ] **Step 2: Verify subagent commits landed** ([[subagent-implementers-stop-before-commit]]): `git status --short && git log --oneline master..HEAD`.
- [ ] **Step 3: PLAN/ACTION_LOG.** Move FWK13 → Done; append the completion entry. Commit.
- [ ] **Step 4 (9b): Cut v0.2.7** ([[release-cut-procedure]]): bump `pyproject` 0.2.6→0.2.7, `uv lock`, `DOGFOOD_COMMIT`→`"v0.2.7"`; `uv build` → 0.2.7 artifacts; version-consistency tests; commit `chore(release): v0.2.7`. Bundle into the FWK13 PR (v0.2.4-style — one render-matrix).
- [ ] **Step 5: Finish the branch** ([[finishing-a-development-branch]]): push `fwk13-llm-profiles`, open one PR, confirm `gate`/`build`/`render-complete` green, squash-merge, tag `v0.2.7` → `release.yml`, verify the published Release (2 assets), grep `master` for a marker ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** config/back-compat default profile (Task 2) · named profiles + per-call override + resolution layering (Task 3) · key fail-fast for key-requiring providers (Tasks 3/5) · duck-typed `reset_hint` exhaustion (Tasks 1/5) · per-profile cost metrics (Task 4) · demo route profile (Task 6) · per-profile alert+dashboard (Task 7) · obs-completeness/render/acceptance (Task 8) · release (Task 9). The `requires`-test handling and the claude-cli provider are explicitly **FWK16** (next slice), not here.
- **Type consistency:** `LLMProfile{provider,model,api_key,max_tokens,temperature}` (settings) · `ResolvedProfile{name,provider,model,api_key,max_tokens,temperature}`+`.model_id`/`.requires_key` · `resolve_profile(settings, name="default", *, provider, model)` · `LLMMetrics.record_call(outcome, profile="default")`/`record_tokens(profile, *, …)`/`record_cost(profile, usd)` · `LLMService.complete(messages, system=None, *, profile="default", provider=None, model=None)` — consistent across tasks.
- **No placeholders:** every code/test/yaml/json block is complete. The `_new_metrics()` test helper is defined in Task 5 Step 1.

# LLM Profiles + Claude-Subscription Provider — Design

> Design spec for the per-task LLM selection capability and the subscription
> (claude-cli) provider. Status: approved (brainstorming, 2026-06-15). Builds on
> the `--with llm` battery (v0.2.6, `2026-06-14-agents-battery-design.md`) and the
> externalized `litellm-claude-cli` package (FWK11). Supersedes the original
> single-axis `hotswapllm` framing.

## Context & goal

The `--with llm` battery ships a single-configuration LLM runtime (one provider +
model + key). Real apps (Meridian) need **different choices for different tasks** —
a cheap/fast model for one path, a strong model for another, the **Claude
subscription** (via `claude -p`) for cost-sensitive work and the API for the
critical path. The motivating constraint: the API path is expensive, so the
subscription backend is what unblocks real usage.

Once you can select per task, "hot-swap API↔subscription" stops being its own
feature — it is just **two named profiles**. So the capability is **named LLM
profiles** (selectable per call, with per-call overrides for spikes), and the
subscription is **one available provider** within a profile.

## Decomposition

Two layered slices, each its own plan / branch / merge / release. The `requires`
chain is `claudesubscriptioncli` → `llm`.

| Slice | Battery | Ships |
|-------|---------|-------|
| **1 (FWK13)** | evolve `--with llm` | named profiles + per-call override + per-profile observability + profile-aware key fail-fast + duck-typed exhaustion (subscription-ready). Provider-agnostic (API). A `"default"` profile reproduces today's single-model behavior — backward compatible. |
| **2 (FWK16)** | `--with claudesubscriptioncli` (`requires=("llm",)`) | the `litellm-claude-cli` dep + the `claude-cli` custom-provider registration, making `provider: "claude-cli"` a valid (keyless) profile value. `obs="rides-existing"`. |

`--with agents` (FWK14, the tool loop, `requires=("llm",)`) remains downstream.

Rationale for putting profiles in base `llm` (not bundling into the gated
battery): profiles are a general "which model" capability useful to any llm user
without forcing the claude-cli dep; and it keeps the gated battery tiny and honest
— it adds *one provider*, not a config system.

---

## Slice 1 — LLM profiles in `--with llm`

### Configuration (backward-compatible)

Today's single-config fields become the implicit **`"default"` profile**;
existing projects are untouched:

- `llm_provider` / `llm_model` / `llm_api_key` (`SecretStr`) / `llm_max_tokens` /
  `llm_temperature` — the `default` profile.

Additional profiles come from one JSON-encoded env var parsed by
pydantic-settings into a typed map:

```python
class LLMProfile(BaseModel):
    provider: str | None = None      # inherits default when unset
    model: str | None = None
    api_key: SecretStr | None = None
    max_tokens: int | None = None
    temperature: float | None = None

# Settings:
llm_profiles: dict[str, LLMProfile] = {}   # env APP_LLM_PROFILES (JSON)
```

```
APP_LLM_PROFILES='{"smart":{"provider":"anthropic","model":"claude-opus-4-8"},
                   "cheap":{"model":"claude-haiku-4-5-20251001"},
                   "sub":{"provider":"claude-cli","model":"claude-sonnet-4-6"}}'
```

A profile specifies only what differs; every unset field **inherits the
`default` profile**. A profile may carry its own `api_key` for cross-account /
cross-provider cases.

### Selection API (named profiles + per-call override)

```python
LLMService.complete(messages, *, profile="default", provider=None, model=None,
                    system=None) -> CompletionResult
LLMService.complete_structured(messages, schema, *, profile="default",
                               provider=None, model=None, system=None) -> T
```

Effective config resolves by layering: **`default` profile ← named-profile
overlay ← per-call `provider`/`model` overrides**. Named selection is the
backbone (a); the per-call kwargs are the spike / exception escape hatch (b).
An unknown profile name raises `LLMError`.

### Key handling + the (folded) fail-fast nit

A module constant `KEY_REQUIRING_PROVIDERS = {"anthropic", "openai"}` (extend as providers are added). When
the effective provider is in that set and the effective key is empty, the service
raises a clear `LLMError("no API key configured for profile '<name>'")` **before**
the network call. Providers outside the set (notably the future `claude-cli`) are
**keyless by default** — so Slice 2 needs no special-casing here; it just adds a
keyless provider. The key, when present, is passed explicitly to LiteLLM; it is
never logged.

### Exhaustion — duck-typed (subscription-ready, zero coupling)

The service maps `litellm.exceptions.RateLimitError` → `LLMExhausted` as today,
and additionally, on any caught exception, walks the `__cause__`/`__context__`
chain: **if any link exposes a `reset_hint` attribute, map to
`LLMExhausted(reset_hint=…)`** (HTTP 503). This is the contract the subscription
plugin's `ClaudeExhausted` satisfies automatically — the base `llm` service never
imports the plugin, and the seam generalizes to any future provider that signals
exhaustion the same way. Everything else stays `LLMError` (502).

### Observability — per-profile cost

Add a **bounded `profile` label** to the spend-relevant series so subscription-vs-
API and cheap-vs-smart cost is attributable:

- `app_llm_calls_total{outcome, profile}`
- `app_llm_tokens_total{kind, profile}`
- `app_llm_cost_usd_total{profile}`

`app_llm_call_latency_p99_ms` stays a single (unlabeled) gauge. The failure-rate
alert generalizes to per-profile. Profile names are bounded config, so this is a
real low-cardinality dimension, consistent with the house label-light doctrine.
Verified by `test_obs_completeness.py` (still `in-process`: alert + dashboard,
no scrape/service).

---

## Slice 2 — `--with claudesubscriptioncli`

### Battery

`BatterySpec("claudesubscriptioncli", requires=("llm",), obs="rides-existing")`.
Name = provider (Claude) + channel (subscription) + interface (CLI adapter). It
adds **one provider**; subscription usage flows through `llm`'s profile-labeled
metrics (subscription-vs-API cost on the same panels), so it owns no new obs.

### Dependency (PEP 508 direct reference)

Adds, under the battery guard, to the generated `pyproject.toml` dependencies:

```
litellm-claude-cli @ git+https://github.com/cdowell-swtr/litellm-claude-cli@v0.1.1
```

A **PEP 508 direct reference**, *not* `[tool.uv.sources]` — generated projects may
be pip-installed and uv-sources is uv-only (FWK11 review I2).

### Registration

A battery-gated file
`src/{{package_name}}/llm/{% if "claudesubscriptioncli" in batteries %}claude_cli{% endif %}.py`
exports `register_claude_cli()`:

```python
def register_claude_cli() -> None:
    import litellm
    from litellm_claude_cli import ClaudeCliLLM

    existing = [p for p in (litellm.custom_provider_map or [])
                if p.get("provider") != "claude-cli"]
    litellm.custom_provider_map = [
        {"provider": "claude-cli", "custom_handler": ClaudeCliLLM()},
        *existing,
    ]
```

Idempotent (replaces any prior `claude-cli` entry), mirroring the framework's own
`review/backend.py`. A jinja-guarded call at app startup (`create_app`) runs it
when the battery is active:

```jinja
{%- if "claudesubscriptioncli" in batteries %}
    from {{ package_name }}.llm.claude_cli import register_claude_cli

    register_claude_cli()
{%- endif %}
```

Once registered, a profile `{"sub": {"provider":"claude-cli", "model":"…"}}`
routes through the subscription, keyless.

### Runtime requirement (the operational caveat)

Subscription profiles only work where the `claude` CLI is **on PATH and
authenticated** (logged into the subscription). The generated image does **not**
bake in `claude` — it is auth-bound and tied to a personal subscription. This is
called out explicitly in the generated `SECRETS.md` + README and the battery
summary; it is the one gotcha that otherwise fails silently (every `sub`-profile
call errors until `claude` is present).

---

## Cross-cutting

### `requires` ↔ per-battery render tests (first battery with `requires`)

`render_project` does not resolve `requires` (the CLI's `resolve_batteries`
does), and `test_obs_completeness.py` + the per-battery acceptance tests render
each battery **alone**. `claudesubscriptioncli` is the first battery with
`requires`, so those tests are updated to **resolve `requires` for the candidate
render**. For the obs test specifically, the **baseline is built from the
resolved deps** so the diff attributes only the battery's *own* obs:

- baseline = `render(resolve(requires) \ {self})` — e.g. `render(["llm"])`
- candidate = `render(resolve({self} ∪ requires))` — e.g. `render(["claudesubscriptioncli","llm"])`
- diff = the battery's own contribution → for `claudesubscriptioncli`, none (→ correctly `rides-existing`, since `llm`'s alert/dashboard appear in both).

This is a small, general framework-test fix that every future `requires`-battery
needs.

### Naming

`hotswapllm` is dropped; "hot-swap" is subsumed by profiles. The gated battery is
`claudesubscriptioncli`.

---

## Testing

- **Slice 1 (hermetic, mocked LiteLLM):** profile resolution + override layering
  (default ← named ← per-call); per-profile metrics + cost labeling; the key
  fail-fast for a key-requiring provider with an empty key; duck-typed exhaustion
  via a fake `reset_hint`-bearing exception (no plugin needed); unknown-profile →
  `LLMError`. Plus the existing completion/structured/route tests, profile-aware.
- **Slice 2:** registration idempotency; a `claude-cli` profile routes to
  `claude-cli/<model>` keyless (mocked handler, no real CLI); `ClaudeExhausted` →
  `LLMExhausted`; the dep renders as a PEP 508 ref; the startup guard calls
  `register_claude_cli()` only when active. A **gated live smoke** (real `claude`
  CLI) exercises a real subscription completion, kept out of the default gate.
- **Both:** template-payload TDD loop; render + acceptance (generated suite,
  coverage gate, clean first pre-commit) with `requires` resolved; obs-completeness
  green; eval-fixture coupling checked.

## Out of scope

- The agentic tool loop (`--with agents`, FWK14).
- Non-Anthropic providers beyond what LiteLLM already routes (the profile model
  supports them, but no new provider plugins ship here).
- Streaming; per-profile rate limiting / budgets / fallback chains (profiles are
  selection, not orchestration — revisit if a real need appears).
- Baking the `claude` CLI into the generated image.

## PLAN re-keying

- **FWK13** → Slice 1: LLM profiles in `--with llm`.
- **FWK16** → Slice 2: `--with claudesubscriptioncli` (`requires` llm).  deps: FWK11, FWK13.
- **FWK14** (`--with agents`, tool loop) stays after; `requires` llm.

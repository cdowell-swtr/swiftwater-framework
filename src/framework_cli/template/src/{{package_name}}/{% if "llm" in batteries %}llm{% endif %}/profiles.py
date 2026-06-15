"""LLM profile resolution: (default profile <- named overlay <- per-call override)."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    api_key: str = field(repr=False)  # plaintext; "" when none configured
    max_tokens: int
    temperature: float

    @property
    def model_id(self) -> str:
        return f"{self.provider}/{self.model}"

    @property
    def requires_key(self) -> bool:
        return self.provider.lower() in KEY_REQUIRING_PROVIDERS


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
        # provider/model use `or` (empty string -> inherit default); the numeric/key fields
        # use `is not None` so a valid falsy value (temperature=0.0, max_tokens=0) is kept.
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

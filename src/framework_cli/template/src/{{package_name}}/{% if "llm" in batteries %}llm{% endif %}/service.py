"""LLMService — a thin, observable LiteLLM wrapper over a provider API key.

Plain LiteLLM (OpenAI-shaped `litellm.completion`); the provider key is passed explicitly.
Stateless. Profiles select the provider/model per call (see profiles.py); the
claudesubscriptioncli battery adds the keyless claude-cli provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config.settings import Settings
from .errors import LLMError, LLMExhausted
from .metrics import LLMMetrics, llm_metrics
from .profiles import ResolvedProfile, resolve_profile

T = TypeVar("T", bound=BaseModel)

Message = dict[str, Any]

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


@dataclass
class CompletionResult:
    text: str
    usage: dict[str, int]


class LLMService:
    def __init__(
        self, settings: Settings, *, metrics: LLMMetrics | None = None
    ) -> None:
        self._settings = settings
        self._metrics = metrics or llm_metrics

    def _with_system(
        self, messages: list[Message], system: str | None
    ) -> list[Message]:
        if system is None:
            return messages
        return [{"role": "system", "content": system}, *messages]

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
        except Exception as exc:  # noqa: BLE001
            hint = _exhaustion_reset_hint(exc)
            if hint is not _NO_HINT:
                self._metrics.record_call("exhausted", resolved.name)
                raise LLMExhausted(
                    str(exc), reset_hint=hint if isinstance(hint, str) else None
                ) from exc
            self._metrics.record_call("error", resolved.name)
            raise LLMError(str(exc)) from exc

        self._metrics.record_latency_ms((perf_counter() - started) * 1000)
        self._metrics.record_call("success", resolved.name)
        self._record_usage(response, resolved.name)
        return response

    @staticmethod
    def _cache_read_tokens(usage: Any) -> int:
        # Anthropic cache-read tokens live at usage.prompt_tokens_details.cached_tokens;
        # litellm's Usage has no top-level cache_read_input_tokens field.
        details = getattr(usage, "prompt_tokens_details", None)
        return (getattr(details, "cached_tokens", 0) or 0) if details is not None else 0

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

    @staticmethod
    def _usage_dict(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        return {
            "input": getattr(usage, "prompt_tokens", 0) or 0,
            "output": getattr(usage, "completion_tokens", 0) or 0,
            "cache_read": LLMService._cache_read_tokens(usage)
            if usage is not None
            else 0,
        }

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

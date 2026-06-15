"""LLMService — a thin, observable LiteLLM wrapper over a provider API key.

Plain LiteLLM (OpenAI-shaped `litellm.completion`); the provider key is passed explicitly.
Stateless. The HotSwapLLM battery later swaps the provider/model prefix to route to the
subscription `claude-cli` provider — this service does not change for that.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config.settings import Settings
from .errors import LLMError, LLMExhausted
from .metrics import LLMMetrics, llm_metrics

T = TypeVar("T", bound=BaseModel)

Message = dict[str, Any]


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

    @property
    def _model(self) -> str:
        return f"{self._settings.llm_provider}/{self._settings.llm_model}"

    def _with_system(
        self, messages: list[Message], system: str | None
    ) -> list[Message]:
        if system is None:
            return messages
        return [{"role": "system", "content": system}, *messages]

    def _call(self, messages: list[Message], **extra: Any) -> Any:
        # Lazy import keeps litellm off the import path until an LLM call actually happens.
        import litellm

        started = perf_counter()
        try:
            response = litellm.completion(
                model=self._model,
                api_key=self._settings.llm_api_key.get_secret_value(),
                max_tokens=self._settings.llm_max_tokens,
                temperature=self._settings.llm_temperature,
                messages=messages,
                **extra,
            )
        except litellm.exceptions.RateLimitError as exc:
            self._metrics.record_call("exhausted")
            raise LLMExhausted(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            # litellm normalizes provider/transport failures to OpenAI-shaped exception types
            # (openai.OpenAIError subclasses); litellm.exceptions.OpenAIError does NOT catch
            # them (name collision between litellm's own class and openai's). Catching Exception
            # here is intentional — the inner guard below re-raises unknown errors verbatim.
            self._metrics.record_call("error")
            raise LLMError(str(exc)) from exc

        self._metrics.record_latency_ms((perf_counter() - started) * 1000)
        self._metrics.record_call("success")
        self._record_usage(response)
        return response

    @staticmethod
    def _cache_read_tokens(usage: Any) -> int:
        # Anthropic cache-read tokens live at usage.prompt_tokens_details.cached_tokens;
        # litellm's Usage has no top-level cache_read_input_tokens field.
        details = getattr(usage, "prompt_tokens_details", None)
        return (getattr(details, "cached_tokens", 0) or 0) if details is not None else 0

    def _record_usage(self, response: Any) -> None:
        import litellm

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._metrics.record_tokens(
                input=getattr(usage, "prompt_tokens", 0) or 0,
                output=getattr(usage, "completion_tokens", 0) or 0,
                cache_read=self._cache_read_tokens(usage),
            )
        try:
            self._metrics.record_cost(
                litellm.completion_cost(completion_response=response)
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
        self, messages: list[Message], system: str | None = None
    ) -> CompletionResult:
        response = self._call(self._with_system(messages, system))
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, usage=self._usage_dict(response))

    def complete_structured(
        self, messages: list[Message], schema: type[T], system: str | None = None
    ) -> T:
        from pydantic import ValidationError

        response = self._call(
            self._with_system(messages, system), response_format=schema
        )
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise LLMError(f"structured output did not match schema: {exc}") from exc

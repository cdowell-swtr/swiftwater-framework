"""AgentRunner — a bounded tool-calling loop over LLMService.respond().

Read-only tools; capped at max_iterations. The loop's model calls are recorded in app_llm_*
(per profile) by the service; this records tool calls + the run's terminal outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..llm.errors import LLMError
from .metrics import AgentMetrics, agent_metrics
from .tools import ToolContext, ToolRegistry, default_registry


class _Responder(Protocol):
    def respond(
        self,
        messages: list[dict[str, Any]],
        system: str | None = ...,
        *,
        profile: str = ...,
        tools: list[dict[str, Any]] | None = ...,
    ) -> Any: ...


@dataclass
class RunResult:
    text: str
    outcome: str  # "completed" | "max_iterations" | "error"
    iterations: int
    tool_calls: list[str]


class AgentRunner:
    def __init__(
        self,
        service: _Responder,
        *,
        max_iterations: int = 5,
        metrics: AgentMetrics | None = None,
    ) -> None:
        self._service = service
        self._max_iterations = max_iterations
        self._metrics = metrics or agent_metrics

    def run(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        profile: str = "default",
        registry: ToolRegistry | None = None,
        context: ToolContext | None = None,
    ) -> RunResult:
        registry = registry or default_registry()
        context = context or ToolContext(session=None)
        msgs = list(messages)
        called: list[str] = []
        last_text = ""
        try:
            for iteration in range(1, self._max_iterations + 1):
                response = self._service.respond(
                    msgs, system, profile=profile, tools=registry.schemas()
                )
                message = response.choices[0].message
                last_text = message.content or last_text
                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    self._metrics.record_run("completed")
                    return RunResult(
                        message.content or "", "completed", iteration, called
                    )
                # Serialise the assistant tool-call turn to a dict (OpenAI wire format) so the
                # history stays homogeneous; tool_calls is always non-empty here (early return above).
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                msgs.append(assistant_msg)
                for call in tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result = registry.dispatch(name, args, context)
                        # Convention: ToolRegistry.dispatch returns an "error: ..." string on a
                        # failed/unknown tool (see tools.py); treat that prefix as a tool failure.
                        outcome = "error" if result.startswith("error:") else "success"
                    except Exception as exc:  # noqa: BLE001  # malformed args / handler crash
                        result = f"error: {exc}"
                        outcome = "error"
                    called.append(name)
                    self._metrics.record_tool_call(name, outcome)
                    msgs.append(
                        {"role": "tool", "tool_call_id": call.id, "content": result}
                    )
        except LLMError:
            self._metrics.record_run("error")
            raise
        self._metrics.record_run("max_iterations")
        return RunResult(last_text, "max_iterations", self._max_iterations, called)

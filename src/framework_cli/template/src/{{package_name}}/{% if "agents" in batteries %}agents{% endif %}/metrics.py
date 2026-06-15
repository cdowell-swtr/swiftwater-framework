"""Process-wide agent metrics — hand-rolled Prometheus exposition (no client lib).

Tool calls and run outcomes; the loop's MODEL calls are counted in app_llm_* (per profile)
by LLMService, so model cost is on the llm panels and tool/run health here.
"""

from __future__ import annotations

import threading

RUN_OUTCOMES = ("completed", "max_iterations", "error")


class AgentMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tool_calls: dict[tuple[str, str], int] = {}  # (tool, outcome) -> count
        self._runs: dict[str, int] = {o: 0 for o in RUN_OUTCOMES}

    def record_tool_call(self, tool: str, outcome: str) -> None:
        if outcome not in ("success", "error"):
            return
        with self._lock:
            key = (tool, outcome)
            self._tool_calls[key] = self._tool_calls.get(key, 0) + 1

    def record_run(self, outcome: str) -> None:
        with self._lock:
            if outcome in self._runs:
                self._runs[outcome] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            tool_calls = "".join(
                f'app_agent_tool_calls_total{{tool="{t}",outcome="{o}"}} {n}\n'
                for (t, o), n in sorted(self._tool_calls.items())
            )
            runs = dict(self._runs)
        return (
            "# HELP app_agent_tool_calls_total Agent tool invocations by tool and outcome\n"
            "# TYPE app_agent_tool_calls_total counter\n"
            f"{tool_calls}"
            "# HELP app_agent_runs_total Agent run loops by terminal outcome\n"
            "# TYPE app_agent_runs_total counter\n"
            + "".join(
                f'app_agent_runs_total{{outcome="{o}"}} {runs[o]}\n'
                for o in RUN_OUTCOMES
            )
        )

    def reset(self) -> None:
        with self._lock:
            self._tool_calls = {}
            self._runs = {o: 0 for o in RUN_OUTCOMES}


agent_metrics = AgentMetrics()
"""Process-wide singleton imported by the runner and the /metrics route."""

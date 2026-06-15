"""Process-wide LLM metrics — hand-rolled Prometheus exposition (no client lib).

Mirrors the house pattern (observability/metrics.py, webhooks/metrics.py): a thread-safe
module-level singleton, label-light by design. `outcome` and `kind` are bounded enums;
the model id is deliberately NOT a label (it is effectively constant per deployment).
"""

from __future__ import annotations

import threading

CALL_OUTCOMES = ("success", "error", "exhausted")
TOKEN_KINDS = ("input", "output", "cache_read")


# Nearest-rank p99 (spec formula). Intentionally differs by up to one rank from
# observability/metrics.py's ceil-based p99 — both are valid estimators; kept separate to avoid coupling.
def _p99(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, round(0.99 * (len(ordered) - 1)))
    return ordered[idx]


class LLMMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, int] = {o: 0 for o in CALL_OUTCOMES}
        self._tokens: dict[str, int] = {k: 0 for k in TOKEN_KINDS}
        self._cost_usd = 0.0
        self._latencies_ms: list[float] = []

    def record_call(self, outcome: str) -> None:
        with self._lock:
            if outcome in self._calls:
                self._calls[outcome] += 1

    def record_tokens(
        self, *, input: int = 0, output: int = 0, cache_read: int = 0
    ) -> None:
        with self._lock:
            self._tokens["input"] += max(0, input)
            self._tokens["output"] += max(0, output)
            self._tokens["cache_read"] += max(0, cache_read)

    def record_cost(self, usd: float) -> None:
        with self._lock:
            self._cost_usd += max(0.0, usd)

    def record_latency_ms(self, ms: float) -> None:
        with self._lock:
            self._latencies_ms.append(ms)

    def render_prometheus(self) -> str:
        with self._lock:
            calls = "".join(
                f'app_llm_calls_total{{outcome="{o}"}} {self._calls[o]}\n'
                for o in CALL_OUTCOMES
            )
            tokens = "".join(
                f'app_llm_tokens_total{{kind="{k}"}} {self._tokens[k]}\n'
                for k in TOKEN_KINDS
            )
            cost = self._cost_usd
            p99 = _p99(self._latencies_ms)
        return (
            "# HELP app_llm_calls_total LLM calls by outcome\n"
            "# TYPE app_llm_calls_total counter\n"
            f"{calls}"
            "# HELP app_llm_tokens_total LLM tokens consumed by kind\n"
            "# TYPE app_llm_tokens_total counter\n"
            f"{tokens}"
            "# HELP app_llm_cost_usd_total Cumulative LLM spend in USD\n"
            "# TYPE app_llm_cost_usd_total counter\n"
            f"app_llm_cost_usd_total {cost:.6f}\n"
            "# HELP app_llm_call_latency_p99_ms p99 LLM-call latency in ms\n"
            "# TYPE app_llm_call_latency_p99_ms gauge\n"
            f"app_llm_call_latency_p99_ms {p99}\n"
        )

    def reset(self) -> None:
        with self._lock:
            self._calls = {o: 0 for o in CALL_OUTCOMES}
            self._tokens = {k: 0 for k in TOKEN_KINDS}
            self._cost_usd = 0.0
            self._latencies_ms = []


llm_metrics = LLMMetrics()
"""Process-wide singleton imported by the llm service and the /metrics route."""

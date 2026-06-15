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
        self._calls: dict[tuple[str, str], int] = {}  # (profile, outcome) -> count
        self._tokens: dict[tuple[str, str], int] = {}  # (profile, kind) -> count
        self._cost_usd: dict[str, float] = {}  # profile -> usd
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
            for kind, value in (
                ("input", input),
                ("output", output),
                ("cache_read", cache_read),
            ):
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

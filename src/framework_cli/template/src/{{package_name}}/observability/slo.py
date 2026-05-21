"""SLO definitions and evaluation.

SLOs are typed config (single source of truth). `evaluate` is pure — it takes the SLOs
and a dict of current values and returns the structured /health report. Plan 3b reads
these same definitions to auto-generate dashboards and alert rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.settings import Settings
    from .metrics import MetricsRegistry


@dataclass(frozen=True, slots=True)
class SLO:
    key: str
    description: str
    threshold: float
    unit: str
    warning_ratio: float = 0.9  # current >= warning_ratio * threshold -> "warning"


def default_slos(settings: "Settings") -> list[SLO]:
    return [
        SLO(
            key="request_latency_p99_ms",
            description="p99 request latency",
            threshold=settings.slo_request_latency_p99_ms,
            unit="ms",
        ),
        SLO(
            key="error_rate_pct",
            description="5xx error rate",
            threshold=settings.slo_error_rate_pct,
            unit="percent",
        ),
    ]


def _status_for(current: float, slo: SLO) -> str:
    if current > slo.threshold:
        return "breached"
    if current >= slo.warning_ratio * slo.threshold:
        return "warning"
    return "ok"


def evaluate(slos: list[SLO], current_values: dict[str, float]) -> dict:
    slo_report: dict[str, dict] = {}
    for slo in slos:
        current = current_values[slo.key]
        slo_report[slo.key] = {
            "threshold": slo.threshold,
            "current": current,
            "unit": slo.unit,
            "status": _status_for(current, slo),
        }
    overall = (
        "ok" if all(s["status"] == "ok" for s in slo_report.values()) else "degraded"
    )
    return {"status": overall, "slos": slo_report}


def build_health_report(metrics: "MetricsRegistry", settings: "Settings") -> dict:
    current_values = {
        "request_latency_p99_ms": metrics.p99_latency_ms(),
        "error_rate_pct": metrics.error_rate_pct(),
    }
    return evaluate(default_slos(settings), current_values)

"""Generate Prometheus alert rules and a Grafana dashboard from the SLO definitions.

Pure functions: SLOs in, config dicts out. `observability/slo.py` is the single source of
truth; `scripts/gen_observability.py` serialises these into `infra/observability/`.

Each SLO key maps to the PromQL expression for its *current value*, over the metrics
exposed by `observability/metrics.py` (`/metrics`). Adding a new SLO requires adding its
PromQL here — `test_provisioning.py` asserts every default SLO key is mapped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .slo import SLO

# PromQL for each SLO's current value. error_rate_pct is computed from the two counters
# (metrics.py exposes counters, not a rate gauge); clamp_min avoids divide-by-zero.
SLO_PROMQL: dict[str, str] = {
    "request_latency_p99_ms": "app_request_latency_p99_ms",
    "error_rate_pct": "100 * app_request_errors_total / clamp_min(app_requests_total, 1)",
}


def _alert_name(key: str) -> str:
    return "".join(part.capitalize() for part in key.split("_")) + "Breached"


def prometheus_alert_rules(slos: list[SLO]) -> dict:
    """A Prometheus rule-group dict (serialise to YAML under rule_files)."""
    rules = [
        {
            "alert": _alert_name(slo.key),
            "expr": f"{SLO_PROMQL[slo.key]} > {slo.threshold}",
            "for": "1m",
            "labels": {"severity": "warning", "slo": slo.key},
            "annotations": {
                "summary": f"{slo.description} above SLO ({slo.threshold}{slo.unit})"
            },
        }
        for slo in slos
    ]
    return {"groups": [{"name": "slo", "rules": rules}]}


def grafana_dashboard(slos: list[SLO]) -> dict:
    """A minimal Grafana dashboard dict: one timeseries panel per SLO, value vs threshold."""
    panels = [
        {
            "id": i + 1,
            "title": f"{slo.description} (SLO {slo.threshold}{slo.unit})",
            "type": "timeseries",
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "gridPos": {"h": 8, "w": 12, "x": (i % 2) * 12, "y": (i // 2) * 8},
            "targets": [{"refId": "A", "expr": SLO_PROMQL[slo.key]}],
            "fieldConfig": {
                "defaults": {
                    "unit": slo.unit,
                    "custom": {"thresholdsStyle": {"mode": "line"}},
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": slo.threshold},
                        ],
                    },
                },
                "overrides": [],
            },
        }
        for i, slo in enumerate(slos)
    ]
    return {
        "uid": "slo",
        "title": "SLOs",
        "tags": ["slo"],
        "schemaVersion": 39,
        "version": 1,
        "time": {"from": "now-1h", "to": "now"},
        "panels": panels,
    }

"""Tenant-engine subsystem metrics — hand-rolled Prometheus exposition (house pattern).

Counters for the routing subsystem; the live pool gauges are rendered by the registry
itself (engine_registry.render_pool_gauges). Endpoint labels are host:port (bounded by the
fleet's DB topology, never user-supplied)."""

from __future__ import annotations

import threading


class TenantEngineMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evictions: dict[str, int] = {}
        self._dsn: dict[str, int] = {"hit": 0, "miss": 0}

    def record_eviction(self, endpoint: str) -> None:
        with self._lock:
            self._evictions[endpoint] = self._evictions.get(endpoint, 0) + 1

    def record_dsn_hit(self) -> None:
        with self._lock:
            self._dsn["hit"] += 1

    def record_dsn_miss(self) -> None:
        with self._lock:
            self._dsn["miss"] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            evict = "".join(
                f'app_tenant_engine_evictions_total{{endpoint="{ep}"}} {n}\n'
                for ep, n in sorted(self._evictions.items())
            )
            dsn = "".join(
                f'app_tenant_dsn_cache_total{{outcome="{o}"}} {self._dsn[o]}\n'
                for o in ("hit", "miss")
            )
        return (
            "# HELP app_tenant_engine_evictions_total Tenant-engine LRU evictions per endpoint\n"
            "# TYPE app_tenant_engine_evictions_total counter\n"
            f"{evict}"
            "# HELP app_tenant_dsn_cache_total Tenant DSN-cache lookups by outcome\n"
            "# TYPE app_tenant_dsn_cache_total counter\n"
            f"{dsn}"
        )

    def reset(self) -> None:
        with self._lock:
            self._evictions = {}
            self._dsn = {"hit": 0, "miss": 0}


tenant_engine_metrics = TenantEngineMetrics()
"""Process-wide singleton imported by the engine registry + session resolver."""

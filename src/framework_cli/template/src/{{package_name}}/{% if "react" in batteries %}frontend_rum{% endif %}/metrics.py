"""Process-wide frontend RUM metrics — Core Web Vitals (histograms) + JS errors,
page-view navigation, query-param attribution, and beacon-ingest health (counters).

A module-level singleton (like observability/recoverability.py / websockets/metrics.py),
fed by the POST /internal/rum route and appended to the /metrics exposition. Cardinality is
bounded by construction: vital names + error types + beacon statuses are fixed enums; route
and attribution labels are capped with an "other" overflow bucket; all label values are
sanitized. No free-text (error messages, full URLs, query strings) is ever stored.
"""

from __future__ import annotations

import math
import re
import threading

# Core Web Vitals histogram buckets. LCP/INP in milliseconds; CLS is unitless.
_LCP_BUCKETS = (1000.0, 2000.0, 2500.0, 4000.0)
_INP_BUCKETS = (100.0, 200.0, 500.0, 1000.0)
_CLS_BUCKETS = (0.1, 0.25, 0.5, 1.0)

_VITALS = {
    "lcp": (
        "app_frontend_web_vitals_lcp_milliseconds",
        _LCP_BUCKETS,
        "Largest Contentful Paint (ms)",
    ),
    "inp": (
        "app_frontend_web_vitals_inp_milliseconds",
        _INP_BUCKETS,
        "Interaction to Next Paint (ms)",
    ),
    "cls": (
        "app_frontend_web_vitals_cls",
        _CLS_BUCKETS,
        "Cumulative Layout Shift (unitless)",
    ),
}
_ERROR_TYPES = ("error", "unhandledrejection")
_BEACON_STATUSES = ("accepted", "rejected")
_ATTRIBUTION_KEYS = ("utm_source", "utm_medium", "utm_campaign")

_SAN = re.compile(r"[^A-Za-z0-9_./:-]")


def _san(value: str, limit: int = 64) -> str:
    """Sanitize a label value: drop exposition-breaking chars, bound length."""
    return _SAN.sub("_", value)[:limit]


def _g(value: float) -> str:
    return f"{value:g}"


class _Histogram:
    """A minimal Prometheus histogram (no labels). Buckets are non-cumulative internally;
    rendered cumulatively per the exposition format."""

    def __init__(self, buckets: tuple[float, ...]) -> None:
        self._buckets = buckets
        self._counts = [0] * len(buckets)
        self._total = 0
        self._sum = 0.0

    def observe(self, value: float) -> None:
        self._sum += value
        self._total += 1
        for i, edge in enumerate(self._buckets):
            if value <= edge:
                self._counts[i] += 1
                break

    def render(self, name: str, help_text: str) -> str:
        out = [f"# HELP {name} {help_text}", f"# TYPE {name} histogram"]
        cumulative = 0
        for i, edge in enumerate(self._buckets):
            cumulative += self._counts[i]
            out.append(f'{name}_bucket{{le="{_g(edge)}"}} {cumulative}')
        out.append(f'{name}_bucket{{le="+Inf"}} {self._total}')
        out.append(f"{name}_sum {self._sum:g}")
        out.append(f"{name}_count {self._total}")
        return "\n".join(out) + "\n"

    def reset(self) -> None:
        self._counts = [0] * len(self._buckets)
        self._total = 0
        self._sum = 0.0


class FrontendMetrics:
    MAX_ROUTES = 32
    MAX_ATTRIBUTION = 64
    MAX_REFERRERS = 32

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._vitals = {k: _Histogram(v[1]) for k, v in _VITALS.items()}
        self._errors: dict[str, int] = {}
        self._page_views: dict[str, int] = {}
        self._attribution: dict[tuple[str, str, str], int] = {}
        self._referrers: dict[str, int] = {}
        self._beacons: dict[str, int] = {}

    def observe_web_vital(self, name: str, value: float) -> None:
        key = name.lower()
        # Drop unknown vitals and non-finite values (inf/nan would poison the histogram
        # _sum irrecoverably — this is a public endpoint, never trust the submitted number).
        if key not in self._vitals or not math.isfinite(value):
            return
        with self._lock:
            self._vitals[key].observe(value)

    def record_error(self, error_type: str) -> None:
        t = error_type if error_type in _ERROR_TYPES else "error"
        with self._lock:
            self._errors[t] = self._errors.get(t, 0) + 1

    def record_page_view(
        self, route: str, params: dict[str, str], referrer: str | None
    ) -> None:
        route = _san(route)
        attribution = tuple(_san(params.get(k, "")) for k in _ATTRIBUTION_KEYS)
        with self._lock:
            self._bump_capped(self._page_views, route, self.MAX_ROUTES)
            if any(attribution):
                self._bump_capped(
                    self._attribution,
                    attribution,
                    self.MAX_ATTRIBUTION,
                    overflow=("other", "other", "other"),
                )
            if referrer:
                self._bump_capped(self._referrers, _san(referrer), self.MAX_REFERRERS)

    def record_beacon(self, status: str) -> None:
        s = status if status in _BEACON_STATUSES else "rejected"
        with self._lock:
            self._beacons[s] = self._beacons.get(s, 0) + 1

    @staticmethod
    def _bump_capped(store: dict, key, cap: int, overflow="other") -> None:
        if key not in store and len(store) >= cap:
            key = overflow
        store[key] = store.get(key, 0) + 1

    def render_prometheus(self) -> str:
        with self._lock:
            parts = [
                self._vitals[k].render(_VITALS[k][0], _VITALS[k][2]) for k in _VITALS
            ]
            parts.append(
                self._render_counter(
                    "app_frontend_js_errors_total",
                    "Uncaught frontend JS errors",
                    [(f'type="{t}"', n) for t, n in sorted(self._errors.items())],
                )
            )
            parts.append(
                self._render_counter(
                    "app_frontend_page_views_total",
                    "Frontend page views by route",
                    [(f'route="{r}"', n) for r, n in sorted(self._page_views.items())],
                )
            )
            parts.append(
                self._render_counter(
                    "app_frontend_attribution_total",
                    "Frontend page views by UTM attribution",
                    [
                        (
                            f'utm_source="{a[0]}",utm_medium="{a[1]}",utm_campaign="{a[2]}"',
                            n,
                        )
                        for a, n in sorted(self._attribution.items())
                    ],
                )
            )
            parts.append(
                self._render_counter(
                    "app_frontend_referrers_total",
                    "Frontend page views by referrer host",
                    [
                        (f'referrer="{r}"', n)
                        for r, n in sorted(self._referrers.items())
                    ],
                )
            )
            parts.append(
                self._render_counter(
                    "app_frontend_rum_beacons_total",
                    "RUM beacon ingest outcomes",
                    [(f'status="{s}"', n) for s, n in sorted(self._beacons.items())],
                )
            )
        return "".join(parts)

    @staticmethod
    def _render_counter(
        name: str, help_text: str, series: list[tuple[str, int]]
    ) -> str:
        if not series:
            return ""  # omit the family entirely when it has no observed series
        out = [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
        for labels, value in series:
            out.append(f"{name}{{{labels}}} {value}")
        return "\n".join(out) + "\n"

    def reset(self) -> None:
        with self._lock:
            for h in self._vitals.values():
                h.reset()
            self._errors.clear()
            self._page_views.clear()
            self._attribution.clear()
            self._referrers.clear()
            self._beacons.clear()


frontend_metrics = FrontendMetrics()
"""The process-wide singleton imported by the /internal/rum route and /metrics."""

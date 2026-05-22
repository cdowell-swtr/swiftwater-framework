"""Phase 1 — fast, dependency-light checks that a deployment is alive and meeting SLOs.

Target is configured via SMOKE_TARGET (see conftest.py); default is http://localhost:8000.
"""

import time

import httpx


def test_heartbeat_is_200(client: httpx.Client):
    resp = client.get("/heartbeat")
    assert resp.status_code == 200


def test_health_reports_no_breached_slo(client: httpx.Client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    breached = [k for k, v in body["slos"].items() if v["status"] == "breached"]
    assert not breached, f"SLOs breached on the deployed target: {breached}"


def test_health_round_trip_within_2x_p99(client: httpx.Client):
    # Spec Phase 1: every service responds within 2x its defined p99 latency threshold.
    start = time.perf_counter()
    resp = client.get("/health")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert resp.status_code == 200
    threshold_ms = resp.json()["slos"]["request_latency_p99_ms"]["threshold"]
    assert elapsed_ms < 2 * threshold_ms, (
        f"/health round-trip {elapsed_ms:.0f}ms exceeded 2x p99 ({threshold_ms}ms)"
    )

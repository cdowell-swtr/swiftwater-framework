"""Phase 2 — skeleton probes of the system's critical paths on a real deployment.

Target is configured via SNIFF_TARGET (see conftest.py); default is http://localhost:8000.
"""

import httpx


def test_health_is_serving(client: httpx.Client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"ok", "degraded"}


def test_core_read_path_returns_expected_shape(client: httpx.Client):
    # Core read path: the primary data surface returns the documented shape.
    resp = client.get("/items")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:  # a deployed env is seeded; an empty store is still a valid shape
        assert set(body[0]) == {"id", "name"}

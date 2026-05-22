"""Sniff tests (CD Phase 2) — fast, stateless probes of critical paths against a real env.

Target via SNIFF_TARGET (default the local `lite` stack). Add a probe per critical path as
the project grows (auth, worker heartbeat, webhook ingress, ...) — see DEPLOY.md.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

DEFAULT_TARGET = "http://localhost:8000"


@pytest.fixture(scope="session")
def target() -> str:
    return os.environ.get("SNIFF_TARGET", DEFAULT_TARGET).rstrip("/")


@pytest.fixture
def client(target: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=target, timeout=10.0) as c:
        yield c

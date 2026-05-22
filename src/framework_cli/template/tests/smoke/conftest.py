"""Smoke tests (CD Phase 1) — hit a deployed target's liveness/readiness surface.

Target via SMOKE_TARGET (default the local `lite` stack). These run against a REAL
environment in deploy-staging.yml / deploy-prod.yml, and locally via `task test:smoke`.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

DEFAULT_TARGET = "http://localhost:8000"


@pytest.fixture(scope="session")
def target() -> str:
    return os.environ.get("SMOKE_TARGET", DEFAULT_TARGET).rstrip("/")


@pytest.fixture
def client(target: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=target, timeout=10.0) as c:
        yield c

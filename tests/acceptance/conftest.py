"""Acceptance-tier fixtures. The dev/CI /tmp is RAM-backed (tmpfs); heavy renders + dind layers
must use a disk-backed dir. `disk_tmp` yields a per-test dir under a disk-backed root
(SWIFTWATER_TEST_TMP if set, else /var/tmp/swiftwater-tests)."""

import os
import re
import shutil
from pathlib import Path

import pytest

from tests.acceptance import _tier3

_DISK_ROOT = Path(os.environ.get("SWIFTWATER_TEST_TMP", "/var/tmp/swiftwater-tests"))


def _docker_present() -> bool:
    return shutil.which("docker") is not None


def _is_xdist_worker(session) -> bool:
    """True on a pytest-xdist worker process (controller / non-xdist run → False)."""
    return hasattr(getattr(session, "config", None), "workerinput")


def _should_sweep(session) -> bool:
    """Sweep only on the controller (or a plain non-xdist run) and only when docker is on
    PATH. Under `-n`, every worker runs these hooks; a worker's *finish*-sweep would reap
    a peer worker's still-live `<slug>-t-…` stack. The controller's sessionstart fires
    before any worker starts and its sessionfinish after all workers are done, so scoping
    the sweep to the controller gives the right reaping windows with no mid-run races."""
    return not _is_xdist_worker(session) and _docker_present()


def pytest_sessionstart(session):
    """FWK95 tier-3 reaping (start-sweep): reap any transient `<slug>-t-*` stack a prior
    run left behind — a SIGKILL'd / crashed worker means `sessionfinish` never ran for
    it. Guarded so the fast (non-docker) tier never shells out and workers never sweep."""
    if _should_sweep(session):
        _tier3.sweep_tier3_stacks()


def pytest_sessionfinish(session, exitstatus):
    """FWK95 tier-3 reaping (finish-sweep): tear down every transient stack this run
    created (guaranteed reaping with no testcontainers / Ryuk sidecar)."""
    if _should_sweep(session):
        _tier3.sweep_tier3_stacks()


@pytest.fixture
def disk_tmp(request):
    _DISK_ROOT.mkdir(parents=True, exist_ok=True)
    # Key on the full nodeid (module::test), not bare node.name: under pytest-xdist
    # (FWK93) two same-named tests in different modules would otherwise collide on one
    # disk dir. The worker id keeps the path unique even if a nodeid ever repeats.
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{request.node.nodeid}-{worker}")
    d = _DISK_ROOT / slug
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)

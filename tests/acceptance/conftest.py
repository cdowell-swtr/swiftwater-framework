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
    PATH. Under `-n`, every worker shares this worktree's inst, so a worker's *finish*-sweep
    would reap a peer worker's still-live `<slug>-<inst>-t-…` stack. The controller's sessionstart fires
    before any worker starts and its sessionfinish after all workers are done, so scoping
    the sweep to the controller gives the right reaping windows with no mid-run races."""
    return not _is_xdist_worker(session) and _docker_present()


def pytest_sessionstart(session):
    """FWK95/FWK129 tier-3 reaping (start-sweep): reap any transient stacks a prior
    run left behind — a SIGKILL'd / crashed worker means `sessionfinish` never ran for
    it. Guarded so the fast (non-docker) tier never shells out and workers never sweep.

    `stale_only=True` (FWK99): inst-agnostic scope — reaps stale orphans of ANY worktree
    (incl. a `git worktree remove`d one whose inst never recurs), grace-filters young
    stacks (concurrent peers). Stays tier-2-disjoint under the FWK129 `-t-` infix ban."""
    if _should_sweep(session):
        _tier3.sweep_tier3_stacks(stale_only=True)


def pytest_sessionfinish(session, exitstatus):
    """FWK95/FWK129 tier-3 reaping (finish-sweep): tear down every transient stack this
    worktree created (guaranteed reaping with no testcontainers / Ryuk sidecar).

    Uses the exact this-worktree-inst scope (default `stale_only=False`): matches only
    ``^<slug>-<inst>-t-[0-9a-f]+$``. The FWK99 finish-side residual hazard is STRUCTURALLY
    CLOSED (FWK129): a peer worktree's ``demo-<other>-t-<uuid>`` is invisible to this
    worktree's finish-sweep by construction — not a grace-filter, a namespace disjointness."""
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

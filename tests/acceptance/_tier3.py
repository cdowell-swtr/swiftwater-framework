"""Tier-3 transient test-instance contract (FWK95 / FWK88).

The acceptance suite spins up short-lived `docker compose` stacks. Tier-3 of the FWK88
instance-addressing contract governs them:

  * **Reserved namespace** — every transient stack's ``COMPOSE_PROJECT_NAME`` is
    ``<slug>-t-<uuid>``. The ``<slug>-t-`` prefix is reserved for tier-3
    (operator-pinned in FWK88, 2026-06-28); A2/FWK74's tier-2 generator MUST reject any
    instance whose name begins with ``t-``, so tier-2 (``<slug>-<inst>``) and tier-3 are
    *structurally* disjoint — not a slug-value coincidence.
  * **Guaranteed reaping** — there is **no** testcontainers-python / Ryuk sidecar in
    this suite. Reaping is a docker label sweep over the reserved prefix at pytest
    session **start AND finish**: the finish-sweep reaps this run's stacks; the
    start-sweep reaps a prior run a SIGKILL / crashed xdist worker left behind
    (``sessionfinish`` never ran for it). The sweep keys on the
    ``com.docker.compose.project`` label docker auto-applies to every container,
    volume, and network — no custom label injection (compose has no clean per-run
    ``--label`` for all resource kinds).

Known boundaries (recorded, not silently absorbed — see ACTION_LOG):
  * Two *concurrent* acceptance sessions on one box (e.g. two worktrees, both slug
    ``demo``) share the ``demo-t-`` namespace. **Start-sweep: fixed (FWK99)** — it now
    grace-filters (``stale_only``), reaping only stale leftovers and sparing a peer's
    young live stack. **Finish-sweep: residual** — it must reap this run's own young
    stacks so it cannot grace-filter, so a session finishing while a peer still runs can
    still reap the peer's young stacks. Fully closing it needs the per-worktree-namespace
    fix (fold ``<inst>`` into the prefix → ``<slug>-<inst>-t-…``), which touches the frozen
    tier-2↔tier-3 disjointness contract → left as the FWK99 follow-up. Bites only when the
    full/docker tier runs concurrently across worktrees (branch-end, not per-commit).
  * ``test_rendered_project._run_image_serving`` uses a bare ``docker run`` (no compose
    project label), so the prefix sweep won't catch a leaked one — it is already
    context-manager-removed on every exit path.
"""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

# The acceptance render slug (DATA["project_slug"]); `test_tier3_contract.py` pins this
# equality so the reserved prefix can't drift from what the suite renders.
TIER3_SLUG = "demo"
# Reserved tier-3 namespace. The trailing hyphen is load-bearing: it makes the
# reservation structural (`demo-tango` is NOT tier-3; only `demo-t-…` is).
TIER3_PREFIX = f"{TIER3_SLUG}-t-"
# The label docker compose auto-applies to every container/volume/network it creates.
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"

# FWK99 start-sweep grace period. A tier-3 stack lives only for ONE test (brought up,
# asserted, context-manager-torn-down — minutes). A `<slug>-t-…` stack whose newest container
# is older than this is almost certainly a crashed-run leftover, not a concurrent peer session's
# still-live stack in the shared namespace. The start-sweep reaps only those (so two worktrees
# both running `task test:full` don't reap each other mid-run). The threshold is a *fixed* age,
# NOT "older than this session's start": everything visible to a start-sweep predates the sweep,
# so a session-start threshold reaps everything (a no-op). One hour is comfortably above any
# single tier-3 test yet well below a prior-day leftover.
TIER3_STALE_AGE_SECONDS = 3600.0

Runner = Callable[[list[str]], str]
Clock = Callable[[], float]


def tier3_project_name() -> str:
    """A fresh tier-3 transient ``COMPOSE_PROJECT_NAME`` of the pinned ``<slug>-t-<uuid>``
    form. The uuid hex is all-lowercase ``[0-9a-f]`` so the whole name satisfies both the
    compose project-name charset and the FWK88 ``^[a-z0-9-]+$`` instance rule."""
    return f"{TIER3_PREFIX}{uuid4().hex}"


def is_tier3_project(name: str) -> bool:
    """True iff ``name`` is in the reserved tier-3 namespace (``<slug>-t-…``)."""
    return name.startswith(TIER3_PREFIX)


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def list_tier3_projects(run: Runner = _run) -> set[str]:
    """The set of tier-3 compose project names currently present in docker — discovered
    across containers (incl. stopped), volumes, and networks via the auto-applied
    project label, then filtered to the reserved ``<slug>-t-`` prefix."""
    fmt = f'--format={{{{.Label "{COMPOSE_PROJECT_LABEL}"}}}}'
    label = f"--filter=label={COMPOSE_PROJECT_LABEL}"
    discovery = (
        ["docker", "ps", "-a", label, fmt],
        ["docker", "volume", "ls", label, fmt],
        ["docker", "network", "ls", label, fmt],
    )
    names: set[str] = set()
    for cmd in discovery:
        for line in run(cmd).splitlines():
            name = line.strip()
            if name and is_tier3_project(name):
                names.add(name)
    return names


def reap_project(project: str, run: Runner = _run) -> None:
    """Force-remove every container, volume, and network labelled with ``project``.

    Label-based (not ``docker compose down``) so it needs no compose file / cwd — it
    reaps a stack whose source tree is already gone (a crashed-worker leftover)."""
    sel = f"--filter=label={COMPOSE_PROJECT_LABEL}={project}"
    containers = run(["docker", "ps", "-aq", sel]).split()
    if containers:
        run(["docker", "rm", "-f", *containers])
    volumes = run(["docker", "volume", "ls", "-q", sel]).split()
    if volumes:
        run(["docker", "volume", "rm", "-f", *volumes])
    networks = run(["docker", "network", "ls", "-q", sel]).split()
    if networks:
        run(["docker", "network", "rm", *networks])


def _parse_docker_time(value: str) -> float | None:
    """Parse a docker ``.Created`` RFC3339(/Nano) timestamp to epoch seconds; ``None`` if blank
    or unparseable. Docker emits up to 9 fractional digits and a trailing ``Z``; clamp the
    fraction to 6 digits (``datetime.fromisoformat``'s limit) and normalize ``Z`` to ``+00:00``."""
    s = value.strip()
    if not s:
        return None
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", s
    )
    if not m:
        return None
    base, frac, tz = m.group(1), m.group(2) or "", m.group(3) or "+00:00"
    if tz == "Z":
        tz = "+00:00"
    if frac:
        frac = frac[:7]  # '.' + up to 6 digits
    try:
        return datetime.fromisoformat(f"{base}{frac}{tz}").timestamp()
    except ValueError:
        return None


def project_created_at(project: str, run: Runner = _run) -> float | None:
    """The NEWEST container-creation epoch among ``project``'s containers, or ``None`` if it has
    no containers (an orphan volume/network remnant — never a live stack). 'Newest' so a stack
    counts as young if *any* of its containers is recent (conservative against reaping a peer)."""
    sel = f"--filter=label={COMPOSE_PROJECT_LABEL}={project}"
    ids = run(["docker", "ps", "-aq", sel]).split()
    times = [
        t
        for cid in ids
        if (
            t := _parse_docker_time(
                run(["docker", "inspect", "-f", "{{.Created}}", cid])
            )
        )
        is not None
    ]
    return max(times) if times else None


def sweep_tier3_stacks(
    run: Runner = _run,
    *,
    stale_only: bool = False,
    now: Clock = time.time,
) -> set[str]:
    """Reap tier-3 transient stacks present in docker; returns the projects reaped.

    ``stale_only`` (the **start**-sweep, FWK99): reap only stacks whose newest container is older
    than ``TIER3_STALE_AGE_SECONDS`` — crashed-run leftovers — and SPARE a young stack (a
    concurrent peer session's still-live run in the shared ``<slug>-t-`` namespace). A project
    with no containers is never a live stack → reaped. Default (the **finish**-sweep) reaps every
    tier-3 stack: it must tear down this run's own young stacks, so it cannot grace-filter (the
    residual cross-session hazard it leaves at finish is closed only by the per-worktree-namespace
    follow-up, not this start-side fix)."""
    projects = list_tier3_projects(run)
    reaped: set[str] = set()
    for project in projects:
        if stale_only:
            created = project_created_at(project, run)
            if created is not None and (now() - created) < TIER3_STALE_AGE_SECONDS:
                continue  # young → a concurrent peer's live stack; spare it
        reap_project(project, run)
        reaped.add(project)
    return reaped

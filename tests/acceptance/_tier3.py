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
    ``demo``) share the ``demo-t-`` namespace, so one session's start-sweep would reap
    the other's live stacks. Out of B3's scope; tracked as FWK99 (age-filter the
    start-sweep is the cheap fix). Bites only when the full/docker tier is run
    concurrently across worktrees (branch-end, not per-commit).
  * ``test_rendered_project._run_image_serving`` uses a bare ``docker run`` (no compose
    project label), so the prefix sweep won't catch a leaked one — it is already
    context-manager-removed on every exit path.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from uuid import uuid4

# The acceptance render slug (DATA["project_slug"]); `test_tier3_contract.py` pins this
# equality so the reserved prefix can't drift from what the suite renders.
TIER3_SLUG = "demo"
# Reserved tier-3 namespace. The trailing hyphen is load-bearing: it makes the
# reservation structural (`demo-tango` is NOT tier-3; only `demo-t-…` is).
TIER3_PREFIX = f"{TIER3_SLUG}-t-"
# The label docker compose auto-applies to every container/volume/network it creates.
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"

Runner = Callable[[list[str]], str]


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


def sweep_tier3_stacks(run: Runner = _run) -> set[str]:
    """Reap every tier-3 transient stack present in docker. Returns the projects reaped."""
    projects = list_tier3_projects(run)
    for project in projects:
        reap_project(project, run)
    return projects

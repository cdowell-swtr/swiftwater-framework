"""Tier-3 transient test-instance contract (FWK95 / FWK88 / FWK129).

The acceptance suite spins up short-lived ``docker compose`` stacks. Tier-3 of the FWK88
instance-addressing contract governs them:

  * **Reserved namespace** — every transient stack's ``COMPOSE_PROJECT_NAME`` is
    ``<slug>-<inst>-t-<uuid>``, where ``<inst>`` is a per-worktree 12-char hex digest
    (SHA-256 of the canonical worktree root path). The infix marker ``-t-`` (FWK129) is
    reserved for tier-3 (operator-pinned in FWK88/FWK129); A2/FWK74's tier-2 generator
    MUST reject any instance whose name **contains** ``-t-``, so tier-2
    (``<slug>-<inst>``) and tier-3 are *structurally* disjoint — not a value coincidence.
  * **Guaranteed reaping** — there is **no** testcontainers-python / Ryuk sidecar in
    this suite. Reaping is a docker label sweep at pytest session **start AND finish**:
    the finish-sweep reaps THIS worktree's stacks (anchored exact-inst regex → can never
    touch a peer's stacks); the start-sweep reaps orphans of ANY worktree (inst-agnostic
    + grace filter), recovering stacks a deleted worktree left behind. The sweep keys on
    the ``com.docker.compose.project`` label docker auto-applies to every container,
    volume, and network — no custom label injection.

Cross-session safety (FWK99 + FWK129):
  * **Finish-sweep residual: CLOSED (FWK129)** — the per-worktree ``<inst>`` fold means
    this worktree's finish-sweep matches only ``^<slug>-<inst>-t-[0-9a-f]+$``; a peer's
    ``demo-<other>-t-<uuid>`` is invisible. Safety is structural, not a value coincidence.
  * **Start-sweep: inst-agnostic** — reaps stale orphans of ANY worktree (incl. a
    ``git worktree remove``d one whose inst never recurs), grace-filter spares young peers.
  * ``test_rendered_project._run_image_serving`` uses a bare ``docker run`` (no compose
    project label), so the prefix sweep won't catch a leaked one — it is already
    context-manager-removed on every exit path.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# The acceptance render slug (DATA["project_slug"]); `test_tier3_contract.py` pins this
# equality so the reserved prefix can't drift from what the suite renders.
TIER3_SLUG = "demo"
# The infix marker that separates <inst> from <uuid> in the tier-3 namespace.
# Lockstep with src/framework_cli/template/scripts/worktree.RESERVED_TIER3_MARKER —
# the cross-layer coupling test (test_worktree.py::test_cross_layer_marker_identity)
# asserts byte identity between the two.
RESERVED_TIER3_MARKER = "-t-"
# The label docker compose auto-applies to every container/volume/network it creates.
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"


def _worktree_instance(root: Path | None = None) -> str:
    """Fixed-width 12-char lowercase hex from SHA-256 of the canonical worktree root path.

    No git shell-out; deterministic per-worktree across runs; unique per worktree (two
    worktrees can never share an absolute realpath). Fixed-width hex means no instance
    is a string-prefix of another, and none contains the infix marker ``-t-``.
    ``root`` is injectable for hermetic tests (default: this file's repo root).
    """
    if root is None:
        root = Path(__file__).resolve().parents[2]
    return hashlib.sha256(str(root).encode()).hexdigest()[:12]


# Module-level constant: computed once at import from this worktree's absolute path.
# Tests can pass explicit paths to _worktree_instance() or to list_tier3_projects(scope_inst=)
# rather than monkeypatching this value (baked defaults would not reflect a patched value).
_TIER3_INSTANCE: str = _worktree_instance()

# Reserved tier-3 prefix for THIS worktree: <slug>-<inst>-t-.
# Membership is an anchored exact regex, NOT startswith — see is_tier3_project().
TIER3_PREFIX: str = f"{TIER3_SLUG}-{_TIER3_INSTANCE}-t-"

# FWK99 start-sweep grace period. A tier-3 stack lives only for ONE test (brought up,
# asserted, context-manager-torn-down — minutes). A `<slug>-<inst>-t-…` stack whose newest container
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
    """A fresh tier-3 transient ``COMPOSE_PROJECT_NAME`` of the form
    ``<slug>-<inst>-t-<uuid>``. The uuid hex is all-lowercase ``[0-9a-f]`` so the whole
    name satisfies both the compose project-name charset and the FWK88
    ``^[a-z0-9-]+$`` instance rule."""
    return f"{TIER3_PREFIX}{uuid4().hex}"


def is_tier3_project(name: str) -> bool:
    """True iff ``name`` is in THIS worktree's tier-3 namespace.

    Uses an anchored exact regex ``^<slug>-<inst>-t-[0-9a-f]+$`` — NOT a bare
    ``startswith``. The hex-only uuid tail and the fixed-width inst are the structural
    guarantees: a peer worktree's ``demo-<other>-t-<uuid>`` and any prefix-extension
    both fail the match.
    """
    return bool(
        re.fullmatch(
            rf"{re.escape(TIER3_SLUG)}-{re.escape(_TIER3_INSTANCE)}-t-[0-9a-f]+",
            name,
        )
    )


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def list_tier3_projects(
    run: Runner = _run,
    *,
    scope_inst: str | None = _TIER3_INSTANCE,
) -> set[str]:
    """The set of tier-3 compose project names currently present in docker.

    Discovered across containers (incl. stopped), volumes, and networks via the
    auto-applied project label, then filtered by scope:

    ``scope_inst=<inst>`` (default: this worktree's inst) — **exact-inst** scope:
        ``^<slug>-<inst>-t-[0-9a-f]+$``. The finish-sweep uses this so it can never
        list a peer worktree's stacks.

    ``scope_inst=None`` — **inst-agnostic** scope:
        ``^<slug>-[0-9a-f]+-t-[0-9a-f]+$``. The start-sweep uses this so it can
        reap orphans of a deleted worktree (whose inst never recurs). Still tier-2-disjoint
        because a tier-2 name ``<slug>-<inst2>`` would need ``<inst2>`` to contain ``-t-``,
        which the FWK129 ban forbids.
    """
    if scope_inst is None:
        pattern = re.compile(rf"^{re.escape(TIER3_SLUG)}-[0-9a-f]+-t-[0-9a-f]+$")
    else:
        pattern = re.compile(
            rf"^{re.escape(TIER3_SLUG)}-{re.escape(scope_inst)}-t-[0-9a-f]+$"
        )
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
            if name and pattern.fullmatch(name):
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

    **start-sweep** (``stale_only=True``): inst-agnostic scope (any worktree's hex inst),
    reap only stacks whose newest container is older than ``TIER3_STALE_AGE_SECONDS`` —
    crashed-run leftovers — and SPARE young stacks (concurrent peer sessions). A project
    with no containers is never a live stack → reaped. Inst-agnostic so it also reaps
    orphans left by a ``git worktree remove``d worktree.

    **finish-sweep** (default, ``stale_only=False``): exact this-worktree-inst scope
    (``^<slug>-<inst>-t-[0-9a-f]+$``) — can never list or reap a peer worktree's stacks.
    The FWK99 finish-side residual hazard is now STRUCTURALLY CLOSED (FWK129): a peer's
    ``demo-<other>-t-<uuid>`` is invisible to this worktree's finish-sweep by construction.
    """
    scope_inst: str | None = None if stale_only else _TIER3_INSTANCE
    projects = list_tier3_projects(run, scope_inst=scope_inst)
    reaped: set[str] = set()
    for project in projects:
        if stale_only:
            created = project_created_at(project, run)
            if created is not None and (now() - created) < TIER3_STALE_AGE_SECONDS:
                continue  # young → a concurrent peer's live stack; spare it
        reap_project(project, run)
        reaped.add(project)
    return reaped

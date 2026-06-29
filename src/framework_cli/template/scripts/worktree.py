"""Worktree-aware dev-stack provisioning (FWK74 / stream A2).

Computes this worktree's box-agnostic instance identity STACK_INSTANCE=<slug>-<inst>
from the git branch, sanitized to a single ^[a-z0-9-]+$ DNS label so the box's static
*.localhost cert covers it. Later sub-PLANs add the durable .env writer (FWK93),
provision via `task dev:edge` (FWK94), and symmetric deprovision (FWK95).

Plain (non-Jinja) template payload: the pure functions take slug/branch as arguments
so they are unit-testable in the framework venv; the runtime resolvers
(read_slug / current_branch) supply them from the project + git at runtime.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

# Stream B's transient COMPOSE_PROJECT_NAME namespace is <slug>-t-<uuid>; the
# <slug>-t- PREFIX is reserved for tier-3 (carving spec, "Tier-2 ↔ tier-3 name
# disjointness", PINNED 2026-06-28 by operator). A2's tier-2 generator (<slug>-<inst>)
# must reject any <inst> beginning with "t-" so the two never collide on
# COMPOSE_PROJECT_NAME. The trailing hyphen is load-bearing: "tango" is fine
# (-> <slug>-tango), "t-foo" is not (-> <slug>-t-foo, inside the reserved prefix);
# a bare "t" (-> <slug>-t) is structurally disjoint from every <slug>-t-<uuid>.
RESERVED_TIER3_PREFIX = "t-"

_NON_LABEL = re.compile(r"[^a-z0-9]+")


class Tier3NamespaceError(ValueError):
    """Raised when a branch-derived instance falls in stream B's reserved tier-3 namespace."""


def sanitize_instance(raw: str) -> str:
    """Reduce an arbitrary branch/worktree name to a single ^[a-z0-9-]+$ DNS label."""
    label = _NON_LABEL.sub("-", raw.lower()).strip("-")
    if not label:
        raise ValueError(
            f"cannot derive a valid instance label from {raw!r} "
            "(empty after sanitization); pass an explicit instance name"
        )
    return label


def build_stack_instance(slug: str, branch: str) -> str:
    """Return STACK_INSTANCE=<slug>-<sanitized-branch>, guarding B's reserved namespace."""
    inst = sanitize_instance(branch)
    if inst.startswith(RESERVED_TIER3_PREFIX):
        raise Tier3NamespaceError(
            f"instance {inst!r} is in the reserved tier-3 namespace "
            f"(the {RESERVED_TIER3_PREFIX!r} prefix); rename the branch or pass an "
            "explicit instance name (--instance, FWK94)"
        )
    return f"{slug}-{inst}"


_NAME_KEY = re.compile(r"^name:\s*(?P<name>[A-Za-z0-9._-]+)\s*$", re.MULTILINE)

# Path to the rendered project's compose base, relative to the project root.
COMPOSE_BASE = Path("infra/compose/base.yml")


def read_slug(base_yml: Path = COMPOSE_BASE) -> str:
    """Return the compose project name (== the slug / COMPOSE_PROJECT_NAME default)."""
    m = _NAME_KEY.search(base_yml.read_text())
    if not m:
        raise ValueError(f"no top-level `name:` key found in {base_yml}")
    return m.group("name")


def current_branch(cwd: Path | None = None) -> str:
    """Return the current git branch name.

    `symbolic-ref --short HEAD` resolves the branch even on an unborn branch (no
    commits yet) and errors loudly on a detached HEAD — a parallel-dev worktree is
    always on a named branch, so a detached HEAD is a real misuse worth failing on.
    """
    out = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def resolve_stack_instance(
    base_yml: Path = COMPOSE_BASE, cwd: Path | None = None
) -> str:
    """Compute this worktree's STACK_INSTANCE from the compose slug + the git branch."""
    return build_stack_instance(read_slug(base_yml), current_branch(cwd))


# --- Durable per-worktree .env (FWK93) -----------------------------------

# The durable .env is the project's gitignored .env (per-worktree by working tree).
ENV_PATH = Path(".env")


def parse_env(text: str) -> dict[str, str]:
    """Plain KEY=VAL reader: skip blanks/comments/non-assignments; last wins."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def merge_env_vars(text: str, updates: dict[str, str]) -> str:
    """Update each key in place where it is a real KEY=… assignment, else append.

    Comment lines are never matched, so a commented `# PORT_OFFSET=` decoy cannot be
    mistaken for the live assignment.
    """
    remaining = dict(updates)
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in remaining:
                out_lines.append(f"{key}={remaining.pop(key)}")
                continue
        out_lines.append(line)
    out_lines.extend(f"{key}={value}" for key, value in remaining.items())
    result = "\n".join(out_lines)
    if not text or text.endswith("\n"):
        result += "\n"
    return result


def write_env(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    """Idempotently merge `updates` into the durable .env at `path` (create if absent)."""
    text = path.read_text() if path.exists() else ""
    path.write_text(merge_env_vars(text, updates))


# --- PORT_OFFSET selection via live introspection (FWK93) -----------------

# Host-port defaults mirrored from scripts/compose.sh (FWK31). The all-battery
# superset: over-reserving a port a disabled battery wouldn't publish is safe
# (it only makes selection more conservative, never less).
BASE_HOST_PORTS: tuple[int, ...] = (
    80,  # TRAEFIK_HTTP
    443,  # TRAEFIK_HTTPS
    3000,  # GRAFANA
    3100,  # LOKI
    3200,  # TEMPO
    5173,  # FRONTEND
    5432,  # POSTGRES
    6379,  # REDIS
    8000,  # HTTP (app)
    9090,  # PROMETHEUS
    9093,  # ALERTMANAGER
    9121,  # REDIS_EXPORTER
    9187,  # POSTGRES_EXPORTER
    9216,  # MONGODB_EXPORTER
    9808,  # CELERY_EXPORTER
    27017,  # MONGO
)

OFFSET_STEP = 1000

_MAX_HOST_PORT = 65535
_PUBLISHED_PORT = re.compile(r":(\d+)->")


def running_host_ports(
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> set[int]:
    """Return the set of host ports currently published by running containers.

    The single docker touch in this module — `run` is injectable so unit tests
    can feed canned `docker ps` output with no daemon.
    """
    out = run(
        ["docker", "ps", "--format", "{{.Ports}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {int(port) for port in _PUBLISHED_PORT.findall(out.stdout)}


def select_port_offset(
    occupied: set[int],
    *,
    base_ports: tuple[int, ...] = BASE_HOST_PORTS,
    step: int = OFFSET_STEP,
) -> int:
    """Lowest multiple of `step` whose shifted port window avoids `occupied`.

    The port-set disjointness check subsumes the offset-diff self-collision (a
    higher window's low port landing on a lower window's high port) with no
    special-casing. Raises RuntimeError when every in-range window is occupied.
    """
    highest = max(base_ports)
    offset = 0
    while highest + offset <= _MAX_HOST_PORT:
        window = {port + offset for port in base_ports}
        if window.isdisjoint(occupied):
            return offset
        offset += step
    raise RuntimeError(
        "no free PORT_OFFSET: every candidate host-port window is occupied"
    )


# --- Provision planner: identity + .env + offset reconcile (FWK93) --------


def plan_provision(
    env_text: str,
    instance: str,
    *,
    with_ports: bool,
    occupied: set[int] | None = None,
) -> dict[str, str]:
    """Compute the durable-.env updates for provisioning `instance`.

    STACK_INSTANCE / COMPOSE_PROJECT_NAME are always the resolved `instance` literal.
    With `--ports`, PORT_OFFSET is reused verbatim when the .env records a prior SELECTION
    for this instance (the PORT_OFFSET_FOR marker — the /clear reconcile, never re-introspect
    a live stack), else freshly selected. The marker distinguishes a deliberately-selected
    offset (incl. a legitimate 0) from the template default PORT_OFFSET=0 (carry-forward #1).
    """
    updates = {"STACK_INSTANCE": instance, "COMPOSE_PROJECT_NAME": instance}
    if with_ports:
        recorded = parse_env(env_text)
        if recorded.get("PORT_OFFSET_FOR") == instance and "PORT_OFFSET" in recorded:
            updates["PORT_OFFSET"] = recorded["PORT_OFFSET"]
        else:
            updates["PORT_OFFSET"] = str(select_port_offset(occupied or set()))
        updates["PORT_OFFSET_FOR"] = instance
    return updates


# --- Provision orchestration: up → export → task dev:edge (FWK94) ---------

# FWK88-frozen edge-routable observability UIs (A1 adds the discovery labels). loki/tempo/
# exporters/otel-collector have no UI and are not edge-routable. A2 only selects from this set.
ROUTABLE_OBS: tuple[str, ...] = ("grafana", "prometheus", "alertmanager")


def parse_obs_selection(raw: str) -> tuple[str, ...]:
    """Parse/validate a comma-separated --obs list against the frozen routable set."""
    selected = tuple(part.strip() for part in raw.split(",") if part.strip())
    invalid = [svc for svc in selected if svc not in ROUTABLE_OBS]
    if invalid:
        raise ValueError(
            f"--obs: {invalid} not edge-routable; choose from {list(ROUTABLE_OBS)}"
        )
    return selected


def provision(
    instance: str,
    *,
    with_ports: bool,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    env_path: Path = ENV_PATH,
) -> int:
    """Provision this worktree's stack: plan → write durable .env → export → task dev:edge.

    Exports STACK_INSTANCE/COMPOSE_PROJECT_NAME (+ PORT_OFFSET when --ports) into the
    dev:edge child environment, so compose.sh sees an EXPORTED PORT_OFFSET — never a bare
    .env value (the whole reason this engine exports rather than leaning on `dotenv:`).
    """
    occupied = running_host_ports(run=run) if with_ports else set()
    env_text = env_path.read_text() if env_path.exists() else ""
    updates = plan_provision(
        env_text, instance, with_ports=with_ports, occupied=occupied
    )
    write_env(updates, path=env_path)
    child_env = {**os.environ, **updates}
    run(["task", "dev:edge"], check=True, env=child_env)
    return 0


# --- Deprovision: worktree:down (FWK95) ----------------------------------

# Cleared on `down` so a later `up --ports` re-introspects + picks fresh (offset
# "release"): the FWK94 reconcile-verbatim path would otherwise reuse a stale recorded
# offset another worktree may have grabbed. STACK_INSTANCE/COMPOSE_PROJECT_NAME are kept.
OFFSET_RELEASE_KEYS: tuple[str, ...] = ("PORT_OFFSET", "PORT_OFFSET_FOR")


def remove_env_vars(text: str, keys: set[str]) -> str:
    """Drop any real KEY=… assignment whose key is in `keys` (comments untouched).

    The symmetric counterpart to merge_env_vars: a commented `# PORT_OFFSET=` decoy is
    never matched, and the trailing-newline convention is preserved.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            if stripped.partition("=")[0].strip() in keys:
                continue
        out_lines.append(line)
    result = "\n".join(out_lines)
    if not text or text.endswith("\n"):
        result += "\n"
    return result


def resolve_provisioned_instance(env_text: str) -> str:
    """Return the STACK_INSTANCE a prior `up` recorded; error if none.

    `down` reads the instance from the durable .env — NOT re-derived from the branch
    (design line 77): a branch renamed after `up` would otherwise tear down the wrong
    stack.
    """
    instance = parse_env(env_text).get("STACK_INSTANCE")
    if not instance:
        raise ValueError(
            "nothing provisioned for this worktree (.env has no STACK_INSTANCE) — "
            "run `worktree up` first"
        )
    return instance


def deprovision(
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    env_path: Path = ENV_PATH,
) -> int:
    """Tear down this worktree's stack (with volume reclaim) + release the port offset.

    `down -v` reclaims the named volumes the normal `dev:down` keeps by design (so the
    worktree path would otherwise leak 3–7 volumes). Edge-disconnect from the shared edge
    net (A1's `dev:edge:down`) is a Milestone-M carry-forward — pre-A1 there is no shared
    edge net to disconnect from. Ordered before `git worktree remove` (the operator's next
    step; this tool never removes the worktree itself).
    """
    env_text = env_path.read_text() if env_path.exists() else ""
    instance = resolve_provisioned_instance(env_text)
    run(["docker", "compose", "-p", instance, "down", "-v"], check=True)
    released = remove_env_vars(env_text, set(OFFSET_RELEASE_KEYS))
    if released != env_text:
        env_path.write_text(released)
    print(
        f"stack {instance!r} torn down (volumes reclaimed). "
        "Run `git worktree remove <path>` to remove this worktree."
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """CLI entrypoint. `up` provisions this worktree's stack; `down` deprovisions it."""
    parser = argparse.ArgumentParser(prog="worktree", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser(
        "up", help="provision this worktree's stack behind the shared edge"
    )
    up.add_argument(
        "--ports",
        action="store_true",
        help="also allocate a free PORT_OFFSET for direct host access",
    )
    up.add_argument(
        "--obs",
        default="",
        help=f"comma-separated obs UIs to expose ({', '.join(ROUTABLE_OBS)})",
    )
    up.add_argument(
        "--instance",
        default="",
        help="override the branch-derived instance (escape hatch for a reserved name)",
    )
    sub.add_parser("down", help="tear down this worktree's stack + reclaim its volumes")
    args = parser.parse_args(argv)

    if args.command == "up":
        try:
            parse_obs_selection(
                args.obs
            )  # validate now; edge propagation is Milestone M
        except ValueError as exc:
            parser.error(str(exc))
        if args.instance:
            source = args.instance
        else:
            try:
                source = current_branch()
            except subprocess.CalledProcessError:
                # detached HEAD or non-git cwd: git can't name a branch. Friendly hint
                # (carried-forward FWK92 Minor — don't surface a raw traceback at the CLI).
                parser.error(
                    "could not determine the git branch (detached HEAD?); "
                    "pass --instance to name the worktree explicitly"
                )
        try:
            instance = build_stack_instance(read_slug(), source)
        except Tier3NamespaceError as exc:
            parser.error(f"{exc} — pass --instance to override")
        return provision(instance, with_ports=args.ports, run=run)

    if args.command == "down":
        try:
            return deprovision(run=run)
        except ValueError as exc:
            parser.error(str(exc))

    parser.error(f"unknown command {args.command!r}")  # unreachable (required=True)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

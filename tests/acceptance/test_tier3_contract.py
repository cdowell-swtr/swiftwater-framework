"""Tier-3 transient-instance contract — stream-B B3 (FWK95, consuming FWK88).

Docker-FREE guard for the tier-3 leg of the FWK88 instance-addressing contract, so
it runs in the fast tier (it is not a documented docker exception in
`test_test_tiers.py`). It pins, statically:

  * the **per-worktree reserved namespace** `<slug>-<inst>-t-<uuid>` (FWK129, completing the
    FWK88 operator-pinned `-t-` reservation) and the structural tier-2↔tier-3 disjointness it buys;
  * the **reaping** sweep logic (with an injected runner — no real docker here);
  * the **isolation guards**: no transient stack joins an external/shared edge net,
    and the default `lite` transient stack mounts no host docker socket.

The docker-requiring half (the reaper firing on real stacks, the fixture's runtime
project name) lives in `test_rendered_project.py` / the session hooks, exercised in
the full tier.
"""

import re
from datetime import datetime

import yaml

from tests._render_cache import render_project
from tests.acceptance import _tier3

# The acceptance render answer-set (kept local to stay docker-free / fast-tier).
DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


# --- reserved namespace + tier-2↔tier-3 disjointness (FWK88 + FWK129) ---


def test_tier3_slug_matches_render_data():
    """The reserved prefix is derived from the slug the suite actually renders — pin
    the equality so the two can't silently drift."""
    assert _tier3.TIER3_SLUG == DATA["project_slug"]


def test_tier3_inst_format():
    """FWK129: _TIER3_INSTANCE is a fixed-width 12-char lowercase hex string (sha256[:12])."""
    assert re.fullmatch(r"[0-9a-f]{12}", _tier3._TIER3_INSTANCE), _tier3._TIER3_INSTANCE


def test_tier3_instance_unique_per_path():
    """FWK129: two different root paths produce two different 12-char hex instances
    (structural uniqueness — no two worktrees share an absolute realpath)."""
    from pathlib import Path

    inst_a = _tier3._worktree_instance(Path("/some/path/a"))
    inst_b = _tier3._worktree_instance(Path("/some/path/b"))
    assert inst_a != inst_b
    assert re.fullmatch(r"[0-9a-f]{12}", inst_a)
    assert re.fullmatch(r"[0-9a-f]{12}", inst_b)


def test_tier3_prefix_is_slug_dash_inst_dash_t_dash():
    """FWK129: TIER3_PREFIX is per-worktree: <slug>-<inst>-t- (12-char hex inst)."""
    inst = _tier3._TIER3_INSTANCE
    assert _tier3.TIER3_PREFIX == f"{DATA['project_slug']}-{inst}-t-"


def test_tier3_project_name_matches_pinned_form():
    inst = _tier3._TIER3_INSTANCE
    slug = DATA["project_slug"]
    name = _tier3.tier3_project_name()
    assert re.fullmatch(rf"{re.escape(slug)}-{re.escape(inst)}-t-[0-9a-f]+", name), name
    assert _tier3.is_tier3_project(name)


def test_tier3_project_names_are_unique_per_call():
    assert _tier3.tier3_project_name() != _tier3.tier3_project_name()


def test_tier3_reservation_is_structural_not_a_value_coincidence():
    """FWK129: tier-3 membership is an anchored exact-inst regex, not a bare startswith.
    A peer's `demo-<other>-t-<uuid>` and any prefix-extension are excluded by the regex."""
    inst = _tier3._TIER3_INSTANCE
    slug = DATA["project_slug"]
    # a valid tier-3 name for THIS worktree
    own_name = f"{slug}-{inst}-t-{'a' * 32}"
    assert _tier3.is_tier3_project(own_name)
    # different inst (peer worktree) → excluded
    other_inst = ("a" * 12) if inst != ("a" * 12) else ("b" * 12)
    assert not _tier3.is_tier3_project(f"{slug}-{other_inst}-t-{'a' * 32}")
    # old bare prefix format → excluded (no inst in the name)
    assert not _tier3.is_tier3_project(f"{slug}-t-deadbeef")
    # unrelated names
    assert not _tier3.is_tier3_project("demo")
    assert not _tier3.is_tier3_project("demo-prod")
    assert not _tier3.is_tier3_project(f"other-{inst}-t-1")
    # prefix-extension → excluded (non-hex character after -t-)
    assert not _tier3.is_tier3_project(f"{slug}-{inst}-t-{'a' * 32}-extra")


# --- reaping sweep logic (injected runner; no real docker) ---


def test_list_tier3_projects_filters_to_exact_inst_and_dedups():
    """FWK129: list_tier3_projects with the default exact-inst scope (finish-sweep)
    filters to THIS worktree's inst, deduplicates, and ignores non-matching names."""
    inst = _tier3._TIER3_INSTANCE
    slug = DATA["project_slug"]
    other_inst = ("a" * 12) if inst != ("a" * 12) else ("b" * 12)

    def fake_run(cmd):
        return (
            f"{slug}-{inst}-t-aaa\n"
            f"{slug}\n"
            f"other-{inst}-t-bbb\n"
            f"{slug}-{inst}-t-aaa\n"  # duplicate
            f"{slug}-{inst}-t-ccc\n"
            f"{slug}-{other_inst}-t-ddd\n"  # peer worktree → excluded
        )

    result = _tier3.list_tier3_projects(run=fake_run)
    assert result == {f"{slug}-{inst}-t-aaa", f"{slug}-{inst}-t-ccc"}


def test_list_tier3_projects_inst_agnostic_includes_all_worktrees():
    """FWK129: scope_inst=None (start-sweep) collects names from ANY worktree's inst."""
    inst_a = "aaaaaaaaaaaa"
    inst_b = "bbbbbbbbbbbb"
    slug = DATA["project_slug"]

    def fake_run(cmd):
        return (
            f"{slug}-{inst_a}-t-{'0' * 32}\n"
            f"{slug}-{inst_b}-t-{'1' * 32}\n"
            f"{slug}-t-oldformat\n"  # old bare-prefix format → excluded (not pure hex inst)
            "demo\n"
        )

    result = _tier3.list_tier3_projects(run=fake_run, scope_inst=None)
    assert result == {
        f"{slug}-{inst_a}-t-{'0' * 32}",
        f"{slug}-{inst_b}-t-{'1' * 32}",
    }


def test_reap_project_removes_containers_volumes_and_networks():
    commands = []

    def fake_run(cmd):
        commands.append(cmd)
        if cmd[:3] == ["docker", "ps", "-aq"]:
            return "c1\nc2\n"
        if cmd[:3] == ["docker", "volume", "ls"]:
            return "v1\n"
        if cmd[:3] == ["docker", "network", "ls"]:
            return "n1\n"
        return ""

    _tier3.reap_project("demo-t-x", run=fake_run)
    assert ["docker", "rm", "-f", "c1", "c2"] in commands
    assert ["docker", "volume", "rm", "-f", "v1"] in commands
    assert ["docker", "network", "rm", "n1"] in commands


def test_reap_project_is_a_noop_when_nothing_matches():
    commands = []

    def fake_run(cmd):
        commands.append(cmd)
        return ""

    _tier3.reap_project("demo-t-empty", run=fake_run)
    # no rm/remove commands issued when discovery is empty
    assert not any(
        c[1] in ("rm",) or c[:3] == ["docker", "network", "rm"] for c in commands
    )
    assert not any(c[:3] == ["docker", "volume", "rm"] for c in commands)


def test_sweep_lists_then_reaps_each(monkeypatch):
    inst = _tier3._TIER3_INSTANCE
    projects = {f"demo-{inst}-t-1", f"demo-{inst}-t-2"}
    monkeypatch.setattr(
        _tier3, "list_tier3_projects", lambda run=None, *, scope_inst=None: projects
    )
    reaped = []
    monkeypatch.setattr(_tier3, "reap_project", lambda p, run=None: reaped.append(p))
    out = _tier3.sweep_tier3_stacks(run=lambda cmd: "")
    assert set(reaped) == projects
    assert out == projects


# --- FWK99 + FWK129: start-sweep grace filter + per-worktree finish-sweep isolation ---


def test_start_sweep_spares_young_peer_and_reaps_stale_and_orphan(monkeypatch):
    """The start-sweep (`stale_only=True`, inst-agnostic) reaps only stacks whose newest
    container is older than the grace period — and SPARES young stacks (concurrent peers,
    any worktree). A project with no containers (an orphan remnant) is never a live stack
    → reaped regardless of age.

    Fixed age threshold, NOT "older than this session's start": every stack visible to a
    start-sweep predates the sweep, so a session-start threshold is a no-op. A healthy
    tier-3 stack lives only minutes; a fixed grace separates leftovers (old) from peers."""
    inst = _tier3._TIER3_INSTANCE
    young = f"demo-{inst}-t-young"
    stale = f"demo-{inst}-t-stale"
    orphan = f"demo-{inst}-t-orphan"
    monkeypatch.setattr(
        _tier3,
        "list_tier3_projects",
        lambda run=None, *, scope_inst=None: {young, stale, orphan},
    )
    now = 1_000_000.0
    ages = {
        young: now - 30.0,  # 30s old → a peer mid-test, spare it
        stale: now - (_tier3.TIER3_STALE_AGE_SECONDS + 60.0),  # older than grace
        orphan: None,  # no containers → not a live stack
    }
    monkeypatch.setattr(_tier3, "project_created_at", lambda p, run=None: ages[p])
    reaped: list[str] = []
    monkeypatch.setattr(_tier3, "reap_project", lambda p, run=None: reaped.append(p))
    out = _tier3.sweep_tier3_stacks(
        run=lambda cmd: "", stale_only=True, now=lambda: now
    )
    assert set(reaped) == {stale, orphan}
    assert young not in reaped
    assert out == {stale, orphan}


def test_finish_sweep_reaps_all_including_young(monkeypatch):
    """FWK129: finish-sweep (default) reaps ALL stacks in THIS worktree's exact-inst scope.
    The FWK99 residual cross-session hazard is CLOSED: a peer's stacks are structurally
    invisible to the finish-sweep (different inst, anchored regex)."""
    inst = _tier3._TIER3_INSTANCE
    young = f"demo-{inst}-t-young"
    stale = f"demo-{inst}-t-stale"
    monkeypatch.setattr(
        _tier3,
        "list_tier3_projects",
        lambda run=None, *, scope_inst=None: {young, stale},
    )
    monkeypatch.setattr(_tier3, "project_created_at", lambda p, run=None: 1_000_000.0)
    reaped: list[str] = []
    monkeypatch.setattr(_tier3, "reap_project", lambda p, run=None: reaped.append(p))
    out = _tier3.sweep_tier3_stacks(run=lambda cmd: "", now=lambda: 1_000_000.0)
    assert set(reaped) == {young, stale}
    assert out == {young, stale}


def test_project_created_at_returns_newest_container_time():
    """`project_created_at` returns the NEWEST container-creation epoch among a project's
    containers (a stack counts as 'young' if any container is recent)."""

    def run(cmd: list[str]) -> str:
        if cmd[:3] == ["docker", "ps", "-aq"]:
            return "cid_old\ncid_new\n"
        if cmd[:3] == ["docker", "inspect", "-f"]:
            return {
                "cid_old": "2026-06-28T22:00:00.000000000Z",
                "cid_new": "2026-06-28T22:05:00Z",
            }[cmd[-1]]
        return ""

    got = _tier3.project_created_at("demo-t-x", run=run)
    assert got == datetime.fromisoformat("2026-06-28T22:05:00+00:00").timestamp()


def test_project_created_at_is_none_without_containers():
    assert _tier3.project_created_at("demo-t-x", run=lambda cmd: "") is None


def test_parse_docker_time_handles_nanoseconds_z_and_garbage():
    assert (
        _tier3._parse_docker_time("2026-06-28T22:05:00.123456789Z")
        == datetime.fromisoformat("2026-06-28T22:05:00.123456+00:00").timestamp()
    )
    assert _tier3._parse_docker_time("  ") is None
    assert _tier3._parse_docker_time("not-a-timestamp") is None


# --- isolation guards: no edge net, no socket in the default transient stack ---


def test_transient_compose_path_declares_no_external_edge_network(tmp_path):
    """Tier-3 stays on the per-project default network — no `external: true` network
    (the shared box edge net A1/FWK75 may add later) in *any* compose overlay a transient
    stack can compose in (base + dev + observability)."""
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    for fname in ("base.yml", "dev.yml", "observability.yml"):
        doc = yaml.safe_load((dest / "infra" / "compose" / fname).read_text())
        for net, spec in (doc.get("networks") or {}).items():
            assert not (isinstance(spec, dict) and spec.get("external")), (
                f"{fname} declares external network {net!r}; a tier-3 transient stack "
                "must stay on its own per-project default network"
            )


def test_lite_transient_stack_mounts_no_docker_socket(tmp_path):
    """The default transient stack (`base + dev`, `--profile lite`) mounts no host
    docker socket — the tier-3 contract bans a socket-mounting reaper sidecar
    (no testcontainers / Ryuk).

    Scoped to the `lite` stack deliberately: dev-profile `traefik` (and the
    observability `promtail`) DO mount the socket, but as the rendered *product under
    test* — a per-stack reverse proxy / log shipper doing its own container discovery,
    not a shared edge and not a test-harness reaper. Tier-3's "no socket" is about the
    isolation mechanism, so the guard pins the lightweight DB-backed `lite` stack the
    transient tier actually uses: that is `base.yml`'s always-on services (no `profiles`
    key) plus `dev.yml`'s `lite`-profile services.
    """
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    base = yaml.safe_load((dest / "infra" / "compose" / "base.yml").read_text())
    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())

    lite_stack = {
        # base.yml: a service with no `profiles` is always part of the stack (incl. lite).
        f"base.yml:{svc}": spec
        for svc, spec in (base.get("services") or {}).items()
        if not (spec.get("profiles") or [])
    }
    lite_stack.update(
        {
            f"dev.yml:{svc}": spec
            for svc, spec in dev["services"].items()
            if "lite" in (spec.get("profiles") or [])
        }
    )
    assert any(k.startswith("dev.yml:") for k in lite_stack), (
        "expected the dev overlay to define a `lite` profile"
    )
    for svc, spec in lite_stack.items():
        for vol in spec.get("volumes") or []:
            assert "/var/run/docker.sock" not in str(vol), (
                f"lite-stack service {svc!r} mounts the docker socket"
            )


# --- session hooks: reap at session start AND finish, guarded by docker presence ---


class _FakeSession:
    """Stand-in for a pytest Session. A worker carries `config.workerinput`."""

    def __init__(self, *, worker: bool):
        self.config = type("Cfg", (), {})()
        if worker:
            self.config.workerinput = {"workerid": "gw0"}


def test_session_hooks_sweep_on_controller_when_docker_is_present(monkeypatch):
    from tests.acceptance import conftest

    calls = []
    monkeypatch.setattr(
        conftest._tier3,
        "sweep_tier3_stacks",
        lambda **kw: calls.append(kw.get("stale_only", False)),
    )
    monkeypatch.setattr(conftest.shutil, "which", lambda name: "/usr/bin/docker")
    controller = _FakeSession(worker=False)
    conftest.pytest_sessionstart(session=controller)
    conftest.pytest_sessionfinish(session=controller, exitstatus=0)
    # Both sweeps fire on the controller; the start-sweep grace-filters (FWK99,
    # `stale_only=True`), the finish-sweep reaps everything (`stale_only` defaulted False).
    assert calls == [True, False]


def test_session_hooks_do_not_sweep_on_an_xdist_worker(monkeypatch):
    """A worker's finish-sweep would reap a peer worker's still-live stack — only the
    controller sweeps (its windows bracket all workers)."""
    from tests.acceptance import conftest

    monkeypatch.setattr(conftest.shutil, "which", lambda name: "/usr/bin/docker")
    called = []
    monkeypatch.setattr(
        conftest._tier3, "sweep_tier3_stacks", lambda **kw: called.append(1)
    )
    worker = _FakeSession(worker=True)
    conftest.pytest_sessionstart(session=worker)
    conftest.pytest_sessionfinish(session=worker, exitstatus=0)
    assert called == []


def test_session_hooks_are_a_noop_without_docker(monkeypatch):
    from tests.acceptance import conftest

    monkeypatch.setattr(conftest.shutil, "which", lambda name: None)
    called = []
    monkeypatch.setattr(
        conftest._tier3, "sweep_tier3_stacks", lambda **kw: called.append(1)
    )
    controller = _FakeSession(worker=False)
    conftest.pytest_sessionstart(session=controller)
    conftest.pytest_sessionfinish(session=controller, exitstatus=0)
    assert called == []

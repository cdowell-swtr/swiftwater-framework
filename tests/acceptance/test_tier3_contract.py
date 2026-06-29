"""Tier-3 transient-instance contract — stream-B B3 (FWK95, consuming FWK88).

Docker-FREE guard for the tier-3 leg of the FWK88 instance-addressing contract, so
it runs in the fast tier (it is not a documented docker exception in
`test_test_tiers.py`). It pins, statically:

  * the **reserved namespace** `<slug>-t-<uuid>` (operator-pinned in FWK88) and the
    structural tier-2↔tier-3 disjointness it buys;
  * the **reaping** sweep logic (with an injected runner — no real docker here);
  * the **isolation guards**: no transient stack joins an external/shared edge net,
    and the default `lite` transient stack mounts no host docker socket.

The docker-requiring half (the reaper firing on real stacks, the fixture's runtime
project name) lives in `test_rendered_project.py` / the session hooks, exercised in
the full tier.
"""

import re

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


# --- reserved namespace + tier-2↔tier-3 disjointness (FWK88, operator-pinned) ---


def test_tier3_slug_matches_render_data():
    """The reserved prefix is derived from the slug the suite actually renders — pin
    the equality so the two can't silently drift."""
    assert _tier3.TIER3_SLUG == DATA["project_slug"]


def test_tier3_prefix_is_slug_dash_t_dash():
    assert _tier3.TIER3_PREFIX == f"{DATA['project_slug']}-t-"


def test_tier3_project_name_matches_pinned_form():
    name = _tier3.tier3_project_name()
    assert re.fullmatch(rf"{re.escape(DATA['project_slug'])}-t-[0-9a-f]+", name), name
    assert _tier3.is_tier3_project(name)


def test_tier3_project_names_are_unique_per_call():
    assert _tier3.tier3_project_name() != _tier3.tier3_project_name()


def test_tier3_reservation_is_structural_not_a_value_coincidence():
    """A2/FWK74's tier-2 names are `<slug>-<inst>`; the `t-`-prefix ban makes them
    disjoint from tier-3 *structurally*. A tier-2-style name that merely *starts with*
    the letter t (`demo-tango`) is NOT tier-3 — only the exact `<slug>-t-` prefix is."""
    assert _tier3.is_tier3_project("demo-t-deadbeef")
    assert not _tier3.is_tier3_project(
        "demo-tango-1"
    )  # starts with 'demo-t' but not 'demo-t-'
    assert not _tier3.is_tier3_project("demo")
    assert not _tier3.is_tier3_project("demo-prod")
    assert not _tier3.is_tier3_project("other-t-1")


# --- reaping sweep logic (injected runner; no real docker) ---


def test_list_tier3_projects_filters_to_reserved_prefix_and_dedups():
    def fake_run(cmd):
        # every discovery command returns the same project-label dump
        return "demo-t-aaa\ndemo\nother-t-bbb\ndemo-t-aaa\ndemo-t-ccc\n"

    assert _tier3.list_tier3_projects(run=fake_run) == {"demo-t-aaa", "demo-t-ccc"}


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
    monkeypatch.setattr(
        _tier3, "list_tier3_projects", lambda run=None: {"demo-t-1", "demo-t-2"}
    )
    reaped = []
    monkeypatch.setattr(_tier3, "reap_project", lambda p, run=None: reaped.append(p))
    out = _tier3.sweep_tier3_stacks(run=lambda cmd: "")
    assert set(reaped) == {"demo-t-1", "demo-t-2"}
    assert out == {"demo-t-1", "demo-t-2"}


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
        conftest._tier3, "sweep_tier3_stacks", lambda: calls.append("swept")
    )
    monkeypatch.setattr(conftest.shutil, "which", lambda name: "/usr/bin/docker")
    controller = _FakeSession(worker=False)
    conftest.pytest_sessionstart(session=controller)
    conftest.pytest_sessionfinish(session=controller, exitstatus=0)
    assert calls == ["swept", "swept"]  # start-sweep + finish-sweep


def test_session_hooks_do_not_sweep_on_an_xdist_worker(monkeypatch):
    """A worker's finish-sweep would reap a peer worker's still-live stack — only the
    controller sweeps (its windows bracket all workers)."""
    from tests.acceptance import conftest

    monkeypatch.setattr(conftest.shutil, "which", lambda name: "/usr/bin/docker")
    called = []
    monkeypatch.setattr(conftest._tier3, "sweep_tier3_stacks", lambda: called.append(1))
    worker = _FakeSession(worker=True)
    conftest.pytest_sessionstart(session=worker)
    conftest.pytest_sessionfinish(session=worker, exitstatus=0)
    assert called == []


def test_session_hooks_are_a_noop_without_docker(monkeypatch):
    from tests.acceptance import conftest

    monkeypatch.setattr(conftest.shutil, "which", lambda name: None)
    called = []
    monkeypatch.setattr(conftest._tier3, "sweep_tier3_stacks", lambda: called.append(1))
    controller = _FakeSession(worker=False)
    conftest.pytest_sessionstart(session=controller)
    conftest.pytest_sessionfinish(session=controller, exitstatus=0)
    assert called == []

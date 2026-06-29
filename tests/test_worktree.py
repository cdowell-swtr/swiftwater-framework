"""FWK92 — worktree instance identity. Framework-level: loads the plain template
script via importlib and exercises the pure functions in the framework venv (no
render), mirroring tests/test_check_migrations.py."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src/framework_cli/template/scripts/worktree.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("worktree", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- sanitize_instance ---------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("fwk92-instance-identity", "fwk92-instance-identity"),  # already clean
        ("Feature/Foo_Bar", "feature-foo-bar"),  # slash, underscore, case
        ("---edge---", "edge"),  # trim leading/trailing dashes
        ("a__b//c", "a-b-c"),  # collapse runs to one dash
        ("CAPS", "caps"),  # lowercase
    ],
)
def test_sanitize_instance(raw, expected):
    mod = _load()
    assert mod.sanitize_instance(raw) == expected


def test_sanitize_instance_empty_raises():
    mod = _load()
    with pytest.raises(ValueError):
        mod.sanitize_instance("___")


def test_sanitize_instance_output_is_a_single_dns_label():
    import re

    mod = _load()
    for raw in ("Feature/Foo", "x..y", "9-Lives", "a/b/c"):
        out = mod.sanitize_instance(raw)
        assert re.fullmatch(r"[a-z0-9-]+", out), out
        assert not out.startswith("-") and not out.endswith("-")


# --- build_stack_instance ------------------------------------------------


def test_build_stack_instance_happy():
    mod = _load()
    assert mod.build_stack_instance("acme", "feature/foo") == "acme-feature-foo"


def test_build_stack_instance_tier3_reserved_raises():
    mod = _load()
    # An instance beginning with "t-" would enter B's reserved tier-3 prefix
    # <slug>-t-<uuid> (carving spec, "Tier-2 ↔ tier-3 name disjointness", PINNED
    # 2026-06-28) — A2 must never emit it.
    with pytest.raises(mod.Tier3NamespaceError):
        mod.build_stack_instance("acme", "t-1234")


def test_build_stack_instance_tier3_ban_is_t_dash_prefix_not_bare_t():
    # The pinned ban reserves the "t-" PREFIX, not the bare letter "t": the trailing
    # hyphen is load-bearing. "demo-tango" is fine (t not followed by "-"); "demo-t-foo"
    # is not (inside tier-3's reserved "demo-t-" prefix); "demo-t" is fine (structurally
    # disjoint from every "demo-t-<uuid>").
    mod = _load()
    assert mod.build_stack_instance("demo", "tango") == "demo-tango"
    assert mod.build_stack_instance("demo", "test-branch") == "demo-test-branch"
    assert mod.build_stack_instance("demo", "t") == "demo-t"  # bare t allowed
    with pytest.raises(mod.Tier3NamespaceError):
        mod.build_stack_instance("demo", "t-foo")


def test_tier2_name_never_enters_tier3_reserved_prefix():
    # Structural disjointness, not coincidental: for any accepted instance, <slug>-<inst>
    # never begins with the tier-3 reserved prefix <slug>-t-; and any t-* instance is refused.
    mod = _load()
    slug = "demo"
    reserved = f"{slug}-{mod.RESERVED_TIER3_PREFIX}"  # "demo-t-"
    for branch in ("tango", "test-branch", "t", "feature/foo", "wt-blue", "main"):
        assert not mod.build_stack_instance(slug, branch).startswith(reserved)
    for banned in ("t-1234", "t/abc", "t--x"):
        with pytest.raises(mod.Tier3NamespaceError):
            mod.build_stack_instance(slug, banned)


# --- read_slug -----------------------------------------------------------


def test_read_slug_parses_compose_name(tmp_path):
    mod = _load()
    base = tmp_path / "base.yml"
    base.write_text("# header\nname: acme-store\nservices:\n  app: {}\n")
    assert mod.read_slug(base) == "acme-store"


def test_read_slug_missing_name_raises(tmp_path):
    mod = _load()
    base = tmp_path / "base.yml"
    base.write_text("services:\n  app: {}\n")
    with pytest.raises(ValueError):
        mod.read_slug(base)


# --- current_branch ------------------------------------------------------


def test_current_branch_reads_git(tmp_path):
    mod = _load()
    subprocess.run(["git", "init", "-q", "-b", "feature/foo"], cwd=tmp_path, check=True)
    assert mod.current_branch(tmp_path) == "feature/foo"


# --- resolve_stack_instance ----------------------------------------------


def test_resolve_stack_instance_end_to_end(tmp_path):
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(
        ["git", "init", "-q", "-b", "wt/blue", "."], cwd=tmp_path, check=True
    )
    assert mod.resolve_stack_instance(base, tmp_path) == "acme-store-wt-blue"


def test_full_stack_instance_is_a_single_dns_label():
    # The FROZEN FWK88 seam: the WHOLE STACK_INSTANCE (<slug>-<inst>), not just the
    # sanitized branch, must be a single ^[a-z0-9-]+$ label so the box `*.localhost`
    # cert covers it. Lock the composed output directly, not only transitively.
    import re

    mod = _load()
    for slug, branch in [
        ("acme-store", "feature/Foo"),
        ("x", "a__b//c"),
        ("p9", "RELEASE-1.2"),
    ]:
        out = mod.build_stack_instance(slug, branch)
        assert re.fullmatch(r"[a-z0-9-]+", out), out
        assert not out.startswith("-") and not out.endswith("-")


# --- .env merge (FWK93) --------------------------------------------------

# A realistic durable .env: the managed FRAMEWORK block carries PORT_OFFSET=0 and the
# host-port set, plus a commented decoy and user content below the closing marker.
_REALISTIC_ENV = """\
# FRAMEWORK:BEGIN
APP_ENVIRONMENT=dev
# PORT_OFFSET is shifted to run a second stack alongside this one.
PORT_OFFSET=0
HTTP_HOST_PORT=8000
# APP_LOG_LEVEL=
# FRAMEWORK:END

# Your app's config below.
MY_OWN_VAR=keepme
"""


def test_parse_env_skips_comments_and_blanks():
    mod = _load()
    parsed = mod.parse_env(_REALISTIC_ENV)
    assert parsed["PORT_OFFSET"] == "0"
    assert parsed["APP_ENVIRONMENT"] == "dev"
    assert parsed["MY_OWN_VAR"] == "keepme"
    assert "APP_LOG_LEVEL" not in parsed  # commented-out line is not a value


def test_merge_updates_existing_port_offset_in_place_exactly_once():
    mod = _load()
    out = mod.merge_env_vars(_REALISTIC_ENV, {"PORT_OFFSET": "3000"})
    # Updated in place — exactly one real PORT_OFFSET assignment, value changed.
    assert "\nPORT_OFFSET=3000\n" in out
    assert [ln for ln in out.splitlines() if ln == "PORT_OFFSET=3000"] == [
        "PORT_OFFSET=3000"
    ]
    assert "PORT_OFFSET=0" not in out
    # The commented decoy is untouched; user content survives.
    assert "# PORT_OFFSET is shifted" in out
    assert "MY_OWN_VAR=keepme" in out


def test_merge_appends_absent_keys():
    mod = _load()
    out = mod.merge_env_vars(_REALISTIC_ENV, {"STACK_INSTANCE": "acme-store-wt-blue"})
    assert "STACK_INSTANCE=acme-store-wt-blue" in out
    # Appended (absent before) — original PORT_OFFSET line is untouched.
    assert "PORT_OFFSET=0" in out


def test_merge_resolved_literal_round_trips_through_a_plain_parser():
    # advisor #2: COMPOSE_PROJECT_NAME must be the RESOLVED literal, so a plain
    # KEY=VAL reader sees the instance, never the unexpanded string "$STACK_INSTANCE".
    mod = _load()
    out = mod.merge_env_vars(
        _REALISTIC_ENV,
        {
            "STACK_INSTANCE": "acme-store-wt-blue",
            "COMPOSE_PROJECT_NAME": "acme-store-wt-blue",
        },
    )
    reparsed = mod.parse_env(out)
    assert reparsed["COMPOSE_PROJECT_NAME"] == "acme-store-wt-blue"
    assert "$" not in reparsed["COMPOSE_PROJECT_NAME"]


def test_merge_empty_file_just_appends():
    mod = _load()
    out = mod.merge_env_vars("", {"STACK_INSTANCE": "x-y"})
    assert out == "STACK_INSTANCE=x-y\n"


def test_write_env_creates_then_reconciles(tmp_path):
    mod = _load()
    env = tmp_path / ".env"
    mod.write_env({"STACK_INSTANCE": "x-y"}, path=env)
    assert "STACK_INSTANCE=x-y" in env.read_text()
    # Re-write updates in place — no duplicate line.
    mod.write_env({"STACK_INSTANCE": "x-z"}, path=env)
    lines = [
        ln for ln in env.read_text().splitlines() if ln.startswith("STACK_INSTANCE=")
    ]
    assert lines == ["STACK_INSTANCE=x-z"]


# --- offset selection (FWK93) --------------------------------------------


def test_select_offset_zero_when_nothing_occupied():
    mod = _load()
    assert mod.select_port_offset(set()) == 0


def test_select_offset_skips_window_with_any_collision():
    mod = _load()
    # The main stack is up on offset 0 (its app port 8000 is bound) → 0 is rejected,
    # next free window is offset 1000.
    assert mod.select_port_offset({8000}) == 1000


def test_select_offset_handles_cross_window_self_collision():
    # advisor #4 / FWK88 note: grafana base 3000 shifted by 5000 == app base 8000.
    # If a stack at offset 0 binds app:8000, an offset-5000 window's grafana would
    # collide — the port-set disjointness check rejects it with no special-casing.
    mod = _load()
    chosen = mod.select_port_offset({8000})
    shifted = {p + chosen for p in mod.BASE_HOST_PORTS}
    assert 8000 not in shifted


def test_select_offset_raises_when_pool_exhausted():
    mod = _load()
    # Occupy every candidate window's app port so no offset is free.
    occupied = {8000 + off for off in range(0, 60000, mod.OFFSET_STEP)}
    with pytest.raises(RuntimeError):
        mod.select_port_offset(occupied)


def test_running_host_ports_parses_docker_ps():
    import subprocess as _sp

    mod = _load()

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["docker", "ps"]
        out = (
            "0.0.0.0:8000->8000/tcp, :::8000->8000/tcp\n"
            "0.0.0.0:5432->5432/tcp\n"
            "\n"  # a container with no published ports
        )
        return _sp.CompletedProcess(cmd, 0, stdout=out, stderr="")

    assert mod.running_host_ports(run=fake_run) == {8000, 5432}


# --- provision planner / reconcile (FWK93) -------------------------------


def test_plan_provision_sets_resolved_literals_no_ports():
    mod = _load()
    updates = mod.plan_provision("", "acme-store-wt-blue", with_ports=False)
    assert updates == {
        "STACK_INSTANCE": "acme-store-wt-blue",
        "COMPOSE_PROJECT_NAME": "acme-store-wt-blue",
    }
    # No --ports → PORT_OFFSET is left to the .env default, not written.
    assert "PORT_OFFSET" not in updates


def test_plan_provision_fresh_selects_offset():
    mod = _load()
    # Fresh .env (no STACK_INSTANCE recorded) with the main stack up on offset 0.
    updates = mod.plan_provision(
        "PORT_OFFSET=0\n", "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert updates["PORT_OFFSET"] == "1000"


def test_plan_provision_reconciles_recorded_offset_verbatim():
    # advisor #1 / FWK94 F2: the .env records THIS instance's SELECTED offset via the
    # PORT_OFFSET_FOR marker. A re-run (e.g. after /clear, stack still up) must reuse 3000
    # verbatim — NOT re-introspect — even though `occupied` would otherwise select 1000.
    mod = _load()
    env_text = (
        "STACK_INSTANCE=acme-store-wt-blue\n"
        "PORT_OFFSET_FOR=acme-store-wt-blue\n"
        "PORT_OFFSET=3000\n"
    )
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["PORT_OFFSET"] == "3000"
    # The marker is (idempotently) re-asserted on the reconcile path too.
    assert updates["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


def test_plan_provision_recorded_other_instance_is_not_reconciled():
    # A DIFFERENT instance's selection is recorded (marker + offset) → for THIS instance
    # the marker mismatches, so the recorded offset is NOT reused; a free offset is
    # selected. Exercises the marker-mismatch branch (distinct from the no-marker branch).
    mod = _load()
    env_text = (
        "STACK_INSTANCE=other-stack\nPORT_OFFSET_FOR=other-stack\nPORT_OFFSET=3000\n"
    )
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied=set()
    )
    assert updates["PORT_OFFSET"] == "0"


def test_plan_provision_portless_then_ports_selects_fresh():
    # carry-forward #1: a prior ports-less up left STACK_INSTANCE=<inst> + the template
    # default PORT_OFFSET=0 but NO PORT_OFFSET_FOR marker. A later --ports up must select
    # fresh (1000 here), NOT silently reconcile to the defaulted 0 → main-stack collision.
    mod = _load()
    env_text = "STACK_INSTANCE=acme-store-wt-blue\nPORT_OFFSET=0\n"
    updates = mod.plan_provision(
        env_text, "acme-store-wt-blue", with_ports=True, occupied={8000}
    )
    assert updates["PORT_OFFSET"] == "1000"
    assert updates["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


def test_plan_provision_writes_marker_on_fresh_select():
    # A fresh --ports provision records the selection marker so the NEXT run reconciles.
    mod = _load()
    updates = mod.plan_provision(
        "", "acme-store-wt-blue", with_ports=True, occupied=set()
    )
    assert (
        updates["PORT_OFFSET"] == "0"
    )  # nothing occupied → offset 0 is a real selection
    assert updates["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


# --- BASE_HOST_PORTS ↔ compose.sh sync-guard (FWK94, carry-forward #2) ----


def test_base_host_ports_mirror_compose_sh():
    # BASE_HOST_PORTS is a hand-copied mirror of compose.sh's `_p VAR DEFAULT` host-port
    # defaults. Parse the template compose.sh and assert the DEFAULT set matches exactly,
    # so a future port added to compose.sh can't silently drift the offset window.
    import re as _re

    mod = _load()
    compose_sh = (
        Path(__file__).resolve().parents[1]
        / "src/framework_cli/template/scripts/compose.sh"
    )
    defaults = {
        int(m.group(1))
        for m in _re.finditer(
            r"^\s*_p\s+\w+\s+(\d+)\s*$", compose_sh.read_text(), _re.MULTILINE
        )
    }
    assert defaults == set(mod.BASE_HOST_PORTS), (
        f"compose.sh defaults {sorted(defaults)} != "
        f"BASE_HOST_PORTS {sorted(mod.BASE_HOST_PORTS)}"
    )


# --- provision orchestration (FWK94) -------------------------------------


def test_parse_obs_selection_accepts_frozen_set():
    mod = _load()
    assert mod.parse_obs_selection("grafana,prometheus") == ("grafana", "prometheus")
    assert mod.parse_obs_selection("") == ()
    assert mod.parse_obs_selection(" alertmanager ") == ("alertmanager",)


def test_parse_obs_selection_rejects_non_routable():
    mod = _load()
    # loki/tempo/exporters have no UI → not edge-routable (FWK88 frozen set).
    with pytest.raises(ValueError):
        mod.parse_obs_selection("grafana,loki")


def test_provision_exports_instance_and_offset_to_dev_edge(tmp_path):
    # The deliverable: worktree.py exports the vars itself so `task dev:edge` (and the
    # compose.sh under it) sees an EXPORTED PORT_OFFSET — never a bare .env value.
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("PORT_OFFSET=0\n")
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["task", "dev:edge"]:
            seen["cmd"] = cmd
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.provision(
        "acme-store-wt-blue", with_ports=True, run=fake_run, env_path=env
    )
    assert rc == 0
    assert seen["cmd"] == ["task", "dev:edge"]
    # Exported into the child env (nothing occupied → offset 0).
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert seen["env"]["COMPOSE_PROJECT_NAME"] == "acme-store-wt-blue"
    assert seen["env"]["PORT_OFFSET"] == "0"
    # And persisted to the durable .env (idempotent merge), with the selection marker.
    written = mod.parse_env(env.read_text())
    assert written["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert written["PORT_OFFSET_FOR"] == "acme-store-wt-blue"


def test_provision_no_ports_skips_docker_and_offset(tmp_path):
    # Without --ports: no docker ps introspection, no PORT_OFFSET written; dev:edge still runs.
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("")
    seen = {}

    def fake_run(cmd, **kwargs):
        assert cmd[:2] != ["docker", "ps"], "must not introspect without --ports"
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    mod.provision("acme-store-wt-blue", with_ports=False, run=fake_run, env_path=env)
    # No --ports → no offset planned: the durable .env carries STACK_INSTANCE but no
    # PORT_OFFSET (the non-vacuous guarantee; the os.environ-merged child env can't be
    # asserted negatively since the test host may already export PORT_OFFSET).
    written = mod.parse_env(env.read_text())
    assert written["STACK_INSTANCE"] == "acme-store-wt-blue"
    assert "PORT_OFFSET" not in written
    assert "PORT_OFFSET_FOR" not in written
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_main_up_resolves_branch_and_provisions(tmp_path, monkeypatch):
    # End-to-end glue: main('up') reads slug from infra/compose/base.yml + branch from git,
    # then provisions. Mirrors test_resolve_stack_instance_end_to_end's project setup.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(
        ["git", "init", "-q", "-b", "wt/blue", "."], cwd=tmp_path, check=True
    )
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.main(["up"], run=fake_run)
    assert rc == 0
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_main_up_instance_override(tmp_path, monkeypatch):
    # --instance overrides the branch (the escape hatch for a branch that sanitizes into t-*).
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["task", "dev:edge"]:
            seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    mod.main(["up", "--instance", "green"], run=fake_run)
    assert seen["env"]["STACK_INSTANCE"] == "acme-store-green"


def test_main_up_tier3_branch_errors_with_instance_hint(tmp_path, monkeypatch, capsys):
    # A branch sanitizing into B's reserved t-* namespace fails loud with a --instance hint.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "t/1234", "."], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["up"], run=lambda *a, **k: None)
    assert "--instance" in capsys.readouterr().err


def test_main_up_detached_head_errors_with_instance_hint(tmp_path, monkeypatch, capsys):
    # Detached HEAD: `git symbolic-ref` fails → friendly --instance hint, no raw traceback
    # (carried-forward FWK92 Minor). Set up a repo with a commit, then detach.
    mod = _load()
    base = tmp_path / "infra" / "compose" / "base.yml"
    base.parent.mkdir(parents=True)
    base.write_text("name: acme-store\n")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", sha], cwd=tmp_path, check=True)  # detach
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["up"], run=lambda *a, **k: None)
    assert "--instance" in capsys.readouterr().err


# --- .env removal (FWK95) ------------------------------------------------


def test_remove_env_vars_drops_keys_keeps_comments_and_others():
    mod = _load()
    out = mod.remove_env_vars(_REALISTIC_ENV, {"PORT_OFFSET"})
    parsed = mod.parse_env(out)
    assert "PORT_OFFSET" not in parsed
    # The commented decoy + unrelated user content survive.
    assert "# PORT_OFFSET is shifted" in out
    assert "MY_OWN_VAR=keepme" in out
    assert parsed["APP_ENVIRONMENT"] == "dev"


def test_remove_env_vars_absent_key_is_noop():
    mod = _load()
    out = mod.remove_env_vars("STACK_INSTANCE=x-y\n", {"PORT_OFFSET"})
    assert out == "STACK_INSTANCE=x-y\n"


# --- resolve_provisioned_instance (FWK95) --------------------------------


def test_resolve_provisioned_instance_reads_env():
    mod = _load()
    assert (
        mod.resolve_provisioned_instance("STACK_INSTANCE=acme-store-wt-blue\n")
        == "acme-store-wt-blue"
    )


def test_resolve_provisioned_instance_absent_raises():
    mod = _load()
    with pytest.raises(ValueError):
        mod.resolve_provisioned_instance("PORT_OFFSET=0\n")


# --- deprovision orchestration (FWK95) -----------------------------------


def test_deprovision_tears_down_with_volume_reclaim_and_releases_offset(tmp_path):
    # The deliverable: `down -v` reclaims volumes (dev:down keeps them) + the offset
    # markers are cleared so a later `up --ports` re-introspects (F2 release).
    mod = _load()
    env = tmp_path / ".env"
    env.write_text(
        "STACK_INSTANCE=acme-store-wt-blue\n"
        "COMPOSE_PROJECT_NAME=acme-store-wt-blue\n"
        "PORT_OFFSET_FOR=acme-store-wt-blue\n"
        "PORT_OFFSET=1000\n"
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.deprovision(run=fake_run, env_path=env)
    assert rc == 0
    # The real teardown — project-scoped down WITH -v (volume reclaim).
    assert calls == [["docker", "compose", "-p", "acme-store-wt-blue", "down", "-v"]]
    # Offset released; STACK_INSTANCE kept (identifies the worktree; re-up reconciles).
    written = mod.parse_env(env.read_text())
    assert "PORT_OFFSET" not in written
    assert "PORT_OFFSET_FOR" not in written
    assert written["STACK_INSTANCE"] == "acme-store-wt-blue"


def test_deprovision_no_instance_raises(tmp_path):
    mod = _load()
    env = tmp_path / ".env"
    env.write_text("PORT_OFFSET=0\n")
    with pytest.raises(ValueError):
        mod.deprovision(run=lambda *a, **k: None, env_path=env)


def test_deprovision_missing_env_raises(tmp_path):
    # No .env at all → nothing provisioned → friendly error, no docker touched.
    mod = _load()
    env = tmp_path / ".env"  # not created
    with pytest.raises(ValueError):
        mod.deprovision(run=lambda *a, **k: None, env_path=env)


def test_main_down_resolves_from_env_and_tears_down(tmp_path, monkeypatch):
    mod = _load()
    env = tmp_path / ".env"
    env.write_text(
        "STACK_INSTANCE=acme-store-wt-blue\nPORT_OFFSET_FOR=acme-store-wt-blue\nPORT_OFFSET=1000\n"
    )
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    rc = mod.main(["down"], run=fake_run)
    assert rc == 0
    assert ["docker", "compose", "-p", "acme-store-wt-blue", "down", "-v"] in calls


def test_main_down_no_instance_errors_friendly(tmp_path, monkeypatch, capsys):
    mod = _load()
    (tmp_path / ".env").write_text("PORT_OFFSET=0\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        mod.main(["down"], run=lambda *a, **k: None)
    assert "provisioned" in capsys.readouterr().err

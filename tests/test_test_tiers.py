"""Guard: the fast/full test-tier partition has no SILENT coverage gap (FWK96 / FWK77).

The framework runs two named tiers:

  * **fast** (per-commit / local / the CI `gate` job): the non-docker suite under
    `pytest -n auto`. The CI form is `ci.yml`'s `gate` step; the local form is
    `task test:fast` — and this guard pins the two to the *same* ignore set so they
    can't drift.
  * **full** (per-merge / branch-end): the fast tier **plus** the docker acceptance
    suite, run with a *bounded* `-n` (not `auto`) to cap docker contention —
    `task test:full`.

FWK77's load-bearing requirement is that no test the fast tier skips is dropped
*silently*: every skipped test must either run in a required PR check, or be a
**documented** exception recorded here.

CI topology (pinned to branch-protection ruleset 17579429, verified 2026-06-28):

    REQUIRED_CHECKS = {gate, build, render-complete}
      - gate            (ci.yml)            -> the ONLY job that runs the framework pytest suite
      - build           (docs.yml)          -> `mkdocs build --strict`; runs NO pytest
      - render-complete (render-matrix.yml) -> renders projects + runs the *rendered*
                                               project's `task ci`; runs NO framework pytest

So `gate` is the sole pytest-claiming required check; anything `gate` `--ignore`s
runs in **no** required check. Therefore each ignored path MUST be a documented
exception below — a `--ignore` that isn't listed fails this guard.

`render-complete` / render-matrix is **not** the framework pytest suite (it is the
generated project's own `task ci`); "the whole suite" in this guard means the pytest
tests under `tests/` — stated explicitly so the partition isn't comparing unlike sets.
"""

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
_TASKFILE = Path(__file__).parent.parent / "Taskfile.yml"
_TESTS = Path(__file__).parent

# Branch-protection ruleset 17579429 ("main protection"), verified live 2026-06-28.
# A CI unit test cannot read the live ruleset (no network/auth), so this is pinned
# here; if the required checks change, change this set (and re-derive the guard).
REQUIRED_CHECKS = frozenset({"gate", "build", "render-complete"})

# Of the required checks, only `gate` runs the framework's own pytest suite.
PYTEST_REQUIRED_CHECKS = frozenset({"gate"})

# The ONLY tests the fast tier (gate) may skip without running them in a required
# check. Each entry: path -> why it's exempt + where it DOES run. A new `--ignore`
# that is not listed here fails `test_fast_tier_ignores_only_documented_exceptions`
# (FWK77: a coverage skip must be logged, not silent).
#
# Operator decision (FWK96, 2026-06-28): the docker acceptance tests stay NON-required
# in CI — heavy + dind-flaky on GitHub runners; they run at branch-end via the full
# tier (`task test:full`). This is a *documented exception* to the stricter "every
# skipped test runs in some required check"; the exception is recorded loudly here so
# it can never become a silent gap.
ACCEPTANCE_DOCKER_EXCEPTIONS = {
    "tests/acceptance/test_rendered_project.py": (
        "docker/dind acceptance: renders a project and exercises `docker compose` "
        "(dev/CI overlays, TLS routing, integrity tamper/restore). Runs in the full "
        "tier (`task test:full`, branch-end/local). NOT a required CI check by operator "
        "decision (FWK96, 2026-06-28): heavy + dind-flaky on GHA."
    ),
    "tests/acceptance/test_deploy_e2e.py": (
        "docker/dind compose-over-SSH deploy e2e (multi-container harness). Full tier "
        "only — same rationale as test_rendered_project.py."
    ),
}


def _gate_pytest_cmd() -> str:
    wf = yaml.safe_load((_WORKFLOWS / "ci.yml").read_text())
    steps = wf["jobs"]["gate"]["steps"]
    runs = [str(s.get("run", "")) for s in steps]
    pytest_runs = [r for r in runs if "pytest" in r]
    assert len(pytest_runs) == 1, (
        f"expected exactly one pytest step in gate, got {pytest_runs}"
    )
    return pytest_runs[0]


def _ignore_paths(cmd: str) -> set[str]:
    """Extract the `--ignore=<path>` arguments from a pytest command string."""
    return {tok.split("=", 1)[1] for tok in cmd.split() if tok.startswith("--ignore=")}


def _taskfile_cmd(task: str) -> str:
    tf = yaml.safe_load(_TASKFILE.read_text())
    return " ".join(str(c) for c in tf["tasks"][task]["cmds"])


def test_gate_is_the_sole_pytest_running_required_check():
    """build = mkdocs, render-complete = rendered project's task ci; only gate runs pytest.

    Pins the premise the coverage partition rests on: of the three required checks,
    exactly one (`gate`) runs the framework pytest suite, so what it ignores is
    uncovered by *every* required check.
    """
    assert PYTEST_REQUIRED_CHECKS <= REQUIRED_CHECKS

    # build (docs.yml): mkdocs, no pytest.
    docs = yaml.safe_load((_WORKFLOWS / "docs.yml").read_text())
    build_run = " ".join(str(s.get("run", "")) for s in docs["jobs"]["build"]["steps"])
    assert "mkdocs build" in build_run
    assert "pytest" not in build_run

    # render-complete (render-matrix.yml): the required check is an aggregator job
    # over the `render` matrix; `render` renders projects + runs the *rendered*
    # project's `task ci`. Neither runs the framework's own pytest suite.
    rm = yaml.safe_load((_WORKFLOWS / "render-matrix.yml").read_text())
    assert "render-complete" in rm["jobs"]
    complete_run = " ".join(
        str(s.get("run", "")) for s in rm["jobs"]["render-complete"]["steps"]
    )
    assert "pytest" not in complete_run  # umbrella aggregator — no pytest
    render_run = " ".join(str(s.get("run", "")) for s in rm["jobs"]["render"]["steps"])
    assert "task ci" in render_run
    assert "pytest" not in render_run

    # gate (ci.yml): does run pytest.
    assert "pytest" in _gate_pytest_cmd()


def test_fast_tier_ignores_only_documented_exceptions():
    """Every path the fast tier `--ignore`s is a documented exception — the core guard.

    A new `--ignore=` (e.g. quietly skipping a slow/flaky test) that isn't recorded
    in ACCEPTANCE_DOCKER_EXCEPTIONS reddens this test: that is FWK77's "a skip must be
    logged, not silent" made enforceable.
    """
    ignored = _ignore_paths(_gate_pytest_cmd())
    assert ignored == set(ACCEPTANCE_DOCKER_EXCEPTIONS), (
        "fast-tier (gate) --ignore set drifted from the documented exceptions.\n"
        f"  ignored but undocumented: {sorted(ignored - set(ACCEPTANCE_DOCKER_EXCEPTIONS))}\n"
        f"  documented but not ignored: {sorted(set(ACCEPTANCE_DOCKER_EXCEPTIONS) - ignored)}\n"
        "Add an ACCEPTANCE_DOCKER_EXCEPTIONS entry (path -> reason + where it runs), "
        "or stop ignoring the path."
    )


def test_documented_exceptions_exist_and_disk_tmp_unit_test_is_not_skipped():
    """Exception entries point at real files, and the non-docker acceptance unit test
    is *not* ignored (it must run in the fast tier).

    `tests/acceptance/test_conftest_disk_tmp.py` is a pure unit test of the `disk_tmp`
    fixture — it needs no docker, so it belongs in the fast tier. Ignoring the whole
    `tests/acceptance/` directory used to drop it silently (a second, sneakier gap);
    this asserts it is claimed by the fast tier.
    """
    root = _TESTS.parent
    for path, reason in ACCEPTANCE_DOCKER_EXCEPTIONS.items():
        assert (root / path).is_file(), (
            f"documented exception points at a missing file: {path}"
        )
        assert reason.strip(), f"exception {path} has an empty reason"

    ignored = _ignore_paths(_gate_pytest_cmd())
    disk_tmp = "tests/acceptance/test_conftest_disk_tmp.py"
    assert (root / disk_tmp).is_file()
    assert disk_tmp not in ignored, (
        f"{disk_tmp} is a non-docker unit test and must run in the fast tier, not be ignored"
    )

    # Defence in depth: any acceptance test file that is NOT a documented docker
    # exception must run in the fast tier (i.e. not be ignored). A new docker test
    # added without an exception entry will therefore run in the gate (and fail there
    # for lack of docker / be caught as heavy) rather than silently vanish.
    acc_files = {
        f"tests/acceptance/{p.name}"
        for p in (root / "tests" / "acceptance").glob("test_*.py")
    }
    for f in acc_files - set(ACCEPTANCE_DOCKER_EXCEPTIONS):
        assert f not in ignored, (
            f"{f} is neither a documented exception nor in the fast tier"
        )


def test_local_fast_tier_matches_the_ci_gate():
    """`task test:fast` runs the same ignore set as the CI `gate` — no fast-tier drift."""
    local = _taskfile_cmd("test:fast")
    assert "pytest" in local
    assert "-n auto" in local
    assert _ignore_paths(local) == _ignore_paths(_gate_pytest_cmd()), (
        "task test:fast and the CI gate disagree on which tests the fast tier skips"
    )


def test_full_tier_includes_acceptance_with_bounded_n():
    """`task test:full` is the fast tier + docker acceptance, with a *bounded* `-n`.

    The full tier must NOT ignore the docker exceptions (it is where they run) and
    must cap parallelism (`-n <int>`, not `-n auto`) so concurrent docker stacks don't
    contend (per the decomposition spec).
    """
    full = _taskfile_cmd("test:full")
    assert "pytest" in full
    assert _ignore_paths(full) == set(), (
        "the full tier must run the docker acceptance tests"
    )
    assert "-n auto" not in full, (
        "the full tier must bound -n (not auto) to cap docker contention"
    )
    tokens = full.split()
    n_idx = [i for i, t in enumerate(tokens) if t == "-n"]
    assert n_idx, "the full tier should pass a bounded -n"
    bound = tokens[n_idx[0] + 1]
    assert bound.isdigit() and int(bound) >= 1, (
        f"-n bound must be a positive int, got {bound!r}"
    )

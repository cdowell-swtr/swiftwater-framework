# Test tiers — fast (per-commit) vs full (per-merge)

> Stream-B B4 / `FWK96`. The companion levers are `FWK93` (`pytest-xdist -n auto`) and
> `FWK94` (per-worker render cache). This page is the **coverage contract** for the
> tiering; the machine-checked form is `tests/test_test_tiers.py`.

## The two tiers

| Tier | Invocation | What it runs | When |
|---|---|---|---|
| **fast** | `task test:fast` / CI `gate` | the **non-docker** suite, `pytest -n auto` | every commit / locally / on every PR |
| **full** | `task test:full` | fast tier **+ docker acceptance**, `pytest -n 4` (bounded) | branch-end / before merge |

The fast tier's pytest invocation is **byte-identical** between `task test:fast` and the
CI `gate` step (`.github/workflows/ci.yml`) — `tests/test_test_tiers.py` pins them together
so they cannot drift. The full tier uses a *bounded* `-n` (not `auto`) so concurrent docker
stacks don't contend on the daemon.

`task test` / `uv run pytest -q` still runs **everything, serially** — kept as a simple
escape hatch; it is not a tier.

> **Tier-3 namespace migration (`FWK116`, post-v0.4.4).** The full tier's transient acceptance
> stacks were renamed `<slug>-t-<uuid>` → `<slug>-<inst>-t-<uuid>` (a per-worktree namespace, so
> concurrent runs across worktrees no longer reap each other's stacks). The start-sweep recognizes
> only the **new** form, so if you ran `task test:full` on a **≤ v0.4.4** checkout and then switch to
> a newer one, any leftover old-format `<slug>-t-<uuid>` stacks are **not** auto-reaped — clear them
> once by hand (e.g. `docker ps -aq --filter name=<slug>-t- | xargs -r docker rm -f`). One-time only;
> new-format stacks self-clean.

## The coverage contract (why there is no silent gap)

FWK77's load-bearing requirement: **a test the fast tier skips must not be dropped
silently** — it must run in a required PR check, or be a *documented* exception.

The live branch-protection ruleset (`17579429`, "main protection") requires three checks:

| Required check | Workflow | Runs framework pytest? |
|---|---|---|
| `gate` | `ci.yml` | **yes** — the fast tier |
| `build` | `docs.yml` | no — `mkdocs build --strict` |
| `render-complete` | `render-matrix.yml` | no — renders projects and runs the *rendered* project's `task ci`, not the framework's `tests/` |

So **`gate` is the only required check that runs the framework pytest suite.** Whatever
`gate` `--ignore`s therefore runs in *no* required check. The fast tier ignores exactly the
two docker/dind acceptance files:

- `tests/acceptance/test_rendered_project.py`
- `tests/acceptance/test_deploy_e2e.py`

These run only in the full tier (`task test:full`), at branch-end, locally.

> Note: "the whole suite" here means the pytest tests under `tests/`. `render-complete` /
> render-matrix is a different artifact (the generated project's own `task ci`), not the
> framework pytest suite — the partition is not comparing unlike sets.

## The acceptance-as-required decision (operator, 2026-06-28)

B4 had to decide explicitly: do the docker acceptance tests become a *required* PR check?

**Decision: no — keep them non-required; record this as a loud, documented exception.**

Rationale: the docker/dind acceptance suite is heavy and dind-flaky on GitHub runners;
making it required would add that cost + flakiness to every PR, against the inner-loop-speed
goal of the whole stream. It is continuity with the repo's existing posture — `FWK70`
already judged acceptance "not merge-blocking", and `gate-cadence-for-framework-slices`
already defers heavy gates to branch-end. This is an explicit, recorded exception to the
decomposition spec's stricter "every skipped test runs in some *required* check"; the
exception is enforced loudly so it can never silently widen.

Because acceptance stays non-required, **`FWK70`** (the known-failing acceptance
fixture-bug, which would have had to be fixed first had acceptance become a required check)
is *not* a prerequisite of this change. It remains its own open `PLAN.md` item.

## What the guard enforces (`tests/test_test_tiers.py`)

- Every `--ignore=` in the fast tier (CI `gate`) is a documented entry in
  `ACCEPTANCE_DOCKER_EXCEPTIONS` (path → reason → where it runs). A new, undocumented
  `--ignore` (e.g. quietly skipping a slow test) **fails the build**.
- `gate` is the sole pytest-running required check (`build` = mkdocs, `render-complete` =
  rendered project's `task ci`).
- The non-docker `tests/acceptance/test_conftest_disk_tmp.py` unit test is **not** ignored
  — it runs in the fast tier. (Ignoring the whole `tests/acceptance/` directory used to drop
  it silently; the per-file ignore closes that second gap.)
- `task test:fast` and the CI `gate` share one ignore set (no drift).
- `task test:full` runs the acceptance tests (no `--ignore`) with a bounded `-n`.

When the required checks change, update `REQUIRED_CHECKS` in `tests/test_test_tiers.py`
(it is pinned there because a CI unit test cannot read the live ruleset).

## The generated project's suite stays serial (`FWK97`, measured 2026-06-28)

Stream-B B5 / `FWK97` set out to mirror these levers — `pytest-xdist -n auto` + the
fast/full split — into the **generated** project's shipped suite. The tiering already
existed (pre-commit `coverage.sh 70 unit functional` = fast; CI `coverage.sh 85 unit
functional e2e` = full), so the only new lever was xdist. **We measured it and it does not
transfer — the generated suite stays serial.**

The cost structures are *opposite*. The framework's own fast tier is render-bound,
container-free, and embarrassingly parallel (283 renders → `-n auto` is a 6.4× win). The
generated project's suite is the reverse: small, and **Postgres-container-bound**. Its DB
container fixture (`tests/conftest.py` `pg_url`) is `scope="session"`, and an xdist worker
is a separate process with its own session — so `-n auto` starts **one Postgres container +
one `alembic upgrade head` per worker**, not one for the run.

Measured on a fresh scaffold (12-core box):

| Run | unit + functional | Postgres containers |
|---|---|---|
| serial | **6.97 s** | 1 |
| `-n auto` | **12.81 s** (2× slower) | **6 concurrent** |

So shipping `-n auto` would push a *measured regression* — slower wall-clock plus N
containers' memory/flakiness pressure (worse on a 2-core CI runner) — to every generated
project. That defeats the very wall-clock goal the lever exists to serve. This applies the
same measurement-gated discipline the decomposition spec already mandates for B2 (`FWK94`):
re-evaluate a lever against its measured number rather than treating it as a given.

A genuine xdist win for the generated suite is possible but out of B5's tail scope: share
**one** container across workers (the xdist file-lock pattern) with **per-worker DB
isolation** — needed because `api_client` does a global `TRUNCATE TABLE items` at teardown,
so parallel workers on one shared database would clobber each other. That correctness work
is carved as its own follow-up (`FWK98`), to be done only if a real generated project's
suite grows large enough to need it. `pytest-xdist` is intentionally **not** added to the
template's dev deps until then (no unused dependency in the scaffold).

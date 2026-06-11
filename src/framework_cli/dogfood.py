"""Pure logic for the generated-project end-to-end CI dogfood harness (Plan 13).

Framework-internal (like devmatrix.py): renders + assertion logic for proving the
generated ci.yml runs green on real GitHub Actions. The imperative gh/git shell
lives in scripts/dogfood_e2e.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from framework_cli.batteries import battery_names, resolve

#: The framework tag this dogfood run pins (installed by the generated integrity step-0).
DOGFOOD_COMMIT = "v0.2.1"

#: Workflow jobs present in every generated ci.yml regardless of batteries.
ALWAYS_ON_JOBS: frozenset[str] = frozenset(
    {
        "integrity",
        "lint",
        "security",
        "test",
        "build",
        "contract",
        "review-plan",
        "review-aggregate",
    }
)

#: Battery -> the conditional ci.yml job it adds.
BATTERY_JOBS: dict[str, str] = {
    "react": "frontend",
    "consumers": "contracts",
    "docs": "docs",
}


@dataclass(frozen=True)
class DogfoodConfig:
    name: str
    batteries: tuple[str, ...]

    def expected_jobs(self) -> set[str]:
        """Workflow jobs that must be present and `success`. Excludes the dynamic
        `review (<agent>)` matrix jobs (matched by prefix at classify time)."""
        jobs = set(ALWAYS_ON_JOBS)
        jobs.update(job for b, job in BATTERY_JOBS.items() if b in self.batteries)
        return jobs


BASELINE = DogfoodConfig(name="baseline", batteries=())
ALL_BATTERIES = DogfoodConfig(
    name="all-batteries",
    batteries=tuple(resolve(list(battery_names()))),
)


@dataclass(frozen=True)
class Job:
    name: str
    conclusion: str  # success | failure | neutral | skipped | cancelled | "" (pending)
    url: str = ""


@dataclass
class Verdict:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_jobs(payload: dict) -> list[Job]:
    return [
        Job(j["name"], j.get("conclusion") or "", j.get("url", ""))
        for j in payload.get("jobs", [])
    ]


def _is_review_matrix_job(name: str) -> bool:
    return name.startswith("review (") and name.endswith(")")


def classify_jobs(jobs: list[Job], config: DogfoodConfig) -> Verdict:
    """Surface 1: every expected job present + `success`, and a non-empty review matrix
    where every matrix job is `success`."""
    by_name = {j.name: j for j in jobs}
    failures: list[str] = []
    for name in sorted(config.expected_jobs()):
        job = by_name.get(name)
        if job is None:
            failures.append(f"expected job '{name}' missing from the run")
        elif job.conclusion != "success":
            failures.append(
                f"job '{name}' concluded '{job.conclusion or 'pending'}' "
                f"(expected success) — {job.url}"
            )
    matrix = [j for j in jobs if _is_review_matrix_job(j.name)]
    if not matrix:
        failures.append(
            "no 'review (<agent>)' matrix jobs ran — the review matrix did not expand"
        )
    for j in matrix:
        if j.conclusion != "success":
            failures.append(
                f"review matrix job '{j.name}' concluded '{j.conclusion or 'pending'}' "
                f"(expected success) — {j.url}"
            )
    return Verdict(ok=not failures, failures=failures)


@dataclass(frozen=True)
class CheckRun:
    name: str
    conclusion: str
    url: str = ""


def parse_checks(payload: dict) -> list[CheckRun]:
    return [
        CheckRun(c["name"], c.get("conclusion") or "", c.get("html_url", ""))
        for c in payload.get("check_runs", [])
    ]


def classify_review_checks(
    checks: list[CheckRun], *, expected_agents: list[str], with_key: bool
) -> Verdict:
    """Surface 2: the review-agent Check Runs prove the secret-gated behavior.

    No key  -> every expected agent posted a `neutral` check (the graceful no-key path).
    With key -> `success`/`neutral` pass; a `failure` is a warning (an agent flagged the
                benign change as blocking) for the operator to inspect, not a hard fail.
    """
    by_name = {c.name: c for c in checks}
    failures: list[str] = []
    warnings: list[str] = []
    for agent in sorted(expected_agents):
        check = by_name.get(agent)
        if check is None:
            failures.append(f"expected review check for agent '{agent}' missing")
            continue
        if with_key:
            if check.conclusion == "failure":
                warnings.append(
                    f"review check '{agent}' concluded 'failure' (blocking finding on "
                    f"the benign diff — inspect) — {check.url}"
                )
            elif check.conclusion not in {"success", "neutral"}:
                failures.append(
                    f"review check '{agent}' concluded '{check.conclusion or 'pending'}' "
                    f"(expected success/neutral) — {check.url}"
                )
        elif check.conclusion != "neutral":
            failures.append(
                f"review check '{agent}' concluded '{check.conclusion or 'pending'}' "
                f"(expected neutral with no key — the no-key safety path regressed) — {check.url}"
            )
    return Verdict(ok=not failures, failures=failures, warnings=warnings)


@dataclass
class RunResult:
    config: str
    with_key: bool
    push_run_url: str
    pr_run_url: str
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def render_scorecard(results: list[RunResult], *, commit: str) -> str:
    overall = "GREEN" if all(r.ok for r in results) else "RED"
    lines = [
        "# Dogfood E2E scorecard",
        "",
        f"- **Framework tag dogfooded:** `{commit}`",
        f"- **Overall:** {overall}",
        "",
        "| Config | review key | push run | PR run | result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        status = "✅ green" if r.ok else "❌ red"
        key = "yes" if r.with_key else "no (review→neutral)"
        lines.append(
            f"| {r.config} | {key} | {r.push_run_url} | {r.pr_run_url} | {status} |"
        )
    for r in results:
        if r.failures or r.warnings:
            lines += ["", f"## {r.config}"]
            lines += [f"- ❌ {f}" for f in r.failures]
            lines += [f"- ⚠️ {w}" for w in r.warnings]
    return "\n".join(lines) + "\n"

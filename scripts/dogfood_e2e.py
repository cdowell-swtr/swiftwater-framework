#!/usr/bin/env python3
"""Operator-run dogfood e2e harness (Plan 13).

Renders the baseline + all-batteries projects pinned to _commit: DOGFOOD_COMMIT, pushes each to
the dedicated public repo cdowell-swtr/swiftwater-dogfood (reset between configs), seeds
main (-> on:push run) and opens a benign-no-op PR (-> on:pull_request run), watches both
runs, and asserts: (surface 1) every workflow job succeeded; (surface 2) the review-*
Check Runs are neutral by default. --with-review-key sets the repo secret for the paid
full review path. Writes a dated scorecard.

Prerequisites: gh authed (scopes repo+workflow); the DOGFOOD_COMMIT tag pushed; run from the repo root.
NOT a hermetic test — talks to real GitHub Actions. See docs/dogfood-e2e.md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

# Make the in-repo framework_cli importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from framework_cli.copier_runner import render_project  # noqa: E402
from framework_cli.integrity.generate import write_manifest  # noqa: E402
from framework_cli.naming import derive_names  # noqa: E402
from framework_cli.dogfood import (  # noqa: E402
    ALL_BATTERIES,
    BASELINE,
    DOGFOOD_COMMIT,
    DogfoodConfig,
    RunResult,
    Verdict,
    classify_jobs,
    classify_review_checks,
    parse_checks,
    parse_jobs,
    render_scorecard,
)
from framework_cli.review.registry import active_agents  # noqa: E402
from framework_cli.source import record_portable_source  # noqa: E402

REPO = "cdowell-swtr/swiftwater-dogfood"
SECRET_NAME = "ANTHROPIC_SWIFTWATER_DOGFOOD_CI_RUNTIME"
BENIGN_MARKER = "<!-- dogfood-e2e: benign no-op change to trigger the PR pipeline -->"


def sh(args: Sequence[str], *, cwd: str | None = None, check: bool = True) -> str:
    """Run a command, returning stdout. Raises on non-zero unless check=False."""
    result = subprocess.run(
        list(args), cwd=cwd, text=True, capture_output=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}"
        )
    return result.stdout


def assert_run(
    jobs_payload: dict,
    checks_payload: dict,
    config: DogfoodConfig,
    *,
    expected_agents: list[str],
    with_key: bool,
) -> Verdict:
    """Combine surface 1 (jobs) + surface 2 (review checks) into one verdict."""
    jv = classify_jobs(parse_jobs(jobs_payload), config)
    cv = classify_review_checks(
        parse_checks(checks_payload), expected_agents=expected_agents, with_key=with_key
    )
    return Verdict(
        ok=jv.ok and cv.ok,
        failures=jv.failures + cv.failures,
        warnings=jv.warnings + cv.warnings,
    )


def render(config: DogfoodConfig, dest: Path) -> None:
    """Render exactly like `framework new`: render_project -> write_manifest (the
    .framework/integrity.lock the integrity step-0 verifies) -> record_portable_source.
    Omitting write_manifest makes the generated integrity job fail on GHA."""
    names = derive_names("Swiftwater Dogfood")
    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "out": str(dest),
            "package_name": names.package_name,
            "batteries": list(config.batteries),
            "alert_channels": ["webhook"],
        },
    )
    version = DOGFOOD_COMMIT.lstrip("v")
    write_manifest(dest, version)  # generates .framework/integrity.lock
    record_portable_source(dest, version)  # pins _commit to the published tag


def prepare_project(config: DogfoodConfig, project: Path) -> None:
    """Replicate the builder's documented pre-push setup so the committed tree matches what
    the generated ci.yml's `uv sync --frozen` / openapi-staleness / graphql-staleness checks
    require: `uv sync` (-> uv.lock) + export openapi.json (+ schema.graphql for graphql).
    `framework new` does not (yet) generate these — that push-readiness gap is a tracked
    follow-up; the dogfood proves the pipeline green for a correctly-set-up project."""
    log("preparing project: uv sync + export openapi (+ graphql) schema")
    sh(["uv", "sync"], cwd=str(project))
    sh(["bash", "scripts/export-openapi.sh"], cwd=str(project))
    if "graphql" in config.batteries:
        sh(["bash", "scripts/export-graphql-schema.sh"], cwd=str(project))


def expected_agents(config: DogfoodConfig) -> list[str]:
    """The review-agent Check Run names active on a PR for this config's batteries. The
    generated `framework review` posts each agent's check as `review-<agent>` (against
    GITHUB_SHA, which on a pull_request is the merge commit — see merge_sha/fetch_checks)."""
    return [
        f"review-{a}" for a in active_agents("pull_request", list(config.batteries))
    ]


def log(msg: str) -> None:
    """Emit a progress line (flushed) — this harness runs for many minutes per config."""
    print(f"[dogfood] {msg}", flush=True)


def ensure_repo() -> None:
    if sh(["gh", "repo", "view", REPO], check=False).strip():
        return
    sh(
        [
            "gh",
            "repo",
            "create",
            REPO,
            "--public",
            "--description",
            "swiftwater-framework dogfood e2e target (auto-managed; safe to ignore)",
        ]
    )


def seed_main(project: Path) -> str:
    """Force-reset the dogfood repo's main to the freshly rendered project. Returns the
    pushed commit SHA (used to disambiguate the triggered run)."""
    sh(["git", "init", "-b", "main"], cwd=str(project))
    sh(
        ["git", "remote", "add", "origin", f"https://github.com/{REPO}.git"],
        cwd=str(project),
    )
    sh(["git", "add", "-A"], cwd=str(project))
    sh(
        [
            "git",
            "-c",
            "user.name=dogfood",
            "-c",
            "user.email=dogfood@swiftwaterhorizon.com",
            "commit",
            "-m",
            "dogfood: rendered project",
        ],
        cwd=str(project),
    )
    sh(["git", "push", "--force", "origin", "main"], cwd=str(project))
    return sh(["git", "rev-parse", "HEAD"], cwd=str(project)).strip()


def open_benign_pr(project: Path) -> tuple[str, str]:
    """Branch, make a benign README-only change, push, open a PR. Returns (pr_url, head_sha)."""
    sh(["git", "checkout", "-b", "dogfood-pr"], cwd=str(project))
    readme = project / "README.md"
    readme.write_text(readme.read_text() + f"\n{BENIGN_MARKER}\n")
    sh(["git", "add", "README.md"], cwd=str(project))
    sh(
        [
            "git",
            "-c",
            "user.name=dogfood",
            "-c",
            "user.email=dogfood@swiftwaterhorizon.com",
            "commit",
            "-m",
            "dogfood: benign no-op change",
        ],
        cwd=str(project),
    )
    sh(["git", "push", "--force", "origin", "dogfood-pr"], cwd=str(project))
    pr_url = sh(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            REPO,
            "--base",
            "main",
            "--head",
            "dogfood-pr",
            "--title",
            "Dogfood e2e",
            "--body",
            "Automated dogfood run.",
        ],
        check=True,
    ).strip()
    head_sha = sh(["git", "rev-parse", "HEAD"], cwd=str(project)).strip()
    return pr_url, head_sha


def wait_for_run(event: str, branch: str, sha: str, timeout_s: int = 2400) -> str:
    """Poll for the CI run matching (event, branch, head sha), watch it to completion, and
    return its URL. The sha guard avoids selecting a stale run from a prior config on the
    reused repo. Raises on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = sh(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPO,
                "--workflow",
                "CI",
                "--event",
                event,
                "--branch",
                branch,
                "--limit",
                "10",
                "--json",
                "databaseId,url,headSha",
            ],
            check=False,
        )
        rows = json.loads(out or "[]")
        match = next((r for r in rows if r.get("headSha") == sha), None)
        if match:
            log(f"  found {event} run {match['databaseId']}; watching {match['url']}")
            sh(
                [
                    "gh",
                    "run",
                    "watch",
                    str(match["databaseId"]),
                    "--repo",
                    REPO,
                    "--exit-status",
                ],
                check=False,
            )
            return str(match["url"])
        time.sleep(10)
    raise RuntimeError(f"timed out waiting for the {event} run on {branch} @ {sha}")


def fetch_jobs(run_url: str) -> dict:
    run_id = run_url.rstrip("/").split("/")[-1]
    return json.loads(
        sh(["gh", "run", "view", run_id, "--repo", REPO, "--json", "jobs"])
    )


def fetch_checks(sha: str) -> dict:
    return json.loads(
        sh(["gh", "api", f"repos/{REPO}/commits/{sha}/check-runs?per_page=100"])
    )


def merge_sha(pr_url: str) -> str:
    """The PR's merge commit sha. An on:pull_request run sets GITHUB_SHA to this merge
    commit, so the review agents' `review-<agent>` check-runs attach here, NOT to the PR
    head — query this sha for surface 2 (the head sha only carries the workflow-job checks)."""
    num = pr_url.rstrip("/").split("/")[-1]
    return sh(
        ["gh", "api", f"repos/{REPO}/pulls/{num}", "-q", ".merge_commit_sha"]
    ).strip()


def set_secret() -> None:
    key = os.environ.get("ANTHROPIC_RUNTIME_API_KEY", "")
    if not key:
        raise RuntimeError(
            "--with-review-key needs ANTHROPIC_RUNTIME_API_KEY in the env"
        )
    subprocess.run(
        ["gh", "secret", "set", SECRET_NAME, "--repo", REPO, "--body", key],
        text=True,
        check=True,
        capture_output=True,
    )


def clear_secret() -> None:
    sh(["gh", "secret", "delete", SECRET_NAME, "--repo", REPO], check=False)


def reset_repo() -> None:
    """Close the PR + delete the branch, leaving main as the seed for the next config."""
    sh(
        ["gh", "pr", "close", "dogfood-pr", "--repo", REPO, "--delete-branch"],
        check=False,
    )


def run_config(config: DogfoodConfig, with_key: bool) -> RunResult:
    log(f"=== config '{config.name}' (with_key={with_key}) ===")
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        project = Path(tmp) / "render"
        log(f"rendering {config.name} ({len(config.batteries)} batteries) at {project}")
        render(config, project)
        prepare_project(config, project)
        ensure_repo()
        reset_repo()  # idempotent pre-clean: close any stale dogfood-pr from a crashed run
        if with_key:
            set_secret()
        else:
            clear_secret()
        log("seeding main (force-push the rendered project)")
        seed_sha = seed_main(project)
        log(
            f"waiting for the on:push run (sha {seed_sha[:8]}) — watching to completion"
        )
        push_url = wait_for_run("push", "main", seed_sha)
        log(f"push run done: {push_url}")
        agents = expected_agents(config)
        log(f"opening benign-no-op PR ({len(agents)} review agents expected)")
        pr_url, pr_sha = open_benign_pr(project)
        log(
            f"PR opened: {pr_url}; waiting for the on:pull_request run (sha {pr_sha[:8]})"
        )
        pr_run_url = wait_for_run("pull_request", "dogfood-pr", pr_sha)
        checks_sha = merge_sha(pr_url)  # review checks attach to the merge commit
        log(
            f"PR run done: {pr_run_url}; asserting both surfaces (checks @ {checks_sha[:8]})"
        )
        verdict = assert_run(
            fetch_jobs(pr_run_url),
            fetch_checks(checks_sha),
            config,
            expected_agents=agents,
            with_key=with_key,
        )
        push_jobs = classify_jobs(parse_jobs(fetch_jobs(push_url)), config)
        verdict.failures += [f"[push] {f}" for f in push_jobs.failures]
        verdict.ok = verdict.ok and push_jobs.ok
        reset_repo()
        return RunResult(
            config=config.name,
            with_key=with_key,
            push_run_url=push_url,
            pr_run_url=pr_run_url,
            ok=verdict.ok,
            failures=verdict.failures,
            warnings=verdict.warnings,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generated-project dogfood e2e on real GHA."
    )
    parser.add_argument(
        "--with-review-key",
        action="store_true",
        help="Set the repo runtime secret for the paid full review path.",
    )
    args = parser.parse_args()

    results = [
        run_config(cfg, args.with_review_key) for cfg in (BASELINE, ALL_BATTERIES)
    ]
    scorecard = render_scorecard(results, commit=DOGFOOD_COMMIT)
    print(scorecard)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

import json
import os
import sys
from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check as check_integrity, record_drift
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.batteries import resolve as resolve_batteries
from framework_cli.naming import derive_names
from framework_cli.review.aggregate import write_findings
from framework_cli.review.checks import neutral_payload, post_or_skip, to_check_run
from framework_cli.review.diff import (
    changed_files,
    framework_diff,
    matches_globs,
    pr_diff,
)
from framework_cli.review.registry import active_agents, agent_names, get_agent
from framework_cli.review.runner import EVAL_KEY_ENV, RUNTIME_KEY_ENV, default_client
from framework_cli.source import (
    REPO_URL,
    latest_release,
    record_portable_source,
    version_tag,
)
from framework_cli.downskill import DownskillError, downskill_project
from framework_cli.upskill import UpskillError, upskill_project

app = typer.Typer(
    help="Framework CLI — scaffold solid, observable, testable Python projects.",
    no_args_is_help=True,
)


@app.callback()
def _main() -> None:
    """Framework CLI — scaffold solid, observable, testable Python projects."""


@app.command()
def new(
    name: str = typer.Argument(..., help="Human-readable project name"),
    python_version: str = typer.Option("3.12", help="Python version to target"),
    with_: list[str] = typer.Option(
        [], "--with", help="Activate a battery (repeatable), e.g. --with websockets."
    ),
    alerts: str = typer.Option(
        None,
        "--alerts",
        help="Alert channels, comma-separated: webhook,slack,email,pagerduty.",
    ),
) -> None:
    """Scaffold a new project from the framework template."""
    from framework_cli.wizard import run_wizard

    names = derive_names(name)
    dest = Path.cwd() / names.project_slug

    if dest.exists():
        typer.echo(f"Error: {dest} already exists", err=True)
        raise typer.Exit(code=1)

    try:
        answers = run_wizard(with_=with_, alerts=alerts, interactive=sys.stdin.isatty())
        batteries = resolve_batteries(answers["batteries"])
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "package_name": names.package_name,
            "python_version": python_version,
            "batteries": batteries,
            "alert_channels": answers["alert_channels"],
        },
    )
    write_manifest(dest, installed_framework_version())
    record_portable_source(dest, installed_framework_version())
    msg = f"Created '{names.project_slug}' at {dest}"
    if batteries:
        msg += f" (batteries: {', '.join(batteries)})"
    if answers["alert_channels"] != ["webhook"]:
        msg += f" (alerts: {', '.join(answers['alert_channels'])})"
    typer.echo(msg)


@app.command()
def integrity(
    ci: bool = typer.Option(
        False,
        "--ci",
        help="CI mode: skip gitignored existence checks (fresh checkouts).",
    ),
    allow_drift: list[str] = typer.Option(
        [], "--allow-drift", help="Record a managed file as intentionally diverged."
    ),
) -> None:
    """Verify the framework scaffolding in the current project is intact."""
    project = Path.cwd()
    if allow_drift:
        try:
            record_drift(project, allow_drift)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Recorded intentional drift: {', '.join(allow_drift)}")
        raise typer.Exit(0)

    findings = check_integrity(project, ci=ci)
    for f in findings:
        label = "ERROR" if f.fatal else "warning"
        typer.echo(f"{label}: {f.path}: {f.problem} — {f.fix}", err=f.fatal)
    if any(f.fatal for f in findings):
        fatal = sum(1 for f in findings if f.fatal)
        typer.echo(f"\nframework integrity: {fatal} problem(s) found.", err=True)
        raise typer.Exit(1)
    typer.echo("framework integrity: OK")


@app.command(name="dev-combos")
def dev_combos(
    strategy: str = typer.Option(
        "representative",
        "--strategy",
        help="representative | pairwise | sample | broad",
    ),
    seed: int = typer.Option(0, "--seed", help="Seed for the random rotation."),
    sample_size: int = typer.Option(
        6, "--sample-size", help="Random combos added to the broad/sample set."
    ),
) -> None:
    """Emit the render-matrix battery combinations as JSON (framework dogfooding CI)."""
    from framework_cli.devmatrix import combos_for_strategy

    try:
        combos = combos_for_strategy(strategy, seed=seed, sample_size=sample_size)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps([c.as_dict() for c in combos]))


@app.command()
def restore(
    file: str = typer.Argument(
        ...,
        help="Path (relative to the project root) of the framework file to restore.",
    ),
) -> None:
    """Re-fetch a canonical framework file, discarding local edits to it."""
    try:
        restore_file(Path.cwd(), file)
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Restored {file} to the canonical framework version.")


@app.command()
def upskill(
    name: str = typer.Argument(..., help="Path to the project to upskill."),
    with_: list[str] = typer.Option(
        [], "--with", help="Add a battery to the project (repeatable)."
    ),
    alerts: str = typer.Option(
        None,
        "--alerts",
        help="Reconfigure alert channels (comma-separated; replaces the set).",
    ),
) -> None:
    """Update a project to a newer framework version, then run its tests."""
    from framework_cli.source import read_batteries
    from framework_cli.wizard import parse_channels, split_alerts

    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)

    with_batteries = None
    if with_:
        try:
            with_batteries = resolve_batteries([*read_batteries(project), *with_])
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    channels = None
    if alerts is not None:
        try:
            channels = parse_channels(split_alerts(alerts))
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        green = upskill_project(
            project, with_batteries=with_batteries, alert_channels=channels
        )
    except UpskillError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if green:
        typer.echo(f"Upskilled {name}; tests pass.")
    else:
        typer.echo(
            f"Upskilled {name}, but `task test` failed — resolve any Copier conflict markers "
            "and fix failures before committing.",
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def downskill(
    name: str = typer.Argument(..., help="Path to the project."),
    battery: str = typer.Argument(..., help="Battery to remove, e.g. 'webhooks'."),
    force: bool = typer.Option(
        False, "--force", help="Remove even if the battery appears in use."
    ),
) -> None:
    """Remove a battery from a project (deletes its files; preserves migrations), then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)
    try:
        green = downskill_project(project, battery, force=force)
    except (DownskillError, KeyError, UpskillError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if green:
        typer.echo(f"Removed '{battery}' from {name}; tests pass.")
    else:
        typer.echo(
            f"Removed '{battery}' from {name}, but `task test` failed — review the removal diff "
            "and fix references before committing.",
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def check() -> None:
    """Report whether a newer framework release is available."""
    current_tag = version_tag(installed_framework_version())
    latest = latest_release()
    if latest is None:
        typer.echo("framework check: no releases found (or the remote is unreachable).")
        raise typer.Exit(0)
    if latest == current_tag:
        typer.echo(f"framework check: up to date ({current_tag}).")
    else:
        typer.echo(
            f"framework check: installed {current_tag}, latest {latest}. "
            f"Upgrade the CLI with `uv tool install git+{REPO_URL}@{latest}`, "
            f"then run `framework upskill <project>`."
        )


# Module-level seams so tests can monkeypatch the I/O without the SDK.
def realize_cached(fx: object, cache: dict, base_dir: object) -> tuple:
    """Thin seam delegating to evals.realize_cached so tests can monkeypatch it."""
    from framework_cli.review.evals import realize_cached as _rc

    return _rc(fx, cache, base_dir)  # type: ignore[arg-type]


def _review_diff() -> str:
    return pr_diff()


def _review_run(diff: str, spec: object, force_agentic: bool = False) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    if force_agentic or spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(
            diff, Path.cwd(), spec, default_client(RUNTIME_KEY_ENV), max_turns=turns
        )
    bundle = assemble(diff, Path.cwd(), spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client(RUNTIME_KEY_ENV))  # type: ignore[arg-type]


def _eval_run(diff: str, root: object, spec: object) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    base = root if isinstance(root, Path) else Path.cwd()
    if spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(
            diff, base, spec, default_client(EVAL_KEY_ENV), max_turns=turns
        )
    bundle = assemble(diff, base, spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client(EVAL_KEY_ENV))  # type: ignore[arg-type]


@app.command(name="review-aggregate")
def review_aggregate(
    directory: str = typer.Argument(
        ..., help="Directory of per-agent findings JSON files."
    ),
    pr: str = typer.Option("", "--pr", help="PR number (default: $GITHUB_PR_NUMBER)."),
) -> None:
    """Aggregate per-agent review findings into one sticky PR comment (prints on a push)."""
    from framework_cli.review import comment
    from framework_cli.review.aggregate import aggregate, load_results

    result = aggregate(load_results(Path(directory)))
    pr_number = pr or os.environ.get("GITHUB_PR_NUMBER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if pr_number and repo and token:
        comment.post_sticky_comment(
            result.markdown, repo=repo, pr=pr_number, token=token
        )
        typer.echo(
            f"review-aggregate: posted summary to PR #{pr_number} ({result.overall})"
        )
    else:
        typer.echo(result.markdown)


@app.command(name="review-agents")
def review_agents(
    event: str = typer.Option(
        "", "--event", help="GitHub event name (default: $GITHUB_EVENT_NAME)."
    ),
    target: str = typer.Option(
        "project", "--target", help="Review target: 'project' (default) or 'framework'."
    ),
) -> None:
    """Print the JSON array of review agents active for the event (drives the CI matrix)."""
    if target == "framework":
        from framework_cli.review.context import FRAMEWORK_AGENTS

        typer.echo(json.dumps(sorted(FRAMEWORK_AGENTS)))
        return

    from framework_cli.source import read_batteries

    resolved = event or os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    batteries = read_batteries(
        Path(".")
    )  # the generated project's recorded battery set
    typer.echo(json.dumps(active_agents(resolved, batteries)))


@app.command(name="eval")
def eval_agents(
    agent: str = typer.Argument(
        "", help="Evaluate only this agent (default: all registered)."
    ),
    fixtures: str = typer.Option(
        "tests/eval/fixtures", "--fixtures", help="Fixtures root directory."
    ),
    repeat: int = typer.Option(
        1, "--repeat", help="Runs per fixture; rates are averaged."
    ),
    require_fixtures: bool = typer.Option(
        False, "--require-fixtures", help="Fail if an evaluated agent has no fixtures."
    ),
    require_key: bool = typer.Option(
        False,
        "--require-key",
        help="Fail (not skip) if ANTHROPIC_EVAL_API_KEY is unset.",
    ),
) -> None:
    """Run golden fixtures through the review agents and score recall/precision (spec §20)."""
    from framework_cli.review.evals import (
        DEFAULT_THRESHOLDS,
        flags,
        load_fixtures,
        load_thresholds,
        score_agent,
    )

    if not os.environ.get(EVAL_KEY_ENV):
        if require_key:
            typer.echo("eval: ANTHROPIC_EVAL_API_KEY is required but unset", err=True)
            raise typer.Exit(1)
        typer.echo("eval: skipped (no ANTHROPIC_EVAL_API_KEY)")
        raise typer.Exit(0)

    if repeat < 1:
        typer.echo("eval: --repeat must be >= 1", err=True)
        raise typer.Exit(2)

    import tempfile

    root = Path(fixtures)
    _base_dir = Path(tempfile.mkdtemp(prefix="evalbase-"))
    _combo_cache: dict = {}
    thresholds = load_thresholds(root / "thresholds.yaml")
    by_agent: dict[str, list] = {}
    for fx in load_fixtures(root):
        by_agent.setdefault(fx.agent, []).append(fx)

    known = set(agent_names())
    for a in sorted(by_agent):
        if a not in known:
            typer.echo(
                f"warning: fixtures for unknown agent '{a}' (not in registry)", err=True
            )

    targets = [agent] if agent else agent_names()
    failing = 0
    missing: list[str] = []
    for a in targets:
        try:
            spec = get_agent(a)
        except KeyError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        fx_list = by_agent.get(a, [])
        if not fx_list:
            missing.append(a)
            typer.echo(f"{spec.name}    no fixtures (skipped)")
            continue
        bad_rates: list[float] = []
        good_rates: list[float] = []
        for fx in fx_list:
            rroot, rdiff = realize_cached(fx, _combo_cache, _base_dir)
            hits = 0
            for _ in range(repeat):
                try:
                    found = _eval_run(rdiff, rroot, spec)
                except Exception:  # noqa: BLE001 - a failed run counts as a non-detection
                    found = []
                blocked = (
                    flags(found, spec, file=fx.seeded_file)
                    if fx.kind == "bad"
                    else flags(found, spec)
                )
                hits += 1 if blocked else 0
            (bad_rates if fx.kind == "bad" else good_rates).append(hits / repeat)
        score = score_agent(
            a, bad_rates, good_rates, thresholds.get(a, DEFAULT_THRESHOLDS)
        )
        status = "PASS" if score.passed else f"FAIL ({score.reason})"
        typer.echo(
            f"{spec.name}    recall {score.recall:.2f}  fp {score.fp_rate:.2f}    {status}"
        )
        if not score.passed:
            failing += 1

    summary = f"{len(targets)} agent(s) · {failing} failing"
    if missing:
        summary += f" · {len(missing)} without fixtures"
    typer.echo(summary)
    coverage_fail = bool(missing) and require_fixtures
    raise typer.Exit(1 if failing or coverage_fail else 0)


@app.command()
def review(
    agent: str = typer.Argument(..., help="Review agent name, e.g. 'security'."),
    findings_out: str = typer.Option(
        "",
        "--findings-out",
        help="Write this agent's findings JSON to this path (for aggregation).",
    ),
    target: str = typer.Option(
        "project", "--target", help="Review target: 'project' (default) or 'framework'."
    ),
) -> None:
    """Run a Layer-3 review agent over the PR diff and post a GitHub Check Run."""
    try:
        spec = get_agent(agent)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    def _emit(conclusion: str, found: list) -> None:
        if findings_out:
            write_findings(Path(findings_out), spec.name, conclusion, found)

    if not os.environ.get(RUNTIME_KEY_ENV):
        payload = neutral_payload(
            spec.name, "review skipped — set ANTHROPIC_RUNTIME_API_KEY to enable."
        )
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        _emit(payload.conclusion, [])
        typer.echo(f"{spec.name}: skipped (no ANTHROPIC_RUNTIME_API_KEY)")
        raise typer.Exit(0)

    try:
        diff = framework_diff() if target == "framework" else _review_diff()
        if spec.trigger_globs and not matches_globs(
            changed_files(diff), spec.trigger_globs
        ):
            payload = neutral_payload(
                spec.name, f"not triggered (no {', '.join(spec.trigger_globs)} change)"
            )
            post_or_skip(payload, token=token, repo=repo, sha=sha)
            _emit(payload.conclusion, [])
            typer.echo(f"{spec.name}: skipped (not triggered)")
            raise typer.Exit(0)
        findings = _review_run(diff, spec, force_agentic=(target == "framework"))
        payload = to_check_run(spec, findings)
    except typer.Exit:
        raise  # the not-triggered skip (and any Exit) must propagate, not become neutral
    except Exception as exc:  # noqa: BLE001 - infra failure must not block CI
        payload = neutral_payload(spec.name, f"review could not run: {exc}")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        _emit(payload.conclusion, [])
        typer.echo(f"{spec.name}: neutral (could not run: {exc})", err=True)
        raise typer.Exit(0) from exc

    post_or_skip(payload, token=token, repo=repo, sha=sha)
    _emit(payload.conclusion, findings)
    typer.echo(
        f"{spec.name}: {payload.conclusion} ({len(payload.annotations)} finding(s))"
    )
    raise typer.Exit(1 if payload.conclusion == "failure" else 0)

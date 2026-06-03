import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check as check_integrity, record_drift
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.batteries import resolve as resolve_batteries
from framework_cli.lockfile import write_lockfile
from framework_cli.naming import derive_names
from framework_cli.review.aggregate import write_findings
from framework_cli.review.checks import neutral_payload, post_or_skip, to_check_run
from framework_cli.review.diff import (
    changed_files,
    framework_diff,
    matches_globs,
    pr_diff,
    staged_diff,
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
    write_lockfile(
        dest
    )  # ship a committed uv.lock so the first push's --frozen jobs pass
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


@app.command(name="template-render")
def template_render(
    out: str = typer.Option(..., "--out", help="Target directory to render into."),
    batteries: str = typer.Option(
        "all",
        "--batteries",
        help="'all' (default) or a comma-separated battery subset.",
    ),
) -> None:
    """Render the bundled template into OUT (deterministic, non-interactive).

    Uses the canonical fixture answers (package_name=demo) plus the chosen
    batteries (default: all), then git-inits + commits so review tooling sees a
    clean repo. Produces the audit subject for /reviewers:template-audit.
    """
    from framework_cli.batteries import battery_names, resolve

    if batteries.strip() == "all":
        selected = battery_names()
    else:
        selected = [b.strip() for b in batteries.split(",") if b.strip()]
    resolved = resolve(selected)

    root = Path(out).resolve()
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": resolved,
        },
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "template-audit base",
        ],
        cwd=root,
        check=True,
    )
    typer.echo(
        json.dumps(
            {"out": str(root), "package_name": "demo", "batteries": resolved},
            indent=2,
        )
    )


@app.command(name="template-map")
def template_map_cmd(
    findings: str = typer.Option(
        ..., "--findings", help="Path to the findings/ dir (per-agent JSON)."
    ),
    template_root: str = typer.Option(
        ..., "--template-root", help="Path to src/framework_cli/template."
    ),
    package_name: str = typer.Option(
        "demo", "--package-name", help="package_name used in the render."
    ),
    out: str = typer.Option(
        "", "--out", help="Output markdown path (default: <findings>/../path-map.md)."
    ),
) -> None:
    """Annotate rendered-project findings with best-guess template-source paths."""
    from framework_cli.template_map import map_findings, render_markdown

    findings_dir = Path(findings)
    rows = map_findings(findings_dir, Path(template_root), package_name)
    out_path = Path(out) if out else findings_dir.parent / "path-map.md"
    out_path.write_text(render_markdown(rows))
    typer.echo(json.dumps({"rows": len(rows), "out": str(out_path)}, indent=2))


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
    from framework_cli.review.decisions import relevant_decisions
    from framework_cli.review.runner import run_agent

    short = spec.name.removeprefix("review-")  # type: ignore[attr-defined]
    if force_agentic or spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(
            diff,
            Path.cwd(),
            spec,
            default_client(RUNTIME_KEY_ENV),
            max_turns=turns,
            decisions=tuple(relevant_decisions(short, Path.cwd())),
        )
    bundle = assemble(diff, Path.cwd(), spec.context, model=spec.model, agent=short)  # type: ignore[attr-defined]
    return run_agent(bundle, spec, default_client(RUNTIME_KEY_ENV))  # type: ignore[arg-type]


def _eval_run(
    diff: str, root: object, spec: object, *, report: dict | None = None
) -> list:
    from framework_cli.review.context import assemble
    from framework_cli.review.runner import run_agent

    base = root if isinstance(root, Path) else Path.cwd()
    if spec.context.strategy == "agentic":  # type: ignore[attr-defined]
        from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic

        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS  # type: ignore[attr-defined]
        return run_agent_agentic(
            diff,
            base,
            spec,
            default_client(EVAL_KEY_ENV),
            max_turns=turns,
            report=report,
        )
    bundle = assemble(diff, base, spec.context, model=spec.model)  # type: ignore[attr-defined]
    return run_agent(
        bundle,
        spec,  # type: ignore[arg-type]
        default_client(EVAL_KEY_ENV),
        report=report,
    )


def _write_findings(
    out: Path, fx: object, repeat_idx: int, findings: list, report: dict
) -> None:
    """Persist one (agent, fixture, repeat)'s findings + telemetry as JSON for diagnosis."""
    from dataclasses import asdict

    dest = out / fx.agent / fx.kind  # type: ignore[attr-defined]
    dest.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent": fx.agent,  # type: ignore[attr-defined]
        "kind": fx.kind,  # type: ignore[attr-defined]
        "case": fx.name,  # type: ignore[attr-defined]
        "repeat": repeat_idx,
        "seeded_file": fx.seeded_file,  # type: ignore[attr-defined]
        "findings": [asdict(f) for f in findings],
        **report,
    }
    (dest / f"{fx.name}__r{repeat_idx}.json").write_text(  # type: ignore[attr-defined]
        json.dumps(payload, indent=2, sort_keys=True)
    )


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
    findings_out: str = typer.Option(
        "",
        "--findings-out",
        help="Directory to write per-(agent,fixture,repeat) findings JSON for diagnosis.",
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

    import anthropic

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
            for i in range(repeat):
                report: dict | None = {} if findings_out else None
                try:
                    found = _eval_run(rdiff, rroot, spec, report=report)
                except anthropic.APIError as exc:
                    typer.echo(
                        f"\neval: ABORTED at {spec.name} — API error "
                        f"({type(exc).__name__}): {exc}",
                        err=True,
                    )
                    typer.echo(
                        "An API/credit/rate-limit failure is not a non-detection; "
                        "scores so far are unreliable. Resolve the API issue and re-run.",
                        err=True,
                    )
                    raise typer.Exit(3) from exc
                if findings_out:
                    _write_findings(Path(findings_out), fx, i, found, report or {})
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


@app.command(name="eval-analyze")
def eval_analyze(
    findings_dir: str = typer.Argument(
        ..., help="Directory written by `framework eval --findings-out`."
    ),
    out: str = typer.Option(
        "", "--out", help="Write the report to this path (else print to stdout)."
    ),
    thresholds: str = typer.Option(
        "tests/eval/fixtures/thresholds.yaml",
        "--thresholds",
        help="Current thresholds file (used as the comparison baseline).",
    ),
    margin: float = typer.Option(
        0.10,
        "--margin",
        help="Margin applied when proposing thresholds (recall_min = recall - margin).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit code 2 if any drift is detected (used by the gate context).",
    ),
) -> None:
    """Produce scorecard + cost + recall/fp diagnosis + threshold proposal from
    per-call eval records (the artifacts written by `framework eval --findings-out`)."""
    from framework_cli.review import analyze
    from framework_cli.review.evals import load_thresholds

    records = analyze.load_records(Path(findings_dir))
    if not records:
        typer.echo(f"eval-analyze: no records found under {findings_dir}", err=True)
        raise typer.Exit(1)
    thr = load_thresholds(Path(thresholds))
    scores = analyze.scorecard(records, thr)
    model_map: dict[str, str] = {}
    for r in records:
        try:
            model_map[r.agent] = get_agent(r.agent).model
        except KeyError:
            pass
    costs = analyze.cost_report(records, model_map)
    recall_diag = analyze.recall_diagnosis(records)
    fp_diag = analyze.fp_diagnosis(records)
    agentic = analyze.agentic_behavior(records)
    proposed = analyze.propose_thresholds(scores, margin=margin)
    md = analyze.render_markdown(
        records, scores, costs, recall_diag, fp_diag, agentic, proposed
    )
    if out:
        Path(out).write_text(md)
        typer.echo(f"eval-analyze: wrote {out}")
    else:
        typer.echo(md)
    if strict:
        drifts = analyze.drift_check(records)
        if drifts:
            typer.echo(
                f"eval-analyze: STRICT failure — {len(drifts)} drifted call(s) "
                f"(see ## Drift check section above)",
                err=True,
            )
            raise typer.Exit(2)
        # --strict is purely about drift fidelity; do not also exit on score-FAILs.
        return
    # Non-strict: exit 1 if any agent failed its thresholds (so callers can detect).
    if any(not s.passed for s in scores):
        raise typer.Exit(1)


@app.command(name="tune-prepare")
def tune_prepare(
    agent: str = typer.Option(
        "",
        "--agent",
        help="Single agent to prepare (default: all from registry).",
    ),
    fixtures: str = typer.Option(
        "tests/eval/fixtures",
        "--fixtures",
        help="Fixtures root.",
    ),
    repeat: int = typer.Option(1, "--repeat", help="Repeats per fixture."),
    output_dir: str = typer.Option(
        "",
        "--output-dir",
        help="Output dir for finalize (echoed in the prep manifest).",
    ),
    split_to: str = typer.Option(
        "",
        "--split-to",
        help=(
            "If set, write a small index.json + per-item items/item-NNNN.json under "
            "DIR (in addition to the stdout manifest). Lets the Workflow tool be "
            "invoked with a tiny args payload instead of a multi-MB inline manifest. "
            "Idempotent: an existing DIR is cleared first."
        ),
    ),
) -> None:
    """Emit the tune-mode work-item manifest (fixtures × agents × repeats).

    Output is JSON on stdout; consumed by /reviewers:tune.
    """
    _emit_tune_prep(agent, Path(fixtures), repeat, output_dir, split_to)


@app.command(name="audit-prepare")
def audit_prepare(
    agent: list[str] = typer.Option(
        None,
        "--agent",
        help=(
            "Restrict to this agent. Repeat for multiple agents. "
            "Omit for all active agents for the target."
        ),
    ),
    target: str = typer.Option(
        "",
        "--target",
        help="'framework' or 'project' (default: auto-detect).",
    ),
    output_dir: str = typer.Option(
        "",
        "--output-dir",
        help="Output dir for finalize (echoed in the prep manifest).",
    ),
    split_to: str = typer.Option(
        "",
        "--split-to",
        help=(
            "If set, write a small index.json + per-item items/item-NNNN.json under "
            "DIR (in addition to the stdout manifest). Lets the Workflow tool be "
            "invoked with a tiny args payload instead of a multi-MB inline manifest. "
            "Idempotent: an existing DIR is cleared first."
        ),
    ),
    snapshot: bool = typer.Option(
        False,
        "--snapshot",
        help=(
            "Force every agent into snapshot mode (no diff seed; bundled context "
            "does the work). Skips per-agent baseline auto-discovery."
        ),
    ),
    since: str = typer.Option(
        "",
        "--since",
        help=(
            "Force delta mode against a chosen anchor — either a git ref/SHA "
            "(all agents diff HEAD vs that ref) or a baseline directory under "
            "docs/superpowers/eval-scorecards/ (per-agent: agents in that baseline "
            "diff against its SHA; agents not in the baseline fall back to snapshot)."
        ),
    ),
) -> None:
    """Emit the audit-mode work-item manifest (current code, one item per agent).

    Output is JSON on stdout; consumed by /reviewers:audit. When ``--split-to DIR``
    is set, also writes a split-manifest layout (``index.json`` + ``items/item-NNNN.json``)
    under DIR for the Workflow tool to consume via ``{indexPath, itemsDir}`` args.

    By default, each agent's mode is auto-discovered: if a prior baseline under
    ``docs/superpowers/eval-scorecards/audit-*/`` exists for this (target, agent),
    the agent runs in delta mode (diff vs that baseline's git_sha). Otherwise the
    agent falls back to snapshot mode (with a visible log line per agent).
    """
    if snapshot and since:
        typer.echo(
            "audit-prepare: --snapshot and --since are mutually exclusive",
            err=True,
        )
        raise typer.Exit(2)
    _emit_audit_prep(
        list(agent or []),
        target,
        output_dir,
        split_to,
        snapshot_flag=snapshot,
        since_arg=since or None,
    )


@app.command(name="gate-prepare")
def gate_prepare(
    split_to: str = typer.Option(
        "",
        "--split-to",
        help=(
            "If set, write a small index.json + per-item items/item-NNNN.json under "
            "DIR (in addition to the stdout manifest). Lets the Workflow tool be "
            "invoked with a tiny args payload instead of a multi-MB inline manifest. "
            "Idempotent: an existing DIR is cleared first."
        ),
    ),
) -> None:
    """Emit the gate-mode work-item manifest (affected agents for the staged set).

    Output is JSON on stdout; consumed by /reviewers:gate (and the PreToolUse
    hook, which uses it to recompute the current staged_hash).
    """
    _emit_gate_prep(split_to)


def _staged_files() -> list[str]:
    """Return the list of files in the staged set (git diff --cached --name-only)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def _is_review_relevant(path: str) -> bool:
    """True if `path` is one of the review-relevant paths the gate cares about."""
    if path.startswith("src/framework_cli/review/"):
        return True
    if path.startswith("src/framework_cli/template/"):
        return True
    if path.startswith("tests/eval/fixtures/"):
        return True
    return False


def _affected_agents(staged: list[str]) -> tuple[str, list[str]]:
    """Return (mode, agents_set). mode is 'gate', 'regrade', or 'noop'."""
    if not staged:
        return ("noop", [])
    # Thresholds-only → regrade
    review_relevant = {p for p in staged if _is_review_relevant(p)}
    if review_relevant == {"tests/eval/fixtures/thresholds.yaml"}:
        return ("regrade", [])
    if not review_relevant:
        return ("noop", [])

    all_agents = agent_names()
    bundle_agents = [
        a for a in all_agents if get_agent(a).context.strategy != "agentic"
    ]
    agentic_agents = [
        a for a in all_agents if get_agent(a).context.strategy == "agentic"
    ]
    affected: set[str] = set()
    for path in review_relevant:
        # Per-agent prompt
        if path.startswith("src/framework_cli/review/agents/") and path.endswith(".md"):
            name = Path(path).stem
            if name in all_agents:
                affected.add(name)
            continue
        # Per-agent fixture
        if path.startswith("tests/eval/fixtures/"):
            parts = Path(path).parts
            if len(parts) >= 4:  # tests/eval/fixtures/<agent>/<kind>/<case>/<file>
                name = parts[3]
                if name in all_agents:
                    affected.add(name)
            continue
        # runner.py → all bundle
        if path == "src/framework_cli/review/runner.py":
            affected.update(bundle_agents)
            continue
        # agentic.py → all agentic
        if path == "src/framework_cli/review/agentic.py":
            affected.update(agentic_agents)
            continue
        # context.py / findings.py / registry.py → all
        if path in (
            "src/framework_cli/review/context.py",
            "src/framework_cli/review/findings.py",
            "src/framework_cli/review/registry.py",
        ):
            affected.update(all_agents)
            continue
        # template/** → all (fixtures render from template)
        if path.startswith("src/framework_cli/template/"):
            affected.update(all_agents)
            continue
    return ("gate", sorted(affected))


def _staged_hash(staged: list[str]) -> str:
    """sha256 of concatenated staged review-relevant file contents (sorted by path)."""
    h = hashlib.sha256()
    for p in sorted(staged):
        if not _is_review_relevant(p):
            continue
        try:
            content = subprocess.run(
                ["git", "show", f":{p}"],  # the staged blob's content
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        except Exception:
            content = ""
        h.update(p.encode())
        h.update(b"\x00")
        h.update(content.encode())
        h.update(b"\x00")
    return "sha256:" + h.hexdigest()


def _prepare_split_dir(split_to: str) -> tuple[Path, Path]:
    """Create a clean, private (0o700) split-manifest directory at ``split_to``.

    Returns ``(split_dir, items_dir)``. Hardening for the deferred findings in the
    2026-05-30 audit (#3/#6/#7): refuse a symlink or non-directory at the target —
    so we never rmtree/replace through a symlink or raise opaquely on a file
    collision — and build the tree under a private ``tempfile.mkdtemp`` staging dir
    that is atomically ``os.replace``d into place, so the published directory is
    0o700 with no umask window and the publish is atomic. A narrow rmtree->replace
    race remains (proportionate for this surface); a hostile racer recreating the
    target as a non-empty dir makes ``os.replace`` raise rather than clobber.
    """
    import shutil
    import tempfile

    split_dir = Path(split_to)
    if split_dir.is_symlink():
        raise RuntimeError(f"--split-to target is a symlink, refusing: {split_dir}")
    if split_dir.exists():
        if not split_dir.is_dir():
            raise RuntimeError(
                f"--split-to target exists and is not a directory: {split_dir}"
            )
        shutil.rmtree(split_dir)
    parent = split_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".split-staging-", dir=parent))
    items_dir = staging / "items"
    items_dir.mkdir()
    items_dir.chmod(0o700)
    os.replace(staging, split_dir)
    return split_dir, split_dir / "items"


def _emit_gate_prep(split_to: str = "") -> None:
    """Emit a gate-mode manifest from the current staged set."""
    staged = _staged_files()
    detected_mode, agents = _affected_agents(staged)
    staged_hash = _staged_hash(staged)

    if detected_mode == "noop":
        manifest: dict = {
            "mode": "noop",
            "agents_set": [],
            "work_items": [],
            "staged_hash": staged_hash,
            "output_dir": ".framework/audit/latest",
        }
    elif detected_mode == "regrade":
        manifest = {
            "mode": "regrade",
            "agents_set": [],
            "work_items": [],
            "staged_hash": staged_hash,
            "output_dir": ".framework/audit/latest",
        }
    else:
        # Build work items for each affected agent (same shape as audit-mode items).
        # Use staged_diff() — NOT _review_diff() / pr_diff() — so the gate reviews the
        # about-to-be-committed staged set, not the prior commit (HEAD~1...HEAD), which
        # was the original (buggy) behavior that reviewed the wrong content.
        diff = staged_diff()
        root = Path.cwd()
        work_items: list[dict] = []
        for a in agents:
            try:
                spec = get_agent(a)
            except KeyError:
                continue
            work_items.append(_build_audit_work_item(spec, diff, root))
        manifest = {
            "mode": "gate",
            "agents_set": agents,
            "work_items": work_items,
            "staged_hash": staged_hash,
            "output_dir": ".framework/audit/latest",
        }

    # Optional split-manifest write: in addition to the stdout manifest, write a small
    # index.json + per-item items/item-NNNN.json so the Workflow tool can be invoked with
    # a tiny args payload ({indexPath, itemsDir}) instead of a multi-MB inline manifest.
    # Mirrors the tune-prepare split layout but with gate's simpler item shape
    # (one item per affected agent; no kind/case/repeat dimension).
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)

        index_items: list[dict] = []
        for i, wi in enumerate(manifest["work_items"]):
            item_path = items_dir / f"item-{i:04d}.json"
            item_path.write_text(json.dumps(wi, indent=2))
            item_path.chmod(0o600)
            index_items.append(
                {
                    "i": i,
                    "agent": wi["agent"],
                    "subagent_type": wi["subagent_type"],
                    # Carry the registry model so the subscription Workflow
                    # dispatches each subagent at its intended tier instead of
                    # the harness default.
                    "model": wi["model"],
                }
            )
        index = {
            "mode": manifest["mode"],
            "agents_set": manifest["agents_set"],
            "staged_hash": staged_hash,
            "items": index_items,
            "output_dir": manifest["output_dir"],
        }
        index_path = split_dir / "index.json"
        index_path.write_text(json.dumps(index, indent=2))
        index_path.chmod(0o600)

    typer.echo(json.dumps(manifest, indent=2))


def _emit_tune_prep(
    single_agent: str,
    fixtures_root: Path,
    repeat: int,
    output_dir: str,
    split_to: str = "",
) -> None:
    import tempfile

    from framework_cli.review.evals import load_fixtures

    targets = [single_agent] if single_agent else agent_names()
    base_dir = Path(tempfile.mkdtemp(prefix="evalprep-"))
    cache: dict = {}

    by_agent: dict[str, list] = {}
    for fx in load_fixtures(fixtures_root):
        by_agent.setdefault(fx.agent, []).append(fx)

    work_items: list[dict] = []
    for a in targets:
        try:
            spec = get_agent(a)
        except KeyError:
            typer.echo(f"tune-prepare: unknown agent '{a}'", err=True)
            raise typer.Exit(1) from None
        for fx in by_agent.get(a, []):
            root, diff = realize_cached(fx, cache, base_dir)
            for i in range(repeat):
                work_items.append(_build_work_item(spec, fx, i, diff, root))

    manifest = {
        "mode": "tune",
        "agents_set": targets,
        "work_items": work_items,
        "output_dir": output_dir or "",
    }

    # Optional split-manifest write: in addition to the stdout manifest, write a small
    # index.json + per-item items/item-NNNN.json so the Workflow tool can be invoked with
    # a tiny args payload ({indexPath, itemsDir}) instead of a multi-MB inline manifest.
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)

        index_items: list[dict] = []
        for i, wi in enumerate(work_items):
            item_path = items_dir / f"item-{i:04d}.json"
            item_path.write_text(json.dumps(wi, indent=2))
            item_path.chmod(0o600)
            index_items.append(
                {
                    "i": i,
                    "agent": wi["agent"],
                    "kind": wi["kind"],
                    "case": wi["case"],
                    "repeat_idx": wi["repeat_idx"],
                    "subagent_type": wi["subagent_type"],
                    "model": wi["model"],
                    "seeded_file": wi.get("seeded_file"),
                }
            )
        index = {
            "mode": "tune",
            "agents_set": targets,
            "items": index_items,
            "output_dir": output_dir or "",
        }
        index_path = split_dir / "index.json"
        index_path.write_text(json.dumps(index, indent=2))
        index_path.chmod(0o600)

    typer.echo(json.dumps(manifest, indent=2))


def _build_work_item(
    spec: object, fx: object, repeat_idx: int, diff: str, root: Path
) -> dict:
    """Build one work item: subagent_type + model + assembled prompt + diff + root."""
    from framework_cli.review.context import assemble

    is_agentic = spec.context.strategy == "agentic"  # type: ignore[attr-defined]
    if is_agentic:
        # Agentic: pass diff + agent prompt + tool-use instruction.
        system_blocks = [
            {"text": f"Review this unified diff:\n\n{diff}"},
            {"text": spec.prompt},  # type: ignore[attr-defined]
        ]
        user_message = (
            f"You are reviewing the codebase rooted at: {root}\n\n"
            "Use the Read, Grep, and Glob tools (these only — do NOT use Bash, "
            "WebFetch, WebSearch, or any other tool) to explore the surrounding "
            "code as needed. Use absolute paths starting with the root above for "
            "all tool calls.\n\n"
            "When done, reply with ONLY a JSON array of findings:\n"
            '  [{"path": "...", "line": N, "severity": "...", "message": "...", '
            '"suggestion": "..."}]\n\n'
            "IMPORTANT: in each finding, the `path` MUST be a path RELATIVE to "
            f"the project root above (e.g. 'src/demo/foo.py'), NOT the absolute "
            "path you used for the tool call. The scoring layer matches on "
            "relative paths; absolute paths register as misses."
        )
        return {
            "agent": fx.agent,  # type: ignore[attr-defined]
            "kind": fx.kind,  # type: ignore[attr-defined]
            "case": fx.name,  # type: ignore[attr-defined]
            "repeat_idx": repeat_idx,
            "seeded_file": fx.seeded_file,  # type: ignore[attr-defined]
            "subagent_type": "Explore",
            "model": spec.model,  # type: ignore[attr-defined]
            "system_blocks": system_blocks,
            "user_message": user_message,
            "tools_allowed": ["Read", "Grep", "Glob"],
            "root_dir": str(root),
            "diff": diff,
        }
    # Bundle tier: assemble with context_files, single text completion.
    bundle = assemble(diff, root, spec.context, model=spec.model)  # type: ignore[attr-defined]
    system_blocks = [{"text": f"Review this unified diff:\n\n{bundle.diff}"}]
    if bundle.context_files:
        joined = "\n\n".join(f"=== {p} ===\n{c}" for p, c in bundle.context_files)
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system_blocks.append(
            {"text": f"Relevant repository files for context:\n\n{joined}{note}"}
        )
    system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
    return {
        "agent": fx.agent,  # type: ignore[attr-defined]
        "kind": fx.kind,  # type: ignore[attr-defined]
        "case": fx.name,  # type: ignore[attr-defined]
        "repeat_idx": repeat_idx,
        "seeded_file": fx.seeded_file,  # type: ignore[attr-defined]
        "subagent_type": "general-purpose",
        "model": spec.model,  # type: ignore[attr-defined]
        "system_blocks": system_blocks,
        "user_message": "Return your findings as a JSON array only.",
        "tools_allowed": None,
        "root_dir": str(root),
        "diff": diff,
    }


def _detect_audit_target(explicit: str) -> str:
    """Return 'framework' or 'project'. Errors loudly if neither matches and no explicit override."""
    if explicit in ("framework", "project"):
        return explicit
    if explicit:
        raise typer.BadParameter(
            f"--target must be 'framework' or 'project' (got '{explicit}')"
        )
    cwd = Path.cwd()
    if (cwd / "src" / "framework_cli").is_dir() and (cwd / "pyproject.toml").is_file():
        try:
            import tomllib

            data = tomllib.loads((cwd / "pyproject.toml").read_text())
            if data.get("project", {}).get("name") == "framework-cli":
                return "framework"
        except (OSError, tomllib.TOMLDecodeError):
            pass
    if (cwd / ".copier-answers.yml").is_file():
        return "project"
    raise typer.BadParameter(
        "Could not auto-detect target. Pass --target framework or --target project."
    )


def _default_scorecards_root() -> Path:
    """The directory under which preserved audit baselines live."""
    return Path("docs/superpowers/eval-scorecards")


def _resolve_audit_base(
    agent: str,
    target: str,
    *,
    snapshot_flag: bool,
    since_arg: str | None,
    scorecards_root: Path,
) -> tuple[str, str | None, str | None]:
    """Return (review_mode, base_sha, base_baseline_name) for one agent.

    review_mode is "snapshot" or "delta".
    base_sha is the commit to diff HEAD against (None for snapshot).
    base_baseline_name is the dated-dir name of the resolved baseline, if any.

    Cases:
      * snapshot_flag → ("snapshot", None, None) — forced.
      * since_arg is a baseline dir → per-agent: ("delta", sha, name) if agent
        was in that baseline, else ("snapshot", None, None) (fallback).
      * since_arg is a ref/SHA → ("delta", resolved_sha, None); raises
        ValueError if the ref doesn't resolve.
      * No flags → auto-discover the newest baseline for this (target, agent);
        ("delta", sha, name) if found, else ("snapshot", None, None) (fallback).
    """
    from framework_cli.review.baselines import (
        find_latest_baseline_for_agent,
        is_baseline_dir,
        read_baseline_sha,
    )

    if snapshot_flag:
        return ("snapshot", None, None)

    if since_arg:
        since_path = Path(since_arg)
        if is_baseline_dir(since_path):
            meta = json.loads((since_path / "meta.json").read_text())
            agents_in_baseline = meta.get("agents") or []
            if agent in agents_in_baseline:
                sha = read_baseline_sha(since_path)
                return ("delta", sha, since_path.name)
            return ("snapshot", None, None)
        # Treat as a ref/SHA. Resolve via git rev-parse.
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{since_arg}^{{commit}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            detail = f": {stderr}" if stderr else ""
            raise ValueError(
                f"could not resolve --since ref {since_arg!r}{detail}. Is that ref reachable?"
            )
        return ("delta", result.stdout.strip(), None)

    # Auto-discover.
    found = find_latest_baseline_for_agent(target, agent, scorecards_root)
    if found is None:
        return ("snapshot", None, None)
    sha = read_baseline_sha(found)
    return ("delta", sha, found.name)


def _emit_audit_prep(
    selected_agents: list[str],
    target_arg: str,
    output_dir: str,
    split_to: str = "",
    *,
    snapshot_flag: bool = False,
    since_arg: str | None = None,
) -> None:
    """Emit the audit-mode manifest to stdout (always) plus, when ``split_to`` is
    non-empty, an on-disk split-manifest layout under ``split_to``:

    * ``<split_to>/index.json`` — slim metadata (``mode``, ``target``,
      ``agents_set``, ``output_dir``, ``items: [{i, agent, subagent_type,
      review_mode, base_sha, base_baseline}]``). The three mode-related fields
      ride on the index entry — not just the per-item file — so the workflow's
      per-item dispatch can branch the DELTA vs SNAPSHOT prompt template
      without re-reading each item file. Written with mode 0o600.
    * ``<split_to>/items/item-NNNN.json`` — one full work-item per file
      (``system_blocks``, ``user_message``, etc.). Each written with mode 0o600.
    * ``<split_to>/`` and ``<split_to>/items/`` themselves get mode 0o700.

    Each work-item also carries ``review_mode`` / ``base_sha`` / ``base_baseline``
    fields, resolved per-agent via :func:`_resolve_audit_base`. The
    ``system_blocks[0]`` diff text is :func:`delta_diff` output when
    ``review_mode == "delta"``, or the (empty) :func:`snapshot_seed` output
    when ``review_mode == "snapshot"``.

    The split layout exists so the Workflow tool can be invoked with a tiny
    ``{indexPath, itemsDir}`` args payload instead of a multi-MB inline manifest
    (the documented ~1.76 MB Workflow-args ceiling). Mirrors ``_emit_tune_prep``
    and ``_emit_gate_prep``.
    """
    from framework_cli.review.context import FRAMEWORK_AGENTS
    from framework_cli.review.diff import delta_diff, snapshot_seed
    from framework_cli.source import read_batteries

    target = _detect_audit_target(target_arg)
    if target == "framework":
        all_agents = sorted(FRAMEWORK_AGENTS)
    else:
        all_agents = active_agents("pull_request", read_batteries(Path(".")))
    # Dedupe selected agents while preserving insertion order.
    selected = list(dict.fromkeys(selected_agents))
    if selected:
        unknown = [a for a in selected if a not in all_agents]
        if unknown:
            typer.echo(
                f"audit-prepare: unknown agent(s): {', '.join(unknown)}. "
                f"Valid agents for target '{target}': {', '.join(sorted(all_agents))}",
                err=True,
            )
            raise typer.Exit(2)
        agents_set = selected
    else:
        agents_set = all_agents

    scorecards_root = _default_scorecards_root()
    root = Path.cwd()
    work_items: list[dict] = []
    for a in agents_set:
        try:
            spec = get_agent(a)
        except KeyError:
            continue

        try:
            mode, base_sha, base_baseline = _resolve_audit_base(
                a,
                target,
                snapshot_flag=snapshot_flag,
                since_arg=since_arg,
                scorecards_root=scorecards_root,
            )
        except ValueError as exc:
            typer.echo(f"audit-prepare: {exc}", err=True)
            raise typer.Exit(2) from exc

        if mode == "delta":
            try:
                diff = delta_diff(base_sha)  # type: ignore[arg-type]
            except ValueError as exc:
                typer.echo(f"audit-prepare: {exc}", err=True)
                raise typer.Exit(2) from exc
        else:
            diff = snapshot_seed(target, root)
            # Visible log for the fallback / forced-snapshot path.
            typer.echo(f"audit-prepare: {a} running in snapshot mode", err=True)

        wi = _build_audit_work_item(spec, diff, root)
        wi["review_mode"] = mode
        wi["base_sha"] = base_sha
        wi["base_baseline"] = base_baseline
        work_items.append(wi)

    resolved_output_dir = output_dir or ".framework/audit/latest"
    manifest = {
        "mode": "audit",
        "target": target,
        "agents_set": agents_set,
        "work_items": work_items,
        "output_dir": resolved_output_dir,
    }

    # Optional split-manifest write: in addition to the stdout manifest, write a small
    # index.json + per-item items/item-NNNN.json so the Workflow tool can be invoked with
    # a tiny args payload ({indexPath, itemsDir}) instead of a multi-MB inline manifest.
    # Mirrors the gate-prepare / tune-prepare split layout. Audit items can be agentic
    # (root_dir + tools_allowed), so per-item files carry the full audit work-item shape.
    if split_to:
        split_dir, items_dir = _prepare_split_dir(split_to)

        index_items: list[dict] = []
        for i, wi in enumerate(work_items):
            item_path = items_dir / f"item-{i:04d}.json"
            item_path.write_text(json.dumps(wi, indent=2))
            item_path.chmod(0o600)
            index_items.append(
                {
                    "i": i,
                    "agent": wi["agent"],
                    "subagent_type": wi["subagent_type"],
                    # Carry the registry model so the subscription Workflow
                    # dispatches each subagent at its intended tier (Sonnet
                    # non-agentic / Opus agentic) instead of the harness default.
                    "model": wi["model"],
                    # Per-agent audit mode metadata — the workflow's per-item
                    # dispatch reads these directly from the index entry to
                    # select the DELTA vs SNAPSHOT prompt template (it does
                    # not re-read the per-item file just for the framing).
                    "review_mode": wi.get("review_mode", "snapshot"),
                    "base_sha": wi.get("base_sha"),
                    "base_baseline": wi.get("base_baseline"),
                }
            )
        index = {
            "mode": "audit",
            "target": target,
            "agents_set": agents_set,
            "items": index_items,
            "output_dir": resolved_output_dir,
        }
        index_path = split_dir / "index.json"
        index_path.write_text(json.dumps(index, indent=2))
        index_path.chmod(0o600)

    typer.echo(json.dumps(manifest, indent=2))


def _build_audit_work_item(spec: object, diff: str, root: Path) -> dict:
    """Audit shape: one item per agent (no kind/case/repeat dimension)."""
    from framework_cli.review.decisions import (
        relevant_decisions,
        render_decisions_block,
    )

    short = spec.name.removeprefix("review-")  # type: ignore[attr-defined]
    dec_block = render_decisions_block(relevant_decisions(short, root))

    is_agentic = spec.context.strategy == "agentic"  # type: ignore[attr-defined]
    if is_agentic:
        system_blocks = [{"text": f"Review this unified diff:\n\n{diff}"}]
        if dec_block is not None:
            system_blocks.append({"text": dec_block})
        system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
        user_message = (
            f"You are reviewing the codebase rooted at: {root}\n\n"
            "Use the Read, Grep, and Glob tools (these only — do NOT use Bash, "
            "WebFetch, WebSearch, or any other tool) to explore the code as "
            "needed. Use absolute paths starting with the root above.\n\n"
            "When done, reply with ONLY a JSON array of findings:\n"
            '  [{"path": "...", "line": N, "severity": "...", "message": "...", '
            '"suggestion": "..."}]\n\n'
            "IMPORTANT: in each finding, the `path` MUST be a path RELATIVE to "
            f"the project root above (e.g. 'src/demo/foo.py'), NOT the absolute "
            "path you used for the tool call. The scoring layer matches on "
            "relative paths; absolute paths register as misses."
        )
        return {
            "agent": short,
            "kind": "current",
            "case": short,
            "repeat_idx": 0,
            "seeded_file": None,
            "subagent_type": "Explore",
            "model": spec.model,  # type: ignore[attr-defined]
            "system_blocks": system_blocks,
            "user_message": user_message,
            "tools_allowed": ["Read", "Grep", "Glob"],
            "root_dir": str(root),
            "diff": diff,
        }
    from framework_cli.review.context import assemble

    bundle = assemble(diff, root, spec.context, model=spec.model)  # type: ignore[attr-defined]
    system_blocks = [{"text": f"Review this unified diff:\n\n{bundle.diff}"}]
    if bundle.context_files:
        joined = "\n\n".join(f"=== {p} ===\n{c}" for p, c in bundle.context_files)
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system_blocks.append(
            {"text": f"Relevant repository files for context:\n\n{joined}{note}"}
        )
    if dec_block is not None:
        system_blocks.append({"text": dec_block})
    system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
    return {
        "agent": short,
        "kind": "current",
        "case": short,
        "repeat_idx": 0,
        "seeded_file": None,
        "subagent_type": "general-purpose",
        "model": spec.model,  # type: ignore[attr-defined]
        "system_blocks": system_blocks,
        "user_message": "Return your findings as a JSON array only.",
        "tools_allowed": None,
        "root_dir": str(root),
        "diff": diff,
    }


def _load_finalize_payload(results: str, command_name: str) -> tuple[list, dict]:
    """Load and validate a finalize results JSON; return (records, meta_in)."""
    try:
        payload = json.loads(Path(results).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(
            f"{command_name}: failed to load results from {results}: {exc}", err=True
        )
        raise typer.Exit(1) from exc
    if "results" not in payload:
        typer.echo(f"{command_name}: results JSON missing 'results' key", err=True)
        raise typer.Exit(1)
    return payload["results"], payload.get("meta", {})


@app.command(name="tune-finalize")
def tune_finalize(
    results: str = typer.Option(
        ..., "--results", help="Path to JSON file from the workflow."
    ),
    out_dir: str = typer.Option(
        ..., "--out-dir", help="Output dir to write artifacts."
    ),
) -> None:
    """Take the tune workflow's results, write per-call JSON records + scorecard.md
    + thresholds.proposal.yaml + apply.md + meta.json."""
    records, meta_in = _load_finalize_payload(results, "tune-finalize")
    out = Path(out_dir)
    findings_dir = out / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    _finalize_tune(records, findings_dir, out, meta_in)


@app.command(name="audit-finalize")
def audit_finalize(
    results: str = typer.Option(
        ..., "--results", help="Path to JSON file from the workflow."
    ),
    out_dir: str = typer.Option(
        ..., "--out-dir", help="Output dir to write artifacts."
    ),
    preserve_as: str | None = typer.Option(
        None,
        "--preserve-as",
        help="After writing out_dir, copy its tree into this dated baseline directory.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Required to overwrite a non-empty --preserve-as target.",
    ),
) -> None:
    """Take the audit workflow's results, write findings/<agent>.json records,
    audit-report.md (per-agent findings grouped by severity), and meta.json.

    If --preserve-as is set, also copies the out_dir tree (findings/, audit-report.md,
    meta.json) into the target directory. Refuses to overwrite a non-empty target
    without --force.
    """
    records, meta_in = _load_finalize_payload(results, "audit-finalize")
    out = Path(out_dir)
    findings_dir = out / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    _finalize_audit(records, findings_dir, out, meta_in)
    if preserve_as is not None:
        _preserve_audit_tree(out, Path(preserve_as), force=force)


def _preserve_audit_tree(src: Path, dst: Path, *, force: bool) -> None:
    """Copy the audit output tree (findings/, audit-report.md, meta.json) from
    src into dst. Refuses to overwrite a non-empty dst without force=True.

    Used by `audit-finalize --preserve-as` to snapshot a hygiene-mode audit run
    into a dated baseline directory parallel to the tune scorecards under
    `docs/superpowers/eval-scorecards/`.
    """
    import shutil

    if dst.exists() and any(dst.iterdir()):
        if not force:
            typer.echo(
                f"audit-finalize: --preserve-as target exists and is non-empty: {dst}. "
                f"Pass --force to overwrite.",
                err=True,
            )
            raise typer.Exit(2)
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in ("findings", "audit-report.md", "meta.json"):
        s = src / item
        if not s.exists():
            continue
        if s.is_dir():
            shutil.copytree(s, dst / item)
        else:
            shutil.copy2(s, dst / item)
    typer.echo(f"audit-finalize: preserved to {dst}")


@app.command(name="gate-finalize")
def gate_finalize(
    results: str = typer.Option(
        ..., "--results", help="Path to JSON file from the workflow."
    ),
    out_dir: str = typer.Option(
        ..., "--out-dir", help="Output dir to write artifacts."
    ),
) -> None:
    """Take the gate workflow's results, write per-agent records (gate mode), compute
    verdict, write marker.json.

    In gate mode, stale per-agent records under <out-dir>/findings/ are cleared
    before this run's records are written, so the verdict reflects only this run.
    Noop/regrade modes leave findings_dir alone so the regrade-against-prior-findings
    workflow continues to work.
    """
    records, meta_in = _load_finalize_payload(results, "gate-finalize")
    out = Path(out_dir)
    findings_dir = out / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    _finalize_gate(records, findings_dir, out, meta_in)


def _finalize_tune(records: list, findings_dir: Path, out: Path, meta_in: dict) -> None:
    from framework_cli.review import analyze
    from framework_cli.review.evals import load_thresholds

    for r in records:
        agent_dir = findings_dir / r["agent"] / r["kind"]
        agent_dir.mkdir(parents=True, exist_ok=True)
        case = r["case"]
        i = r["repeat_idx"]
        record = {
            "agent": r["agent"],
            "kind": r["kind"],
            "case": case,
            "repeat": i,
            "seeded_file": r.get("seeded_file"),
            "findings": r.get("findings", []),
            "usage": r.get("usage", {}),
            "latency_ms": r.get("latency_ms"),
            "stop_reason": r.get("stop_reason"),
            "raw_text": r.get("raw_text", ""),
            "turns": r.get("turns", 1),
            "tool_calls": r.get("tool_calls", []),
        }
        (agent_dir / f"{case}__r{i}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True)
        )

    # Generate scorecard.md via analyze
    loaded = analyze.load_records(findings_dir)
    thr = load_thresholds(Path("tests/eval/fixtures/thresholds.yaml"))
    scores = analyze.scorecard(loaded, thr)
    model_map: dict[str, str] = {}
    for r in loaded:
        try:
            model_map[r.agent] = get_agent(r.agent).model
        except KeyError:
            pass
    costs = analyze.cost_report(loaded, model_map)
    recall_diag = analyze.recall_diagnosis(loaded)
    fp_diag = analyze.fp_diagnosis(loaded)
    agentic = analyze.agentic_behavior(loaded)
    proposed = analyze.propose_thresholds(scores)
    md = analyze.render_markdown(
        loaded, scores, costs, recall_diag, fp_diag, agentic, proposed
    )
    (out / "scorecard.md").write_text(md)

    # Extract thresholds proposal yaml block
    in_block = False
    yaml_lines: list[str] = []
    for line in md.splitlines():
        if line.startswith("```yaml") and not in_block:
            in_block = True
            continue
        if in_block and line.startswith("```"):
            break
        if in_block:
            yaml_lines.append(line)
    (out / "thresholds.proposal.yaml").write_text("\n".join(yaml_lines) + "\n")

    # apply.md
    (out / "apply.md").write_text(_apply_md_content())

    # meta.json
    drift_detected = len(analyze.drift_check(loaded)) > 0
    meta = {
        "mode": "tune",
        "slug": meta_in.get("slug", ""),
        "repeat": meta_in.get("repeat", 1),
        "agent_count": len({r["agent"] for r in records}),
        "subagent_call_count": len(records),
        "drift_detected": drift_detected,
        "git_ref": meta_in.get("git_ref", ""),
        "model_used": meta_in.get("model_used", ""),
        "run_duration_seconds": meta_in.get("run_duration_seconds", 0),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    typer.echo(f"tune-finalize: wrote {out}")


def _finalize_audit(
    records: list, findings_dir: Path, out: Path, meta_in: dict
) -> None:
    from datetime import datetime, timezone

    from framework_cli.review import analyze

    for r in records:
        record = {
            "agent": r["agent"],
            "findings": r.get("findings", []),
            "review_mode": r.get("review_mode", "snapshot"),
            "base_sha": r.get("base_sha"),
            "base_baseline": r.get("base_baseline"),
            "usage": r.get("usage", {}),
            "latency_ms": r.get("latency_ms"),
            "stop_reason": r.get("stop_reason"),
            "raw_text": r.get("raw_text", ""),
            "turns": r.get("turns", 1),
            "tool_calls": r.get("tool_calls", []),
        }
        record_path = findings_dir / f"{r['agent']}.json"
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True))
        record_path.chmod(0o600)
    loaded = analyze.load_records(findings_dir)
    model_map: dict[str, str] = {}
    for r in loaded:
        try:
            model_map[r.agent] = get_agent(r.agent).model
        except KeyError:
            pass
    costs = analyze.cost_report(loaded, model_map)
    analyze.agentic_behavior(loaded)
    md_lines = ["# Audit report", "", "## Cost (subagent-dispatched, ~$0)", ""]
    md_lines.append("| Agent | Calls | In tok | Out tok |")
    md_lines.append("|---|---|---|---|")
    for agent in sorted(costs):
        c = costs[agent]
        md_lines.append(
            f"| review-{agent} | {c['calls']} | {c['input_tokens']} | {c['output_tokens']} |"
        )
    md_lines.append("")
    md_lines.append("## Findings")
    for r in loaded:
        md_lines.append(f"### review-{r.agent}")
        if not r.findings:
            md_lines.append("_(no findings)_")
        else:
            for f in r.findings:
                md_lines.append(
                    f"- `{f.get('path')}:{f.get('line')}` "
                    f"**{f.get('severity')}** — {f.get('message')}"
                )
        md_lines.append("")
    md_lines.append("## Drift check")
    drifts = analyze.drift_check(loaded)
    if not drifts:
        md_lines.append("_(no drift detected)_")
    else:
        for d in drifts:
            tools = ", ".join(f"{t}×{d['counts'][t]}" for t in d["disallowed_tools"])
            md_lines.append(f"- ⚠ `{d['agent']}` — disallowed tools: {tools}")
    md_lines.append("")
    from framework_cli.review.decisions import active_decision_ids

    md_lines.append(
        analyze.render_acknowledged_section(loaded, active_decision_ids(Path.cwd()))
    )
    md_lines.append("")
    (out / "audit-report.md").write_text("\n".join(md_lines) + "\n")

    # Determine current git SHA (full, not short).
    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    git_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""

    per_agent: dict[str, dict] = {}
    for r in records:
        per_agent[r["agent"]] = {
            "review_mode": r.get("review_mode", "snapshot"),
            "base_sha": r.get("base_sha"),
            "base_baseline": r.get("base_baseline"),
        }

    meta_out = {
        "target": meta_in.get("target", ""),
        "git_sha": git_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agents": [r["agent"] for r in records],
        "per_agent": per_agent,
    }
    meta_path = out / "meta.json"
    meta_path.write_text(json.dumps(meta_out, indent=2, sort_keys=True))
    meta_path.chmod(0o600)

    typer.echo(f"audit-finalize: wrote {out}")


def _finalize_gate(records: list, findings_dir: Path, out: Path, meta_in: dict) -> None:
    """Write records (if any), compute verdict, write marker.json."""
    from datetime import datetime, timezone

    from framework_cli.review import analyze
    from framework_cli.review.evals import flags
    from framework_cli.review.findings import Finding

    actual_mode = meta_in.get("mode", "gate")
    staged_hash = meta_in.get("staged_hash", "")
    agents_run = meta_in.get("agents_set", [])

    # Clear stale per-agent records from prior runs before writing this run's records.
    # Without this, analyze.load_records() below would mix old findings into the verdict —
    # surfaced as a known follow-up in CLAUDE.md and flagged by the gate's data-lineage
    # reviewer. Noop/regrade modes skip the clear so the regrade-against-prior-findings
    # workflow still works.
    if actual_mode == "gate":
        for stale in findings_dir.glob("*.json"):
            stale.unlink()
        for r in records:
            record = {
                "agent": r["agent"],
                "findings": r.get("findings", []),
                "usage": r.get("usage", {}),
                "latency_ms": r.get("latency_ms"),
                "stop_reason": r.get("stop_reason"),
                "raw_text": r.get("raw_text", ""),
                "turns": r.get("turns", 1),
                "tool_calls": r.get("tool_calls", []),
            }
            record_path = findings_dir / f"{r['agent']}.json"
            record_path.write_text(json.dumps(record, indent=2, sort_keys=True))
            record_path.chmod(0o600)

    # Load all records under findings_dir (works for regrade too).
    loaded = analyze.load_records(findings_dir)

    # Resolve active decision ids once for the integrity guard. A finding tagged
    # acknowledged: <id> is only non-blocking when <id> is an active (accepted/deferred)
    # decision; an unknown or inactive id is ignored → finding blocks normally.
    from framework_cli.review.decisions import active_decision_ids

    active_ids = active_decision_ids(Path.cwd())

    # Compute verdict: any agent's findings include a finding at/above its block_threshold?
    failing = False
    summary_parts: list[str] = []
    for r in loaded:
        try:
            spec = get_agent(r.agent)
        except KeyError:
            continue
        findings_objs = [
            Finding(
                f["path"],
                int(f["line"]),
                f["severity"],
                f["message"],
                f.get("suggestion"),
                acknowledged=f.get("acknowledged"),
                stale=f.get("stale"),
            )
            for f in r.findings
        ]
        # Advisory agents (block_threshold is None) surface findings into the
        # report but must NOT block the gate — per the flags() docstring
        # "Advisory agent ... never blocks in production". flags() itself
        # returns True on any finding for None-threshold agents (intentional
        # for eval scoring's surfacing metrics); we need to gate the gate-mode
        # FAIL on real block_threshold agents only.
        if spec.block_threshold is None:
            continue
        # Exclude findings that are acknowledged against an active decision
        # (integrity guard: only active ids exempt; unknown/inactive ids block normally).
        blocking = [
            f
            for f in findings_objs
            if not (f.acknowledged and f.acknowledged in active_ids)
        ]
        if flags(blocking, spec):
            failing = True
            summary_parts.append(f"{r.agent}:{len(blocking)}")
    drifts = analyze.drift_check(loaded)
    drift_detected = bool(drifts)
    verdict = "FAIL" if failing or drift_detected else "PASS"
    if drift_detected and not failing:
        summary_parts.append("drift")

    # marker.json lives at .framework/audit/marker.json (sibling to latest/)
    marker_path = out.parent / "marker.json"
    marker = {
        "staged_hash": staged_hash,
        "agents_run": agents_run,
        "verdict": verdict,
        "drift_detected": drift_detected,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": "; ".join(summary_parts)
        or f"{len(agents_run)} agents · 0 findings above block threshold",
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True))
    typer.echo(f"gate-finalize: verdict={verdict}, marker={marker_path}")


def _apply_md_content() -> str:
    return (
        "# Applying these threshold updates\n\n"
        "To apply the proposed values from `thresholds.proposal.yaml`:\n\n"
        "1. Diff `tests/eval/fixtures/thresholds.yaml` against `thresholds.proposal.yaml`.\n"
        "2. For each changed agent, sanity-check the new values against the observed\n"
        "   `recall` / `fp` columns in `scorecard.md`. If a number looks borderline,\n"
        "   prefer the more conservative side (lower recall_min, higher fp_max).\n"
        "3. Copy approved entries into `tests/eval/fixtures/thresholds.yaml`.\n"
        "4. Commit referencing this scorecard dir.\n\n"
        "See `scorecard.md` for the source observations and `findings/` for raw records.\n"
    )


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

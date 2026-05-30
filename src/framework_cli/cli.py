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


@app.command(name="eval-prepare")
def eval_prepare(
    mode: str = typer.Option(
        ...,
        "--mode",
        help="'tune' (against fixtures) or 'audit' (against current code).",
    ),
    agent: str = typer.Option(
        "",
        "--agent",
        help="Single agent to prepare (default: all from registry / target).",
    ),
    fixtures: str = typer.Option(
        "tests/eval/fixtures",
        "--fixtures",
        help="Fixtures root (tune mode only).",
    ),
    repeat: int = typer.Option(
        1, "--repeat", help="Repeats per fixture (tune mode only)."
    ),
    target: str = typer.Option(
        "",
        "--target",
        help="'framework' or 'project' (audit mode; default: auto-detect).",
    ),
    output_dir: str = typer.Option(
        "",
        "--output-dir",
        help="Output dir for finalize (echoed in the prep manifest).",
    ),
) -> None:
    """Output the complete work-item list for subagent dispatch as JSON to stdout.

    Consumed by the slash command, which passes it to a Workflow tool invocation.
    """
    if mode == "tune":
        _emit_tune_prep(agent, Path(fixtures), repeat, output_dir)
    elif mode == "audit":
        _emit_audit_prep(agent, target, output_dir)
    else:
        typer.echo(
            f"eval-prepare: invalid --mode '{mode}' (expected 'tune' or 'audit')",
            err=True,
        )
        raise typer.Exit(2)


def _emit_tune_prep(
    single_agent: str, fixtures_root: Path, repeat: int, output_dir: str
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
            typer.echo(f"eval-prepare: unknown agent '{a}'", err=True)
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
            '"suggestion": "..."}]'
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


def _emit_audit_prep(single_agent: str, target_arg: str, output_dir: str) -> None:
    from framework_cli.review.context import FRAMEWORK_AGENTS
    from framework_cli.source import read_batteries

    target = _detect_audit_target(target_arg)
    if target == "framework":
        all_agents = sorted(FRAMEWORK_AGENTS)
    else:
        all_agents = active_agents("pull_request", read_batteries(Path(".")))
    if single_agent:
        if single_agent not in all_agents:
            typer.echo(
                f"eval-prepare: agent '{single_agent}' not active for target '{target}'",
                err=True,
            )
            raise typer.Exit(1)
        agents_set = [single_agent]
    else:
        agents_set = all_agents

    diff = _review_diff()
    root = Path.cwd()
    work_items: list[dict] = []
    for a in agents_set:
        try:
            spec = get_agent(a)
        except KeyError:
            continue
        work_items.append(_build_audit_work_item(spec, diff, root))

    manifest = {
        "mode": "audit",
        "target": target,
        "agents_set": agents_set,
        "work_items": work_items,
        "output_dir": output_dir or ".framework/audit/latest",
    }
    typer.echo(json.dumps(manifest, indent=2))


def _build_audit_work_item(spec: object, diff: str, root: Path) -> dict:
    """Audit shape: one item per agent (no kind/case/repeat dimension)."""
    is_agentic = spec.context.strategy == "agentic"  # type: ignore[attr-defined]
    if is_agentic:
        system_blocks = [
            {"text": f"Review this unified diff:\n\n{diff}"},
            {"text": spec.prompt},  # type: ignore[attr-defined]
        ]
        user_message = (
            f"You are reviewing the codebase rooted at: {root}\n\n"
            "Use the Read, Grep, and Glob tools (these only — do NOT use Bash, "
            "WebFetch, WebSearch, or any other tool) to explore the code as "
            "needed. Use absolute paths starting with the root above.\n\n"
            "When done, reply with ONLY a JSON array of findings:\n"
            '  [{"path": "...", "line": N, "severity": "...", "message": "...", '
            '"suggestion": "..."}]'
        )
        short = spec.name.removeprefix("review-")  # type: ignore[attr-defined]
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
    system_blocks.append({"text": spec.prompt})  # type: ignore[attr-defined]
    short = spec.name.removeprefix("review-")  # type: ignore[attr-defined]
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


@app.command(name="eval-finalize")
def eval_finalize(
    mode: str = typer.Option(..., "--mode", help="'tune' or 'audit'."),
    results: str = typer.Option(
        ..., "--results", help="Path to JSON file from the workflow."
    ),
    out_dir: str = typer.Option(
        ..., "--out-dir", help="Output dir to write artifacts."
    ),
) -> None:
    """Take the workflow's results, write per-call JSON records + scorecard/audit-report
    + apply.md (tune) + meta.json."""
    payload = json.loads(Path(results).read_text())
    records = payload["results"]
    meta_in = payload.get("meta", {})
    out = Path(out_dir)
    findings_dir = out / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)

    if mode == "tune":
        _finalize_tune(records, findings_dir, out, meta_in)
    elif mode == "audit":
        _finalize_audit(records, findings_dir, out, meta_in)
    else:
        typer.echo(f"eval-finalize: invalid --mode '{mode}'", err=True)
        raise typer.Exit(2)


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
    typer.echo(f"eval-finalize: wrote {out}")


def _finalize_audit(
    records: list, findings_dir: Path, out: Path, meta_in: dict
) -> None:
    from framework_cli.review import analyze

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
        (findings_dir / f"{r['agent']}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True)
        )
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
    (out / "audit-report.md").write_text("\n".join(md_lines) + "\n")
    typer.echo(f"eval-finalize: wrote {out}")


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

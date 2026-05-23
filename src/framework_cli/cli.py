import os
from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check as check_integrity, record_drift
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.naming import derive_names
from framework_cli.review.checks import neutral_payload, post_or_skip, to_check_run
from framework_cli.review.diff import pr_diff
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import default_client, run_agent
from framework_cli.source import REPO_URL, latest_release, record_portable_source, version_tag
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
) -> None:
    """Scaffold a new project from the framework template."""
    names = derive_names(name)
    dest = Path.cwd() / names.project_slug

    if dest.exists():
        typer.echo(f"Error: {dest} already exists", err=True)
        raise typer.Exit(code=1)

    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "package_name": names.package_name,
            "python_version": python_version,
        },
    )
    write_manifest(dest, installed_framework_version())
    record_portable_source(dest, installed_framework_version())
    typer.echo(f"Created '{names.project_slug}' at {dest}")


@app.command()
def integrity(
    ci: bool = typer.Option(
        False, "--ci", help="CI mode: skip gitignored existence checks (fresh checkouts)."
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


@app.command()
def restore(
    file: str = typer.Argument(
        ..., help="Path (relative to the project root) of the framework file to restore."
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
) -> None:
    """Update a project to a newer framework version, then run its tests."""
    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)
    try:
        green = upskill_project(project)
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
def _review_diff() -> str:
    return pr_diff()


def _review_run(diff: str, spec: object) -> list:
    return run_agent(diff, spec, default_client())  # type: ignore[arg-type]


@app.command()
def review(agent: str = typer.Argument(..., help="Review agent name, e.g. 'security'.")) -> None:
    """Run a Layer-3 review agent over the PR diff and post a GitHub Check Run."""
    try:
        spec = get_agent(agent)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        payload = neutral_payload(spec.name, "review skipped — set ANTHROPIC_API_KEY to enable.")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        typer.echo(f"{spec.name}: skipped (no ANTHROPIC_API_KEY)")
        raise typer.Exit(0)

    try:
        findings = _review_run(_review_diff(), spec)
        payload = to_check_run(spec, findings)
    except Exception as exc:  # noqa: BLE001 - infra failure must not block CI
        payload = neutral_payload(spec.name, f"review could not run: {exc}")
        post_or_skip(payload, token=token, repo=repo, sha=sha)
        typer.echo(f"{spec.name}: neutral (could not run: {exc})", err=True)
        raise typer.Exit(0) from exc

    post_or_skip(payload, token=token, repo=repo, sha=sha)
    typer.echo(f"{spec.name}: {payload.conclusion} ({len(payload.annotations)} finding(s))")
    raise typer.Exit(1 if payload.conclusion == "failure" else 0)

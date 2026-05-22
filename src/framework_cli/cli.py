from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check as check_integrity, record_drift
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.naming import derive_names
from framework_cli.source import REPO_URL, latest_release, record_portable_source

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
def check() -> None:
    """Report whether a newer framework release is available."""
    current_tag = f"v{installed_framework_version()}"
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

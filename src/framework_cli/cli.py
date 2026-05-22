from pathlib import Path

import typer

from framework_cli.copier_runner import render_project
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.naming import derive_names

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
    typer.echo(f"Created '{names.project_slug}' at {dest}")

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Optional

import typer

from cli import __version__
from cli.commands.applications import apps_app
from cli.commands.auth import auth_app
from cli.commands.doctor import doctor_app
from cli.commands.interview import interview_app
from cli.commands.profile import profile_app
from cli.commands.workflow import workflow_app
from cli.context import CliContext, build_context

app = typer.Typer(
    name="applypilot",
    help="ApplyPilot CLI — manage job applications from your terminal.",
    no_args_is_help=True,
    add_completion=False,
)


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


@app.callback()
def main_callback(
    ctx: typer.Context,
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        help="ApplyPilot server URL (default from ~/.applypilot/config.toml)",
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--format",
        help="Output format: human or json",
    ),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Minimal output"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output"),
) -> None:
    """ApplyPilot command-line interface."""
    ctx.obj = build_context(
        base_url=base_url,
        output_format=output_format,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
    )


@app.command("version")
def version_cmd() -> None:
    """Print CLI version."""
    typer.echo(__version__)


app.add_typer(doctor_app, name="doctor")
app.add_typer(auth_app, name="auth")
app.add_typer(profile_app, name="profile")
app.add_typer(workflow_app, name="workflow")
app.add_typer(apps_app, name="apps")
app.add_typer(interview_app, name="interview")


def main() -> None:
    """Console entry point for setuptools."""
    app()


if __name__ == "__main__":
    main()

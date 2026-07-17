# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Optional

import typer

from cli.config import load_config, save_config
from cli.context import CliContext
from cli.output import emit

config_app = typer.Typer(help="View and edit ~/.rolemule/config.toml.")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


@config_app.callback(invoke_without_command=True)
def config_show(ctx: typer.Context) -> None:
    """Show current CLI configuration (default)."""
    if ctx.invoked_subcommand is not None:
        return
    cli_ctx: CliContext = ctx.obj
    cfg = load_config()
    payload = {
        "base_url": cfg.base_url,
        "default_format": cfg.default_format,
        "color": cfg.color,
        "poll_interval_seconds": cfg.poll_interval_seconds,
        "poll_timeout_seconds": cfg.poll_timeout_seconds,
    }
    if cli_ctx.output_format == "json":
        emit(cli_ctx, payload)
        return
    lines = [
        f"base_url: {cfg.base_url}",
        f"default_format: {cfg.default_format}",
        f"color: {cfg.color}",
        f"poll_interval_seconds: {cfg.poll_interval_seconds}",
        f"poll_timeout_seconds: {cfg.poll_timeout_seconds}",
    ]
    emit(cli_ctx, payload, human="\n".join(lines))


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Server origin URL"),
    default_format: Optional[str] = typer.Option(None, "--format", help="Default output: human or json"),
    poll_interval: Optional[int] = typer.Option(None, "--poll-interval", min=1, help="Poll interval seconds"),
    poll_timeout: Optional[int] = typer.Option(None, "--poll-timeout", min=5, help="Poll timeout seconds"),
    color: Optional[bool] = typer.Option(None, "--color/--no-color", help="Enable colored output by default"),
) -> None:
    """Update config.toml (partial patch)."""
    cli_ctx: CliContext = ctx.obj
    cfg = load_config()
    if base_url is not None:
        cfg.base_url = base_url.rstrip("/")
    if default_format is not None:
        if default_format not in ("human", "json"):
            typer.secho("format must be 'human' or 'json'", fg="red", err=True)
            raise typer.Exit(code=1)
        cfg.default_format = default_format
    if poll_interval is not None:
        cfg.poll_interval_seconds = poll_interval
    if poll_timeout is not None:
        cfg.poll_timeout_seconds = poll_timeout
    if color is not None:
        cfg.color = color

    if base_url is None and default_format is None and poll_interval is None and poll_timeout is None and color is None:
        typer.secho("Provide at least one option to set.", fg="red", err=True)
        raise typer.Exit(code=1)

    save_config(cfg)
    emit(cli_ctx, {"updated": True}, human="Configuration saved.")

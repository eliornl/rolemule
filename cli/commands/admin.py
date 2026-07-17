# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Optional

import typer

from rolemule_client.errors import ApiClientError
from cli.context import CliContext
from cli.output import emit, emit_error, require_client
from cli.util import require_confirm

admin_app = typer.Typer(help="Admin and monitoring commands (requires is_admin on your account).")
maintenance_app = typer.Typer(help="Maintenance mode control.")

admin_app.add_typer(maintenance_app, name="maintenance")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _run_admin(ctx: CliContext, action, *, human: Optional[str] = None) -> None:
    client = require_client(ctx)
    try:
        data = action(client)
    except ApiClientError as exc:
        emit_error(ctx, exc)
    emit(ctx, data, human=human or _default_human(data))


def _default_human(data: dict) -> str:
    if "enabled" in data and len(data) <= 4:
        state = "ON" if data.get("enabled") else "OFF"
        lines = [f"Maintenance mode: {state}"]
        if data.get("message"):
            lines.append(f"Message: {data['message']}")
        if data.get("estimated_end"):
            lines.append(f"Estimated end: {data['estimated_end']}")
        return "\n".join(lines)
    if "message" in data and len(data) == 1:
        return str(data["message"])
    return ""


@maintenance_app.command("show")
def maintenance_show(ctx: typer.Context) -> None:
    """Show current maintenance mode status."""
    cli_ctx: CliContext = ctx.obj
    _run_admin(cli_ctx, lambda c: c.admin.maintenance_status())


@maintenance_app.command("on")
def maintenance_on(
    ctx: typer.Context,
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Custom maintenance message"),
    estimated_end: Optional[str] = typer.Option(None, "--estimated-end", help="Estimated end time"),
    confirm: bool = typer.Option(False, "--confirm", help="Required to enable maintenance mode"),
) -> None:
    """Enable maintenance mode."""
    cli_ctx: CliContext = ctx.obj
    require_confirm(confirm, "enable maintenance mode")

    def _enable(client):
        return client.admin.set_maintenance(
            enabled=True,
            message=message,
            estimated_end=estimated_end,
        )

    _run_admin(cli_ctx, _enable)


@maintenance_app.command("off")
def maintenance_off(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Required to disable maintenance mode"),
) -> None:
    """Disable maintenance mode."""
    cli_ctx: CliContext = ctx.obj
    require_confirm(confirm, "disable maintenance mode")
    _run_admin(cli_ctx, lambda c: c.admin.clear_maintenance())


@admin_app.command("metrics")
def admin_metrics(ctx: typer.Context) -> None:
    """Show aggregate business metrics (admin only)."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.admin.metrics()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
        return

    users = data.get("users") or {}
    workflows = data.get("workflows") or {}
    apps = data.get("applications") or {}
    lines = [
        "# RoleMule metrics",
        f"Generated: {data.get('generated_at', 'N/A')}",
        "",
        "## Users",
        f"- Total: {users.get('total', 0)}",
        f"- Active (7d): {users.get('active_last_7d', 0)}",
        f"- New (30d): {users.get('new_last_30d', 0)}",
        f"- Email verified: {users.get('email_verified', 0)}",
        "",
        "## Workflows",
        f"- Total: {workflows.get('total', 0)}",
        f"- Completed: {workflows.get('completed', 0)}",
        f"- Failed: {workflows.get('failed', 0)}",
        f"- In progress: {workflows.get('in_progress', 0)}",
        f"- Success rate: {workflows.get('success_rate_pct', 0)}%",
        "",
        "## Applications",
        f"- Total: {apps.get('total', 0)}",
        f"- New (30d): {apps.get('new_last_30d', 0)}",
    ]
    emit(cli_ctx, data, human="\n".join(lines))


@admin_app.command("cache-stats")
def admin_cache_stats(ctx: typer.Context) -> None:
    """Show Redis cache statistics (admin only)."""
    cli_ctx: CliContext = ctx.obj
    _run_admin(cli_ctx, lambda c: c.admin.cache_stats())

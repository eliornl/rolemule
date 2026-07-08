# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from applypilot_client.errors import ApiClientError, ExitCode
from cli.context import CliContext
from cli.formatters.applications import format_application_show, format_applications_table, format_stats_human
from cli.output import emit, emit_error, require_client
from cli.util import filename_from_headers, require_confirm

apps_app = typer.Typer(help="List and manage job applications.")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _read_notes_text(text: Optional[str], file: Optional[str]) -> str:
    if file:
        if file == "-":
            return sys.stdin.read()
        return Path(file).read_text(encoding="utf-8")
    if text is not None:
        return text
    raise typer.BadParameter("Provide notes TEXT or --file")


@apps_app.command("list")
def apps_list(
    ctx: typer.Context,
    search: Optional[str] = typer.Option(None, "--search", help="Search title and company"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    company: Optional[str] = typer.Option(None, "--company", help="Partial company match"),
    days: Optional[int] = typer.Option(None, "--days", min=1, max=365, help="Last N days"),
    sort: Optional[str] = typer.Option(None, "--sort", help="Sort order"),
    page: int = typer.Option(1, "--page", min=1),
    per_page: int = typer.Option(20, "--per-page", min=1, max=100),
) -> None:
    """List applications with optional filters."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.applications.list(
            page=page,
            per_page=per_page,
            status_filter=status,
            days=days,
            company=company,
            search=search,
            sort=sort,
        )
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_applications_table(data))


@apps_app.command("show")
def apps_show(
    ctx: typer.Context,
    application_id: str = typer.Argument(..., help="Application UUID"),
) -> None:
    """Show one application by ID (includes workflow session link)."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.applications.get(application_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_application_show(data))


@apps_app.command("stats")
def apps_stats(ctx: typer.Context) -> None:
    """Show application funnel statistics."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.applications.stats()
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_stats_human(data))


@apps_app.command("status")
def apps_status(
    ctx: typer.Context,
    application_id: str = typer.Argument(..., help="Application UUID"),
    new_status: str = typer.Argument(..., help="New status value"),
) -> None:
    """Update an application's tracking status."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.applications.update_status(application_id, new_status)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human=f"Status updated to {new_status}.")


@apps_app.command("notes")
def apps_notes(
    ctx: typer.Context,
    application_id: str = typer.Argument(..., help="Application UUID"),
    text: Optional[str] = typer.Argument(None, help="Notes text"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Read notes from file or '-'"),
) -> None:
    """Update personal notes on an application."""
    cli_ctx: CliContext = ctx.obj
    try:
        notes = _read_notes_text(text, file)
    except typer.BadParameter as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR)) from exc

    client = require_client(cli_ctx)
    try:
        data = client.applications.update_notes(application_id, notes)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human="Notes updated.")


@apps_app.command("delete")
def apps_delete(
    ctx: typer.Context,
    application_id: str = typer.Argument(..., help="Application UUID"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Delete an application (soft delete)."""
    require_confirm(confirm, "delete this application")
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.applications.delete(application_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Application deleted."))


@apps_app.command("download")
def apps_download(
    ctx: typer.Context,
    application_id: str = typer.Argument(..., help="Application UUID"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Save report to this path"),
) -> None:
    """Download a text report for an application."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        content, headers = client.applications.download(application_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    filename = filename_from_headers(headers, "application-report.txt")
    if out is None:
        out = Path(filename)

    out.write_bytes(content)
    emit(cli_ctx, {"saved_to": str(out), "size_bytes": len(content)}, human=f"Saved to {out}")

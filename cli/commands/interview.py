# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import typer

from rolemule_client.errors import ApiClientError, ExitCode
from rolemule_client.polling import InterviewPollTimeout, wait_for_interview_prep
from cli.context import CliContext
from cli.formatters.interview import format_interview_prep
from cli.output import emit, emit_error, require_client
from cli.util import require_confirm

interview_app = typer.Typer(help="Generate and view interview preparation.")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _progress_callback(ctx: CliContext):
    def _on_progress(status: dict) -> None:
        if ctx.quiet or ctx.output_format == "json":
            return
        if status.get("is_generating"):
            typer.echo("Generating interview prep…", err=True)

    return _on_progress


@interview_app.command("show")
def interview_show(ctx: typer.Context, session_id: str) -> None:
    """Show interview preparation materials."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.interview_prep.show(session_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_interview_prep(data))


@interview_app.command("status")
def interview_status(ctx: typer.Context, session_id: str) -> None:
    """Check interview prep generation status."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.interview_prep.status(session_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, data)


@interview_app.command("generate")
def interview_generate(
    ctx: typer.Context,
    session_id: str,
    wait: bool = typer.Option(False, "--wait", help="Poll until generation completes"),
    regenerate: bool = typer.Option(False, "--regenerate", help="Regenerate existing prep"),
) -> None:
    """Generate interview prep for a workflow session."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        start = client.interview_prep.generate(session_id, regenerate=regenerate)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if start.get("status") == "exists" and not regenerate:
        if wait or cli_ctx.output_format == "json":
            try:
                data = client.interview_prep.show(session_id)
            except ApiClientError as exc:
                emit_error(cli_ctx, exc)
            if cli_ctx.output_format == "json":
                emit(cli_ctx, data)
            else:
                emit(cli_ctx, data, human=format_interview_prep(data))
            return
        emit(cli_ctx, start, human=start.get("message", "Interview prep already exists."))
        return

    if not wait:
        emit(cli_ctx, start, human=start.get("message", "Generation started."))
        return

    try:
        wait_for_interview_prep(
            lambda: client.interview_prep.status(session_id),
            interval_seconds=float(cli_ctx.config.poll_interval_seconds),
            timeout_seconds=float(cli_ctx.config.poll_timeout_seconds),
            on_progress=_progress_callback(cli_ctx),
        )
    except InterviewPollTimeout as exc:
        if exc.generation_failed:
            if cli_ctx.output_format == "json":
                emit(cli_ctx, {"error": "generation_failed", "session_id": session_id, "last_status": exc.last_status})
            else:
                typer.secho("Interview prep generation failed.", fg="red", err=True)
            raise typer.Exit(code=int(ExitCode.ERROR)) from exc
        if cli_ctx.output_format == "json":
            emit(cli_ctx, {"error": "timeout", "session_id": session_id, "last_status": exc.last_status})
        else:
            typer.secho(f"Timed out waiting for interview prep ({session_id}).", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR)) from exc

    try:
        data = client.interview_prep.show(session_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_interview_prep(data))


@interview_app.command("delete")
def interview_delete(
    ctx: typer.Context,
    session_id: str,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Delete interview prep for a session."""
    require_confirm(confirm, "delete interview prep")
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        client.interview_prep.delete(session_id)
    except ApiClientError as exc:
        emit_error(cli_ctx, exc)
    emit(cli_ctx, {"deleted": True, "session_id": session_id}, human="Interview prep deleted.")

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from rolemule_client.errors import ApiClientError, ExitCode
from rolemule_client.polling import CvPollTimeout, wait_for_cv_optimization
from cli.context import CliContext
from cli.formatters.cv import format_cv_result
from cli.output import emit, emit_error, emit_workflow_error, require_client
from cli.util import filename_from_headers, require_confirm

cv_app = typer.Typer(help="Optimize CV for a completed workflow session.")

MIN_ITERATIONS = 2
MAX_ITERATIONS = 7
MIN_THRESHOLD = 7.0
MAX_THRESHOLD = 9.5


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _progress_callback(ctx: CliContext):
    def _on_progress(status: dict) -> None:
        if ctx.quiet or ctx.output_format == "json":
            return
        score = status.get("best_score")
        running = status.get("is_running")
        if running:
            if score is not None:
                typer.echo(f"Optimizing… best score so far: {score}", err=True)
            else:
                typer.echo("CV optimization running…", err=True)

    return _on_progress


@cv_app.command("start")
def cv_start(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Workflow session ID"),
    max_iter: Optional[int] = typer.Option(None, "--max-iter", min=MIN_ITERATIONS, max=MAX_ITERATIONS),
    threshold: Optional[float] = typer.Option(None, "--threshold", min=MIN_THRESHOLD, max=MAX_THRESHOLD),
    wait: bool = typer.Option(False, "--wait", help="Poll until optimization completes"),
) -> None:
    """Start the CV optimization loop."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        start_data = client.cv_optimizer.start(
            session_id,
            max_iterations=max_iter,
            score_threshold=threshold,
        )
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    if not wait:
        emit(cli_ctx, start_data, human=start_data.get("message", "CV optimization started."))
        return

    if start_data.get("status") != "already_running":
        typer.echo(start_data.get("message", "Started."), err=True)

    try:
        wait_for_cv_optimization(
            lambda: client.cv_optimizer.status(session_id),
            interval_seconds=float(cli_ctx.config.poll_interval_seconds),
            timeout_seconds=float(cli_ctx.config.poll_timeout_seconds),
            on_progress=_progress_callback(cli_ctx),
        )
    except CvPollTimeout as exc:
        if exc.failed:
            if cli_ctx.output_format == "json":
                emit(cli_ctx, {"error": "optimization_failed", "session_id": session_id, "last_status": exc.last_status})
            else:
                typer.secho("CV optimization failed or produced no result.", fg="red", err=True)
            raise typer.Exit(code=int(ExitCode.ERROR)) from exc
        if cli_ctx.output_format == "json":
            emit(cli_ctx, {"error": "timeout", "session_id": session_id, "last_status": exc.last_status})
        else:
            typer.secho(f"Timed out waiting for CV optimization ({session_id}).", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR)) from exc

    try:
        data = client.cv_optimizer.show(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_cv_result(data))


@cv_app.command("show")
def cv_show(ctx: typer.Context, session_id: str) -> None:
    """Show the full CV optimization result."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.cv_optimizer.show(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_cv_result(data))


@cv_app.command("status")
def cv_status(ctx: typer.Context, session_id: str) -> None:
    """Check CV optimization progress."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.cv_optimizer.status(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data)


@cv_app.command("download")
def cv_download(
    ctx: typer.Context,
    session_id: str,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Save CV document to this path"),
) -> None:
    """Download the optimized CV (.odt or .docx)."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        content, headers = client.cv_optimizer.download_cv(session_id)
    except ApiClientError as exc:
        if exc.status_code == 429 or exc.error_code == "RATE_4001":
            if cli_ctx.output_format != "json":
                typer.secho(str(exc), fg="red", err=True)
                typer.secho("CV download is rate limited — try again later.", fg="yellow", err=True)
            else:
                emit_error(cli_ctx, exc)
            raise typer.Exit(code=int(ExitCode.RATE_LIMITED))
        emit_workflow_error(cli_ctx, exc)

    filename = filename_from_headers(headers, "optimized-cv.odt")
    if out is None:
        out = Path(filename)

    out.write_bytes(content)
    emit(cli_ctx, {"saved_to": str(out), "size_bytes": len(content)}, human=f"Saved to {out}")


@cv_app.command("clear")
def cv_clear(
    ctx: typer.Context,
    session_id: str,
    confirm: bool = typer.Option(False, "--confirm", help="Confirm clearing results"),
) -> None:
    """Clear CV optimization results for a session."""
    require_confirm(confirm, "clear CV optimization results")
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        client.cv_optimizer.clear(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, {"cleared": True, "session_id": session_id}, human="CV optimization cleared.")

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from rolemule_client.errors import ApiClientError, ExitCode
from rolemule_client.polling import WorkflowPollTimeout, wait_for_terminal_status
from cli.context import CliContext
from cli.formatters.workflow import VALID_SECTIONS, format_workflow_results
from cli.output import emit, emit_workflow_error, require_client
from cli.workflow_output import write_workflow_results
from cli.workflow_watch import watch_workflow_session

workflow_app = typer.Typer(help="Analyze jobs and manage workflow sessions.")
regenerate_app = typer.Typer(help="Regenerate workflow outputs.")


workflow_app.add_typer(regenerate_app, name="regenerate")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _read_job_text(source: Optional[str]) -> str:
    if source == "-":
        return sys.stdin.read()
    if source:
        return Path(source).read_text(encoding="utf-8")
    return ""


def _dashboard_url(ctx: CliContext, session_id: str, application_id: Optional[str] = None) -> str:
    if application_id:
        return f"{ctx.base_url}/applications/{application_id}"
    return f"{ctx.base_url}/applications?session={session_id}"


def _progress_callback(ctx: CliContext):
    def _on_progress(status: Dict[str, Any]) -> None:
        if ctx.quiet or ctx.output_format == "json":
            return
        pct = status.get("progress_percentage", 0)
        agent = status.get("current_agent") or status.get("status_display") or status.get("status")
        typer.echo(f"[{pct}%] {agent}", err=True)

    return _on_progress


def _finalize_analyze(
    ctx: CliContext,
    client,
    session_id: str,
    *,
    wait: bool,
    section: str,
    open_dashboard: bool,
    start_response: Optional[Dict[str, Any]] = None,
) -> None:
    cli_ctx: CliContext = ctx
    status_data: Dict[str, Any] = start_response or {"session_id": session_id}

    if wait:
        try:
            status_data = wait_for_terminal_status(
                lambda: client.workflow.get_status(session_id),
                interval_seconds=float(cli_ctx.config.poll_interval_seconds),
                timeout_seconds=float(cli_ctx.config.poll_timeout_seconds),
                on_progress=_progress_callback(cli_ctx),
            )
        except WorkflowPollTimeout as exc:
            if cli_ctx.output_format == "json":
                emit(
                    cli_ctx,
                    {
                        "error": "timeout",
                        "session_id": session_id,
                        "last_status": exc.last_status,
                    },
                )
            else:
                typer.secho(f"Timed out waiting for workflow {session_id}.", fg="red", err=True)
            raise typer.Exit(code=int(ExitCode.ERROR)) from exc

    terminal_status = status_data.get("status")
    try:
        results = client.workflow.get_results(session_id)
    except ApiClientError as exc:
        if terminal_status == "failed":
            emit(
                cli_ctx,
                {
                    "session_id": session_id,
                    "status": terminal_status,
                    "error_messages": status_data.get("error_messages") or [exc.message],
                },
                human="Workflow failed.",
            )
            raise typer.Exit(code=int(ExitCode.ERROR))
        emit_workflow_error(cli_ctx, exc)

    if open_dashboard:
        url = _dashboard_url(cli_ctx, session_id, results.get("application_id"))
        if cli_ctx.output_format != "json":
            typer.echo(f"Dashboard: {url}")

    if terminal_status == "failed":
        if cli_ctx.output_format == "json":
            emit(cli_ctx, results)
        else:
            typer.secho("Workflow failed.", fg="red", err=True)
            for msg in results.get("error_messages") or []:
                typer.echo(f"  - {msg}", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    if terminal_status == "awaiting_confirmation":
        hint = "Low match score — run: rolemule workflow continue " + session_id
        if cli_ctx.output_format == "json":
            payload = {**results, "next_step": hint}
            emit(cli_ctx, payload)
        else:
            emit(cli_ctx, results, human=format_workflow_results(results, section))
            typer.secho(hint, fg="yellow")
        return

    if terminal_status == "analysis_complete":
        hint = "Run: rolemule workflow generate-documents " + session_id
        if cli_ctx.output_format == "json":
            payload = {**results, "next_step": hint}
            emit(cli_ctx, payload)
        else:
            emit(cli_ctx, results, human=format_workflow_results(results, section))
            typer.secho(hint, fg="yellow")
        return

    if cli_ctx.output_format == "json":
        emit(cli_ctx, results)
    else:
        emit(cli_ctx, results, human=format_workflow_results(results, section))


@workflow_app.command("analyze")
def workflow_analyze(
    ctx: typer.Context,
    input_source: Optional[str] = typer.Argument(
        None,
        help="Job description file path, or '-' for stdin",
    ),
    upload: Optional[Path] = typer.Option(None, "--upload", help="Upload .pdf, .txt, or .docx"),
    url: Optional[str] = typer.Option(None, "--url", help="Posting URL (metadata only)"),
    source_url: Optional[str] = typer.Option(None, "--source-url", help="Source page URL"),
    title: Optional[str] = typer.Option(None, "--title", help="Detected job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Detected company name"),
    wait: bool = typer.Option(False, "--wait", help="Poll until a terminal workflow status"),
    section: str = typer.Option("all", "--section", help="Human output section filter"),
    open_dashboard: bool = typer.Option(False, "--open", help="Print dashboard URL"),
) -> None:
    """Start job analysis from text, file, or upload."""
    cli_ctx: CliContext = ctx.obj
    if section not in VALID_SECTIONS:
        typer.secho(
            f"Invalid --section {section!r}. Choose from: {', '.join(sorted(VALID_SECTIONS))}",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    job_text: Optional[str] = None
    job_file: Optional[str] = None

    if upload:
        job_file = str(upload)
    elif input_source:
        job_text = _read_job_text(input_source)
    elif url or source_url:
        pass
    else:
        typer.secho(
            "Provide job text (FILE or '-'), --upload, or --url.",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=int(ExitCode.ERROR))

    try:
        start_data = client.workflow.start(
            job_text=job_text,
            job_file=job_file,
            job_url=url,
            source_url=source_url,
            detected_title=title,
            detected_company=company,
        )
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    session_id = str(start_data.get("session_id") or "")
    if not session_id:
        emit(cli_ctx, start_data)
        return

    if not wait:
        if cli_ctx.output_format == "json":
            emit(cli_ctx, start_data)
        else:
            typer.echo(f"Started workflow {session_id}. Check status with: rolemule workflow status {session_id}")
        if open_dashboard:
            typer.echo(f"Dashboard: {_dashboard_url(cli_ctx, session_id)}")
        return

    _finalize_analyze(
        cli_ctx,
        client,
        session_id,
        wait=True,
        section=section,
        open_dashboard=open_dashboard,
        start_response=start_data,
    )


@workflow_app.command("status")
def workflow_status(ctx: typer.Context, session_id: str) -> None:
    """Get workflow status."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.get_status(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data)


@workflow_app.command("results")
def workflow_results(
    ctx: typer.Context,
    session_id: str,
    section: str = typer.Option("all", "--section", help="Human output section filter"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write results to this file"),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", help="Write section files into this directory"),
) -> None:
    """Get workflow results."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.get_results(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    as_json = cli_ctx.output_format == "json"
    if out is not None and out_dir is not None:
        typer.secho("Use only one of --out or --out-dir.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.ERROR))

    if out is not None or out_dir is not None:
        summary = write_workflow_results(
            data,
            section=section,
            out=out,
            out_dir=out_dir,
            as_json=as_json,
        )
        emit(cli_ctx, {**data, **summary}, human=f"Saved: {summary.get('saved_to')}")
        return

    if as_json:
        emit(cli_ctx, data)
    else:
        emit(cli_ctx, data, human=format_workflow_results(data, section))


@workflow_app.command("history")
def workflow_history(
    ctx: typer.Context,
    page: int = typer.Option(1, "--page", min=1),
    per_page: int = typer.Option(10, "--per-page", min=1, max=100),
    status_filter: Optional[str] = typer.Option(None, "--status"),
    sort: Optional[str] = typer.Option(None, "--sort"),
) -> None:
    """List past workflow sessions."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.history(
            page=page,
            per_page=per_page,
            status_filter=status_filter,
            sort=sort,
        )
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data)


@workflow_app.command("continue")
def workflow_continue(
    ctx: typer.Context,
    session_id: str,
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt"),
) -> None:
    """Continue workflow after a low match-score gate."""
    cli_ctx: CliContext = ctx.obj
    if cli_ctx.output_format == "human" and not confirm:
        if not typer.confirm(f"Continue workflow {session_id} despite low match score?"):
            raise typer.Exit(code=int(ExitCode.ERROR))

    client = require_client(cli_ctx)
    try:
        data = client.workflow.continue_workflow(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Workflow resumed."))


@workflow_app.command("generate-documents")
def workflow_generate_documents(ctx: typer.Context, session_id: str) -> None:
    """Generate cover letter and resume recommendations."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.generate_documents(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Document generation started."))


@regenerate_app.command("cover-letter")
def regenerate_cover_letter(ctx: typer.Context, session_id: str) -> None:
    """Regenerate the cover letter."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.regenerate_cover_letter(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Cover letter regenerated."))


@regenerate_app.command("resume")
def regenerate_resume(ctx: typer.Context, session_id: str) -> None:
    """Regenerate resume recommendations."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.regenerate_resume(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Resume recommendations regenerated."))


@workflow_app.command("generate-interview-prep")
def workflow_generate_interview_prep(ctx: typer.Context, session_id: str) -> None:
    """Generate interview prep (legacy — prefer rolemule interview generate)."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.workflow.generate_interview_prep(session_id)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)
    emit(cli_ctx, data, human=data.get("message", "Interview prep generation started."))


@workflow_app.command("watch")
def workflow_watch(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Workflow session UUID"),
) -> None:
    """Stream workflow progress over WebSocket until completion or error."""
    cli_ctx: CliContext = ctx.obj
    if not cli_ctx.access_token:
        typer.secho("Not logged in.", fg="red", err=True)
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))

    watch_workflow_session(
        base_url=cli_ctx.base_url,
        access_token=cli_ctx.access_token,
        session_id=session_id,
        quiet=cli_ctx.quiet,
        human=cli_ctx.output_format != "json",
    )

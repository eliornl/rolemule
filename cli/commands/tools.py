# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import typer

from applypilot_client.errors import ApiClientError
from cli.context import CliContext
from cli.formatters.tools import format_tool_result
from cli.output import emit, emit_workflow_error, require_client
from cli.tool_schemas import TOOL_SCHEMAS
from cli.util import payload_from_file

tools_app = typer.Typer(help="Career tools — emails, salary coach, job comparison, and more.")
schema_app = typer.Typer(help="Print example JSON request bodies for career tools.")

tools_app.add_typer(schema_app, name="schema")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _split_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    items = [part.strip() for part in value.split(",") if part.strip()]
    return items or None


def _resolve_payload(
    file: Optional[str],
    build_from_flags: Callable[[], Dict[str, Any]],
    *,
    hint: str,
) -> Dict[str, Any]:
    if file:
        return payload_from_file(file)
    payload = build_from_flags()
    if not payload:
        raise typer.BadParameter(hint)
    return payload


def _emit_tool_result(ctx: CliContext, tool: str, data: Dict[str, Any]) -> None:
    human = format_tool_result(tool, data)
    emit(ctx, data, human=human)


def _run_tool(
    ctx: CliContext,
    tool: str,
    payload: Dict[str, Any],
    api_call: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    client = require_client(ctx)
    try:
        data = api_call(payload)
    except ApiClientError as exc:
        emit_workflow_error(ctx, exc)
    _emit_tool_result(ctx, tool, data)


@tools_app.command("followup-stages")
def followup_stages(ctx: typer.Context) -> None:
    """List valid follow-up email stages."""
    cli_ctx: CliContext = ctx.obj
    client = require_client(cli_ctx)
    try:
        data = client.tools.followup_stages()
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    if cli_ctx.output_format == "json":
        emit(cli_ctx, data)
        return

    stages = data.get("stages") or []
    lines = ["Follow-up stages:"]
    for stage in stages:
        if isinstance(stage, dict):
            lines.append(f"- {stage.get('value', '?')}: {stage.get('label', '')}")
        else:
            lines.append(f"- {stage}")
    emit(cli_ctx, data, human="\n".join(lines))


@tools_app.command("thank-you")
def thank_you(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
    application_id: Optional[str] = typer.Option(None, "--application-id", help="Application UUID"),
    interviewer: Optional[str] = typer.Option(None, "--interviewer", help="Interviewer name"),
    interview_type: Optional[str] = typer.Option(None, "--interview-type", help="Interview type (e.g. video)"),
    company: Optional[str] = typer.Option(None, "--company", help="Company name"),
    title: Optional[str] = typer.Option(None, "--title", help="Job title"),
    highlights: Optional[str] = typer.Option(None, "--highlights", help="Comma-separated discussion highlights"),
) -> None:
    """Generate a post-interview thank-you email."""
    cli_ctx: CliContext = ctx.obj

    def _build() -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if application_id:
            payload["application_id"] = application_id
        if interviewer:
            payload["interviewer_name"] = interviewer
        if interview_type:
            payload["interview_type"] = interview_type
        if company:
            payload["company_name"] = company
        if title:
            payload["job_title"] = title
        points = _split_list(highlights)
        if points:
            payload["key_discussion_points"] = points
        if not file and not application_id:
            if not interviewer or not interview_type:
                return {}
            if not company or not title:
                return {}
        return payload

    payload = _resolve_payload(
        file,
        _build,
        hint="Provide --file or (--interviewer, --interview-type, --company, --title). "
        "Use --application-id to pull context from an existing application.",
    )
    _run_tool(cli_ctx, "thank-you", payload, require_client(cli_ctx).tools.thank_you)


@tools_app.command("followup")
def followup(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
    stage: Optional[str] = typer.Option(None, "--stage", help="Follow-up stage (see followup-stages)"),
    company: Optional[str] = typer.Option(None, "--company", help="Company name"),
    title: Optional[str] = typer.Option(None, "--title", help="Job title"),
    contact: Optional[str] = typer.Option(None, "--contact", help="Contact name"),
    days: Optional[int] = typer.Option(None, "--days", help="Days since last contact"),
    application_id: Optional[str] = typer.Option(None, "--application-id", help="Application UUID"),
) -> None:
    """Generate a follow-up email for an application stage."""
    cli_ctx: CliContext = ctx.obj

    def _build() -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if application_id:
            payload["application_id"] = application_id
        if stage:
            payload["stage"] = stage
        if company:
            payload["company_name"] = company
        if title:
            payload["job_title"] = title
        if contact:
            payload["contact_name"] = contact
        if days is not None:
            payload["days_since_contact"] = days
        if not file and not application_id and (not stage or not company or not title):
            return {}
        return payload

    payload = _resolve_payload(
        file,
        _build,
        hint="Provide --file or (--stage, --company, --title). "
        "Use --application-id to pull context from an existing application.",
    )
    _run_tool(cli_ctx, "followup", payload, require_client(cli_ctx).tools.followup)


@tools_app.command("salary-coach")
def salary_coach(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
    title: Optional[str] = typer.Option(None, "--title", help="Job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Company name"),
    offered: Optional[str] = typer.Option(None, "--offered", help="Offered salary (e.g. $155,000)"),
    target: Optional[str] = typer.Option(None, "--target", help="Target salary range"),
) -> None:
    """Get salary negotiation coaching for an offer."""
    cli_ctx: CliContext = ctx.obj

    def _build() -> Dict[str, Any]:
        if not title or not company or not offered:
            return {}
        payload: Dict[str, Any] = {
            "job_title": title,
            "company_name": company,
            "offered_salary": offered,
        }
        if target:
            payload["target_range"] = target
        return payload

    payload = _resolve_payload(
        file,
        _build,
        hint="Provide --file or (--title, --company, --offered).",
    )
    _run_tool(cli_ctx, "salary-coach", payload, require_client(cli_ctx).tools.salary_coach)


@tools_app.command("rejection-analysis")
def rejection_analysis(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
    email: Optional[str] = typer.Option(None, "--email", help="Rejection email text"),
    title: Optional[str] = typer.Option(None, "--title", help="Job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Company name"),
) -> None:
    """Analyze a rejection email and suggest improvements."""
    cli_ctx: CliContext = ctx.obj

    def _build() -> Dict[str, Any]:
        if not email:
            return {}
        payload: Dict[str, Any] = {"rejection_email": email}
        if title:
            payload["job_title"] = title
        if company:
            payload["company_name"] = company
        return payload

    payload = _resolve_payload(
        file,
        _build,
        hint="Provide --file or --email with the rejection message text.",
    )
    _run_tool(cli_ctx, "rejection-analysis", payload, require_client(cli_ctx).tools.rejection_analysis)


@tools_app.command("reference-request")
def reference_request(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
    name: Optional[str] = typer.Option(None, "--name", help="Reference contact name"),
    relationship: Optional[str] = typer.Option(None, "--relationship", help="Your relationship to the reference"),
    title: Optional[str] = typer.Option(None, "--title", help="Target job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Target company"),
) -> None:
    """Draft a reference request email."""
    cli_ctx: CliContext = ctx.obj

    def _build() -> Dict[str, Any]:
        if not name or not relationship:
            return {}
        payload: Dict[str, Any] = {
            "reference_name": name,
            "reference_relationship": relationship,
        }
        if title:
            payload["target_job_title"] = title
        if company:
            payload["target_company"] = company
        return payload

    payload = _resolve_payload(
        file,
        _build,
        hint="Provide --file or (--name, --relationship).",
    )
    _run_tool(cli_ctx, "reference-request", payload, require_client(cli_ctx).tools.reference_request)


@tools_app.command("job-comparison")
def job_comparison(
    ctx: typer.Context,
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request file (or - for stdin)"),
) -> None:
    """Compare multiple job offers side by side."""
    cli_ctx: CliContext = ctx.obj
    if not file:
        raise typer.BadParameter("Provide --file with a JSON request (see: applypilot tools schema job-comparison).")
    payload = payload_from_file(file)
    _run_tool(cli_ctx, "job-comparison", payload, require_client(cli_ctx).tools.job_comparison)


def _schema_command(tool_key: str) -> Callable[[typer.Context], None]:
    def _cmd(ctx: typer.Context) -> None:
        cli_ctx: CliContext = ctx.obj
        example = TOOL_SCHEMAS[tool_key]
        emit(cli_ctx, example, human=json.dumps(example, indent=2))

    _cmd.__doc__ = f"Print example JSON for {tool_key}."
    return _cmd


for _tool_key in TOOL_SCHEMAS:
    schema_app.command(name=_tool_key, help=f"Example JSON request for {_tool_key}.")(
        _schema_command(_tool_key)
    )

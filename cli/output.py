# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import typer

from rolemule_client.client import RoleMuleClient
from rolemule_client.errors import ApiClientError, ExitCode
from cli.config import Credentials, load_credentials, save_credentials
from cli.context import CliContext


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def emit(ctx: CliContext, data: Any, *, human: Optional[str] = None) -> None:
    """Print JSON or human-readable output."""
    if ctx.output_format == "json":
        typer.echo(json.dumps(data, indent=2, default=str))
    elif human is not None:
        from cli.pager import maybe_page

        maybe_page(human, no_pager=ctx.no_pager, quiet=ctx.quiet)


def emit_error(ctx: CliContext, exc: ApiClientError) -> None:
    """Print API error and exit with mapped code."""
    if ctx.output_format == "json":
        payload = {
            "success": False,
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "request_id": exc.request_id,
        }
        typer.echo(json.dumps({k: v for k, v in payload.items() if v is not None}, indent=2))
    else:
        typer.secho(str(exc), fg="red", err=True)
    raise typer.Exit(code=int(exc.exit_code))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_auth_response(data: Dict[str, Any], email_hint: Optional[str] = None) -> None:
    """Save credentials when response includes access_token."""
    token = data.get("access_token")
    if not token:
        return
    user = data.get("user") or {}
    email = email_hint or user.get("email") or data.get("email")
    save_credentials(
        Credentials(
            access_token=str(token),
            email=str(email) if email else None,
            saved_at=_now_iso(),
        )
    )


def make_client(ctx: CliContext) -> RoleMuleClient:
    """Build API client with token refresh persistence."""

    def _on_refresh(token: str) -> None:
        existing = load_credentials()
        save_credentials(
            Credentials(
                access_token=token,
                email=existing.email if existing else (ctx.credentials.email if ctx.credentials else None),
                saved_at=_now_iso(),
            )
        )

    return RoleMuleClient(
        ctx.base_url,
        access_token=ctx.access_token,
        on_token_refreshed=_on_refresh,
    )


def require_client(ctx: CliContext) -> RoleMuleClient:
    """Return an authenticated client or exit with AUTH_OR_PROFILE."""
    if not ctx.access_token:
        emit(
            ctx,
            {"authenticated": False, "message": "Not logged in. Run: rolemule auth login"},
            human="Not logged in. Run: rolemule auth login",
        )
        raise typer.Exit(code=int(ExitCode.AUTH_OR_PROFILE))
    return make_client(ctx)


def _detail_ids(details: Optional[list]) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for item in details or []:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if field in ("application_id", "session_id") and item.get("message"):
            ids[str(field)] = str(item["message"])
    return ids


def emit_duplicate_application(ctx: CliContext, exc: ApiClientError) -> None:
    """Emit RES_3002 duplicate warning and exit 0."""
    ids = _detail_ids(exc.details)
    payload: Dict[str, Any] = {
        "warning": True,
        "error_code": exc.error_code,
        "message": exc.message,
        **ids,
    }
    if ctx.output_format == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        typer.secho(f"Warning: {exc.message}", fg="yellow", err=True)
        if ids.get("application_id"):
            typer.echo(f"Existing application: {ids['application_id']}")
        if ids.get("session_id"):
            typer.echo(f"Existing session: {ids['session_id']}")
    raise typer.Exit(code=int(ExitCode.SUCCESS))


def emit_workflow_error(ctx: CliContext, exc: ApiClientError) -> None:
    """Handle workflow-specific API errors before generic emit_error."""
    if exc.error_code == "RES_3002":
        emit_duplicate_application(ctx, exc)
    if exc.error_code == "CFG_6001":
        hint = (
            "Configure AI: rolemule profile api-key set --provider gemini "
            "(or openai/anthropic), or set preferred_provider=ollama / USE_VERTEX_AI"
        )
        if ctx.output_format == "json":
            payload = {
                "success": False,
                "error_code": exc.error_code,
                "message": exc.message,
                "hint": hint,
                "details": exc.details,
            }
            typer.echo(json.dumps({k: v for k, v in payload.items() if v is not None}, indent=2))
        else:
            typer.secho(f"{exc.message}", fg="red", err=True)
            typer.secho(hint, fg="yellow", err=True)
        raise typer.Exit(code=int(exc.exit_code))
    emit_error(ctx, exc)

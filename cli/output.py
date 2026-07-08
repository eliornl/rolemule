# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import typer

from applypilot_client.client import ApplyPilotClient
from applypilot_client.errors import ApiClientError, ExitCode
from cli.config import Credentials, clear_credentials, load_credentials, mask_token, save_credentials
from cli.context import CliContext


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def emit(ctx: CliContext, data: Any, *, human: Optional[str] = None) -> None:
    """Print JSON or human-readable output."""
    if ctx.output_format == "json":
        typer.echo(json.dumps(data, indent=2, default=str))
    elif human is not None:
        typer.echo(human)


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


def make_client(ctx: CliContext) -> ApplyPilotClient:
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

    return ApplyPilotClient(
        ctx.base_url,
        access_token=ctx.access_token,
        on_token_refreshed=_on_refresh,
    )

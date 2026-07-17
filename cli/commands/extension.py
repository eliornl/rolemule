# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Optional

import typer

from rolemule_client.errors import ApiClientError
from cli.context import CliContext
from cli.formatters.extension import format_autofill_map
from cli.output import emit, emit_workflow_error, require_client
from cli.util import payload_from_file

extension_app = typer.Typer(
    help="Chrome extension helpers (advanced — for autofill testing without the browser).",
)
autofill_app = typer.Typer(help="Test autofill field mapping against your profile.")

extension_app.add_typer(autofill_app, name="autofill")


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


@autofill_app.command("map")
def autofill_map(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", "-f", help="JSON with page_url and fields (or - for stdin)"),
    url: Optional[str] = typer.Option(None, "--url", help="Override page_url from the JSON file"),
) -> None:
    """
    Map form fields to profile values (same API the Chrome extension uses).

    Requires a complete profile. Intended for extension development and testing —
    most users should use the browser extension instead.
    """
    cli_ctx: CliContext = ctx.obj
    payload = payload_from_file(file)
    if url:
        payload["page_url"] = url
    if not payload.get("page_url"):
        raise typer.BadParameter("JSON must include page_url (or pass --url).")
    if not payload.get("fields"):
        raise typer.BadParameter("JSON must include a non-empty fields array.")

    client = require_client(cli_ctx)
    try:
        data = client.extension.autofill_map(payload)
    except ApiClientError as exc:
        emit_workflow_error(cli_ctx, exc)

    human = format_autofill_map(data) if cli_ctx.output_format != "json" else None
    emit(cli_ctx, data, human=human)

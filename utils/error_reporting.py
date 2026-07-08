"""
utils/error_reporting.py — Google Cloud Error Reporting integration.

Wraps the google-cloud-error-reporting client with:
  • Graceful degradation when the package isn't installed (dev machines)
  • Production-only reporting (no noise during local development)
  • Async-safe: reporting is fire-and-forget via asyncio.create_task()
  • User context attached to every report for faster triage

Usage:
    from utils.error_reporting import report_exception

    await report_exception(exc, request=request, user_id="usr_123")

Cloud Error Reporting automatically groups similar tracebacks, sends email
alerts on new error types, and links to Cloud Logging for full context.
No Sentry account required — it runs entirely within GCP.
"""

import asyncio
import logging
import traceback
from typing import Optional

from fastapi import Request

from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import — degrades gracefully if package is not installed
# ---------------------------------------------------------------------------
try:
    from google.cloud import error_reporting as _gcp_error_reporting  # type: ignore
    _CLIENT_AVAILABLE = True
except ImportError:
    _gcp_error_reporting = None  # type: ignore
    _CLIENT_AVAILABLE = False

# Lazily-initialised client (one instance per process)
_client: Optional[object] = None
_client_lookup_done: bool = False


def _get_client() -> Optional[object]:
    """Return the Error Reporting client, initialising it on first call."""
    global _client, _client_lookup_done
    if _client_lookup_done:
        return _client

    _client_lookup_done = True
    _client = None

    if not _CLIENT_AVAILABLE:
        return _client

    try:
        _client = _gcp_error_reporting.Client()
        logger.info("Google Cloud Error Reporting client initialised")
    except Exception as exc:
        logger.warning("Could not initialise Cloud Error Reporting: %s", sanitize_log_value(str(exc)))
        _client = None

    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def report_exception(
    exc: BaseException,
    *,
    request: Optional[Request] = None,
    user_id: Optional[str] = None,
) -> None:
    """Report an exception to Google Cloud Error Reporting.

    Fire-and-forget: schedules the blocking gRPC call in the executor so it
    never delays the HTTP response.  Silently swallows all errors so a
    reporting failure never masks the original exception.
    """
    from config.settings import get_settings
    settings = get_settings()

    if not settings.is_production:
        return  # Skip reporting outside production to reduce noise

    client = _get_client()
    if client is None:
        return

    http_context = None
    if request is not None and _CLIENT_AVAILABLE:
        try:
            http_context = _gcp_error_reporting.HTTPContext(
                method=request.method,
                url=str(request.url),
                user_agent=request.headers.get("user-agent", ""),
                referrer=request.headers.get("referer", ""),
                response_status_code=500,
                remote_ip=request.client.host if request.client else "",
            )
        except Exception as http_err:
            logger.debug(
                "Could not build HTTP context for error reporting: %s",
                sanitize_log_value(str(http_err)),
                exc_info=True,
            )
            http_context = None

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def _report() -> None:
        try:
            client.report(  # type: ignore[union-attr]
                message=tb,
                http_context=http_context,
                user=user_id or "",
            )
        except Exception as report_exc:
            logger.debug("Error Reporting submission failed: %s", sanitize_log_value(str(report_exc)))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _report)

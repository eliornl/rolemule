"""
Request middleware for the ApplyPilot.
Provides request ID generation, logging, and performance tracking.
"""

import logging
import re
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from utils.logging_config import (
    generate_request_id,
    set_request_context,
    clear_request_context,
    get_structured_logger,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

_NEWLINE_RE = re.compile(r"[\r\n\x00]")


def _sanitize_log_value(value: str) -> str:
    """Strip CR/LF/NUL characters to prevent log-injection attacks."""
    return _NEWLINE_RE.sub(" ", value)

# Request ID header name
REQUEST_ID_HEADER = "X-Request-ID"

# Paths to exclude from detailed logging (health checks, static files)
EXCLUDE_PATHS = {
    "/health",
    "/favicon.ico",
    "/static",
}


# =============================================================================
# REQUEST LOGGING MIDDLEWARE
# =============================================================================


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds request ID tracking and logging for all HTTP requests.

    Features:
    - Generates unique request ID for each request
    - Logs request start and completion with timing
    - Adds request ID to response headers for client-side correlation
    - Sets logging context for downstream components
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request with logging and timing."""
        # Check if request should be excluded from detailed logging
        path = request.url.path
        exclude = any(path.startswith(excluded) for excluded in EXCLUDE_PATHS)

        # Generate or extract request ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or generate_request_id()

        # Store request_id on request.state for access in other parts of the application
        request.state.request_id = request_id

        # Extract user ID from request state if available (set by auth middleware)
        user_id = None
        if hasattr(request.state, "user"):
            user_id = getattr(request.state.user, "id", None) or request.state.user.get(
                "id"
            )

        # Set logging context (also stores in context var for error responses)
        tokens = set_request_context(
            request_id=request_id,
            user_id=str(user_id) if user_id else None,
        )

        # Start timing
        start_time = perf_counter()

        # Log request start (only at DEBUG level — avoids noise at INFO)
        if not exclude:
            query = f"?{_sanitize_log_value(str(request.query_params))}" if request.query_params else ""
            client_ip = _sanitize_log_value(
                request.client.host if request.client else "unknown"
            )
            logger.debug(
                f">> {request.method} {path}{query}  ip={client_ip}",
                extra={
                    "method": request.method,
                    "path": path,
                    "query_params": _sanitize_log_value(str(request.query_params)),
                    "client_ip": client_ip,
                },
            )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (perf_counter() - start_time) * 1000

            # Add request ID to response headers
            response.headers[REQUEST_ID_HEADER] = request_id

            # Log request completion (skip for excluded paths)
            if not exclude:
                status = response.status_code
                if status >= 500:
                    log_level = logging.ERROR
                elif status >= 400:
                    log_level = logging.WARNING
                else:
                    log_level = logging.INFO

                # Include user context and query string on non-2xx for easier debugging
                extra_context = ""
                if status >= 400 and request.query_params:
                    safe_params = {k: _sanitize_log_value(str(v)) for k, v in request.query_params.items()}
                    extra_context = f"  params={safe_params}"
                if user_id:
                    extra_context += f"  user={str(user_id)[:8]}..."

                logger.log(
                    log_level,
                    f"{request.method} {path} -> {status}  ({duration_ms:.0f}ms){extra_context}",
                    extra={
                        "method": request.method,
                        "path": path,
                        "status_code": status,
                        "duration_ms": duration_ms,
                    },
                )

            return response

        except Exception as e:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error(
                f"UNHANDLED {request.method} {path}  ({duration_ms:.0f}ms)"
                f"  {type(e).__name__}: {e}",
                extra={
                    "method": request.method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

        finally:
            # Clear logging context
            clear_request_context(tokens)


# =============================================================================
# SLOW REQUEST WARNING MIDDLEWARE
# =============================================================================


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs warnings for slow requests.
    Useful for identifying performance bottlenecks.
    """

    def __init__(self, app, threshold_ms: float = 5000.0):
        """
        Initialize slow request middleware.

        Args:
            app: FastAPI application
            threshold_ms: Threshold in milliseconds for slow request warning
        """
        super().__init__(app)
        self.threshold_ms = threshold_ms

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check request duration and log if slow."""
        start_time = perf_counter()

        response = await call_next(request)

        duration_ms = (perf_counter() - start_time) * 1000

        if duration_ms > self.threshold_ms:
            logger.warning(
                f"SLOW  {request.method} {request.url.path}"
                f"  {duration_ms:.0f}ms  (threshold {self.threshold_ms:.0f}ms)",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "threshold_ms": self.threshold_ms,
                },
            )

        return response


# =============================================================================
# REQUEST CONTEXT UTILITIES
# =============================================================================


def get_request_id(request: Request) -> str:
    """
    Get request ID from request headers or generate a new one.

    Args:
        request: FastAPI request object

    Returns:
        Request ID string
    """
    return request.headers.get(REQUEST_ID_HEADER) or generate_request_id()


def add_request_id_header(response: Response, request_id: str) -> Response:
    """
    Add request ID header to response.

    Args:
        response: FastAPI response object
        request_id: Request ID to add

    Returns:
        Response with request ID header
    """
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


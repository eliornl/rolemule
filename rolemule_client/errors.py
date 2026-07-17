# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional


class ExitCode(IntEnum):
    """CLI process exit codes (see docs/cli-implementation-plan.md)."""

    SUCCESS = 0
    ERROR = 1
    AUTH_OR_PROFILE = 2
    RATE_LIMITED = 3
    CONFIG = 4


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


@dataclass
class ApiClientError(Exception):
    """Raised when the RoleMule API returns an error response."""

    message: str
    status_code: int
    error_code: Optional[str] = None
    details: Optional[List[Dict[str, Any]]] = None
    request_id: Optional[str] = None
    exit_code: ExitCode = ExitCode.ERROR
    raw: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [self.message]
        if self.error_code:
            parts.append(f"({self.error_code})")
        return " ".join(parts)


def parse_error_response(status_code: int, body: Any) -> ApiClientError:
    """
    Parse a failed HTTP response body into ApiClientError.

    Args:
        status_code: HTTP status code
        body: Parsed JSON dict or raw string

    Returns:
        ApiClientError with mapped exit code
    """
    if not isinstance(body, dict):
        return ApiClientError(
            message=str(body) if body else f"HTTP {status_code}",
            status_code=status_code,
        )

    error_code = body.get("error_code")
    message = body.get("message") or f"HTTP {status_code}"
    details = body.get("details")
    request_id = body.get("request_id")

    exit_code = _exit_code_for(status_code, error_code)

    return ApiClientError(
        message=message,
        status_code=status_code,
        error_code=error_code,
        details=details if isinstance(details, list) else None,
        request_id=request_id,
        exit_code=exit_code,
        raw=body,
    )


def _exit_code_for(status_code: int, error_code: Optional[str]) -> ExitCode:
    if error_code == "RATE_4001" or status_code == 429:
        return ExitCode.RATE_LIMITED
    if status_code in (401, 403):
        return ExitCode.AUTH_OR_PROFILE
    return ExitCode.ERROR

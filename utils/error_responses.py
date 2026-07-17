"""
Standardized error responses for the RoleMule.
Provides consistent error format across all API endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.logging_config import request_id_var


# =============================================================================
# ERROR CODES
# =============================================================================


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""

    # Authentication errors (1xxx)
    AUTH_INVALID_CREDENTIALS = "AUTH_1001"
    AUTH_TOKEN_EXPIRED = "AUTH_1002"
    AUTH_TOKEN_INVALID = "AUTH_1003"
    AUTH_ACCOUNT_LOCKED = "AUTH_1004"
    AUTH_UNAUTHORIZED = "AUTH_1005"
    AUTH_FORBIDDEN = "AUTH_1006"

    # Validation errors (2xxx)
    VALIDATION_ERROR = "VAL_2001"
    VALIDATION_MISSING_FIELD = "VAL_2002"
    VALIDATION_INVALID_FORMAT = "VAL_2003"

    # Resource errors (3xxx)
    RESOURCE_NOT_FOUND = "RES_3001"
    RESOURCE_ALREADY_EXISTS = "RES_3002"
    RESOURCE_CONFLICT = "RES_3003"

    # Rate limiting (4xxx)
    RATE_LIMIT_EXCEEDED = "RATE_4001"
    TOO_MANY_CONNECTIONS = "RATE_4002"

    # External service errors (5xxx)
    EXTERNAL_SERVICE_ERROR = "EXT_5001"
    LLM_SERVICE_ERROR = "EXT_5002"
    DATABASE_ERROR = "EXT_5003"
    CACHE_ERROR = "EXT_5004"

    # Configuration errors (6xxx)
    NO_API_KEY = "CFG_6001"

    # Not implemented (9xxx)
    NOT_IMPLEMENTED = "INT_9002"

    # Internal errors (9xxx)
    INTERNAL_ERROR = "INT_9001"
    UNKNOWN_ERROR = "INT_9999"


# =============================================================================
# ERROR RESPONSE MODELS
# =============================================================================


class ErrorDetail(BaseModel):
    """Detailed error information."""

    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Specific error code for this detail")


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    success: bool = Field(False, description="Always false for errors")
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[list[ErrorDetail]] = Field(
        None, description="Additional error details"
    )
    request_id: str = Field(..., description="Request ID for tracing")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error_code": "AUTH_1001",
                "message": "Invalid email or password",
                "details": None,
                "request_id": "abc123",
                "timestamp": "2026-01-02T12:00:00Z",
            }
        }


# =============================================================================
# ERROR RESPONSE FACTORY
# =============================================================================


def create_error_response(
    error_code: ErrorCode,
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    details: Optional[list[Dict[str, Any]]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        error_code: Error code enum value
        message: Human-readable error message
        status_code: HTTP status code
        details: Optional list of error details
        headers: Optional extra HTTP headers (e.g. Retry-After)

    Returns:
        JSONResponse with standardized error format
    """
    request_id = request_id_var.get() or "unknown"

    error_details = None
    if details:
        error_details = [
            ErrorDetail(
                field=d.get("field"),
                message=d.get("message", "Unknown error"),
                code=d.get("code"),
            ).model_dump(exclude_none=True)
            for d in details
        ]

    response_data = ErrorResponse(
        success=False,
        error_code=error_code.value,
        message=message,
        details=error_details,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    ).model_dump(exclude_none=True)

    return JSONResponse(
        status_code=status_code,
        content=response_data,
        headers=headers,
    )


# =============================================================================
# CUSTOM HTTP EXCEPTIONS
# =============================================================================


class APIError(HTTPException):
    """
    Custom API error with standardized response format.

    Usage:
        raise APIError(
            error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            message="Invalid email or password",
            status_code=401
        )
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[list[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.details = details
        super().__init__(status_code=status_code, detail=message, headers=headers)

    def to_response(self) -> JSONResponse:
        """Convert to standardized JSON response."""
        hdrs = getattr(self, "headers", None)
        return create_error_response(
            error_code=self.error_code,
            message=self.message,
            status_code=self.status_code,
            details=self.details,
            headers=dict(hdrs) if hdrs else None,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def unauthorized_error(
    message: str = "Authentication required",
    error_code: ErrorCode = ErrorCode.AUTH_UNAUTHORIZED,
) -> APIError:
    """Create unauthorized (401) error."""
    return APIError(
        error_code=error_code,
        message=message,
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


def forbidden_error(
    message: str = "Access denied",
    error_code: ErrorCode = ErrorCode.AUTH_FORBIDDEN,
) -> APIError:
    """Create forbidden (403) error."""
    return APIError(
        error_code=error_code,
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
    )


def not_found_error(
    message: str = "Resource not found",
    resource_type: Optional[str] = None,
) -> APIError:
    """Create not found (404) error."""
    if resource_type:
        message = f"{resource_type} not found"
    return APIError(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
    )


def validation_error(
    message: str = "Validation failed",
    details: Optional[list[Dict[str, Any]]] = None,
) -> APIError:
    """Create validation (422) error."""
    return APIError(
        error_code=ErrorCode.VALIDATION_ERROR,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details=details,
    )


def rate_limit_error(
    message: str = "Rate limit exceeded",
    retry_after: Optional[int] = None,
) -> APIError:
    """Create rate limit (429) error."""
    error = APIError(
        error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
        message=message,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    if retry_after:
        error.headers = {"Retry-After": str(retry_after)}
    return error


def internal_error(
    message: str = "An unexpected error occurred",
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
) -> APIError:
    """Create internal server (500) error."""
    return APIError(
        error_code=error_code,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def account_locked_error(
    message: str = "Account temporarily locked due to too many failed login attempts",
    retry_after: int = 900,
) -> APIError:
    """Create account locked (423) error."""
    error = APIError(
        error_code=ErrorCode.AUTH_ACCOUNT_LOCKED,
        message=message,
        status_code=status.HTTP_423_LOCKED,
    )
    error.headers = {"Retry-After": str(retry_after)}
    return error


def external_service_error(
    message: str = "An external service is temporarily unavailable",
    error_code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
) -> APIError:
    """Create external service unavailable (503) error."""
    return APIError(
        error_code=error_code,
        message=message,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def not_implemented_error(
    message: str = "This feature is not yet implemented",
) -> APIError:
    """Create not implemented (501) error."""
    return APIError(
        error_code=ErrorCode.NOT_IMPLEMENTED,
        message=message,
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
    )


def no_api_key_error(
    message: str = "No API key configured. Choose a provider and add your API key in Settings → AI Setup.",
) -> APIError:
    """Create no-API-key (422) error with a dedicated code so the frontend can show a targeted prompt."""
    return APIError(
        error_code=ErrorCode.NO_API_KEY,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


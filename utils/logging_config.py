"""
Centralized logging configuration for the RoleMule.
Provides structured JSON logging, request tracing, log rotation, and security-aware logging.
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, TypeVar
from uuid import uuid4

# =============================================================================
# SERVICE METADATA  (set once at startup by setup_logging)
# =============================================================================

# Injected into every JSON log record so aggregators (DataDog, CloudWatch,
# Splunk, ELK) can filter/group by service, version, and environment.
_SERVICE_META: Dict[str, str] = {
    "service": "rolemule",
    "version": "unknown",
    "environment": "development",
    "host": "",
}


def _get_hostname() -> str:
    import socket
    try:
        return socket.gethostname()
    except Exception as exc:
        logging.getLogger(__name__).debug('Could not resolve hostname for log metadata: %s', sanitize_log_value(exc), exc_info=True)
        return "unknown"


# =============================================================================
# CONTEXT VARIABLES FOR REQUEST TRACING
# =============================================================================

# Context variables for request-scoped data
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)

# =============================================================================
# CONSTANTS
# =============================================================================

# Sensitive field patterns to redact from logs
SENSITIVE_PATTERNS: List[str] = [
    r"password",
    r"passwd",
    r"secret",
    r"token",
    r"api_key",
    r"apikey",
    r"authorization",
    r"auth",
    r"credential",
    r"private_key",
    r"access_key",
    r"jwt",
    r"bearer",
    r"cookie",
    r"session",
]

# Compile patterns for performance
SENSITIVE_REGEX = re.compile(
    r"(" + "|".join(SENSITIVE_PATTERNS) + r")\s*[:=]\s*['\"]?([^'\"\s,}]+)",
    re.IGNORECASE,
)

# Redaction placeholder
REDACTED = "[REDACTED]"

# Column widths for the development formatter
_COL_NAME_WIDTH = 24
_COL_LEVEL_WIDTH = 8

# Log rotation defaults
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5
DEFAULT_LOG_DIR = "logs"

# =============================================================================
# SENSITIVE DATA REDACTION
# =============================================================================


def redact_sensitive_data(data: Any, depth: int = 0, max_depth: int = 10) -> Any:
    """
    Recursively redact sensitive data from logs.

    Args:
        data: Data to redact (dict, list, string, or other)
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Redacted copy of the data
    """
    if depth > max_depth:
        return "[MAX_DEPTH_EXCEEDED]"

    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            # Check if key matches any sensitive pattern
            if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_sensitive_data(value, depth + 1, max_depth)
        return redacted

    elif isinstance(data, (list, tuple)):
        return [redact_sensitive_data(item, depth + 1, max_depth) for item in data]

    elif isinstance(data, str):
        # Redact inline sensitive values in strings
        return SENSITIVE_REGEX.sub(r"\1: " + REDACTED, data)

    return data


# =============================================================================
# CUSTOM LOG RECORD FACTORY
# =============================================================================


_original_factory = logging.getLogRecordFactory()


def custom_record_factory(*args, **kwargs) -> logging.LogRecord:
    """
    Custom log record factory that adds context variables to log records.
    """
    record = _original_factory(*args, **kwargs)

    # Add context variables
    record.request_id = request_id_var.get() or "-"
    record.user_id = user_id_var.get() or "-"
    record.session_id = session_id_var.get() or "-"

    return record


# =============================================================================
# JSON FORMATTER
# =============================================================================


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging in production.
    Outputs one JSON object per line for easy parsing by log aggregators.
    """

    def __init__(
        self,
        include_extras: bool = True,
        redact_sensitive: bool = True,
        include_traceback: bool = True,
    ):
        super().__init__()
        self.include_extras = include_extras
        self.redact_sensitive = redact_sensitive
        self.include_traceback = include_traceback

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as a single JSON line.

        Standard fields recognised by DataDog, CloudWatch, Splunk, and ELK:
          timestamp, level, message, logger, service, version, environment,
          host, trace_id (= request_id), user_id, session_id
        """
        msg = record.getMessage()
        if isinstance(msg, str):
            msg = sanitize_log_value(msg)
        if self.redact_sensitive and isinstance(msg, str):
            msg = SENSITIVE_REGEX.sub(r"\1: " + REDACTED, msg)

        log_data: Dict[str, Any] = {
            # ---- Standard / aggregator-required fields ----
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "level":       record.levelname,
            "message":     msg,
            "logger":      record.name,
            # ---- Service identity (set at startup via setup_logging) ----
            "service":     _SERVICE_META["service"],
            "version":     _SERVICE_META["version"],
            "environment": _SERVICE_META["environment"],
            "host":        _SERVICE_META["host"] or _get_hostname(),
            # ---- Request tracing ----
            "trace_id":    getattr(record, "request_id", None) or "-",
        }

        # Optional context
        user_id = getattr(record, "user_id", None)
        if user_id and user_id != "-":
            log_data["user_id"] = user_id

        session_id = getattr(record, "session_id", None)
        if session_id and session_id != "-":
            log_data["session_id"] = session_id

        # Source location on ERROR and above
        if record.levelno >= logging.ERROR:
            log_data["source"] = {
                "file":     record.pathname,
                "line":     record.lineno,
                "function": record.funcName,
            }

        # Exception info
        if record.exc_info and self.include_traceback:
            log_data["exception"] = {
                "type":      record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message":   str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Well-known performance / HTTP extra fields
        if self.include_extras:
            for field in (
                "duration_ms", "status_code", "method", "path",
                "agent", "workflow_id", "service", "operation",
                "cache_type", "event", "auth_method",
            ):
                val = getattr(record, field, None)
                if val is not None:
                    log_data[field] = val

        # Redact any remaining sensitive values
        if self.redact_sensitive:
            log_data = redact_sensitive_data(log_data)

        return json.dumps(log_data, default=str, ensure_ascii=False)


# =============================================================================
# DEVELOPMENT FORMATTER
# =============================================================================


class DevelopmentFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Output columns (all fixed-width for easy scanning):
        HH:MM:SS.mmm  LEVEL     module_name               [req_id]  message
    """

    LEVEL_COLORS = {
        "DEBUG":    "\033[36m",      # Cyan
        "INFO":     "\033[32m",      # Green
        "WARNING":  "\033[33m",      # Yellow
        "ERROR":    "\033[31m",      # Red
        "CRITICAL": "\033[1;31m",    # Bold Red
    }
    # Status-code colour for request log lines
    STATUS_COLORS = {
        "2": "\033[32m",   # 2xx green
        "3": "\033[36m",   # 3xx cyan
        "4": "\033[33m",   # 4xx yellow
        "5": "\033[31m",   # 5xx red
    }
    RESET = "\033[0m"
    DIM   = "\033[2m"
    BOLD  = "\033[1m"

    def __init__(self, use_colors: bool = True, redact_sensitive: bool = True):
        super().__init__(datefmt="%H:%M:%S")
        self.use_colors = use_colors and sys.stdout.isatty()
        self.redact_sensitive = redact_sensitive

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _short_name(self, name: str) -> str:
        """Return only the last component of a dotted logger name."""
        return name.rsplit(".", 1)[-1]

    def _colorize_status(self, status: str) -> str:
        if not self.use_colors:
            return status
        color = self.STATUS_COLORS.get(status[0], "")
        return f"{color}{status}{self.RESET}"

    def _colorize_level(self, level: str) -> str:
        if not self.use_colors:
            return level
        color = self.LEVEL_COLORS.get(level, "")
        return f"{color}{level}{self.RESET}"

    def _colorize_dim(self, text: str) -> str:
        if not self.use_colors:
            return text
        return f"{self.DIM}{text}{self.RESET}"

    def _colorize_bold(self, text: str) -> str:
        if not self.use_colors:
            return text
        return f"{self.BOLD}{text}{self.RESET}"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as a clean, columnar dev-mode line."""
        # --- Timestamp ---
        msecs = f"{int(record.msecs):03d}"
        time_str = self.formatTime(record, "%H:%M:%S") + f".{msecs}"

        # --- Level (fixed width, colorised) ---
        level_raw = record.levelname
        level_display = self._colorize_level(f"{level_raw:<{_COL_LEVEL_WIDTH}}")

        # --- Logger name (last component, fixed width) ---
        short = self._short_name(record.name)
        name_display = self._colorize_dim(f"{short:<{_COL_NAME_WIDTH}}")

        # --- Request ID ---
        req_id = getattr(record, "request_id", "-") or "-"
        req_display = self._colorize_dim(f"[{req_id:<8}]")

        # --- Message ---
        msg = record.getMessage()
        if isinstance(msg, str):
            msg = sanitize_log_value(msg)
        if self.redact_sensitive and isinstance(msg, str):
            msg = SENSITIVE_REGEX.sub(r"\1: " + REDACTED, msg)

        # Colour the HTTP status code embedded in request completion lines,
        # e.g.  "GET /api/... - 200 (22.36ms)"
        import re as _re
        status_match = _re.search(r"\b([2345]\d{2})\b", msg)
        if status_match and self.use_colors:
            status_code = status_match.group(1)
            colored_status = self._colorize_status(status_code)
            msg = msg.replace(status_code, colored_status, 1)

        # Colour ERROR / WARNING messages themselves
        if self.use_colors and level_raw in ("ERROR", "CRITICAL"):
            msg = f"{self.LEVEL_COLORS[level_raw]}{msg}{self.RESET}"
        elif self.use_colors and level_raw == "WARNING":
            msg = f"{self.LEVEL_COLORS['WARNING']}{msg}{self.RESET}"

        line = f"{time_str}  {level_display}  {name_display}  {req_display}  {msg}"

        # Append exception traceback if present
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================


class LoggingConfig:
    """
    Centralized logging configuration manager.
    """

    def __init__(
        self,
        log_level: str = "INFO",
        log_format: str = "json",  # "json" or "text"
        log_dir: str = DEFAULT_LOG_DIR,
        enable_file_logging: bool = True,
        enable_console_logging: bool = True,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        redact_sensitive: bool = True,
        app_name: str = "rolemule",
    ):
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_format = log_format.lower()
        self.log_dir = log_dir
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.redact_sensitive = redact_sensitive
        self.app_name = app_name
        self._configured = False

    def configure(self) -> None:
        """
        Configure the logging system.
        Should be called once at application startup.
        """
        if self._configured:
            return

        # Create logs directory
        if self.enable_file_logging:
            Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Set custom record factory for context variables
        logging.setLogRecordFactory(custom_record_factory)

        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # Remove existing handlers
        root_logger.handlers.clear()

        # Create formatters
        if self.log_format == "json":
            main_formatter = JSONFormatter(redact_sensitive=self.redact_sensitive)
            error_formatter = JSONFormatter(
                redact_sensitive=self.redact_sensitive,
                include_traceback=True,
            )
        else:
            main_formatter = DevelopmentFormatter(redact_sensitive=self.redact_sensitive)
            error_formatter = DevelopmentFormatter(redact_sensitive=self.redact_sensitive)

        # Console handler
        if self.enable_console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(main_formatter)
            root_logger.addHandler(console_handler)

        # File handlers with rotation
        if self.enable_file_logging:
            # Main application log
            app_log_path = os.path.join(self.log_dir, f"{self.app_name}.log")
            app_handler = logging.handlers.RotatingFileHandler(
                app_log_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8",
            )
            app_handler.setLevel(self.log_level)
            app_handler.setFormatter(main_formatter)
            root_logger.addHandler(app_handler)

            # Error-only log
            error_log_path = os.path.join(self.log_dir, f"{self.app_name}-error.log")
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(error_formatter)
            root_logger.addHandler(error_handler)

        # ---- Third-party logger noise suppression ----
        # Each library listed here either has its own handlers (uvicorn) or
        # produces excessive INFO/DEBUG chatter that adds no operational value.
        noisy_loggers = [
            # uvicorn — access log is disabled (access_log=False in uvicorn.run),
            # but its error/lifecycle logs are still useful at WARNING+.
            "uvicorn",
            "uvicorn.access",     # disabled via access_log=False, belt-and-suspenders
            "uvicorn.error",
            # HTTP clients
            "httpx",
            "httpcore",
            "httpcore.connection",
            "httpcore.http11",
            # Google Cloud / Gemini SDK
            "google.auth",
            "google.auth.transport",
            "google.api_core",
            "google.cloud",
            "google.genai",
            "models",          # google-genai internal: "AFC is enabled..."
            "grpc",
            # LangGraph / LangChain internals
            "langgraph",
            "langchain",
            "langchain_core",
        ]
        for name in noisy_loggers:
            lib_logger = logging.getLogger(name)
            lib_logger.setLevel(logging.WARNING)
            lib_logger.propagate = False   # do NOT bubble up to our root handler

        # SQLAlchemy — suppress by default; show SQL only at DEBUG level.
        # engine.echo=False (database.py) ensures SA never adds its own duplicate handler.
        sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
        sqlalchemy_logger.setLevel(
            logging.INFO if self.log_level <= logging.DEBUG else logging.WARNING
        )
        sqlalchemy_logger.propagate = True

        self._configured = True
        logging.getLogger(__name__).info('Logging configured: level=%s, format=%s, file_logging=%s', sanitize_log_value(logging.getLevelName(self.log_level)), sanitize_log_value(self.log_format), sanitize_log_value(self.enable_file_logging))


# =============================================================================
# CONTEXT MANAGERS AND DECORATORS
# =============================================================================


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set request context for logging.

    Args:
        request_id: Unique request identifier
        user_id: User identifier
        session_id: Session identifier

    Returns:
        Dict with tokens for resetting context
    """
    tokens = {}
    if request_id:
        tokens["request_id"] = request_id_var.set(request_id)
    if user_id:
        tokens["user_id"] = user_id_var.set(user_id)
    if session_id:
        tokens["session_id"] = session_id_var.set(session_id)
    return tokens


def clear_request_context(tokens: Dict[str, Any]) -> None:
    """
    Clear request context after request processing.

    Args:
        tokens: Tokens returned from set_request_context
    """
    if "request_id" in tokens:
        request_id_var.reset(tokens["request_id"])
    if "user_id" in tokens:
        user_id_var.reset(tokens["user_id"])
    if "session_id" in tokens:
        session_id_var.reset(tokens["session_id"])


def generate_request_id() -> str:
    """
    Generate a unique request ID.

    Uses 16 hex chars (64-bit entropy) — collision probability stays below 1-in-a-million
    well past 100 million requests, suitable for production trace correlation.
    """
    return str(uuid4()).replace("-", "")[:16]


T = TypeVar("T")


def log_execution_time(
    logger: Optional[logging.Logger] = None,
    level: int = logging.INFO,
    message: Optional[str] = None,
) -> Callable:
    """
    Decorator to log function execution time.

    Args:
        logger: Logger to use (defaults to function's module logger)
        level: Log level for timing message
        message: Custom message template (uses {func_name} and {duration_ms})

    Example:
        @log_execution_time(message="Job analysis took {duration_ms}ms")
        async def analyze_job(self, state):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_logger = logger or logging.getLogger(func.__module__)
        msg_template = message or "{func_name} completed in {duration_ms:.2f}ms"

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            start = perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (perf_counter() - start) * 1000
                func_logger.log(
                    level,
                    msg_template.format(func_name=func.__name__, duration_ms=duration_ms),
                    extra={"duration_ms": duration_ms},
                )
                return result
            except Exception as e:
                duration_ms = (perf_counter() - start) * 1000
                func_logger.error(
                    "%s failed after %.2fms: %s",
                    sanitize_log_value(func.__name__),
                    duration_ms,
                    sanitize_log_value(e),
                    extra={"duration_ms": duration_ms},
                    exc_info=True,
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            start = perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (perf_counter() - start) * 1000
                func_logger.log(
                    level,
                    msg_template.format(func_name=func.__name__, duration_ms=duration_ms),
                    extra={"duration_ms": duration_ms},
                )
                return result
            except Exception as e:
                duration_ms = (perf_counter() - start) * 1000
                func_logger.error(
                    "%s failed after %.2fms: %s",
                    sanitize_log_value(func.__name__),
                    duration_ms,
                    sanitize_log_value(e),
                    extra={"duration_ms": duration_ms},
                    exc_info=True,
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# PII MASKING HELPERS
# =============================================================================


def sanitize_log_value(value: Any) -> str:
    """Strip CRLF and null bytes from values before logging to prevent log injection."""
    if value is None:
        return ""
    return re.sub(r"[\r\n\x00]", "", str(value))


def mask_email(email: str) -> str:
    """Return a masked version of an email address for safe logging.

    Example: "user@example.com" → "use***@***"
    Keeps the first 3 characters of the local part so logs remain useful
    for debugging without exposing the full address.
    """
    safe_email = sanitize_log_value(email)
    if not safe_email or "@" not in safe_email:
        return "***"
    local = safe_email.split("@")[0]
    return f"{local[:3]}***@***"


# =============================================================================
# STRUCTURED LOGGING HELPERS
# =============================================================================


class StructuredLogger:
    """
    Helper class for consistent structured logging.
    Wraps a standard logger with methods for common log patterns.
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None,
    ) -> None:
        """Log an HTTP request with standard fields."""
        self.logger.info(
            "%s %s - %s (%.2fms)",
            sanitize_log_value(method),
            sanitize_log_value(path),
            status_code,
            duration_ms,
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
            },
        )

    def log_agent_start(self, agent_name: str, workflow_id: str) -> None:
        """Log agent execution start."""
        self.logger.info(
            "Agent %r starting",
            sanitize_log_value(agent_name),
            extra={"agent": agent_name, "workflow_id": workflow_id},
        )

    def log_agent_complete(
        self, agent_name: str, workflow_id: str, duration_ms: float
    ) -> None:
        """Log agent execution completion."""
        self.logger.info(
            "Agent %r completed in %.2fms",
            sanitize_log_value(agent_name),
            duration_ms,
            extra={
                "agent": agent_name,
                "workflow_id": workflow_id,
                "duration_ms": duration_ms,
            },
        )

    def log_agent_error(
        self,
        agent_name: str,
        workflow_id: str,
        error: Exception,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log agent execution error."""
        extra = {"agent": agent_name, "workflow_id": workflow_id}
        if duration_ms:
            extra["duration_ms"] = duration_ms
        self.logger.error(
            "Agent %r failed: %s",
            sanitize_log_value(agent_name),
            sanitize_log_value(error),
            extra=extra,
            exc_info=True,
        )

    def log_external_api_call(
        self,
        service: str,
        operation: str,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Log external API call."""
        if success:
            self.logger.info(
                "External API call: %s.%s - %.2fms",
                sanitize_log_value(service),
                sanitize_log_value(operation),
                duration_ms,
                extra={
                    "service": service,
                    "operation": operation,
                    "duration_ms": duration_ms,
                },
            )
        else:
            self.logger.warning(
                "External API call failed: %s.%s - %s",
                sanitize_log_value(service),
                sanitize_log_value(operation),
                sanitize_log_value(error),
                extra={
                    "service": service,
                    "operation": operation,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )

    def log_db_operation(
        self,
        operation: str,
        table: str,
        duration_ms: float,
        rows_affected: Optional[int] = None,
    ) -> None:
        """Log database operation."""
        if rows_affected is not None:
            self.logger.debug(
                "DB %s on %s - %.2fms (%s rows)",
                sanitize_log_value(operation),
                sanitize_log_value(table),
                duration_ms,
                sanitize_log_value(rows_affected),
                extra={
                    "operation": operation,
                    "table": table,
                    "duration_ms": duration_ms,
                    "rows_affected": rows_affected,
                },
            )
        else:
            self.logger.debug(
                "DB %s on %s - %.2fms",
                sanitize_log_value(operation),
                sanitize_log_value(table),
                duration_ms,
                extra={
                    "operation": operation,
                    "table": table,
                    "duration_ms": duration_ms,
                    "rows_affected": rows_affected,
                },
            )

    # =========================================================================
    # SECURITY EVENT LOGGING
    # =========================================================================

    def log_login_success(self, email: str, auth_method: str = "local") -> None:
        """Log successful login."""
        self.logger.info(
            "Login successful: %s via %s",
            mask_email(email),
            sanitize_log_value(auth_method),
            extra={"event": "login_success", "auth_method": auth_method},
        )

    def log_login_failure(
        self, email: str, reason: str, attempts_remaining: Optional[int] = None
    ) -> None:
        """Log failed login attempt."""
        extra = {"event": "login_failure", "reason": reason}
        if attempts_remaining is not None:
            extra["attempts_remaining"] = attempts_remaining
        self.logger.warning(
            "Login failed for %s: %s",
            mask_email(email),
            sanitize_log_value(reason),
            extra=extra,
        )

    def log_account_lockout(self, email: str, duration_seconds: int) -> None:
        """Log account lockout event."""
        self.logger.warning(
            "Account locked: %s for %s minutes",
            mask_email(email),
            sanitize_log_value(duration_seconds // 60),
            extra={
                "event": "account_lockout",
                "duration_seconds": duration_seconds,
            },
        )

    def log_registration(self, email: str, auth_method: str = "local") -> None:
        """Log user registration."""
        self.logger.info(
            "User registered: %s via %s",
            mask_email(email),
            sanitize_log_value(auth_method),
            extra={"event": "registration", "auth_method": auth_method},
        )

    def log_password_reset_request(self, email: str) -> None:
        """Log password reset request."""
        self.logger.info(
            "Password reset requested for %s",
            mask_email(email),
            extra={"event": "password_reset_request"},
        )

    def log_password_reset_complete(self, email: str) -> None:
        """Log successful password reset."""
        self.logger.info(
            "Password reset completed for %s",
            mask_email(email),
            extra={"event": "password_reset_complete"},
        )

    def log_password_change(self, email: str) -> None:
        """Log password change."""
        self.logger.info(
            "Password changed for %s",
            mask_email(email),
            extra={"event": "password_change"},
        )

    def log_token_refresh(self, email: str) -> None:
        """Log token refresh."""
        self.logger.debug(
            "Token refreshed for %s",
            mask_email(email),
            extra={"event": "token_refresh"},
        )

    def log_oauth_login(self, email: str, provider: str, is_new_user: bool) -> None:
        """Log OAuth login."""
        action = "registered" if is_new_user else "logged in"
        self.logger.info(
            "OAuth user %s: %s via %s",
            sanitize_log_value(action),
            mask_email(email),
            sanitize_log_value(provider),
            extra={
                "event": "oauth_login",
                "provider": provider,
                "is_new_user": is_new_user,
            },
        )

    # =========================================================================
    # CACHE LOGGING
    # =========================================================================

    def log_cache_hit(self, cache_type: str, key: str) -> None:
        """Log cache hit."""
        self.logger.debug(
            "Cache hit: %s - %s...",
            sanitize_log_value(cache_type),
            sanitize_log_value(key[:20]),
            extra={"event": "cache_hit", "cache_type": cache_type},
        )

    def log_cache_miss(self, cache_type: str, key: str) -> None:
        """Log cache miss."""
        self.logger.debug(
            "Cache miss: %s - %s...",
            sanitize_log_value(cache_type),
            sanitize_log_value(key[:20]),
            extra={"event": "cache_miss", "cache_type": cache_type},
        )


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger for the given module name."""
    return StructuredLogger(name)


def log_startup_info(
    app_name: str,
    version: str,
    environment: str,
    debug: bool,
    host: str,
    port: int,
    gemini_model: str,
    use_vertex_ai: bool,
    vertex_project: Optional[str],
    vertex_location: str,
    database_url: str,
    redis_url: str,
    log_level: str,
) -> None:
    """
    Emit a clear startup summary so the console immediately shows
    what model, backend, and environment the app is running with.
    """
    _log = logging.getLogger("startup")

    # Redact credentials from the DB URL for display
    import re as _re
    db_display = _re.sub(r"://[^@]+@", "://<credentials>@", database_url)

    llm_backend = (
        f"Vertex AI  project={vertex_project}  location={vertex_location}"
        if use_vertex_ai
        else "Google AI Studio  (set USE_VERTEX_AI=true for production)"
    )

    sep = "-" * 60
    _log.info(sep)
    _log.info("  %s v%s", sanitize_log_value(app_name), sanitize_log_value(version))
    _log.info(sep)
    _log.info(
        "  env        : %s%s",
        sanitize_log_value(environment),
        "  [DEBUG]" if debug else "",
    )
    _log.info(
        "  listening  : http://%s:%s",
        sanitize_log_value(host),
        sanitize_log_value(port),
    )
    _log.info("  LLM model  : %s", sanitize_log_value(gemini_model))
    _log.info("  LLM backend: %s", sanitize_log_value(llm_backend))
    redis_display = _re.sub(r"://[^@]+@", "://<credentials>@", redis_url)
    _log.info("  database   : %s", sanitize_log_value(db_display))
    _log.info("  redis      : %s", sanitize_log_value(redis_display))
    _log.info("  log level  : %s", sanitize_log_value(log_level))
    _log.info(sep)


# =============================================================================
# GLOBAL CONFIGURATION INSTANCE
# =============================================================================

# Default configuration - will be overwritten by setup_logging()
_logging_config: Optional[LoggingConfig] = None


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_dir: str = DEFAULT_LOG_DIR,
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    redact_sensitive: bool = True,
    app_name: str = "rolemule",
    # Service identity fields embedded in every JSON log line
    service_name: str = "rolemule",
    service_version: str = "unknown",
    environment: str = "development",
) -> LoggingConfig:
    """
    Setup logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ("json" for production, "text" for development)
        log_dir: Directory for log files
        enable_file_logging: Whether to enable file logging
        enable_console_logging: Whether to enable console logging
        max_bytes: Maximum size of each log file before rotation
        backup_count: Number of backup files to keep
        redact_sensitive: Whether to redact sensitive data from logs
        app_name: Application name for log files
        service_name: Service name embedded in JSON logs (for aggregators)
        service_version: Version string embedded in JSON logs
        environment: Environment name embedded in JSON logs (development/production)

    Returns:
        LoggingConfig instance
    """
    global _logging_config, _SERVICE_META

    # Populate service metadata used by JSONFormatter
    _SERVICE_META["service"]     = service_name
    _SERVICE_META["version"]     = service_version
    _SERVICE_META["environment"] = environment
    _SERVICE_META["host"]        = _get_hostname()

    _logging_config = LoggingConfig(
        log_level=log_level,
        log_format=log_format,
        log_dir=log_dir,
        enable_file_logging=enable_file_logging,
        enable_console_logging=enable_console_logging,
        max_bytes=max_bytes,
        backup_count=backup_count,
        redact_sensitive=redact_sensitive,
        app_name=app_name,
    )
    _logging_config.configure()
    return _logging_config


def get_logging_config() -> Optional[LoggingConfig]:
    """Get the current logging configuration."""
    return _logging_config


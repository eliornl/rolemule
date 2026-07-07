"""Extended tests for utils/logging_config.py coverage gaps."""

import logging
import sys

import pytest

from utils.logging_config import (
    DevelopmentFormatter,
    LoggingConfig,
    StructuredLogger,
    get_logging_config,
    get_structured_logger,
    log_execution_time,
    log_startup_info,
    setup_logging,
)


def test_dev_formatter_with_colors_and_status(monkeypatch) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    formatter = DevelopmentFormatter(use_colors=True, redact_sensitive=True)
    record = logging.LogRecord(
        name="utils.request_middleware",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="GET /api/v1/test -> 500  (12ms)",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc12345"
    out = formatter.format(record)
    assert "500" in out
    assert "request_middleware" in out


def test_dev_formatter_warning_and_no_colors() -> None:
    formatter = DevelopmentFormatter(use_colors=False, redact_sensitive=False)
    record = logging.LogRecord(
        name="app.main",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Slow request",
        args=(),
        exc_info=None,
    )
    assert "Slow request" in formatter.format(record)


def test_structured_logger_security_events() -> None:
    slog = get_structured_logger("test.security")
    slog.log_login_success("user@example.com", auth_method="local")
    slog.log_login_failure("user@example.com", reason="bad_password", attempts_remaining=2)
    slog.log_account_lockout("user@example.com", duration_seconds=900)
    slog.log_registration("user@example.com")
    slog.log_password_reset_request("user@example.com")
    slog.log_password_reset_complete("user@example.com")
    slog.log_password_change("user@example.com")
    slog.log_token_refresh("user@example.com")
    slog.log_oauth_login("user@example.com", provider="google", is_new_user=True)
    slog.log_oauth_login("user@example.com", provider="google", is_new_user=False)


def test_log_startup_info_vertex_and_studio() -> None:
    log_startup_info(
        app_name="ApplyPilot",
        version="1.0.0",
        environment="production",
        debug=False,
        host="0.0.0.0",
        port=8000,
        gemini_model="gemini-3.5-flash",
        use_vertex_ai=True,
        vertex_project="my-proj",
        vertex_location="us-central1",
        database_url="postgresql://user:pass@localhost/db",
        redis_url="rediss://user:pass@redis:6379",
        log_level="INFO",
    )
    log_startup_info(
        app_name="ApplyPilot",
        version="1.0.0",
        environment="development",
        debug=True,
        host="127.0.0.1",
        port=8000,
        gemini_model="gemini-3.5-flash",
        use_vertex_ai=False,
        vertex_project=None,
        vertex_location="us-central1",
        database_url="postgresql://localhost/db",
        redis_url="redis://localhost:6379",
        log_level="DEBUG",
    )


@pytest.mark.asyncio
async def test_log_execution_time_async_success_and_failure() -> None:
    test_logger = logging.getLogger("test.exec.async")

    @log_execution_time(logger=test_logger, message="{func_name} took {duration_ms:.1f}ms")
    async def ok():
        return 42

    assert await ok() == 42

    @log_execution_time(logger=test_logger)
    async def fail():
        raise ValueError("async boom")

    with pytest.raises(ValueError, match="async boom"):
        await fail()


def test_log_execution_time_sync_success_and_failure() -> None:
    test_logger = logging.getLogger("test.exec.sync")

    @log_execution_time(logger=test_logger)
    def ok():
        return "done"

    assert ok() == "done"

    @log_execution_time(logger=test_logger)
    def fail():
        raise ValueError("sync boom")

    with pytest.raises(ValueError, match="sync boom"):
        fail()


def test_setup_logging_json_mode_and_get_config(tmp_path) -> None:
    cfg = setup_logging(
        log_level="INFO",
        log_format="json",
        log_dir=str(tmp_path),
        enable_file_logging=False,
        service_name="applypilot-test",
        service_version="0.0.1",
        environment="test",
    )
    assert isinstance(cfg, LoggingConfig)
    assert get_logging_config() is cfg


def test_structured_logger_agent_methods() -> None:
    slog = StructuredLogger("agents.test")
    slog.log_agent_start("job_analyzer", "wf-1")
    slog.log_agent_complete("job_analyzer", "wf-1", duration_ms=100.0)
    slog.log_agent_error("job_analyzer", "wf-1", ValueError("x"), duration_ms=50.0)

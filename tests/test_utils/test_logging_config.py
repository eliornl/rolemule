"""Tests for utils/logging_config.py."""

import logging
from unittest.mock import patch

from utils.logging_config import (
    JSONFormatter,
    LoggingConfig,
    StructuredLogger,
    _get_hostname,
    clear_request_context,
    generate_request_id,
    get_structured_logger,
    mask_email,
    redact_sensitive_data,
    sanitize_log_value,
    set_request_context,
    setup_logging,
)


def test_generate_request_id_length() -> None:
    rid = generate_request_id()
    assert len(rid) == 16


def test_sanitize_log_value_strips_newlines() -> None:
    assert "127.0.0.1" in sanitize_log_value("127.0.0.1\r\nINJECT")
    assert "\r" not in sanitize_log_value("127.0.0.1\r\nINJECT")
    assert "\n" not in sanitize_log_value("127.0.0.1\r\nINJECT")
    assert "\x00" not in sanitize_log_value("a\x00b")


def test_mask_email() -> None:
    assert mask_email("user@example.com") == "use***@***"
    assert mask_email("") == "***"
    assert mask_email("bad") == "***"


def test_redact_sensitive_data_dict() -> None:
    data = {"password": "secret123", "username": "alice"}
    out = redact_sensitive_data(data)
    assert out["password"] == "[REDACTED]"
    assert out["username"] == "alice"


def test_redact_sensitive_data_string() -> None:
    text = 'token: "abc123" end'
    out = redact_sensitive_data(text)
    assert "[REDACTED]" in out


def test_redact_sensitive_data_max_depth() -> None:
    nested: dict = {"a": {}}
    cur = nested["a"]
    for _ in range(12):
        nxt: dict = {}
        cur["b"] = nxt
        cur = nxt
    cur["leaf"] = "x"
    out = redact_sensitive_data(nested, max_depth=5)
    # Deep branch should hit max-depth guard
    deep = out
    for _ in range(8):
        if not isinstance(deep, dict) or "b" not in deep:
            break
        deep = deep["b"]
    assert deep == "[MAX_DEPTH_EXCEEDED]" or "[MAX_DEPTH_EXCEEDED]" in str(out)


def test_set_and_clear_request_context() -> None:
    tokens = set_request_context(request_id="abc", user_id="u1", session_id="s1")
    record = logging.getLogRecordFactory()(
        "name", logging.INFO, "", 0, "msg", (), None
    )
    assert record.request_id == "abc"
    clear_request_context(tokens)
    record2 = logging.getLogRecordFactory()(
        "name", logging.INFO, "", 0, "msg", (), None
    )
    assert record2.request_id == "-"


def test_json_formatter_output() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    record.request_id = "rid123"
    out = formatter.format(record)
    assert '"message": "hello world"' in out
    assert '"trace_id": "rid123"' in out


def test_structured_logger_helpers() -> None:
    slog = get_structured_logger("test.structured")
    assert isinstance(slog, StructuredLogger)
    slog.log_agent_start("job_analyzer", "wf-1")
    slog.log_agent_complete("job_analyzer", "wf-1", duration_ms=100.0)
    slog.log_agent_error("job_analyzer", "wf-1", ValueError("x"), duration_ms=50.0)
    slog.log_external_api_call("gemini", "generate", duration_ms=10.0, success=True)
    slog.log_db_operation("SELECT", "users", duration_ms=1.0, rows_affected=1)
    slog.log_cache_hit("job_analysis", "key")
    slog.log_cache_miss("user_profile", "uid")


def test_setup_logging_text_mode(tmp_path) -> None:
    with patch("utils.logging_config._get_hostname", return_value="testhost"):
        setup_logging(
            log_level="DEBUG",
            log_format="text",
            service_name="applypilot-test",
            service_version="0.0.1",
            environment="test",
            log_dir=str(tmp_path),
        )


def test_get_hostname_fallback(monkeypatch) -> None:
    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: (_ for _ in ()).throw(OSError("no host")))
    assert _get_hostname() == "unknown"


def test_logging_config_configure_is_idempotent() -> None:
    config = LoggingConfig(log_dir="logs", enable_file_logging=False)
    config.configure()
    handlers_before = len(logging.getLogger().handlers)
    config.configure()
    assert len(logging.getLogger().handlers) == handlers_before


def test_structured_logger_request_and_cache_helpers() -> None:
    from unittest.mock import MagicMock

    slog = get_structured_logger("cache-test")
    slog.logger = MagicMock()
    slog.log_request("GET", "/api/v1/test", 200, 12.5, user_id="u1")
    slog.log_cache_hit("job_analysis", "v1:job_analysis:abc")
    slog.log_cache_miss("job_analysis", "v1:job_analysis:xyz")
    slog.logger.info.assert_called_once()
    assert slog.logger.debug.call_count == 2


def test_structured_logger_cache_helpers_with_real_logger() -> None:
    slog = get_structured_logger("cache-real-test")
    with patch.object(slog.logger, "debug") as mock_debug:
        slog.log_cache_hit("job_analysis", "v1:job_analysis:abc")
        slog.log_cache_miss("job_analysis", "v1:job_analysis:xyz")
    assert mock_debug.call_count == 2


def test_json_formatter_includes_user_id_when_set() -> None:
    formatter = JSONFormatter(redact_sensitive=False)
    record = logging.LogRecord(
        name="api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "req123"
    record.user_id = "user-42"
    record.session_id = "sess-9"
    payload = formatter.format(record)
    assert "user-42" in payload
    assert "sess-9" in payload

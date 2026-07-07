"""Tests for utils/request_middleware.py."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import Request, Response

from utils.request_middleware import (
    REQUEST_ID_HEADER,
    RequestLoggingMiddleware,
    SlowRequestMiddleware,
    _sanitize_log_value,
    add_request_id_header,
    get_request_id,
)


def test_sanitize_log_value_strips_newlines() -> None:
    assert "127.0.0.1" in _sanitize_log_value("127.0.0.1\r\nINJECT")
    assert "\r" not in _sanitize_log_value("127.0.0.1\r\nINJECT")
    assert "\n" not in _sanitize_log_value("127.0.0.1\r\nINJECT")


def test_get_request_id_from_header() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-request-id", b"custom-id")],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    req = Request(scope)
    assert get_request_id(req) == "custom-id"


def test_add_request_id_header() -> None:
    resp = Response()
    out = add_request_id_header(resp, "rid-99")
    assert out.headers[REQUEST_ID_HEADER] == "rid-99"


@pytest.mark.asyncio
async def test_request_logging_middleware_success() -> None:
    async def call_next(request: Request) -> Response:
        return Response(status_code=200)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/test",
        "headers": [],
        "query_string": b"q=1",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    mw = RequestLoggingMiddleware(app=MagicMock())
    response = await mw.dispatch(request, call_next)
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers


@pytest.mark.asyncio
async def test_request_logging_middleware_excluded_path() -> None:
    async def call_next(request: Request) -> Response:
        return Response(status_code=200)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    mw = RequestLoggingMiddleware(app=MagicMock())
    response = await mw.dispatch(request, call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_request_logging_middleware_error_propagates() -> None:
    async def call_next(request: Request) -> Response:
        raise RuntimeError("boom")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/fail",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    mw = RequestLoggingMiddleware(app=MagicMock())
    with pytest.raises(RuntimeError):
        await mw.dispatch(request, call_next)


@pytest.mark.asyncio
async def test_request_logging_middleware_logs_user_and_query_on_4xx(caplog) -> None:
    async def call_next(request: Request) -> Response:
        return Response(status_code=404)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/missing",
        "headers": [],
        "query_string": b"foo=bar",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    request.state.user = {"id": "user-uuid-12345678"}

    mw = RequestLoggingMiddleware(app=MagicMock())
    with caplog.at_level(logging.WARNING):
        response = await mw.dispatch(request, call_next)
    assert response.status_code == 404
    assert any("params=" in r.message for r in caplog.records)
    assert any("user=user-uui" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_request_logging_middleware_user_object_attr() -> None:
    async def call_next(request: Request) -> Response:
        return Response(status_code=200)

    class _User:
        id = "obj-user-id"

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/profile/",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    request.state.user = _User()

    mw = RequestLoggingMiddleware(app=MagicMock())
    response = await mw.dispatch(request, call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_slow_request_middleware_logs_warning(caplog) -> None:
    async def call_next(request: Request) -> Response:
        return Response(status_code=200)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/slow",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("test", 80),
    }
    request = Request(scope)
    mw = SlowRequestMiddleware(app=MagicMock(), threshold_ms=-1)
    with caplog.at_level(logging.WARNING):
        await mw.dispatch(request, call_next)
    assert any("SLOW" in r.message for r in caplog.records)

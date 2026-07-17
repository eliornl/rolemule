"""Tests for rolemule_client."""

from __future__ import annotations

import httpx
import pytest

from rolemule_client.client import RoleMuleClient, DEFAULT_TIMEOUT_SECONDS
from rolemule_client.errors import ApiClientError, ExitCode, parse_error_response


def _client_with_transport(handler) -> RoleMuleClient:
    """Build client whose requests go through a mock transport."""
    client = RoleMuleClient("http://localhost:8000", access_token="tok123")

    def _request(method, path, **kwargs):
        url = f"{client.base_url}{path}"
        request = httpx.Request(method, url, headers=client._headers())
        response = handler(request)
        if response.is_success:
            return response
        try:
            body = response.json()
        except Exception:
            body = response.text
        from rolemule_client.errors import parse_error_response

        raise parse_error_response(response.status_code, body)

    client.request = _request  # type: ignore[method-assign]
    return client


def test_auth_header_injected() -> None:
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"status": "healthy"})

    client = _client_with_transport(handler)
    client.health()
    assert seen_auth == ["Bearer tok123"]


def test_health_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy"})

    client = _client_with_transport(handler)
    data = client.health()
    assert data["status"] == "healthy"


def test_api_error_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "success": False,
                "error_code": "CFG_6001",
                "message": "No API key",
                "request_id": "r1",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        )

    client = _client_with_transport(handler)
    with pytest.raises(ApiClientError) as exc_info:
        client.verify_token()
    assert exc_info.value.error_code == "CFG_6001"


def test_parse_error_response_rate_limit() -> None:
    err = parse_error_response(
        429,
        {
            "success": False,
            "error_code": "RATE_4001",
            "message": "Too many requests",
            "request_id": "r1",
            "timestamp": "2026-01-01T00:00:00Z",
        },
    )
    assert err.exit_code == ExitCode.RATE_LIMITED
    assert err.error_code == "RATE_4001"


def test_parse_error_response_auth() -> None:
    err = parse_error_response(401, {"message": "Unauthorized", "error_code": "AUTH_1005"})
    assert err.exit_code == ExitCode.AUTH_OR_PROFILE


def test_connection_error() -> None:
    client = RoleMuleClient("http://127.0.0.1:1", timeout=0.5)
    with pytest.raises(ApiClientError, match="Cannot connect"):
        client.health()


def test_default_timeout() -> None:
    assert DEFAULT_TIMEOUT_SECONDS == 30.0

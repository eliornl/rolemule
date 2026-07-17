"""Tests for rolemule_client.resources.admin."""

from __future__ import annotations

import httpx

from rolemule_client.client import RoleMuleClient


def _mock_client(handler) -> RoleMuleClient:
    client = RoleMuleClient("http://localhost:8000", access_token="jwt")

    def _request(method, path, **kwargs):
        url = f"{client.base_url}{path}"
        headers = client._headers(auth=kwargs.get("auth", True))
        req = httpx.Request(method, url, headers=headers)
        if kwargs.get("json") is not None:
            req = httpx.Request(
                method,
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=kwargs["json"],
            )
        response = handler(req, kwargs)
        if response.is_success:
            return response
        from rolemule_client.errors import parse_error_response

        try:
            body = response.json()
        except Exception:
            body = response.text
        raise parse_error_response(response.status_code, body)

    client.request = _request  # type: ignore[method-assign]
    return client


def test_admin_maintenance_get() -> None:
    def handler(request: httpx.Request, _kwargs) -> httpx.Response:
        assert request.url.path == "/api/v1/admin/maintenance"
        return httpx.Response(200, json={"enabled": False, "message": None, "estimated_end": None})

    data = _mock_client(handler).admin.maintenance_status()
    assert data["enabled"] is False


def test_admin_set_maintenance_post() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.method == "POST"
        seen.append(kwargs["json"])
        return httpx.Response(200, json={"enabled": True, "message": "Upgrading", "estimated_end": "1h"})

    _mock_client(handler).admin.set_maintenance(enabled=True, message="Upgrading", estimated_end="1h")
    assert seen == [{"enabled": True, "message": "Upgrading", "estimated_end": "1h"}]


def test_admin_cache_stats_path() -> None:
    def handler(request: httpx.Request, _kwargs) -> httpx.Response:
        assert request.url.path == "/api/v1/cache/stats"
        return httpx.Response(200, json={"status": "ok", "hits": 10})

    data = _mock_client(handler).admin.cache_stats()
    assert data["status"] == "ok"

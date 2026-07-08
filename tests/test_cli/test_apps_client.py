"""Tests for applypilot_client.resources.applications."""

from __future__ import annotations

import httpx

from applypilot_client.client import ApplyPilotClient


def _mock_client(handler) -> ApplyPilotClient:
    client = ApplyPilotClient("http://localhost:8000", access_token="jwt")

    def _request(method, path, **kwargs):
        response = handler(method, path, kwargs)
        if response.is_success:
            return response
        from applypilot_client.errors import parse_error_response

        try:
            body = response.json()
        except Exception:
            body = response.text
        raise parse_error_response(response.status_code, body)

    client.request = _request  # type: ignore[method-assign]
    return client


def test_list_builds_query_params() -> None:
    seen: list[dict] = []

    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "GET"
        assert path == "/api/v1/applications/"
        seen.append(kwargs.get("params") or {})
        return httpx.Response(
            200,
            json={"applications": [], "total": 0, "page": 1, "per_page": 20, "has_next": False, "has_prev": False},
        )

    _mock_client(handler).applications.list(
        page=2,
        per_page=10,
        status_filter="applied",
        search="python",
        company="Acme",
        days=30,
        sort="title_asc",
    )
    assert seen[0]["page"] == 2
    assert seen[0]["per_page"] == 10
    assert seen[0]["status_filter"] == "applied"
    assert seen[0]["search"] == "python"
    assert seen[0]["company"] == "Acme"
    assert seen[0]["days"] == 30
    assert seen[0]["sort"] == "title_asc"


def test_update_status_body() -> None:
    seen: list[dict] = []

    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "PATCH"
        assert path == "/api/v1/applications/app-1/status"
        seen.append(kwargs.get("json") or {})
        return httpx.Response(200, json={"id": "app-1", "status": "applied"})

    _mock_client(handler).applications.update_status("app-1", "applied")
    assert seen[0] == {"new_status": "applied"}


def test_delete_application() -> None:
    def handler(method, path, _kwargs) -> httpx.Response:
        assert method == "DELETE"
        assert path == "/api/v1/applications/app-2"
        return httpx.Response(200, json={"message": "Application deleted successfully"})

    data = _mock_client(handler).applications.delete("app-2")
    assert "deleted" in data["message"].lower()

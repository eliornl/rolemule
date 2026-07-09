"""Tests for applypilot_client.resources.workflow."""

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


def test_start_with_job_text() -> None:
    seen: list[dict] = []

    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "POST"
        assert path == "/api/v1/workflow/start"
        seen.append(kwargs.get("data") or {})
        return httpx.Response(200, json={"session_id": "sess-1", "status": "initialized"})

    data = _mock_client(handler).workflow.start(job_text="Engineer role at Acme")
    assert data["session_id"] == "sess-1"
    assert seen[0]["job_text"] == "Engineer role at Acme"


def test_start_strips_non_http_url() -> None:
    seen: list[dict] = []

    def handler(_method, _path, kwargs) -> httpx.Response:
        seen.append(kwargs.get("data") or {})
        return httpx.Response(200, json={"session_id": "sess-2", "status": "initialized"})

    _mock_client(handler).workflow.start(job_text="text", job_url="ftp://bad.example/job")
    assert "job_url" not in seen[0]


def test_history_query_params() -> None:
    seen: list[dict] = []

    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "GET"
        assert path == "/api/v1/workflow/history"
        seen.append(kwargs.get("params") or {})
        return httpx.Response(200, json={"sessions": [], "total": 0})

    _mock_client(handler).workflow.history(page=2, per_page=5, status_filter="completed")
    assert seen[0]["page"] == 2
    assert seen[0]["per_page"] == 5
    assert seen[0]["status_filter"] == "completed"

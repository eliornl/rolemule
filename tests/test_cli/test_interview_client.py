"""Tests for applypilot_client.resources.interview_prep."""

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


def test_generate_starts_background_job() -> None:
    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "POST"
        assert path == "/api/v1/interview-prep/sess-1/generate"
        assert kwargs.get("params") is None
        return httpx.Response(
            200,
            json={"session_id": "sess-1", "status": "generating", "message": "Started"},
        )

    data = _mock_client(handler).interview_prep.generate("sess-1")
    assert data["status"] == "generating"


def test_generate_regenerate_query_param() -> None:
    seen: list[dict | None] = []

    def handler(_method, _path, kwargs) -> httpx.Response:
        seen.append(kwargs.get("params"))
        return httpx.Response(200, json={"session_id": "sess-1", "status": "generating", "message": "ok"})

    _mock_client(handler).interview_prep.generate("sess-1", regenerate=True)
    assert seen[0] == {"regenerate": True}


def test_show_and_status_paths() -> None:
    paths: list[str] = []

    def handler(method, path, _kwargs) -> httpx.Response:
        paths.append(f"{method} {path}")
        if path.endswith("/status"):
            return httpx.Response(200, json={"session_id": "sess-2", "has_interview_prep": True, "is_generating": False})
        return httpx.Response(200, json={"session_id": "sess-2", "has_interview_prep": True, "interview_prep": {}})

    client = _mock_client(handler)
    client.interview_prep.status("sess-2")
    client.interview_prep.show("sess-2")
    assert "GET /api/v1/interview-prep/sess-2/status" in paths
    assert "GET /api/v1/interview-prep/sess-2" in paths

"""Tests for applypilot_client.resources.cv_optimizer."""

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


def test_start_sends_config_body() -> None:
    seen: list[dict] = []

    def handler(method, path, kwargs) -> httpx.Response:
        assert method == "POST"
        assert path == "/api/v1/cv-optimizer/sess-1/start"
        seen.append(kwargs.get("json") or {})
        return httpx.Response(202, json={"session_id": "sess-1", "status": "started", "message": "ok"})

    _mock_client(handler).cv_optimizer.start("sess-1", max_iterations=4, score_threshold=8.0)
    assert seen[0] == {"max_iterations": 4, "score_threshold": 8.0}


def test_status_and_show() -> None:
    paths: list[str] = []

    def handler(method, path, _kwargs) -> httpx.Response:
        paths.append(f"{method} {path}")
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={"session_id": "sess-2", "has_result": True, "is_running": False, "best_score": 8.7},
            )
        return httpx.Response(
            200,
            json={"session_id": "sess-2", "has_result": True, "result": {"best_score": 8.7, "status": "completed"}},
        )

    client = _mock_client(handler)
    client.cv_optimizer.status("sess-2")
    client.cv_optimizer.show("sess-2")
    assert "GET /api/v1/cv-optimizer/sess-2/status" in paths
    assert "GET /api/v1/cv-optimizer/sess-2" in paths

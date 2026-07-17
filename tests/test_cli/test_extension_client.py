"""Tests for rolemule_client.resources.extension."""

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


def test_autofill_map_post() -> None:
    payload = {
        "page_url": "https://careers.example.com/apply",
        "fields": [{"field_uid": "0", "tag": "input", "input_type": "text", "label_text": "First name"}],
    }
    seen: list[dict] = []

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/extension/autofill/map"
        seen.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "assignments": [{"field_uid": "0", "value": "Jane", "label_text": "First name"}],
                "skipped": [],
                "warnings": ["Review every value before applying."],
            },
        )

    data = _mock_client(handler).extension.autofill_map(payload)
    assert seen == [payload]
    assert data["assignments"][0]["value"] == "Jane"

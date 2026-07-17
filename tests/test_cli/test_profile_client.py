"""Tests for rolemule_client.resources.profile."""

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
            req = httpx.Request(method, url, headers={**headers, "Content-Type": "application/json"}, json=kwargs["json"])
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


def test_profile_show() -> None:
    def handler(request: httpx.Request, _kwargs) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/profile/"
        return httpx.Response(200, json={"profile_data": {}})

    data = _mock_client(handler).profile.show()
    assert "profile_data" in data


def test_update_basic_info() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/api/v1/profile/basic-info"
        seen.append(kwargs["json"])
        return httpx.Response(200, json={"success": True})

    payload = {"city": "Austin", "state": "TX", "country": "USA", "professional_title": "Eng", "years_experience": 5, "summary": "Hi"}
    _mock_client(handler).profile.update_basic_info(payload)
    assert seen == [payload]


def test_parse_resume_multipart(tmp_path) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    seen: list[bool] = []

    def handler(method, path, **kwargs) -> httpx.Response:
        assert method == "POST"
        assert path == "/api/v1/profile/parse-resume"
        assert kwargs.get("files") is not None
        seen.append(True)
        return httpx.Response(200, json={"parsed": True})

    client = RoleMuleClient("http://localhost:8000", access_token="jwt")
    client.request = handler  # type: ignore[method-assign]
    data = client.profile.parse_resume(str(resume))
    assert data["parsed"] is True
    assert seen == [True]


def test_clear_data_sends_confirm_body() -> None:
    seen: list[dict | None] = []

    def handler(_request: httpx.Request, kwargs) -> httpx.Response:
        seen.append(kwargs.get("json"))
        return httpx.Response(200, json={"cleared": True})

    _mock_client(handler).profile.clear_data()
    assert seen == [{"confirm": True}]


def test_delete_account_password_body() -> None:
    seen: list[dict | None] = []

    def handler(_request: httpx.Request, kwargs) -> httpx.Response:
        seen.append(kwargs.get("json"))
        return httpx.Response(200, json={"deleted": True})

    _mock_client(handler).profile.delete_account("")
    assert seen == [{"password": ""}]


def test_workflow_preferences_patch() -> None:
    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.method == "PATCH"
        assert kwargs["json"] == {"cover_letter_tone": "professional"}
        return httpx.Response(200, json={"cover_letter_tone": "professional"})

    data = _mock_client(handler).profile.workflow_preferences_set({"cover_letter_tone": "professional"})
    assert data["cover_letter_tone"] == "professional"

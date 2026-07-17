"""Tests for rolemule_client.resources.auth."""

from __future__ import annotations

import json

import httpx

from rolemule_client.client import RoleMuleClient


def _mock_client(handler) -> RoleMuleClient:
    client = RoleMuleClient("http://localhost:8000", access_token="old-token")

    def _request(method, path, **kwargs):
        url = f"{client.base_url}{path}"
        req = httpx.Request(method, url, headers=client._headers(auth=kwargs.get("auth", True)))
        if kwargs.get("json") is not None:
            req = httpx.Request(
                method,
                url,
                headers={**client._headers(auth=kwargs.get("auth", True)), "Content-Type": "application/json"},
                json=kwargs["json"],
            )
        response = handler(req)
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


def test_login_no_auth_header() -> None:
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        assert request.url.path == "/api/v1/auth/login"
        return httpx.Response(
            200,
            json={
                "access_token": "jwt",
                "token_type": "bearer",
                "expires_in": 3600,
                "user": {"email": "a@b.com"},
                "profile_completed": False,
            },
        )

    client = _mock_client(handler)
    client.access_token = "should-not-send"
    data = client.auth.login("a@b.com", "secret")
    assert seen_auth == [None]
    assert data["access_token"] == "jwt"


def test_refresh_on_401_retry() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/v1/auth/verify" and calls.count("/api/v1/auth/verify") == 1:
            return httpx.Response(401, json={"success": False, "error_code": "AUTH_1002", "message": "expired"})
        if request.url.path == "/api/v1/auth/refresh":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-jwt",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "user": {"email": "a@b.com"},
                    "profile_completed": True,
                },
            )
        if request.url.path == "/api/v1/auth/verify":
            return httpx.Response(200, json={"success": True, "email": "a@b.com"})
        return httpx.Response(404)

    saved: list[str] = []
    client = RoleMuleClient(
        "http://localhost:8000",
        access_token="old-jwt",
        on_token_refreshed=saved.append,
    )

    def _request(method, path, **kwargs):
        url = f"{client.base_url}{path}"
        req = httpx.Request(method, url, headers=client._headers(auth=kwargs.get("auth", True)))
        response = handler(req)
        if response.status_code == 401 and kwargs.get("_allow_refresh", True) and client.access_token:
            refreshed = client.refresh_token()
            token = refreshed.get("access_token")
            if token:
                client.access_token = str(token)
                if client.on_token_refreshed:
                    client.on_token_refreshed(client.access_token)
                return _request(method, path, **{**kwargs, "_allow_refresh": False})
        if response.is_success:
            return response
        from rolemule_client.errors import parse_error_response

        raise parse_error_response(response.status_code, response.json())

    client.request = _request  # type: ignore[method-assign]
    data = client.verify_token()
    assert data["success"] is True
    assert "new-jwt" in saved
    assert "/api/v1/auth/refresh" in calls


def test_create_pat_posts_body() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/tokens"
        assert request.method == "POST"
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "id": "pat-1",
                "name": "CI",
                "token_prefix": "rm_pat_ab",
                "token": "rm_pat_secret",
                "created_at": "2026-07-08T00:00:00Z",
            },
        )

    data = _mock_client(handler).auth.create_pat("CI", expires_days=14)
    assert seen[0] == {"name": "CI", "expires_days": 14}
    assert data["token"].startswith("rm_pat_")


def test_list_pats_get() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/tokens"
        assert request.method == "GET"
        return httpx.Response(200, json={"tokens": []})

    data = _mock_client(handler).auth.list_pats()
    assert data["tokens"] == []


def test_revoke_pat_delete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/auth/tokens/pat-9"
        assert request.method == "DELETE"
        return httpx.Response(200, json={"message": "Token revoked", "id": "pat-9"})

    data = _mock_client(handler).auth.revoke_pat("pat-9")
    assert data["message"] == "Token revoked"


def test_oauth_status_no_auth_header() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        assert request.url.path == "/api/v1/auth/oauth/status"
        return httpx.Response(200, json={"google_oauth_enabled": False})

    data = _mock_client(handler).auth.oauth_status()
    assert seen == [None]
    assert data["google_oauth_enabled"] is False

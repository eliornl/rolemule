"""Integration tests for personal access token endpoints."""

from __future__ import annotations

import uuid

import pytest

from main import app
from utils.auth import get_current_user, get_current_user_with_complete_profile

BASE = "/api/v1/auth"


def _clear_auth_overrides() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_complete_profile, None)


class TestPersonalAccessTokens:
    """POST/GET/DELETE /api/v1/auth/tokens and PAT authentication."""

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, api_client) -> None:
        resp = await api_client.post(f"{BASE}/tokens", json={"name": "CI token"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_list_revoke_flow(self, authed_client_with_user, api_client) -> None:
        create = await authed_client_with_user.post(
            f"{BASE}/tokens",
            json={"name": "Automation", "expires_days": 30},
        )
        assert create.status_code == 200, create.text
        body = create.json()
        assert body["name"] == "Automation"
        assert body["token"].startswith("ap_pat_")
        assert "token_prefix" in body
        token_id = body["id"]
        plaintext = body["token"]
        jwt_header = authed_client_with_user.headers["Authorization"]

        listed = await authed_client_with_user.get(f"{BASE}/tokens")
        assert listed.status_code == 200, listed.text
        tokens = listed.json()["tokens"]
        assert any(t["id"] == token_id for t in tokens)
        assert all("token" not in t for t in tokens)

        _clear_auth_overrides()
        verify = await api_client.get(
            f"{BASE}/verify",
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert verify.status_code == 200, verify.text
        assert verify.json().get("success") is True

        revoke = await api_client.delete(
            f"{BASE}/tokens/{token_id}",
            headers={"Authorization": jwt_header},
        )
        assert revoke.status_code == 200, revoke.text

        verify_after = await api_client.get(
            f"{BASE}/verify",
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert verify_after.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_unknown_returns_404(self, authed_client_with_user) -> None:
        resp = await authed_client_with_user.delete(f"{BASE}/tokens/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invalid_expiry_returns_422(self, authed_client_with_user) -> None:
        resp = await authed_client_with_user.post(
            f"{BASE}/tokens",
            json={"name": "Bad", "expires_days": 0},
        )
        assert resp.status_code == 422

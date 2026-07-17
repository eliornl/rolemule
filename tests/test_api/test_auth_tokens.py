"""Integration tests for personal access token endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import jwt
import pytest

from config.settings import get_security_settings

from main import app
from utils.auth import get_current_user, get_current_user_with_complete_profile

BASE = "/api/v1/auth"


def _user_id_from_client_headers(headers: dict) -> uuid.UUID:
    token = headers["Authorization"].split(" ", 1)[1]
    sec = get_security_settings()
    payload = jwt.decode(
        token,
        sec.jwt_config["secret_key"],
        algorithms=[sec.jwt_config["algorithm"]],
    )
    return uuid.UUID(payload["sub"])


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
        assert body["token"].startswith("rm_pat_")
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

    @pytest.mark.asyncio
    async def test_verify_invalid_pat_returns_401(self, api_client) -> None:
        _clear_auth_overrides()
        resp = await api_client.get(
            f"{BASE}/verify",
            headers={"Authorization": "Bearer rm_pat_notvalid"},
        )
        assert resp.status_code == 401
        assert resp.json().get("error_code") == "AUTH_1003"

    @pytest.mark.asyncio
    async def test_revoke_invalid_token_id_returns_422(self, authed_client_with_user) -> None:
        resp = await authed_client_with_user.delete(f"{BASE}/tokens/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_max_active_tokens_returns_422(self, authed_client_with_user) -> None:
        with patch("utils.personal_access_tokens.MAX_PATS_PER_USER", 1):
            first = await authed_client_with_user.post(
                f"{BASE}/tokens",
                json={"name": "One"},
            )
            assert first.status_code == 200, first.text
            second = await authed_client_with_user.post(
                f"{BASE}/tokens",
                json={"name": "Two"},
            )
            assert second.status_code == 422

    @pytest.mark.asyncio
    async def test_pat_endpoints_direct(self, authed_client_with_user) -> None:
        """Invoke PAT route handlers directly for coverage of response assembly."""
        from api.auth import (
            CreatePatRequest,
            create_personal_access_token_endpoint,
            list_personal_access_tokens_endpoint,
            revoke_personal_access_token_endpoint,
        )
        from tests.test_api.conftest import _NullSessionLocal

        user_id = _user_id_from_client_headers(authed_client_with_user.headers)
        current_user = {"id": user_id, "email": f"x@{user_id.hex[:6]}.com"}

        async with _NullSessionLocal() as db:
            created = await create_personal_access_token_endpoint(
                CreatePatRequest(name="Direct", expires_days=14),
                current_user,
                db,
            )
            assert created.token.startswith("rm_pat_")
            listed = await list_personal_access_tokens_endpoint(current_user, db)
            assert any(t["id"] == created.id for t in listed["tokens"])
            revoked = await revoke_personal_access_token_endpoint(created.id, current_user, db)
            assert revoked["id"] == created.id

    @pytest.mark.asyncio
    async def test_pat_endpoint_error_paths(self, authed_client_with_user) -> None:
        from api.auth import (
            CreatePatRequest,
            create_personal_access_token_endpoint,
            list_personal_access_tokens_endpoint,
            revoke_personal_access_token_endpoint,
        )
        from tests.test_api.conftest import _NullSessionLocal

        user_id = _user_id_from_client_headers(authed_client_with_user.headers)
        current_user = {"id": user_id, "email": f"err@{user_id.hex[:6]}.com"}

        async with _NullSessionLocal() as db:
            with patch(
                "utils.personal_access_tokens.create_personal_access_token",
                side_effect=ValueError("too many tokens"),
            ):
                with pytest.raises(Exception) as exc:
                    await create_personal_access_token_endpoint(
                        CreatePatRequest(name="X", expires_days=30),
                        current_user,
                        db,
                    )
                assert exc.value.status_code == 422

            with patch(
                "utils.personal_access_tokens.create_personal_access_token",
                side_effect=RuntimeError("db down"),
            ):
                with pytest.raises(Exception) as exc:
                    await create_personal_access_token_endpoint(
                        CreatePatRequest(name="Y", expires_days=30),
                        current_user,
                        db,
                    )
                assert exc.value.status_code == 500

            with patch(
                "utils.personal_access_tokens.list_personal_access_tokens",
                side_effect=RuntimeError("list fail"),
            ):
                with pytest.raises(Exception) as exc:
                    await list_personal_access_tokens_endpoint(current_user, db)
                assert exc.value.status_code == 500

            with patch(
                "utils.personal_access_tokens.revoke_personal_access_token",
                side_effect=RuntimeError("revoke fail"),
            ):
                with pytest.raises(Exception) as exc:
                    await revoke_personal_access_token_endpoint(str(uuid.uuid4()), current_user, db)
                assert exc.value.status_code == 500


def test_validator_field_values_helper() -> None:
    from api.auth import _validator_field_values

    assert _validator_field_values(None) == {}
    assert _validator_field_values({"k": "v"}) == {"k": "v"}

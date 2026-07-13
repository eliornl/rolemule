# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from applypilot_client.constants import API_V1_PREFIX


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================

class AuthResource:
    """Auth API resource (/api/v1/auth)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def login(self, email: str, password: str, *, remember_me: bool = False) -> Dict[str, Any]:
        return self._client.post_json(
            f"{API_V1_PREFIX}/auth/login",
            json={"email": email, "password": password, "remember_me": remember_me},
            auth=False,
        )

    def logout(self) -> None:
        self._client.post_json(f"{API_V1_PREFIX}/auth/logout", json={})

    def refresh(self) -> Dict[str, Any]:
        return self._client.post_json(f"{API_V1_PREFIX}/auth/refresh", json={})

    def verify(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/verify")

    def register(
        self,
        full_name: str,
        email: str,
        password: str,
        confirm_password: str,
    ) -> Dict[str, Any]:
        return self._client.post_json(
            f"{API_V1_PREFIX}/auth/register",
            json={
                "full_name": full_name,
                "email": email,
                "password": password,
                "confirm_password": confirm_password,
            },
            auth=False,
        )

    def verify_code(self, email: str, code: str) -> Dict[str, Any]:
        return self._client.post_json(
            f"{API_V1_PREFIX}/auth/verify-code",
            json={"email": email, "code": code},
            auth=False,
        )

    def resend_verification(self, email: str) -> Dict[str, Any]:
        return self._client.post_json(
            f"{API_V1_PREFIX}/auth/resend-verification",
            json={"email": email},
            auth=False,
        )

    def verification_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/verification-status")

    def extension_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/extension-status")

    def email_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/email-status", auth=False)

    def oauth_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/oauth/status", auth=False)

    def change_password(
        self,
        current_password: str,
        new_password: str,
        confirm_password: str,
    ) -> Dict[str, Any]:
        return self._client.put_json(
            f"{API_V1_PREFIX}/auth/change-password",
            json={
                "current_password": current_password,
                "new_password": new_password,
                "confirm_password": confirm_password,
            },
        )

    def create_pat(self, name: str, *, expires_days: Optional[int] = 90) -> Dict[str, Any]:
        return self._client.post_json(
            f"{API_V1_PREFIX}/auth/tokens",
            json={"name": name, "expires_days": expires_days},
        )

    def list_pats(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/auth/tokens")

    def revoke_pat(self, token_id: str) -> Dict[str, Any]:
        return self._client.delete_json(f"{API_V1_PREFIX}/auth/tokens/{token_id}")

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict

from applypilot_client.client import API_V1_PREFIX, ApplyPilotClient


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


class InterviewPrepResource:
    """Interview prep API resource (/api/v1/interview-prep)."""

    def __init__(self, client: ApplyPilotClient) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/interview-prep"

    def show(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/{session_id}")

    def status(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/{session_id}/status")

    def generate(self, session_id: str, *, regenerate: bool = False) -> Dict[str, Any]:
        params = {"regenerate": True} if regenerate else None
        return self._client.post_json(
            f"{self._prefix}/{session_id}/generate",
            json={},
            params=params,
        )

    def delete(self, session_id: str) -> None:
        self._client.delete_json(f"{self._prefix}/{session_id}")

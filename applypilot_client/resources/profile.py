# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Tuple, TYPE_CHECKING

from applypilot_client.constants import API_V1_PREFIX

if TYPE_CHECKING:
    from applypilot_client.client import ApplyPilotClient


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


class ProfileResource:
    """Profile API resource (/api/v1/profile)."""

    def __init__(self, client: ApplyPilotClient) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/profile"

    def show(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/")

    def status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/status")

    def complete(self) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/complete", json={})

    def update_basic_info(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/basic-info", json=payload)

    def update_work_experience(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/work-experience", json=payload)

    def update_education(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/education", json=payload)

    def update_skills(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/skills-qualifications", json=payload)

    def update_career_preferences(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/career-preferences", json=payload)

    def update_notifications(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.put_json(f"{self._prefix}/notifications", json=payload)

    def parse_resume(self, file_path: str) -> Dict[str, Any]:
        return self._client.post_multipart(f"{self._prefix}/parse-resume", "resume", file_path)

    def download_resume(self) -> Tuple[bytes, Dict[str, str]]:
        return self._client.download_bytes(f"{self._prefix}/resume")

    def delete_resume(self) -> Dict[str, Any]:
        return self._client.delete_json(f"{self._prefix}/resume")

    def api_key_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/api-key/status")

    def api_key_set(self, api_key: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/api-key", json={"api_key": api_key})

    def api_key_delete(self) -> Dict[str, Any]:
        return self._client.delete_json(f"{self._prefix}/api-key")

    def api_key_validate(self, api_key: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/api-key/validate", json={"api_key": api_key})

    def workflow_preferences_show(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/preferences")

    def workflow_preferences_set(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.patch_json(f"{self._prefix}/preferences", json=payload)

    def export_data(self) -> Tuple[bytes, Dict[str, str]]:
        return self._client.download_bytes(f"{self._prefix}/export")

    def clear_data(self) -> Dict[str, Any]:
        return self._client.delete_json(f"{self._prefix}/clear-data", json={"confirm": True})

    def delete_account(self, password: str) -> Dict[str, Any]:
        return self._client.delete_json(
            f"{self._prefix}/delete-account",
            json={"password": password},
        )

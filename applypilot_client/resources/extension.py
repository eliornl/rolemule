# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from applypilot_client.constants import API_V1_PREFIX

if TYPE_CHECKING:
    from applypilot_client.client import ApplyPilotClient


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


class ExtensionResource:
    """Chrome extension API resource (/api/v1/extension)."""

    def __init__(self, client: ApplyPilotClient) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/extension"

    def autofill_map(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /extension/autofill/map — map form fields to profile values."""
        return self._client.post_json(f"{self._prefix}/autofill/map", json=payload)

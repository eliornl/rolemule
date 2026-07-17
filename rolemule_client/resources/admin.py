# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from rolemule_client.constants import API_V1_PREFIX


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================

class AdminResource:
    """Admin and monitoring API resource (/api/v1/admin, /api/v1/cache)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/admin"

    def maintenance_status(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/maintenance")

    def set_maintenance(
        self,
        *,
        enabled: bool,
        message: Optional[str] = None,
        estimated_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"enabled": enabled}
        if message is not None:
            body["message"] = message
        if estimated_end is not None:
            body["estimated_end"] = estimated_end
        return self._client.post_json(f"{self._prefix}/maintenance", json=body)

    def clear_maintenance(self) -> Dict[str, Any]:
        return self._client.delete_json(f"{self._prefix}/maintenance")

    def metrics(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/metrics")

    def cache_stats(self) -> Dict[str, Any]:
        return self._client.get_json(f"{API_V1_PREFIX}/cache/stats")

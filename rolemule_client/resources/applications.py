# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from rolemule_client.constants import API_V1_PREFIX


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================

class ApplicationsResource:
    """Applications API resource (/api/v1/applications)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/applications"

    def get(self, application_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/{application_id}")

    def list(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        status_filter: Optional[str] = None,
        days: Optional[int] = None,
        company: Optional[str] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if status_filter:
            params["status_filter"] = status_filter
        if days is not None:
            params["days"] = days
        if company:
            params["company"] = company
        if search:
            params["search"] = search
        if sort:
            params["sort"] = sort
        return self._client.get_json(f"{self._prefix}/", params=params)

    def stats(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/stats/overview")

    def update_status(self, application_id: str, new_status: str) -> Dict[str, Any]:
        return self._client.patch_json(
            f"{self._prefix}/{application_id}/status",
            json={"new_status": new_status},
        )

    def update_notes(self, application_id: str, notes: str) -> Dict[str, Any]:
        return self._client.patch_json(
            f"{self._prefix}/{application_id}/notes",
            json={"notes": notes},
        )

    def delete(self, application_id: str) -> Dict[str, Any]:
        return self._client.delete_json(f"{self._prefix}/{application_id}")

    def download(self, application_id: str) -> Tuple[bytes, Dict[str, str]]:
        return self._client.download_bytes(f"{self._prefix}/{application_id}/download")

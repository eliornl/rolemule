# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from rolemule_client.constants import API_V1_PREFIX


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================

class CvOptimizerResource:
    """CV optimizer API resource (/api/v1/cv-optimizer)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/cv-optimizer"

    def start(
        self,
        session_id: str,
        *,
        max_iterations: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if max_iterations is not None:
            body["max_iterations"] = max_iterations
        if score_threshold is not None:
            body["score_threshold"] = score_threshold
        return self._client.post_json(f"{self._prefix}/{session_id}/start", json=body)

    def show(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/{session_id}")

    def status(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/{session_id}/status")

    def download_cv(self, session_id: str) -> Tuple[bytes, Dict[str, str]]:
        return self._client.download_bytes(f"{self._prefix}/{session_id}/download-cv")

    def clear(self, session_id: str) -> None:
        self._client.delete_json(f"{self._prefix}/{session_id}")

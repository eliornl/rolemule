# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict

from applypilot_client.client import API_V1_PREFIX, ApplyPilotClient


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


class ToolsResource:
    """Career tools API resource (/api/v1/tools)."""

    def __init__(self, client: ApplyPilotClient) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/tools"

    def followup_stages(self) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/followup-stages")

    def thank_you(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/thank-you", json=payload)

    def followup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/followup", json=payload)

    def salary_coach(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/salary-coach", json=payload)

    def rejection_analysis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/rejection-analysis", json=payload)

    def reference_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/reference-request", json=payload)

    def job_comparison(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/job-comparison", json=payload)

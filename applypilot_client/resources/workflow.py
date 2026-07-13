# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from applypilot_client.constants import API_V1_PREFIX


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================

def _http_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    trimmed = value.strip()
    if trimmed.lower().startswith(("http://", "https://")):
        return trimmed
    return None

class WorkflowResource:
    """Workflow API resource (/api/v1/workflow)."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._prefix = f"{API_V1_PREFIX}/workflow"

    def start(
        self,
        *,
        job_text: Optional[str] = None,
        job_file: Optional[str] = None,
        job_url: Optional[str] = None,
        source_url: Optional[str] = None,
        detected_title: Optional[str] = None,
        detected_company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a workflow from text, file upload, and/or posting URL metadata."""
        data: Dict[str, Any] = {}
        if job_text:
            data["job_text"] = job_text

        safe_job_url = _http_url(job_url)
        if safe_job_url:
            data["job_url"] = safe_job_url

        safe_source_url = _http_url(source_url)
        if safe_source_url:
            data["source_url"] = safe_source_url

        if detected_title:
            data["detected_title"] = detected_title
        if detected_company:
            data["detected_company"] = detected_company

        path = f"{self._prefix}/start"
        if job_file:
            return self._client.post_multipart(path, "job_file", job_file, data=data or None)
        return self._client.post_form(path, data=data)

    def get_status(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/status/{session_id}")

    def get_results(self, session_id: str) -> Dict[str, Any]:
        return self._client.get_json(f"{self._prefix}/results/{session_id}")

    def history(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        status_filter: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if status_filter:
            params["status_filter"] = status_filter
        if sort:
            params["sort"] = sort
        return self._client.get_json(f"{self._prefix}/history", params=params)

    def continue_workflow(self, session_id: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/continue/{session_id}", json={})

    def generate_documents(self, session_id: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/generate-documents/{session_id}", json={})

    def regenerate_cover_letter(self, session_id: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/regenerate-cover-letter/{session_id}", json={})

    def regenerate_resume(self, session_id: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/regenerate-resume/{session_id}", json={})

    def generate_interview_prep(self, session_id: str) -> Dict[str, Any]:
        return self._client.post_json(f"{self._prefix}/generate-interview-prep/{session_id}", json={})

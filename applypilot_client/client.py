# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple, Union

import httpx

from applypilot_client.errors import ApiClientError, parse_error_response

DEFAULT_TIMEOUT_SECONDS = 30.0
API_V1_PREFIX = "/api/v1"


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


class ApplyPilotClient:
    """
    Synchronous HTTP client for ApplyPilot API v1.

    Args:
        base_url: Server origin, e.g. http://localhost:8000
        access_token: Optional Bearer JWT
        timeout: Request timeout in seconds
        on_token_refreshed: Called with new access token after a successful refresh
    """

    def __init__(
        self,
        base_url: str,
        access_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        on_token_refreshed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.on_token_refreshed = on_token_refreshed

    def _headers(self, *, auth: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        _allow_refresh: bool = True,
    ) -> httpx.Response:
        """
        Send an HTTP request to the API.

        Args:
            method: HTTP method
            path: Path starting with / (e.g. /health or /api/v1/auth/verify)
            json: JSON body
            params: Query parameters
            data: Form fields
            files: Multipart files
            auth: Attach Bearer token when True
            _allow_refresh: Internal flag to prevent infinite refresh loops

        Returns:
            httpx.Response on success (2xx)

        Raises:
            ApiClientError: On API error responses and connection failures
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._headers(auth=auth),
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                )
        except httpx.ConnectError as exc:
            raise ApiClientError(
                message=f"Cannot connect to {self.base_url}: {exc}",
                status_code=0,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiClientError(
                message=f"Request timed out after {self.timeout}s",
                status_code=0,
            ) from exc

        if response.status_code == 401 and auth and _allow_refresh and self.access_token:
            try:
                refreshed = self.refresh_token()
                new_token = refreshed.get("access_token")
                if new_token:
                    self.access_token = str(new_token)
                    if self.on_token_refreshed:
                        self.on_token_refreshed(self.access_token)
                    return self.request(
                        method,
                        path,
                        json=json,
                        params=params,
                        data=data,
                        files=files,
                        auth=auth,
                        _allow_refresh=False,
                    )
            except ApiClientError:
                pass

        if response.is_success:
            return response

        try:
            body: Any = response.json()
        except Exception:
            body = response.text

        raise parse_error_response(response.status_code, body)

    def get_json(self, path: str, *, auth: bool = True, **kwargs: Any) -> Any:
        """GET and parse JSON body."""
        response = self.request("GET", path, auth=auth, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def post_json(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """POST JSON and parse response body."""
        response = self.request("POST", path, json=json or {}, auth=auth, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def put_json(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """PUT JSON and parse response body."""
        response = self.request("PUT", path, json=json or {}, auth=auth, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def patch_json(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """PATCH JSON and parse response body."""
        response = self.request("PATCH", path, json=json or {}, auth=auth, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def delete_json(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """DELETE with optional JSON body."""
        response = self.request("DELETE", path, json=json, auth=auth, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def post_multipart(
        self,
        path: str,
        field_name: str,
        file_path: str,
        *,
        auth: bool = True,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """POST a single file as multipart form data with optional form fields."""
        from pathlib import Path

        filename = Path(file_path).name
        with Path(file_path).open("rb") as handle:
            files: Dict[str, Tuple[str, Any, str]] = {
                field_name: (filename, handle, "application/octet-stream"),
            }
            response = self.request("POST", path, data=data, files=files, auth=auth)
        if not response.content:
            return {}
        return response.json()

    def post_form(
        self,
        path: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        """POST multipart or urlencoded form data."""
        response = self.request("POST", path, data=data, files=files, auth=auth)
        if not response.content:
            return {}
        return response.json()

    def download_bytes(self, path: str, *, auth: bool = True) -> Tuple[bytes, Dict[str, str]]:
        """GET binary response; returns body bytes and response headers."""
        response = self.request("GET", path, auth=auth)
        return response.content, dict(response.headers)

    def refresh_token(self) -> Dict[str, Any]:
        """POST /api/v1/auth/refresh — requires current Bearer token."""
        return self.post_json(f"{API_V1_PREFIX}/auth/refresh", json={}, auth=True, _allow_refresh=False)

    def health(self) -> Dict[str, Any]:
        """GET /health — server health (no auth)."""
        return self.get_json("/health", auth=False)

    def verify_token(self) -> Dict[str, Any]:
        """GET /api/v1/auth/verify — requires Bearer token."""
        return self.get_json(f"{API_V1_PREFIX}/auth/verify")

    @property
    def auth(self):
        """Auth API resource."""
        from applypilot_client.resources.auth import AuthResource

        return AuthResource(self)

    @property
    def profile(self):
        """Profile API resource."""
        from applypilot_client.resources.profile import ProfileResource

        return ProfileResource(self)

    @property
    def workflow(self):
        """Workflow API resource."""
        from applypilot_client.resources.workflow import WorkflowResource

        return WorkflowResource(self)

    @property
    def applications(self):
        """Applications API resource."""
        from applypilot_client.resources.applications import ApplicationsResource

        return ApplicationsResource(self)

    @property
    def interview_prep(self):
        """Interview prep API resource."""
        from applypilot_client.resources.interview_prep import InterviewPrepResource

        return InterviewPrepResource(self)

    @property
    def cv_optimizer(self):
        """CV optimizer API resource."""
        from applypilot_client.resources.cv_optimizer import CvOptimizerResource

        return CvOptimizerResource(self)

"""Tests for rolemule_client.resources.tools."""

from __future__ import annotations

import httpx

from rolemule_client.client import RoleMuleClient


def _mock_client(handler) -> RoleMuleClient:
    client = RoleMuleClient("http://localhost:8000", access_token="jwt")

    def _request(method, path, **kwargs):
        url = f"{client.base_url}{path}"
        headers = client._headers(auth=kwargs.get("auth", True))
        req = httpx.Request(method, url, headers=headers)
        if kwargs.get("json") is not None:
            req = httpx.Request(
                method,
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=kwargs["json"],
            )
        response = handler(req, kwargs)
        if response.is_success:
            return response
        from rolemule_client.errors import parse_error_response

        try:
            body = response.json()
        except Exception:
            body = response.text
        raise parse_error_response(response.status_code, body)

    client.request = _request  # type: ignore[method-assign]
    return client


def test_followup_stages_get() -> None:
    def handler(request: httpx.Request, _kwargs) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/tools/followup-stages"
        return httpx.Response(200, json={"stages": [{"value": "after_interview", "label": "After interview"}]})

    data = _mock_client(handler).tools.followup_stages()
    assert data["stages"][0]["value"] == "after_interview"


def test_thank_you_post_body() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/tools/thank-you"
        seen.append(kwargs["json"])
        return httpx.Response(200, json={"subject_line": "Thanks", "email_body": "Dear Jane..."})

    payload = {
        "interviewer_name": "Jane",
        "interview_type": "video",
        "company_name": "Acme",
        "job_title": "Engineer",
    }
    data = _mock_client(handler).tools.thank_you(payload)
    assert seen == [payload]
    assert data["subject_line"] == "Thanks"


def test_job_comparison_post_body() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert request.url.path == "/api/v1/tools/job-comparison"
        seen.append(kwargs["json"])
        return httpx.Response(200, json={"recommended_job": "Job A", "jobs_analysis": []})

    payload = {"jobs": [{"title": "A", "company": "X"}, {"title": "B", "company": "Y"}]}
    _mock_client(handler).tools.job_comparison(payload)
    assert seen == [payload]

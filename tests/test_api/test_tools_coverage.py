"""
Coverage tests for api/tools.py — helper functions and endpoint edge cases.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.tools import (
    _check_api_key_available,
    _get_application_context,
    _get_user_api_key,
    _get_user_uuid,
)
from tests.test_api.test_career_tools import (
    BASE,
    FOLLOWUP_RESULT,
    JOB_COMPARISON_RESULT,
    REFERENCE_RESULT,
    REJECTION_RESULT,
    SALARY_RESULT,
    THANK_YOU_RESULT,
    _api_key_patches,
)
from utils.cache import RateLimitResult


class TestToolsHelpers:
    def test_get_user_uuid_string_and_object(self) -> None:
        uid = uuid.uuid4()
        assert _get_user_uuid({"id": str(uid)}) == uid
        assert _get_user_uuid({"_id": uid}) == uid

    @pytest.mark.asyncio
    async def test_get_user_api_key_decrypts(self) -> None:
        uid = uuid.uuid4()
        user = MagicMock()
        user.gemini_api_key_encrypted = b"enc"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        with patch("api.tools.decrypt_api_key", return_value="sk-test"):
            key = await _get_user_api_key(mock_db, uid)
        assert key == "sk-test"

    @pytest.mark.asyncio
    async def test_get_user_api_key_decrypt_failure(self) -> None:
        uid = uuid.uuid4()
        user = MagicMock()
        user.gemini_api_key_encrypted = b"enc"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        with patch("api.tools.decrypt_api_key", side_effect=RuntimeError("bad key")):
            assert await _get_user_api_key(mock_db, uid) is None

    @pytest.mark.asyncio
    async def test_check_api_key_available_user_key(self) -> None:
        mock_db = AsyncMock()
        with patch("api.tools._get_user_api_key", AsyncMock(return_value="user-key")):
            assert await _check_api_key_available(mock_db, uuid.uuid4()) is True

    @pytest.mark.asyncio
    async def test_check_api_key_available_server_vertex(self) -> None:
        mock_db = AsyncMock()
        settings = MagicMock()
        settings.gemini_api_key = None
        settings.use_vertex_ai = True
        with (
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.settings", settings),
        ):
            assert await _check_api_key_available(mock_db, uuid.uuid4()) is True

    @pytest.mark.asyncio
    async def test_get_application_context_found(self) -> None:
        uid = uuid.uuid4()
        app_id = uuid.uuid4()
        app = MagicMock()
        app.job_title = "Engineer"
        app.company_name = "Co"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = app
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        ctx = await _get_application_context(mock_db, uid, str(app_id))
        assert ctx == {"job_title": "Engineer", "company_name": "Co"}

    @pytest.mark.asyncio
    async def test_get_application_context_invalid_uuid(self) -> None:
        mock_db = AsyncMock()
        assert await _get_application_context(mock_db, uuid.uuid4(), "bad-id") is None

    @pytest.mark.asyncio
    async def test_get_application_context_not_found(self) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        assert await _get_application_context(mock_db, uuid.uuid4(), str(uuid.uuid4())) is None


class TestToolsEndpointCoverage:
    @pytest.mark.asyncio
    async def test_thank_you_no_api_key(self, authed_client) -> None:
        with patch("api.tools._check_api_key_available", AsyncMock(return_value=False)):
            resp = await authed_client.post(
                f"{BASE}/thank-you",
                json={
                    "interviewer_name": "Sam",
                    "interview_type": "phone",
                    "company_name": "Co",
                    "job_title": "Eng",
                },
            )
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "VAL_2001"

    @pytest.mark.asyncio
    async def test_job_comparison_with_user_context(self, authed_client) -> None:
        patches = _api_key_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch("agents.job_comparison.JobComparisonAgent.compare", AsyncMock(return_value=JOB_COMPARISON_RESULT)),
        ):
            resp = await authed_client.post(
                f"{BASE}/job-comparison",
                json={
                    "jobs": [
                        {"title": "A", "company": "Co1", "description": "Desc1"},
                        {"title": "B", "company": "Co2", "description": "Desc2"},
                    ],
                    "user_context": {
                        "career_goals": "Leadership",
                        "priorities": "Remote",
                        "experience_years": 5,
                        "work_style": "Collaborative",
                        "location_preference": "Remote",
                        "salary_expectations": "$150k",
                    },
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_job_comparison_cache_hit(self, authed_client) -> None:
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=JOB_COMPARISON_RESULT)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
        ):
            resp = await authed_client.post(
                f"{BASE}/job-comparison",
                json={
                    "jobs": [
                        {"title": "A", "company": "Co1", "description": "D1"},
                        {"title": "B", "company": "Co2", "description": "D2"},
                    ],
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rejection_analysis_happy_path(self, authed_client) -> None:
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
            patch("agents.rejection_analyzer.RejectionAnalyzerAgent.analyze", AsyncMock(return_value=REJECTION_RESULT)),
        ):
            resp = await authed_client.post(
                f"{BASE}/rejection-analysis",
                json={"rejection_email": "Dear John, we regret to inform you..."},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reference_request_happy_path(self, authed_client) -> None:
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
            patch(
                "agents.reference_request_writer.ReferenceRequestWriterAgent.generate",
                AsyncMock(return_value=REFERENCE_RESULT),
            ),
        ):
            resp = await authed_client.post(
                f"{BASE}/reference-request",
                json={"reference_name": "Bob", "reference_relationship": "Manager"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_salary_coach_happy_path(self, authed_client) -> None:
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
            patch("agents.salary_coach.SalaryCoachAgent.generate_strategy", AsyncMock(return_value=SALARY_RESULT)),
        ):
            resp = await authed_client.post(
                f"{BASE}/salary-coach",
                json={
                    "job_title": "Engineer",
                    "company_name": "TechCorp",
                    "offered_salary": "$155,000",
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_followup_rate_limited(self, authed_client) -> None:
        blocked = RateLimitResult(allowed=False, limit=10, remaining=0, reset_seconds=3600)
        with patch("api.tools.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            resp = await authed_client.post(
                f"{BASE}/followup",
                json={"stage": "after_application", "company_name": "Co", "job_title": "Eng"},
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_thank_you_with_application_id(self, authed_client_with_user) -> None:
        # application_id path enriches context via _get_application_context
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=None)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
            patch("agents.thank_you_writer.ThankYouWriterAgent.generate", AsyncMock(return_value=THANK_YOU_RESULT)),
            patch(
                "api.tools._get_application_context",
                AsyncMock(return_value={"job_title": "From App", "company_name": "From Co"}),
            ),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/thank-you",
                json={
                    "interviewer_name": "Sam",
                    "interview_type": "phone",
                    "application_id": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_followup_cache_hit(self, authed_client) -> None:
        with (
            patch("api.tools._check_api_key_available", AsyncMock(return_value=True)),
            patch("api.tools._get_user_api_key", AsyncMock(return_value=None)),
            patch("api.tools.get_cached_tool_result", AsyncMock(return_value=FOLLOWUP_RESULT)),
            patch("api.tools.cache_tool_result", AsyncMock(return_value=None)),
        ):
            resp = await authed_client.post(
                f"{BASE}/followup",
                json={"stage": "after_interview", "company_name": "Co", "job_title": "Eng"},
            )
        assert resp.status_code == 200

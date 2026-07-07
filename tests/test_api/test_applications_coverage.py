"""
Coverage tests for api/applications.py — helpers, formatters, error paths, edge cases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from api.applications import (
    StatusUpdateRequest,
    _add_dict_section,
    _format_application_response,
    _generate_application_report,
    get_user_uuid,
    list_applications,
    safe_items,
)
from main import app
from models.database import ApplicationStatus, JobApplication, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal, _make_test_jwt
from tests.test_api.test_applications_extended import (
    BASE,
    _cleanup_user,
    _client_for,
    _create_complete_user,
    _seed_application,
    _clear_overrides,
)
from utils.auth import get_current_user_with_complete_profile

# ---------------------------------------------------------------------------
# Unit tests — pure helpers
# ---------------------------------------------------------------------------


class TestApplicationHelpers:
    def test_safe_items_non_dict(self) -> None:
        assert safe_items(None) == []
        assert safe_items("x") == []

    def test_safe_items_dict(self) -> None:
        assert safe_items({"a": 1}) == [("a", 1)]

    def test_get_user_uuid_from_id_string(self) -> None:
        uid = uuid.uuid4()
        assert get_user_uuid({"id": str(uid)}) == uid

    def test_get_user_uuid_from_id_object(self) -> None:
        uid = uuid.uuid4()
        assert get_user_uuid({"id": uid}) == uid

    def test_get_user_uuid_from_underscore_id(self) -> None:
        uid = uuid.uuid4()
        assert get_user_uuid({"_id": str(uid)}) == uid

    def test_status_update_request_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            StatusUpdateRequest(new_status="not-a-real-status")

    def test_add_dict_section_list_and_dict(self) -> None:
        lines: list[str] = []
        _add_dict_section(
            lines,
            {
                "skills": ["Python", "Go"],
                "meta": {"level": "senior"},
                "empty": "",
                "score": 42,
            },
        )
        text = "\n".join(lines)
        assert "Skills:" in text
        assert "- Python" in text
        assert "Meta:" in text
        assert "level: senior" in text
        assert "Score: 42" in text

    @pytest.mark.asyncio
    async def test_generate_application_report_full(self) -> None:
        applied = datetime(2026, 1, 15, tzinfo=timezone.utc)
        report = await _generate_application_report(
            {"job_title": "Engineer", "company_name": "Acme", "status": "processing", "applied_date": applied},
            {
                "workflow_status": "completed",
                "job_analysis": {"title": "Engineer", "requirements": ["Python"]},
                "company_research": {"website": "https://acme.example"},
                "profile_matching": {
                    "executive_summary": {
                        "recommendation": "Apply",
                        "confidence": "high",
                        "one_line_verdict": "Strong fit",
                    },
                    "final_scores": {"overall_match_score": 0.85},
                },
                "resume_recommendations": {"tips": ["Add metrics"]},
                "cover_letter": {"content": "Dear team,"},
            },
            {},
        )
        assert "JOB APPLICATION REPORT" in report
        assert "COMPLETED" in report
        assert "APPLIED DATE: 2026-01-15" in report
        assert "JOB ANALYSIS" in report
        assert "COMPANY RESEARCH" in report
        assert "PROFILE MATCHING" in report
        assert "Overall Match Score: 85.0%" in report
        assert "RESUME RECOMMENDATIONS" in report
        assert "COVER LETTER" in report
        assert "Dear team," in report

    @pytest.mark.asyncio
    async def test_format_application_response_workflow_fallbacks(self) -> None:
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        app = JobApplication(
            id=uuid.uuid4(),
            user_id=uid,
            session_id=session_id,
            job_title="",
            company_name="",
            status=ApplicationStatus.PROCESSING.value,
            match_score=None,
            created_at=now,
            updated_at=now,
        )
        ws = WorkflowSession(
            session_id=session_id,
            user_id=uid,
            workflow_status="completed",
            job_analysis={"job_title": "From Analysis", "company_name": "From Co"},
            profile_matching={
                "final_scores": {"overall_fit_score": 0.72},
            },
        )
        mock_db = AsyncMock()
        result = await _format_application_response(app, mock_db, {session_id: ws})
        assert result.job_title == "From Analysis"
        assert result.company_name == "From Co"
        assert result.status == ApplicationStatus.COMPLETED.value
        assert result.match_score == 0.72

    @pytest.mark.asyncio
    async def test_format_application_response_db_lookup_and_failed_status(self) -> None:
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        app = JobApplication(
            id=uuid.uuid4(),
            user_id=uid,
            session_id=session_id,
            job_title="Title",
            company_name="Co",
            status=ApplicationStatus.PROCESSING.value,
            created_at=now,
            updated_at=now,
        )
        ws = WorkflowSession(
            session_id=session_id,
            user_id=uid,
            workflow_status="failed",
            profile_matching={"overall_score": 0.5},
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ws
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        result = await _format_application_response(app, mock_db)
        assert result.status == ApplicationStatus.FAILED.value
        assert result.match_score == 0.5

    @pytest.mark.asyncio
    async def test_format_application_response_session_fetch_error(self) -> None:
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        app = JobApplication(
            id=uuid.uuid4(),
            user_id=uid,
            session_id=session_id,
            job_title="T",
            company_name="C",
            status="completed",
            created_at=now,
            updated_at=now,
        )
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db error"))
        result = await _format_application_response(app, mock_db)
        assert result.job_title == "T"


# ---------------------------------------------------------------------------
# Integration — additional endpoint branches
# ---------------------------------------------------------------------------


class TestApplicationsCoverageIntegration:
    @pytest.mark.asyncio
    async def test_list_hides_workflow_failed_rows(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        failed_sid = str(uuid.uuid4())
        try:
            await _seed_application(
                uid,
                job_title="Failed Run",
                company_name="FailCo",
                status="processing",
                session_id=failed_sid,
            )
            async with _NullSessionLocal() as session:
                ws = await session.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == failed_sid)
                )
                row = ws.scalar_one()
                row.workflow_status = "failed"
                await session.commit()
            resp = await client.get(f"{BASE}/")
            titles = [a.get("job_title") for a in resp.json()["applications"]]
            assert "Failed Run" not in titles
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_list_sort_updated_desc_and_title_asc(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="Zebra Role", company_name="Co")
            await _seed_application(uid, job_title="Alpha Role", company_name="Co")
            for sort in ("updated_desc", "title_asc", "created_asc"):
                resp = await client.get(f"{BASE}/", params={"sort": sort})
                assert resp.status_code == 200
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_status_accepted_sets_response_date(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="R", company_name="C", status="applied")
            resp = await client.patch(f"{BASE}/{app_id}/status", json={"new_status": "accepted"})
            assert resp.status_code == 200
            assert resp.json().get("response_date") is not None
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_status_rejected_sets_response_date(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            app_id = await _seed_application(uid, job_title="R", company_name="C", status="applied")
            resp = await client.patch(f"{BASE}/{app_id}/status", json={"new_status": "rejected"})
            assert resp.status_code == 200
            assert resp.json().get("response_date") is not None
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_notes_not_found(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            resp = await client.patch(
                f"{BASE}/{uuid.uuid4()}/notes",
                json={"notes": "nope"},
            )
            assert resp.status_code == 404
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_status_not_found(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            resp = await client.patch(
                f"{BASE}/{uuid.uuid4()}/status",
                json={"new_status": "applied"},
            )
            assert resp.status_code == 404
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_download_workflow_session_not_found(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        session_id = str(uuid.uuid4())
        try:
            app_id = await _seed_application(
                uid,
                job_title="Ghost",
                company_name="Co",
                session_id=session_id,
            )
            async with _NullSessionLocal() as session:
                await session.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
                from sqlalchemy import delete

                await session.execute(
                    delete(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
                await session.commit()
            resp = await client.get(f"{BASE}/{app_id}/download")
            assert resp.status_code == 404
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_download_invalid_uuid(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            resp = await client.get(f"{BASE}/not-a-uuid/download")
            assert resp.status_code == 422
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_stats_with_zero_tracked_funnel(self) -> None:
        uid, email = await _create_complete_user()
        client = await _client_for(uid, email)
        try:
            await _seed_application(uid, job_title="Only", company_name="Co", status="completed")
            resp = await client.get(f"{BASE}/stats/overview")
            assert resp.status_code == 200
            assert resp.json()["response_rate"] == 0.0
        finally:
            await client.aclose()
            _clear_overrides()
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_list_applications_internal_error(self) -> None:
        uid = uuid.uuid4()
        email = f"err_{uid.hex[:8]}@example.com"

        async def _boom():
            return {"id": str(uid), "email": email, "profile_completed": True}

        app.dependency_overrides[get_current_user_with_complete_profile] = _boom
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        from utils.database import get_database

        async def _broken():
            yield mock_db

        app.dependency_overrides[get_database] = _broken
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {_make_test_jwt(str(uid), email)}"},
        ) as client:
            resp = await client.get(f"{BASE}/")
        assert resp.status_code == 500
        from tests.test_api.conftest import _get_null_pool_db

        app.dependency_overrides[get_database] = _get_null_pool_db
        app.dependency_overrides.pop(get_current_user_with_complete_profile, None)

    @pytest.mark.asyncio
    async def test_list_applications_direct_call(self) -> None:
        """Exercise list_applications coroutine directly with real DB session."""
        uid, email = await _create_complete_user()
        await _seed_application(uid, job_title="Direct", company_name="CallCo")
        async with _NullSessionLocal() as db:
            result = await list_applications(
                current_user={"id": str(uid), "email": email},
                db=db,
                page=1,
                per_page=10,
                status_filter=None,
                days=None,
                company=None,
                search="direct",
                sort="created_desc",
            )
            assert result.total >= 1
        await _cleanup_user(uid)

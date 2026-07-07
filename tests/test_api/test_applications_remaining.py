"""
Direct-handler coverage for remaining api/applications.py gaps.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from api.applications import (
    NotesUpdateRequest,
    StatusUpdateRequest,
    delete_application,
    get_application_download,
    get_application_stats,
    list_applications,
    update_application_notes,
    update_application_status,
)
from models.database import ApplicationStatus, JobApplication, WorkflowSession
from tests.test_api.test_applications_extended import (
    _cleanup_user,
    _create_complete_user,
    _seed_application,
)
from tests.test_api.conftest import _NullSessionLocal


def _user(uid: uuid.UUID, email: str) -> dict:
    return {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Apps User",
        "profile_completed": True,
    }


class TestApplicationsDirectHandlers:
    @pytest.mark.asyncio
    async def test_list_with_filters_and_company(self) -> None:
        uid, email = await _create_complete_user()
        try:
            await _seed_application(uid, job_title="Alpha Role", company_name="Acme Corp")
            await _seed_application(uid, job_title="Beta Role", company_name="Other Inc")
            async with _NullSessionLocal() as db:
                by_status = await list_applications(
                    current_user=_user(uid, email),
                    db=db,
                    page=1,
                    per_page=20,
                    status_filter=ApplicationStatus.COMPLETED.value,
                    days=30,
                    company="acme",
                    search=None,
                    sort="company_asc",
                )
                by_search = await list_applications(
                    current_user=_user(uid, email),
                    db=db,
                    page=1,
                    per_page=20,
                    status_filter=None,
                    days=None,
                    company=None,
                    search="beta",
                    sort="title_asc",
                )
            assert by_status.total >= 1
            assert any("Acme" in (a.company_name or "") for a in by_status.applications)
            assert any("Beta" in (a.job_title or "") for a in by_search.applications)
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_status_applied_and_interview_dates(self) -> None:
        uid, email = await _create_complete_user()
        try:
            app_id = await _seed_application(uid, job_title="Role", company_name="Co", status="completed")
            async with _NullSessionLocal() as db:
                applied = await update_application_status(
                    application_id=str(app_id),
                    status_update=StatusUpdateRequest(new_status=ApplicationStatus.APPLIED.value),
                    current_user=_user(uid, email),
                    db=db,
                )
                assert applied.applied_date is not None
                interview = await update_application_status(
                    application_id=str(app_id),
                    status_update=StatusUpdateRequest(new_status=ApplicationStatus.INTERVIEW.value),
                    current_user=_user(uid, email),
                    db=db,
                )
                assert interview.response_date is not None
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_update_notes_direct(self) -> None:
        uid, email = await _create_complete_user()
        try:
            app_id = await _seed_application(uid, job_title="Role", company_name="Co")
            async with _NullSessionLocal() as db:
                resp = await update_application_notes(
                    application_id=str(app_id),
                    notes_update=NotesUpdateRequest(notes="Follow up next week"),
                    current_user=_user(uid, email),
                    db=db,
                )
            assert resp.notes == "Follow up next week"
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_delete_application_direct(self) -> None:
        uid, email = await _create_complete_user()
        try:
            app_id = await _seed_application(uid, job_title="Delete Me", company_name="Co")
            async with _NullSessionLocal() as db:
                result = await delete_application(
                    application_id=str(app_id),
                    current_user=_user(uid, email),
                    db=db,
                )
            assert "deleted" in result["message"].lower()
            async with _NullSessionLocal() as db:
                row = await db.execute(select(JobApplication).where(JobApplication.id == app_id))
                assert row.scalar_one().deleted_at is not None
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_stats_with_interview_funnel(self) -> None:
        uid, email = await _create_complete_user()
        try:
            await _seed_application(uid, job_title="Applied", company_name="Co", status="applied")
            await _seed_application(uid, job_title="Interview", company_name="Co2", status="interview")
            async with _NullSessionLocal() as db:
                stats = await get_application_stats(current_user=_user(uid, email), db=db)
            assert stats.applied >= 2
            assert stats.interviews >= 1
            assert stats.response_rate > 0
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_download_application_report_direct(self) -> None:
        uid, email = await _create_complete_user()
        session_id = str(uuid.uuid4())
        try:
            app_id = await _seed_application(
                uid,
                job_title="Engineer",
                company_name="Acme",
                session_id=session_id,
            )
            async with _NullSessionLocal() as db:
                ws = (await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )).scalar_one()
                ws.job_analysis = {"job_title": "Engineer", "company_name": "Acme"}
                ws.profile_matching = {
                    "executive_summary": {"recommendation": "Apply"},
                    "final_scores": {"overall_match_score": 0.8},
                }
                await db.commit()
                resp = await get_application_download(
                    application_id=str(app_id),
                    current_user=_user(uid, email),
                    db=db,
                )
            assert b"JOB APPLICATION REPORT" in resp.body
            assert "Acme" in resp.headers.get("content-disposition", "")
        finally:
            await _cleanup_user(uid)

    @pytest.mark.asyncio
    async def test_list_internal_error_direct(self) -> None:
        uid, email = await _create_complete_user()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db fail"))
        try:
            from utils.error_responses import APIError

            with pytest.raises(APIError) as exc:
                await list_applications(
                    current_user=_user(uid, email),
                    db=mock_db,
                    page=1,
                    per_page=10,
                    status_filter=None,
                    days=None,
                    company=None,
                    search=None,
                    sort="created_desc",
                )
            assert exc.value.status_code == 500
        finally:
            await _cleanup_user(uid)

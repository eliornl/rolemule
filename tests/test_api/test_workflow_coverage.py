"""
Targeted coverage tests for api/workflow.py.

Invokes route handlers and background helpers directly so async line coverage
is attributed reliably (HTTP-only tests can under-report FastAPI coroutines).
"""

from __future__ import annotations

import io
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Response, UploadFile
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from api.workflow import (
    WorkflowStartRequest,
    _agent_error_message,
    _execute_workflow_background,
    _continue_workflow_background,
    _generate_documents_background,
    _find_duplicate_active_application,
    _job_text_from_uploaded_file,
    _raise_if_agent_soft_failure,
    _revert_workflow_session_after_duplicate_job_constraint,
    _update_job_application_with_final_state,
    _update_workflow_session_with_state,
    continue_workflow_after_gate,
    execute_workflow_task,
    generate_documents,
    generate_interview_prep,
    get_workflow_results,
    get_workflow_status,
    list_workflow_history,
    regenerate_cover_letter,
    regenerate_resume,
    start_workflow,
    WorkflowTaskPayload,
)
from models.database import (
    ApplicationStatus,
    JobApplication,
    User,
    UserProfile,
    UserWorkflowPreferences,
    WorkflowSession,
)
from tests.test_api.conftest import _NullSessionLocal
from tests.test_api.test_workflow_extended import (
    LONG_JOB_TEXT,
    _ensure_user,
    _make_docx_bytes,
    _mock_settings,
    _setup_complete_user,
)
from utils.error_responses import APIError, ErrorCode
from utils.cache import RateLimitResult
from workflows.state_schema import WorkflowPhase, WorkflowStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def wf_user_bundle():
    """Real user + profile row for direct handler calls."""
    uid = uuid.uuid4()
    email = f"cov-{uid.hex[:10]}@example.com"
    await _ensure_user(uid, email=email)
    await _setup_complete_user(uid, email=email)
    user_dict = {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Coverage User",
        "auth_method": "local",
        "profile_completed": True,
        "profile_completion_percentage": 100,
    }
    yield uid, email, user_dict


def _user_dict(uid: uuid.UUID, email: str) -> Dict[str, Any]:
    return {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Coverage User",
        "auth_method": "local",
        "profile_completed": True,
        "profile_completion_percentage": 100,
    }


async def _session_for_user(uid: uuid.UUID):
    async with _NullSessionLocal() as db:
        yield db


# ---------------------------------------------------------------------------
# Helpers / validators
# ---------------------------------------------------------------------------


class TestWorkflowCoverageHelpers:
    def test_docx_extracted_text_too_short(self):
        short = "x" * 20
        with patch("api.workflow.extract_text_from_docx", return_value=short):
            with pytest.raises(Exception):
                _job_text_from_uploaded_file(b"PK\x03\x04", ".docx")

    def test_raise_if_agent_soft_failure_non_dict(self):
        _raise_if_agent_soft_failure([])  # line 211

    def test_workflow_start_request_rejects_bad_url(self):
        with pytest.raises(Exception):
            WorkflowStartRequest(job_url="ftp://example.com/job")

    @pytest.mark.asyncio
    async def test_revert_duplicate_constraint_missing_session(self):
        async with _NullSessionLocal() as db:
            result = await _revert_workflow_session_after_duplicate_job_constraint(
                db, str(uuid.uuid4())
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_find_duplicate_by_title_company(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    job_title="  Staff Engineer  ",
                    company_name="  Globex  ",
                    status="completed",
                )
            )
            await db.commit()
            dup = await _find_duplicate_active_application(
                db, uid, None, "staff engineer", "globex", None
            )
            assert dup is not None

    @pytest.mark.asyncio
    async def test_find_duplicate_returns_none(self):
        uid = uuid.uuid4()
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            assert await _find_duplicate_active_application(db, uid, None, None, None, None) is None

    def test_agent_error_message_debug(self):
        assert "boom" in _agent_error_message(Exception("boom"), "fb", debug=True)


# ---------------------------------------------------------------------------
# start_workflow — direct handler
# ---------------------------------------------------------------------------


class TestStartWorkflowDirect:
    @pytest.mark.asyncio
    async def test_start_manual_success_background_tasks(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        bg = BackgroundTasks()
        resp = Response()
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(return_value=True)
        mock_rc.delete = AsyncMock()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    background_tasks=bg,
                    response=resp,
                    request=None,
                    job_file=None,
                    job_url=None,
                    job_text=LONG_JOB_TEXT,
                    detected_title_form="Role A",
                    detected_company_form="Co A",
                    source_form=None,
                    source_url_form=None,
                    current_user=user_dict,
                    db=db,
                )
        assert result.session_id
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_start_json_body_with_job_url(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        req = WorkflowStartRequest(
            job_text=LONG_JOB_TEXT,
            job_url="https://example.com/careers/role-1",
        )
        bg = BackgroundTasks()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    background_tasks=bg,
                    response=Response(),
                    request=req,
                    job_file=None,
                    job_url=None,
                    job_text=None,
                    detected_title_form=None,
                    detected_company_form=None,
                    source_form=None,
                    source_url_form=None,
                    current_user=user_dict,
                    db=db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_extension_source(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        bg = BackgroundTasks()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    background_tasks=bg,
                    response=Response(),
                    request=None,
                    job_file=None,
                    job_url=None,
                    job_text=LONG_JOB_TEXT,
                    detected_title_form=None,
                    detected_company_form=None,
                    source_form="extension",
                    source_url_form="https://example.com/jobs/1",
                    current_user=user_dict,
                    db=db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_cloud_tasks_enqueue(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        bg = BackgroundTasks()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch(
                 "config.settings.get_settings",
                 return_value=_mock_settings(use_cloud_tasks=True),
             ), \
             patch("api.workflow.enqueue_workflow_task", AsyncMock()) as enq:
            async with _NullSessionLocal() as db:
                await start_workflow(
                    background_tasks=bg,
                    response=Response(),
                    request=None,
                    job_file=None,
                    job_url=None,
                    job_text=LONG_JOB_TEXT,
                    detected_title_form=None,
                    detected_company_form=None,
                    source_form=None,
                    source_url_form=None,
                    current_user=user_dict,
                    db=db,
                )
        enq.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_redis_lock_contention(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(return_value=False)
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=None,
                        job_url=None,
                        job_text=LONG_JOB_TEXT,
                        detected_title_form=None,
                        detected_company_form=None,
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )

    @pytest.mark.asyncio
    async def test_start_file_too_large(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        big = b"x" * (6 * 1024 * 1024)
        upload = UploadFile(filename="job.txt", file=io.BytesIO(big))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=upload,
                        job_url=None,
                        job_text=None,
                        detected_title_form=None,
                        detected_company_form=None,
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )

    @pytest.mark.asyncio
    async def test_start_txt_invalid_utf8_upload(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        upload = UploadFile(filename="job.txt", file=io.BytesIO(b"\xff\xfe"))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=upload,
                        job_url=None,
                        job_text=None,
                        detected_title_form=None,
                        detected_company_form=None,
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )

    @pytest.mark.asyncio
    async def test_start_missing_profile(self):
        uid = uuid.uuid4()
        email = f"noprof-{uid.hex[:8]}@example.com"
        await _ensure_user(uid, email=email)
        user_dict = _user_dict(uid, email)
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=None,
                        job_url=None,
                        job_text=LONG_JOB_TEXT,
                        detected_title_form=None,
                        detected_company_form=None,
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )

    @pytest.mark.asyncio
    async def test_start_byok_decrypt_failure(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            await db.commit()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("utils.encryption.decrypt_api_key", side_effect=ValueError("bad key")), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    background_tasks=BackgroundTasks(),
                    response=Response(),
                    request=None,
                    job_file=None,
                    job_url=None,
                    job_text=LONG_JOB_TEXT,
                    detected_title_form=None,
                    detected_company_form=None,
                    source_form=None,
                    source_url_form=None,
                    current_user=user_dict,
                    db=db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_with_workflow_preferences(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        async with _NullSessionLocal() as db:
            existing = await db.execute(
                select(UserWorkflowPreferences).where(
                    UserWorkflowPreferences.user_id == uid
                )
            )
            prefs = existing.scalar_one_or_none()
            if prefs is None:
                db.add(
                    UserWorkflowPreferences(
                        id=uuid.uuid4(),
                        user_id=uid,
                        workflow_gate_threshold=0.6,
                        auto_generate_documents=True,
                        preferred_provider="ollama",
                    )
                )
            else:
                prefs.workflow_gate_threshold = 0.6
                prefs.auto_generate_documents = True
                prefs.preferred_provider = "ollama"
            await db.commit()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    background_tasks=BackgroundTasks(),
                    response=Response(),
                    request=None,
                    job_file=None,
                    job_url=None,
                    job_text=LONG_JOB_TEXT,
                    detected_title_form=None,
                    detected_company_form=None,
                    source_form=None,
                    source_url_form=None,
                    current_user=user_dict,
                    db=db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_duplicate_releases_redis_lock(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        other_sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Dup Role",
                    company_name="Dup Co",
                    status="completed",
                )
            )
            await db.commit()
        mock_rc = AsyncMock()
        mock_rc.delete = AsyncMock()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError) as exc:
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=None,
                        job_url=None,
                        job_text=LONG_JOB_TEXT,
                        detected_title_form="Dup Role",
                        detected_company_form="Dup Co",
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )
        assert exc.value.error_code == ErrorCode.RESOURCE_ALREADY_EXISTS
        mock_rc.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_unhandled_exception_releases_lock(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(return_value=True)
        mock_rc.delete = AsyncMock()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch(
                 "api.workflow._find_duplicate_active_application",
                 AsyncMock(side_effect=RuntimeError("db down")),
             ):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        background_tasks=BackgroundTasks(),
                        response=Response(),
                        request=None,
                        job_file=None,
                        job_url=None,
                        job_text=LONG_JOB_TEXT,
                        detected_title_form=None,
                        detected_company_form=None,
                        source_form=None,
                        source_url_form=None,
                        current_user=user_dict,
                        db=db,
                    )
        assert mock_rc.delete.await_count >= 1


# ---------------------------------------------------------------------------
# Status / results / history — direct
# ---------------------------------------------------------------------------


class TestWorkflowEndpointsDirect:
    @pytest.mark.asyncio
    async def test_get_status_db_in_progress_caches(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    current_phase=WorkflowPhase.JOB_ANALYSIS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)), \
             patch("api.workflow.cache_workflow_state", AsyncMock()) as cache_mock:
            async with _NullSessionLocal() as db:
                out = await get_workflow_status(sid, user_dict, db)
        assert out.progress_percentage >= 0
        cache_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_status_internal_error(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)), \
             patch(
                 "api.workflow.get_user_uuid",
                 side_effect=RuntimeError("bad"),
             ):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await get_workflow_status(str(uuid.uuid4()), user_dict, db)

    @pytest.mark.asyncio
    async def test_get_results_full(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "Eng", "company_name": "Co"},
                    company_research={"industry": "Tech"},
                    profile_matching={"final_scores": {"overall_fit": 0.5}},
                    resume_recommendations={"comprehensive_advice": {}},
                    cover_letter={"content": "Hi"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status="completed",
                    job_url="https://example.com/j",
                    notes="note",
                )
            )
            await db.commit()
        async with _NullSessionLocal() as db:
            out = await get_workflow_results(sid, user_dict, db)
        assert out.application_id
        assert out.notes == "note"

    @pytest.mark.asyncio
    async def test_get_results_internal_error(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_user_uuid", side_effect=RuntimeError("x")):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await get_workflow_results(str(uuid.uuid4()), user_dict, db)

    @pytest.mark.asyncio
    async def test_list_history_sort_variants(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        async with _NullSessionLocal() as db:
            out = await list_workflow_history(
                user_dict, db, page=1, per_page=5, status_filter=None, sort="updated_desc"
            )
        assert out.page == 1

    @pytest.mark.asyncio
    async def test_list_history_error(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_user_uuid", side_effect=RuntimeError("x")):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await list_workflow_history(user_dict, db)


# ---------------------------------------------------------------------------
# Regenerate / interview prep — direct
# ---------------------------------------------------------------------------


class TestRegenerateDirect:
    async def _completed_session(self, uid: uuid.UUID) -> str:
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "Eng", "company_name": "Co"},
                    profile_matching={"final_scores": {"overall_fit": 0.7}},
                    company_research={"industry": "Tech"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        return sid

    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_direct(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(return_value={"cover_letter": {"content": "New"}})
        resp = Response()
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.cover_letter_writer.CoverLetterWriterAgent", return_value=mock_agent):
            async with _NullSessionLocal() as db:
                out = await regenerate_cover_letter(sid, resp, user_dict, db)
        assert out.cover_letter["content"] == "New"

    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_failure(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        with patch("utils.llm_client.get_gemini_client", AsyncMock(side_effect=RuntimeError("llm"))):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_cover_letter(sid, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_regenerate_resume_direct(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(
            return_value={"resume_recommendations": {"comprehensive_advice": {"quick_wins": []}}}
        )
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.resume_advisor.ResumeAdvisorAgent", return_value=mock_agent):
            async with _NullSessionLocal() as db:
                out = await regenerate_resume(sid, Response(), user_dict, db)
        assert "result" in out.model_dump()

    @pytest.mark.asyncio
    async def test_regenerate_resume_rate_limit(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        blocked = RateLimitResult(allowed=False, limit=5, remaining=0, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_resume(sid, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_generate_interview_prep_direct(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(
            return_value={"response": '{"interview_stages": []}', "filtered": False}
        )
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
            async with _NullSessionLocal() as db:
                out = await generate_interview_prep(sid, Response(), user_dict, db)
        assert out.result

    @pytest.mark.asyncio
    async def test_generate_interview_prep_parse_fallback(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value={"response": "not json", "filtered": False})
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
            async with _NullSessionLocal() as db:
                out = await generate_interview_prep(sid, Response(), user_dict, db)
        assert out.result.get("parse_error") or out.result.get("raw_response")

    @pytest.mark.asyncio
    async def test_generate_interview_prep_rate_limit(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = await self._completed_session(uid)
        blocked = RateLimitResult(allowed=False, limit=5, remaining=0, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_interview_prep(sid, Response(), user_dict, db)


# ---------------------------------------------------------------------------
# Continue / generate-documents — direct
# ---------------------------------------------------------------------------


class TestContinueGenerateDirect:
    @pytest.mark.asyncio
    async def test_continue_workflow_cloud_tasks(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.AWAITING_CONFIRMATION.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("config.settings.get_settings", return_value=_mock_settings(use_cloud_tasks=True)), \
             patch("api.workflow.enqueue_continue_workflow_task", AsyncMock()):
            async with _NullSessionLocal() as db:
                out = await continue_workflow_after_gate(
                    sid, BackgroundTasks(), user_dict, db
                )
        assert out.status == WorkflowStatus.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_continue_workflow_error(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_user_uuid", side_effect=RuntimeError("x")):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await continue_workflow_after_gate(
                        str(uuid.uuid4()), BackgroundTasks(), user_dict, db
                    )

    @pytest.mark.asyncio
    async def test_generate_documents_direct(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="analysis_complete",
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        blocked = RateLimitResult(allowed=True, limit=5, remaining=4, reset_seconds=60)
        bg = BackgroundTasks()
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)), \
             patch("api.workflow._generate_documents_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                out = await generate_documents(sid, bg, Response(), user_dict, db)
        assert out.status == WorkflowStatus.IN_PROGRESS.value
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_generate_documents_rate_limit(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        blocked = RateLimitResult(allowed=False, limit=5, remaining=0, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_documents(
                        str(uuid.uuid4()),
                        BackgroundTasks(),
                        Response(),
                        user_dict,
                        db,
                    )


# ---------------------------------------------------------------------------
# Background tasks — all branches
# ---------------------------------------------------------------------------


class TestBackgroundTasksCoverage:
    def _session_ctx(self):
        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                yield s

        return _ctx

    @pytest.mark.asyncio
    async def test_execute_background_session_missing(self):
        sid = str(uuid.uuid4())
        with patch("api.workflow.get_session", self._session_ctx()):
            await _execute_workflow_background(
                sid, str(uuid.uuid4()), "manual", LONG_JOB_TEXT, {}
            )

    @pytest.mark.asyncio
    async def test_execute_background_session_update_failure(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "current_phase": WorkflowPhase.COMPLETED.value,
            "job_analysis": {"job_title": "T", "company_name": "C"},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch(
                 "api.workflow._update_workflow_session_with_state",
                 AsyncMock(side_effect=RuntimeError("session write fail")),
             ), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(
                sid, str(uid), "manual", LONG_JOB_TEXT, {}
            )

    @pytest.mark.asyncio
    async def test_execute_background_app_update_failure(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()
        final = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "job_analysis": {"job_title": "T", "company_name": "C"},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch(
                 "api.workflow._update_job_application_with_final_state",
                 AsyncMock(side_effect=RuntimeError("app fail")),
             ), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(
                sid, str(uid), "manual", LONG_JOB_TEXT, {}
            )

    @pytest.mark.asyncio
    async def test_execute_background_top_level_failure(self):
        with patch("api.workflow.get_session", side_effect=RuntimeError("no db")), \
             patch("api.workflow.report_exception", AsyncMock()) as rep:
            await _execute_workflow_background(
                str(uuid.uuid4()), str(uuid.uuid4()), "manual", LONG_JOB_TEXT, {}
            )
        rep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_continue_background_missing_session(self):
        with patch("api.workflow.get_session", self._session_ctx()):
            await _continue_workflow_background(str(uuid.uuid4()), user_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_continue_background_with_byok_decrypt_error(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {"workflow_status": WorkflowStatus.COMPLETED.value, "job_analysis": {}}
        mock_wf = MagicMock()
        mock_wf.continue_workflow_after_gate = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("utils.encryption.decrypt_api_key", side_effect=ValueError("bad")), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

    @pytest.mark.asyncio
    async def test_continue_background_failure_paths(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_wf = MagicMock()
        mock_wf.continue_workflow_after_gate = AsyncMock(side_effect=RuntimeError("fail"))
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

    @pytest.mark.asyncio
    async def test_generate_documents_background_paths(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "job_analysis": {"job_title": "T", "company_name": "C"},
        }
        mock_wf = MagicMock()
        mock_wf.run_document_generation = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=True)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _generate_documents_background(sid, user_id=str(uid))

    @pytest.mark.asyncio
    async def test_generate_documents_background_top_level_error(self):
        with patch("api.workflow.get_session", side_effect=RuntimeError("db")), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _generate_documents_background(str(uuid.uuid4()), user_id=str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


class TestPersistenceCoverage:
    @pytest.mark.asyncio
    async def test_update_session_success_with_outputs(self):
        sid = str(uuid.uuid4())
        uid = uuid.uuid4()
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            await _update_workflow_session_with_state(
                db,
                sid,
                {
                    "workflow_status": WorkflowStatus.COMPLETED.value,
                    "current_phase": WorkflowPhase.COMPLETED.value,
                    "current_agent": "job_analyzer",
                    "agent_status": {"job_analyzer": "completed"},
                    "completed_agents": ["job_analyzer"],
                    "failed_agents": [],
                    "error_messages": [],
                    "warning_messages": [],
                    "job_analysis": {"job_title": "T"},
                    "company_research": {"industry": "X"},
                    "profile_matching": {"final_scores": {}},
                    "resume_recommendations": {"comprehensive_advice": {}},
                    "cover_letter": {"content": "Hi"},
                },
            )

    @pytest.mark.asyncio
    async def test_update_session_missing_row(self):
        async with _NullSessionLocal() as db:
            await _update_workflow_session_with_state(db, str(uuid.uuid4()), {})

    @pytest.mark.asyncio
    async def test_update_job_application_status_variants(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()
            for status, extra in (
                (WorkflowStatus.ANALYSIS_COMPLETE.value, {}),
                (WorkflowStatus.AWAITING_CONFIRMATION.value, {}),
                (WorkflowStatus.FAILED.value, {}),
                ("processing", {}),
            ):
                state = {
                    "workflow_status": status,
                    "job_analysis": {"job_title": f"T-{status}", "company_name": f"C-{status}"},
                    "profile_matching": {
                        "overall_score": 0.5,
                        "final_scores": {"overall_match_score": 0.6},
                    },
                    **extra,
                }
                await _update_job_application_with_final_state(db, sid, state)
                await db.commit()

    @pytest.mark.asyncio
    async def test_update_job_application_integrity_failed_workflow(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        other_sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.FAILED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Same",
                    company_name="Co",
                    status="completed",
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()

            @asynccontextmanager
            async def _boom(*args, **kwargs):
                raise IntegrityError("dup", {}, Exception())
                yield  # pragma: no cover

            with patch.object(db, "begin_nested", _boom):
                reverted = await _update_job_application_with_final_state(
                    db,
                    sid,
                    {
                        "workflow_status": WorkflowStatus.FAILED.value,
                        "job_analysis": {"job_title": "Same", "company_name": "Co"},
                    },
                )
            assert reverted is False


# ---------------------------------------------------------------------------
# Cloud Tasks execute endpoint
# ---------------------------------------------------------------------------


class TestExecuteWorkflowTaskDirect:
    @pytest.mark.asyncio
    async def test_execute_initial_task(self):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/internal/workflow/execute",
            "headers": [(b"x-cloudtasks-secret", b"test")],
        }
        request = Request(scope)
        payload = WorkflowTaskPayload(
            session_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            input_method="manual",
            job_input=LONG_JOB_TEXT,
            user_data={"full_name": "U"},
        )
        with patch("api.workflow.verify_cloud_tasks_secret", return_value=True), \
             patch("api.workflow._execute_workflow_background", AsyncMock()) as bg:
            resp = await execute_workflow_task(payload, request)
        assert resp.status_code == 204
        bg.assert_awaited_once()


class TestWorkflowFinalLineCoverage:
    def test_workflow_start_request_url_none(self):
        assert WorkflowStartRequest(job_url=None, job_text=LONG_JOB_TEXT).job_url is None

    @pytest.mark.asyncio
    async def test_start_no_api_key(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        from tests.test_api.test_workflow_extended import _clear_llm_prefs

        await _clear_llm_prefs(uid)
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch(
                 "config.settings.get_settings",
                 return_value=_mock_settings(gemini_api_key=None, use_vertex_ai=False),
             ):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError) as exc:
                    await start_workflow(
                        BackgroundTasks(),
                        Response(),
                        None,
                        None,
                        None,
                        LONG_JOB_TEXT,
                        None,
                        None,
                        None,
                        None,
                        user_dict,
                        db,
                    )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_start_discards_invalid_job_url(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    BackgroundTasks(),
                    Response(),
                    None,
                    None,
                    "javascript:alert(1)",
                    LONG_JOB_TEXT,
                    None,
                    None,
                    None,
                    None,
                    user_dict,
                    db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_docx_file_upload(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        docx = _make_docx_bytes(LONG_JOB_TEXT)
        upload = UploadFile(filename="job.docx", file=io.BytesIO(docx))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow.extract_text_from_docx", return_value=LONG_JOB_TEXT), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    BackgroundTasks(),
                    Response(),
                    None,
                    upload,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    user_dict,
                    db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_cloud_tasks_fallback(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        bg = BackgroundTasks()
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch(
                 "config.settings.get_settings",
                 return_value=_mock_settings(use_cloud_tasks=True),
             ), \
             patch(
                 "api.workflow.enqueue_workflow_task",
                 AsyncMock(side_effect=RuntimeError("cloud down")),
             ), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                await start_workflow(
                    bg,
                    Response(),
                    None,
                    None,
                    None,
                    LONG_JOB_TEXT,
                    None,
                    None,
                    None,
                    None,
                    user_dict,
                    db,
                )
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await get_workflow_status(str(uuid.uuid4()), user_dict, db)

    @pytest.mark.asyncio
    async def test_get_status_analysis_complete_progress(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="analysis_complete",
                    current_phase=WorkflowPhase.ANALYSIS_COMPLETE.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)), \
             patch("api.workflow.cache_workflow_state", AsyncMock()) as cache_mock:
            async with _NullSessionLocal() as db:
                out = await get_workflow_status(sid, user_dict, db)
        assert out.progress_percentage == 100
        cache_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_results_not_found_and_in_progress(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await get_workflow_results(str(uuid.uuid4()), user_dict, db)
            with pytest.raises(APIError):
                await get_workflow_results(sid, user_dict, db)

    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_not_found_and_bad_status(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await regenerate_cover_letter(str(uuid.uuid4()), Response(), user_dict, db)
            with pytest.raises(APIError):
                await regenerate_cover_letter(sid, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_missing_profile(self, wf_user_bundle):
        uid, email, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        await _ensure_user(uid, email=email)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.execute(
                update(UserProfile).where(UserProfile.user_id == uid).values(
                    professional_title=None
                )
            )
            await db.delete(
                (
                    await db.execute(
                        select(UserProfile).where(UserProfile.user_id == uid)
                    )
                ).scalar_one()
            )
            await db.commit()
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_cover_letter(sid, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_continue_not_found_and_wrong_status(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        from api.workflow import continue_workflow_after_gate

        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await continue_workflow_after_gate(
                    str(uuid.uuid4()), BackgroundTasks(), user_dict, db
                )
            with pytest.raises(APIError):
                await continue_workflow_after_gate(sid, BackgroundTasks(), user_dict, db)

    @pytest.mark.asyncio
    async def test_generate_documents_direct(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status="analysis_complete",
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        bg = BackgroundTasks()
        with patch("api.workflow._generate_documents_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                out = await generate_documents(sid, bg, Response(), user_dict, db)
        assert out.status == WorkflowStatus.IN_PROGRESS.value
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_list_history_with_job_analysis_rows(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "Listed", "company_name": "Org"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        async with _NullSessionLocal() as db:
            out = await list_workflow_history(
                user_dict, db, page=1, per_page=10, status_filter=None, sort="created_asc"
            )
        assert any(item.job_title == "Listed" for item in out.sessions)

    @pytest.mark.asyncio
    async def test_update_job_application_duplicate_with_broadcast(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        other_sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            for s, title, company in (
                (other_sid, "Dup", "Co"),
                (sid, None, None),
            ):
                db.add(
                    WorkflowSession(
                        id=uuid.uuid4(),
                        session_id=s,
                        user_id=uid,
                        workflow_status=WorkflowStatus.COMPLETED.value,
                        job_input_data={},
                        user_data={},
                        processing_start_time=datetime.now(timezone.utc),
                    )
                )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Dup",
                    company_name="Co",
                    status="completed",
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()

            @asynccontextmanager
            async def _integrity(*args, **kwargs):
                raise IntegrityError("dup", {}, Exception())
                yield  # pragma: no cover

            with patch.object(db, "begin_nested", _integrity), \
                 patch("api.workflow.broadcast_workflow_error", AsyncMock()) as broadcast:
                reverted = await _update_job_application_with_final_state(
                    db,
                    sid,
                    {
                        "workflow_status": WorkflowStatus.COMPLETED.value,
                        "job_analysis": {"job_title": "Dup", "company_name": "Co"},
                        "profile_matching": {},
                    },
                )
            assert reverted is True
            broadcast.assert_awaited()


class TestWorkflowBranchCompletion:
    """Cover remaining api/workflow.py branches."""

    def _session_ctx(self):
        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                yield s

        return _ctx

    @pytest.mark.asyncio
    async def test_start_redis_lock_fail_open(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(side_effect=ConnectionError("redis down"))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    BackgroundTasks(),
                    Response(),
                    None,
                    None,
                    None,
                    LONG_JOB_TEXT,
                    None,
                    None,
                    None,
                    None,
                    user_dict,
                    db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_success_lock_release_failure(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(return_value=True)
        mock_rc.delete = AsyncMock(side_effect=RuntimeError("del fail"))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            async with _NullSessionLocal() as db:
                result = await start_workflow(
                    BackgroundTasks(),
                    Response(),
                    None,
                    None,
                    None,
                    LONG_JOB_TEXT,
                    None,
                    None,
                    None,
                    None,
                    user_dict,
                    db,
                )
        assert result.session_id

    @pytest.mark.asyncio
    async def test_start_duplicate_lock_release_failure(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        other_sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Dev",
                    company_name="Y",
                    status="completed",
                )
            )
            await db.commit()
        mock_rc = AsyncMock()
        mock_rc.delete = AsyncMock(side_effect=RuntimeError("del fail"))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        BackgroundTasks(),
                        Response(),
                        None,
                        None,
                        None,
                        LONG_JOB_TEXT,
                        "Dev",
                        "Y",
                        None,
                        None,
                        user_dict,
                        db,
                    )

    @pytest.mark.asyncio
    async def test_start_error_cleanup_lock_release_failure(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        mock_rc = AsyncMock()
        mock_rc.set = AsyncMock(return_value=True)
        mock_rc.delete = AsyncMock(side_effect=RuntimeError("del fail"))
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=mock_rc)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch(
                 "api.workflow._find_duplicate_active_application",
                 AsyncMock(side_effect=RuntimeError("boom")),
             ):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await start_workflow(
                        BackgroundTasks(),
                        Response(),
                        None,
                        None,
                        None,
                        LONG_JOB_TEXT,
                        None,
                        None,
                        None,
                        None,
                        user_dict,
                        db,
                    )

    @pytest.mark.asyncio
    async def test_continue_cloud_tasks_fallback(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.AWAITING_CONFIRMATION.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        bg = BackgroundTasks()
        with patch(
            "api.workflow.get_settings",
            return_value=_mock_settings(use_cloud_tasks=True),
        ), patch(
            "api.workflow.enqueue_continue_workflow_task",
            AsyncMock(side_effect=RuntimeError("cloud down")),
        ):
            async with _NullSessionLocal() as db:
                out = await continue_workflow_after_gate(sid, bg, user_dict, db)
        assert out.status == WorkflowStatus.IN_PROGRESS.value
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_generate_documents_not_found_and_bad_status(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        allowed = RateLimitResult(allowed=True, limit=5, remaining=4, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_documents(
                        str(uuid.uuid4()), BackgroundTasks(), Response(), user_dict, db
                    )
                with pytest.raises(APIError):
                    await generate_documents(sid, BackgroundTasks(), Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_generate_documents_unhandled_error(self, wf_user_bundle):
        _, _, user_dict = wf_user_bundle
        with patch("api.workflow.get_user_uuid", side_effect=RuntimeError("x")):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_documents(
                        str(uuid.uuid4()), BackgroundTasks(), Response(), user_dict, db
                    )

    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_byok_decrypt(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    profile_matching={},
                    company_research={},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(return_value={"cover_letter": {"content": "CL"}})
        with patch("utils.encryption.decrypt_api_key", return_value="key"), \
             patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.cover_letter_writer.CoverLetterWriterAgent", return_value=mock_agent):
            async with _NullSessionLocal() as db:
                out = await regenerate_cover_letter(sid, Response(), user_dict, db)
        assert out.cover_letter["content"] == "CL"

    @pytest.mark.asyncio
    async def test_regenerate_resume_error_paths(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        allowed = RateLimitResult(allowed=True, limit=5, remaining=4, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_resume(str(uuid.uuid4()), Response(), user_dict, db)
                with pytest.raises(APIError):
                    await regenerate_resume(sid, Response(), user_dict, db)

        sid2 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            await db.execute(
                update(UserProfile).where(UserProfile.user_id == uid).values(
                    professional_title=None,
                    years_experience=None,
                )
            )
            await db.delete(
                (await db.execute(select(UserProfile).where(UserProfile.user_id == uid))).scalar_one()
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid2,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_resume(sid2, Response(), user_dict, db)

        sid3 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            await _ensure_user(uid)
            await _setup_complete_user(uid, email=user_dict["email"])
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid3,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    profile_matching={},
                    company_research={},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(return_value={"resume_recommendations": {"x": 1}})
        with patch("utils.encryption.decrypt_api_key", return_value="key"), \
             patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.resume_advisor.ResumeAdvisorAgent", return_value=mock_agent), \
             patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                await regenerate_resume(sid3, Response(), user_dict, db)

        sid4 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid4,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)), \
             patch("utils.llm_client.get_gemini_client", AsyncMock(side_effect=RuntimeError("llm"))):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await regenerate_resume(sid4, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_generate_interview_prep_error_paths(self, wf_user_bundle):
        uid, _, user_dict = wf_user_bundle
        sid = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        allowed = RateLimitResult(allowed=True, limit=5, remaining=4, reset_seconds=60)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_interview_prep(str(uuid.uuid4()), Response(), user_dict, db)
                with pytest.raises(APIError):
                    await generate_interview_prep(sid, Response(), user_dict, db)

        sid2 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid2,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    profile_matching={},
                    company_research=None,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(
            return_value={"response": '{"interview_stages": []}', "filtered": False}
        )
        with patch("utils.encryption.decrypt_api_key", return_value="key"), \
             patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)), \
             patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)):
            async with _NullSessionLocal() as db:
                out = await generate_interview_prep(sid2, Response(), user_dict, db)
        assert out.result

        sid3 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid3,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "E", "company_name": "C"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=allowed)), \
             patch("utils.llm_client.get_gemini_client", AsyncMock(side_effect=RuntimeError("llm"))):
            async with _NullSessionLocal() as db:
                with pytest.raises(APIError):
                    await generate_interview_prep(sid3, Response(), user_dict, db)

    @pytest.mark.asyncio
    async def test_update_job_application_overall_fit_score_and_broadcast_fail(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        other_sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            for s in (other_sid, sid):
                db.add(
                    WorkflowSession(
                        id=uuid.uuid4(),
                        session_id=s,
                        user_id=uid,
                        workflow_status=WorkflowStatus.COMPLETED.value,
                        job_input_data={},
                        user_data={},
                        processing_start_time=datetime.now(timezone.utc),
                    )
                )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Dup",
                    company_name="Co",
                    status="completed",
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()

            @asynccontextmanager
            async def _integrity(*args, **kwargs):
                raise IntegrityError("dup", {}, Exception())
                yield  # pragma: no cover

            with patch.object(db, "begin_nested", _integrity), \
                 patch(
                     "api.workflow.broadcast_workflow_error",
                     AsyncMock(side_effect=RuntimeError("ws fail")),
                 ):
                reverted = await _update_job_application_with_final_state(
                    db,
                    sid,
                    {
                        "workflow_status": WorkflowStatus.COMPLETED.value,
                        "job_analysis": {"job_title": "Dup", "company_name": "Co"},
                        "profile_matching": {"overall_fit_score": 0.88},
                    },
                )
            assert reverted is True

        sid2 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid2,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid2,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()
            await _update_job_application_with_final_state(
                db,
                sid2,
                {
                    "workflow_status": WorkflowStatus.COMPLETED.value,
                    "job_analysis": {"job_title": "Solo", "company_name": "Only"},
                    "profile_matching": {"overall_fit_score": 0.75},
                },
            )

    @pytest.mark.asyncio
    async def test_update_job_application_failed_integrity_with_match_score(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        other_sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    job_title="Same",
                    company_name="Co",
                    status="completed",
                )
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.FAILED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()

            @asynccontextmanager
            async def _integrity(*args, **kwargs):
                raise IntegrityError("dup", {}, Exception())
                yield  # pragma: no cover

            with patch.object(db, "begin_nested", _integrity):
                reverted = await _update_job_application_with_final_state(
                    db,
                    sid,
                    {
                        "workflow_status": WorkflowStatus.FAILED.value,
                        "job_analysis": {"job_title": "Same", "company_name": "Co"},
                        "profile_matching": {"overall_fit_score": 0.5},
                    },
                )
            assert reverted is False

    @pytest.mark.asyncio
    async def test_execute_background_duplicate_reverted_and_rollback_fail(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {"workflow_status": WorkflowStatus.COMPLETED.value, "job_analysis": {}}
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final)

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock(side_effect=RuntimeError("s"))), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=True)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_execute_background_workflow_failure_paths(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(side_effect=RuntimeError("wf fail"))

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch(
                 "api.workflow._soft_delete_job_application_for_failed_workflow",
                 AsyncMock(side_effect=RuntimeError("soft del fail")),
             ):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_execute_background_top_level_recovery(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=sid,
                    status=ApplicationStatus.PROCESSING.value,
                )
            )
            await db.commit()

        calls = {"n": 0}

        @asynccontextmanager
        async def _ctx():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("outer db fail")
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_continue_background_success_and_error_branches(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {"workflow_status": WorkflowStatus.COMPLETED.value, "job_analysis": {}}
        mock_wf = MagicMock()
        mock_wf.continue_workflow_after_gate = AsyncMock(return_value=final)

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock(side_effect=RuntimeError("s"))), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(side_effect=RuntimeError("a"))), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

        mock_wf2 = MagicMock()
        mock_wf2.continue_workflow_after_gate = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf2), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=True)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

    @pytest.mark.asyncio
    async def test_continue_background_failure_rollback_and_top_level(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_wf = MagicMock()
        mock_wf.continue_workflow_after_gate = AsyncMock(side_effect=RuntimeError("fail"))

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                s.commit = AsyncMock(side_effect=RuntimeError("commit fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

        calls = {"n": 0}

        @asynccontextmanager
        async def _outer():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("outer")
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _outer), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

    @pytest.mark.asyncio
    async def test_generate_documents_background_all_branches(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        with patch("api.workflow.get_session", self._session_ctx()):
            await _generate_documents_background(sid, user_id=str(uid))

        sid2 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == uid).values(gemini_api_key_encrypted="enc")
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid2,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {"workflow_status": WorkflowStatus.COMPLETED.value, "job_analysis": {}}
        mock_wf = MagicMock()
        mock_wf.run_document_generation = AsyncMock(return_value=final)

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("utils.encryption.decrypt_api_key", side_effect=ValueError("bad")), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock(side_effect=RuntimeError("s"))), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(side_effect=RuntimeError("a"))), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _generate_documents_background(sid2, user_id=str(uid))

        mock_wf2 = MagicMock()
        mock_wf2.run_document_generation = AsyncMock(return_value=final)
        with patch("api.workflow.get_session", self._session_ctx()), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf2), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=True)), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _generate_documents_background(sid2, user_id=str(uid))

        sid3 = str(uuid.uuid4())
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid3,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_wf3 = MagicMock()
        mock_wf3.run_document_generation = AsyncMock(side_effect=RuntimeError("gen fail"))

        @asynccontextmanager
        async def _fail_ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                s.commit = AsyncMock(side_effect=RuntimeError("commit fail"))
                yield s

        with patch("api.workflow.get_session", _fail_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf3), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()):
            await _generate_documents_background(sid3, user_id=str(uid))

        calls = {"n": 0}

        @asynccontextmanager
        async def _outer():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("outer")
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _outer), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _generate_documents_background(str(uuid.uuid4()), user_id=str(uid))


class TestWorkflowRemainingLineCoverage:
    def test_invalid_file_upload_state_helper(self):
        from api.workflow import _job_text_from_uploaded_file_with_ext

        with pytest.raises(APIError):
            _job_text_from_uploaded_file_with_ext(b"data", None)

    @pytest.mark.asyncio
    async def test_execute_background_app_update_rollback_failure(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {"workflow_status": WorkflowStatus.COMPLETED.value, "job_analysis": {}}
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final)

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch(
                 "api.workflow._update_job_application_with_final_state",
                 AsyncMock(side_effect=RuntimeError("app fail")),
             ), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_execute_background_error_state_commit_failure(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(side_effect=RuntimeError("wf fail"))

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock()
                s.commit = AsyncMock(side_effect=RuntimeError("commit fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_continue_background_top_level_recovery_failure(self):
        sid = str(uuid.uuid4())
        calls = {"n": 0}

        @asynccontextmanager
        async def _ctx():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("outer")
            async with _NullSessionLocal() as s:
                s.commit = AsyncMock(side_effect=RuntimeError("commit fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_generate_documents_background_missing_session(self):
        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _ctx):
            await _generate_documents_background(str(uuid.uuid4()), user_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_execute_background_app_update_rollback_fail(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        final = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "job_analysis": {"job_title": "T", "company_name": "C"},
        }
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final)

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                s.rollback = AsyncMock(side_effect=RuntimeError("rb fail"))
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch(
                 "api.workflow._update_job_application_with_final_state",
                 AsyncMock(side_effect=RuntimeError("app fail")),
             ), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_execute_background_save_error_state_commit_fail(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.INITIALIZED.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(side_effect=RuntimeError("wf fail"))
        commit_count = {"n": 0}

        @asynccontextmanager
        async def _ctx():
            async with _NullSessionLocal() as s:
                real_commit = s.commit

                async def counting_commit():
                    commit_count["n"] += 1
                    if commit_count["n"] >= 2:
                        raise RuntimeError("commit fail on error state")
                    return await real_commit()

                s.commit = counting_commit
                yield s

        with patch("api.workflow.get_session", _ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch(
                 "api.workflow._soft_delete_job_application_for_failed_workflow",
                 AsyncMock(),
             ):
            await _execute_workflow_background(sid, str(uid), "manual", LONG_JOB_TEXT, {})

    @pytest.mark.asyncio
    async def test_continue_background_top_level_recovery_commit_fail(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        calls = {"n": 0}

        @asynccontextmanager
        async def _outer():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("outer")
            async with _NullSessionLocal() as s:
                s.commit = AsyncMock(side_effect=RuntimeError("commit fail"))
                yield s

        with patch("api.workflow.get_session", _outer), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))

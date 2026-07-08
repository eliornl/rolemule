"""
Extended integration and unit tests for api/workflow.py.

Covers file uploads, dedupe, background tasks, status/results/continue/generate/regenerate,
and internal helper functions.
"""

import io
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from sqlalchemy import select, update

from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY
from api.workflow import (
    _agent_error_message,
    _canonical_job_url,
    _execute_workflow_background,
    _continue_workflow_background,
    _generate_documents_background,
    _fingerprint_job_content,
    _find_duplicate_active_application,
    _job_text_from_uploaded_file,
    _normalize_workflow_status_string,
    _raise_if_agent_soft_failure,
    _revert_workflow_session_after_duplicate_job_constraint,
    _safe_error_msg,
    _soft_delete_job_application_for_failed_workflow,
    _strip_agent_outputs_on_session_model,
    _update_job_application_with_final_state,
    _update_workflow_session_with_state,
    get_user_uuid,
)
from config.settings import get_security_settings
from models.database import (
    ApplicationStatus,
    AuthMethod,
    JobApplication,
    User,
    UserProfile,
    WorkflowSession,
)
from tests.test_api.conftest import _NullSessionLocal
from utils.error_responses import APIError
from workflows.state_schema import WorkflowPhase, WorkflowStatus

BASE = "/api/v1/workflow"

LONG_JOB_TEXT = (
    "We are hiring a Senior Software Engineer to build scalable backend services. "
    "Requirements include Python, FastAPI, PostgreSQL, and strong communication. "
    "Remote-friendly role with competitive compensation and benefits. "
) * 2


def _make_docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


async def _ensure_user(uid: uuid.UUID, email: Optional[str] = None) -> None:
    email = email or f"wf-helper-{uid.hex[:12]}@example.com"
    async with _NullSessionLocal() as session:
        existing = await session.execute(select(User).where(User.id == uid))
        if existing.scalar_one_or_none() is None:
            session.add(
                User(
                    id=uid,
                    email=email,
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="Workflow Helper",
                    profile_completed=True,
                    profile_completion_percentage=100,
                )
            )
            await session.commit()


async def _setup_complete_user(
    uid: uuid.UUID,
    *,
    email: str = "wf@example.com",
) -> None:
    async with _NullSessionLocal() as session:
        await session.execute(
            update(User).where(User.id == uid).values(profile_completed=True)
        )
        existing = await session.execute(
            select(UserProfile).where(UserProfile.user_id == uid)
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=5,
                    summary="Summary for workflow tests.",
                    city="City",
                    state="ST",
                    country="US",
                )
            )
        await session.commit()


async def _override_complete_user(app, uid: uuid.UUID, email: str) -> None:
    from utils.auth import get_current_user, get_current_user_with_complete_profile

    async def _mock():
        return {
            "id": str(uid),
            "_id": str(uid),
            "email": email,
            "full_name": "Workflow Tester",
            "auth_method": "local",
            "is_admin": False,
            "profile_completed": True,
            "profile_completion_percentage": 100,
            "has_google_linked": False,
            "has_password": True,
        }

    app.dependency_overrides[get_current_user] = _mock
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock


def _mock_settings(**overrides):
    base = dict(
        gemini_api_key=DUMMY_GEMINI_API_KEY,
        use_cloud_tasks=False,
        use_vertex_ai=False,
        debug=False,
    )
    base.update(overrides)
    return MagicMock(**base)


async def _create_session_row(
    uid: uuid.UUID,
    *,
    session_id: Optional[str] = None,
    status: str = WorkflowStatus.COMPLETED.value,
    job_analysis: Optional[Dict] = None,
    profile_matching: Optional[Dict] = None,
    company_research: Optional[Dict] = None,
) -> str:
    sid = session_id or str(uuid.uuid4())
    await _ensure_user(uid, email=f"wf-{uid.hex[:8]}@example.com")
    async with _NullSessionLocal() as db:
        db.add(
            WorkflowSession(
                id=uuid.uuid4(),
                session_id=sid,
                user_id=uid,
                workflow_status=status,
                current_phase=WorkflowPhase.COMPLETED.value,
                job_input_data={"input_method": "manual", "job_content": LONG_JOB_TEXT},
                user_data={"full_name": "Tester", "application_preferences": {}},
                job_analysis=job_analysis or {"job_title": "Engineer", "company_name": "Acme"},
                profile_matching=profile_matching or {"final_scores": {"overall_fit": 0.7}},
                company_research=company_research or {"industry": "Tech"},
                processing_start_time=datetime.now(timezone.utc),
            )
        )
        db.add(
            JobApplication(
                id=uuid.uuid4(),
                user_id=uid,
                session_id=sid,
                status=ApplicationStatus.COMPLETED.value,
                job_title="Engineer",
                company_name="Acme",
            )
        )
        await db.commit()
    return sid


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestWorkflowHelperFunctions:
    def test_canonical_job_url_empty(self):
        assert _canonical_job_url("") == ""
        assert _canonical_job_url("   ") == ""

    def test_fingerprint_short_text_returns_none(self):
        assert _fingerprint_job_content("short") is None
        assert _fingerprint_job_content(None) is None

    def test_fingerprint_normalizes_unicode(self):
        a = _fingerprint_job_content(LONG_JOB_TEXT)
        b = _fingerprint_job_content(LONG_JOB_TEXT.upper())
        assert a == b
        assert len(a) == 64

    def test_job_text_from_txt(self):
        text = "A" * 60
        assert _job_text_from_uploaded_file(text.encode("utf-8"), ".txt") == text

    def test_job_text_from_txt_too_short(self):
        with pytest.raises(Exception):
            _job_text_from_uploaded_file(b"short", ".txt")

    def test_job_text_from_pdf_success(self):
        with patch("api.workflow.extract_text_from_pdf", return_value="X" * 60):
            assert len(_job_text_from_uploaded_file(b"%PDF-1.4", ".pdf")) == 60

    def test_job_text_from_pdf_extract_failure(self):
        with patch("api.workflow.extract_text_from_pdf", side_effect=ValueError("bad pdf")):
            with pytest.raises(Exception):
                _job_text_from_uploaded_file(b"%PDF-1.4", ".pdf")

    def test_job_text_from_docx_success(self):
        with patch("api.workflow.extract_text_from_docx", return_value="Y" * 60):
            assert len(_job_text_from_uploaded_file(b"PK\x03\x04", ".docx")) == 60

    def test_job_text_unsupported_ext(self):
        with pytest.raises(Exception):
            _job_text_from_uploaded_file(b"data", ".exe")

    def test_get_user_uuid_from_string_and_uuid(self):
        u = uuid.uuid4()
        assert get_user_uuid({"id": str(u)}) == u
        assert get_user_uuid({"_id": u}) == u

    def test_normalize_workflow_status_string(self):
        assert _normalize_workflow_status_string(WorkflowStatus.FAILED) == "failed"
        assert _normalize_workflow_status_string(" COMPLETED ") == "completed"
        assert _normalize_workflow_status_string(None) == "completed"

    def test_safe_error_msg_debug_vs_prod(self):
        exc = RuntimeError("internal detail")
        assert "internal detail" in _safe_error_msg(exc, debug=True)
        assert "internal error" in _safe_error_msg(exc, debug=False).lower()

    def test_raise_if_agent_soft_failure_quota(self):
        with patch("api.workflow.is_llm_quota_or_rate_limit_exception", return_value=True), \
             patch("api.workflow.user_facing_message_from_llm_exception", return_value="quota"):
            with pytest.raises(Exception):
                _raise_if_agent_soft_failure({"error": True, "error_message": "429"})

    def test_raise_if_agent_soft_failure_nested(self):
        with patch("api.workflow.user_facing_message_from_llm_exception", return_value="fail"):
            with pytest.raises(APIError):
                _raise_if_agent_soft_failure(
                    {"comprehensive_advice": {"parse_error": True, "error_message": "bad json"}}
                )

    def test_raise_if_agent_soft_failure_ignores_clean_payload(self):
        _raise_if_agent_soft_failure({"comprehensive_advice": {"quick_wins": []}})

    def test_strip_agent_outputs_on_session_model(self):
        ws = WorkflowSession(
            id=uuid.uuid4(),
            session_id=str(uuid.uuid4()),
            user_id=uuid.uuid4(),
            job_analysis={"x": 1},
            cover_letter={"content": "Hi"},
        )
        _strip_agent_outputs_on_session_model(ws)
        assert ws.job_analysis is None
        assert ws.cover_letter is None


# ---------------------------------------------------------------------------
# File upload start
# ---------------------------------------------------------------------------


class TestWorkflowFileUploadStart:
    @pytest.mark.asyncio
    async def test_txt_upload_starts_workflow(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid, email=payload.get("email", "wf@example.com"))
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        txt = LONG_JOB_TEXT.encode("utf-8")
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                files={"job_file": ("job.txt", txt, "text/plain")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("session_id")

    @pytest.mark.asyncio
    async def test_pdf_upload_starts_workflow(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow.extract_text_from_pdf", return_value=LONG_JOB_TEXT), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                files={"job_file": ("job.pdf", b"%PDF-1.4\n", "application/pdf")},
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_docx_upload_starts_workflow(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        docx = _make_docx_bytes(LONG_JOB_TEXT)
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow.extract_text_from_docx", return_value=LONG_JOB_TEXT), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                files={
                    "job_file": (
                        "job.docx",
                        docx,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_pdf_magic_mismatch_returns_422(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                files={"job_file": ("fake.pdf", b"NOTPDF", "application/pdf")},
            )
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_no_api_key_returns_cfg6001(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch(
                 "config.settings.get_settings",
                 return_value=_mock_settings(gemini_api_key=None, use_vertex_ai=False),
             ):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_text": LONG_JOB_TEXT},
            )
        assert resp.status_code == 422
        assert resp.json().get("error_code") == "CFG_6001"


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


class TestWorkflowDedupeExtended:
    @pytest.mark.asyncio
    async def test_duplicate_title_company_returns_409(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        async with _NullSessionLocal() as session:
            other_sid = str(uuid.uuid4())
            session.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            session.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_sid,
                    status=ApplicationStatus.COMPLETED.value,
                    job_title="Staff Engineer",
                    company_name="Globex",
                )
            )
            await session.commit()

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={
                    "job_text": LONG_JOB_TEXT,
                    "detected_title": "Staff Engineer",
                    "detected_company": "Globex",
                },
            )
        assert resp.status_code == 409
        assert resp.json().get("error_code") == "RES_3002"

    @pytest.mark.asyncio
    async def test_find_duplicate_by_fingerprint(self):
        uid = uuid.uuid4()
        fp = _fingerprint_job_content(LONG_JOB_TEXT)
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    job_input_data={"content_fingerprint": fp},
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
                )
            )
            await db.commit()
            dup = await _find_duplicate_active_application(
                db, uid, None, None, None, fp
            )
            assert dup is not None


# ---------------------------------------------------------------------------
# Status / results / continue / generate-documents
# ---------------------------------------------------------------------------


class TestWorkflowStatusAndResults:
    @pytest.mark.asyncio
    async def test_status_from_db_returns_progress(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.IN_PROGRESS.value)

        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)):
            resp = await authed_client_with_user.get(f"{BASE}/status/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert "progress_percentage" in data

    @pytest.mark.asyncio
    async def test_status_cache_hit(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = str(uuid.uuid4())
        cached = {
            "user_id": str(uid),
            "session_id": sid,
            "status": "in_progress",
            "status_display": "In Progress",
            "current_phase": "job_analysis",
            "current_agent": "job_analyzer",
            "agent_status": {},
            "completed_agents": [],
            "error_messages": [],
            "progress_percentage": 20,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=cached)):
            resp = await authed_client_with_user.get(f"{BASE}/status/{sid}")
        assert resp.status_code == 200
        assert resp.json()["progress_percentage"] == 20

    @pytest.mark.asyncio
    async def test_results_for_completed_session(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid)

        resp = await authed_client_with_user.get(f"{BASE}/results/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_analysis"]["job_title"] == "Engineer"
        assert data["application_id"]

    @pytest.mark.asyncio
    async def test_results_in_progress_returns_422(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.IN_PROGRESS.value)

        resp = await authed_client_with_user.get(f"{BASE}/results/{sid}")
        assert resp.status_code in (400, 422)


class TestWorkflowContinueAndGenerate:
    @pytest.mark.asyncio
    async def test_continue_awaiting_confirmation(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(
            uid, status=WorkflowStatus.AWAITING_CONFIRMATION.value
        )

        with patch("api.workflow._continue_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(f"{BASE}/continue/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == WorkflowStatus.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_continue_wrong_status_returns_422(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.COMPLETED.value)

        resp = await authed_client_with_user.post(f"{BASE}/continue/{sid}")
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_generate_documents_from_analysis_complete(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(
            uid, status=WorkflowStatus.ANALYSIS_COMPLETE.value
        )

        with patch("api.workflow._generate_documents_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(f"{BASE}/generate-documents/{sid}")
        assert resp.status_code == 200
        assert resp.json()["message"]


class TestWorkflowRegenerate:
    @pytest.mark.asyncio
    async def test_regenerate_cover_letter(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid)

        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(return_value={"cover_letter": {"content": "New letter"}})

        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.cover_letter_writer.CoverLetterWriterAgent", return_value=mock_agent):
            resp = await authed_client_with_user.post(
                f"{BASE}/regenerate-cover-letter/{sid}"
            )
        assert resp.status_code == 200
        assert resp.json()["cover_letter"]["content"] == "New letter"

    @pytest.mark.asyncio
    async def test_regenerate_resume(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid)

        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(
            return_value={"resume_recommendations": {"comprehensive_advice": {"quick_wins": []}}}
        )

        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("agents.resume_advisor.ResumeAdvisorAgent", return_value=mock_agent):
            resp = await authed_client_with_user.post(f"{BASE}/regenerate-resume/{sid}")
        assert resp.status_code == 200
        assert "result" in resp.json()


# ---------------------------------------------------------------------------
# Background tasks (direct invocation)
# ---------------------------------------------------------------------------


class TestWorkflowBackgroundTasks:
    @pytest.mark.asyncio
    async def test_execute_workflow_background_success(self):
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
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
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

        final_state = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "current_phase": WorkflowPhase.COMPLETED.value,
            "job_analysis": {"job_title": "Role", "company_name": "Co"},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }

        mock_wf = MagicMock()
        mock_wf.run_initial_workflow = AsyncMock(return_value=final_state)

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)):
            await _execute_workflow_background(
                session_id=sid,
                user_id=str(uid),
                input_method="manual",
                job_input=LONG_JOB_TEXT,
                user_data={"full_name": "U"},
            )
        mock_wf.run_initial_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_workflow_background_idempotent_skip(self):
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

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow") as wf_cls:
            await _execute_workflow_background(
                session_id=sid,
                user_id=str(uid),
                input_method="manual",
                job_input=LONG_JOB_TEXT,
                user_data={},
            )
            wf_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_background_idempotent_skip(self):
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

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow") as wf_cls, \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()):
            await _continue_workflow_background(sid, user_id=str(uid))
            wf_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_soft_delete_job_application_for_failed_workflow(self):
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
            await _soft_delete_job_application_for_failed_workflow(db, sid)
            await db.commit()
            row = (
                await db.execute(
                    select(JobApplication).where(JobApplication.session_id == sid)
                )
            ).scalar_one()
            assert row.deleted_at is not None
            assert row.status == ApplicationStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_update_workflow_session_with_state_failed_strips_outputs(self):
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
                    job_analysis={"job_title": "Keep?"},
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
                    "workflow_status": WorkflowStatus.FAILED.value,
                    "current_phase": WorkflowPhase.ERROR.value,
                    "agent_status": {},
                    "completed_agents": [],
                    "failed_agents": [],
                    "error_messages": ["fail"],
                    "warning_messages": [],
                    "job_analysis": {"job_title": "Should strip"},
                },
            )
            row = (
                await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == sid)
                )
            ).scalar_one()
            assert row.job_analysis is None

    @pytest.mark.asyncio
    async def test_revert_session_after_duplicate_constraint(self):
        sid = str(uuid.uuid4())
        uid = uuid.uuid4()
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_analysis={"job_title": "Dup"},
                    job_input_data={},
                    user_data={},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            ws_user = await _revert_workflow_session_after_duplicate_job_constraint(db, sid)
            await db.commit()
            assert ws_user == str(uid)
            row = (
                await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == sid)
                )
            ).scalar_one()
            assert row.workflow_status == WorkflowStatus.FAILED.value
            assert row.job_analysis is None


class TestWorkflowHistoryAndInternal:
    @pytest.mark.asyncio
    async def test_history_lists_sessions_with_filter(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        await _create_session_row(uid, status=WorkflowStatus.COMPLETED.value)

        resp = await authed_client_with_user.get(
            f"{BASE}/history?page=1&per_page=5&status_filter=completed&sort=created_asc"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["sessions"]) >= 1

    @pytest.mark.asyncio
    async def test_execute_workflow_task_continue(self, api_client):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)

        with patch("api.workflow.verify_cloud_tasks_secret", return_value=True), \
             patch("api.workflow._continue_workflow_background", AsyncMock()) as cont:
            resp = await api_client.post(
                f"{BASE}/internal/workflow/execute",
                json={
                    "session_id": sid,
                    "user_id": str(uid),
                    "action": "continue",
                },
                headers={"X-CloudTasks-Secret": "test-secret"},
            )
        assert resp.status_code == 204
        cont.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_workflow_task_initial_requires_fields(self, api_client):
        with patch("api.workflow.verify_cloud_tasks_secret", return_value=True):
            resp = await api_client.post(
                f"{BASE}/internal/workflow/execute",
                json={"session_id": "s", "user_id": "u"},
                headers={"X-CloudTasks-Secret": "test-secret"},
            )
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_execute_workflow_task_unauthorized(self, api_client):
        with patch("api.workflow.verify_cloud_tasks_secret", return_value=False):
            resp = await api_client.post(
                f"{BASE}/internal/workflow/execute",
                json={"session_id": "s", "user_id": "u", "action": "continue"},
            )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_start_cloud_tasks_fallback_to_background(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch(
                 "config.settings.get_settings",
                 return_value=_mock_settings(use_cloud_tasks=True),
             ), \
             patch(
                 "api.workflow.enqueue_workflow_task",
                 AsyncMock(side_effect=RuntimeError("cloud tasks down")),
             ), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock) as bg:
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_text": LONG_JOB_TEXT},
            )
        assert resp.status_code == 200, resp.text
        bg.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_documents_background_success(self):
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
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        final_state = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "current_phase": WorkflowPhase.COMPLETED.value,
            "job_analysis": {"job_title": "R", "company_name": "C"},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }
        mock_wf = MagicMock()
        mock_wf.run_document_generation = AsyncMock(return_value=final_state)

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)):
            await _generate_documents_background(sid, user_id=str(uid))
        mock_wf.run_document_generation.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_application_duplicate_constraint(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        other_sid = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            for s in (sid, other_sid):
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
                    job_title="Same Title",
                    company_name="Same Co",
                    status=ApplicationStatus.COMPLETED.value,
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

            reverted = await _update_job_application_with_final_state(
                db,
                sid,
                {
                    "workflow_status": WorkflowStatus.COMPLETED.value,
                    "job_analysis": {"job_title": "Same Title", "company_name": "Same Co"},
                    "profile_matching": {},
                },
            )
            await db.commit()
            assert reverted is True


# ---------------------------------------------------------------------------
# Additional helper / dedupe coverage
# ---------------------------------------------------------------------------


class TestWorkflowHelperFunctionsExtended:
    def test_canonical_job_url_strips_tracking_params(self):
        url = "https://Jobs.Example.com/path/?utm_source=x&gclid=abc&role=eng"
        canon = _canonical_job_url(url)
        assert "utm_" not in canon
        assert "gclid" not in canon
        assert "role=eng" in canon

    def test_agent_error_message_quota_in_prod(self):
        from utils.llm_client import _GEMINI_QUOTA_USER_MESSAGE

        exc = Exception("429 RESOURCE_EXHAUSTED")
        with patch("api.workflow.user_facing_message_from_llm_exception", return_value=_GEMINI_QUOTA_USER_MESSAGE):
            msg = _agent_error_message(exc, "fallback", debug=False)
            assert msg == _GEMINI_QUOTA_USER_MESSAGE

    def test_job_text_pdf_too_short_after_extract(self):
        with patch("api.workflow.extract_text_from_pdf", return_value="tiny"):
            with pytest.raises(Exception):
                _job_text_from_uploaded_file(b"%PDF-1.4", ".pdf")

    def test_job_text_docx_extract_failure(self):
        with patch("api.workflow.extract_text_from_docx", side_effect=ValueError("bad")):
            with pytest.raises(Exception):
                _job_text_from_uploaded_file(b"PK\x03\x04", ".docx")

    def test_job_text_txt_invalid_utf8(self):
        with pytest.raises(Exception):
            _job_text_from_uploaded_file(b"\xff\xfe", ".txt")

    @pytest.mark.asyncio
    async def test_find_duplicate_by_canonical_url(self):
        uid = uuid.uuid4()
        sid = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=sid,
                    user_id=uid,
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
                    job_url="https://example.com/jobs/1?utm_source=email",
                )
            )
            await db.commit()
            dup = await _find_duplicate_active_application(
                db,
                uid,
                "https://example.com/jobs/1/",
                None,
                None,
                None,
            )
            assert dup is not None


# ---------------------------------------------------------------------------
# Start workflow — additional HTTP paths
# ---------------------------------------------------------------------------


class TestWorkflowStartExtended:
    @pytest.mark.asyncio
    async def test_json_start_success(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={
                    "job_text": LONG_JOB_TEXT,
                    "detected_title": "Unique Role",
                    "detected_company": "UniqueCo",
                },
            )
        assert resp.status_code == 200
        assert resp.json().get("session_id")

    @pytest.mark.asyncio
    async def test_start_missing_input_returns_422(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()):
            resp = await authed_client_with_user.post(f"{BASE}/start", data={})
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_start_rate_limit_returns_429(self, authed_client_with_user):
        from main import app
        from utils.cache import RateLimitResult

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        blocked = RateLimitResult(allowed=False, limit=30, remaining=0, reset_seconds=3600)
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_text": LONG_JOB_TEXT},
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_extension_source_stores_fingerprint(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("config.settings.get_settings", return_value=_mock_settings()), \
             patch("api.workflow._execute_workflow_background", new_callable=AsyncMock):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={
                    "job_text": LONG_JOB_TEXT,
                    "source": "extension",
                    "source_url": "javascript:alert(1)",
                },
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Status / results / history
# ---------------------------------------------------------------------------


class TestWorkflowStatusResultsHistory:
    @pytest.mark.asyncio
    async def test_status_not_found(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))

        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)):
            resp = await authed_client_with_user.get(f"{BASE}/status/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_analysis_complete_shows_100_progress(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status="analysis_complete")

        with patch("api.workflow.get_cached_workflow_state", AsyncMock(return_value=None)), \
             patch("api.workflow.cache_workflow_state", AsyncMock()) as mock_cache:
            resp = await authed_client_with_user.get(f"{BASE}/status/{sid}")
        assert resp.status_code == 200
        assert resp.json()["progress_percentage"] == 100
        mock_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_results_failed_status_allowed(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.FAILED.value)

        resp = await authed_client_with_user.get(f"{BASE}/results/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == WorkflowStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_list_workflow_history(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        await _create_session_row(uid)

        resp = await authed_client_with_user.get(f"{BASE}/history?page=1&per_page=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["sessions"]


# ---------------------------------------------------------------------------
# Regenerate / interview prep / rate limits
# ---------------------------------------------------------------------------


class TestWorkflowRegenerateExtended:
    @pytest.mark.asyncio
    async def test_regenerate_cover_letter_rate_limit(self, authed_client_with_user):
        from main import app
        from utils.cache import RateLimitResult

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid)

        blocked = RateLimitResult(allowed=False, limit=5, remaining=0, reset_seconds=3600)
        with patch("api.workflow.check_rate_limit_with_headers", AsyncMock(return_value=blocked)):
            resp = await authed_client_with_user.post(f"{BASE}/regenerate-cover-letter/{sid}")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_regenerate_resume_wrong_status(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.IN_PROGRESS.value)

        resp = await authed_client_with_user.post(f"{BASE}/regenerate-resume/{sid}")
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_generate_interview_prep_success(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _setup_complete_user(uid)
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid)

        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(
            return_value={"response": '{"interview_stages": []}', "filtered": False}
        )
        with patch("utils.llm_client.get_gemini_client", AsyncMock(return_value=mock_client)):
            resp = await authed_client_with_user.post(
                f"{BASE}/generate-interview-prep/{sid}"
            )
        assert resp.status_code == 200
        assert "result" in resp.json()


class TestWorkflowContinueGenerateExtended:
    @pytest.mark.asyncio
    async def test_continue_rate_limit(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(
            uid, status=WorkflowStatus.AWAITING_CONFIRMATION.value
        )

        with patch("api.workflow.check_rate_limit", AsyncMock(return_value=(False, 0))):
            resp = await authed_client_with_user.post(f"{BASE}/continue/{sid}")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_generate_documents_wrong_status(self, authed_client_with_user):
        from main import app

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token, sec.jwt_config["secret_key"], algorithms=[sec.jwt_config["algorithm"]]
        )
        uid = uuid.UUID(payload["sub"])
        await _override_complete_user(app, uid, payload.get("email", "wf@example.com"))
        sid = await _create_session_row(uid, status=WorkflowStatus.COMPLETED.value)

        resp = await authed_client_with_user.post(f"{BASE}/generate-documents/{sid}")
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Background tasks — failure / duplicate / cloud tasks callback
# ---------------------------------------------------------------------------


class TestWorkflowBackgroundTasksExtended:
    @pytest.mark.asyncio
    async def test_execute_background_workflow_failure_marks_failed(self):
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
        mock_wf.run_initial_workflow = AsyncMock(side_effect=RuntimeError("agent blew up"))

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch("api.workflow.report_exception", AsyncMock()):
            await _execute_workflow_background(
                session_id=sid,
                user_id=str(uid),
                input_method="manual",
                job_input=LONG_JOB_TEXT,
                user_data={},
            )

        async with _NullSessionLocal() as db:
            row = (
                await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == sid)
                )
            ).scalar_one()
            assert row.workflow_status == WorkflowStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_continue_background_runs_workflow(self):
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

        final_state = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "current_phase": WorkflowPhase.COMPLETED.value,
            "job_analysis": {"job_title": "Done", "company_name": "Co"},
            "profile_matching": {"final_scores": {"overall_fit": 0.9}},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }
        mock_wf = MagicMock()
        mock_wf.continue_workflow_after_gate = AsyncMock(return_value=final_state)

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_workflow_resumed", AsyncMock()), \
             patch("api.workflow.invalidate_workflow_state", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)):
            await _continue_workflow_background(sid, user_id=str(uid))
        mock_wf.continue_workflow_after_gate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_documents_background_success(self):
        from api.workflow import _generate_documents_background

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

        final_state = {
            "workflow_status": WorkflowStatus.COMPLETED.value,
            "current_phase": WorkflowPhase.COMPLETED.value,
            "job_analysis": {"job_title": "Doc", "company_name": "Co"},
            "cover_letter": {"content": "Hi"},
            "agent_status": {},
            "completed_agents": [],
            "failed_agents": [],
            "error_messages": [],
            "warning_messages": [],
        }
        mock_wf = MagicMock()
        mock_wf.run_document_generation = AsyncMock(return_value=final_state)

        @asynccontextmanager
        async def _session_ctx():
            async with _NullSessionLocal() as s:
                yield s

        with patch("api.workflow.get_session", _session_ctx), \
             patch("api.workflow.JobApplicationWorkflow", return_value=mock_wf), \
             patch("api.workflow.broadcast_document_generation_started", AsyncMock()), \
             patch("api.workflow._update_workflow_session_with_state", AsyncMock()), \
             patch("api.workflow._update_job_application_with_final_state", AsyncMock(return_value=False)):
            await _generate_documents_background(sid, user_id=str(uid))
        mock_wf.run_document_generation.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_application_success_with_match_score(self):
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
            reverted = await _update_job_application_with_final_state(
                db,
                sid,
                {
                    "workflow_status": WorkflowStatus.COMPLETED.value,
                    "job_analysis": {"job_title": "Title A", "company_name": "Co A"},
                    "profile_matching": {
                        "final_scores": {"overall_fit": 0.77},
                    },
                },
            )
            await db.commit()
            assert reverted is False
            app_row = (
                await db.execute(
                    select(JobApplication).where(JobApplication.session_id == sid)
                )
            ).scalar_one()
            assert app_row.job_title == "Title A"
            assert float(app_row.match_score) == pytest.approx(0.77)


class TestExecuteWorkflowTaskEndpoint:
    @pytest.mark.asyncio
    async def test_execute_task_unauthorized(self, api_client):
        resp = await api_client.post(
            f"{BASE}/internal/workflow/execute",
            json={
                "session_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "input_method": "manual",
                "job_input": LONG_JOB_TEXT,
                "user_data": {},
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_execute_task_continue_action(self, api_client):
        with patch("api.workflow.verify_cloud_tasks_secret", return_value=True), \
             patch("api.workflow._continue_workflow_background", AsyncMock()) as mock_cont:
            resp = await api_client.post(
                f"{BASE}/internal/workflow/execute",
                json={
                    "session_id": str(uuid.uuid4()),
                    "user_id": str(uuid.uuid4()),
                    "action": "continue",
                },
                headers={"X-CloudTasks-Secret": "test"},
            )
        assert resp.status_code == 204
        mock_cont.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_task_initial_missing_fields(self, api_client):
        with patch("api.workflow.verify_cloud_tasks_secret", return_value=True):
            resp = await api_client.post(
                f"{BASE}/internal/workflow/execute",
                json={"session_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
                headers={"X-CloudTasks-Secret": "test"},
            )
        assert resp.status_code in (400, 422)

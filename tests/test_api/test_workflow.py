"""
Integration tests for Workflow API endpoints.

Endpoints:
  POST /api/v1/workflow/start
  GET  /api/v1/workflow/status/{session_id}
  GET  /api/v1/workflow/results/{session_id}
  GET  /api/v1/workflow/history
"""

import uuid
import pytest
import jwt
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy import update

from api.workflow import _canonical_job_url
from config.settings import get_security_settings
from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY
from models.database import ApplicationStatus, JobApplication, User, UserProfile
from tests.test_api.conftest import _NullSessionLocal

BASE = "/api/v1/workflow"
SESSION_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------


class TestWorkflowStart:
    """POST /api/v1/workflow/start"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(
            f"{BASE}/start",
            data={"job_text": "We are looking for a software engineer..."},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_input_returns_400_or_422(self, authed_client):
        """Starting a workflow with no job input should be rejected."""
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            resp = await authed_client.post(f"{BASE}/start", data={})
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_start_with_text_input_returns_session_or_error(self, authed_client):
        """A valid text input should return 200/202 (session created) or validation error."""
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)):
            resp = await authed_client.post(
                f"{BASE}/start",
                data={
                    "job_text": "We are looking for a Senior Python Engineer with 5+ years experience. "
                                "Must have strong knowledge of FastAPI and PostgreSQL. "
                                "Full remote, competitive salary.",
                },
            )

        # May return 200/202 (started) or 400/422 (validation) or 500 (LLM not configured)
        assert resp.status_code in (200, 202, 400, 422, 500), resp.text

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self, authed_client):
        from utils.cache import RateLimitResult
        blocked = RateLimitResult(allowed=False, limit=30, remaining=0, reset_seconds=3600)
        with patch("api.workflow.check_rate_limit_with_headers",
                   AsyncMock(return_value=blocked)):
            resp = await authed_client.post(
                f"{BASE}/start",
                data={"job_text": "We need a backend engineer..."},
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_unsupported_file_type_returns_400(self, authed_client):
        """Uploading an unsupported file type should return 400."""
        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), \
             patch("api.workflow.check_rate_limit_with_headers",
                   AsyncMock(return_value=MagicMock(allowed=True, reset_seconds=3600,
                                                    get_headers=lambda: {}))):
            resp = await authed_client.post(
                f"{BASE}/start",
                files={"job_file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
            )
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# GET /status/{session_id}
# ---------------------------------------------------------------------------


class TestWorkflowStatus:
    """GET /api/v1/workflow/status/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/status/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self, authed_client):
        resp = await authed_client.get(f"{BASE}/status/{str(uuid.uuid4())}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_session_id_format_returns_400_or_404(self, authed_client):
        resp = await authed_client.get(f"{BASE}/status/not-a-uuid")
        assert resp.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# GET /results/{session_id}
# ---------------------------------------------------------------------------


class TestWorkflowResults:
    """GET /api/v1/workflow/results/{session_id}"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/results/{SESSION_ID}")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self, authed_client):
        resp = await authed_client.get(f"{BASE}/results/{str(uuid.uuid4())}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_session_id_returns_404_or_422(self, authed_client):
        resp = await authed_client.get(f"{BASE}/results/")
        assert resp.status_code in (404, 405, 422)


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------


class TestWorkflowHistory:
    """GET /api/v1/workflow/history"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/history")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list_for_new_user(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/history")
        assert resp.status_code == 200
        data = resp.json()
        sessions_key = "sessions" if "sessions" in data else list(data.keys())[0]
        assert isinstance(data[sessions_key], list)

    @pytest.mark.asyncio
    async def test_pagination_params_accepted(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/history?page=1&page_size=10")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Duplicate prevention helpers + POST /start conflict
# ---------------------------------------------------------------------------


def test_canonical_job_url_strips_tracking_and_fragments():
    a = "https://Jobs.EXAMPLE.com/role/abc/?utm_source=x&gclid=1&role=eng"
    b = "https://jobs.example.com/role/abc?role=eng"
    assert _canonical_job_url(a) == _canonical_job_url(b)


class TestWorkflowStartDuplicate:
    """POST /api/v1/workflow/start duplicate detection (409)."""

    @pytest.mark.asyncio
    async def test_duplicate_job_url_returns_409(self, authed_client_with_user):
        from main import app
        from utils.auth import get_current_user, get_current_user_with_complete_profile

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])

        job_url = "https://careers.example.com/jobs/tetrix-senior-fs?utm_medium=social"

        async with _NullSessionLocal() as session:
            await session.execute(
                update(User).where(User.id == uid).values(profile_completed=True)
            )
            session.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=5,
                    summary="Summary text for testing duplicate detection.",
                    city="City",
                    state="ST",
                    country="US",
                )
            )
            session.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=None,
                    status=ApplicationStatus.COMPLETED.value,
                    job_url="https://careers.example.com/jobs/tetrix-senior-fs",
                    job_title="Senior Full Stack Engineer",
                    company_name="Tetrix",
                )
            )
            await session.commit()

        async def _mock_complete_user():
            return {
                "id": str(uid),
                "_id": str(uid),
                "email": payload.get("email", "u@example.com"),
                "full_name": "Test User",
                "auth_method": "local",
                "is_admin": False,
                "profile_completed": True,
                "profile_completion_percentage": 100,
                "has_google_linked": False,
                "has_password": True,
            }

        app.dependency_overrides[get_current_user] = _mock_complete_user
        app.dependency_overrides[get_current_user_with_complete_profile] = _mock_complete_user

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), patch(
            "config.settings.get_settings",
            return_value=MagicMock(
                gemini_api_key=DUMMY_GEMINI_API_KEY,
                use_cloud_tasks=False,
                use_vertex_ai=False,
            ),
        ):
            resp = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_url": job_url},
            )
        assert resp.status_code == 409
        body = resp.json()
        assert body.get("error_code") == "RES_3002"
        details = body.get("details") or []
        assert any(d.get("field") == "application_id" for d in details)

    @pytest.mark.asyncio
    async def test_duplicate_manual_job_text_returns_409(self, authed_client_with_user):
        """Same pasted job description twice should 409 (content fingerprint)."""
        from main import app
        from utils.auth import get_current_user, get_current_user_with_complete_profile

        token = authed_client_with_user.headers["Authorization"].split(" ", 1)[1]
        sec = get_security_settings()
        payload = jwt.decode(
            token,
            sec.jwt_config["secret_key"],
            algorithms=[sec.jwt_config["algorithm"]],
        )
        uid = uuid.UUID(payload["sub"])

        long_job = (
            "We are hiring a Senior Software Engineer - Product to build our platform. "
            "Requirements include Python, distributed systems, and collaboration. " * 3
        )

        async with _NullSessionLocal() as session:
            await session.execute(
                update(User).where(User.id == uid).values(profile_completed=True)
            )
            session.add(
                UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    professional_title="Engineer",
                    years_experience=5,
                    summary="Summary for fingerprint duplicate test.",
                    city="City",
                    state="ST",
                    country="US",
                )
            )
            await session.commit()

        async def _mock_complete_user():
            return {
                "id": str(uid),
                "_id": str(uid),
                "email": payload.get("email", "u@example.com"),
                "full_name": "Test User",
                "auth_method": "local",
                "is_admin": False,
                "profile_completed": True,
                "profile_completion_percentage": 100,
                "has_google_linked": False,
                "has_password": True,
            }

        app.dependency_overrides[get_current_user] = _mock_complete_user
        app.dependency_overrides[get_current_user_with_complete_profile] = _mock_complete_user

        mock_settings = MagicMock(
            gemini_api_key=DUMMY_GEMINI_API_KEY,
            use_cloud_tasks=False,
            use_vertex_ai=False,
        )

        with patch("utils.redis_client.get_redis_client", AsyncMock(return_value=None)), patch(
            "config.settings.get_settings",
            return_value=mock_settings,
        ), patch(
            "api.workflow._execute_workflow_background",
            new_callable=AsyncMock,
        ):
            r1 = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_text": long_job},
            )
            assert r1.status_code == 200, r1.text
            r2 = await authed_client_with_user.post(
                f"{BASE}/start",
                data={"job_text": long_job},
            )
        assert r2.status_code == 409
        assert r2.json().get("error_code") == "RES_3002"

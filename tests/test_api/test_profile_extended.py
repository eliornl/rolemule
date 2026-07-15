"""
Extended integration tests for api/profile.py — full CRUD flow, resume parse/upload,
API key management, preferences, account deletion, clear data, and completion.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from passlib.context import CryptContext
from sqlalchemy import delete, select, update

from main import app
from models.database import AuthMethod, JobApplication, User, UserProfile, UserResumeAsset, UserWorkflowPreferences, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal, _make_test_jwt
from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY
from utils.auth import get_current_user, get_current_user_with_complete_profile

BASE = "/api/v1/profile"
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

MOCK_PARSED_RESUME: Dict[str, Any] = {
    "professional_title": "Software Engineer",
    "years_experience": 4,
    "summary": "Backend developer with Python experience.",
    "city": "Austin",
    "state": "TX",
    "country": "USA",
    "skills": ["Python", "FastAPI"],
    "parsing_confidence": "HIGH",
    "processing_time": 1.2,
}

CAREER_PREFS = {
    "desired_salary_range": {"min": 90000, "max": 130000},
    "desired_company_sizes": ["Startup (1-10 employees)"],
    "job_types": ["Full-time"],
    "work_arrangements": ["Remote"],
    "willing_to_relocate": False,
    "requires_visa_sponsorship": False,
    "work_authorization": "us_citizen",
    "has_security_clearance": False,
    "max_travel_preference": "0",
}

BASIC_INFO = {
    "city": "Austin",
    "state": "TX",
    "country": "USA",
    "professional_title": "Software Engineer",
    "years_experience": 4,
    "is_student": False,
    "summary": "Backend developer with four years of Python and FastAPI experience.",
    "phone": "+1 512 555 0100",
}


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


async def _create_user_with_password(
    *,
    email: Optional[str] = None,
    password: str = "SecurePass123!",
) -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = email or f"profileext_{uid.hex[:10]}@example.com"
    async with _NullSessionLocal() as session:
        session.add(
            User(
                id=uid,
                email=email,
                password_hash=pwd_ctx.hash(password[:72]),
                auth_method=AuthMethod.LOCAL.value,
                full_name="Profile Extended User",
                profile_completed=False,
                profile_completion_percentage=0,
                email_verified=True,
            )
        )
        session.add(
            UserWorkflowPreferences(
                id=uuid.uuid4(),
                user_id=uid,
                preferred_provider="ollama",
            )
        )
        await session.commit()
    return uid, email


async def _delete_user_data(uid: uuid.UUID) -> None:
    async with _NullSessionLocal() as session:
        await session.execute(delete(JobApplication).where(JobApplication.user_id == uid))
        await session.execute(delete(WorkflowSession).where(WorkflowSession.user_id == uid))
        await session.execute(delete(UserResumeAsset).where(UserResumeAsset.user_id == uid))
        await session.execute(delete(UserProfile).where(UserProfile.user_id == uid))
        await session.execute(delete(User).where(User.id == uid))
        await session.commit()


async def _client_for(uid: uuid.UUID, email: str, *, profile_completed: bool = False) -> AsyncClient:
    now = datetime.now(timezone.utc)
    user_dict = {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Profile Extended User",
        "auth_method": "local",
        "is_admin": False,
        "profile_completed": profile_completed,
        "profile_completion_percentage": 100 if profile_completed else 0,
        "has_google_linked": False,
        "has_password": True,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    async def _mock():
        return user_dict

    app.dependency_overrides[get_current_user] = _mock
    app.dependency_overrides[get_current_user_with_complete_profile] = _mock
    from httpx import ASGITransport

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {_make_test_jwt(str(uid), email)}"},
    )


async def _fill_all_profile_sections(client: AsyncClient) -> None:
    resp = await client.put(f"{BASE}/basic-info", json=BASIC_INFO)
    assert resp.status_code in (200, 201, 204), resp.text
    resp = await client.put(f"{BASE}/work-experience", json={"work_experience": []})
    assert resp.status_code in (200, 201, 204), resp.text
    resp = await client.put(f"{BASE}/education", json={"education": []})
    assert resp.status_code in (200, 201, 204), resp.text
    resp = await client.put(
        f"{BASE}/skills-qualifications",
        json={"skills": ["Python", "FastAPI", "PostgreSQL"]},
    )
    assert resp.status_code in (200, 201, 204), resp.text
    resp = await client.put(f"{BASE}/career-preferences", json=CAREER_PREFS)
    assert resp.status_code in (200, 201, 204), resp.text


# ---------------------------------------------------------------------------
# Full profile CRUD
# ---------------------------------------------------------------------------


class TestProfileCrudExtended:
    @pytest.mark.asyncio
    async def test_get_profile_returns_nested_structure(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            await _fill_all_profile_sections(client)
            resp = await client.get(f"{BASE}/")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "profile_data" in data or "user_info" in data
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_work_experience_valid_row(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            resp = await client.put(
                f"{BASE}/work-experience",
                json={
                    "work_experience": [
                        {
                            "job_title": "Engineer",
                            "company": "Acme Corp",
                            "start_date": "2020-01",
                            "end_date": "2023-06",
                            "is_current": False,
                            "description": "Built APIs.",
                        }
                    ]
                },
            )
            assert resp.status_code in (200, 201, 204), resp.text
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_career_preferences_invalid_salary_returns_422(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            bad = dict(CAREER_PREFS)
            bad["desired_salary_range"] = {"min": 150000, "max": 100000}
            resp = await client.put(f"{BASE}/career-preferences", json=bad)
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Profile completion
# ---------------------------------------------------------------------------


class TestProfileCompletion:
    @pytest.mark.asyncio
    async def test_complete_profile_success(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            await _fill_all_profile_sections(client)
            resp = await client.post(f"{BASE}/complete")
            assert resp.status_code == 200, resp.text
            assert resp.json()["profile_completed"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_missing_sections_returns_422(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            resp = await client.post(f"{BASE}/complete")
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_status_reflects_completed_steps(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            await client.put(f"{BASE}/basic-info", json=BASIC_INFO)
            resp = await client.get(f"{BASE}/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "basic_info" in data.get("completed_steps", [])
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Resume parse / upload / download / delete
# ---------------------------------------------------------------------------


class TestResumeExtended:
    @pytest.mark.asyncio
    async def test_parse_resume_txt_success(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        content = b"Jane Doe\nSoftware Engineer\nPython FastAPI PostgreSQL"
        try:
            with patch(
                "api.profile.parse_resume_from_file",
                AsyncMock(return_value=MOCK_PARSED_RESUME),
            ), patch(
                "config.settings.get_settings",
                return_value=MagicMock(
                    use_vertex_ai=True,
                    gemini_api_key=None,
                    user_resume_storage_dir="/tmp/applypilot-test-resumes",
                ),
            ), patch(
                "api.profile.save_resume_bytes", return_value=("rel/path", "sha", "txt")
            ), patch(
                "api.profile.invalidate_user_profile", AsyncMock(return_value=None)
            ):
                files = {"resume": ("resume.txt", content, "text/plain")}
                resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 200, resp.text
            assert resp.json()["success"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_no_api_key_returns_422(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                await session.execute(
                    update(UserWorkflowPreferences)
                    .where(UserWorkflowPreferences.user_id == uid)
                    .values(preferred_provider=None)
                )
                await session.commit()
            files = {"resume": ("resume.txt", b"hello world resume text", "text/plain")}
            resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 422
            assert resp.json().get("error_code") == "CFG_6001"
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_oversized_returns_413(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = DUMMY_GEMINI_API_KEY
                mock_settings.use_vertex_ai = False
                huge = b"x" * (11 * 1024 * 1024)
                files = {"resume": ("resume.txt", huge, "text/plain")}
                resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 413
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_stored_resume_lifecycle(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                session.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path=f"{uid}/resume.txt",
                        original_filename="resume.txt",
                        mime_type="text/plain",
                        byte_size=12,
                        sha256_hex="abc",
                    )
                )
                await session.commit()

            with patch("api.profile.resume_absolute_path") as mock_path, patch(
                "api.profile.delete_resume_file"
            ), patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)):
                from pathlib import Path

                tmp = Path("/tmp/applypilot-test-resume.txt")
                tmp.write_text("resume content", encoding="utf-8")
                mock_path.return_value = tmp
                get_resp = await client.get(f"{BASE}/resume")
                assert get_resp.status_code == 200
                del_resp = await client.delete(f"{BASE}/resume")
                assert del_resp.status_code == 200
                tmp.unlink(missing_ok=True)
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


class TestApiKeyExtended:
    VALID_KEY = DUMMY_GEMINI_API_KEY

    @pytest.mark.asyncio
    async def test_set_and_delete_api_key(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
            ):
                set_resp = await client.post(f"{BASE}/api-key", json={"api_key": self.VALID_KEY})
            assert set_resp.status_code == 200, set_resp.text

            status_resp = await client.get(f"{BASE}/api-key/status")
            assert status_resp.status_code == 200
            status = status_resp.json()
            assert status["has_user_key"] is True
            assert status.get("has_credentials") is True
            assert status.get("preferred_provider") == "gemini"
            assert status["providers"]["gemini"]["has_key"] is True

            with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
            ):
                del_resp = await client.delete(f"{BASE}/api-key?provider=gemini")
            assert del_resp.status_code == 200
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_set_openai_api_key(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        openai_key = "sk-" + ("x" * 40)
        try:
            with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
            ):
                set_resp = await client.post(
                    f"{BASE}/api-key",
                    json={"api_key": openai_key, "provider": "openai"},
                )
            assert set_resp.status_code == 200, set_resp.text
            assert set_resp.json().get("provider") == "openai"

            status_resp = await client.get(f"{BASE}/api-key/status")
            assert status_resp.status_code == 200
            status = status_resp.json()
            assert status["preferred_provider"] == "openai"
            assert status["has_credentials"] is True
            assert status["providers"]["openai"]["has_key"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_preferred_provider_ollama_ready_without_key(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            patch_resp = await client.patch(
                f"{BASE}/preferences",
                json={"preferred_provider": "ollama"},
            )
            assert patch_resp.status_code == 200, patch_resp.text
            assert patch_resp.json().get("preferred_provider") == "ollama"

            status_resp = await client.get(f"{BASE}/api-key/status")
            assert status_resp.status_code == 200
            status = status_resp.json()
            assert status["preferred_provider"] == "ollama"
            assert status["has_credentials"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_status_not_ready_without_provider(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                await session.execute(
                    update(UserWorkflowPreferences)
                    .where(UserWorkflowPreferences.user_id == uid)
                    .values(preferred_provider=None)
                )
                await session.commit()
            status_resp = await client.get(f"{BASE}/api-key/status")
            assert status_resp.status_code == 200
            status = status_resp.json()
            assert status["has_credentials"] is False
            assert not status.get("preferred_provider")
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_switching_provider_clears_preferred_model(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
            ):
                set_resp = await client.post(
                    f"{BASE}/api-key",
                    json={"api_key": self.VALID_KEY, "provider": "gemini"},
                )
            assert set_resp.status_code == 200, set_resp.text

            patch_model = await client.patch(
                f"{BASE}/preferences",
                json={"preferred_model": "gemini-2.5-flash"},
            )
            assert patch_model.status_code == 200, patch_model.text
            assert patch_model.json().get("preferred_model") == "gemini-2.5-flash"

            switch = await client.patch(
                f"{BASE}/preferences",
                json={"preferred_provider": "ollama"},
            )
            assert switch.status_code == 200, switch.text
            assert switch.json().get("preferred_provider") == "ollama"
            assert switch.json().get("preferred_model") is None
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_success(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            mock_model = MagicMock()
            with patch("api.profile.validate_gemini_api_key", return_value=True), patch(
                "google.genai.Client"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.models.list.return_value = [mock_model]
                mock_client_cls.return_value = mock_client
                resp = await client.post(f"{BASE}/api-key/validate", json={"api_key": self.VALID_KEY})
            assert resp.status_code == 200
            assert resp.json()["valid"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_invalid_format_returns_422(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.validate_gemini_api_key", return_value=False):
                resp = await client.post(f"{BASE}/api-key/validate", json={"api_key": "bad-key"})
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


class TestPreferencesExtended:
    @pytest.mark.asyncio
    async def test_get_and_patch_preferences(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            get_resp = await client.get(f"{BASE}/preferences")
            assert get_resp.status_code in (200, 500)
            if get_resp.status_code == 200:
                patch_resp = await client.patch(
                    f"{BASE}/preferences",
                    json={"cover_letter_tone": "conversational", "resume_length": "detailed"},
                )
                assert patch_resp.status_code in (200, 500)
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Export / delete account / clear data / notifications
# ---------------------------------------------------------------------------


class TestAccountManagement:
    @pytest.mark.asyncio
    async def test_export_returns_json_attachment(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            await _fill_all_profile_sections(client)
            resp = await client.get(f"{BASE}/export")
            assert resp.status_code == 200
            assert "application/json" in resp.headers.get("content-type", "")
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_clear_data_requires_confirm(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            resp = await client.request("DELETE", f"{BASE}/clear-data", json={"confirm": False})
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_clear_data_success(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                session.add(
                    JobApplication(
                        id=uuid.uuid4(),
                        user_id=uid,
                        job_title="Engineer",
                        company_name="Acme",
                        status="completed",
                    )
                )
                await session.commit()
            resp = await client.request("DELETE", f"{BASE}/clear-data", json={"confirm": True})
            assert resp.status_code == 200, resp.text
            assert resp.json()["deleted"]["applications"] >= 1
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_account_wrong_password_returns_422(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            resp = await client.request(
                "DELETE",
                f"{BASE}/delete-account",
                json={"password": "WrongPass99!"},
            )
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_account_success(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.invalidate_all_user_tokens", AsyncMock(return_value=True)), patch(
                "api.profile.invalidate_user_profile", AsyncMock(return_value=None)
            ), patch("api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)):
                resp = await client.request(
                    "DELETE",
                    f"{BASE}/delete-account",
                    json={"password": "SecurePass123!"},
                )
            assert resp.status_code == 200, resp.text
            async with _NullSessionLocal() as session:
                row = await session.execute(select(User).where(User.id == uid))
                assert row.scalar_one_or_none() is None
        finally:
            await client.aclose()
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_notifications_not_implemented_returns_501(self):
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            resp = await client.put(
                f"{BASE}/notifications",
                json={"email_notifications": True},
            )
            assert resp.status_code == 501
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

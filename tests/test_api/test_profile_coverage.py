"""
Coverage tests for api/profile.py — validators, helpers, error paths, and edge cases.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.profile import (
    ApiKeyRequest,
    ApplicationPreferencesRequest,
    BasicInfoRequest,
    CareerPreferencesRequest,
    ClearDataRequest,
    DeleteAccountRequest,
    EducationItem,
    EducationRequest,
    SkillsQualificationsRequest,
    WorkExperienceItem,
    WorkExperienceRequest,
    _blank_to_none,
    _check_career_preferences_completion,
    _merge_resume_contact_into_profile_if_empty,
    _upsert_user_resume_asset,
    _validate_location,
    _validate_professional_name,
    _validate_profile_url_field,
    _validate_text_field,
    clear_user_data,
    delete_api_key,
    delete_stored_resume,
    delete_user_account,
    download_stored_resume,
    export_user_data,
    get_api_key_status,
    get_application_preferences,
    get_profile_completion_status,
    get_profile_data,
    get_profile_status,
    get_user_id_from_token,
    parse_resume_endpoint,
    set_api_key,
    update_application_preferences,
    update_basic_info,
    update_career_preferences,
    update_education,
    update_skills_qualifications,
    update_work_experience,
    validate_api_key_endpoint,
)
from main import app
from models.database import (
    AuthMethod,
    JobApplication,
    User,
    UserProfile,
    UserResumeAsset,
    UserWorkflowPreferences,
    WorkflowSession,
)
from tests.test_api.conftest import _NullSessionLocal
from tests.test_api.test_profile_extended import (
    BASIC_INFO,
    CAREER_PREFS,
    MOCK_PARSED_RESUME,
    _client_for,
    _create_user_with_password,
    _delete_user_data,
)
from utils.error_responses import APIError, validation_error

from tests.gemini_test_keys import DUMMY_GEMINI_API_KEY

BASE = "/api/v1/profile"
VALID_KEY = DUMMY_GEMINI_API_KEY


def _current_user(uid: uuid.UUID, email: str, **extra: Any) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "id": str(uid),
        "_id": str(uid),
        "email": email,
        "full_name": "Coverage User",
        "auth_method": extra.get("auth_method", "local"),
        "profile_completed": extra.get("profile_completed", False),
        "profile_completion_percentage": extra.get("profile_completion_percentage", 0),
        "has_google_linked": extra.get("has_google_linked", False),
        "has_password": extra.get("has_password", True),
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }


def _make_pdf_bytes(text: str = "Resume content") -> bytes:
    return b"%PDF-1.4\n" + text.encode("utf-8")


def _make_docx_bytes(text: str = "Resume") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helper / validator unit tests
# ---------------------------------------------------------------------------


class TestProfileHelperFunctions:
    def test_get_user_id_missing_raises(self) -> None:
        with pytest.raises(APIError):
            get_user_id_from_token({})

    def test_get_user_id_invalid_uuid_raises(self) -> None:
        with pytest.raises(APIError):
            get_user_id_from_token({"id": "not-a-uuid"})

    def test_get_user_id_string_converts(self) -> None:
        uid = uuid.uuid4()
        assert get_user_id_from_token({"id": str(uid)}) == uid

    def test_get_user_id_underscore_key(self) -> None:
        uid = uuid.uuid4()
        assert get_user_id_from_token({"_id": str(uid)}) == uid

    def test_get_user_id_uuid_object(self) -> None:
        uid = uuid.uuid4()
        assert get_user_id_from_token({"id": uid}) == uid

    def test_validate_professional_name_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_professional_name("   ", "Company")

    def test_validate_professional_name_invalid_chars(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_professional_name("Acme\x07Corp", "Company")

    def test_validate_text_field_none_returns_none(self) -> None:
        assert _validate_text_field(None, "Summary", 100) is None
        assert _validate_text_field("", "Summary", 100) is None

    def test_validate_text_field_too_long(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            _validate_text_field("x" * 101, "Summary", 100)

    def test_validate_text_field_invalid_chars(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_text_field("Hello\x00World", "Summary", 100)

    def test_validate_location_none_and_blank(self) -> None:
        assert _validate_location(None, "City") is None
        assert _validate_location("   ", "City") is None

    def test_validate_location_invalid(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            _validate_location("City@#$", "City")

    def test_validate_profile_url_blank_ok(self) -> None:
        _validate_profile_url_field("", "LinkedIn URL")

    def test_validate_profile_url_requires_scheme(self) -> None:
        with pytest.raises(ValueError, match="http"):
            _validate_profile_url_field("example.com/in/me", "LinkedIn URL")

    def test_validate_profile_url_too_long(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            _validate_profile_url_field("https://example.com/" + "a" * 500, "LinkedIn URL")

    def test_blank_to_none(self) -> None:
        assert _blank_to_none(None) is None
        assert _blank_to_none("  ") is None
        assert _blank_to_none(" hello ") == "hello"


class TestProfilePydanticModels:
    def test_basic_info_invalid_city(self) -> None:
        data = dict(BASIC_INFO)
        data["city"] = "Bad@City"
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_invalid_state(self) -> None:
        data = dict(BASIC_INFO)
        data["state"] = ""
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_invalid_country(self) -> None:
        data = dict(BASIC_INFO)
        data["country"] = "!!!"
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_years_negative(self) -> None:
        data = dict(BASIC_INFO)
        data["years_experience"] = -1
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_years_over_max(self) -> None:
        data = dict(BASIC_INFO)
        data["years_experience"] = 999
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_phone_too_long(self) -> None:
        data = dict(BASIC_INFO)
        data["phone"] = "1" * 50
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_basic_info_url_validators(self) -> None:
        data = dict(BASIC_INFO)
        data["linkedin_url"] = "ftp://bad"
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        data = dict(BASIC_INFO)
        data["github_url"] = "not-a-url"
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        data = dict(BASIC_INFO)
        data["portfolio_url"] = "javascript:alert(1)"
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)

    def test_work_experience_start_date_required(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="",
                is_current=False,
            )

    def test_work_experience_start_date_bad_format(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2023-13",
                is_current=False,
            )

    def test_work_experience_start_date_bad_year_month(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="abcd-ef",
                is_current=False,
            )

    def test_work_experience_start_date_year_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="1800-01",
                is_current=False,
            )

    def test_work_experience_start_date_bad_month(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2020-13",
                is_current=False,
            )

    def test_work_experience_start_date_future(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2099-01",
                is_current=False,
            )

    def test_work_experience_end_date_present(self) -> None:
        item = WorkExperienceItem(
            company="Acme",
            job_title="Dev",
            start_date="2020-01",
            end_date="Present",
            is_current=False,
        )
        assert item.end_date == "Present"

    def test_work_experience_end_date_bad_format(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2020-01",
                end_date="not-a-date",
                is_current=False,
            )

    def test_work_experience_end_date_too_far_future(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2020-01",
                end_date="2099-12",
                is_current=False,
            )

    def test_work_experience_is_current_conflict(self) -> None:
        with pytest.raises(ValidationError):
            WorkExperienceItem(
                company="Acme",
                job_title="Dev",
                start_date="2020-01",
                end_date="2021-06",
                is_current=True,
            )

    def test_work_experience_multiple_current_positions(self) -> None:
        row = {
            "company": "Acme",
            "job_title": "Dev",
            "start_date": "2020-01",
            "end_date": "Present",
            "is_current": True,
        }
        with pytest.raises(ValidationError):
            WorkExperienceRequest(work_experience=[WorkExperienceItem(**row), WorkExperienceItem(**row)])

    def test_education_start_date_validators(self) -> None:
        base = {
            "institution": "State U",
            "degree": "BS",
            "field_of_study": "CS",
            "is_current": False,
            "end_date": "2022-05",
        }
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="")
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="2020-13")
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="abcd-ef")
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="1800-01")
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="2020-13")
        with pytest.raises(ValidationError):
            EducationItem(**base, start_date="2099-01")

    def test_education_end_date_validators(self) -> None:
        with pytest.raises(ValidationError):
            EducationItem(
                institution="State U",
                degree="BS",
                field_of_study="CS",
                start_date="2018-09",
                end_date="bad-date",
                is_current=False,
            )
        with pytest.raises(ValidationError):
            EducationItem(
                institution="State U",
                degree="BS",
                field_of_study="CS",
                start_date="2018-09",
                end_date="2099-12",
                is_current=False,
            )
        with pytest.raises(ValidationError):
            EducationItem(
                institution="State U",
                degree="BS",
                field_of_study="CS",
                start_date="2018-09",
                end_date="2017-05",
                is_current=False,
            )

    def test_education_is_current_requires_empty_end(self) -> None:
        with pytest.raises(ValidationError):
            EducationItem(
                institution="State U",
                degree="BS",
                field_of_study="CS",
                start_date="2018-09",
                end_date="2022-05",
                is_current=True,
            )

    def test_education_end_required_when_not_current(self) -> None:
        with pytest.raises(ValidationError):
            EducationItem(
                institution="State U",
                degree="BS",
                field_of_study="CS",
                start_date="2018-09",
                is_current=False,
            )

    def test_skills_filters_and_validates(self) -> None:
        req = SkillsQualificationsRequest(skills=["Python", "  ", "Py", "Python", "C++"])
        assert "Python" in req.skills
        assert "C++" in req.skills
        with pytest.raises(ValidationError):
            SkillsQualificationsRequest(skills=["Bad@Skill"])

    def test_career_preferences_enum_transform(self) -> None:
        req = CareerPreferencesRequest(
            desired_company_sizes=["startup"],
            job_types=["full-time"],
            work_arrangements=["remote"],
            max_travel_preference="25",
        )
        assert req.max_travel_preference.value == "25"

    def test_career_preferences_salary_validators(self) -> None:
        with pytest.raises(ValueError, match="must be an integer"):
            CareerPreferencesRequest.validate_desired_salary_range({"min": True})
        normalized = CareerPreferencesRequest.validate_desired_salary_range({"min": "$90,000"})
        assert normalized == {"min": 90000}
        with pytest.raises(ValueError, match="must be positive"):
            CareerPreferencesRequest.validate_desired_salary_range({"min": -1})
        with pytest.raises(ValueError, match="unreasonably high"):
            CareerPreferencesRequest.validate_desired_salary_range({"max": 3000000})
        with pytest.raises(ValueError, match="Minimum salary must be less"):
            CareerPreferencesRequest.validate_desired_salary_range({"min": 150000, "max": 100000})

    def test_career_preferences_work_authorization(self) -> None:
        req = CareerPreferencesRequest(
            desired_company_sizes=["Startup (1-10 employees)"],
            job_types=["Full-time"],
            work_arrangements=["Remote"],
            work_authorization="",
        )
        assert req.work_authorization is None
        with pytest.raises(ValidationError):
            CareerPreferencesRequest(
                desired_company_sizes=["Startup (1-10 employees)"],
                job_types=["Full-time"],
                work_arrangements=["Remote"],
                work_authorization="invalid_status",
            )


class TestProfileCompletionHelpers:
    def test_career_preferences_legacy_without_work_authorization(self) -> None:
        prof = UserProfile(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            city="Austin",
            state="TX",
            country="USA",
            professional_title="Engineer",
            years_experience=4,
            summary="Summary text here.",
            work_experience=[],
            education=[],
            skills=["Python"],
            job_types=["Full-time"],
            work_arrangements=["Remote"],
            desired_company_sizes=["Startup (1-10 employees)"],
            work_authorization=None,
        )
        assert _check_career_preferences_completion(prof) is True

    @pytest.mark.asyncio
    async def test_get_profile_completion_status_updates_user(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                prof = UserProfile(
                    id=uuid.uuid4(),
                    user_id=uid,
                    city="Austin",
                    state="TX",
                    country="USA",
                    professional_title="Engineer",
                    years_experience=4,
                    summary="Summary text here.",
                    work_experience=[],
                    education=[],
                    skills=["Python"],
                    job_types=["Full-time"],
                    work_arrangements=["Remote"],
                    desired_company_sizes=["Startup (1-10 employees)"],
                    work_authorization="us_citizen",
                )
                db.add(prof)
                await db.commit()
                status = await get_profile_completion_status(uid, prof, db)
                assert status["completion_percentage"] == 100
        finally:
            await _delete_user_data(uid)


class TestMergeResumeContact:
    def test_merge_resume_contact_fills_empty_fields(self) -> None:
        prof = UserProfile(id=uuid.uuid4(), user_id=uuid.uuid4())
        parsed = {
            "phone": "+1 555 0100",
            "linkedin_url": "https://linkedin.com/in/test",
            "github_url": "https://github.com/test",
            "portfolio_url": "https://portfolio.example",
        }
        _merge_resume_contact_into_profile_if_empty(prof, parsed)
        assert prof.phone == "+1 555 0100"
        assert prof.linkedin_url == "https://linkedin.com/in/test"

    def test_merge_resume_contact_skips_existing_and_invalid(self) -> None:
        prof = UserProfile(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            phone="+1 existing",
            linkedin_url="https://existing.example",
        )
        _merge_resume_contact_into_profile_if_empty(
            prof,
            {
                "phone": "+1 new",
                "linkedin_url": "not-a-url",
                "github_url": "https://github.com/new",
            },
        )
        assert prof.phone == "+1 existing"
        assert prof.linkedin_url == "https://existing.example"
        assert prof.github_url == "https://github.com/new"


# ---------------------------------------------------------------------------
# Direct endpoint calls — DB error paths and branches
# ---------------------------------------------------------------------------


class TestProfileEndpointDirectCalls:
    @pytest.mark.asyncio
    async def test_get_profile_status_direct(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                result = await get_profile_status(_current_user(uid, email), db)
                assert result.completion_percentage >= 0
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_profile_status_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await get_profile_status(_current_user(uid, "x@example.com"), db)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_basic_info_create_and_update_paths(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                req = BasicInfoRequest(**BASIC_INFO)
                await update_basic_info(req, _current_user(uid, email), db)
                req.summary = "Updated summary with enough characters here."
                await update_basic_info(req, _current_user(uid, email), db)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_basic_info_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_basic_info(
                            BasicInfoRequest(**BASIC_INFO),
                            _current_user(uid, email),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_work_experience_create_path(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                req = WorkExperienceRequest(work_experience=[])
                await update_work_experience(req, _current_user(uid, email), db)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_work_experience_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_work_experience(
                            WorkExperienceRequest(work_experience=[]),
                            _current_user(uid, email),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_education_create_path(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                await update_education(
                    EducationRequest(education=[]),
                    _current_user(uid, email),
                    db,
                )
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_education_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_education(
                            EducationRequest(education=[]),
                            _current_user(uid, email),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_skills_create_path(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                await update_skills_qualifications(
                    SkillsQualificationsRequest(skills=["Python", "Go"]),
                    _current_user(uid, email),
                    db,
                )
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_skills_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_skills_qualifications(
                            SkillsQualificationsRequest(skills=["Python"]),
                            _current_user(uid, email),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_career_preferences_create_path(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                req = CareerPreferencesRequest(**CAREER_PREFS)
                await update_career_preferences(req, _current_user(uid, email), db)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_update_career_preferences_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_career_preferences(
                            CareerPreferencesRequest(**CAREER_PREFS),
                            _current_user(uid, email),
                            db,
                        )
            assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_profile_data_cache_miss_and_resume_file(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path=f"{uid}/resume.txt",
                        original_filename="resume.txt",
                        mime_type="text/plain",
                        byte_size=10,
                        sha256_hex="abc",
                    )
                )
                await db.commit()
                with patch("api.profile.get_cached_user_profile", AsyncMock(return_value=None)), patch(
                    "api.profile.cache_user_profile", AsyncMock(return_value=None)
                ), patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)):
                    data = await get_profile_data(_current_user(uid, email), db)
                assert data["profile_data"]["resume_file"]["has_file"] is True
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_profile_data_cache_hit(self) -> None:
        uid = uuid.uuid4()
        cached = {"user_info": {"id": str(uid)}, "profile_data": {}, "completion_status": {}}
        async with _NullSessionLocal() as db:
            with patch("api.profile.get_cached_user_profile", AsyncMock(return_value=cached)):
                data = await get_profile_data(_current_user(uid, "hit@example.com"), db)
        assert data == cached

    @pytest.mark.asyncio
    async def test_get_profile_data_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch("api.profile.get_user_id_from_token", side_effect=RuntimeError("boom")):
                with pytest.raises(Exception) as exc:
                    await get_profile_data(_current_user(uid, "err@example.com"), db)
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Resume parse / stored resume
# ---------------------------------------------------------------------------


class TestResumeCoverage:
    @pytest.mark.asyncio
    async def test_upsert_user_resume_asset_insert_and_update(self) -> None:
        uid, email = await _create_user_with_password()
        content = b"resume bytes"
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.save_resume_bytes", return_value=("path/a", "sha", "txt")), patch(
                    "api.profile.delete_resume_file"
                ), patch("api.profile.settings"
                ) as mock_settings:
                    mock_settings.user_resume_storage_dir = "/tmp/resumes"
                    await _upsert_user_resume_asset(db, uid, content, "resume.txt", "txt")
                    await db.flush()
                    await _upsert_user_resume_asset(db, uid, content, "resume2.txt", "txt")
                    await db.commit()
                    row = (
                        await db.execute(select(UserResumeAsset).where(UserResumeAsset.user_id == uid))
                    ).scalar_one()
                    assert row.original_filename == "resume2.txt"
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_rate_limit(self, authed_client_with_user: AsyncClient) -> None:
        with patch(
            "api.profile.check_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ):
            files = {"resume": ("resume.txt", b"hello resume", "text/plain")}
            resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_parse_resume_missing_filename(self, authed_client_with_user: AsyncClient) -> None:
        files = {"resume": ("", b"hello", "text/plain")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_resume_empty_file(self, authed_client_with_user: AsyncClient) -> None:
        files = {"resume": ("resume.txt", b"", "text/plain")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_resume_bad_magic_bytes(self, authed_client_with_user: AsyncClient) -> None:
        files = {"resume": ("resume.pdf", b"NOTPDF", "application/pdf")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_resume_non_utf8_txt(self, authed_client_with_user: AsyncClient) -> None:
        files = {"resume": ("resume.txt", b"\xff\xfe", "text/plain")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_resume_decrypt_failure_still_parses(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                user = (await session.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "encrypted-blob"
                await session.commit()
            with patch("api.profile.parse_resume_from_file", AsyncMock(return_value=MOCK_PARSED_RESUME)), patch(
                "utils.encryption.decrypt_api_key", side_effect=RuntimeError("decrypt fail")
            ), patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                mock_settings.user_resume_storage_dir = "/tmp/resumes"
                with patch("api.profile.save_resume_bytes", return_value=("p", "sha", "txt")), patch(
                    "api.profile.invalidate_user_profile", AsyncMock(return_value=None)
                ):
                    files = {"resume": ("resume.txt", b"hello world resume", "text/plain")}
                    resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 200
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_persist_failure_still_returns_success(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.parse_resume_from_file", AsyncMock(return_value=MOCK_PARSED_RESUME)), patch(
                "api.profile.settings"
            ) as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                mock_settings.user_resume_storage_dir = "/tmp/resumes"
                with patch(
                    "api.profile._upsert_user_resume_asset",
                    AsyncMock(side_effect=RuntimeError("disk full")),
                ):
                    files = {"resume": ("resume.txt", b"hello world resume", "text/plain")}
                    resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_validation_error(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch(
                "api.profile.parse_resume_from_file",
                AsyncMock(side_effect=ValueError("bad resume")),
            ), patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                files = {"resume": ("resume.txt", b"hello world resume", "text/plain")}
                resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch(
                "api.profile.parse_resume_from_file",
                AsyncMock(side_effect=RuntimeError("llm down")),
            ), patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                files = {"resume": ("resume.txt", b"hello world resume", "text/plain")}
                resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 500
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_download_resume_invalid_path(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                session.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path="../escape",
                        original_filename="resume.txt",
                        mime_type="text/plain",
                        byte_size=1,
                        sha256_hex="x",
                    )
                )
                await session.commit()
            with patch("api.profile.resume_absolute_path", side_effect=ValueError("bad path")):
                resp = await client.get(f"{BASE}/resume")
            assert resp.status_code == 404
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_download_resume_missing_file(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                session.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path=f"{uid}/missing.txt",
                        original_filename="missing.txt",
                        mime_type="text/plain",
                        byte_size=1,
                        sha256_hex="x",
                    )
                )
                await session.commit()
            from pathlib import Path

            with patch("api.profile.resume_absolute_path", return_value=Path("/tmp/does-not-exist-resume.txt")):
                resp = await client.get(f"{BASE}/resume")
            assert resp.status_code == 404
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


class TestApiKeyCoverage:
    @pytest.mark.asyncio
    async def test_api_key_status_with_encrypted_key(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.encrypt_api_key", return_value="enc"), patch(
                    "utils.encryption.decrypt_api_key", return_value=VALID_KEY
                ):
                    await set_api_key(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                        db,
                    )
                    status = await get_api_key_status(_current_user(uid, email), db)
                assert status.has_user_key is True
                assert status.key_preview is not None
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_api_key_status_decrypt_failure(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "blob"
                prefs = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one_or_none()
                if prefs:
                    prefs.preferred_provider = "gemini"
                await db.commit()
                with patch("utils.encryption.decrypt_api_key", side_effect=RuntimeError("bad")):
                    status = await get_api_key_status(_current_user(uid, email), db)
                assert status.key_preview == "(invalid)"
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_api_key_status_user_not_found(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with pytest.raises(Exception) as exc:
                await get_api_key_status(_current_user(uid, "ghost@example.com"), db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_api_key_status_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await get_api_key_status(_current_user(uid, "x@example.com"), db)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_set_api_key_invalid_format(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.validate_gemini_api_key", return_value=False):
                    with pytest.raises(Exception) as exc:
                        await set_api_key(
                            ApiKeyRequest(api_key=VALID_KEY),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_set_api_key_value_error_and_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.validate_gemini_api_key", return_value=True), patch(
                    "api.profile.encrypt_api_key", side_effect=ValueError("bad key")
                ):
                    with pytest.raises(Exception) as exc:
                        await set_api_key(
                            ApiKeyRequest(api_key=VALID_KEY),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 422
                with patch("api.profile.validate_gemini_api_key", return_value=True), patch(
                    "api.profile.encrypt_api_key", return_value="enc"
                ), patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc2:
                        await set_api_key(
                            ApiKeyRequest(api_key=VALID_KEY),
                            _current_user(uid, email),
                            db,
                        )
                assert exc2.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_api_key_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await delete_api_key(
                            current_user=_current_user(uid, email),
                            db=db,
                        )
                assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_rate_limit(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            with patch("api.profile.check_rate_limit", AsyncMock(return_value=(False, 0))):
                with pytest.raises(Exception) as exc:
                    await validate_api_key_endpoint(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                    )
            assert exc.value.status_code == 429
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_no_models(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            mock_client = MagicMock()
            mock_client.models.list.return_value = []
            with patch("api.profile.validate_gemini_api_key", return_value=True), patch(
                "google.genai.Client", return_value=mock_client
            ):
                with pytest.raises(Exception) as exc:
                    await validate_api_key_endpoint(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_api_failure_and_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            mock_client = MagicMock()
            mock_client.models.list.side_effect = RuntimeError("google down")
            with patch("api.profile.validate_gemini_api_key", return_value=True), patch(
                "google.genai.Client", return_value=mock_client
            ):
                with pytest.raises(Exception) as exc:
                    await validate_api_key_endpoint(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                    )
            assert exc.value.status_code == 422
            with patch("api.profile.validate_gemini_api_key", side_effect=RuntimeError("boom")):
                with pytest.raises(Exception) as exc2:
                    await validate_api_key_endpoint(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                    )
            assert exc2.value.status_code == 500
        finally:
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


class TestPreferencesCoverage:
    @pytest.mark.asyncio
    async def test_get_preferences_existing_row(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                prefs = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one()
                prefs.workflow_gate_threshold = 0.6
                await db.commit()
                resp = await get_application_preferences(_current_user(uid, email), db)
                assert resp.workflow_gate_threshold == 0.6
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_preferences_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await get_application_preferences(_current_user(uid, "x@example.com"), db)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_patch_preferences_create_and_invalid_fields(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                req = ApplicationPreferencesRequest(
                    cover_letter_tone="conversational",
                    resume_length="detailed",
                    preferred_provider="gemini",
                    preferred_model="gemini-2.5-flash",
                )
                resp = await update_application_preferences(req, _current_user(uid, email), db)
                assert resp.cover_letter_tone == "conversational"
                with pytest.raises(Exception) as exc:
                    await update_application_preferences(
                        ApplicationPreferencesRequest(cover_letter_tone="angry"),
                        _current_user(uid, email),
                        db,
                    )
                assert exc.value.status_code == 422
                with pytest.raises(Exception) as exc2:
                    await update_application_preferences(
                        ApplicationPreferencesRequest(resume_length="verbose"),
                        _current_user(uid, email),
                        db,
                    )
                assert exc2.value.status_code == 422
                with pytest.raises(Exception) as exc3:
                    await update_application_preferences(
                        ApplicationPreferencesRequest(preferred_model="bad-model"),
                        _current_user(uid, email),
                        db,
                    )
                assert exc3.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_patch_preferences_integrity_error_recovery(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                existing = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one()
                existing.workflow_gate_threshold = 0.4
                await db.commit()

                class FakeNested:
                    async def __aenter__(self):
                        raise IntegrityError("", {}, None)

                    async def __aexit__(self, *args):
                        return False

                with patch.object(db, "begin_nested", return_value=FakeNested()):
                    resp = await update_application_preferences(
                        ApplicationPreferencesRequest(auto_generate_documents=True),
                        _current_user(uid, email),
                        db,
                    )
                assert resp.auto_generate_documents is True
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_patch_preferences_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await update_application_preferences(
                            ApplicationPreferencesRequest(resume_length="concise"),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Export / delete account / clear data
# ---------------------------------------------------------------------------


class TestAccountDataCoverage:
    @pytest.mark.asyncio
    async def test_export_rate_limit(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.get_settings") as mock_settings:
                    mock_settings.return_value.is_production = True
                    with patch(
                        "api.profile.get_rate_limit_remaining",
                        AsyncMock(return_value=0),
                    ):
                        with pytest.raises(Exception) as exc:
                            await export_user_data(_current_user(uid, email), db)
                assert exc.value.status_code == 429
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_export_with_applications_and_sessions(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserProfile(
                        id=uuid.uuid4(),
                        user_id=uid,
                        city="Austin",
                        state="TX",
                        country="USA",
                        professional_title="Engineer",
                        years_experience=4,
                        summary="Summary text here.",
                    )
                )
                db.add(
                    JobApplication(
                        id=uuid.uuid4(),
                        user_id=uid,
                        job_title="Engineer",
                        company_name="Acme",
                        status="completed",
                    )
                )
                db.add(
                    WorkflowSession(
                        id=uuid.uuid4(),
                        user_id=uid,
                        session_id=str(uuid.uuid4()),
                        workflow_status="completed",
                    )
                )
                await db.commit()
                resp = await export_user_data(_current_user(uid, email), db)
                assert resp.headers["content-type"].startswith("application/json")
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_export_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await export_user_data(_current_user(uid, "x@example.com"), db)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_account_rate_limit(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.check_rate_limit", AsyncMock(return_value=(False, 0))):
                    with pytest.raises(Exception) as exc:
                        await delete_user_account(
                            DeleteAccountRequest(password="SecurePass123!"),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 429
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_google_account_paths(self) -> None:
        uid = uuid.uuid4()
        email = f"google_{uid.hex[:8]}@example.com"
        async with _NullSessionLocal() as session:
            session.add(
                User(
                    id=uid,
                    email=email,
                    password_hash=None,
                    auth_method=AuthMethod.GOOGLE.value,
                    google_id=f"g_{uid.hex[:8]}",
                    full_name="Google User",
                    email_verified=True,
                )
            )
            await session.commit()
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await delete_user_account(
                        DeleteAccountRequest(password="wrong"),
                        _current_user(uid, email, auth_method="google", has_password=False),
                        db,
                    )
                assert exc.value.status_code == 422
                with patch("api.profile.invalidate_all_user_tokens", AsyncMock(side_effect=RuntimeError("redis"))), patch(
                    "api.profile.invalidate_user_profile", AsyncMock(side_effect=RuntimeError("cache"))
                ), patch("api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)):
                    result = await delete_user_account(
                        DeleteAccountRequest(password=""),
                        _current_user(uid, email, auth_method="google", has_password=False),
                        db,
                    )
                assert result["message"]
        finally:
            async with _NullSessionLocal() as session:
                await session.execute(User.__table__.delete().where(User.id == uid))
                await session.commit()

    @pytest.mark.asyncio
    async def test_delete_account_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await delete_user_account(
                            DeleteAccountRequest(password="SecurePass123!"),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_clear_data_rate_limit(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.check_rate_limit", AsyncMock(return_value=(False, 0))):
                    with pytest.raises(Exception) as exc:
                        await clear_user_data(
                            ClearDataRequest(confirm=True),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 429
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_clear_data_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await clear_user_data(
                            ClearDataRequest(confirm=True),
                            _current_user(uid, email),
                            db,
                        )
                assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_missing_sections_list(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            await client.put(f"{BASE}/basic-info", json=BASIC_INFO)
            resp = await client.post(f"{BASE}/complete")
            assert resp.status_code == 422
            assert "Work Experience" in resp.json().get("message", "")
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_no_profile_row(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                from api.profile import complete_profile

                with pytest.raises(Exception) as exc:
                    await complete_profile(_current_user(uid, email), db)
                assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_internal_error(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserProfile(
                        id=uuid.uuid4(),
                        user_id=uid,
                        city="Austin",
                        state="TX",
                        country="USA",
                        professional_title="Engineer",
                        years_experience=4,
                        summary="Summary text here.",
                        work_experience=[],
                        education=[],
                        skills=["Python"],
                        job_types=["Full-time"],
                        work_arrangements=["Remote"],
                        desired_company_sizes=["Startup (1-10 employees)"],
                        work_authorization="us_citizen",
                    )
                )
                await db.commit()
                from api.profile import complete_profile

                with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("db"))):
                    with pytest.raises(Exception) as exc:
                        await complete_profile(_current_user(uid, email), db)
                assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)


# ---------------------------------------------------------------------------
# Remaining line coverage
# ---------------------------------------------------------------------------


class TestProfileCoverageRemaining:
    def test_basic_info_validator_branches(self) -> None:
        data = dict(BASIC_INFO)
        data["city"] = "   "
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        data = dict(BASIC_INFO)
        data["state"] = "   "
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        data = dict(BASIC_INFO)
        data["country"] = "   "
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        with pytest.raises(ValueError):
            BasicInfoRequest.validate_years_experience(-1)
        with pytest.raises(ValueError):
            BasicInfoRequest.validate_years_experience(999)
        data = dict(BASIC_INFO)
        data["phone"] = "x" * 50
        with pytest.raises(ValidationError):
            BasicInfoRequest(**data)
        data = dict(BASIC_INFO)
        data["linkedin_url"] = "https://linkedin.com/in/test"
        data["github_url"] = "https://github.com/test"
        data["portfolio_url"] = "https://portfolio.example"
        req = BasicInfoRequest(**data)
        assert req.linkedin_url.startswith("https://")

    def test_work_experience_item_direct_validators(self) -> None:
        with pytest.raises(ValueError):
            WorkExperienceItem.validate_start_date("")
        with pytest.raises(ValueError):
            WorkExperienceItem.validate_start_date("abcd-ef")
        assert WorkExperienceItem.validate_end_date(None, {}) is None
        with pytest.raises(ValueError):
            WorkExperienceItem.validate_end_date("bad", {})

    def test_education_item_direct_validators(self) -> None:
        long_field = "A" * 201
        with pytest.raises(ValueError):
            EducationItem.validate_field_of_study(long_field)
        with pytest.raises(ValueError):
            EducationItem.validate_edu_start_date("")
        with pytest.raises(ValueError):
            EducationItem.validate_edu_start_date("abcd-ef")
        assert EducationItem.validate_edu_end_date(None, {}) is None
        with pytest.raises(ValueError):
            EducationItem.validate_edu_end_date("bad-date", {})

    def test_skills_empty_list_validator(self) -> None:
        assert SkillsQualificationsRequest.validate_skills_list([]) == []

    def test_career_enum_transform_edge_cases(self) -> None:
        info_empty = MagicMock(field_name="job_types")
        assert CareerPreferencesRequest.transform_enums([], info_empty) == []
        info_unknown = MagicMock(field_name="unknown_field")
        assert CareerPreferencesRequest.transform_enums(["x"], info_unknown) == ["x"]
        info_job = MagicMock(field_name="job_types")
        out = CareerPreferencesRequest.transform_enums(["full-time"], info_job)
        assert out[0].value == "Full-time"
        info_travel = MagicMock(field_name="max_travel_preference")
        assert CareerPreferencesRequest.transform_enums("25", info_travel).value == "25"
        info_bad = MagicMock(field_name="job_types")
        assert CareerPreferencesRequest.transform_enums(["not-an-enum"], info_bad) == ["not-an-enum"]

    def test_career_salary_edge_cases(self) -> None:
        assert CareerPreferencesRequest.validate_desired_salary_range(None) is None
        assert CareerPreferencesRequest.validate_desired_salary_range({}) is None
        assert CareerPreferencesRequest.validate_desired_salary_range({"min": "no digits"}) is None
        with pytest.raises(ValueError):
            CareerPreferencesRequest.validate_desired_salary_range({"min": object()})

    def test_merge_resume_skips_invalid_url(self) -> None:
        prof = UserProfile(id=uuid.uuid4(), user_id=uuid.uuid4())
        _merge_resume_contact_into_profile_if_empty(
            prof,
            {"portfolio_url": "ftp://bad.example"},
        )
        assert prof.portfolio_url is None

    @pytest.mark.asyncio
    async def test_update_existing_profile_rows(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(UserProfile(id=uuid.uuid4(), user_id=uid))
                await db.commit()
                user = _current_user(uid, email)
                await update_work_experience(WorkExperienceRequest(work_experience=[]), user, db)
                await update_education(EducationRequest(education=[]), user, db)
                await update_skills_qualifications(
                    SkillsQualificationsRequest(skills=["Go"]), user, db
                )
                await update_career_preferences(CareerPreferencesRequest(**CAREER_PREFS), user, db)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_profile_without_resume_file(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.get_cached_user_profile", AsyncMock(return_value=None)), patch(
                    "api.profile.cache_user_profile", AsyncMock(return_value=None)
                ):
                    data = await get_profile_data(_current_user(uid, email), db)
                assert data["profile_data"]["resume_file"]["has_file"] is False
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_full_success_with_user_key(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            async with _NullSessionLocal() as session:
                session.add(
                    UserProfile(
                        id=uuid.uuid4(),
                        user_id=uid,
                        city="Austin",
                        state="TX",
                        country="USA",
                    )
                )
                user = (await session.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "enc"
                await session.commit()
            parsed = dict(MOCK_PARSED_RESUME)
            parsed["phone"] = "+1 555 9999"
            parsed["linkedin_url"] = "ftp://skip.me"
            with patch("api.profile.parse_resume_from_file", AsyncMock(return_value=parsed)), patch(
                "utils.encryption.decrypt_api_key", return_value=VALID_KEY
            ), patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = None
                mock_settings.use_vertex_ai = False
                mock_settings.user_resume_storage_dir = "/tmp/resumes"
                with patch("api.profile.save_resume_bytes", return_value=("p", "sha", "pdf")), patch(
                    "api.profile.invalidate_user_profile", AsyncMock(return_value=None)
                ):
                    files = {"resume": ("resume.pdf", _make_pdf_bytes(), "application/pdf")}
                    resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 200
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_unsupported_and_empty_filename(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                resp = await client.post(
                    f"{BASE}/parse-resume",
                    files={"resume": ("resume.xyz", b"data", "application/octet-stream")},
                )
            assert resp.status_code == 422
            upload = MagicMock()
            upload.filename = None
            upload.read = AsyncMock(return_value=b"hello")
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception):
                    await parse_resume_endpoint(upload, _current_user(uid, email), db)
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_stored_resume_download_and_delete_direct(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path=f"{uid}/r.txt",
                        original_filename="r.txt",
                        mime_type="text/plain",
                        byte_size=4,
                        sha256_hex="abc",
                    )
                )
                await db.commit()
                from pathlib import Path
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(b"data")
                    tmp_path = Path(tmp.name)
                with patch("api.profile.resume_absolute_path", return_value=tmp_path), patch(
                    "api.profile.delete_resume_file"
                ), patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)):
                    resp = await download_stored_resume(_current_user(uid, email), db)
                    assert resp.path == str(tmp_path)
                    out = await delete_stored_resume(_current_user(uid, email), db)
                    assert "deleted" in out["message"].lower()
                tmp_path.unlink(missing_ok=True)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_api_key_status_short_preview(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "enc"
                prefs = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one_or_none()
                if prefs:
                    prefs.preferred_provider = "gemini"
                await db.commit()
                with patch("utils.encryption.decrypt_api_key", return_value="short"):
                    status = await get_api_key_status(_current_user(uid, email), db)
                assert status.key_preview == "****"
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_preferences_defaults(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                prefs = await get_application_preferences(_current_user(uid, email), db)
                assert prefs.cover_letter_tone == "professional"
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_patch_preferences_gate_threshold(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                resp = await update_application_preferences(
                    ApplicationPreferencesRequest(workflow_gate_threshold=0.75),
                    _current_user(uid, email),
                    db,
                )
                assert resp.workflow_gate_threshold == 0.75
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_export_user_not_found(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute") as mock_exec:
                user_result = MagicMock()
                user_result.scalar_one_or_none.return_value = None
                mock_exec.return_value = user_result
                with pytest.raises(Exception) as exc:
                    await export_user_data(_current_user(uid, "ghost@example.com"), db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_account_user_not_found_and_with_resume(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = None
            with patch.object(db, "execute", AsyncMock(return_value=user_result)):
                with pytest.raises(Exception) as exc:
                    await delete_user_account(
                        DeleteAccountRequest(password=""),
                        _current_user(uid, "ghost@example.com", auth_method="google"),
                        db,
                    )
            assert exc.value.status_code == 404

        uid2, email2 = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid2,
                        storage_relative_path=f"{uid2}/r.pdf",
                        original_filename="r.pdf",
                        mime_type="application/pdf",
                        byte_size=10,
                        sha256_hex="x",
                    )
                )
                await db.commit()
                with patch("api.profile.invalidate_all_user_tokens", AsyncMock(return_value=True)), patch(
                    "api.profile.delete_resume_file"
                ), patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                    "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
                ):
                    result = await delete_user_account(
                        DeleteAccountRequest(password="SecurePass123!"),
                        _current_user(uid2, email2),
                        db,
                    )
                assert result["deleted"]["profile"] is False
        finally:
            async with _NullSessionLocal() as session:
                row = await session.execute(select(User).where(User.id == uid2))
                if row.scalar_one_or_none() is None:
                    pass
                else:
                    await _delete_user_data(uid2)

    @pytest.mark.asyncio
    async def test_clear_data_success_counts(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    JobApplication(
                        id=uuid.uuid4(),
                        user_id=uid,
                        job_title="Dev",
                        company_name="Co",
                        status="completed",
                    )
                )
                db.add(
                    WorkflowSession(
                        id=uuid.uuid4(),
                        user_id=uid,
                        session_id=str(uuid.uuid4()),
                        workflow_status="completed",
                    )
                )
                await db.commit()
                result = await clear_user_data(
                    ClearDataRequest(confirm=True),
                    _current_user(uid, email),
                    db,
                )
                assert result["deleted"]["applications"] == 1
                assert result["deleted"]["workflow_sessions"] == 1
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_lists_all_missing_sections(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserProfile(
                        id=uuid.uuid4(),
                        user_id=uid,
                        city="Austin",
                        state="TX",
                        country="USA",
                        professional_title="Engineer",
                        years_experience=4,
                        summary="Summary text here.",
                    )
                )
                await db.commit()
                from api.profile import complete_profile

                with pytest.raises(Exception) as exc:
                    await complete_profile(_current_user(uid, email), db)
                msg = exc.value.detail if hasattr(exc.value, "detail") else str(exc.value)
                assert "Skills" in str(msg)
        finally:
            await _delete_user_data(uid)

    def test_basic_info_phone_and_url_direct_validators(self) -> None:
        assert BasicInfoRequest.validate_phone("") == ""
        assert BasicInfoRequest.validate_phone(" 555 ") == "555"
        with pytest.raises(ValueError):
            BasicInfoRequest.validate_phone("x" * 50)
        assert BasicInfoRequest.validate_linkedin_url("") == ""
        assert BasicInfoRequest.validate_github_url("  ") == ""
        assert BasicInfoRequest.validate_portfolio_url("") == ""
        assert (
            BasicInfoRequest.validate_linkedin_url("https://linkedin.com/in/me")
            == "https://linkedin.com/in/me"
        )

    def test_work_start_date_map_value_error(self) -> None:
        with patch("api.profile.map", side_effect=ValueError("bad")):
            with pytest.raises(ValueError):
                WorkExperienceItem.validate_start_date("2020-01")

    def test_education_date_edge_validators(self) -> None:
        with pytest.raises(ValueError):
            EducationItem.validate_edu_start_date("1800-01")
        with pytest.raises(ValueError):
            EducationItem.validate_edu_start_date("2020-13")
        assert EducationItem.validate_edu_end_date("2022-05", {"start_date": "not-a-date"}) == "2022-05"

    def test_career_enum_value_error_fallback(self) -> None:
        info = MagicMock(field_name="job_types")
        out = CareerPreferencesRequest.transform_enums(["__invalid__"], info)
        assert out == ["__invalid__"]

    @pytest.mark.asyncio
    async def test_get_profile_http_exception_reraise(self) -> None:
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await get_profile_data({}, db)

    @pytest.mark.asyncio
    async def test_update_endpoints_http_exception_reraise(self) -> None:
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await update_work_experience(
                    WorkExperienceRequest(work_experience=[]),
                    {},
                    db,
                )
            with pytest.raises(APIError):
                await update_education(EducationRequest(education=[]), {}, db)

    @pytest.mark.asyncio
    async def test_complete_profile_success_invalidates_cache(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserProfile(
                        id=uuid.uuid4(),
                        user_id=uid,
                        city="Austin",
                        state="TX",
                        country="USA",
                        professional_title="Engineer",
                        years_experience=4,
                        summary="Summary text here.",
                        work_experience=[],
                        education=[],
                        skills=["Python"],
                        job_types=["Full-time"],
                        work_arrangements=["Remote"],
                        desired_company_sizes=["Startup (1-10 employees)"],
                        work_authorization="us_citizen",
                    )
                )
                await db.commit()
                from api.profile import complete_profile

                with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)) as mock_inv:
                    result = await complete_profile(_current_user(uid, email), db)
                assert result["profile_completed"] is True
                mock_inv.assert_awaited()
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_complete_profile_missing_basic_info_branch(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(UserProfile(id=uuid.uuid4(), user_id=uid, skills=["Python"]))
                await db.commit()
                from api.profile import complete_profile

                with pytest.raises(Exception) as exc:
                    await complete_profile(_current_user(uid, email), db)
                assert "Basic Info" in str(getattr(exc.value, "detail", exc.value))
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_api_key_status_long_preview_and_delete_success(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "enc"
                prefs = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one_or_none()
                if prefs:
                    prefs.preferred_provider = "gemini"
                await db.commit()
                with patch("utils.encryption.decrypt_api_key", return_value=VALID_KEY):
                    status = await get_api_key_status(_current_user(uid, email), db)
                assert "..." in (status.key_preview or "")
                with patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)), patch(
                    "api.profile.invalidate_user_llm_cache", AsyncMock(return_value=None)
                ) as mock_llm:
                    await delete_api_key(
                        current_user=_current_user(uid, email),
                        db=db,
                    )
                mock_llm.assert_awaited()
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_validate_api_key_invalid_format_before_api(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            with patch("api.profile.validate_gemini_api_key", return_value=False):
                with pytest.raises(Exception) as exc:
                    await validate_api_key_endpoint(
                        ApiKeyRequest(api_key=VALID_KEY),
                        _current_user(uid, email),
                    )
            assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_preferences_integrity_error_on_create(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                existing = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one()
                existing.workflow_gate_threshold = 0.3
                await db.commit()

                class FakeNested:
                    async def __aenter__(self):
                        raise IntegrityError("", {}, None)

                    async def __aexit__(self, *args):
                        return False

                with patch.object(db, "begin_nested", return_value=FakeNested()):
                    resp = await update_application_preferences(
                        ApplicationPreferencesRequest(auto_generate_documents=True),
                        _current_user(uid, email),
                        db,
                    )
                assert resp.auto_generate_documents is True
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_preferences_create_integrity_error_first_insert(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                existing = UserWorkflowPreferences(
                    id=uuid.uuid4(),
                    user_id=uid,
                    workflow_gate_threshold=0.5,
                    auto_generate_documents=False,
                    cover_letter_tone="professional",
                    resume_length="concise",
                )

                class FakeNested:
                    async def __aenter__(self):
                        raise IntegrityError("", {}, None)

                    async def __aexit__(self, *args):
                        return False

                call_count = {"n": 0}

                async def fake_execute(stmt, *args, **kwargs):
                    call_count["n"] += 1
                    result = MagicMock()
                    if call_count["n"] == 1:
                        result.scalar_one_or_none.return_value = None
                    elif call_count["n"] == 2:
                        result.scalar_one.return_value = existing
                    else:
                        result.scalar_one_or_none.return_value = existing
                    return result

                with patch.object(db, "execute", side_effect=fake_execute), patch.object(
                    db, "begin_nested", return_value=FakeNested()
                ), patch.object(db, "commit", AsyncMock(return_value=None)):
                    resp = await update_application_preferences(
                        ApplicationPreferencesRequest(cover_letter_tone="enthusiastic"),
                        _current_user(uid, email),
                        db,
                    )
                assert resp.cover_letter_tone == "enthusiastic"
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_account_wrong_password_local_user(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await delete_user_account(
                        DeleteAccountRequest(password="WrongPass99!"),
                        _current_user(uid, email),
                        db,
                    )
                assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_empty_content_via_http(self) -> None:
        uid, email = await _create_user_with_password()
        client = await _client_for(uid, email)
        try:
            with patch("api.profile.settings") as mock_settings:
                mock_settings.gemini_api_key = VALID_KEY
                mock_settings.use_vertex_ai = False
                files = {"resume": ("resume.txt", b"", "text/plain")}
                resp = await client.post(f"{BASE}/parse-resume", files=files)
            assert resp.status_code == 422
        finally:
            await client.aclose()
            app.dependency_overrides.clear()
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_success_persists_profile_merge(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(UserProfile(id=uuid.uuid4(), user_id=uid))
                user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "enc"
                await db.commit()
                upload = MagicMock()
                upload.filename = "resume.txt"
                upload.read = AsyncMock(return_value=b"Resume text long enough for parsing.")
                with patch("api.profile.parse_resume_from_file", AsyncMock(return_value=MOCK_PARSED_RESUME)), patch(
                    "utils.encryption.decrypt_api_key", return_value=VALID_KEY
                ), patch("api.profile.settings") as mock_settings, patch(
                    "api.profile.save_resume_bytes", return_value=("rel/path", "sha", "txt")
                ), patch("api.profile.invalidate_user_profile", AsyncMock(return_value=None)):
                    mock_settings.gemini_api_key = None
                    mock_settings.use_vertex_ai = False
                    mock_settings.user_resume_storage_dir = "/tmp/resumes"
                    resp = await parse_resume_endpoint(upload, _current_user(uid, email), db)
                assert resp.success is True
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_value_error_and_http_exception(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"hello world resume content")
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.parse_resume_from_file", AsyncMock(side_effect=ValueError("bad"))), patch(
                    "api.profile.settings"
                ) as mock_settings:
                    mock_settings.gemini_api_key = VALID_KEY
                    mock_settings.use_vertex_ai = False
                    with pytest.raises(Exception) as exc:
                        await parse_resume_endpoint(upload, _current_user(uid, email), db)
                    assert exc.value.status_code == 422
                with patch(
                    "api.profile.get_user_id_from_token",
                    side_effect=validation_error("session"),
                ):
                    with pytest.raises(Exception):
                        await parse_resume_endpoint(upload, _current_user(uid, email), db)
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_download_resume_not_found_paths(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await download_stored_resume(_current_user(uid, email), db)
                assert exc.value.status_code == 404
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_delete_resume_not_found(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await delete_stored_resume(_current_user(uid, email), db)
                assert exc.value.status_code == 404
        finally:
            await _delete_user_data(uid)

    def test_education_start_date_map_value_error(self) -> None:
        with patch("api.profile.map", side_effect=ValueError("bad")):
            with pytest.raises(ValueError):
                EducationItem.validate_edu_start_date("2020-01")

    def test_career_enum_non_string_passthrough(self) -> None:
        info = MagicMock(field_name="job_types")
        out = CareerPreferencesRequest.transform_enums([123], info)
        assert out == [123]

    @pytest.mark.asyncio
    async def test_parse_resume_no_api_key_and_decrypt_warning(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"hello world resume text here")
        try:
            async with _NullSessionLocal() as db:
                user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
                user.gemini_api_key_encrypted = "enc"
                prefs = (
                    await db.execute(
                        select(UserWorkflowPreferences).where(
                            UserWorkflowPreferences.user_id == uid
                        )
                    )
                ).scalar_one_or_none()
                if prefs:
                    prefs.preferred_provider = None
                await db.commit()
                with patch("utils.encryption.decrypt_api_key", side_effect=RuntimeError("decrypt fail")), patch(
                    "api.profile.settings"
                ) as mock_settings:
                    mock_settings.gemini_api_key = None
                    mock_settings.use_vertex_ai = False
                    with pytest.raises(Exception) as exc:
                        await parse_resume_endpoint(upload, _current_user(uid, email), db)
                    assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_persist_failure_logs_warning(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"hello world resume text here")
        try:
            async with _NullSessionLocal() as db:
                with patch("api.profile.parse_resume_from_file", AsyncMock(return_value=MOCK_PARSED_RESUME)), patch(
                    "api.profile.settings"
                ) as mock_settings, patch(
                    "api.profile._upsert_user_resume_asset",
                    AsyncMock(side_effect=RuntimeError("disk full")),
                ):
                    mock_settings.gemini_api_key = VALID_KEY
                    mock_settings.use_vertex_ai = False
                    resp = await parse_resume_endpoint(upload, _current_user(uid, email), db)
                assert resp.success is True
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_generic_exception(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"hello world resume text here")
        try:
            async with _NullSessionLocal() as db:
                with patch(
                    "api.profile.parse_resume_from_file",
                    AsyncMock(side_effect=RuntimeError("llm down")),
                ), patch("api.profile.settings") as mock_settings:
                    mock_settings.gemini_api_key = VALID_KEY
                    mock_settings.use_vertex_ai = False
                    with pytest.raises(Exception) as exc:
                        await parse_resume_endpoint(upload, _current_user(uid, email), db)
                    assert exc.value.status_code == 500
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_parse_resume_empty_content_direct(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"")
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await parse_resume_endpoint(upload, _current_user(uid, email), db)
                assert exc.value.status_code == 422
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_download_resume_invalid_and_missing_file(self) -> None:
        uid, email = await _create_user_with_password()
        try:
            async with _NullSessionLocal() as db:
                db.add(
                    UserResumeAsset(
                        id=uuid.uuid4(),
                        user_id=uid,
                        storage_relative_path=f"{uid}/bad.txt",
                        original_filename="bad.txt",
                        mime_type="text/plain",
                        byte_size=1,
                        sha256_hex="x",
                    )
                )
                await db.commit()
                with patch("api.profile.resume_absolute_path", side_effect=ValueError("bad path")):
                    with pytest.raises(Exception) as exc:
                        await download_stored_resume(_current_user(uid, email), db)
                    assert exc.value.status_code == 404
                from pathlib import Path

                with patch(
                    "api.profile.resume_absolute_path",
                    return_value=Path("/tmp/applypilot-missing-resume.bin"),
                ):
                    with pytest.raises(Exception) as exc2:
                        await download_stored_resume(_current_user(uid, email), db)
                    assert exc2.value.status_code == 404
        finally:
            await _delete_user_data(uid)

    @pytest.mark.asyncio
    async def test_get_preferences_http_exception_reraise(self) -> None:
        async with _NullSessionLocal() as db:
            with pytest.raises(APIError):
                await get_application_preferences({}, db)

    @pytest.mark.asyncio
    async def test_get_preferences_internal_error(self) -> None:
        uid = uuid.uuid4()
        async with _NullSessionLocal() as db:
            with patch.object(db, "execute", AsyncMock(side_effect=RuntimeError("db"))):
                with pytest.raises(Exception) as exc:
                    await get_application_preferences(_current_user(uid, "x@example.com"), db)
            assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_parse_resume_oversized_direct(self) -> None:
        uid, email = await _create_user_with_password()
        upload = MagicMock()
        upload.filename = "resume.txt"
        upload.read = AsyncMock(return_value=b"x" * (11 * 1024 * 1024))
        try:
            async with _NullSessionLocal() as db:
                with pytest.raises(Exception) as exc:
                    await parse_resume_endpoint(upload, _current_user(uid, email), db)
                assert exc.value.status_code == 413
        finally:
            await _delete_user_data(uid)

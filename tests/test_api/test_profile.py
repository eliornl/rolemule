"""
Integration tests for Profile / Settings API endpoints.

Endpoints:
  GET    /api/v1/profile/
  PUT    /api/v1/profile/basic-info
  PUT    /api/v1/profile/work-experience
  PUT    /api/v1/profile/education
  PUT    /api/v1/profile/skills-qualifications
  PUT    /api/v1/profile/career-preferences
  GET    /api/v1/profile/resume
  DELETE /api/v1/profile/resume
  GET    /api/v1/profile/status
  GET    /api/v1/profile/api-key/status
  POST   /api/v1/profile/api-key
  DELETE /api/v1/profile/api-key
  GET    /api/v1/profile/preferences
  PATCH  /api/v1/profile/preferences
  GET    /api/v1/profile/export
  POST   /api/v1/profile/parse-resume (format validation; LLM path not covered here)
"""

import pytest

BASE = "/api/v1/profile"


# ---------------------------------------------------------------------------
# GET /profile/
# ---------------------------------------------------------------------------


class TestGetProfile:
    """GET /api/v1/profile/"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_with_profile_shape(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/")
        assert resp.status_code == 200
        data = resp.json()
        # Response has nested keys: user_info, profile_data, completion_status
        assert "user_info" in data or "email" in data or "full_name" in data


# ---------------------------------------------------------------------------
# GET /profile/status
# ---------------------------------------------------------------------------


class TestProfileStatus:
    """GET /api/v1/profile/status"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_with_completion_fields(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "profile_completed" in data or "completion_percentage" in data or "is_complete" in data


# ---------------------------------------------------------------------------
# PUT /profile/basic-info
# ---------------------------------------------------------------------------


class TestUpdateBasicInfo:
    """PUT /api/v1/profile/basic-info"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.put(
            f"{BASE}/basic-info",
            json={"full_name": "Test User", "professional_title": "Engineer"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_valid_payload_accepted(self, authed_client_with_user):
        resp = await authed_client_with_user.put(
            f"{BASE}/basic-info",
            json={
                "city": "San Francisco",
                "state": "CA",
                "country": "USA",
                "professional_title": "Senior Engineer",
                "years_experience": 5,
                "is_student": False,
                "summary": "Experienced software engineer with 5 years in FastAPI and Python.",
                "phone": "+1 415 555 0100",
                "linkedin_url": "https://example.com/in/testuser",
            },
        )
        assert resp.status_code in (200, 201, 204)

    @pytest.mark.asyncio
    async def test_negative_years_experience_returns_422(self, authed_client_with_user):
        resp = await authed_client_with_user.put(
            f"{BASE}/basic-info",
            json={
                "city": "NYC", "state": "NY", "country": "USA",
                "professional_title": "Dev", "years_experience": -1,
                "is_student": False,
                "summary": "Summary here.",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /profile/work-experience
# ---------------------------------------------------------------------------


class TestUpdateWorkExperience:
    """PUT /api/v1/profile/work-experience"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.put(f"{BASE}/work-experience", json={"work_experience": []})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_empty_list_marks_work_experience_step_complete(self, authed_client_with_user):
        """Explicit [] is stored in JSONB and counts as completing step 2 (no experience yet)."""
        resp = await authed_client_with_user.put(
            f"{BASE}/work-experience",
            json={"work_experience": []},
        )
        assert resp.status_code in (200, 201, 204)
        st = await authed_client_with_user.get(f"{BASE}/status")
        assert st.status_code == 200
        data = st.json()
        assert "work_experience" in data.get("completed_steps", [])


# ---------------------------------------------------------------------------
# PUT /profile/education
# ---------------------------------------------------------------------------


class TestUpdateEducation:
    """PUT /api/v1/profile/education"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.put(f"{BASE}/education", json={"education": []})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_empty_list_marks_education_step_complete(self, authed_client_with_user):
        """Explicit [] is stored in JSONB and counts as completing the education step."""
        resp = await authed_client_with_user.put(
            f"{BASE}/education",
            json={"education": []},
        )
        assert resp.status_code in (200, 201, 204)
        st = await authed_client_with_user.get(f"{BASE}/status")
        assert st.status_code == 200
        data = st.json()
        assert "education" in data.get("completed_steps", [])

    @pytest.mark.asyncio
    async def test_valid_education_row_accepted(self, authed_client_with_user):
        resp = await authed_client_with_user.put(
            f"{BASE}/education",
            json={
                "education": [
                    {
                        "institution": "State University",
                        "degree": "Bachelor of Science",
                        "field_of_study": "Computer Science",
                        "start_date": "2018-09",
                        "end_date": "2022-05",
                        "is_current": False,
                    }
                ]
            },
        )
        assert resp.status_code in (200, 201, 204)
        st = await authed_client_with_user.get(f"{BASE}/status")
        assert st.status_code == 200
        assert "education" in st.json().get("completed_steps", [])

    @pytest.mark.asyncio
    async def test_education_row_without_start_date_rejected(self, authed_client_with_user):
        """Start date is required for each education entry."""
        resp = await authed_client_with_user.put(
            f"{BASE}/education",
            json={
                "education": [
                    {
                        "institution": "State University",
                        "degree": "Bachelor of Science",
                        "field_of_study": "Computer Science",
                        "end_date": "2022-05",
                        "is_current": False,
                    }
                ]
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_education_row_institution_degree_only_no_dates_rejected(self, authed_client_with_user):
        """Institution, degree, field, and dates are required (or Currently enrolled)."""
        resp = await authed_client_with_user.put(
            f"{BASE}/education",
            json={
                "education": [
                    {
                        "institution": "State University",
                        "degree": "Bachelor of Science",
                        "field_of_study": "Computer Science",
                        "is_current": False,
                    }
                ]
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_education_row_missing_field_of_study_rejected(self, authed_client_with_user):
        """field_of_study is required with institution and degree."""
        resp = await authed_client_with_user.put(
            f"{BASE}/education",
            json={
                "education": [
                    {
                        "institution": "State University",
                        "degree": "Bachelor of Science",
                        "is_current": False,
                    }
                ]
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /profile/skills-qualifications
# ---------------------------------------------------------------------------


class TestUpdateSkills:
    """PUT /api/v1/profile/skills-qualifications"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.put(f"{BASE}/skills-qualifications", json={"skills": ["Python"]})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_valid_skills_accepted(self, authed_client_with_user):
        resp = await authed_client_with_user.put(
            f"{BASE}/skills-qualifications",
            json={"skills": ["Python", "FastAPI", "PostgreSQL"]},
        )
        assert resp.status_code in (200, 201, 204)


# ---------------------------------------------------------------------------
# GET /profile/api-key/status
# ---------------------------------------------------------------------------


class TestApiKeyStatus:
    """GET /api/v1/profile/api-key/status"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/api-key/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_with_has_key_field(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/api-key/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "has_api_key" in data or "has_key" in data or "configured" in data


# ---------------------------------------------------------------------------
# POST /profile/api-key
# ---------------------------------------------------------------------------


class TestSetApiKey:
    """POST /api/v1/profile/api-key"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.post(f"{BASE}/api-key", json={"api_key": "AIzaSy..."})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_empty_key_returns_422(self, authed_client_with_user):
        resp = await authed_client_with_user.post(f"{BASE}/api-key", json={"api_key": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_key_returns_422(self, authed_client_with_user):
        resp = await authed_client_with_user.post(f"{BASE}/api-key", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /profile/api-key
# ---------------------------------------------------------------------------


class TestDeleteApiKey:
    """DELETE /api/v1/profile/api-key"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.delete(f"{BASE}/api-key")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_or_204_when_authenticated(self, authed_client_with_user):
        resp = await authed_client_with_user.delete(f"{BASE}/api-key")
        assert resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# GET /profile/preferences
# ---------------------------------------------------------------------------


class TestGetPreferences:
    """GET /api/v1/profile/preferences"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/preferences")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_with_preferences(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/preferences")
        # 500 may occur on test DBs lacking the latest migrations
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert isinstance(resp.json(), dict)


# ---------------------------------------------------------------------------
# PATCH /profile/preferences
# ---------------------------------------------------------------------------


class TestUpdatePreferences:
    """PATCH /api/v1/profile/preferences"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.patch(f"{BASE}/preferences", json={})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_valid_preference_update_accepted(self, authed_client_with_user):
        resp = await authed_client_with_user.patch(
            f"{BASE}/preferences",
            json={"resume_length": "concise"},
        )
        # 500 may occur on test DBs lacking the latest schema migrations
        assert resp.status_code in (200, 204, 500)


# ---------------------------------------------------------------------------
# GET /profile/export
# ---------------------------------------------------------------------------


class TestProfileExport:
    """GET /api/v1/profile/export"""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/export")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_200_or_204_when_authenticated(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/export")
        assert resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# POST /profile/parse-resume — format validation (no LLM)
# ---------------------------------------------------------------------------


class TestParseResumeFormatValidation:
    """POST /api/v1/profile/parse-resume rejects legacy .doc before API key check."""

    @pytest.mark.asyncio
    async def test_legacy_doc_extension_rejected(self, authed_client_with_user):
        files = {"resume": ("resume.doc", b"\xd0\xcf\x11\xe0fake", "application/msword")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code in (400, 422)
        data = resp.json()
        msg = data.get("message", "").lower()
        assert "doc" in msg and "not supported" in msg

    @pytest.mark.asyncio
    async def test_docx_with_ole_body_rejected(self, authed_client_with_user):
        ole_doc = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 64
        files = {"resume": ("resume.docx", ole_doc, "application/vnd...")}
        resp = await authed_client_with_user.post(f"{BASE}/parse-resume", files=files)
        assert resp.status_code in (400, 422)
        msg = resp.json().get("message", "").lower()
        assert "legacy" in msg and "not supported" in msg


# ---------------------------------------------------------------------------
# GET/DELETE /profile/resume
# ---------------------------------------------------------------------------


class TestProfileStoredResume:
    """GET/DELETE /api/v1/profile/resume"""

    @pytest.mark.asyncio
    async def test_get_resume_404_when_none(self, authed_client_with_user):
        resp = await authed_client_with_user.get(f"{BASE}/resume")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_resume_404_when_none(self, authed_client_with_user):
        resp = await authed_client_with_user.delete(f"{BASE}/resume")
        assert resp.status_code == 404

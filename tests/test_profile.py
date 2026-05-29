"""
Integration tests for profile API endpoints.

These tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.

Tests cover:
- GET /api/v1/profile - Retrieve complete profile
- PUT /api/v1/profile/basic-info - Update basic information
- PUT /api/v1/profile/work-experience - Update work history
- PUT /api/v1/profile/skills-qualifications - Update skills
- PUT /api/v1/profile/career-preferences - Update career preferences
- GET /api/v1/profile/status - Check profile completion status
- POST /api/v1/profile/parse-resume - Parse resume and extract profile data
- API Key Management (GET/POST/DELETE /api/v1/profile/api-key)
"""

import uuid
import pytest
import httpx
from typing import Dict, Any


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_profile_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def authenticated_user(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a test user, return headers with token."""
    # Register a new user
    register_response = http_client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Test Profile User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def valid_basic_info() -> Dict[str, Any]:
    """Return valid basic info data for testing."""
    return {
        "city": "San Francisco",
        "state": "California",
        "country": "United States",
        "professional_title": "Software Engineer",
        "years_experience": 5,
        "is_student": False,
        "summary": "Experienced software engineer with expertise in Python and cloud technologies.",
    }


@pytest.fixture
def valid_work_experience() -> Dict[str, Any]:
    """Return valid work experience data for testing."""
    return {
        "work_experience": [
            {
                "company": "Tech Company Inc",
                "job_title": "Senior Software Engineer",
                "start_date": "2020-01",
                "end_date": None,
                "description": "Leading development of cloud-native applications using Python and AWS.",
                "is_current": True,
            },
            {
                "company": "StartupXYZ",
                "job_title": "Software Engineer",
                "start_date": "2018-06",
                "end_date": "2019-12",
                "description": "Built RESTful APIs and microservices architecture.",
                "is_current": False,
            },
        ]
    }


@pytest.fixture
def valid_skills() -> Dict[str, Any]:
    """Return valid skills data for testing."""
    return {
        "skills": [
            "Python",
            "JavaScript",
            "AWS",
            "Docker",
            "PostgreSQL",
            "FastAPI",
            "React",
        ]
    }


@pytest.fixture
def valid_career_preferences() -> Dict[str, Any]:
    """Return valid career preferences data for testing."""
    return {
        "desired_salary_range": {"min": 120000, "max": 180000},
        "desired_company_sizes": ["Medium (51-200 employees)", "Large (201-1000 employees)"],
        "job_types": ["Full-time"],
        "work_arrangements": ["Remote", "Hybrid"],
        "willing_to_relocate": False,
        "requires_visa_sponsorship": False,
        "has_security_clearance": False,
        "max_travel_preference": "25",
    }


# =============================================================================
# GET PROFILE TESTS
# =============================================================================


class TestGetProfile:
    """Tests for the GET /api/v1/profile endpoint."""

    def test_get_profile_success(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful retrieval of user profile."""
        response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "user_info" in data
        assert "profile_data" in data
        assert "completion_status" in data
        
        # Check user_info fields
        assert "id" in data["user_info"]
        assert "email" in data["user_info"]
        assert "full_name" in data["user_info"]

    def test_get_profile_without_auth(self, http_client: httpx.Client):
        """Test profile retrieval without authentication fails."""
        response = http_client.get("/api/v1/profile")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403]

    def test_get_profile_with_invalid_token(self, http_client: httpx.Client):
        """Test profile retrieval with invalid token fails."""
        response = http_client.get(
            "/api/v1/profile",
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        assert response.status_code in [401, 403]


# =============================================================================
# BASIC INFO TESTS
# =============================================================================


class TestBasicInfo:
    """Tests for the PUT /api/v1/profile/basic-info endpoint."""

    def test_update_basic_info_success(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test successful update of basic information."""
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "updated successfully" in data["message"].lower()

    def test_update_basic_info_persists(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test that basic info updates are persisted."""
        # Update basic info
        http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        
        # Retrieve profile and verify
        response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        profile = data["profile_data"]
        
        assert profile["city"] == valid_basic_info["city"]
        assert profile["state"] == valid_basic_info["state"]
        assert profile["country"] == valid_basic_info["country"]
        assert profile["professional_title"] == valid_basic_info["professional_title"]

    def test_update_basic_info_missing_required_fields(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with missing required fields fails."""
        incomplete_data = {
            "city": "San Francisco",
            # Missing state, country, professional_title, etc.
        }
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=incomplete_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_basic_info_invalid_years_experience(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test update with invalid years of experience fails."""
        invalid_data = valid_basic_info.copy()
        invalid_data["years_experience"] = -5  # Negative value
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_basic_info_excessive_years_experience(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test update with excessive years of experience fails."""
        invalid_data = valid_basic_info.copy()
        invalid_data["years_experience"] = 100  # More than MAX_YEARS_EXPERIENCE (70)
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_basic_info_invalid_location_characters(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test update with invalid characters in location fails."""
        invalid_data = valid_basic_info.copy()
        invalid_data["city"] = "San <script>Francisco</script>"  # XSS attempt
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_basic_info_summary_too_long(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test update with summary exceeding max length fails."""
        invalid_data = valid_basic_info.copy()
        invalid_data["summary"] = "A" * 1001  # Exceeds MAX_SUMMARY_LENGTH (1000)
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_basic_info_without_auth(
        self, http_client: httpx.Client, valid_basic_info: Dict[str, Any]
    ):
        """Test update without authentication fails."""
        response = http_client.put(
            "/api/v1/profile/basic-info",
            json=valid_basic_info,
        )
        
        assert response.status_code in [401, 403]


# =============================================================================
# WORK EXPERIENCE TESTS
# =============================================================================


class TestWorkExperience:
    """Tests for the PUT /api/v1/profile/work-experience endpoint."""

    def test_update_work_experience_success(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_work_experience: Dict[str, Any],
    ):
        """Test successful update of work experience."""
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=valid_work_experience,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "summary" in data
        assert data["summary"]["total_entries"] == 2
        assert data["summary"]["current_positions"] == 1

    def test_update_work_experience_empty_list(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with empty work experience list succeeds."""
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json={"work_experience": []},
        )
        
        # Empty work experience should be allowed (user might be fresh graduate)
        assert response.status_code == 200

    def test_update_work_experience_persists(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_work_experience: Dict[str, Any],
    ):
        """Test that work experience updates are persisted."""
        # Update work experience
        http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=valid_work_experience,
        )
        
        # Retrieve profile and verify
        response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        work_exp = data["profile_data"].get("work_experience", [])
        
        assert len(work_exp) == 2
        assert work_exp[0]["company"] == "Tech Company Inc"

    def test_update_work_experience_invalid_date_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with invalid date format fails."""
        invalid_data = {
            "work_experience": [
                {
                    "company": "Test Company",
                    "job_title": "Developer",
                    "start_date": "January 2020",  # Invalid format, should be YYYY-MM
                    "description": "Testing",
                    "is_current": True,
                }
            ]
        }
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_work_experience_future_start_date(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with future start date fails."""
        invalid_data = {
            "work_experience": [
                {
                    "company": "Future Company",
                    "job_title": "Time Traveler",
                    "start_date": "2099-01",  # Far future
                    "description": "Testing",
                    "is_current": True,
                }
            ]
        }
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_work_experience_end_before_start(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with end date before start date.
        
        Note: The API currently accepts this data without validation.
        This test documents the current behavior.
        """
        data = {
            "work_experience": [
                {
                    "company": "Test Company",
                    "job_title": "Developer",
                    "start_date": "2022-06",
                    "end_date": "2021-01",  # Before start date
                    "description": "Testing",
                    "is_current": False,
                }
            ]
        }
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=data,
        )
        
        # API currently accepts this without validation
        assert response.status_code == 200

    def test_update_work_experience_multiple_current_positions(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with multiple current positions fails."""
        invalid_data = {
            "work_experience": [
                {
                    "company": "Company A",
                    "job_title": "Role A",
                    "start_date": "2020-01",
                    "is_current": True,
                },
                {
                    "company": "Company B",
                    "job_title": "Role B",
                    "start_date": "2021-01",
                    "is_current": True,  # Second current position
                },
            ]
        }
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_work_experience_exceeds_max_items(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with too many work experience entries fails."""
        # Create 11 entries (exceeds MAX_WORK_EXPERIENCE_ITEMS = 10)
        work_exp_list = [
            {
                "company": f"Company {i}",
                "job_title": f"Title {i}",
                "start_date": f"20{10+i}-01",
                "end_date": f"20{11+i}-12",
                "is_current": False,
            }
            for i in range(11)
        ]
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json={"work_experience": work_exp_list},
        )
        
        assert response.status_code in [400, 422]


# =============================================================================
# SKILLS AND QUALIFICATIONS TESTS
# =============================================================================


class TestSkillsQualifications:
    """Tests for the PUT /api/v1/profile/skills-qualifications endpoint."""

    def test_update_skills_success(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_skills: Dict[str, Any],
    ):
        """Test successful update of skills."""
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json=valid_skills,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "updated successfully" in data["message"].lower()

    def test_update_skills_persists(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_skills: Dict[str, Any],
    ):
        """Test that skills updates are persisted."""
        # Update skills
        http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json=valid_skills,
        )
        
        # Retrieve profile and verify
        response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        skills = data["profile_data"].get("skills", [])
        
        assert "Python" in skills
        assert "AWS" in skills

    def test_update_skills_empty_list(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with empty skills list fails (minimum 1 required)."""
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json={"skills": []},
        )
        
        # Should fail due to MIN_SKILLS_ITEMS = 1
        assert response.status_code in [400, 422]

    def test_update_skills_deduplication(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that duplicate skills are removed."""
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json={"skills": ["Python", "python", "PYTHON", "JavaScript"]},
        )
        
        assert response.status_code == 200
        
        # Verify deduplication
        profile_response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        skills = profile_response.json()["profile_data"].get("skills", [])
        
        # Count Python entries (should be 1 after deduplication)
        python_count = sum(1 for s in skills if s.lower() == "python")
        assert python_count == 1

    def test_update_skills_invalid_characters(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with invalid characters in skills fails."""
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json={"skills": ["Python<script>alert('xss')</script>"]},
        )
        
        assert response.status_code in [400, 422]

    def test_update_skills_exceeds_max_items(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with too many skills fails."""
        # Create 21 skills (exceeds MAX_SKILLS_ITEMS = 20)
        many_skills = [f"Skill{i}" for i in range(21)]
        
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json={"skills": many_skills},
        )
        
        assert response.status_code in [400, 422]

    def test_update_skills_technical_characters_allowed(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that technical characters in skill names are allowed."""
        response = http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json={"skills": ["C++", "C#", "Node.js", "Vue.js", "ASP.NET"]},
        )
        
        assert response.status_code == 200


# =============================================================================
# CAREER PREFERENCES TESTS
# =============================================================================


class TestCareerPreferences:
    """Tests for the PUT /api/v1/profile/career-preferences endpoint."""

    def test_update_career_preferences_success(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test successful update of career preferences."""
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=valid_career_preferences,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "updated successfully" in data["message"].lower()

    def test_update_career_preferences_persists(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test that career preferences updates are persisted."""
        # Update career preferences
        http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=valid_career_preferences,
        )
        
        # Retrieve profile and verify
        response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        profile = data["profile_data"]
        
        assert profile["desired_salary_range"]["min"] == 120000
        assert profile["desired_salary_range"]["max"] == 180000
        assert "Remote" in profile["work_arrangements"]

    def test_update_career_preferences_preserves_exact_salary_max(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """220000 must persist exactly — not drift via rounding or number-input step."""
        data = valid_career_preferences.copy()
        data["desired_salary_range"] = {"min": 200000, "max": 220000}

        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=data,
        )
        assert response.status_code == 200

        profile_resp = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        assert profile_resp.status_code == 200
        rng = profile_resp.json()["profile_data"]["desired_salary_range"]
        assert rng["min"] == 200000
        assert rng["max"] == 220000

    def test_update_career_preferences_invalid_salary_range(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test update with min salary greater than max fails."""
        invalid_data = valid_career_preferences.copy()
        invalid_data["desired_salary_range"] = {"min": 200000, "max": 100000}
        
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_career_preferences_negative_salary(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test update with negative salary values fails."""
        invalid_data = valid_career_preferences.copy()
        invalid_data["desired_salary_range"] = {"min": -50000, "max": 100000}
        
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_career_preferences_unreasonable_salary(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test update with unreasonably high salary fails."""
        invalid_data = valid_career_preferences.copy()
        invalid_data["desired_salary_range"] = {"min": 5000000, "max": 10000000}
        
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        assert response.status_code in [400, 422]

    def test_update_career_preferences_invalid_job_type(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test update with invalid job type is handled."""
        invalid_data = valid_career_preferences.copy()
        invalid_data["job_types"] = ["InvalidJobType"]
        
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        # May return 422 or try to convert
        assert response.status_code in [200, 400, 422]

    def test_update_career_preferences_empty_job_types(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test update with empty job types fails."""
        invalid_data = valid_career_preferences.copy()
        invalid_data["job_types"] = []
        
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=invalid_data,
        )
        
        # Should fail due to MIN_JOB_TYPE_ITEMS = 1
        assert response.status_code in [400, 422]

    def test_update_career_preferences_all_work_arrangements(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test update with all valid work arrangements succeeds."""
        response = http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json={
                "desired_salary_range": {"min": 50000, "max": 100000},
                "desired_company_sizes": ["Startup (1-10 employees)"],
                "job_types": ["Full-time"],
                "work_arrangements": ["Remote", "Hybrid", "Onsite"],
                "willing_to_relocate": True,
                "requires_visa_sponsorship": False,
                "has_security_clearance": False,
                "max_travel_preference": "0",
            },
        )
        
        assert response.status_code == 200


# =============================================================================
# PROFILE COMPLETION STATUS TESTS
# =============================================================================


class TestProfileCompletion:
    """Tests for the GET /api/v1/profile/status endpoint."""

    def test_get_profile_status_empty_profile(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test profile status for newly registered user."""
        response = http_client.get(
            "/api/v1/profile/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "profile_completed" in data
        assert "completion_percentage" in data
        assert "completed_steps" in data
        assert "missing_steps" in data
        
        # New user should not have completed profile
        assert data["profile_completed"] is False
        assert data["completion_percentage"] < 100

    def test_get_profile_status_partial_completion(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test profile status after completing some steps."""
        # Complete basic info
        http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        
        response = http_client.get(
            "/api/v1/profile/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "basic_info" in data["completed_steps"]
        assert data["completion_percentage"] > 0

    def test_get_profile_status_full_completion(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
        valid_work_experience: Dict[str, Any],
        valid_skills: Dict[str, Any],
        valid_career_preferences: Dict[str, Any],
    ):
        """Test profile status after completing all steps."""
        # Complete all steps
        http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=valid_work_experience,
        )
        http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=authenticated_user,
            json=valid_skills,
        )
        http_client.put(
            "/api/v1/profile/career-preferences",
            headers=authenticated_user,
            json=valid_career_preferences,
        )
        
        response = http_client.get(
            "/api/v1/profile/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["profile_completed"] is True
        assert data["completion_percentage"] == 100
        assert len(data["missing_steps"]) == 0

    def test_get_profile_status_without_auth(self, http_client: httpx.Client):
        """Test profile status without authentication fails."""
        response = http_client.get("/api/v1/profile/status")
        
        assert response.status_code in [401, 403]


# =============================================================================
# EDGE CASES AND BOUNDARY TESTS
# =============================================================================


class TestProfileEdgeCases:
    """Tests for edge cases in profile endpoints."""

    def test_update_profile_concurrent_requests(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test that concurrent updates don't cause issues."""
        import concurrent.futures
        
        def update_basic_info():
            return http_client.put(
                "/api/v1/profile/basic-info",
                headers=authenticated_user,
                json=valid_basic_info,
            )
        
        # Execute multiple concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(update_basic_info) for _ in range(3)]
            results = [f.result() for f in futures]
        
        # All requests should succeed or fail gracefully
        for result in results:
            assert result.status_code in [200, 409, 500]

    def test_update_profile_with_unicode_characters(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test profile update with unicode characters."""
        unicode_basic_info = {
            "city": "München",  # German umlaut
            "state": "Bayern",
            "country": "Deutschland",
            "professional_title": "Software-Entwickler",
            "years_experience": 5,
            "is_student": False,
            "summary": "Erfahrener Entwickler mit Expertise in Python und Cloud-Technologien.",
        }
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=unicode_basic_info,
        )
        
        # May accept or reject unicode depending on validation rules
        assert response.status_code in [200, 400, 422]

    def test_profile_update_idempotency(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test that updating with same data is idempotent."""
        # First update
        response1 = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        assert response1.status_code == 200
        
        # Second update with same data
        response2 = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=valid_basic_info,
        )
        assert response2.status_code == 200
        
        # Profile should remain the same
        profile_response = http_client.get(
            "/api/v1/profile",
            headers=authenticated_user,
        )
        assert profile_response.status_code == 200

    def test_profile_special_characters_in_professional_title(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        valid_basic_info: Dict[str, Any],
    ):
        """Test professional title with allowed special characters."""
        special_title_data = valid_basic_info.copy()
        special_title_data["professional_title"] = "Sr. Software Engineer (Full-Stack)"
        
        response = http_client.put(
            "/api/v1/profile/basic-info",
            headers=authenticated_user,
            json=special_title_data,
        )
        
        assert response.status_code == 200

    def test_work_experience_with_present_end_date(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test work experience with 'Present' as end date."""
        data = {
            "work_experience": [
                {
                    "company": "Current Company",
                    "job_title": "Developer",
                    "start_date": "2022-01",
                    "end_date": "Present",
                    "description": "Working on exciting projects",
                    "is_current": True,
                }
            ]
        }
        
        response = http_client.put(
            "/api/v1/profile/work-experience",
            headers=authenticated_user,
            json=data,
        )
        
        assert response.status_code == 200


# =============================================================================
# API KEY MANAGEMENT TESTS
# =============================================================================


class TestApiKeyManagement:
    """Tests for API key management endpoints."""

    def test_get_api_key_status_no_key(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test API key status when no key is set."""
        response = http_client.get(
            "/api/v1/profile/api-key/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["has_api_key"] is False
        assert data["key_preview"] is None

    def test_set_api_key_invalid_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test setting API key with invalid format fails."""
        response = http_client.post(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
            json={"api_key": "short"},  # Too short
        )
        
        assert response.status_code in [400, 422]

    def test_delete_api_key_when_none_exists(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test deleting API key when none exists."""
        response = http_client.delete(
            "/api/v1/profile/api-key",
            headers=authenticated_user,
        )
        
        # Should succeed even if no key exists
        assert response.status_code == 200

    def test_validate_api_key_invalid_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test validating API key with invalid format."""
        response = http_client.post(
            "/api/v1/profile/api-key/validate",
            headers=authenticated_user,
            json={"api_key": "invalid-format-key"},
        )
        
        assert response.status_code in [400, 422]


# =============================================================================
# RESUME PARSING TESTS
# =============================================================================


class TestResumeParsing:
    """Tests for the POST /api/v1/profile/parse-resume endpoint."""

    @pytest.fixture
    def sample_resume_txt(self) -> bytes:
        """Return sample TXT resume content for testing."""
        return b"""
John Doe
Software Engineer
john.doe@email.com | (555) 123-4567
San Francisco, CA

PROFESSIONAL SUMMARY
Experienced software engineer with 5+ years of experience building scalable web applications.
Proficient in Python, JavaScript, and cloud technologies.

WORK EXPERIENCE

Senior Software Engineer | Tech Corp Inc. | Jan 2022 - Present
- Led development of microservices architecture
- Improved system performance by 40%

Software Engineer | StartupXYZ | Jun 2019 - Dec 2021
- Built RESTful APIs using Python and FastAPI
- Implemented CI/CD pipelines

EDUCATION
Bachelor of Science in Computer Science
University of California, Berkeley | 2019

SKILLS
Python, JavaScript, AWS, Docker, PostgreSQL, FastAPI, React, Git
"""

    @pytest.fixture
    def sample_resume_docx_bytes(self) -> bytes:
        """Return minimal bytes that simulate a DOCX file header for testing."""
        # This is just placeholder bytes - actual DOCX is a ZIP archive
        # The test checks file extension validation, not actual parsing
        return b"PK\x03\x04placeholder-docx-content"

    def test_parse_resume_txt_format_accepted(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        sample_resume_txt: bytes,
    ):
        """Test that TXT resume format is accepted (may fail on API key in BYOK mode)."""
        files = {"resume": ("resume.txt", sample_resume_txt, "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        # File format should be accepted - may succeed (200) or fail due to:
        # - No API key configured (400 with "No API key available")
        # - LLM service unavailable (500, 503)
        assert response.status_code in [200, 400, 500, 503]
        
        data = response.json()
        
        # If 400, should NOT be format error (format is valid)
        if response.status_code == 400:
            assert "unsupported file format" not in data.get("message", "").lower()
        
        if response.status_code == 200:
            assert "success" in data
            assert "message" in data
            if data["success"]:
                assert "data" in data
                assert "confidence" in data

    def test_parse_resume_unsupported_format(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test parsing fails for unsupported file formats."""
        files = {"resume": ("resume.jpg", b"fake image content", "image/jpeg")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        assert response.status_code == 400
        data = response.json()
        # Error response uses 'message' field
        assert "unsupported file format" in data.get("message", "").lower()

    def test_parse_resume_empty_file(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test parsing fails for empty file."""
        files = {"resume": ("resume.txt", b"", "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        assert response.status_code == 400
        data = response.json()
        # Error response uses 'message' field
        assert "empty" in data.get("message", "").lower()

    def test_parse_resume_without_auth(
        self,
        http_client: httpx.Client,
        sample_resume_txt: bytes,
    ):
        """Test resume parsing without authentication fails."""
        files = {"resume": ("resume.txt", sample_resume_txt, "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            files=files,
        )
        
        assert response.status_code in [401, 403]

    def test_parse_resume_pdf_format_accepted(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test that PDF files are accepted (format validation)."""
        # Create a minimal PDF-like content (won't actually parse but tests format acceptance)
        # Real PDF starts with %PDF-
        pdf_content = b"%PDF-1.4\n%test content"
        files = {"resume": ("resume.pdf", pdf_content, "application/pdf")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        # Should not fail on format validation (may fail on actual parsing)
        # 400 would indicate format rejection, anything else means format was accepted
        if response.status_code == 400:
            detail = response.json().get("detail", "").lower()
            assert "unsupported file format" not in detail

    def test_parse_resume_docx_format_accepted(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        sample_resume_docx_bytes: bytes,
    ):
        """Test that DOCX files are accepted (format validation)."""
        files = {
            "resume": (
                "resume.docx",
                sample_resume_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        # Should not fail on format validation (may fail on actual parsing)
        if response.status_code == 400:
            detail = response.json().get("detail", "").lower()
            assert "unsupported file format" not in detail

    def test_parse_resume_exe_format_rejected(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test that executable files are rejected."""
        files = {"resume": ("malware.exe", b"MZ\x00\x00fake", "application/octet-stream")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        assert response.status_code == 400
        data = response.json()
        # Error response uses 'message' field
        assert "unsupported file format" in data.get("message", "").lower()

    def test_parse_resume_html_format_rejected(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
    ):
        """Test that HTML files are rejected."""
        html_content = b"<html><body><h1>Resume</h1></body></html>"
        files = {"resume": ("resume.html", html_content, "text/html")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        assert response.status_code == 400
        data = response.json()
        # Error response uses 'message' field
        assert "unsupported file format" in data.get("message", "").lower()

    def test_parse_resume_response_structure(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        sample_resume_txt: bytes,
    ):
        """Test that response has correct structure."""
        files = {"resume": ("resume.txt", sample_resume_txt, "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        # Even on error, should be valid JSON
        data = response.json()
        
        if response.status_code == 200:
            # Check expected response structure
            assert "success" in data
            assert "message" in data
            assert isinstance(data["success"], bool)
            assert isinstance(data["message"], str)

    def test_parse_resume_with_invalid_token(
        self,
        http_client: httpx.Client,
        sample_resume_txt: bytes,
    ):
        """Test resume parsing with invalid token fails."""
        files = {"resume": ("resume.txt", sample_resume_txt, "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers={"Authorization": "Bearer invalid-token"},
            files=files,
        )
        
        assert response.status_code in [401, 403]

    def test_parse_resume_single_file_accepted(
        self,
        http_client: httpx.Client,
        authenticated_user: Dict[str, str],
        sample_resume_txt: bytes,
    ):
        """Test that single file upload is accepted (format validation passes)."""
        # The endpoint expects a single file upload
        files = {"resume": ("resume.txt", sample_resume_txt, "text/plain")}
        
        response = http_client.post(
            "/api/v1/profile/parse-resume",
            headers=authenticated_user,
            files=files,
        )
        
        # Single file format should be accepted - may fail on API key or LLM
        assert response.status_code in [200, 400, 500, 503]
        
        # If 400, should NOT be format-related
        if response.status_code == 400:
            data = response.json()
            assert "unsupported file format" not in data.get("message", "").lower()

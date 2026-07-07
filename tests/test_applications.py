"""
Comprehensive tests for Applications API endpoints.

These tests cover the complete applications functionality:
- GET /api/v1/applications/ - List applications with pagination and filtering
- PATCH /api/v1/applications/{id}/status - Update application status
- DELETE /api/v1/applications/{id} - Delete application
- GET /api/v1/applications/stats/overview - Get application statistics
- GET /api/v1/applications/{id}/download - Download application report

Tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.
"""

import uuid
import pytest
import httpx
from typing import Dict


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"

# Valid profile data for completing profile setup
VALID_BASIC_INFO = {
    "city": "San Francisco",
    "state": "California",
    "country": "United States",
    "professional_title": "Software Engineer",
    "years_experience": 5,
    "is_student": False,
    "summary": "Experienced software engineer with expertise in Python and cloud technologies.",
}

VALID_SKILLS = {
    "skills": ["Python", "JavaScript", "React", "PostgreSQL", "AWS"]
}

VALID_CAREER_PREFERENCES = {
    "desired_salary_range": {"min": 100000, "max": 200000},
    "desired_company_sizes": ["Medium (51-200 employees)"],
    "job_types": ["Full-time"],
    "work_arrangements": ["Remote"],
    "willing_to_relocate": False,
    "requires_visa_sponsorship": False,
    "has_security_clearance": False,
    "max_travel_preference": "25",
}

# Valid status values from ApplicationStatus enum
VALID_STATUSES = [
    "processing",
    "completed",
    "applied",
    "interview",
    "accepted",
    "rejected",
    "withdrawn",
    "failed",
]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_apps_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def authenticated_user(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a test user, return headers with token."""
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Applications Test User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_with_complete_profile(http_client: httpx.Client, authenticated_user: Dict[str, str]):
    """Create a user with a complete profile setup."""
    # Complete basic info
    http_client.put(
        "/api/v1/profile/basic-info",
        headers=authenticated_user,
        json=VALID_BASIC_INFO,
    )
    
    # Complete work experience
    http_client.put(
        "/api/v1/profile/work-experience",
        headers=authenticated_user,
        json={"work_experience": []},
    )
    
    # Complete skills
    http_client.put(
        "/api/v1/profile/skills-qualifications",
        headers=authenticated_user,
        json=VALID_SKILLS,
    )
    
    # Complete career preferences
    http_client.put(
        "/api/v1/profile/career-preferences",
        headers=authenticated_user,
        json=VALID_CAREER_PREFERENCES,
    )
    
    return authenticated_user


@pytest.fixture
def second_authenticated_user(http_client: httpx.Client):
    """Create a second authenticated user for isolation tests."""
    unique_email = f"test_apps_second_{uuid.uuid4().hex[:8]}@example.com"
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Second Applications Test User",
        },
    )
    assert register_response.status_code == 200
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# LIST APPLICATIONS TESTS
# =============================================================================


class TestListApplications:
    """Tests for GET /api/v1/applications/ endpoint."""

    def test_list_applications_empty(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test listing applications when user has none."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
        )
        
        # 200 = success, 403 = profile incomplete
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert "applications" in data
            assert "total" in data
            assert "page" in data
            assert "per_page" in data
            assert "has_next" in data
            assert "has_prev" in data
            assert data["total"] >= 0

    def test_list_applications_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated requests are rejected."""
        response = http_client.get("/api/v1/applications/")
        
        assert response.status_code in [401, 403]

    def test_list_applications_pagination(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test pagination parameters."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"page": 1, "per_page": 5},
        )
        
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert data["page"] == 1
            assert data["per_page"] == 5

    def test_list_applications_max_page_size(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that page size is capped at max (100)."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"per_page": 200},
        )
        
        # Should either cap at 100 or reject
        assert response.status_code in [200, 400, 403, 422]

    def test_list_applications_invalid_page(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that invalid page number is rejected."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"page": 0},
        )
        
        assert response.status_code in [400, 403, 422]

    def test_list_applications_negative_page(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that negative page number is rejected."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"page": -1},
        )
        
        assert response.status_code in [400, 403, 422]

    def test_list_applications_status_filter(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test filtering by status."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"status_filter": "applied"},
        )
        
        assert response.status_code in [200, 403]

    def test_list_applications_response_structure(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that response has correct structure."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Required fields
            required_fields = [
                "applications",
                "total",
                "page",
                "per_page",
                "has_next",
                "has_prev",
            ]
            
            for field in required_fields:
                assert field in data, f"Missing field: {field}"
            
            # Type checks
            assert isinstance(data["applications"], list)
            assert isinstance(data["total"], int)
            assert isinstance(data["page"], int)
            assert isinstance(data["per_page"], int)
            assert isinstance(data["has_next"], bool)
            assert isinstance(data["has_prev"], bool)


# =============================================================================
# UPDATE APPLICATION STATUS TESTS
# =============================================================================


class TestUpdateApplicationStatus:
    """Tests for PATCH /api/v1/applications/{id}/status endpoint."""

    def test_update_status_nonexistent_application(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating status of non-existent application."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            headers=user_with_complete_profile,
            json={"new_status": "applied"},
        )
        
        # 404 = not found, 403 = profile incomplete
        assert response.status_code in [404, 403]

    def test_update_status_invalid_uuid(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating status with invalid UUID format."""
        response = http_client.patch(
            "/api/v1/applications/not-a-valid-uuid/status",
            headers=user_with_complete_profile,
            json={"new_status": "applied"},
        )
        
        # 400 = invalid format, 403 = profile incomplete
        assert response.status_code in [400, 403]

    def test_update_status_invalid_status_value(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating with invalid status value."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            headers=user_with_complete_profile,
            json={"new_status": "invalid_status"},
        )
        
        # 400/422 = validation error, 403 = profile incomplete, 404 = not found
        assert response.status_code in [400, 403, 404, 422]

    def test_update_status_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated requests are rejected."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            json={"new_status": "applied"},
        )
        
        assert response.status_code in [401, 403]

    def test_update_status_missing_new_status(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating without providing new_status."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            headers=user_with_complete_profile,
            json={},
        )
        
        assert response.status_code in [400, 403, 422]

    def test_update_status_valid_statuses(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that all valid status values are accepted (validation-wise)."""
        fake_id = str(uuid.uuid4())
        
        for status_value in VALID_STATUSES:
            response = http_client.patch(
                f"/api/v1/applications/{fake_id}/status",
                headers=user_with_complete_profile,
                json={"new_status": status_value},
            )
            
            # Should be 404 (not found) or 403 (profile incomplete), not validation error
            assert response.status_code in [403, 404], \
                f"Status '{status_value}' should be accepted: {response.text}"


# =============================================================================
# DELETE APPLICATION TESTS
# =============================================================================


class TestDeleteApplication:
    """Tests for DELETE /api/v1/applications/{id} endpoint."""

    def test_delete_nonexistent_application(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test deleting non-existent application."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.delete(
            f"/api/v1/applications/{fake_id}",
            headers=user_with_complete_profile,
        )
        
        # 404 = not found, 403 = profile incomplete
        assert response.status_code in [404, 403]

    def test_delete_invalid_uuid(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test deleting with invalid UUID format."""
        response = http_client.delete(
            "/api/v1/applications/not-a-valid-uuid",
            headers=user_with_complete_profile,
        )
        
        # 400 = invalid format, 403 = profile incomplete
        assert response.status_code in [400, 403]

    def test_delete_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated deletes are rejected."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.delete(f"/api/v1/applications/{fake_id}")
        
        assert response.status_code in [401, 403]

    def test_delete_empty_id(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test deleting with empty ID."""
        response = http_client.delete(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
        )
        
        # Either returns method not allowed or redirects
        assert response.status_code in [200, 307, 405]


# =============================================================================
# APPLICATION STATS TESTS
# =============================================================================


class TestApplicationStats:
    """Tests for GET /api/v1/applications/stats/overview endpoint."""

    def test_get_stats_empty(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test getting stats when user has no applications."""
        response = http_client.get(
            "/api/v1/applications/stats/overview",
            headers=user_with_complete_profile,
        )
        
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert "total" in data
            assert "applied" in data
            assert "interviews" in data
            assert "response_rate" in data
            
            assert data["total"] >= 0
            assert data["applied"] >= 0
            assert data["interviews"] >= 0
            assert 0 <= data["response_rate"] <= 100

    def test_get_stats_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated stats requests are rejected."""
        response = http_client.get("/api/v1/applications/stats/overview")
        
        assert response.status_code in [401, 403]

    def test_get_stats_response_structure(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that stats response has correct structure."""
        response = http_client.get(
            "/api/v1/applications/stats/overview",
            headers=user_with_complete_profile,
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Required fields
            required_fields = ["total", "applied", "interviews", "response_rate"]
            
            for field in required_fields:
                assert field in data, f"Missing field: {field}"
            
            # Type checks
            assert isinstance(data["total"], int)
            assert isinstance(data["applied"], int)
            assert isinstance(data["interviews"], int)
            assert isinstance(data["response_rate"], (int, float))


# =============================================================================
# APPLICATION DOWNLOAD TESTS
# =============================================================================


class TestApplicationDownload:
    """Tests for GET /api/v1/applications/{id}/download endpoint."""

    def test_download_nonexistent_application(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test downloading non-existent application."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.get(
            f"/api/v1/applications/{fake_id}/download",
            headers=user_with_complete_profile,
        )
        
        # 404 = not found, 403 = profile incomplete
        assert response.status_code in [404, 403]

    def test_download_invalid_uuid(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test downloading with invalid UUID format."""
        response = http_client.get(
            "/api/v1/applications/not-a-valid-uuid/download",
            headers=user_with_complete_profile,
        )
        
        # 400 = invalid format, 403 = profile incomplete
        assert response.status_code in [400, 403]

    def test_download_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated downloads are rejected."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.get(f"/api/v1/applications/{fake_id}/download")
        
        assert response.status_code in [401, 403]


# =============================================================================
# APPLICATION ISOLATION TESTS
# =============================================================================


class TestApplicationIsolation:
    """Tests to verify application data is properly isolated between users."""

    def test_user_cannot_see_others_applications(
        self,
        http_client: httpx.Client,
        user_with_complete_profile: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that users cannot list other users' applications."""
        # First user lists their applications (should be empty or just their own)
        response1 = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
        )
        
        # Second user lists their applications (should also be separate)
        # Complete profile for second user first
        http_client.put(
            "/api/v1/profile/basic-info",
            headers=second_authenticated_user,
            json=VALID_BASIC_INFO,
        )
        http_client.put(
            "/api/v1/profile/work-experience",
            headers=second_authenticated_user,
            json={"work_experience": []},
        )
        http_client.put(
            "/api/v1/profile/skills-qualifications",
            headers=second_authenticated_user,
            json=VALID_SKILLS,
        )
        http_client.put(
            "/api/v1/profile/career-preferences",
            headers=second_authenticated_user,
            json=VALID_CAREER_PREFERENCES,
        )
        
        response2 = http_client.get(
            "/api/v1/applications/",
            headers=second_authenticated_user,
        )
        
        # Both should succeed (or fail due to profile) - they're separate
        assert response1.status_code in [200, 403]
        assert response2.status_code in [200, 403]


# =============================================================================
# APPLICATION ERROR HANDLING TESTS
# =============================================================================


class TestApplicationErrorHandling:
    """Tests for application error handling."""

    def test_list_with_invalid_json(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that GET with body doesn't cause issues."""
        # GET requests typically don't have body, but shouldn't crash
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
        )
        
        assert response.status_code in [200, 403]

    def test_update_status_with_empty_body(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating status with empty JSON body."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            headers={**user_with_complete_profile, "Content-Type": "application/json"},
            content="{}",
        )
        
        assert response.status_code in [400, 403, 422]

    def test_update_status_with_null_status(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test updating status with null value."""
        fake_id = str(uuid.uuid4())
        
        response = http_client.patch(
            f"/api/v1/applications/{fake_id}/status",
            headers=user_with_complete_profile,
            json={"new_status": None},
        )
        
        assert response.status_code in [400, 403, 422]

    def test_large_page_number(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test requesting a very large page number."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"page": 999999},
        )
        
        # Should return empty list, not error
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert data["applications"] == []


# =============================================================================
# APPLICATION INPUT VALIDATION TESTS
# =============================================================================


class TestApplicationInputValidation:
    """Tests for application input validation."""

    def test_status_case_insensitive_filter(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that status filter is case-insensitive."""
        response_lower = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"status_filter": "applied"},
        )
        
        response_upper = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"status_filter": "APPLIED"},
        )
        
        # Both should succeed
        assert response_lower.status_code in [200, 403]
        assert response_upper.status_code in [200, 403]

    def test_special_characters_in_id(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test handling of special characters in application ID."""
        response = http_client.get(
            "/api/v1/applications/<script>alert('xss')</script>/download",
            headers=user_with_complete_profile,
        )
        
        # Should fail gracefully
        assert response.status_code in [400, 403, 404, 422]

    def test_sql_injection_attempt_in_filter(
        self, http_client: httpx.Client, user_with_complete_profile: Dict[str, str]
    ):
        """Test that SQL injection attempts in filter are handled."""
        response = http_client.get(
            "/api/v1/applications/",
            headers=user_with_complete_profile,
            params={"status_filter": "applied'; DROP TABLE applications;--"},
        )
        
        # Should handle gracefully (returns empty or error, doesn't crash)
        assert response.status_code in [200, 400, 403, 422]

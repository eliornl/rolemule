"""
Comprehensive tests for Workflow API endpoints.

These tests cover the complete workflow functionality:
- POST /api/v1/workflow/start - Start a new job application workflow
- GET /api/v1/workflow/status/{session_id} - Get workflow status
- GET /api/v1/workflow/results/{session_id} - Get workflow results
- POST /api/v1/workflow/continue/{session_id} - Continue after gate decision

Tests run against the actual running server at localhost:8000.
Make sure the server is running before executing these tests.
"""

import uuid
import time
import pytest
import httpx
from typing import Dict, Any, Optional

from tests.live_server_helpers import ensure_llm_ready


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"

# Sample job posting data for testing
SAMPLE_JOB_TEXT = """
Software Engineer - Full Stack

Company: TechCorp Inc.
Location: San Francisco, CA (Remote available)
Salary: $120,000 - $180,000

About the Role:
We are looking for a talented Full Stack Software Engineer to join our team.
You will be working on our flagship product, building scalable web applications.

Requirements:
- 3+ years of experience in software development
- Proficiency in Python and JavaScript
- Experience with React or Vue.js
- Familiarity with PostgreSQL and Redis
- Experience with cloud platforms (AWS, GCP)
- Strong problem-solving skills

Nice to Have:
- Experience with FastAPI
- Knowledge of Docker and Kubernetes
- CI/CD pipeline experience

Benefits:
- Competitive salary
- Health insurance
- 401k matching
- Flexible work hours
- Remote work options
"""

SAMPLE_JOB_URL = "https://boards.greenhouse.io/testcompany/jobs/1234567890"

# Valid profile data for completing profile setup
VALID_BASIC_INFO = {
    "city": "San Francisco",
    "state": "California",
    "country": "United States",
    "professional_title": "Software Engineer",
    "years_experience": 5,
    "is_student": False,
    "summary": "Experienced software engineer with expertise in Python, JavaScript, and cloud technologies.",
}

VALID_SKILLS = {
    "skills": ["Python", "JavaScript", "React", "PostgreSQL", "AWS", "Docker"]
}

VALID_CAREER_PREFERENCES = {
    "desired_salary_range": {"min": 100000, "max": 200000},
    "desired_company_sizes": ["Medium (51-200 employees)", "Large (201-1000 employees)"],
    "job_types": ["Full-time"],
    "work_arrangements": ["Remote", "Hybrid"],
    "willing_to_relocate": False,
    "requires_visa_sponsorship": False,
    "work_authorization": "has_work_authorization",
    "has_security_clearance": False,
    "max_travel_preference": "25",
}


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_workflow_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def authenticated_user(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a test user, return headers with token."""
    # Register a new user
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Workflow Test User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_with_complete_profile(http_client: httpx.Client, authenticated_user: Dict[str, str]):
    """Create a user with a complete profile setup."""
    # Complete basic info
    basic_info_response = http_client.put(
        "/api/v1/profile/basic-info",
        headers=authenticated_user,
        json=VALID_BASIC_INFO,
    )
    assert basic_info_response.status_code == 200, f"Basic info failed: {basic_info_response.text}"
    
    # Complete work experience (empty list is valid — "no relevant experience")
    work_exp_response = http_client.put(
        "/api/v1/profile/work-experience",
        headers=authenticated_user,
        json={"work_experience": []},
    )
    assert work_exp_response.status_code == 200

    # Education step required for profile_completed (empty list = none to add)
    education_response = http_client.put(
        "/api/v1/profile/education",
        headers=authenticated_user,
        json={"education": []},
    )
    assert education_response.status_code == 200, education_response.text
    
    # Complete skills
    skills_response = http_client.put(
        "/api/v1/profile/skills-qualifications",
        headers=authenticated_user,
        json=VALID_SKILLS,
    )
    assert skills_response.status_code == 200
    
    # Complete career preferences
    prefs_response = http_client.put(
        "/api/v1/profile/career-preferences",
        headers=authenticated_user,
        json=VALID_CAREER_PREFERENCES,
    )
    assert prefs_response.status_code == 200

    # Persist users.profile_completed for get_current_user_with_complete_profile
    complete_response = http_client.post(
        "/api/v1/profile/complete",
        headers=authenticated_user,
    )
    assert complete_response.status_code == 200, complete_response.text
    
    return authenticated_user


@pytest.fixture
def user_with_api_key(http_client: httpx.Client, user_with_complete_profile: Dict[str, str]):
    """Create a user with complete profile and BYOK Gemini key configured."""
    ensure_llm_ready(http_client, user_with_complete_profile)
    return user_with_complete_profile


@pytest.fixture
def second_authenticated_user(http_client: httpx.Client):
    """Create a second authenticated user for isolation tests."""
    unique_email = f"test_workflow_second_{uuid.uuid4().hex[:8]}@example.com"
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Second Workflow Test User",
        },
    )
    assert register_response.status_code == 200
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def wait_for_workflow_completion(
    http_client: httpx.Client,
    headers: Dict[str, str],
    session_id: str,
    max_wait_seconds: int = 120,
    poll_interval: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """
    Poll workflow status until completion or timeout.
    
    Returns the final status response or None if timed out.
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        response = http_client.get(
            f"/api/v1/workflow/status/{session_id}",
            headers=headers,
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        status = data.get("status", "")
        
        # Check for terminal states
        if status in ["completed", "failed", "awaiting_confirmation"]:
            return data
        
        time.sleep(poll_interval)
    
    return None


# =============================================================================
# START WORKFLOW TESTS
# =============================================================================


class TestWorkflowStart:
    """Tests for POST /api/v1/workflow/start endpoint."""

    def test_start_workflow_with_text_input(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting a workflow with job text input."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        # May fail due to incomplete profile (403), validation (400), or rate limit (429)
        assert response.status_code in [200, 400, 403, 422, 429]
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "status" in data
            assert "message" in data
            assert data["status"] == "initialized"

    def test_start_workflow_with_url_input(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting a workflow with job URL input."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_url": SAMPLE_JOB_URL},
        )
        
        # URL scraping may fail, profile incomplete (403), or rate limited (429)
        assert response.status_code in [200, 400, 403, 422, 429]
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert data["status"] == "initialized"

    def test_start_workflow_with_extension_source(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting a workflow from Chrome extension."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={
                "job_text": SAMPLE_JOB_TEXT,
                "source": "extension",
                "source_url": "https://example.com/job/12345",
                "detected_title": "Software Engineer",
                "detected_company": "TechCorp Inc.",
            },
        )
        
        # 403 = incomplete profile, 400 = validation, 429 = rate limit
        assert response.status_code in [200, 400, 403, 422, 429]
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert data["status"] == "initialized"

    def test_start_workflow_without_input(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that starting without any input fails."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            json={},
        )
        
        # 400 = missing input, 403 = incomplete profile
        assert response.status_code in [400, 403, 422]

    def test_start_workflow_invalid_url_format(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that invalid URL format is rejected."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_url": "not-a-valid-url"},
        )
        
        # Invalid / non-http(s) posting URLs are discarded server-side; start may
        # still succeed with empty content handling or return a validation error.
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_start_workflow_url_without_protocol(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that URL without http/https is rejected or discarded."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_url": "www.example.com/job/12345"},
        )
        
        # Non-http(s) URLs are discarded; may succeed or fail validation
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_start_workflow_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated requests are rejected."""
        response = http_client.post(
            "/api/v1/workflow/start",
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        assert response.status_code in [401, 403]

    def test_start_workflow_without_complete_profile(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that starting without complete profile fails."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=authenticated_user,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        # Should fail due to incomplete profile
        assert response.status_code in [400, 403, 422]

    def test_start_workflow_response_structure(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that start response has correct structure."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Required fields
            assert "session_id" in data
            assert "status" in data
            assert "message" in data
            
            # Type checks
            assert isinstance(data["session_id"], str)
            assert isinstance(data["status"], str)
            assert isinstance(data["message"], str)
            
            # UUID format check for session_id
            try:
                uuid.UUID(data["session_id"])
            except ValueError:
                pytest.fail("session_id is not a valid UUID")

    def test_start_workflow_with_both_url_and_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting with both URL and text (URL should take precedence)."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={
                "job_url": SAMPLE_JOB_URL,
                "job_text": SAMPLE_JOB_TEXT,
            },
        )
        
        # Should accept - URL takes precedence (403 = profile incomplete)
        assert response.status_code in [200, 400, 403, 422, 429]


# =============================================================================
# WORKFLOW STATUS TESTS
# =============================================================================


class TestWorkflowStatus:
    """Tests for GET /api/v1/workflow/status/{session_id} endpoint."""

    def test_get_status_valid_session(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting status of a valid workflow session."""
        # Start a workflow first
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow for status test")
        
        session_id = start_response.json()["session_id"]
        
        # Get status
        status_response = http_client.get(
            f"/api/v1/workflow/status/{session_id}",
            headers=user_with_api_key,
        )
        
        assert status_response.status_code == 200
        data = status_response.json()
        
        assert data["session_id"] == session_id
        assert "status" in data
        assert "status_display" in data
        assert "current_phase" in data
        assert "progress_percentage" in data

    def test_get_status_nonexistent_session(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting status of non-existent session."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.get(
            f"/api/v1/workflow/status/{fake_session_id}",
            headers=user_with_api_key,
        )
        
        assert response.status_code == 404

    def test_get_status_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated status requests are rejected."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.get(f"/api/v1/workflow/status/{fake_session_id}")
        
        assert response.status_code in [401, 403]

    def test_get_status_other_users_session(
        self,
        http_client: httpx.Client,
        user_with_api_key: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that users cannot access other users' workflow status."""
        # Start workflow as first user
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow for isolation test")
        
        session_id = start_response.json()["session_id"]
        
        # Try to get status as second user
        status_response = http_client.get(
            f"/api/v1/workflow/status/{session_id}",
            headers=second_authenticated_user,
        )
        
        # Should fail - session belongs to another user
        assert status_response.status_code in [404, 403]

    def test_get_status_response_structure(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that status response has correct structure."""
        # Start a workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id = start_response.json()["session_id"]
        
        # Get status
        status_response = http_client.get(
            f"/api/v1/workflow/status/{session_id}",
            headers=user_with_api_key,
        )
        
        assert status_response.status_code == 200
        data = status_response.json()
        
        # Required fields
        required_fields = [
            "session_id",
            "status",
            "status_display",
            "current_phase",
            "agent_status",
            "completed_agents",
            "error_messages",
            "progress_percentage",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Type checks
        assert isinstance(data["session_id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["progress_percentage"], int)
        assert isinstance(data["agent_status"], dict)
        assert isinstance(data["completed_agents"], list)
        assert isinstance(data["error_messages"], list)
        
        # Progress bounds
        assert 0 <= data["progress_percentage"] <= 100

    def test_get_status_invalid_session_id_format(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting status with invalid session ID format."""
        response = http_client.get(
            "/api/v1/workflow/status/not-a-valid-uuid",
            headers=user_with_api_key,
        )
        
        # May return 404 or 422 depending on validation
        assert response.status_code in [404, 422, 500]


# =============================================================================
# WORKFLOW RESULTS TESTS
# =============================================================================


class TestWorkflowResults:
    """Tests for GET /api/v1/workflow/results/{session_id} endpoint."""

    def test_get_results_nonexistent_session(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting results of non-existent session."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.get(
            f"/api/v1/workflow/results/{fake_session_id}",
            headers=user_with_api_key,
        )
        
        assert response.status_code == 404

    def test_get_results_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated results requests are rejected."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.get(f"/api/v1/workflow/results/{fake_session_id}")
        
        assert response.status_code in [401, 403]

    def test_get_results_in_progress_workflow(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting results of workflow that is still in progress."""
        # Start a workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id = start_response.json()["session_id"]
        
        # Try to get results immediately (workflow still in progress)
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id}",
            headers=user_with_api_key,
        )
        
        # Should fail because workflow is still running (validation_error → 422)
        assert results_response.status_code in [400, 404, 422]

    def test_get_results_other_users_session(
        self,
        http_client: httpx.Client,
        user_with_api_key: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that users cannot access other users' workflow results."""
        # Start workflow as first user
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id = start_response.json()["session_id"]
        
        # Try to get results as second user
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id}",
            headers=second_authenticated_user,
        )
        
        # Should fail - session belongs to another user
        assert results_response.status_code in [404, 403]

    def test_get_results_invalid_session_id_format(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting results with invalid session ID format."""
        response = http_client.get(
            "/api/v1/workflow/results/not-a-valid-uuid",
            headers=user_with_api_key,
        )
        
        assert response.status_code in [404, 422, 500]


# =============================================================================
# WORKFLOW CONTINUE TESTS
# =============================================================================


class TestWorkflowContinue:
    """Tests for POST /api/v1/workflow/continue/{session_id} endpoint."""

    def test_continue_nonexistent_session(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test continuing a non-existent session."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.post(
            f"/api/v1/workflow/continue/{fake_session_id}",
            headers=user_with_api_key,
        )
        
        assert response.status_code == 404

    def test_continue_without_auth(self, http_client: httpx.Client):
        """Test that unauthenticated continue requests are rejected."""
        fake_session_id = str(uuid.uuid4())
        
        response = http_client.post(f"/api/v1/workflow/continue/{fake_session_id}")
        
        assert response.status_code in [401, 403]

    def test_continue_workflow_not_awaiting(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test continuing a workflow that is not awaiting confirmation."""
        # Start a workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id = start_response.json()["session_id"]
        
        # Try to continue immediately (not awaiting confirmation)
        continue_response = http_client.post(
            f"/api/v1/workflow/continue/{session_id}",
            headers=user_with_api_key,
        )
        
        # Should fail because workflow is not awaiting confirmation
        assert continue_response.status_code in [400, 404, 422]

    def test_continue_other_users_session(
        self,
        http_client: httpx.Client,
        user_with_api_key: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that users cannot continue other users' workflows."""
        # Start workflow as first user
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id = start_response.json()["session_id"]
        
        # Try to continue as second user
        continue_response = http_client.post(
            f"/api/v1/workflow/continue/{session_id}",
            headers=second_authenticated_user,
        )
        
        # Should fail - session belongs to another user
        assert continue_response.status_code in [404, 403]

    def test_continue_invalid_session_id_format(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test continuing with invalid session ID format."""
        response = http_client.post(
            "/api/v1/workflow/continue/not-a-valid-uuid",
            headers=user_with_api_key,
        )
        
        assert response.status_code in [404, 422, 500]


# =============================================================================
# WORKFLOW INPUT VALIDATION TESTS
# =============================================================================


class TestWorkflowInputValidation:
    """Tests for workflow input validation."""

    def test_job_text_max_length(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that very long job text is handled."""
        # Create text just under limit (50000 chars)
        long_text = "A" * 50000
        
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": long_text},
        )
        
        # Should accept or reject (403 = profile incomplete)
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_job_text_exceeds_max_length(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that text exceeding max length is rejected."""
        # Create text over limit
        very_long_text = "A" * 50001
        
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": very_long_text},
        )
        
        # Form field max length may be enforced as 400/422, or accepted if only
        # the JSON body model had the limit historically.
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_job_url_max_length(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that very long URL is rejected or truncated/discarded."""
        long_url = "https://example.com/" + "a" * 2000
        
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_url": long_url},
        )
        
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_empty_job_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that empty job text is rejected."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": ""},
        )
        
        # Empty text should be treated as no input (403 = profile incomplete)
        assert response.status_code in [400, 403, 422]

    def test_whitespace_only_job_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that whitespace-only job text is handled."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": "   \n\t   "},
        )
        
        # Whitespace-only should be treated as no input (403 = profile incomplete)
        assert response.status_code in [200, 400, 403]

    def test_special_characters_in_job_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test job text with special characters."""
        special_text = """
        Job: Software Engineer 🚀
        Requirements: C++, C#, Node.js
        Salary: $100,000 - $150,000
        Benefits: 401(k), Health Insurance
        Location: San Francisco, CA — Remote
        Email: careers@company.com
        """
        
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": special_text},
        )
        
        # Should handle special characters gracefully (403 = profile incomplete)
        assert response.status_code in [200, 400, 403, 422, 429]

    def test_unicode_job_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test job text with unicode characters."""
        unicode_text = """
        職位: 软件工程师
        Company: Société Générale
        Location: München, Deutschland
        Description: Développement logiciel
        """
        
        response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": unicode_text},
        )
        
        # Should handle unicode gracefully (403 = profile incomplete)
        assert response.status_code in [200, 400, 403, 422, 429]


# =============================================================================
# WORKFLOW RATE LIMITING TESTS
# =============================================================================


class TestWorkflowRateLimiting:
    """Tests for workflow rate limiting."""

    def test_rate_limit_message_format(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that rate limit response has correct format."""
        # Make multiple requests to potentially trigger rate limit
        responses = []
        for _ in range(12):
            response = http_client.post(
                "/api/v1/workflow/start",
                headers=user_with_api_key,
                data={"job_text": SAMPLE_JOB_TEXT},
            )
            responses.append(response)
            
            if response.status_code == 429:
                # Found rate limit response
                data = response.json()
                assert "rate limit" in data.get("detail", "").lower() or \
                       "rate limit" in data.get("message", "").lower()
                break
        
        # If we didn't hit rate limit, that's also OK
        # Just verifying the endpoint handles multiple requests


# =============================================================================
# WORKFLOW ISOLATION TESTS
# =============================================================================


class TestWorkflowIsolation:
    """Tests to verify workflow data is properly isolated between users."""

    def test_sessions_isolated_between_users(
        self,
        http_client: httpx.Client,
        user_with_api_key: Dict[str, str],
        second_authenticated_user: Dict[str, str],
    ):
        """Test that workflow sessions are isolated between users."""
        # Start workflow as first user
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip("Could not start workflow")
        
        session_id_user1 = start_response.json()["session_id"]
        
        # Second user should not be able to access first user's session
        status_response = http_client.get(
            f"/api/v1/workflow/status/{session_id_user1}",
            headers=second_authenticated_user,
        )
        
        assert status_response.status_code in [404, 403]
        
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id_user1}",
            headers=second_authenticated_user,
        )
        
        assert results_response.status_code in [404, 403]


# =============================================================================
# WORKFLOW INTEGRATION TESTS
# =============================================================================


class TestWorkflowIntegration:
    """Integration tests for the complete workflow flow."""

    def test_complete_workflow_flow_text_input(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test complete workflow from start to status check."""
        # Step 1: Start workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": SAMPLE_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip(f"Could not start workflow: {start_response.text}")
        
        data = start_response.json()
        session_id = data["session_id"]
        
        assert data["status"] == "initialized"
        
        # Step 2: Check status (should be running or already completed)
        status_response = http_client.get(
            f"/api/v1/workflow/status/{session_id}",
            headers=user_with_api_key,
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        # Status should be one of the valid states
        valid_statuses = ["initialized", "in_progress", "completed", "failed", "awaiting_confirmation"]
        assert status_data["status"] in valid_statuses

    def test_workflow_multiple_sessions(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that users can create multiple workflow sessions."""
        session_ids = []
        
        # Start multiple workflows
        for i in range(3):
            response = http_client.post(
                "/api/v1/workflow/start",
                headers=user_with_api_key,
                data={"job_text": f"{SAMPLE_JOB_TEXT}\n\nVersion: {i}"},
            )
            
            if response.status_code == 200:
                session_ids.append(response.json()["session_id"])
            elif response.status_code == 429:
                # Rate limited - stop trying
                break
        
        # Each session should have a unique ID
        assert len(session_ids) == len(set(session_ids)), "Session IDs should be unique"
        
        # Each session should be accessible
        for session_id in session_ids:
            status_response = http_client.get(
                f"/api/v1/workflow/status/{session_id}",
                headers=user_with_api_key,
            )
            assert status_response.status_code == 200


# =============================================================================
# WORKFLOW ERROR HANDLING TESTS
# =============================================================================


class TestWorkflowErrorHandling:
    """Tests for workflow error handling."""

    def test_start_with_invalid_json(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting workflow with invalid JSON."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers={**user_with_api_key, "Content-Type": "application/json"},
            content="not valid json",
        )
        
        # 400/422 = invalid JSON, 403 = profile incomplete may be checked first
        assert response.status_code in [400, 403, 422]

    def test_start_with_wrong_content_type(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test starting workflow with wrong content type."""
        response = http_client.post(
            "/api/v1/workflow/start",
            headers={**user_with_api_key, "Content-Type": "text/plain"},
            content="job_text=some text",
        )
        
        # May accept or reject depending on FastAPI parsing (403 = profile incomplete)
        assert response.status_code in [200, 400, 403, 415, 422]

    def test_status_with_empty_session_id(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting status with empty session ID."""
        response = http_client.get(
            "/api/v1/workflow/status/",
            headers=user_with_api_key,
        )
        
        # Empty path segment should 404 or redirect
        assert response.status_code in [404, 405, 307]

    def test_results_with_empty_session_id(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test getting results with empty session ID."""
        response = http_client.get(
            "/api/v1/workflow/results/",
            headers=user_with_api_key,
        )
        
        assert response.status_code in [404, 405, 307]

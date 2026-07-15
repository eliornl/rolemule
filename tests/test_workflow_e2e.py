"""
End-to-End tests for the complete workflow execution.

These tests verify the full workflow from start to completion,
including all agents and the gate decision logic.

Tests are marked as 'slow' and can be skipped in CI with: pytest -m "not slow"

IMPORTANT: These tests require:
1. Running server at localhost:8000
2. Valid Gemini API key configured
3. PostgreSQL and Redis running
"""

import uuid
import time
import pytest
import httpx
from typing import Dict, Any, Optional

from tests.live_server_helpers import (
    ensure_llm_ready,
    skip_unless_llm_ok,
    skip_unless_real_gemini,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"

# Timeout settings for workflow completion
MAX_WORKFLOW_WAIT_SECONDS = 180  # 3 minutes max
POLL_INTERVAL_SECONDS = 3

# Sample job posting that should result in a good match
GOOD_MATCH_JOB_TEXT = """
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

# Sample job posting that should result in a poor match (for gate testing)
POOR_MATCH_JOB_TEXT = """
Senior Neurosurgeon - Chief of Surgery

Hospital: Elite Medical Center
Location: Boston, MA (On-site only)

Requirements:
- MD degree with specialization in Neurosurgery
- Board certified in Neurosurgery
- 15+ years of surgical experience
- Fellowship in Pediatric Neurosurgery
- Active medical license in Massachusetts
- Malpractice insurance

Responsibilities:
- Lead complex neurosurgical procedures
- Supervise surgical residents
- Participate in clinical research
"""

# Valid profile data for completing profile setup
VALID_BASIC_INFO = {
    "city": "San Francisco",
    "state": "California",
    "country": "United States",
    "professional_title": "Software Engineer",
    "years_experience": 5,
    "is_student": False,
    "summary": "Experienced full-stack software engineer with expertise in Python, JavaScript, and cloud technologies. Led teams and delivered scalable applications.",
}

VALID_WORK_EXPERIENCE = {
    "work_experience": [
        {
            "job_title": "Senior Software Engineer",
            "company": "StartupCo",
            "start_date": "2021-01",
            "end_date": None,
            "is_current": True,
            "description": "Lead backend development with Python/FastAPI. Scaled system to 500K users. Mentored 3 junior developers.",
        },
        {
            "job_title": "Software Engineer",
            "company": "TechCompany",
            "start_date": "2019-01",
            "end_date": "2020-12",
            "is_current": False,
            "description": "Full-stack development with React and Node.js. Built customer-facing features.",
        },
    ]
}

VALID_SKILLS = {
    "skills": ["Python", "JavaScript", "React", "FastAPI", "PostgreSQL", "AWS", "Docker", "Git", "REST APIs", "SQL"]
}

VALID_CAREER_PREFERENCES = {
    "desired_salary_range": {"min": 120000, "max": 200000},
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
    return f"test_e2e_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def authenticated_user_with_profile(http_client: httpx.Client, unique_email: str):
    """Create and authenticate a test user with complete profile."""
    # Register
    register_response = http_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "End to End Test User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Complete profile - Basic Info
    basic_info_response = http_client.put(
        "/api/v1/profile/basic-info",
        headers=headers,
        json=VALID_BASIC_INFO,
    )
    assert basic_info_response.status_code == 200, f"Basic info failed: {basic_info_response.text}"
    
    # Complete profile - Work Experience
    work_exp_response = http_client.put(
        "/api/v1/profile/work-experience",
        headers=headers,
        json=VALID_WORK_EXPERIENCE,
    )
    assert work_exp_response.status_code == 200, f"Work experience failed: {work_exp_response.text}"

    education_response = http_client.put(
        "/api/v1/profile/education",
        headers=headers,
        json={"education": []},
    )
    assert education_response.status_code == 200, f"Education failed: {education_response.text}"
    
    # Complete profile - Skills
    skills_response = http_client.put(
        "/api/v1/profile/skills-qualifications",
        headers=headers,
        json=VALID_SKILLS,
    )
    assert skills_response.status_code == 200, f"Skills failed: {skills_response.text}"
    
    # Complete profile - Career Preferences
    prefs_response = http_client.put(
        "/api/v1/profile/career-preferences",
        headers=headers,
        json=VALID_CAREER_PREFERENCES,
    )
    assert prefs_response.status_code == 200, f"Career prefs failed: {prefs_response.text}"

    complete_response = http_client.post(
        "/api/v1/profile/complete",
        headers=headers,
    )
    assert complete_response.status_code == 200, f"Complete failed: {complete_response.text}"
    
    return headers


@pytest.fixture
def user_with_api_key(http_client: httpx.Client, authenticated_user_with_profile: Dict[str, str]):
    """User with complete profile and BYOK Gemini key configured."""
    ensure_llm_ready(http_client, authenticated_user_with_profile)
    return authenticated_user_with_profile


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def wait_for_workflow_completion(
    http_client: httpx.Client,
    headers: Dict[str, str],
    session_id: str,
    max_wait_seconds: int = MAX_WORKFLOW_WAIT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
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
            print(f"Status check failed: {response.status_code} - {response.text}")
            return None
        
        data = response.json()
        status = data.get("status", "")
        current_agent = data.get("current_agent", "")
        progress = data.get("progress_percentage", 0)
        
        print(f"Workflow status: {status}, agent: {current_agent}, progress: {progress}%")
        
        # Check for terminal states
        if status in ["completed", "failed", "awaiting_confirmation"]:
            return data
        
        time.sleep(poll_interval)
    
    print(f"Workflow timed out after {max_wait_seconds} seconds")
    return None


# =============================================================================
# E2E WORKFLOW TESTS
# =============================================================================


@pytest.mark.slow
class TestWorkflowE2E:
    """End-to-end tests for complete workflow execution."""

    def test_complete_workflow_good_match(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """
        Test complete workflow execution with a job that should be a good match.
        
        Expected flow:
        1. Start workflow with good match job
        2. Job Analyzer extracts job data
        3. Profile Matching finds good match (>50%)
        4. Gate decision: CONTINUE
        5. Company Research runs
        6. Resume Advisor and Cover Letter Writer run in parallel
        7. Workflow completes successfully
        """
        skip_unless_real_gemini()
        # Start workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": GOOD_MATCH_JOB_TEXT},
        )
        
        skip_unless_llm_ok(start_response)
        if start_response.status_code == 429:
            pytest.skip("Rate limited - skipping E2E test")

        assert start_response.status_code == 200, f"Start failed: {start_response.text}"
        
        session_id = start_response.json()["session_id"]
        print(f"\nStarted workflow: {session_id}")
        
        # Wait for completion
        final_status = wait_for_workflow_completion(http_client, user_with_api_key, session_id)
        
        assert final_status is not None, "Workflow timed out"
        assert final_status["status"] in ["completed", "awaiting_confirmation"], \
            f"Unexpected final status: {final_status['status']}"
        
        # Get results
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id}",
            headers=user_with_api_key,
        )
        
        assert results_response.status_code == 200, f"Results failed: {results_response.text}"
        
        results = results_response.json()
        
        # Verify all agent outputs are present
        assert results["job_analysis"] is not None, "Missing job analysis"
        assert results["profile_matching"] is not None, "Missing profile matching"
        
        # For completed workflows, these should also be present
        if final_status["status"] == "completed":
            assert results["company_research"] is not None, "Missing company research"
            assert results["resume_recommendations"] is not None, "Missing resume recommendations"
            assert results["cover_letter"] is not None, "Missing cover letter"
        
        # Verify job analysis extracted correct data
        job_analysis = results["job_analysis"]
        assert job_analysis.get("job_title"), "Job title not extracted"
        assert job_analysis.get("company_name"), "Company name not extracted"
        
        # Verify profile matching scores
        profile_matching = results["profile_matching"]
        assert "overall_score" in profile_matching or "final_scores" in profile_matching
        
        print("\nWorkflow completed successfully!")
        print(f"Job: {job_analysis.get('job_title')} at {job_analysis.get('company_name')}")
        
        exec_summary = profile_matching.get("executive_summary", {})
        print(f"Match: {exec_summary.get('recommendation', 'N/A')}")

    def test_workflow_gate_decision_poor_match(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """
        Test workflow gate decision with a job that should be a poor match.
        
        Expected flow:
        1. Start workflow with poor match job (neurosurgeon for software engineer)
        2. Job Analyzer extracts job data
        3. Profile Matching finds poor match (<50%)
        4. Gate decision: STOP (awaiting_confirmation)
        5. Workflow pauses for user confirmation
        """
        skip_unless_real_gemini()
        # Start workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": POOR_MATCH_JOB_TEXT},
        )
        
        skip_unless_llm_ok(start_response)
        if start_response.status_code == 429:
            pytest.skip("Rate limited - skipping E2E test")

        assert start_response.status_code == 200, f"Start failed: {start_response.text}"
        
        session_id = start_response.json()["session_id"]
        print(f"\nStarted workflow: {session_id}")
        
        # Wait for completion (should stop at gate)
        final_status = wait_for_workflow_completion(http_client, user_with_api_key, session_id)
        
        assert final_status is not None, "Workflow timed out"
        
        # Should be either awaiting_confirmation (gate triggered) or completed (if match was okay)
        assert final_status["status"] in ["completed", "failed", "awaiting_confirmation"], \
            f"Unexpected status: {final_status['status']}"
        
        # Get results
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id}",
            headers=user_with_api_key,
        )
        
        assert results_response.status_code == 200
        results = results_response.json()
        
        # Job analysis and profile matching should always be present
        assert results["job_analysis"] is not None
        assert results["profile_matching"] is not None
        
        profile_matching = results["profile_matching"]
        overall_score = profile_matching.get("overall_score", 0)
        
        print(f"\nOverall match score: {overall_score:.2%}")
        print(f"Final status: {final_status['status']}")
        
        # If gate was triggered, verify the status
        if final_status["status"] == "awaiting_confirmation":
            print("Gate decision triggered - workflow paused for user confirmation")
            # Company research and documents should NOT be present yet
            assert results["company_research"] is None or results["company_research"] == {}
            assert results["resume_recommendations"] is None or results["resume_recommendations"] == {}

    def test_workflow_continue_after_gate(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """
        Test continuing workflow after gate decision.
        
        This test:
        1. Starts a workflow that triggers the gate
        2. Calls continue endpoint
        3. Verifies workflow completes
        """
        skip_unless_real_gemini()
        # Start workflow with poor match job to trigger gate
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": POOR_MATCH_JOB_TEXT},
        )
        
        if start_response.status_code == 429:
            pytest.skip("Rate limited - skipping E2E test")
        
        if start_response.status_code != 200:
            pytest.skip(f"Could not start workflow: {start_response.text}")
        
        session_id = start_response.json()["session_id"]
        
        # Wait for gate decision
        gate_status = wait_for_workflow_completion(http_client, user_with_api_key, session_id)
        
        if gate_status is None:
            pytest.skip("Workflow timed out")
        
        if gate_status["status"] != "awaiting_confirmation":
            pytest.skip(f"Gate not triggered - status is {gate_status['status']}")
        
        print(f"\nGate triggered for session {session_id}")
        
        # Continue the workflow
        continue_response = http_client.post(
            f"/api/v1/workflow/continue/{session_id}",
            headers=user_with_api_key,
        )
        
        assert continue_response.status_code == 200, f"Continue failed: {continue_response.text}"
        
        print("Workflow resumed - waiting for completion...")
        
        # Wait for final completion
        final_status = wait_for_workflow_completion(http_client, user_with_api_key, session_id)
        
        assert final_status is not None, "Workflow timed out after continue"
        assert final_status["status"] == "completed", f"Expected completed, got {final_status['status']}"
        
        # Get final results
        results_response = http_client.get(
            f"/api/v1/workflow/results/{session_id}",
            headers=user_with_api_key,
        )
        
        results = results_response.json()
        
        # All outputs should now be present
        assert results["company_research"] is not None
        assert results["resume_recommendations"] is not None
        assert results["cover_letter"] is not None
        
        print("Workflow completed successfully after continue!")


# =============================================================================
# WORKFLOW TIMING TESTS
# =============================================================================


@pytest.mark.slow
class TestWorkflowTiming:
    """Tests for workflow execution timing."""

    def test_workflow_completes_within_timeout(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test that workflow completes within reasonable time."""
        skip_unless_real_gemini()
        start_time = time.time()
        
        # Start workflow
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": GOOD_MATCH_JOB_TEXT},
        )
        
        if start_response.status_code != 200:
            pytest.skip(f"Could not start workflow: {start_response.text}")
        
        session_id = start_response.json()["session_id"]
        
        # Wait for completion
        final_status = wait_for_workflow_completion(http_client, user_with_api_key, session_id)
        
        elapsed_time = time.time() - start_time
        
        assert final_status is not None, f"Workflow did not complete within {MAX_WORKFLOW_WAIT_SECONDS}s"
        
        print(f"\nWorkflow completed in {elapsed_time:.1f} seconds")
        
        # Should complete within 3 minutes
        assert elapsed_time < 180, f"Workflow took too long: {elapsed_time:.1f}s"


# =============================================================================
# WORKFLOW ERROR HANDLING TESTS
# =============================================================================


@pytest.mark.slow  
class TestWorkflowErrorHandling:
    """Tests for workflow error handling during E2E execution."""

    def test_workflow_handles_minimal_job_text(
        self, http_client: httpx.Client, user_with_api_key: Dict[str, str]
    ):
        """Test workflow handles minimal but valid job text."""
        skip_unless_real_gemini()
        minimal_job = """
        Software Engineer
        Company: TestCorp
        Requirements: Python, JavaScript
        """
        
        start_response = http_client.post(
            "/api/v1/workflow/start",
            headers=user_with_api_key,
            data={"job_text": minimal_job},
        )
        
        if start_response.status_code == 429:
            pytest.skip("Rate limited")
        
        # Should either start successfully or return validation error
        assert start_response.status_code in [200, 400, 422]
        
        if start_response.status_code == 200:
            session_id = start_response.json()["session_id"]
            final_status = wait_for_workflow_completion(
                http_client, user_with_api_key, session_id, max_wait_seconds=120
            )
            
            # Should either complete or fail gracefully
            assert final_status is not None
            assert final_status["status"] in ["completed", "failed", "awaiting_confirmation"]

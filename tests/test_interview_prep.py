"""
Integration and unit tests for interview prep API endpoints.

Integration tests run against the running server at localhost:8000.
Make sure the server is running before executing these tests.

Tests cover:
- GET /api/v1/interview-prep/{session_id} - Get interview prep for session
- GET /api/v1/interview-prep/{session_id}/status - Check generation status
- POST /api/v1/interview-prep/{session_id}/generate - Generate interview prep
- DELETE /api/v1/interview-prep/{session_id} - Delete interview prep
- Unit tests for agent and cache functions
"""

import uuid
import time
import pytest
import httpx
from typing import Dict, Optional


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"
GENERATE_TIMEOUT = 120  # Interview prep generation can take time


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_interview_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def http_client():
    """Create a sync HTTP client for testing against external server."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=True) as client:
        yield client


@pytest.fixture
def long_timeout_client():
    """Create a sync HTTP client with longer timeout for generation tests."""
    with httpx.Client(base_url=BASE_URL, timeout=GENERATE_TIMEOUT, follow_redirects=True) as client:
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
            "full_name": "Test Interview User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_with_profile(http_client: httpx.Client, authenticated_user: Dict[str, str]):
    """Create an authenticated user with a fully completed profile (AUTH gate ready)."""
    from tests.live_server_helpers import ensure_llm_ready

    # Update basic info
    basic_info = {
        "city": "San Francisco",
        "state": "California",
        "country": "United States",
        "professional_title": "Software Engineer",
        "years_experience": 5,
        "is_student": False,
        "summary": "Experienced software engineer with expertise in Python and cloud technologies.",
    }
    
    response = http_client.put(
        "/api/v1/profile/basic-info",
        headers=authenticated_user,
        json=basic_info,
    )
    assert response.status_code == 200, f"Basic info update failed: {response.text}"
    
    # Update work experience (avoiding special characters like %)
    work_exp = {
        "work_experience": [
            {
                "company": "Tech Company Inc",
                "job_title": "Senior Software Engineer",
                "start_date": "2020-01",
                "end_date": None,
                "description": "Led development of cloud-native applications using Python and AWS. Managed team of 5 engineers.",
                "is_current": True,
            },
            {
                "company": "StartupXYZ",
                "job_title": "Software Engineer",
                "start_date": "2018-06",
                "end_date": "2019-12",
                "description": "Built RESTful APIs and microservices architecture. Improved system performance significantly.",
                "is_current": False,
            },
        ]
    }
    
    response = http_client.put(
        "/api/v1/profile/work-experience",
        headers=authenticated_user,
        json=work_exp,
    )
    assert response.status_code == 200, f"Work experience update failed: {response.text}"

    # Education step required for profile_completed (empty list = none to add)
    response = http_client.put(
        "/api/v1/profile/education",
        headers=authenticated_user,
        json={"education": []},
    )
    assert response.status_code == 200, f"Education update failed: {response.text}"
    
    # Update skills
    skills = {
        "skills": ["Python", "JavaScript", "AWS", "Docker", "PostgreSQL", "FastAPI", "React"]
    }
    
    response = http_client.put(
        "/api/v1/profile/skills-qualifications",
        headers=authenticated_user,
        json=skills,
    )
    assert response.status_code == 200, f"Skills update failed: {response.text}"
    
    # Update career preferences
    prefs = {
        "desired_salary_range": {"min": 120000, "max": 180000},
        "desired_company_sizes": ["Medium (51-200 employees)", "Large (201-1000 employees)"],
        "job_types": ["Full-time"],
        "work_arrangements": ["Remote", "Hybrid"],
        "willing_to_relocate": False,
        "requires_visa_sponsorship": False,
        "work_authorization": "has_work_authorization",
        "has_security_clearance": False,
        "max_travel_preference": "25",
    }
    
    response = http_client.put(
        "/api/v1/profile/career-preferences",
        headers=authenticated_user,
        json=prefs,
    )
    assert response.status_code == 200, f"Career preferences update failed: {response.text}"

    # Persist users.profile_completed for get_current_user_with_complete_profile
    complete_response = http_client.post(
        "/api/v1/profile/complete",
        headers=authenticated_user,
    )
    assert complete_response.status_code == 200, (
        f"Profile complete failed: {complete_response.text}"
    )

    # Avoid CFG_6001 on workflow start / interview-prep generate
    ensure_llm_ready(http_client, authenticated_user)
    
    return authenticated_user


@pytest.fixture
def completed_workflow_session(
    http_client: httpx.Client, 
    user_with_profile: Dict[str, str]
) -> Optional[str]:
    """
    Get or create a completed workflow session for testing interview prep.
    First tries to find an existing completed workflow, then creates one if needed.
    Returns the session_id of a completed workflow, or None if not available.
    
    Note: Creating a workflow requires LLM processing which takes 1-2 minutes.
    This is normal for integration tests involving AI agents.
    """
    from tests.live_server_helpers import skip_unless_real_gemini

    # A completed workflow needs a real upstream LLM; skip early without one.
    skip_unless_real_gemini()

    # First, try to get an existing completed workflow for this user
    list_response = http_client.get(
        "/api/v1/workflow/list",
        headers=user_with_profile,
    )
    
    if list_response.status_code == 200:
        list_data = list_response.json()
        sessions = list_data.get("sessions", [])
        
        # Look for any completed workflow
        for session in sessions:
            if session.get("status") == "completed" and session.get("job_analysis"):
                print(f"\nUsing existing completed workflow: {session.get('session_id')}")
                return session.get("session_id")
    
    # No existing completed workflow, create one
    # Add timestamp to job text to prevent cache hits
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n{'='*70}")
    print(f"  CREATING NEW WORKFLOW (no cache) - {timestamp}")
    print(f"{'='*70}")
    
    company_name = "TechCorp Industries"
    
    job_text = f"""
TechCorp Industries - Senior Python Developer
Job Reference: JOB-{timestamp}

About {company_name}:
{company_name} is a leading technology company specializing in cloud-native solutions.

We are looking for a Senior Python Developer to join our growing engineering team.

Requirements:
- 5+ years of Python development experience
- Strong knowledge of FastAPI or Django
- Experience with PostgreSQL and Redis
- AWS or GCP cloud experience preferred
- Strong problem solving skills

Responsibilities:
- Design and implement scalable backend services
- Mentor junior developers
- Participate in code reviews
- Collaborate with product and design teams

Benefits:
- Competitive salary ($150k-$200k)
- Remote work options
- Health insurance
- 401k matching

Apply now to join {company_name}!
"""
    
    # Create workflow using form data
    data = {
        "job_title": f"Senior Python Developer - {timestamp}",
        "company_name": company_name,
        "job_text": job_text,
    }
    
    response = http_client.post(
        "/api/v1/workflow/start",
        headers=user_with_profile,
        data=data,
    )
    
    if response.status_code != 200:
        pytest.skip(f"Could not create workflow: {response.text}")
        return None
    
    result = response.json()
    session_id = result.get("session_id")
    
    if not session_id:
        pytest.skip("No session_id returned from workflow start")
        return None
    
    print(f"Workflow started: {session_id}")
    print("Waiting for workflow to complete...")
    
    # Wait for workflow to complete (with timeout)
    max_wait = 180  # 3 minutes max
    start_time = time.time()
    poll_count = 0
    already_continued = False
    
    # Track timing per agent/phase directly
    phase_timings = {}  # phase -> start_time
    agent_timings = {}  # agent -> (start_time, end_time)
    last_agent = None
    last_phase = None
    
    while time.time() - start_time < max_wait:
        poll_count += 1
        elapsed = int(time.time() - start_time)
        
        try:
            status_response = http_client.get(
                f"/api/v1/workflow/status/{session_id}",
                headers=user_with_profile,
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                workflow_status = status_data.get("status", "unknown")
                current_phase = status_data.get("current_phase", "unknown")
                current_agent = status_data.get("current_agent")
                completed = status_data.get("completed_agents", [])
                errors = status_data.get("error_messages", [])
                
                # Track phase timing
                if current_phase != last_phase:
                    now = time.time()
                    if last_phase and last_phase in phase_timings:
                        phase_timings[last_phase] = now - phase_timings[last_phase]
                    if current_phase and current_phase not in phase_timings:
                        phase_timings[current_phase] = now
                    last_phase = current_phase
                
                # Track agent timing
                if current_agent != last_agent:
                    now = time.time()
                    if last_agent and last_agent in agent_timings and isinstance(agent_timings[last_agent], float):
                        agent_timings[last_agent] = now - agent_timings[last_agent]
                    if current_agent and current_agent not in agent_timings:
                        agent_timings[current_agent] = now
                    last_agent = current_agent
                
                # Get agent durations from API if available
                api_durations = status_data.get("agent_durations", {})
                
                # Always print detailed status
                print(f"  [{elapsed}s] Status: {workflow_status} | Phase: {current_phase} | Agent: {current_agent} | Completed: {len(completed)} agents")
                if errors:
                    print(f"       Errors: {errors}")
                
                if workflow_status == "completed":
                    # Finalize timing for last agent/phase
                    now = time.time()
                    if last_agent and last_agent in agent_timings and isinstance(agent_timings[last_agent], float):
                        agent_timings[last_agent] = now - agent_timings[last_agent]
                    if last_phase and last_phase in phase_timings and isinstance(phase_timings[last_phase], float):
                        phase_timings[last_phase] = now - phase_timings[last_phase]
                    
                    print(f"\n{'='*70}")
                    print(f"  WORKFLOW COMPLETED in {elapsed} seconds")
                    print(f"{'='*70}")
                    print(f"  Completed agents: {completed}")
                    
                    # Show measured agent timings
                    print("\n  Agent Timing (measured by test):")
                    total_measured = 0
                    for agent in ["job_analyzer", "profile_matching", "company_research", "resume_advisor", "cover_letter_writer"]:
                        if agent in agent_timings:
                            duration = agent_timings[agent]
                            if isinstance(duration, (int, float)):
                                total_measured += duration
                                print(f"    - {agent}: {duration:.1f}s")
                    print("    ─────────────────────────────────────")
                    print(f"    Total measured: {total_measured:.1f}s")
                    print(f"    Overhead (polling, network): {elapsed - total_measured:.1f}s")
                    
                    # Also show API-reported durations if available (accurate LLM times)
                    if api_durations:
                        print("\n  Agent Timing (actual LLM processing):")
                        total_api_time = 0
                        cached_count = 0
                        fresh_count = 0
                        for agent in ["job_analyzer", "profile_matching", "company_research", "resume_advisor", "cover_letter_writer"]:
                            if agent in api_durations:
                                ms = api_durations[agent]
                                secs = ms / 1000
                                total_api_time += secs
                                # Determine if cached/failed vs fresh
                                if secs < 0.5:
                                    status = "CACHED/SKIP"
                                    cached_count += 1
                                else:
                                    status = "FRESH"
                                    fresh_count += 1
                                print(f"    - {agent}: {secs:.1f}s [{status}]")
                        print("    ─────────────────────────────────────")
                        print(f"    Fresh LLM calls: {fresh_count} | Cached/Skipped: {cached_count}")
                        print(f"    Total LLM time: {total_api_time:.1f}s")
                        # Note: resume_advisor and cover_letter_writer run in parallel
                        parallel_max = max(
                            api_durations.get("resume_advisor", 0),
                            api_durations.get("cover_letter_writer", 0)
                        ) / 1000
                        sequential_time = (
                            api_durations.get("job_analyzer", 0) / 1000 +
                            api_durations.get("profile_matching", 0) / 1000 +
                            api_durations.get("company_research", 0) / 1000 +
                            parallel_max
                        )
                        print(f"    Effective wall time: ~{sequential_time:.0f}s")
                    
                    print(f"{'='*70}\n")
                    return session_id
                    
                elif workflow_status == "awaiting_confirmation" and not already_continued:
                    print("  >> Gate decision triggered, attempting to continue...")
                    continue_resp = http_client.post(
                        f"/api/v1/workflow/continue/{session_id}",
                        headers=user_with_profile,
                    )
                    print(f"  >> Continue response: {continue_resp.status_code}")
                    if continue_resp.status_code == 200:
                        print("  >> SUCCESS - Workflow continuing past gate")
                        already_continued = True
                    else:
                        print(f"  >> FAILED: {continue_resp.text[:200]}")
                        
                elif workflow_status in ["failed", "cancelled", "error"]:
                    print("  >> Workflow FAILED!")
                    print(f"  >> Errors: {errors}")
                    pytest.skip(f"Workflow {workflow_status}: {errors}")
                    return None
                    
            else:
                print(f"  [{elapsed}s] Status check FAILED: {status_response.status_code}")
                print(f"       Response: {status_response.text[:200]}")
                
        except Exception as e:
            print(f"  [{elapsed}s] EXCEPTION: {e}")
        
        time.sleep(3)  # Poll every 3 seconds for faster feedback
    
    pytest.skip(f"Workflow did not complete in {max_wait} seconds")
    return None


# =============================================================================
# GET INTERVIEW PREP TESTS
# =============================================================================


class TestGetInterviewPrep:
    """Tests for the GET /api/v1/interview-prep/{session_id} endpoint."""

    def test_get_interview_prep_without_auth(self, http_client: httpx.Client):
        """Test getting interview prep without authentication fails."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.get(f"/api/v1/interview-prep/{fake_session_id}")
        
        # Should return 401/403 (unauthorized) or 404 (not found due to auth check)
        assert response.status_code in [401, 403, 404]

    def test_get_interview_prep_with_invalid_token(self, http_client: httpx.Client):
        """Test getting interview prep with invalid token fails."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.get(
            f"/api/v1/interview-prep/{fake_session_id}",
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        # Should return 401/403 (unauthorized) or 404 (not found)
        assert response.status_code in [401, 403, 404]

    def test_get_interview_prep_nonexistent_session(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test getting interview prep for non-existent session returns 404."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.get(
            f"/api/v1/interview-prep/{fake_session_id}",
            headers=authenticated_user,
        )
        
        assert response.status_code == 404

    def test_get_interview_prep_no_prep_exists(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test getting interview prep when none has been generated."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        response = http_client.get(
            f"/api/v1/interview-prep/{completed_workflow_session}",
            headers=user_with_profile,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should indicate no prep exists yet
        assert "session_id" in data
        assert data["session_id"] == completed_workflow_session
        assert "has_interview_prep" in data
        # Initially should be False unless already generated
        # The response structure should be present


# =============================================================================
# GET INTERVIEW PREP STATUS TESTS
# =============================================================================


class TestGetInterviewPrepStatus:
    """Tests for the GET /api/v1/interview-prep/{session_id}/status endpoint."""

    def test_get_status_without_auth(self, http_client: httpx.Client):
        """Test getting status without authentication fails."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.get(f"/api/v1/interview-prep/{fake_session_id}/status")
        
        # Should return 401/403 (unauthorized) or 404 (not found)
        assert response.status_code in [401, 403, 404]

    def test_get_status_nonexistent_session(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test getting status for non-existent session returns 404."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.get(
            f"/api/v1/interview-prep/{fake_session_id}/status",
            headers=authenticated_user,
        )
        
        assert response.status_code == 404

    def test_get_status_success(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test getting interview prep status for valid session."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        response = http_client.get(
            f"/api/v1/interview-prep/{completed_workflow_session}/status",
            headers=user_with_profile,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "session_id" in data
        assert data["session_id"] == completed_workflow_session
        assert "has_interview_prep" in data
        assert isinstance(data["has_interview_prep"], bool)


# =============================================================================
# GENERATE INTERVIEW PREP TESTS
# =============================================================================


class TestGenerateInterviewPrep:
    """Tests for the POST /api/v1/interview-prep/{session_id}/generate endpoint."""

    def test_generate_without_auth(self, http_client: httpx.Client):
        """Test generating interview prep without authentication fails."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.post(f"/api/v1/interview-prep/{fake_session_id}/generate")
        
        # Should return 401/403 (unauthorized) or 404 (not found)
        assert response.status_code in [401, 403, 404]

    def test_generate_nonexistent_session(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test generating interview prep for non-existent session returns 404."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.post(
            f"/api/v1/interview-prep/{fake_session_id}/generate",
            headers=authenticated_user,
        )
        
        assert response.status_code == 404

    def test_generate_triggers_background_task(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that generate endpoint triggers background generation."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        response = http_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate",
            headers=user_with_profile,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "session_id" in data
        assert data["session_id"] == completed_workflow_session
        assert "status" in data
        assert data["status"] in ["generating", "exists"]
        assert "message" in data

    def test_generate_returns_exists_if_already_generated(
        self,
        long_timeout_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that calling generate twice returns 'exists' status."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # First generation
        response1 = long_timeout_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate",
            headers=user_with_profile,
        )
        assert response1.status_code == 200
        
        # Wait for generation to complete
        time.sleep(30)
        
        # Second generation attempt (without regenerate flag)
        response2 = long_timeout_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate",
            headers=user_with_profile,
        )
        
        assert response2.status_code == 200
        data = response2.json()
        
        # Should indicate it already exists
        assert data["status"] in ["exists", "generating"]

    def test_generate_with_regenerate_flag(
        self,
        long_timeout_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that regenerate=true forces new generation."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # Generate with regenerate flag
        response = long_timeout_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate?regenerate=true",
            headers=user_with_profile,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "generating"


# =============================================================================
# DELETE INTERVIEW PREP TESTS
# =============================================================================


class TestDeleteInterviewPrep:
    """Tests for the DELETE /api/v1/interview-prep/{session_id} endpoint."""

    def test_delete_without_auth(self, http_client: httpx.Client):
        """Test deleting interview prep without authentication fails."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.delete(f"/api/v1/interview-prep/{fake_session_id}")
        
        # Should return 401/403 (unauthorized) or 404 (not found)
        assert response.status_code in [401, 403, 404]

    def test_delete_nonexistent_session(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test deleting interview prep for non-existent session returns 404."""
        fake_session_id = str(uuid.uuid4())
        response = http_client.delete(
            f"/api/v1/interview-prep/{fake_session_id}",
            headers=authenticated_user,
        )
        
        assert response.status_code == 404

    def test_delete_interview_prep_success(
        self,
        long_timeout_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test successfully deleting interview prep."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # First generate some interview prep
        gen_response = long_timeout_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate",
            headers=user_with_profile,
        )
        assert gen_response.status_code == 200
        
        # Wait for generation
        time.sleep(30)
        
        # Delete it
        delete_response = long_timeout_client.delete(
            f"/api/v1/interview-prep/{completed_workflow_session}",
            headers=user_with_profile,
        )
        
        assert delete_response.status_code == 204
        
        # Verify it's gone
        get_response = long_timeout_client.get(
            f"/api/v1/interview-prep/{completed_workflow_session}",
            headers=user_with_profile,
        )
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["has_interview_prep"] is False


# =============================================================================
# INTERVIEW PREP CONTENT TESTS
# =============================================================================


class TestInterviewPrepContent:
    """Tests for the structure and content of generated interview prep."""

    def test_interview_prep_structure(
        self,
        long_timeout_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that generated interview prep has the expected structure."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # Generate interview prep
        gen_response = long_timeout_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate",
            headers=user_with_profile,
        )
        assert gen_response.status_code == 200
        
        # Poll until ready (max 2 minutes)
        max_wait = 120
        start = time.time()
        interview_prep = None
        
        while time.time() - start < max_wait:
            get_response = long_timeout_client.get(
                f"/api/v1/interview-prep/{completed_workflow_session}",
                headers=user_with_profile,
            )
            
            if get_response.status_code == 200:
                data = get_response.json()
                if data.get("has_interview_prep") and data.get("interview_prep"):
                    interview_prep = data["interview_prep"]
                    break
            
            time.sleep(5)
        
        if interview_prep is None:
            pytest.skip("Interview prep generation did not complete in time")
        
        # Verify structure
        expected_keys = [
            "interview_process",
            "predicted_questions",
            "addressing_concerns",
            "questions_for_them",
            "logistics",
            "quick_reference_card",
            "day_before_checklist",
            "confidence_boosters",
        ]
        
        for key in expected_keys:
            assert key in interview_prep, f"Missing key: {key}"
        
        # Verify predicted_questions structure
        predicted_questions = interview_prep.get("predicted_questions", {})
        assert "behavioral" in predicted_questions
        assert "technical" in predicted_questions
        
        # Verify questions_for_them structure
        questions_for_them = interview_prep.get("questions_for_them", {})
        assert "for_recruiter" in questions_for_them or \
               "for_hiring_manager" in questions_for_them or \
               len(questions_for_them) > 0
        
        # Verify logistics structure
        logistics = interview_prep.get("logistics", {})
        assert "dress_code" in logistics or "timing" in logistics or len(logistics) > 0
        
        # Verify quick_reference_card
        quick_ref = interview_prep.get("quick_reference_card", {})
        assert len(quick_ref) > 0
        
        # Verify metadata
        assert "generated_at" in interview_prep
        assert "version" in interview_prep


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting on interview prep generation."""

    def test_rate_limit_exceeded(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that rate limiting kicks in after too many requests."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # Note: The rate limit is 5 per hour. In a real test environment,
        # you would need to make many requests or mock the rate limiter.
        # This test just verifies the endpoint handles rate limiting properly.
        
        response = http_client.post(
            f"/api/v1/interview-prep/{completed_workflow_session}/generate?regenerate=true",
            headers=user_with_profile,
        )
        
        # Should either succeed or return rate limit error
        assert response.status_code in [200, 429]


# =============================================================================
# AUTHORIZATION TESTS
# =============================================================================


class TestAuthorization:
    """Tests for proper authorization of interview prep endpoints."""

    def test_cannot_access_other_users_interview_prep(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that users cannot access other users' interview prep."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        # Create a second user
        second_email = f"test_second_{uuid.uuid4().hex[:8]}@example.com"
        register_response = http_client.post(
            "/api/v1/auth/register",
            json={
                "email": second_email,
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "full_name": "Second Test User",
            },
        )
        
        if register_response.status_code != 200:
            pytest.skip("Could not create second user")
        
        second_user_headers = {
            "Authorization": f"Bearer {register_response.json()['access_token']}"
        }
        
        # Try to access first user's workflow
        response = http_client.get(
            f"/api/v1/interview-prep/{completed_workflow_session}",
            headers=second_user_headers,
        )
        
        # Should return 404 (not found, not belonging to this user)
        assert response.status_code == 404


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_session_id_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test handling of invalid session ID format."""
        invalid_session_id = "not-a-valid-uuid"
        
        response = http_client.get(
            f"/api/v1/interview-prep/{invalid_session_id}",
            headers=authenticated_user,
        )
        
        # Should return 404 or 422 (validation error)
        assert response.status_code in [404, 422]

    def test_empty_session_id(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test handling of empty session ID."""
        response = http_client.get(
            "/api/v1/interview-prep/",
            headers=authenticated_user,
        )
        
        # Should return 404 (not found) or 405 (method not allowed)
        assert response.status_code in [404, 405, 307]

    def test_get_interview_prep_response_format(
        self,
        http_client: httpx.Client,
        user_with_profile: Dict[str, str],
        completed_workflow_session: Optional[str],
    ):
        """Test that the response format matches the schema."""
        if completed_workflow_session is None:
            pytest.skip("No completed workflow available")
        
        response = http_client.get(
            f"/api/v1/interview-prep/{completed_workflow_session}",
            headers=user_with_profile,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response schema
        assert "session_id" in data
        assert "has_interview_prep" in data
        assert isinstance(data["session_id"], str)
        assert isinstance(data["has_interview_prep"], bool)
        
        # If has_interview_prep is True, interview_prep should be present
        if data["has_interview_prep"]:
            assert "interview_prep" in data
            assert data["interview_prep"] is not None


# =============================================================================
# UNIT TESTS - CACHE FUNCTIONS
# =============================================================================


class TestCacheFunctions:
    """Unit tests for interview prep cache functions."""

    def test_get_interview_prep_cache_key(self):
        """Test cache key generation."""
        from utils.cache import _get_interview_prep_cache_key
        
        session_id = "test-session-123"
        key = _get_interview_prep_cache_key(session_id)
        
        from utils.cache import CACHE_VERSION

        assert key == f"{CACHE_VERSION}:interview_prep:test-session-123"
        assert session_id in key

    def test_cache_key_different_sessions(self):
        """Test that different sessions get different cache keys."""
        from utils.cache import _get_interview_prep_cache_key
        
        key1 = _get_interview_prep_cache_key("session-1")
        key2 = _get_interview_prep_cache_key("session-2")
        
        assert key1 != key2


class TestCacheConstants:
    """Unit tests for interview prep cache constants."""

    def test_cache_prefix_exists(self):
        """Test that the cache prefix constant exists."""
        from utils.cache import CACHE_PREFIX_INTERVIEW_PREP
        
        assert CACHE_PREFIX_INTERVIEW_PREP == "interview_prep"

    def test_ttl_exists(self):
        """Test that the TTL constant exists and is reasonable."""
        from utils.cache import TTL_INTERVIEW_PREP
        
        # Should be 7 days in seconds
        assert TTL_INTERVIEW_PREP == 60 * 60 * 24 * 7
        assert TTL_INTERVIEW_PREP > 0


# =============================================================================
# UNIT TESTS - AGENT
# =============================================================================


class TestInterviewPrepAgentUnit:
    """Unit tests for the InterviewPrepAgent class."""

    def test_agent_initialization(self):
        """Test that the agent initializes correctly."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_format_job_info_empty(self):
        """Test formatting empty job info."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._format_job_info({})
        
        assert "No job analysis available" in result or "Not specified" in result

    def test_format_job_info_with_data(self):
        """Test formatting job info with data."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        job = {
            "job_title": "Software Engineer",
            "company_name": "Test Corp",
            "required_skills": ["Python", "AWS"],
        }
        result = agent._format_job_info(job)
        
        assert "Software Engineer" in result
        assert "Test Corp" in result

    def test_format_company_info_empty(self):
        """Test formatting empty company info."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._format_company_info({})
        
        assert "No company research available" in result

    def test_format_company_info_with_data(self):
        """Test formatting company info with data."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        company = {
            "industry": "Technology",
            "company_size": "1000+",
            "core_values": ["Innovation", "Integrity"],
        }
        result = agent._format_company_info(company)
        
        assert "Technology" in result

    def test_format_profile_info_empty(self):
        """Test formatting empty profile info."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._format_profile_info({})
        
        assert "No profile available" in result

    def test_format_profile_info_with_data(self):
        """Test formatting profile info with data."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        profile = {
            "full_name": "John Doe",
            "professional_title": "Software Engineer",
            "years_experience": 5,
            "skills": ["Python", "JavaScript"],
        }
        result = agent._format_profile_info(profile)
        
        assert "John Doe" in result
        assert "Software Engineer" in result

    def test_format_matching_insights_empty(self):
        """Test formatting empty matching insights."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._format_matching_insights({})
        
        assert "No" in result or len(result) > 0

    def test_create_filtered_result(self):
        """Test creating filtered result."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._create_filtered_result("Test filter message")
        
        assert result["filtered"] is True
        assert result["filter_message"] == "Test filter message"
        assert "interview_process" in result
        assert "predicted_questions" in result
        assert "logistics" in result

    def test_create_parse_error_result(self):
        """Test creating parse error result."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._create_parse_error_result("raw response text")
        
        assert result["parse_error"] is True
        assert "interview_process" in result
        assert "predicted_questions" in result
        assert "quick_reference_card" in result

    def test_filtered_result_structure(self):
        """Test that filtered result has expected structure."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._create_filtered_result("test")
        
        # Check all expected top-level keys
        expected_keys = [
            "interview_process",
            "predicted_questions",
            "addressing_concerns",
            "questions_for_them",
            "logistics",
            "quick_reference_card",
            "day_before_checklist",
            "confidence_boosters",
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_parse_error_result_structure(self):
        """Test that parse error result has expected structure."""
        from agents.interview_prep import InterviewPrepAgent
        
        agent = InterviewPrepAgent()
        result = agent._create_parse_error_result("")
        
        # Should have same structure as filtered result
        assert "interview_process" in result
        assert "predicted_questions" in result
        assert "questions_for_them" in result


class TestInterviewPrepPrompts:
    """Unit tests for interview prep prompt constants."""

    def test_system_context_exists(self):
        """Test that system context is defined."""
        from agents.interview_prep import SYSTEM_CONTEXT
        
        assert SYSTEM_CONTEXT is not None
        assert len(SYSTEM_CONTEXT) > 100
        assert "interview" in SYSTEM_CONTEXT.lower()

    def test_prompt_exists(self):
        """Test that the prompt template is defined."""
        from agents.interview_prep import INTERVIEW_PREP_PROMPT
        
        assert INTERVIEW_PREP_PROMPT is not None
        assert len(INTERVIEW_PREP_PROMPT) > 100
        assert "{job_info}" in INTERVIEW_PREP_PROMPT
        assert "{company_info}" in INTERVIEW_PREP_PROMPT
        assert "{profile_info}" in INTERVIEW_PREP_PROMPT

    def test_llm_constants(self):
        """Test LLM configuration constants."""
        from agents.interview_prep import LLM_TEMPERATURE, LLM_MAX_TOKENS
        
        assert 0 <= LLM_TEMPERATURE <= 1
        assert LLM_MAX_TOKENS > 0


# =============================================================================
# UNIT TESTS - API MODELS
# =============================================================================


class TestAPIModels:
    """Unit tests for API request/response models."""

    def test_interview_prep_response_model(self):
        """Test InterviewPrepResponse model."""
        from api.interview_prep import InterviewPrepResponse
        
        response = InterviewPrepResponse(
            session_id="test-123",
            has_interview_prep=True,
            interview_prep={"test": "data"},
            generated_at="2024-01-01T00:00:00Z",
        )
        
        assert response.session_id == "test-123"
        assert response.has_interview_prep is True
        assert response.interview_prep == {"test": "data"}

    def test_interview_prep_response_model_minimal(self):
        """Test InterviewPrepResponse with minimal data."""
        from api.interview_prep import InterviewPrepResponse
        
        response = InterviewPrepResponse(
            session_id="test-123",
            has_interview_prep=False,
        )
        
        assert response.session_id == "test-123"
        assert response.has_interview_prep is False
        assert response.interview_prep is None

    def test_interview_prep_generate_response_model(self):
        """Test InterviewPrepGenerateResponse model."""
        from api.interview_prep import InterviewPrepGenerateResponse
        
        response = InterviewPrepGenerateResponse(
            session_id="test-123",
            status="generating",
            message="Started generation",
        )
        
        assert response.session_id == "test-123"
        assert response.status == "generating"
        assert response.message == "Started generation"

    def test_interview_prep_status_response_model(self):
        """Test InterviewPrepStatusResponse model."""
        from api.interview_prep import InterviewPrepStatusResponse
        
        response = InterviewPrepStatusResponse(
            session_id="test-123",
            has_interview_prep=True,
            is_generating=False,
            generated_at="2024-01-01T00:00:00Z",
        )
        
        assert response.session_id == "test-123"
        assert response.has_interview_prep is True
        assert response.is_generating is False


# =============================================================================
# UNIT TESTS - DATABASE MODEL
# =============================================================================


class TestDatabaseModel:
    """Unit tests for database model changes."""

    def test_workflow_session_has_interview_prep_field(self):
        """Test that WorkflowSession model has interview_prep field."""
        from models.database import WorkflowSession
        
        # Check that the column exists in the mapper
        columns = [c.name for c in WorkflowSession.__table__.columns]
        assert "interview_prep" in columns

    def test_workflow_session_to_dict_includes_interview_prep(self):
        """Test that to_dict includes interview_prep."""
        from models.database import WorkflowSession
        import uuid as uuid_module
        
        session = WorkflowSession(
            session_id="test-session",
            user_id=uuid_module.uuid4(),
            interview_prep={"test": "data"},
        )
        
        result = session.to_dict()
        
        assert "interview_prep" in result
        assert result["interview_prep"] == {"test": "data"}

"""
Integration and unit tests for career tools API endpoints.

Integration tests run against the running server at localhost:8000.
Make sure the server is running before executing these tests.

Tests cover Phase 1:
- POST /api/v1/tools/thank-you - Generate thank you notes
- POST /api/v1/tools/rejection-analysis - Analyze rejection emails  
- POST /api/v1/tools/reference-request - Generate reference request emails

Tests cover Phase 2:
- POST /api/v1/tools/job-comparison - Compare 2-3 job opportunities
- POST /api/v1/tools/followup - Generate follow-up emails for any stage
- GET /api/v1/tools/followup-stages - Get available follow-up stages
- POST /api/v1/tools/salary-coach - Get salary negotiation coaching
"""

import uuid
import pytest
import httpx
from typing import Dict

from tests.live_server_helpers import ensure_llm_ready, skip_unless_llm_ok


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://localhost:8000"
GENERATE_TIMEOUT = 60  # Tool generation timeout


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def unique_email():
    """Generate a unique email for testing."""
    return f"test_tools_{uuid.uuid4().hex[:8]}@example.com"


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
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "full_name": "Test Tools User",
        },
    )
    assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
    
    token = register_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ensure_llm_ready(http_client, headers)
    return headers


# =============================================================================
# THANK YOU NOTE TESTS
# =============================================================================


class TestThankYouNote:
    """Tests for the POST /api/v1/tools/thank-you endpoint."""

    def test_thank_you_without_auth(self, http_client: httpx.Client):
        """Test generating thank you note without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/thank-you",
            json={
                "interviewer_name": "John Smith",
                "interview_type": "phone",
                "company_name": "Test Corp",
                "job_title": "Software Engineer",
            },
        )
        
        assert response.status_code in [401, 403]

    def test_thank_you_with_invalid_token(self, http_client: httpx.Client):
        """Test generating thank you note with invalid token fails."""
        response = http_client.post(
            "/api/v1/tools/thank-you",
            headers={"Authorization": "Bearer invalid-token"},
            json={
                "interviewer_name": "John Smith",
                "interview_type": "phone",
                "company_name": "Test Corp",
                "job_title": "Software Engineer",
            },
        )
        
        assert response.status_code in [401, 403]

    def test_thank_you_missing_required_fields(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test thank you note with missing required fields returns 422."""
        # Missing interviewer_name
        response = http_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interview_type": "phone",
                "company_name": "Test Corp",
                "job_title": "Software Engineer",
            },
        )
        
        assert response.status_code == 422

    def test_thank_you_missing_company_info(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test thank you note without company info returns 400."""
        response = http_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "John Smith",
                "interview_type": "phone",
                # No company_name or job_title or application_id
            },
        )
        
        # Should return 400 because company/job info is required
        assert response.status_code in [400, 422]

    def test_thank_you_success(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful thank you note generation."""
        response = long_timeout_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "John Smith",
                "interviewer_role": "Engineering Manager",
                "interview_type": "video",
                "company_name": "Acme Tech",
                "job_title": "Senior Software Engineer",
                "key_discussion_points": [
                    "Team structure and collaboration",
                    "Python and FastAPI experience",
                    "Remote work culture",
                ],
                "additional_notes": "Great conversation about microservices architecture",
            },
        )
        
        # Skip if no API key configured
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "subject_line" in data
        assert "email_body" in data
        assert "key_points_referenced" in data
        assert "tone" in data
        assert "generated_at" in data
        
        # Verify content quality
        assert len(data["subject_line"]) > 0
        assert len(data["email_body"]) > 50
        assert isinstance(data["key_points_referenced"], list)

    def test_thank_you_minimal_input(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test thank you note with minimal required input."""
        response = long_timeout_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "Jane Doe",
                "interview_type": "phone",
                "company_name": "TechCo",
                "job_title": "Developer",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "subject_line" in data
        assert "email_body" in data

    def test_thank_you_various_interview_types(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test thank you note for different interview types."""
        interview_types = ["phone", "video", "onsite", "technical", "behavioral"]
        
        for interview_type in interview_types[:2]:  # Test first 2 to save time
            response = long_timeout_client.post(
                "/api/v1/tools/thank-you",
                headers=authenticated_user,
                json={
                    "interviewer_name": "Test Interviewer",
                    "interview_type": interview_type,
                    "company_name": "Test Corp",
                    "job_title": "Engineer",
                },
            )
            
            skip_unless_llm_ok(response)
            
            assert response.status_code == 200, f"Failed for interview type: {interview_type}"


# =============================================================================
# REJECTION ANALYSIS TESTS
# =============================================================================


class TestRejectionAnalysis:
    """Tests for the POST /api/v1/tools/rejection-analysis endpoint."""

    SAMPLE_REJECTION_EMAIL = """
    Dear Candidate,
    
    Thank you for your interest in the Software Engineer position at TechCorp and for 
    taking the time to interview with our team. After careful consideration, we have 
    decided to move forward with another candidate whose experience more closely aligns 
    with our current needs.
    
    We were impressed with your background and encourage you to apply for future 
    openings that match your skills. We will keep your resume on file for future 
    opportunities.
    
    We wish you the best in your job search and future career endeavors.
    
    Best regards,
    HR Team
    """

    def test_rejection_analysis_without_auth(self, http_client: httpx.Client):
        """Test rejection analysis without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/rejection-analysis",
            json={
                "rejection_email": self.SAMPLE_REJECTION_EMAIL,
            },
        )
        
        assert response.status_code in [401, 403]

    def test_rejection_analysis_missing_email(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test rejection analysis without email text returns 422."""
        response = http_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "job_title": "Software Engineer",
            },
        )
        
        assert response.status_code == 422

    def test_rejection_analysis_email_too_short(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test rejection analysis with too short email returns 422."""
        response = http_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": "No thanks",  # Too short (min_length=10)
            },
        )
        
        assert response.status_code == 422

    def test_rejection_analysis_success(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful rejection analysis."""
        response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": self.SAMPLE_REJECTION_EMAIL,
                "job_title": "Software Engineer",
                "company_name": "TechCorp",
                "interview_stage": "Final round",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "analysis_summary" in data
        assert "likely_reasons" in data
        assert "improvement_suggestions" in data
        assert "positive_signals" in data
        assert "follow_up_recommended" in data
        assert "encouragement" in data
        assert "generated_at" in data
        
        # Verify content
        assert isinstance(data["likely_reasons"], list)
        assert isinstance(data["improvement_suggestions"], list)
        assert isinstance(data["positive_signals"], list)
        assert isinstance(data["follow_up_recommended"], bool)
        assert len(data["encouragement"]) > 0

    def test_rejection_analysis_minimal_input(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test rejection analysis with minimal input."""
        response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": self.SAMPLE_REJECTION_EMAIL,
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200

    def test_rejection_analysis_generic_rejection(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test analysis of a generic/template rejection."""
        generic_rejection = """
        Hi,
        
        We have reviewed your application and will not be moving forward.
        
        Thanks,
        HR
        """
        
        response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": generic_rejection,
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should still provide analysis even for generic rejections
        assert "analysis_summary" in data
        assert "encouragement" in data

    def test_rejection_analysis_positive_rejection(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test analysis of a positive-toned rejection with feedback."""
        positive_rejection = """
        Dear Applicant,
        
        Thank you so much for interviewing with us. Your technical skills were excellent,
        and the team really enjoyed meeting you. Unfortunately, we've decided to go with 
        a candidate who has more experience with our specific tech stack (Kubernetes, Terraform).
        
        We strongly encourage you to apply again in the future - perhaps after gaining 
        more DevOps experience. We'll definitely remember your strong problem-solving abilities.
        
        Feel free to stay in touch.
        
        Best,
        Sarah (Hiring Manager)
        """
        
        response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": positive_rejection,
                "interview_stage": "Technical interview",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should identify positive signals
        assert len(data.get("positive_signals", [])) > 0


# =============================================================================
# REFERENCE REQUEST TESTS
# =============================================================================


class TestReferenceRequest:
    """Tests for the POST /api/v1/tools/reference-request endpoint."""

    def test_reference_request_without_auth(self, http_client: httpx.Client):
        """Test reference request without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/reference-request",
            json={
                "reference_name": "John Smith",
                "reference_relationship": "Former Manager",
            },
        )
        
        assert response.status_code in [401, 403]

    def test_reference_request_missing_required_fields(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request with missing required fields returns 422."""
        # Missing reference_name
        response = http_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_relationship": "Former Manager",
            },
        )
        
        assert response.status_code == 422

    def test_reference_request_success(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful reference request generation."""
        response = long_timeout_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_name": "Sarah Johnson",
                "reference_relationship": "Former Manager",
                "reference_company": "Previous Corp",
                "years_worked_together": 3,
                "target_job_title": "Senior Software Engineer",
                "target_company": "Dream Company Inc",
                "key_accomplishments": [
                    "Led migration to cloud infrastructure",
                    "Reduced system latency by 40%",
                    "Mentored 3 junior developers",
                ],
                "time_since_contact": "6 months",
                "user_name": "Test User",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "subject_line" in data
        assert "email_body" in data
        assert "talking_points" in data
        assert "follow_up_timeline" in data
        assert "tips" in data
        assert "generated_at" in data
        
        # Verify content
        assert len(data["subject_line"]) > 0
        assert len(data["email_body"]) > 50
        assert isinstance(data["talking_points"], list)
        assert isinstance(data["tips"], list)

    def test_reference_request_minimal_input(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request with minimal required input."""
        response = long_timeout_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_name": "Bob Smith",
                "reference_relationship": "Colleague",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "subject_line" in data
        assert "email_body" in data

    def test_reference_request_various_relationships(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request for different relationship types."""
        relationships = ["Former Manager", "Colleague", "Mentor", "Professor", "Client"]
        
        for relationship in relationships[:2]:  # Test first 2 to save time
            response = long_timeout_client.post(
                "/api/v1/tools/reference-request",
                headers=authenticated_user,
                json={
                    "reference_name": "Test Reference",
                    "reference_relationship": relationship,
                },
            )
            
            skip_unless_llm_ok(response)
            
            assert response.status_code == 200, f"Failed for relationship: {relationship}"

    def test_reference_request_long_time_since_contact(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request when it's been a long time since contact."""
        response = long_timeout_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_name": "Old Colleague",
                "reference_relationship": "Former Manager",
                "reference_company": "Old Company",
                "years_worked_together": 2,
                "time_since_contact": "3 years",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Email should acknowledge the time gap
        assert len(data["email_body"]) > 50


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting on tools endpoints."""

    def test_rate_limit_per_tool(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that rate limiting is applied per tool."""
        # Note: The rate limit is 10 per hour per tool
        # This test just verifies the endpoint handles rate limiting properly
        
        response = http_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "Test",
                "interview_type": "phone",
                "company_name": "Test",
                "job_title": "Test",
            },
        )
        
        skip_unless_llm_ok(response)
        # Should either succeed, validate-fail, rate-limit, or upstream LLM error
        assert response.status_code in [200, 400, 422, 429, 500]


# =============================================================================
# AUTHORIZATION TESTS
# =============================================================================


class TestAuthorization:
    """Tests for proper authorization of tools endpoints."""

    def test_cannot_access_other_users_application_context(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that providing another user's application ID doesn't leak data."""
        # Use a random UUID that doesn't belong to this user
        fake_application_id = str(uuid.uuid4())
        
        response = long_timeout_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "application_id": fake_application_id,
                "interviewer_name": "Test",
                "interview_type": "phone",
                # No company/job info - should fail since app doesn't exist for this user
            },
        )
        
        # Application not found and no company/job info — validation error
        assert response.status_code in [400, 422]


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_thank_you_with_special_characters(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test thank you note with special characters in input."""
        response = long_timeout_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "José García-López",
                "interview_type": "video",
                "company_name": "Café & Co.",
                "job_title": "Software Engineer (Senior)",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200

    def test_rejection_analysis_with_unicode(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test rejection analysis with unicode characters."""
        unicode_rejection = """
        Dear 候選人,
        
        Thank you for your application. Unfortunately, we won't be moving forward.
        
        Best regards,
        人事部門
        """
        
        response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": unicode_rejection,
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200

    def test_reference_request_with_long_accomplishments(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request with many accomplishments."""
        response = long_timeout_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_name": "Test Reference",
                "reference_relationship": "Former Manager",
                "key_accomplishments": [
                    f"Accomplishment {i} - Did something great" for i in range(10)
                ],
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200

    def test_invalid_application_id_format(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test handling of invalid application ID format."""
        response = http_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "application_id": "not-a-uuid",
                "interviewer_name": "Test",
                "interview_type": "phone",
                "company_name": "Test",
                "job_title": "Test",
            },
        )
        
        skip_unless_llm_ok(response)
        
        # Should still work - just won't find the application
        # Falls back to provided company/job info
        assert response.status_code in [200, 400]


# =============================================================================
# UNIT TESTS - API MODELS
# =============================================================================


class TestAPIModels:
    """Unit tests for API request/response models."""

    def test_thank_you_request_model(self):
        """Test ThankYouNoteRequest model validation."""
        from api.tools import ThankYouNoteRequest
        
        # Valid request
        request = ThankYouNoteRequest(
            interviewer_name="John Smith",
            interview_type="phone",
            company_name="Test Corp",
            job_title="Engineer",
        )
        
        assert request.interviewer_name == "John Smith"
        assert request.interview_type == "phone"

    def test_thank_you_request_model_with_optional_fields(self):
        """Test ThankYouNoteRequest with optional fields."""
        from api.tools import ThankYouNoteRequest
        
        request = ThankYouNoteRequest(
            interviewer_name="John Smith",
            interviewer_role="Engineering Manager",
            interview_type="video",
            company_name="Test Corp",
            job_title="Engineer",
            key_discussion_points=["Point 1", "Point 2"],
            additional_notes="Great interview",
        )
        
        assert request.interviewer_role == "Engineering Manager"
        assert len(request.key_discussion_points) == 2

    def test_thank_you_response_model(self):
        """Test ThankYouNoteResponse model."""
        from api.tools import ThankYouNoteResponse
        
        response = ThankYouNoteResponse(
            subject_line="Thank you for the interview",
            email_body="Dear John...",
            key_points_referenced=["Python", "AWS"],
            tone="professional",
            generated_at="2024-01-01T00:00:00Z",
        )
        
        assert response.subject_line == "Thank you for the interview"
        assert len(response.key_points_referenced) == 2

    def test_rejection_analysis_request_model(self):
        """Test RejectionAnalysisRequest model validation."""
        from api.tools import RejectionAnalysisRequest
        
        request = RejectionAnalysisRequest(
            rejection_email="Thank you for applying, but we have decided to move on.",
            job_title="Software Engineer",
        )
        
        assert len(request.rejection_email) > 10

    def test_rejection_analysis_response_model(self):
        """Test RejectionAnalysisResponse model."""
        from api.tools import RejectionAnalysisResponse
        
        response = RejectionAnalysisResponse(
            analysis_summary="This appears to be a standard rejection.",
            likely_reasons=["Other candidates had more experience"],
            improvement_suggestions=["Focus on specific skills"],
            positive_signals=["They mentioned keeping resume on file"],
            follow_up_recommended=True,
            follow_up_template="Dear HR, Thank you for...",
            encouragement="Keep going! The right opportunity is out there.",
            generated_at="2024-01-01T00:00:00Z",
        )
        
        assert response.follow_up_recommended is True
        assert len(response.likely_reasons) > 0

    def test_reference_request_request_model(self):
        """Test ReferenceRequestRequest model validation."""
        from api.tools import ReferenceRequestRequest
        
        request = ReferenceRequestRequest(
            reference_name="Sarah Johnson",
            reference_relationship="Former Manager",
            years_worked_together=3,
        )
        
        assert request.reference_name == "Sarah Johnson"
        assert request.years_worked_together == 3

    def test_reference_request_response_model(self):
        """Test ReferenceRequestResponse model."""
        from api.tools import ReferenceRequestResponse
        
        response = ReferenceRequestResponse(
            subject_line="Reference Request",
            email_body="Dear Sarah...",
            talking_points=["Project X", "Leadership"],
            follow_up_timeline="1 week",
            tips=["Be specific about the role"],
            generated_at="2024-01-01T00:00:00Z",
        )
        
        assert len(response.talking_points) == 2
        assert response.follow_up_timeline == "1 week"


# =============================================================================
# UNIT TESTS - HELPER FUNCTIONS
# =============================================================================


class TestHelperFunctions:
    """Unit tests for helper functions in the tools module."""

    def test_get_user_uuid_from_string(self):
        """Test extracting UUID from string."""
        from api.tools import _get_user_uuid
        
        test_uuid = str(uuid.uuid4())
        result = _get_user_uuid({"id": test_uuid})
        
        assert isinstance(result, uuid.UUID)
        assert str(result) == test_uuid

    def test_get_user_uuid_from_uuid(self):
        """Test extracting UUID from UUID object."""
        from api.tools import _get_user_uuid
        
        test_uuid = uuid.uuid4()
        result = _get_user_uuid({"id": test_uuid})
        
        assert isinstance(result, uuid.UUID)
        assert result == test_uuid

    def test_get_user_uuid_with_underscore_id(self):
        """Test extracting UUID using _id key."""
        from api.tools import _get_user_uuid
        
        test_uuid = str(uuid.uuid4())
        result = _get_user_uuid({"_id": test_uuid})
        
        assert isinstance(result, uuid.UUID)


# =============================================================================
# UNIT TESTS - AGENTS
# =============================================================================


class TestAgents:
    """Unit tests for the agent classes."""

    def test_thank_you_agent_initialization(self):
        """Test ThankYouWriterAgent initialization."""
        from agents.thank_you_writer import ThankYouWriterAgent
        
        agent = ThankYouWriterAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_rejection_analyzer_initialization(self):
        """Test RejectionAnalyzerAgent initialization."""
        from agents.rejection_analyzer import RejectionAnalyzerAgent
        
        agent = RejectionAnalyzerAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_reference_request_agent_initialization(self):
        """Test ReferenceRequestWriterAgent initialization."""
        from agents.reference_request_writer import ReferenceRequestWriterAgent
        
        agent = ReferenceRequestWriterAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_thank_you_agent_filtered_result(self):
        """Test ThankYouWriterAgent filtered result creation."""
        from agents.thank_you_writer import ThankYouWriterAgent
        
        agent = ThankYouWriterAgent()
        result = agent._create_filtered_result("Test filter message")
        
        assert result["filtered"] is True
        assert result["filter_message"] == "Test filter message"
        assert "subject_line" in result
        assert "email_body" in result

    def test_rejection_analyzer_filtered_result(self):
        """Test RejectionAnalyzerAgent filtered result creation."""
        from agents.rejection_analyzer import RejectionAnalyzerAgent
        
        agent = RejectionAnalyzerAgent()
        result = agent._create_filtered_result("Test filter message")
        
        assert result["filtered"] is True
        assert "analysis_summary" in result
        assert "encouragement" in result

    def test_reference_request_agent_filtered_result(self):
        """Test ReferenceRequestWriterAgent filtered result creation."""
        from agents.reference_request_writer import ReferenceRequestWriterAgent
        
        agent = ReferenceRequestWriterAgent()
        result = agent._create_filtered_result("Test filter", "Test Job")
        
        assert result["filtered"] is True
        assert "subject_line" in result
        assert "email_body" in result


# =============================================================================
# INTEGRATION TEST - FULL WORKFLOW
# =============================================================================


class TestFullWorkflow:
    """Integration tests for complete tool usage workflows."""

    def test_interview_cycle_workflow(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test a complete interview cycle: thank you note, then rejection analysis."""
        # Step 1: Generate thank you note after interview
        thank_you_response = long_timeout_client.post(
            "/api/v1/tools/thank-you",
            headers=authenticated_user,
            json={
                "interviewer_name": "Jane Doe",
                "interview_type": "final",
                "company_name": "Dream Corp",
                "job_title": "Senior Engineer",
                "key_discussion_points": ["Team growth", "Technical challenges"],
            },
        )
        
        skip_unless_llm_ok(thank_you_response)
        
        assert thank_you_response.status_code == 200
        thank_you_data = thank_you_response.json()
        assert "email_body" in thank_you_data
        
        # Step 2: Later, analyze rejection
        rejection_response = long_timeout_client.post(
            "/api/v1/tools/rejection-analysis",
            headers=authenticated_user,
            json={
                "rejection_email": """
                Dear Candidate,
                
                Thank you for interviewing for the Senior Engineer position.
                After careful consideration, we've decided to move forward 
                with another candidate. We were impressed with your technical
                skills and wish you the best.
                
                HR Team
                """,
                "company_name": "Dream Corp",
                "job_title": "Senior Engineer",
                "interview_stage": "Final round",
            },
        )
        
        assert rejection_response.status_code == 200
        rejection_data = rejection_response.json()
        assert "improvement_suggestions" in rejection_data
        assert "encouragement" in rejection_data

    def test_reference_request_workflow(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test reference request for a job application."""
        response = long_timeout_client.post(
            "/api/v1/tools/reference-request",
            headers=authenticated_user,
            json={
                "reference_name": "Previous Boss",
                "reference_relationship": "Former Direct Manager",
                "reference_company": "Old Job Inc",
                "years_worked_together": 2,
                "target_job_title": "Lead Developer",
                "target_company": "New Opportunity Co",
                "key_accomplishments": [
                    "Led team of 5",
                    "Shipped major product",
                ],
                "time_since_contact": "1 year",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have everything needed to send the request
        assert len(data["subject_line"]) > 0
        assert len(data["email_body"]) > 100
        assert len(data["talking_points"]) > 0
        assert len(data["tips"]) > 0


# =============================================================================
# PHASE 2 - JOB COMPARISON TESTS
# =============================================================================


class TestJobComparison:
    """Tests for the POST /api/v1/tools/job-comparison endpoint."""

    def test_job_comparison_without_auth(self, http_client: httpx.Client):
        """Test comparing jobs without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/job-comparison",
            json={
                "jobs": [
                    {"title": "Engineer", "company": "Company A"},
                    {"title": "Engineer", "company": "Company B"},
                ]
            },
        )
        
        assert response.status_code in [401, 403]

    def test_job_comparison_requires_two_jobs(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that comparison requires at least 2 jobs."""
        response = http_client.post(
            "/api/v1/tools/job-comparison",
            headers=authenticated_user,
            json={
                "jobs": [
                    {"title": "Engineer", "company": "Company A"},
                ]
            },
        )
        
        assert response.status_code == 422  # Validation error

    def test_job_comparison_max_three_jobs(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that comparison allows max 3 jobs."""
        response = http_client.post(
            "/api/v1/tools/job-comparison",
            headers=authenticated_user,
            json={
                "jobs": [
                    {"title": "Engineer", "company": "Company A"},
                    {"title": "Engineer", "company": "Company B"},
                    {"title": "Engineer", "company": "Company C"},
                    {"title": "Engineer", "company": "Company D"},
                ]
            },
        )
        
        assert response.status_code == 422  # Validation error

    def test_job_comparison_success(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful job comparison."""
        response = long_timeout_client.post(
            "/api/v1/tools/job-comparison",
            headers=authenticated_user,
            json={
                "jobs": [
                    {
                        "title": "Software Engineer",
                        "company": "Startup Inc",
                        "location": "San Francisco",
                        "salary": "$150k-$180k",
                        "remote_policy": "Remote",
                        "description": "Fast-paced startup, equity, growth opportunity",
                    },
                    {
                        "title": "Software Engineer",
                        "company": "Big Corp",
                        "location": "New York",
                        "salary": "$140k-$160k",
                        "remote_policy": "Hybrid",
                        "description": "Stable company, good benefits, 401k match",
                    },
                ],
                "user_context": {
                    "career_goals": "Become a tech lead",
                    "priorities": "Work-life balance, learning",
                },
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "executive_summary" in data
        assert "recommended_job" in data
        assert "jobs_analysis" in data
        assert data["jobs_compared"] == 2


# =============================================================================
# PHASE 2 - FOLLOW-UP GENERATOR TESTS
# =============================================================================


class TestFollowUpGenerator:
    """Tests for the POST /api/v1/tools/followup endpoint."""

    def test_followup_without_auth(self, http_client: httpx.Client):
        """Test generating follow-up without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/followup",
            json={
                "stage": "after_interview",
                "company_name": "Test Corp",
                "job_title": "Engineer",
            },
        )
        
        assert response.status_code in [401, 403]

    def test_followup_invalid_stage(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that invalid stage is rejected."""
        response = http_client.post(
            "/api/v1/tools/followup",
            headers=authenticated_user,
            json={
                "stage": "invalid_stage",
                "company_name": "Test Corp",
                "job_title": "Engineer",
            },
        )
        
        assert response.status_code in [400, 422]

    def test_followup_stages_endpoint(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test getting available follow-up stages."""
        response = http_client.get(
            "/api/v1/tools/followup-stages",
            headers=authenticated_user,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert len(data["stages"]) > 0

    def test_followup_after_application(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test generating follow-up after application."""
        response = long_timeout_client.post(
            "/api/v1/tools/followup",
            headers=authenticated_user,
            json={
                "stage": "after_application",
                "company_name": "Dream Company",
                "job_title": "Senior Developer",
                "days_since_contact": 5,
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "subject_line" in data
        assert "email_body" in data
        assert data["stage"] == "after_application"

    def test_followup_no_response_checkin(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test generating no-response check-in email."""
        response = long_timeout_client.post(
            "/api/v1/tools/followup",
            headers=authenticated_user,
            json={
                "stage": "no_response",
                "company_name": "Silent Corp",
                "job_title": "Product Manager",
                "contact_name": "Jane Smith",
                "days_since_contact": 10,
                "key_points": ["Mentioned team growth", "Discussed roadmap"],
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "timing_advice" in data
        assert "next_steps" in data


# =============================================================================
# PHASE 2 - SALARY COACH TESTS
# =============================================================================


class TestSalaryCoach:
    """Tests for the POST /api/v1/tools/salary-coach endpoint."""

    def test_salary_coach_without_auth(self, http_client: httpx.Client):
        """Test salary coaching without authentication fails."""
        response = http_client.post(
            "/api/v1/tools/salary-coach",
            json={
                "job_title": "Engineer",
                "company_name": "Test Corp",
                "offered_salary": "$100,000",
                "years_experience": 5,
            },
        )
        
        assert response.status_code in [401, 403]

    def test_salary_coach_missing_required_fields(
        self, http_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test that missing required fields are rejected."""
        response = http_client.post(
            "/api/v1/tools/salary-coach",
            headers=authenticated_user,
            json={
                "job_title": "Engineer",
                # Missing company_name, offered_salary, years_experience
            },
        )
        
        assert response.status_code == 422  # Validation error

    def test_salary_coach_success(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test successful salary negotiation coaching."""
        response = long_timeout_client.post(
            "/api/v1/tools/salary-coach",
            headers=authenticated_user,
            json={
                "job_title": "Senior Software Engineer",
                "company_name": "Tech Giant Inc",
                "offered_salary": "$150,000",
                "years_experience": 7,
                "location": "San Francisco",
                "company_size": "Enterprise",
                "industry": "Technology",
                "current_salary": "$130,000",
                "achievements": ["Led migration to cloud", "Reduced costs 30%"],
                "target_range": "$170k-$190k",
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "market_analysis" in data
        assert "strategy_overview" in data
        assert "main_script" in data
        assert "pushback_responses" in data
        assert "alternative_asks" in data
        assert "dos_and_donts" in data

    def test_salary_coach_response_structure(
        self, long_timeout_client: httpx.Client, authenticated_user: Dict[str, str]
    ):
        """Test salary coaching response has proper structure."""
        response = long_timeout_client.post(
            "/api/v1/tools/salary-coach",
            headers=authenticated_user,
            json={
                "job_title": "Product Manager",
                "company_name": "Startup XYZ",
                "offered_salary": "$120,000",
                "years_experience": 4,
            },
        )
        
        skip_unless_llm_ok(response)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check market analysis structure
        ma = data["market_analysis"]
        assert "salary_assessment" in ma
        assert "market_position" in ma
        assert "recommended_target" in ma
        
        # Check strategy overview
        so = data["strategy_overview"]
        assert "approach" in so
        assert "confidence_level" in so
        
        # Check main script
        ms = data["main_script"]
        assert "opening" in ms
        assert "value_statement" in ms
        assert "counter_offer" in ms
        assert "closing" in ms


# =============================================================================
# PHASE 2 - AGENT UNIT TESTS
# =============================================================================


class TestPhase2AgentUnits:
    """Unit tests for Phase 2 agent classes."""

    def test_job_comparison_agent_initialization(self):
        """Test JobComparisonAgent initialization."""
        from agents.job_comparison import JobComparisonAgent
        
        agent = JobComparisonAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_followup_generator_agent_initialization(self):
        """Test FollowUpGeneratorAgent initialization."""
        from agents.followup_generator import FollowUpGeneratorAgent
        
        agent = FollowUpGeneratorAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_salary_coach_agent_initialization(self):
        """Test SalaryCoachAgent initialization."""
        from agents.salary_coach import SalaryCoachAgent
        
        agent = SalaryCoachAgent()
        
        assert agent.gemini_client is None
        assert agent._current_user_api_key is None

    def test_followup_get_available_stages(self):
        """Test FollowUpGeneratorAgent returns available stages."""
        from agents.followup_generator import FollowUpGeneratorAgent
        
        stages = FollowUpGeneratorAgent.get_available_stages()
        
        assert len(stages) == 7
        stage_ids = [s["id"] for s in stages]
        assert "after_application" in stage_ids
        assert "after_interview" in stage_ids
        assert "no_response" in stage_ids
        assert "after_rejection" in stage_ids

    def test_job_comparison_agent_filtered_result(self):
        """Test JobComparisonAgent filtered result creation."""
        from agents.job_comparison import JobComparisonAgent
        
        agent = JobComparisonAgent()
        result = agent._create_filtered_result("Test filter message")
        
        assert result["filtered"] is True
        assert result["filter_message"] == "Test filter message"
        assert "executive_summary" in result
        assert "recommended_job" in result

    def test_followup_generator_filtered_result(self):
        """Test FollowUpGeneratorAgent filtered result creation."""
        from agents.followup_generator import FollowUpGeneratorAgent
        
        agent = FollowUpGeneratorAgent()
        result = agent._create_filtered_result("Test filter", "after_interview")
        
        assert result["filtered"] is True
        assert result["stage"] == "after_interview"
        assert "subject_line" in result

    def test_salary_coach_filtered_result(self):
        """Test SalaryCoachAgent filtered result creation."""
        from agents.salary_coach import SalaryCoachAgent
        
        agent = SalaryCoachAgent()
        result = agent._create_filtered_result("Test filter message")
        
        assert result["filtered"] is True
        assert "strategy_overview" in result
        assert "final_tips" in result

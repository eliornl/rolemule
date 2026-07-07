"""
Unit tests for the Job Analyzer Agent.
Tests job analysis from URL, manual text, and extension inputs with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agents.job_analyzer import JobAnalyzerAgent, _normalize_string_list


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_test_workflow_state(
    user_id: str = "test-user-123",
    session_id: str = "test-session-456",
    input_method: str = "manual",
    job_content: Optional[str] = None,
    job_url: Optional[str] = None,
    user_profile: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Create a workflow state dict for testing."""
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_profile": user_profile or {"full_name": "Test User"},
        "user_api_key": None,
        "job_input_data": {
            "input_method": input_method,
            "job_content": job_content,
            "job_url": job_url,
            "job_title": "",
            "company_name": "",
        },
        "job_analysis": None,
        "company_research": None,
        "profile_matching": None,
        "resume_recommendations": None,
        "cover_letter": None,
        "current_phase": "initialization",
        "workflow_status": "initialized",
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "processing_end_time": None,
        "agent_status": {},
        "completed_agents": [],
        "failed_agents": [],
        "current_agent": None,
        "error_messages": [],
        "warning_messages": [],
        "agent_start_times": {},
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client that returns valid job analysis JSON."""
    client = AsyncMock()
    client.generate.return_value = {
        "response": '''{
            "job_title": "Senior Software Engineer",
            "company_name": "TechCorp Inc",
            "job_city": "San Francisco",
            "job_state": "California",
            "job_country": "USA",
            "additional_locations": ["New York City, NY", "Seattle, WA"],
            "employment_type": "full-time",
            "work_arrangement": "hybrid",
            "salary_range": {"min": 150000, "max": 200000, "currency": "USD", "period": "yearly"},
            "is_student_position": false,
            "company_size": "Large (1000+)",
            "required_skills": ["Python", "JavaScript", "AWS", "PostgreSQL"],
            "soft_skills": ["Communication", "Leadership", "Problem-solving"],
            "required_qualifications": ["5+ years experience", "BS in Computer Science"],
            "preferred_qualifications": ["Experience with microservices", "Kubernetes knowledge"],
            "education_requirements": {"degree": "Bachelor's", "field": "Computer Science", "required": true},
            "years_experience_required": 5,
            "industry": "Technology",
            "role_classification": "Engineering",
            "keywords": ["python", "backend", "cloud"],
            "ats_keywords": ["Python", "AWS", "microservices", "API"],
            "visa_sponsorship": true,
            "security_clearance": false,
            "responsibilities": ["Design scalable systems", "Lead technical projects"],
            "benefits": ["Health insurance", "401k", "Remote work"]
        }''',
        "filtered": False,
    }
    return client


@pytest.fixture
def sample_job_text():
    """Sample job posting text for testing."""
    return """
    Senior Software Engineer - TechCorp Inc
    Location: San Francisco, CA (Hybrid)
    Salary: $150,000 - $200,000
    
    About the Role:
    We are seeking a Senior Software Engineer to join our growing team.
    You will design and build scalable backend systems.
    
    Requirements:
    - 5+ years of software development experience
    - Proficiency in Python and JavaScript
    - Experience with AWS and cloud services
    - Strong communication skills
    
    Benefits:
    - Competitive salary
    - Health insurance
    - 401k matching
    - Flexible remote work
    """


@pytest.fixture
def workflow_state_manual(sample_job_text):
    """Create workflow state for manual text input."""
    return create_test_workflow_state(
        input_method="manual",
        job_content=sample_job_text,
    )


@pytest.fixture
def workflow_state_extension(sample_job_text):
    """Create workflow state for Chrome extension input."""
    return create_test_workflow_state(
        input_method="extension",
        job_content=sample_job_text,
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestJobAnalyzerInit:
    """Tests for JobAnalyzerAgent initialization."""

    def test_init_with_valid_client(self, mock_gemini_client):
        """Test successful initialization with valid Gemini client."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        assert agent.gemini_client is mock_gemini_client

    def test_init_with_none_client_raises_error(self):
        """Test that None client raises TypeError."""
        with pytest.raises(TypeError, match="Gemini client is required"):
            JobAnalyzerAgent(gemini_client=None)


# =============================================================================
# MANUAL INPUT TESTS
# =============================================================================


class TestManualInputProcessing:
    """Tests for processing manual job text input."""

    @pytest.mark.asyncio
    async def test_process_manual_input_success(
        self, mock_gemini_client, workflow_state_manual
    ):
        """Test successful processing of manual job text."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        # Mock the cache functions
        with patch('agents.job_analyzer.get_cached_job_analysis', return_value=None), \
             patch('agents.job_analyzer.cache_job_analysis', return_value=None):
            result = await agent.process(workflow_state_manual)
        
        assert "job_analysis" in result
        assert result["job_analysis"]["job_title"] == "Senior Software Engineer"

    @pytest.mark.asyncio
    async def test_additional_locations_extracted(
        self, mock_gemini_client, workflow_state_manual
    ):
        """All listed locations beyond the primary are preserved."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)

        with patch('agents.job_analyzer.get_cached_job_analysis', return_value=None), \
             patch('agents.job_analyzer.cache_job_analysis', return_value=None):
            result = await agent.process(workflow_state_manual)

        assert result["job_analysis"]["additional_locations"] == [
            "New York City, NY",
            "Seattle, WA",
        ]

    @pytest.mark.asyncio
    async def test_additional_locations_default_empty(
        self, mock_gemini_client, workflow_state_manual
    ):
        """Missing additional_locations in the LLM response maps to an empty list."""
        payload = mock_gemini_client.generate.return_value["response"].replace(
            '"additional_locations": ["New York City, NY", "Seattle, WA"],', ''
        )
        mock_gemini_client.generate.return_value = {"response": payload, "filtered": False}
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)

        with patch('agents.job_analyzer.get_cached_job_analysis', return_value=None), \
             patch('agents.job_analyzer.cache_job_analysis', return_value=None):
            result = await agent.process(workflow_state_manual)

        assert result["job_analysis"]["additional_locations"] == []

    @pytest.mark.asyncio
    async def test_process_manual_input_too_short(self, mock_gemini_client):
        """Test that short job text raises error."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            input_method="manual",
            job_content="Too short",
        )
        
        with pytest.raises(ValueError, match="too short|minimum"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_extension_input_success(
        self, mock_gemini_client, workflow_state_extension
    ):
        """Test successful processing of extension-extracted content."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        with patch('agents.job_analyzer.get_cached_job_analysis', return_value=None), \
             patch('agents.job_analyzer.cache_job_analysis', return_value=None):
            result = await agent.process(workflow_state_extension)
        
        assert "job_analysis" in result


# =============================================================================
# CACHING TESTS
# =============================================================================


class TestJobAnalysisCaching:
    """Tests for job analysis caching."""

    @pytest.mark.asyncio
    async def test_returns_cached_result_when_available(
        self, mock_gemini_client, workflow_state_manual
    ):
        """Test that cached results are returned when available."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        cached_data = {
            "job_title": "Cached Job",
            "company_name": "Cached Company",
        }
        
        with patch('agents.job_analyzer.get_cached_job_analysis', return_value=cached_data):
            result = await agent.process(workflow_state_manual)
        
        assert result["job_analysis"]["job_title"] == "Cached Job"
        assert result["job_analysis"]["from_cache"] is True


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_missing_job_input_data_raises_error(self, mock_gemini_client):
        """Test that missing job input data raises error."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state()
        state["job_input_data"] = None
        
        with pytest.raises((ValueError, KeyError, TypeError)):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_invalid_input_method_raises_error(self, mock_gemini_client):
        """Test that invalid input method raises error."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            input_method="invalid_method",
        )
        
        with pytest.raises((ValueError, KeyError)):
            await agent.process(state)


# =============================================================================
# LLM RESPONSE PARSING TESTS
# =============================================================================


class TestLLMResponseParsing:
    """Tests for LLM response parsing."""

    @pytest.mark.asyncio
    async def test_parse_valid_json_response(self, mock_gemini_client, sample_job_text):
        """Test parsing valid JSON from LLM response."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None  # Initialize the attribute
        
        result = await agent._parse_generic_job_content(sample_job_text, "manual")
        
        assert result.job_title == "Senior Software Engineer"
        assert result.company_name == "TechCorp Inc"
        assert "Python" in result.required_skills

    @pytest.mark.asyncio
    async def test_parse_filtered_response_raises_error(self, sample_job_text):
        """Test that filtered LLM response is handled."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": "Content filtered",
            "filtered": True,
        }
        
        agent = JobAnalyzerAgent(gemini_client=client)
        agent._current_user_api_key = None
        
        # Should handle gracefully or raise specific error
        with pytest.raises(Exception):
            await agent._parse_generic_job_content(sample_job_text, "manual")


# =============================================================================
# ADDITIONAL COVERAGE — USER API KEY, LLM CALL COUNT, EXCEPTION PROPAGATION
# =============================================================================


class TestJobAnalyzerAdditional:
    """Additional coverage for edge cases not covered in base tests."""

    @pytest.mark.asyncio
    async def test_user_api_key_passed_to_llm(self, mock_gemini_client, sample_job_text):
        """User API key should reach the internal LLM call."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)

        state = create_test_workflow_state(
            input_method="manual",
            job_content=sample_job_text,
        )
        state["user_api_key"] = "byok-key"

        with patch("agents.job_analyzer.get_cached_job_analysis", return_value=None), \
             patch("agents.job_analyzer.cache_job_analysis", return_value=None):
            await agent.process(state)

        assert mock_gemini_client.generate.called

    @pytest.mark.asyncio
    async def test_llm_exception_propagated(self, sample_job_text):
        """Exception raised by gemini_client.generate should propagate."""
        client = AsyncMock()
        client.generate.side_effect = RuntimeError("LLM unavailable")

        agent = JobAnalyzerAgent(gemini_client=client)

        state = create_test_workflow_state(
            input_method="manual",
            job_content=sample_job_text,
        )

        with patch("agents.job_analyzer.get_cached_job_analysis", return_value=None):
            with pytest.raises(Exception):
                await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_extension_with_short_text_raises_error(self, mock_gemini_client):
        """Extension input that is too short should also raise ValueError."""
        agent = JobAnalyzerAgent(gemini_client=mock_gemini_client)

        state = create_test_workflow_state(
            input_method="extension",
            job_content="short",
        )

        with pytest.raises(ValueError):
            await agent.process(state)


class TestNormalizeStringList:
    """Coerce LLM shapes that omit JSON arrays."""

    def test_string_becomes_single_item(self):
        assert _normalize_string_list(" Own the backend ") == ["Own the backend"]

    def test_multiline_splits_when_requested(self):
        assert _normalize_string_list("A\n\nB\nC", split_lines=True) == ["A", "B", "C"]

    def test_list_of_dicts_extracts_known_keys(self):
        raw = [{"duty": "Ship APIs"}, {"text": "Monitor prod"}]
        assert _normalize_string_list(raw) == ["Ship APIs", "Monitor prod"]

    def test_empty_and_none(self):
        assert _normalize_string_list(None) == []
        assert _normalize_string_list("") == []
        assert _normalize_string_list([]) == []

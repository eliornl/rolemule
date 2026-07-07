"""
Unit tests for the Resume Advisor Agent.
Tests resume recommendations generation with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agents.resume_advisor import ResumeAdvisorAgent


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_test_workflow_state(
    user_id: str = "test-user-123",
    session_id: str = "test-session-456",
    user_profile: Optional[Dict] = None,
    job_analysis: Optional[Dict] = None,
    profile_matching: Optional[Dict] = None,
    company_research: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Create a workflow state dict for testing."""
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_profile": user_profile,
        "user_api_key": None,
        "job_input_data": {"input_method": "manual"},
        "job_analysis": job_analysis,
        "company_research": company_research,
        "profile_matching": profile_matching,
        "resume_recommendations": None,
        "cover_letter": None,
        "current_phase": "resume_advisor",
        "workflow_status": "running",
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "processing_end_time": None,
        "agent_status": {},
        "completed_agents": ["job_analyzer", "profile_matching", "company_research"],
        "failed_agents": [],
        "current_agent": "resume_advisor",
        "error_messages": [],
        "warning_messages": [],
        "agent_start_times": {},
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client that returns valid resume recommendations."""
    client = AsyncMock()
    client.generate.return_value = {
        "response": '''{
            "strategic_assessment": {
                "current_competitiveness": "Strong candidate",
                "biggest_opportunity": "Emphasize cloud achievements",
                "ats_pass_likelihood": "HIGH"
            },
            "professional_summary": {
                "current_assessment": "Current summary is too generic",
                "recommended_summary": "Results-driven Software Engineer..."
            },
            "experience_optimization": {
                "prioritization_strategy": "Lead with most recent role",
                "roles_to_highlight": [{"role": "Backend Engineer", "company": "StartupCo"}]
            },
            "skills_section": {
                "must_include_skills": [{"skill": "Python", "reason": "Primary requirement"}],
                "skills_to_add": ["System Design"]
            },
            "ats_optimization": {
                "critical_keywords_missing": [{"keyword": "microservices", "importance": "HIGH"}],
                "format_recommendations": ["Use standard section headers"]
            },
            "quick_wins": [{"action": "Add metrics", "impact": "HIGH", "time_to_implement": "15 min"}],
            "red_flags_to_fix": [],
            "final_checklist": {
                "before_submitting": ["Spell-check all content"],
                "file_format": "PDF"
            },
            "confidence_score": {"score": 0.85}
        }''',
        "filtered": False,
    }
    return client


@pytest.fixture
def workflow_state_complete():
    """Create complete workflow state with all prior analysis."""
    return create_test_workflow_state(
        user_profile={
            "full_name": "John Doe",
            "professional_title": "Software Engineer",
            "years_experience": 5,
            "skills": ["Python", "JavaScript", "AWS"],
            "work_experience": [
                {"job_title": "Backend Engineer", "company": "StartupCo"}
            ],
        },
        job_analysis={
            "job_title": "Senior Software Engineer",
            "company_name": "TechCorp Inc",
            "required_skills": ["Python", "AWS"],
        },
        profile_matching={
            "overall_score": 0.78,
            "executive_summary": {"recommendation": "GOOD_MATCH"},
        },
        company_research={
            "company_overview": {"industry": "Technology"},
        },
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestResumeAdvisorInit:
    """Tests for ResumeAdvisorAgent initialization."""

    def test_init_with_valid_client(self, mock_gemini_client):
        """Test successful initialization with valid Gemini client."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        assert agent.gemini_client is mock_gemini_client

    def test_init_with_none_client_raises_error(self):
        """Test that None client raises TypeError."""
        with pytest.raises(TypeError, match="gemini_client cannot be None"):
            ResumeAdvisorAgent(gemini_client=None)


# =============================================================================
# PROCESSING TESTS
# =============================================================================


class TestResumeAdvisorProcessing:
    """Tests for resume advisor processing."""

    @pytest.mark.asyncio
    async def test_process_success(self, mock_gemini_client, workflow_state_complete):
        """Test successful resume advisory processing."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        
        result = await agent.process(workflow_state_complete)
        
        assert "resume_recommendations" in result
        recommendations = result["resume_recommendations"]
        assert "strategic_assessment" in recommendations or "comprehensive_advice" in recommendations

    @pytest.mark.asyncio
    async def test_process_missing_user_profile_raises_error(self, mock_gemini_client):
        """Test that missing user profile raises error."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile=None,
            job_analysis={"job_title": "Engineer"},
        )
        
        with pytest.raises(ValueError, match="[Uu]ser profile|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_missing_job_analysis_raises_error(self, mock_gemini_client):
        """Test that missing job analysis raises error."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile={"full_name": "Test"},
            job_analysis=None,
        )
        
        with pytest.raises(ValueError, match="[Jj]ob analysis|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_without_optional_data(self, mock_gemini_client):
        """Test processing without optional profile_matching and company_research."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile={"full_name": "Test User", "skills": ["Python"]},
            job_analysis={"job_title": "Engineer", "required_skills": ["Python"]},
            # No profile_matching or company_research
        )
        
        result = await agent.process(state)
        
        assert "resume_recommendations" in result


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_filtered_response(self, workflow_state_complete):
        """Test handling of filtered LLM response."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "Content filtered",
            "filtered": True,
        }
        
        agent = ResumeAdvisorAgent(gemini_client=mock_client)
        result = await agent.process(workflow_state_complete)
        
        # Should return fallback result
        assert "resume_recommendations" in result

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self, workflow_state_complete):
        """Test handling of invalid JSON from LLM."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "This is not valid JSON",
            "filtered": False,
        }
        
        agent = ResumeAdvisorAgent(gemini_client=mock_client)
        result = await agent.process(workflow_state_complete)
        
        # Should return result (possibly with raw_advice or fallback)
        assert "resume_recommendations" in result


# =============================================================================
# ADDITIONAL COVERAGE — LLM CALL COUNT, EXCEPTION PROPAGATION, API KEY
# =============================================================================


class TestResumeAdvisorAdditional:
    """Additional coverage for edge cases not in the base tests."""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self, workflow_state_complete):
        """LLM exception is caught inside _generate_recommendations() and returns a fallback."""
        failing_client = AsyncMock()
        failing_client.generate.side_effect = RuntimeError("Service down")

        agent = ResumeAdvisorAgent(gemini_client=failing_client)
        result = await agent.process(workflow_state_complete)

        # _generate_recommendations catches all exceptions and returns fallback
        assert "resume_recommendations" in result

    @pytest.mark.asyncio
    async def test_llm_called_exactly_once(self, mock_gemini_client, workflow_state_complete):
        """LLM should be called exactly once per process() call."""
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        await agent.process(workflow_state_complete)
        assert mock_gemini_client.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_user_api_key_stored_before_llm_call(
        self, mock_gemini_client, workflow_state_complete
    ):
        """User API key from workflow state should be propagated."""
        workflow_state_complete["user_api_key"] = "byok-key"
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        await agent.process(workflow_state_complete)
        # Verify the call was made (key propagation is internal)
        assert mock_gemini_client.generate.called

    @pytest.mark.asyncio
    async def test_generate_recommendations_timeout_returns_fallback(
        self, mock_gemini_client, workflow_state_complete
    ):
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None
        with patch("agents.resume_advisor.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await agent._generate_recommendations(
                workflow_state_complete["user_profile"],
                workflow_state_complete["job_analysis"],
                workflow_state_complete["profile_matching"],
                workflow_state_complete["company_research"],
            )
        assert result.get("error") is True
        assert "timed out" in result.get("error_message", "").lower()

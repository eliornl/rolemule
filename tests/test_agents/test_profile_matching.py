"""
Unit tests for the Profile Matching Agent.
Tests profile-job matching analysis with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agents.profile_matching import ProfileMatchingAgent


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_test_workflow_state(
    user_id: str = "test-user-123",
    session_id: str = "test-session-456",
    user_profile: Optional[Dict] = None,
    job_analysis: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Create a workflow state dict for testing."""
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_profile": user_profile,
        "user_api_key": None,
        "job_input_data": {"input_method": "manual"},
        "job_analysis": job_analysis,
        "company_research": None,
        "profile_matching": None,
        "resume_recommendations": None,
        "cover_letter": None,
        "current_phase": "profile_matching",
        "workflow_status": "running",
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "processing_end_time": None,
        "agent_status": {},
        "completed_agents": ["job_analyzer"],
        "failed_agents": [],
        "current_agent": "profile_matching",
        "error_messages": [],
        "warning_messages": [],
        "agent_start_times": {},
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini_response():
    """Valid profile matching JSON response from LLM."""
    return {
        "response": '''{
            "executive_summary": {
                "fit_assessment": "Strong technical fit",
                "recommendation": "GOOD_MATCH",
                "confidence_level": "HIGH",
                "one_line_verdict": "Well-qualified candidate"
            },
            "qualification_analysis": {
                "overall_score": 0.78,
                "skills_assessment": {
                    "score": 0.85,
                    "matched_skills": [{"skill": "Python", "strength": "STRONG"}],
                    "missing_critical_skills": [{"skill": "Kubernetes"}]
                },
                "experience_assessment": {"score": 0.75},
                "education_assessment": {"score": 0.9},
                "certification_assessment": {"score": 0.6}
            },
            "preference_analysis": {
                "overall_score": 0.82,
                "salary_fit": {"score": 0.9},
                "work_arrangement_fit": {"score": 0.8},
                "location_fit": {"score": 0.85}
            },
            "deal_breaker_analysis": {
                "overall_passed": true,
                "deal_breakers_found": []
            },
            "competitive_positioning": {
                "estimated_candidate_pool_percentile": 75,
                "unique_value_proposition": "Technical depth with leadership"
            },
            "application_strategy": {
                "should_apply": true,
                "application_priority": "HIGH"
            },
            "risk_assessment": {
                "candidate_risks": [],
                "role_risks": []
            },
            "final_scores": {
                "qualification_score": 0.78,
                "preference_score": 0.82,
                "deal_breaker_score": 1.0,
                "overall_match_score": 0.80
            },
            "ai_insights": {
                "career_advice": "Consider Kubernetes certification"
            }
        }''',
        "filtered": False,
    }


@pytest.fixture
def sample_user_profile():
    """Sample user profile for testing."""
    return {
        "full_name": "John Doe",
        "professional_title": "Software Engineer",
        "years_experience": 5,
        "city": "San Francisco",
        "state": "CA",
        "country": "USA",
        "summary": "Experienced software engineer",
        "skills": ["Python", "JavaScript", "AWS"],
        "work_experience": [
            {
                "job_title": "Backend Engineer",
                "company": "StartupCo",
                "description": "Scaled system to 1M users",
            }
        ],
        "desired_salary_range": {"min": 150000, "max": 200000},
        "work_arrangements": ["Remote", "Hybrid"],
    }


@pytest.fixture
def sample_job_analysis():
    """Sample job analysis for testing."""
    return {
        "job_title": "Senior Software Engineer",
        "company_name": "TechCorp Inc",
        "required_skills": ["Python", "AWS", "Kubernetes"],
        "years_experience_required": 5,
    }


@pytest.fixture
def workflow_state(sample_user_profile, sample_job_analysis):
    """Create workflow state with profile and job analysis."""
    return create_test_workflow_state(
        user_profile=sample_user_profile,
        job_analysis=sample_job_analysis,
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestProfileMatchingInit:
    """Tests for ProfileMatchingAgent initialization."""

    def test_init_success(self):
        """Test successful initialization."""
        agent = ProfileMatchingAgent()
        # ProfileMatchingAgent initializes gemini_client as None, lazily loaded
        assert agent.gemini_client is None


# =============================================================================
# PROCESSING TESTS
# =============================================================================


class TestProfileMatchingProcessing:
    """Tests for profile matching processing."""

    @pytest.mark.asyncio
    async def test_process_success(self, mock_gemini_response, workflow_state):
        """Test successful profile matching processing."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = mock_gemini_response
        
        agent = ProfileMatchingAgent()
        
        # Patch the gemini client getter
        with patch('agents.profile_matching.get_gemini_client', return_value=mock_client):
            result = await agent.process(workflow_state)
        
        assert "profile_matching" in result
        assert result["profile_matching"]["executive_summary"]["recommendation"] == "GOOD_MATCH"

    @pytest.mark.asyncio
    async def test_process_missing_user_profile_raises_error(self, sample_job_analysis):
        """Test that missing user profile raises error."""
        agent = ProfileMatchingAgent()
        
        state = create_test_workflow_state(
            user_profile=None,
            job_analysis=sample_job_analysis,
        )
        
        with pytest.raises(ValueError, match="[Uu]ser profile|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_missing_job_analysis_raises_error(self, sample_user_profile):
        """Test that missing job analysis raises error."""
        agent = ProfileMatchingAgent()
        
        state = create_test_workflow_state(
            user_profile=sample_user_profile,
            job_analysis=None,
        )
        
        with pytest.raises(ValueError, match="[Jj]ob analysis|required"):
            await agent.process(state)


# =============================================================================
# SCORE EXTRACTION TESTS
# =============================================================================


class TestScoreExtraction:
    """Tests for score extraction."""

    @pytest.mark.asyncio
    async def test_extracts_overall_score(self, mock_gemini_response, workflow_state):
        """Test that overall score is extracted."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = mock_gemini_response
        
        agent = ProfileMatchingAgent()
        
        with patch('agents.profile_matching.get_gemini_client', return_value=mock_client):
            result = await agent.process(workflow_state)
        
        # Should have final_scores
        assert "final_scores" in result["profile_matching"]


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_filtered_response(self, workflow_state):
        """Test handling of filtered LLM response."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "Content filtered",
            "filtered": True,
        }
        
        agent = ProfileMatchingAgent()
        
        with patch('agents.profile_matching.get_gemini_client', return_value=mock_client):
            result = await agent.process(workflow_state)
        
        # Should return fallback result
        assert "profile_matching" in result

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self, workflow_state):
        """Test handling of invalid JSON from LLM."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "This is not valid JSON",
            "filtered": False,
        }
        
        agent = ProfileMatchingAgent()
        
        with patch('agents.profile_matching.get_gemini_client', return_value=mock_client):
            result = await agent.process(workflow_state)
        
        # Should return fallback result with parse error indicator
        assert "profile_matching" in result


# =============================================================================
# ADDITIONAL COVERAGE — LLM CALL COUNT, EXCEPTION PROPAGATION, LAZY INIT
# =============================================================================


class TestProfileMatchingAdditional:
    """Additional coverage for edge cases not in the base tests."""

    @pytest.mark.asyncio
    async def test_llm_exception_propagated(self, workflow_state):
        """Exception from get_gemini_client().generate should propagate."""
        failing_client = AsyncMock()
        failing_client.generate.side_effect = RuntimeError("Service down")

        agent = ProfileMatchingAgent()

        with patch("agents.profile_matching.get_gemini_client", return_value=failing_client):
            with pytest.raises(Exception):
                await agent.process(workflow_state)

    @pytest.mark.asyncio
    async def test_llm_called_exactly_once(self, mock_gemini_response, workflow_state):
        """LLM should be called exactly once per process() call."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = mock_gemini_response

        agent = ProfileMatchingAgent()

        with patch("agents.profile_matching.get_gemini_client", return_value=mock_client):
            await agent.process(workflow_state)

        assert mock_client.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_get_gemini_client_called_when_none(self, mock_gemini_response, workflow_state):
        """get_gemini_client() should be invoked on first call when client is None."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = mock_gemini_response

        agent = ProfileMatchingAgent()
        assert agent.gemini_client is None

        with patch(
            "agents.profile_matching.get_gemini_client", return_value=mock_client
        ) as mock_getter:
            await agent.process(workflow_state)

        mock_getter.assert_called_once()

    @pytest.mark.asyncio
    async def test_final_scores_present_in_result(self, mock_gemini_response, workflow_state):
        """final_scores key should be present in profile_matching result."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = mock_gemini_response

        agent = ProfileMatchingAgent()

        with patch("agents.profile_matching.get_gemini_client", return_value=mock_client):
            result = await agent.process(workflow_state)

        assert "final_scores" in result["profile_matching"]
        scores = result["profile_matching"]["final_scores"]
        assert "overall_match_score" in scores

    @pytest.mark.asyncio
    async def test_process_timeout_sets_error_and_raises(self, workflow_state):
        """TimeoutError during matching should store error result and re-raise."""
        mock_client = AsyncMock()
        mock_client.generate.side_effect = asyncio.TimeoutError()

        agent = ProfileMatchingAgent()

        with patch("agents.profile_matching.get_gemini_client", return_value=mock_client):
            with pytest.raises(asyncio.TimeoutError):
                await agent.process(workflow_state)

        assert workflow_state["profile_matching"]["error"] is True

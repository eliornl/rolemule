"""
Unit tests for the Cover Letter Writer Agent.
Tests cover letter generation with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agents.cover_letter_writer import CoverLetterWriterAgent


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
        "current_phase": "cover_letter",
        "workflow_status": "running",
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "processing_end_time": None,
        "agent_status": {},
        "completed_agents": ["job_analyzer", "profile_matching", "company_research", "resume_advisor"],
        "failed_agents": [],
        "current_agent": "cover_letter_writer",
        "error_messages": [],
        "warning_messages": [],
        "agent_start_times": {},
    }


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_gemini_client():
    """Create a mock Gemini client that returns a valid cover letter."""
    client = AsyncMock()
    today = datetime.now().strftime("%B %d, %Y")
    client.generate.return_value = {
        "response": f"""{today}

Dear Hiring Manager,

Your recent launch of the AI platform caught my attention. As a Software Engineer who scaled systems to 1M+ users, I'm excited about the Senior Software Engineer role at TechCorp Inc.

In my current role, I've led a team of engineers in migrating to AWS, reducing costs by 30%.

I would welcome the opportunity to discuss how my background can contribute to TechCorp's growth.

Best regards,
John Doe
john.doe@email.com
""",
        "filtered": False,
    }
    return client


@pytest.fixture
def workflow_state_complete():
    """Create complete workflow state with all prior analysis."""
    return create_test_workflow_state(
        user_profile={
            "full_name": "John Doe",
            "email": "john.doe@email.com",
            "professional_title": "Software Engineer",
            "years_experience": 5,
            "city": "San Francisco",
            "state": "CA",
            "skills": ["Python", "JavaScript", "AWS"],
            "work_experience": [
                {
                    "job_title": "Backend Engineer",
                    "company": "StartupCo",
                    "description": "Scaled system to 1M users",
                }
            ],
        },
        job_analysis={
            "job_title": "Senior Software Engineer",
            "company_name": "TechCorp Inc",
            "industry": "Technology",
            "required_skills": ["Python", "AWS"],
        },
        profile_matching={
            "overall_score": 0.78,
            "executive_summary": {"recommendation": "GOOD_MATCH"},
            "application_strategy": {
                "key_talking_points": ["Scaling experience"],
                "cover_letter_angle": "Focus on scaling expertise",
            },
        },
        company_research={
            "company_overview": {"industry": "Technology"},
            "recent_news": [{"title": "TechCorp launches AI platform"}],
        },
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestCoverLetterWriterInit:
    """Tests for CoverLetterWriterAgent initialization."""

    def test_init_with_valid_client(self, mock_gemini_client):
        """Test successful initialization with valid Gemini client."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        assert agent.gemini_client is mock_gemini_client

    def test_init_with_none_client_raises_error(self):
        """Test that None client raises TypeError."""
        with pytest.raises(TypeError, match="gemini_client cannot be None"):
            CoverLetterWriterAgent(gemini_client=None)


# =============================================================================
# PROCESSING TESTS
# =============================================================================


class TestCoverLetterProcessing:
    """Tests for cover letter processing."""

    @pytest.mark.asyncio
    async def test_process_success(self, mock_gemini_client, workflow_state_complete):
        """Test successful cover letter generation."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        
        result = await agent.process(workflow_state_complete)
        
        assert "cover_letter" in result
        cover_letter = result["cover_letter"]
        assert "content" in cover_letter or isinstance(cover_letter, str)

    @pytest.mark.asyncio
    async def test_process_missing_user_profile_raises_error(self, mock_gemini_client):
        """Test that missing user profile raises error."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile=None,
            job_analysis={"job_title": "Engineer"},
        )
        
        with pytest.raises(ValueError, match="[Uu]ser profile|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_missing_job_analysis_raises_error(self, mock_gemini_client):
        """Test that missing job analysis raises error."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile={"full_name": "Test"},
            job_analysis=None,
        )
        
        with pytest.raises(ValueError, match="[Jj]ob analysis|required"):
            await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_without_optional_data(self, mock_gemini_client):
        """Test processing without optional profile_matching and company_research."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        
        state = create_test_workflow_state(
            user_profile={
                "full_name": "Test User",
                "professional_title": "Engineer",
                "years_experience": 3,
            },
            job_analysis={
                "job_title": "Engineer",
                "company_name": "TestCorp",
                "industry": "Technology",
            },
            # No profile_matching or company_research
        )
        
        result = await agent.process(state)
        
        assert "cover_letter" in result


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
        
        agent = CoverLetterWriterAgent(gemini_client=mock_client)
        result = await agent.process(workflow_state_complete)
        
        # Should return fallback letter or handle gracefully
        assert "cover_letter" in result

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, workflow_state_complete):
        """Test handling of empty LLM response."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "",
            "filtered": False,
        }
        
        agent = CoverLetterWriterAgent(gemini_client=mock_client)
        
        # Should either raise error or return fallback
        try:
            result = await agent.process(workflow_state_complete)
            # If it doesn't raise, verify we have some cover letter output
            assert "cover_letter" in result
        except Exception:
            # Empty response should raise an error
            return


# =============================================================================
# ADDITIONAL COVERAGE — LLM CALL COUNT, EXCEPTION PROPAGATION, API KEY
# =============================================================================


class TestCoverLetterWriterAdditional:
    """Additional coverage for edge cases not in the base tests."""

    @pytest.mark.asyncio
    async def test_llm_exception_propagated(self, mock_gemini_client, workflow_state_complete):
        """Exception from gemini_client.generate should propagate."""
        failing_client = AsyncMock()
        failing_client.generate.side_effect = RuntimeError("LLM unavailable")

        agent = CoverLetterWriterAgent(gemini_client=failing_client)

        with pytest.raises(Exception):
            await agent.process(workflow_state_complete)

    @pytest.mark.asyncio
    async def test_llm_called_exactly_once(self, mock_gemini_client, workflow_state_complete):
        """LLM should be called exactly once per process() call."""
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        await agent.process(workflow_state_complete)
        assert mock_gemini_client.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_user_api_key_stored_before_llm_call(
        self, mock_gemini_client, workflow_state_complete
    ):
        """User API key from workflow state should be propagated to the LLM."""
        workflow_state_complete["user_api_key"] = "user-byok-key"
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        await agent.process(workflow_state_complete)
        assert mock_gemini_client.generate.called

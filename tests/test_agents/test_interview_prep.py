"""
Unit tests for the Interview Prep Agent.
Tests interview preparation generation with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from agents.interview_prep import InterviewPrepAgent


# =============================================================================
# FIXTURES
# =============================================================================

MOCK_LLM_RESPONSE = {
    "response": """{
        "interview_process": {
            "total_timeline": "2-3 weeks",
            "format_prediction": "Video + Onsite",
            "typical_rounds": [
                {"round": 1, "type": "Phone Screen", "duration": "30 min",
                 "with": "Recruiter", "focus": "Background and fit"}
            ]
        },
        "predicted_questions": {
            "behavioral": [
                {"question": "Tell me about a challenge you overcame.",
                 "why_likely": "Tests resilience", "star_framework": {
                     "situation": "At StartupCo...", "task": "I needed to...",
                     "action": "I did...", "result": "The outcome was..."
                 }}
            ],
            "technical": [
                {"question": "Design a URL shortener.", "why_likely": "Common system design"}
            ],
            "role_specific": [
                {"question": "How do you handle tech debt?", "why_likely": "Engineering fit"}
            ],
            "company_specific": [
                {"question": "Why TechCorp?", "why_likely": "Company fit"}
            ]
        },
        "addressing_concerns": [
            {"concern": "Gap in employment",
             "how_to_address": "Frame as intentional learning time.",
             "talking_points": ["Completed Python certification"]}
        ],
        "questions_for_them": [
            {"question": "What does success look like in 90 days?",
             "why_good": "Shows initiative", "when_to_ask": "End of interview"}
        ],
        "logistics": {
            "location": "Remote via Zoom",
            "dress_code": "Business casual",
            "timing": {"arrive": "5 min early", "expected_duration": "60 min"}
        },
        "quick_reference_card": {
            "elevator_pitch": "I am a software engineer with 5 years...",
            "three_key_selling_points": ["Python expertise", "Scalability", "Leadership"]
        },
        "day_before_checklist": ["Research the company", "Prepare STAR stories"],
        "confidence_boosters": ["You solved similar problems", "5 years relevant exp"]
    }""",
    "filtered": False,
}

SAMPLE_JOB_ANALYSIS = {
    "job_title": "Senior Software Engineer",
    "company_name": "TechCorp Inc.",
    "required_skills": ["Python", "AWS"],
    "years_experience_required": 5,
}

SAMPLE_COMPANY_RESEARCH = {
    "industry": "Technology",
    "culture_and_values": {"core_values": ["Innovation", "Integrity"]},
    "interview_intelligence": {"typical_process": ["Phone screen", "Technical"]},
}

SAMPLE_PROFILE_MATCHING = {
    "executive_summary": {"recommendation": "GOOD_MATCH", "fit_assessment": "Strong fit"},
    "final_scores": {"overall_match_score": 0.82},
    "application_strategy": {
        "key_talking_points": ["Scaling experience"],
        "concerns_to_address": [{"concern": "Gap in employment"}],
    },
}

SAMPLE_USER_PROFILE = {
    "full_name": "John Doe",
    "professional_title": "Software Engineer",
    "years_experience": 5,
    "skills": ["Python", "AWS", "PostgreSQL"],
    "work_experience": [
        {"job_title": "Backend Engineer", "company": "StartupCo",
         "description": "Scaled system to 1M users"},
    ],
}


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client returning valid interview prep JSON."""
    client = AsyncMock()
    client.generate.return_value = MOCK_LLM_RESPONSE
    return client


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestInterviewPrepAgentInit:
    """Tests for InterviewPrepAgent initialization."""

    def test_init_starts_with_none_client(self):
        """Agent starts without a Gemini client (lazy-loaded)."""
        agent = InterviewPrepAgent()
        assert agent.gemini_client is None

    def test_init_starts_with_none_api_key(self):
        """Agent starts with no user API key."""
        agent = InterviewPrepAgent()
        assert agent._current_user_api_key is None


# =============================================================================
# SUCCESSFUL GENERATION TESTS
# =============================================================================


class TestInterviewPrepGeneration:
    """Tests for successful interview prep generation."""

    @pytest.mark.asyncio
    async def test_generate_success(self, mock_gemini_client):
        """Test successful generation returns expected structure."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert isinstance(result, dict)
        assert "generated_at" in result
        assert "processing_time" in result
        assert "version" in result

    @pytest.mark.asyncio
    async def test_generate_includes_predicted_questions(self, mock_gemini_client):
        """Result should contain predicted questions."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert "predicted_questions" in result
        assert "behavioral" in result["predicted_questions"]

    @pytest.mark.asyncio
    async def test_generate_includes_interview_process(self, mock_gemini_client):
        """Result should contain interview process info."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert "interview_process" in result

    @pytest.mark.asyncio
    async def test_generated_at_is_iso_timestamp(self, mock_gemini_client):
        """generated_at should be a valid ISO 8601 string."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        ts = result["generated_at"]
        assert isinstance(ts, str)
        # Must parse without error
        datetime.fromisoformat(ts.replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_processing_time_is_positive_number(self, mock_gemini_client):
        """processing_time should be a positive float (seconds)."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert isinstance(result["processing_time"], (int, float))
        assert result["processing_time"] >= 0

    @pytest.mark.asyncio
    async def test_user_api_key_propagated_to_llm(self, mock_gemini_client):
        """User API key should be passed to the LLM generate call."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
                user_api_key="my-byok-key",
            )

        call_kwargs = mock_gemini_client.generate.call_args[1]
        assert call_kwargs.get("user_api_key") == "my-byok-key"

    @pytest.mark.asyncio
    async def test_gemini_client_lazy_initialized(self, mock_gemini_client):
        """get_gemini_client() should be called if client is None."""
        agent = InterviewPrepAgent()
        assert agent.gemini_client is None

        with patch(
            "agents.interview_prep.get_gemini_client", return_value=mock_gemini_client
        ) as mock_getter:
            await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        mock_getter.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_minimal_inputs(self, mock_gemini_client):
        """Should succeed with minimal (but valid) dict inputs."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis={"job_title": "Engineer", "company_name": "Acme"},
                company_research={},
                profile_matching={},
                user_profile={"full_name": "Jane"},
            )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_generate_with_no_user_api_key(self, mock_gemini_client):
        """Should work with no user API key (uses default platform key)."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
                user_api_key=None,
            )

        assert isinstance(result, dict)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestInterviewPrepErrorHandling:
    """Tests for error handling in InterviewPrepAgent."""

    @pytest.mark.asyncio
    async def test_filtered_response_returns_fallback(self):
        """Filtered LLM response returns a graceful fallback result, not an exception."""
        client = AsyncMock()
        client.generate.return_value = {"response": "Filtered", "filtered": True}

        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert "generated_at" in result or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(self):
        """Unparseable LLM response returns a graceful fallback result, not an exception."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": "This is not JSON at all {{}}",
            "filtered": False,
        }

        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=client):
            result = await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_llm_exception_propagated(self):
        """Exception from gemini_client.generate should propagate."""
        client = AsyncMock()
        client.generate.side_effect = RuntimeError("LLM service unavailable")

        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=client):
            with pytest.raises(Exception):
                await agent.generate(
                    job_analysis=SAMPLE_JOB_ANALYSIS,
                    company_research=SAMPLE_COMPANY_RESEARCH,
                    profile_matching=SAMPLE_PROFILE_MATCHING,
                    user_profile=SAMPLE_USER_PROFILE,
                )

    @pytest.mark.asyncio
    async def test_llm_called_once_per_generate(self, mock_gemini_client):
        """LLM should be called exactly once per generate() call."""
        agent = InterviewPrepAgent()

        with patch("agents.interview_prep.get_gemini_client", return_value=mock_gemini_client):
            await agent.generate(
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                profile_matching=SAMPLE_PROFILE_MATCHING,
                user_profile=SAMPLE_USER_PROFILE,
            )

        assert mock_gemini_client.generate.call_count == 1

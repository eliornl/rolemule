"""
Unit tests for the Thank You Writer Agent.
Tests post-interview thank-you email generation with mocked LLM responses.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from agents.thank_you_writer import ThankYouWriterAgent


# =============================================================================
# FIXTURES
# =============================================================================

MOCK_LLM_RESPONSE = {
    "response": """{
        "subject_line": "Thank you for the interview - Senior Software Engineer",
        "email_body": "Dear Sarah,\\n\\nThank you for taking the time to meet with me today...",
        "key_points_referenced": ["Team scaling challenges", "Python architecture discussion"],
        "tone": "professional and warm"
    }""",
    "filtered": False,
}


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client returning valid thank-you JSON."""
    client = AsyncMock()
    client.generate.return_value = MOCK_LLM_RESPONSE
    return client


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestThankYouWriterInit:
    """Tests for ThankYouWriterAgent initialization."""

    def test_init_starts_with_none_client(self):
        """Agent starts without a Gemini client (lazy-loaded)."""
        agent = ThankYouWriterAgent()
        assert agent.gemini_client is None

    def test_init_starts_with_none_api_key(self):
        """Agent starts with no user API key."""
        agent = ThankYouWriterAgent()
        assert agent._current_user_api_key is None


# =============================================================================
# SUCCESSFUL GENERATION TESTS
# =============================================================================


class TestThankYouWriterGeneration:
    """Tests for successful thank-you email generation."""

    @pytest.mark.asyncio
    async def test_generate_success_returns_all_keys(self, mock_gemini_client):
        """Successful generation should return all expected keys."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                interviewer_name="Sarah",
                interview_type="technical",
                company_name="TechCorp Inc.",
                job_title="Senior Software Engineer",
            )

        assert "subject_line" in result
        assert "email_body" in result
        assert "key_points_referenced" in result
        assert "tone" in result
        assert "generated_at" in result
        assert "version" in result

    @pytest.mark.asyncio
    async def test_generate_subject_line_contains_job_title(self, mock_gemini_client):
        """Subject line fallback should reference the job title."""
        client = AsyncMock()
        # LLM returns response without subject_line — triggers fallback
        client.generate.return_value = {
            "response": '{"email_body": "Dear John,\\n\\nThank you..."}',
            "filtered": False,
        }

        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=client):
            result = await agent.generate(
                interviewer_name="John",
                interview_type="behavioral",
                company_name="Acme",
                job_title="Product Manager",
            )

        assert "Product Manager" in result["subject_line"]

    @pytest.mark.asyncio
    async def test_generate_with_all_optional_params(self, mock_gemini_client):
        """Should work with all optional params supplied."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                interviewer_name="Alex",
                interview_type="onsite",
                company_name="BigCo",
                job_title="Staff Engineer",
                interviewer_role="Engineering Manager",
                key_discussion_points=["System design", "Team culture"],
                additional_notes="Mention the AI roadmap discussion",
                user_api_key="byok-key",
            )

        assert isinstance(result, dict)
        assert "email_body" in result

    @pytest.mark.asyncio
    async def test_generate_with_minimal_params(self, mock_gemini_client):
        """Should work with only the four required positional params."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                interviewer_name="Bob",
                interview_type="phone",
                company_name="Startup",
                job_title="Backend Engineer",
            )

        assert "email_body" in result

    @pytest.mark.asyncio
    async def test_generated_at_is_iso_timestamp(self, mock_gemini_client):
        """generated_at should be a valid ISO 8601 timestamp."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                interviewer_name="Dana",
                interview_type="panel",
                company_name="Corp",
                job_title="Engineer",
            )

        datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_version_is_set(self, mock_gemini_client):
        """version field should be present in result."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            result = await agent.generate(
                interviewer_name="Eve",
                interview_type="video",
                company_name="Corp",
                job_title="Engineer",
            )

        assert result["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_user_api_key_passed_to_llm(self, mock_gemini_client):
        """User API key should reach the LLM generate() call."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            await agent.generate(
                interviewer_name="Frank",
                interview_type="technical",
                company_name="Corp",
                job_title="Engineer",
                user_api_key="user-provided-key",
            )

        call_kwargs = mock_gemini_client.generate.call_args[1]
        assert call_kwargs.get("user_api_key") == "user-provided-key"

    @pytest.mark.asyncio
    async def test_gemini_client_lazy_initialized(self, mock_gemini_client):
        """get_gemini_client() should be called when client is None."""
        agent = ThankYouWriterAgent()

        with patch(
            "agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client
        ) as mock_getter:
            await agent.generate(
                interviewer_name="Grace",
                interview_type="technical",
                company_name="Corp",
                job_title="Engineer",
            )

        mock_getter.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_points_referenced_defaults_to_list(self, mock_gemini_client):
        """key_points_referenced should default to an empty list if absent from LLM response."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": '{"subject_line": "Thank you", "email_body": "Thanks!"}',
            "filtered": False,
        }

        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=client):
            result = await agent.generate(
                interviewer_name="Hank",
                interview_type="phone",
                company_name="Co",
                job_title="Dev",
            )

        assert isinstance(result["key_points_referenced"], list)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestThankYouWriterErrorHandling:
    """Tests for error handling in ThankYouWriterAgent."""

    @pytest.mark.asyncio
    async def test_filtered_response_returns_fallback(self):
        """Filtered LLM response should return a graceful fallback result, not raise."""
        client = AsyncMock()
        client.generate.return_value = {"response": "Filtered", "filtered": True}

        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=client):
            result = await agent.generate(
                interviewer_name="Ivy",
                interview_type="technical",
                company_name="Corp",
                job_title="Engineer",
            )

        assert "email_body" in result
        assert "subject_line" in result

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(self):
        """Non-JSON LLM response should return a graceful fallback result, not raise."""
        client = AsyncMock()
        client.generate.return_value = {
            "response": "Here is your thank you email: Dear X, ...",
            "filtered": False,
        }

        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=client):
            result = await agent.generate(
                interviewer_name="Jake",
                interview_type="phone",
                company_name="Corp",
                job_title="Engineer",
            )

        assert "email_body" in result

    @pytest.mark.asyncio
    async def test_llm_exception_propagated(self):
        """Exception raised by gemini_client.generate should propagate."""
        client = AsyncMock()
        client.generate.side_effect = ConnectionError("LLM unreachable")

        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=client):
            with pytest.raises(Exception):
                await agent.generate(
                    interviewer_name="Karen",
                    interview_type="onsite",
                    company_name="Corp",
                    job_title="Engineer",
                )

    @pytest.mark.asyncio
    async def test_llm_called_exactly_once(self, mock_gemini_client):
        """LLM should be called exactly once per generate() call."""
        agent = ThankYouWriterAgent()

        with patch("agents.thank_you_writer.get_gemini_client", return_value=mock_gemini_client):
            await agent.generate(
                interviewer_name="Leo",
                interview_type="video",
                company_name="Corp",
                job_title="Engineer",
            )

        assert mock_gemini_client.generate.call_count == 1

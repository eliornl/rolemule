"""
Unit tests for HiringManagerAgent.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agents.hiring_manager import HiringManagerAgent, HiringManagerEvaluation


# =============================================================================
# FIXTURES
# =============================================================================

MOCK_VALID_RESPONSE = {
    "response": """{
        "requirement_scores": [
            {"requirement": "Python", "status": "fully_met", "evidence": "5 years Python", "weight": "required"},
            {"requirement": "Kubernetes", "status": "not_met", "evidence": "Not mentioned", "weight": "required"}
        ],
        "score": 7.2,
        "strengths": ["Strong Python background", "Leadership experience", "Cloud expertise"],
        "gaps": ["No Kubernetes experience", "Missing CI/CD knowledge"],
        "action_items": ["Add Kubernetes project to skills", "Mention any CI/CD pipeline work"],
        "reasoning": "Good candidate with strong core skills but missing cloud orchestration depth."
    }""",
    "filtered": False,
}

MOCK_FILTERED_RESPONSE = {
    "response": "Content filtered",
    "filtered": True,
}

MOCK_INVALID_JSON_RESPONSE = {
    "response": "This is not JSON at all — something went wrong",
    "filtered": False,
}

SAMPLE_JOB_ANALYSIS = {
    "job_title": "Senior Platform Engineer",
    "company_name": "TechCorp",
    "required_skills": ["Python", "Kubernetes", "AWS"],
    "required_qualifications": ["5+ years backend experience"],
    "preferred_qualifications": ["Experience with Terraform"],
}

SAMPLE_CV = """# Jane Smith
Senior Software Engineer

## Work Experience
### Backend Engineer — ACME Corp (2019–2024)
- Led Python microservices migration
- Managed AWS infrastructure
"""

SAMPLE_JD = "We are seeking a Senior Platform Engineer with Python, Kubernetes, and AWS experience..."


@pytest.fixture
def mock_client():
    """Mock Gemini client returning valid evaluation JSON."""
    client = AsyncMock()
    client.generate.return_value = MOCK_VALID_RESPONSE
    return client


# =============================================================================
# INITIALIZATION
# =============================================================================


class TestHiringManagerAgentInit:
    def test_init_no_client(self):
        agent = HiringManagerAgent()
        assert agent.gemini_client is None


# =============================================================================
# SUCCESSFUL EVALUATION
# =============================================================================


class TestHiringManagerEvaluate:
    @pytest.mark.asyncio
    async def test_evaluate_returns_evaluation(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert isinstance(result, HiringManagerEvaluation)

    @pytest.mark.asyncio
    async def test_evaluate_score_parsed_correctly(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert result.score == pytest.approx(7.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_evaluate_strengths_parsed(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert len(result.strengths) == 3
        assert "Python" in result.strengths[0]

    @pytest.mark.asyncio
    async def test_evaluate_gaps_parsed(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert len(result.gaps) == 2

    @pytest.mark.asyncio
    async def test_evaluate_passes_byok_key(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
                user_api_key="user-test-key",
            )
        call_kwargs = mock_client.generate.call_args.kwargs
        assert call_kwargs.get("user_api_key") == "user-test-key"

    @pytest.mark.asyncio
    async def test_evaluate_includes_previous_context_when_provided(self, mock_client):
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=mock_client):
            await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=1,
                previous_score=6.5,
            )
        call_kwargs = mock_client.generate.call_args.kwargs
        assert "6.5" in call_kwargs.get("prompt", "")


# =============================================================================
# FALLBACK HANDLING
# =============================================================================


class TestHiringManagerFallback:
    @pytest.mark.asyncio
    async def test_filtered_response_returns_fallback(self):
        filtered_client = AsyncMock()
        filtered_client.generate.return_value = MOCK_FILTERED_RESPONSE
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=filtered_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert result.score == pytest.approx(5.0)
        assert len(result.strengths) > 0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(self):
        bad_client = AsyncMock()
        bad_client.generate.return_value = MOCK_INVALID_JSON_RESPONSE
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=bad_client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert isinstance(result, HiringManagerEvaluation)
        assert result.score == pytest.approx(5.0)


# =============================================================================
# SCORE CLAMPING
# =============================================================================


class TestHiringManagerScoreClamping:
    @pytest.mark.asyncio
    async def test_score_clamped_to_max_10(self):
        client = AsyncMock()
        client.generate.return_value = {
            "response": '{"score": 15.0, "strengths": ["a"], "gaps": ["b"], "action_items": ["c"], "reasoning": "r"}',
            "filtered": False,
        }
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert result.score == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_score_clamped_to_min_0(self):
        client = AsyncMock()
        client.generate.return_value = {
            "response": '{"score": -5.0, "strengths": ["a"], "gaps": ["b"], "action_items": ["c"], "reasoning": "r"}',
            "filtered": False,
        }
        agent = HiringManagerAgent()
        with patch("agents.hiring_manager.get_gemini_client", return_value=client):
            result = await agent.evaluate(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                iteration=0,
            )
        assert result.score == pytest.approx(0.0)


# =============================================================================
# SERIALIZATION
# =============================================================================


class TestHiringManagerEvaluationSerialize:
    def test_to_dict_contains_required_fields(self):
        evaluation = HiringManagerEvaluation(
            score=7.5,
            strengths=["s1"],
            gaps=["g1"],
            action_items=["a1"],
            reasoning="Good match",
        )
        d = evaluation.to_dict()
        assert d["score"] == pytest.approx(7.5)
        assert d["strengths"] == ["s1"]
        assert d["gaps"] == ["g1"]
        assert d["action_items"] == ["a1"]
        assert d["reasoning"] == "Good match"

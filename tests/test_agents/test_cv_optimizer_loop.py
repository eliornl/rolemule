"""
Unit tests for cv_optimizer_loop: CVOptimizerAgent, CoverLetterFinalizer,
CVOptimizationOrchestrator, and _compose_cv_from_profile.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.hiring_manager import HiringManagerEvaluation
from agents.cv_optimizer_loop import (
    CVOptimizerAgent,
    CoverLetterFinalizer,
    CVOptimizationOrchestrator,
    OptimizationConfig,
    OptimizationResult,
    _compose_cv_from_profile,
)


# =============================================================================
# FIXTURES
# =============================================================================

SAMPLE_CV = "# Jane Smith\nSenior Engineer\n\n## Experience\n### Engineer at ACME\n- Led Python work"
SAMPLE_JD = "We need a Python engineer with cloud experience."
SAMPLE_JOB_ANALYSIS = {
    "job_title": "Senior Engineer",
    "company_name": "TechCorp",
    "required_skills": ["Python"],
    "required_qualifications": ["5+ years experience"],
    "preferred_qualifications": [],
}
SAMPLE_COMPANY_RESEARCH = {"company_overview": "TechCorp is a cloud company."}

SAMPLE_EVALUATION = HiringManagerEvaluation(
    score=7.0,
    strengths=["Python expertise"],
    gaps=["Missing Kubernetes"],
    action_items=["Highlight container work"],
    reasoning="Solid candidate.",
)

HIGH_SCORE_EVALUATION = HiringManagerEvaluation(
    score=9.0,
    strengths=["Excellent fit"],
    gaps=[],
    action_items=[],
    reasoning="Excellent match.",
)


def _make_hiring_manager_mock(evaluations):
    """Return a HiringManagerAgent mock that cycles through given evaluations."""
    mock = AsyncMock()
    mock.evaluate = AsyncMock(side_effect=evaluations)
    return mock


def _make_cv_optimizer_mock(revised_cv="# Revised CV"):
    mock = AsyncMock()
    mock.revise = AsyncMock(return_value=revised_cv)
    return mock


def _make_cover_letter_mock(text="Dear Hiring Team,\nI am excited..."):
    mock = AsyncMock()
    mock.generate_cover_letter = AsyncMock(return_value=text)
    return mock


async def _noop_broadcast(record):
    pass


# =============================================================================
# _compose_cv_from_profile
# =============================================================================


class TestComposeCvFromProfile:
    def test_full_profile_produces_markdown(self):
        profile = {
            "full_name": "Jane Smith",
            "professional_title": "Software Engineer",
            "email": "jane@example.com",
            "city": "New York",
            "state": "NY",
            "country": "US",
            "summary": "Experienced Python developer.",
            "work_experience": [
                {
                    "title": "Senior Engineer",
                    "company": "ACME Corp",
                    "start_date": "2020-01",
                    "end_date": "2024-01",
                    "accomplishments": ["Led microservices rewrite", "Reduced latency 40%"],
                }
            ],
            "education": [
                {
                    "institution": "MIT",
                    "degree": "B.S.",
                    "field_of_study": "Computer Science",
                    "start_date": "2012",
                    "end_date": "2016",
                }
            ],
            "skills": ["Python", "AWS", "Kubernetes"],
        }
        cv = _compose_cv_from_profile(profile)
        assert "Jane Smith" in cv
        assert "Software Engineer" in cv
        assert "ACME Corp" in cv
        assert "MIT" in cv
        assert "Python" in cv
        assert "Led microservices rewrite" in cv

    def test_empty_profile_does_not_crash(self):
        cv = _compose_cv_from_profile({})
        assert isinstance(cv, str)
        assert "Candidate" in cv

    def test_missing_optional_fields_omitted(self):
        profile = {"full_name": "Bob", "skills": ["Java"]}
        cv = _compose_cv_from_profile(profile)
        assert "Bob" in cv
        assert "Java" in cv
        # No empty section headers for missing data
        assert "Work Experience" not in cv
        assert "Education" not in cv

    def test_current_role_shows_present(self):
        profile = {
            "full_name": "Bob",
            "work_experience": [
                {
                    "title": "Engineer",
                    "company": "BigCo",
                    "start_date": "2022-01",
                    "is_current": True,
                    "accomplishments": ["Built things"],
                }
            ],
        }
        cv = _compose_cv_from_profile(profile)
        assert "Present" in cv


# =============================================================================
# CVOptimizerAgent
# =============================================================================


class TestCVOptimizerAgent:
    @pytest.mark.asyncio
    async def test_revise_returns_string(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "# Improved CV\n...", "filtered": False}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await agent.revise(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
            )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_revise_falls_back_on_filtered(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "filtered", "filtered": True}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await agent.revise(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
            )
        assert result == SAMPLE_CV  # Returns original on filter

    @pytest.mark.asyncio
    async def test_revise_falls_back_on_empty_response(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "", "filtered": False}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await agent.revise(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
            )
        assert result == SAMPLE_CV

    @pytest.mark.asyncio
    async def test_revise_passes_byok_key(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "# CV", "filtered": False}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            await agent.revise(
                cv_text=SAMPLE_CV,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
                user_api_key="byok-key",
            )
        call_kwargs = client.generate.call_args.kwargs
        assert call_kwargs.get("user_api_key") == "byok-key"


# =============================================================================
# CoverLetterFinalizer
# =============================================================================


class TestCoverLetterFinalizer:
    @pytest.mark.asyncio
    async def test_generates_non_empty_cover_letter(self):
        client = AsyncMock()
        client.generate.return_value = {
            "response": "Dear Hiring Team,\nI am excited to apply...\nBest regards,",
            "filtered": False,
        }
        finalizer = CoverLetterFinalizer()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await finalizer.generate_cover_letter(
                optimized_cv=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=SAMPLE_COMPANY_RESEARCH,
                user_api_key="byok-key",
            )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_filter(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "filtered", "filtered": True}
        finalizer = CoverLetterFinalizer()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await finalizer.generate_cover_letter(
                optimized_cv=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research=None,
                user_api_key="byok-key",
            )
        assert result == ""


# =============================================================================
# CVOptimizationOrchestrator — convergence conditions
# =============================================================================


class TestCVOptimizationOrchestratorConvergence:
    @pytest.mark.asyncio
    async def test_stops_at_score_threshold(self):
        """Loop should stop immediately when score >= threshold on iteration 0."""
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([HIGH_SCORE_EVALUATION])
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=5, score_threshold=8.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        assert result.stop_reason == "score_threshold"
        assert len(result.iteration_history) == 1  # Stopped after first eval
        assert result.best_score == pytest.approx(9.0)

    @pytest.mark.asyncio
    async def test_stops_at_max_iterations(self):
        """Loop should stop after max_iterations when no threshold is met."""
        evaluations = [
            HiringManagerEvaluation(score=6.0 + i * 0.5, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r")
            for i in range(10)
        ]
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock(evaluations)
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=3, score_threshold=9.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        assert result.stop_reason == "max_iterations"
        assert len(result.iteration_history) == 3

    @pytest.mark.asyncio
    async def test_stops_on_score_decrease(self):
        """Loop should stop if score drops below best - tolerance."""
        evaluations = [
            HiringManagerEvaluation(score=7.0, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
            HiringManagerEvaluation(score=8.0, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
            HiringManagerEvaluation(score=6.0, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),  # drop > 0.5 from best
        ]
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock(evaluations)
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=7, score_threshold=9.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        assert result.stop_reason == "score_decrease"

    @pytest.mark.asyncio
    async def test_best_cv_is_from_best_scoring_iteration(self):
        """Returned optimized_cv must be from the highest-scoring iteration."""
        evaluations = [
            HiringManagerEvaluation(score=7.0, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
            HiringManagerEvaluation(score=8.5, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),  # best
            HiringManagerEvaluation(score=7.5, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
        ]
        revised_cvs = ["# Rev1", "# Rev2"]  # revisions between iterations 0→1 and 1→2

        cv_optimizer = AsyncMock()
        cv_optimizer.revise = AsyncMock(side_effect=revised_cvs)

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock(evaluations)
        orchestrator._cv_optimizer = cv_optimizer
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=3, score_threshold=9.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        # iteration 1 (index 1) scored 8.5 — best; its CV is what was sent into iteration 1's eval
        # That's the CV after the first revision: "# Rev1"
        assert result.best_score == pytest.approx(8.5)
        assert result.optimized_cv == "# Rev1"

    @pytest.mark.asyncio
    async def test_cover_letter_generated_exactly_once(self):
        """CoverLetterFinalizer.generate_cover_letter must be called exactly once."""
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([HIGH_SCORE_EVALUATION])
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        cover_letter_mock = _make_cover_letter_mock()
        orchestrator._cover_letter_finalizer = cover_letter_mock

        config = OptimizationConfig(max_iterations=5, score_threshold=8.5)
        await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        cover_letter_mock.generate_cover_letter.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_called_per_iteration(self):
        """broadcast_iteration_fn must be called once per completed iteration."""
        evaluations = [
            HiringManagerEvaluation(score=6.0 + i * 0.1, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r")
            for i in range(3)
        ]
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock(evaluations)
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        broadcasts = []

        async def _capture_broadcast(record):
            broadcasts.append(record)

        config = OptimizationConfig(max_iterations=3, score_threshold=9.5)
        await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_capture_broadcast,
        )

        assert len(broadcasts) == 3


# =============================================================================
# OptimizationResult serialization
# =============================================================================


class TestOptimizationResultSerialization:
    @pytest.mark.asyncio
    async def test_to_dict_has_all_required_fields(self):
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([HIGH_SCORE_EVALUATION])
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock("Cover letter text")

        config = OptimizationConfig(max_iterations=5, score_threshold=8.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_noop_broadcast,
        )

        d = result.to_dict()
        required_keys = [
            "status", "started_at", "completed_at", "stop_reason",
            "config", "iteration_history", "best_iteration", "best_score",
            "optimized_cv", "cover_letter", "gap_analysis",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

        assert d["status"] == "completed"
        assert d["cover_letter"] == "Cover letter text"
        assert isinstance(d["iteration_history"], list)

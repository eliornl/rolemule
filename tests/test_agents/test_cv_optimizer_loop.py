"""
Unit tests for cv_optimizer_loop: CVOptimizerAgent, CoverLetterFinalizer,
CVOptimizationOrchestrator, and _compose_cv_from_profile.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agents.hiring_manager import HiringManagerEvaluation
from agents.cv_optimizer_loop import (
    CVOptimizerAgent,
    CoverLetterFinalizer,
    CVOptimizationOrchestrator,
    OptimizationConfig,
    _accept_cv_revision,
    _compose_cv_from_profile,
    _employment_dates_preserved,
    _profile_date_markers,
    _strip_editor_annotations,
    sanitize_application_text,
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
    return None


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

    def test_accomplishments_as_string_included(self):
        profile = {
            "full_name": "Bob",
            "work_experience": [
                {
                    "title": "Engineer",
                    "company": "BigCo",
                    "accomplishments": "Single paragraph of achievements",
                }
            ],
        }
        cv = _compose_cv_from_profile(profile)
        assert "Single paragraph of achievements" in cv


# =============================================================================
# Factuality guardrails
# =============================================================================


class TestSanitizeApplicationText:
    def test_strips_needs_clarification_markers(self):
        raw = "Built systems [NEEDS CLARIFICATION: confirm team size] for clients."
        cleaned = sanitize_application_text(raw)
        assert "NEEDS CLARIFICATION" not in cleaned
        assert "Built systems" in cleaned
        assert "for clients" in cleaned

    def test_strips_adjusted_date_editor_notes(self):
        raw = "*2020-12–Present*\n[Adjusted start date to meet requirement]"
        cleaned = sanitize_application_text(raw)
        assert "Adjusted start date" not in cleaned
        assert "2020-12" in cleaned

    def test_empty_input_returns_empty(self):
        assert _strip_editor_annotations("") == ""
        assert sanitize_application_text("") == ""


class TestEmploymentDatesPreserved:
    def test_detects_removed_profile_date(self):
        profile = {
            "work_experience": [
                {"title": "Engineer", "company": "Co", "start_date": "2020-12", "is_current": True},
            ],
        }
        baseline = _compose_cv_from_profile(profile)
        revised = baseline.replace("2020-12", "2020-02")
        assert not _employment_dates_preserved(baseline, revised, profile)

    def test_accepts_rephrase_with_same_dates(self):
        profile = {
            "work_experience": [
                {"title": "Engineer", "company": "Co", "start_date": "2020-12", "is_current": True},
            ],
        }
        baseline = _compose_cv_from_profile(profile)
        revised = baseline + "\n- Highlighted relevant backend work"
        assert _employment_dates_preserved(baseline, revised, profile)

    def test_education_date_markers_collected(self):
        profile = {
            "education": [
                {
                    "institution": "State U",
                    "start_date": "2014-09",
                    "end_date": "2018-05",
                }
            ],
        }
        markers = _profile_date_markers(profile)
        assert "2014-09" in markers
        assert "2018-05" in markers

    def test_education_current_enrollment_adds_present_marker(self):
        profile = {
            "education": [
                {"institution": "Online U", "start_date": "2024-01", "is_current": True},
            ],
        }
        markers = _profile_date_markers(profile)
        assert "Present" in markers


class TestAcceptCvRevision:
    def test_rejects_revision_that_changes_dates(self):
        profile = {
            "work_experience": [
                {"title": "Engineer", "company": "Co", "start_date": "2020-12", "is_current": True},
            ],
        }
        baseline = _compose_cv_from_profile(profile)
        bad = baseline.replace("2020-12", "2019-01")
        result, accepted = _accept_cv_revision(baseline, bad, baseline, profile)
        assert not accepted
        assert result == baseline

    def test_sanitizes_and_accepts_valid_revision(self):
        profile = {"full_name": "Bob", "summary": "Engineer"}
        baseline = _compose_cv_from_profile(profile)
        revised = baseline + "\n[NEEDS CLARIFICATION: extra detail]"
        result, accepted = _accept_cv_revision(baseline, revised, baseline, profile)
        assert accepted
        assert "NEEDS CLARIFICATION" not in result

    def test_rejects_revision_that_sanitizes_to_empty(self):
        profile = {"full_name": "Bob", "summary": "Engineer"}
        baseline = _compose_cv_from_profile(profile)
        result, accepted = _accept_cv_revision(
            baseline, "[NEEDS CLARIFICATION: only note]", baseline, profile
        )
        assert not accepted
        assert result == baseline


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

    @pytest.mark.asyncio
    async def test_revise_rejects_date_change_from_profile(self):
        profile = {
            "full_name": "Jane",
            "work_experience": [
                {"title": "Engineer", "company": "ACME", "start_date": "2020-12", "is_current": True},
            ],
        }
        baseline = _compose_cv_from_profile(profile)
        bad_revision = baseline.replace("2020-12", "2018-01")

        client = AsyncMock()
        client.generate.return_value = {"response": bad_revision, "filtered": False}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await agent.revise(
                cv_text=baseline,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
                profile_source_cv=baseline,
                user_profile=profile,
            )
        assert result == baseline
        assert "2018-01" not in result

    @pytest.mark.asyncio
    async def test_revise_strips_needs_clarification_from_output(self):
        profile = {"full_name": "Jane", "summary": "Engineer"}
        baseline = _compose_cv_from_profile(profile)
        revised = baseline + "\nSkill [NEEDS CLARIFICATION: confirm Golang depth]"

        client = AsyncMock()
        client.generate.return_value = {"response": revised, "filtered": False}
        agent = CVOptimizerAgent()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            result = await agent.revise(
                cv_text=baseline,
                job_description=SAMPLE_JD,
                evaluation=SAMPLE_EVALUATION,
                iteration=1,
                profile_source_cv=baseline,
                user_profile=profile,
            )
        assert "NEEDS CLARIFICATION" not in result


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


    @pytest.mark.asyncio
    async def test_includes_culture_context_without_overview(self):
        client = AsyncMock()
        client.generate.return_value = {
            "response": "Dear Hiring Team,\nCulture fit...\nBest regards,",
            "filtered": False,
        }
        finalizer = CoverLetterFinalizer()
        with patch("agents.cv_optimizer_loop.get_gemini_client", return_value=client):
            await finalizer.generate_cover_letter(
                optimized_cv=SAMPLE_CV,
                job_description=SAMPLE_JD,
                job_analysis=SAMPLE_JOB_ANALYSIS,
                company_research={"culture_and_values": "Collaborative, async-friendly team"},
                user_api_key="byok-key",
            )
        prompt = client.generate.call_args.kwargs.get("prompt", "")
        assert "Culture:" in prompt


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

    @pytest.mark.asyncio
    async def test_broadcast_failure_does_not_stop_loop(self):
        evaluations = [
            HiringManagerEvaluation(score=6.0, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
            HiringManagerEvaluation(score=6.1, strengths=["s"], gaps=["g"], action_items=["a"], reasoning="r"),
        ]

        async def _failing_broadcast(record):
            raise RuntimeError("websocket down")

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock(evaluations)
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=2, score_threshold=9.5)
        result = await orchestrator.run(
            session_id="test-session",
            user_id="test-user",
            initial_cv=SAMPLE_CV,
            job_description=SAMPLE_JD,
            job_analysis=SAMPLE_JOB_ANALYSIS,
            company_research=None,
            config=config,
            user_api_key="test-key",
            broadcast_iteration_fn=_failing_broadcast,
        )

        assert len(result.iteration_history) == 2

    @pytest.mark.asyncio
    async def test_revise_non_quota_exception_propagates(self):
        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([SAMPLE_EVALUATION])
        cv_optimizer = AsyncMock()
        cv_optimizer.revise = AsyncMock(side_effect=RuntimeError("revise failed"))
        orchestrator._cv_optimizer = cv_optimizer
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=3, score_threshold=9.5)
        with pytest.raises(RuntimeError, match="revise failed"):
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

    @pytest.mark.asyncio
    async def test_cover_letter_non_quota_exception_propagates(self):
        cover_letter_mock = AsyncMock()
        cover_letter_mock.generate_cover_letter = AsyncMock(
            side_effect=RuntimeError("cover letter failed")
        )

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([HIGH_SCORE_EVALUATION])
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = cover_letter_mock

        config = OptimizationConfig(max_iterations=5, score_threshold=8.5)
        with pytest.raises(RuntimeError, match="cover letter failed"):
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

    def test_compute_gap_analysis_empty_history(self):
        orchestrator = CVOptimizationOrchestrator()
        assert orchestrator._compute_gap_analysis([], 0) == []


# =============================================================================
# API rate limit — partial results
# =============================================================================


class TestCVOptimizerRateLimitPartial:
    @pytest.mark.asyncio
    async def test_evaluate_quota_mid_run_returns_partial(self):
        """After at least one iteration, evaluate quota should save partial progress."""
        quota_exc = RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
        hm = AsyncMock()
        hm.evaluate = AsyncMock(side_effect=[SAMPLE_EVALUATION, quota_exc])

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = hm
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        cover_letter_mock = _make_cover_letter_mock()
        orchestrator._cover_letter_finalizer = cover_letter_mock

        config = OptimizationConfig(max_iterations=5, score_threshold=9.5)
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

        assert result.status == "partial"
        assert result.stop_reason == "api_rate_limit"
        assert len(result.iteration_history) == 1
        assert result.best_score == pytest.approx(7.0)
        cover_letter_mock.generate_cover_letter.assert_not_called()

    @pytest.mark.asyncio
    async def test_revise_quota_mid_run_returns_partial(self):
        """Revise quota after a completed iteration should save partial progress."""
        quota_exc = RuntimeError("429 RESOURCE_EXHAUSTED. quota exceeded")
        cv_optimizer = AsyncMock()
        cv_optimizer.revise = AsyncMock(side_effect=quota_exc)

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([SAMPLE_EVALUATION])
        orchestrator._cv_optimizer = cv_optimizer
        cover_letter_mock = _make_cover_letter_mock()
        orchestrator._cover_letter_finalizer = cover_letter_mock

        config = OptimizationConfig(max_iterations=5, score_threshold=9.5)
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

        assert result.status == "partial"
        assert result.stop_reason == "api_rate_limit"
        assert len(result.iteration_history) == 1
        cover_letter_mock.generate_cover_letter.assert_not_called()

    @pytest.mark.asyncio
    async def test_cover_letter_quota_returns_partial_with_cv(self):
        """Cover letter quota after a successful loop should still return optimized CV."""
        quota_exc = RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
        cover_letter_mock = AsyncMock()
        cover_letter_mock.generate_cover_letter = AsyncMock(side_effect=quota_exc)

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = _make_hiring_manager_mock([HIGH_SCORE_EVALUATION])
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = cover_letter_mock

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

        assert result.status == "partial"
        assert result.stop_reason == "api_rate_limit"
        assert len(result.iteration_history) == 1
        assert result.optimized_cv
        assert result.cover_letter == ""

    @pytest.mark.asyncio
    async def test_first_evaluate_quota_still_raises(self):
        """Quota on the first evaluate (no progress) must propagate — no partial result."""
        quota_exc = RuntimeError("429 RESOURCE_EXHAUSTED. quota exceeded")
        hm = AsyncMock()
        hm.evaluate = AsyncMock(side_effect=quota_exc)

        orchestrator = CVOptimizationOrchestrator()
        orchestrator._hiring_manager = hm
        orchestrator._cv_optimizer = _make_cv_optimizer_mock()
        orchestrator._cover_letter_finalizer = _make_cover_letter_mock()

        config = OptimizationConfig(max_iterations=5, score_threshold=9.5)
        with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
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

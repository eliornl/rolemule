"""
Extended unit tests for agent private formatters and edge-case branches.
Targets remaining line gaps in cover_letter_writer, resume_advisor, interview_prep,
job_analyzer, and profile_matching without LLM calls.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agents.cover_letter_writer import CoverLetterWriterAgent
from agents.interview_prep import InterviewPrepAgent
from agents.job_analyzer import JobAnalyzerAgent, _validate_posted_date, _normalize_string_list
from agents.profile_matching import ProfileMatchingAgent
from agents.resume_advisor import ResumeAdvisorAgent
from workflows.state_schema import InputMethod


@pytest.fixture
def mock_gemini_client():
    client = AsyncMock()
    client.generate.return_value = {
        "response": "Dear Hiring Manager,\n\nBody\n\nJane",
        "filtered": False,
    }
    return client


def _rich_profile() -> dict:
    return {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "professional_title": "Engineer",
        "years_experience": 6,
        "city": "Austin",
        "state": "TX",
        "country": "US",
        "summary": "Backend specialist.",
        "skills": ["Python", "Go"],
        "is_student": True,
        "requires_visa_sponsorship": True,
        "has_security_clearance": True,
        "work_experience": [
            {
                "job_title": "Senior Engineer",
                "company": "Acme",
                "start_date": "2020-01",
                "end_date": "Present",
                "is_current": True,
                "description": "Built APIs " + ("x" * 520),
            }
        ],
        "education": [
            {
                "institution": "State U",
                "degree": "BS",
                "field_of_study": "CS",
                "start_date": "2014",
                "end_date": "2018",
            }
        ],
        "desired_salary_range": {"min": 120000, "max": 160000},
        "work_arrangements": ["Remote"],
        "job_types": ["full-time"],
        "desired_company_sizes": ["startup"],
        "willing_to_relocate": True,
        "max_travel_preference": "25%",
        "work_authorization": "us_citizen",
    }


def _rich_job() -> dict:
    return {
        "job_title": "Staff Engineer",
        "company_name": "Globex",
        "industry": "SaaS",
        "job_city": "Remote",
        "job_state": "",
        "job_country": "US",
        "additional_locations": ["NYC", "Seattle"],
        "work_arrangement": "remote",
        "employment_type": "full-time",
        "company_size": "500-1000",
        "years_experience_required": 5,
        "required_skills": ["Python", "PostgreSQL"],
        "soft_skills": ["Communication"],
        "required_qualifications": ["BS in CS", "Cloud experience"],
        "preferred_qualifications": ["Kubernetes"],
        "responsibilities": ["Design services", "Mentor juniors"],
        "benefits": ["401k", "Health"],
        "ats_keywords": ["python", "postgres"],
        "salary_range": {"min": 150000, "max": 190000},
        "team_info": "Platform team",
        "is_student_position": False,
        "visa_sponsorship": True,
        "security_clearance": False,
        "max_travel_preference": "10%",
    }


def _rich_matching() -> dict:
    return {
        "executive_summary": {
            "recommendation": "STRONG_MATCH",
            "one_line_verdict": "Great fit",
            "fit_assessment": "Strong alignment",
        },
        "qualification_score": 0.82,
        "preference_score": 0.75,
        "overall_score": 0.8,
        "qualification_analysis": {
            "skills_assessment": {
                "matched_skills": [
                    {"skill": "Python", "evidence": "5 years", "strength": "HIGH"},
                    "SQL",
                ],
                "missing_critical_skills": [
                    {"skill": "Rust", "importance": "MEDIUM", "can_learn_quickly": True}
                ],
                "hidden_skills": [{"skill": "Leadership", "reasoning": "Led migrations"}],
            },
            "experience_assessment": {
                "years_evaluation": {
                    "candidate_years": 6,
                    "required_years": 5,
                    "assessment": "Meets requirement",
                }
            },
        },
        "application_strategy": {
            "key_talking_points": ["Scale experience"],
            "address_these_concerns": [
                {"concern": "Gap", "how_to_address": "Frame as learning"},
                "Short tenure",
            ],
            "cover_letter_angle": "Lead with platform wins",
        },
        "competitive_positioning": {
            "unique_value_proposition": "Rare mix of backend + leadership",
            "strengths_vs_typical_applicant": ["Depth in Python"],
        },
        "deal_breaker_analysis": {
            "deal_breakers_found": [{"issue": "Remote only", "severity": "LOW"}],
        },
        "risk_assessment": {
            "candidate_risks": [{"risk": "Overqualified"}],
            "red_flags_for_candidate": ["Long commute if onsite"],
        },
        "final_scores": {"overall_match_score": 0.8, "qualification_score": 0.82},
    }


def _rich_company() -> dict:
    return {
        "company_size": "1000+",
        "industry": "Technology",
        "mission_vision": "M" * 600,
        "core_values": ["Innovation", "Integrity"],
        "what_to_emphasize": ["Ownership"],
        "application_insights": {
            "what_to_emphasize": ["Impact metrics"],
            "culture_fit_signals": ["Collaboration"],
        },
        "recent_news": [
            {"headline": "Launch", "summary": "New product"},
            "Plain news string " + ("n" * 200),
        ],
        "company_overview": {"key_products_services": ["Platform", "Analytics"]},
        "competitive_landscape": {"competitive_advantages": ["Speed", "Quality"]},
        "typical_interview_process": ["Recruiter", "Panel"],
        "interview_format": "Virtual",
        "work_environment": "Async-friendly",
    }


class TestCoverLetterFormatters:
    def test_format_helpers_cover_all_sections(self, mock_gemini_client):
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        profile_text = agent._format_profile(_rich_profile())
        assert "Education:" in profile_text
        assert "Senior Engineer" in profile_text

        job_text = agent._format_job(_rich_job())
        assert "KEY TECHNICAL SKILLS" in job_text
        assert "Team Context" in job_text

        match_text = agent._format_matching(_rich_matching())
        assert "STRENGTHS TO HIGHLIGHT" in match_text
        assert "RECOMMENDED NARRATIVE ANGLE" in match_text

    def test_format_matching_string_gap_and_hidden_skill(self, mock_gemini_client):
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        matching = _rich_matching()
        matching["qualification_analysis"]["skills_assessment"]["missing_critical_skills"].append(
            "GraphQL experience"
        )
        matching["qualification_analysis"]["skills_assessment"]["hidden_skills"].append(
            "Informal mentoring"
        )
        match_text = agent._format_matching(matching)
        assert "GraphQL experience" in match_text
        assert "Informal mentoring" in match_text

        company_text = agent._format_company(_rich_company())
        assert "COMPANY MISSION" in company_text
        assert "RECENT NEWS" in company_text

    def test_format_matching_and_company_empty(self, mock_gemini_client):
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        assert "general strong cover letter" in agent._format_matching(None)
        assert "Limited company information" in agent._format_company(None)

    @pytest.mark.asyncio
    async def test_generate_letter_timeout(self, mock_gemini_client):
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None
        slow = AsyncMock()

        async def _slow(**kwargs):
            await asyncio.sleep(5)

        slow.generate = _slow
        agent.gemini_client = slow
        with patch("agents.cover_letter_writer.LLM_TIMEOUT", 0.01):
            with pytest.raises(Exception, match="timed out"):
                await agent._generate_cover_letter(
                    _rich_profile(),
                    _rich_job(),
                    _rich_matching(),
                    _rich_company(),
                    user_tone="enthusiastic",
                    user_model="gemini-2.5-flash",
                )

    @pytest.mark.asyncio
    async def test_generate_letter_empty_response_raises(self, mock_gemini_client):
        agent = CoverLetterWriterAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None
        mock_gemini_client.generate.return_value = {"response": "  ", "filtered": False}
        with pytest.raises(Exception, match="Empty response"):
            await agent._generate_cover_letter(
                _rich_profile(), _rich_job(), None, None, user_tone="professional"
            )


class TestResumeAdvisorFormatters:
    def test_format_helpers(self, mock_gemini_client):
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        assert "Special Considerations" in agent._format_profile(_rich_profile())
        assert "ATS Keywords" in agent._format_job(_rich_job())
        assert "Key Points to Emphasize" in agent._format_matching(_rich_matching())
        assert agent._format_company(_rich_company())
        assert agent._format_company(None) == "No company research available"

    @pytest.mark.asyncio
    async def test_generate_recommendations_timeout_returns_fallback(self, mock_gemini_client):
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None
        with patch(
            "agents.resume_advisor.asyncio.wait_for",
            side_effect=asyncio.TimeoutError(),
        ):
            result = await agent._generate_recommendations(
                _rich_profile(), _rich_job(), _rich_matching(), _rich_company()
            )
        assert result.get("error") is True
        assert "timed out" in result.get("error_message", "").lower()

    @pytest.mark.asyncio
    async def test_generate_recommendations_exception_returns_fallback(self, mock_gemini_client):
        agent = ResumeAdvisorAgent(gemini_client=mock_gemini_client)
        agent._current_user_api_key = None
        mock_gemini_client.generate.side_effect = RuntimeError("LLM unavailable")
        result = await agent._generate_recommendations(
            _rich_profile(), _rich_job(), _rich_matching(), _rich_company()
        )
        assert result.get("error") or "LLM unavailable" in str(result)


class TestInterviewPrepFormatters:
    def test_format_helpers(self):
        agent = InterviewPrepAgent()
        assert "REQUIRED SKILLS" in agent._format_job_info(_rich_job())
        assert "TYPICAL INTERVIEW PROCESS" in agent._format_company_info(_rich_company())
        assert "WORK EXPERIENCE" in agent._format_profile_info(_rich_profile())
        assert "SKILL GAPS" in agent._format_matching_insights(_rich_matching())
        assert agent._format_job_info({}) != ""
        assert "No company research" in agent._format_company_info({})
        assert "No profile" in agent._format_profile_info({})
        assert "No matching analysis" in agent._format_matching_insights({})


class TestProfileMatchingFormatters:
    def test_format_profile_and_job(self):
        agent = ProfileMatchingAgent()
        profile_text = agent._format_user_profile(_rich_profile())
        assert "JOB PREFERENCES" in profile_text
        assert "Program 1" in profile_text

        job_text = agent._format_job_analysis(_rich_job())
        assert "COMPENSATION" in job_text
        assert "ATS/IMPORTANT KEYWORDS" in job_text

        sparse_job = {"job_title": "Role", "salary_range": "120k-140k"}
        assert "120k-140k" in agent._format_job_analysis(sparse_job)

    def test_format_profile_sparse_sections_and_salary_fallback(self):
        agent = ProfileMatchingAgent()
        sparse_profile = {
            "full_name": "Pat Lee",
            "work_experience": [],
            "education": [
                {
                    "institution": "Online U",
                    "degree": "MS",
                    "start_date": "2024-01",
                    "is_current": True,
                }
            ],
            "desired_salary_range": {"min": "120k", "max": "140k"},
        }
        profile_text = agent._format_user_profile(sparse_profile)
        assert "No work experience listed" in profile_text
        assert "currently enrolled" in profile_text
        assert "120k" in profile_text

        bad_job = {
            "job_title": "Role",
            "salary_range": {"min": object(), "max": object()},
        }
        job_text = agent._format_job_analysis(bad_job)
        assert "COMPENSATION" in job_text

    def test_format_profile_without_salary_range(self):
        agent = ProfileMatchingAgent()
        profile_text = agent._format_user_profile({"full_name": "No Salary"})
        assert "Not specified" in profile_text


class TestJobAnalyzerHelpers:
    def test_validate_posted_date_future_rejected(self):
        future = (datetime.now(timezone.utc).replace(year=2030)).strftime("%Y-%m-%d")
        assert _validate_posted_date(future) is None

    def test_validate_posted_date_valid(self):
        assert _validate_posted_date("2026-03-01") == "2026-03-01"

    def test_validate_posted_date_too_old(self):
        assert _validate_posted_date("2020-01-01") is None

    @pytest.mark.asyncio
    async def test_process_uses_cache_hit(self):
        client = AsyncMock()
        agent = JobAnalyzerAgent(gemini_client=client)
        state = {
            "session_id": "s1",
            "job_input_data": {
                "input_method": InputMethod.MANUAL.value,
                "job_content": "x" * 100,
            },
        }
        cached = {"job_title": "Cached Role", "company_name": "Co"}
        with patch(
            "agents.job_analyzer.get_cached_job_analysis",
            AsyncMock(return_value=cached),
        ):
            result = await agent.process(state)
        assert result["job_analysis"]["from_cache"] is True
        client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_stampede_waits_for_cache(self):
        client = AsyncMock()
        agent = JobAnalyzerAgent(gemini_client=client)
        state = {
            "session_id": "s2",
            "job_input_data": {
                "input_method": InputMethod.MANUAL.value,
                "job_content": "y" * 100,
            },
        }
        cached = {"job_title": "Wait Role", "company_name": "WaitCo"}

        async def _second_lookup(*args, **kwargs):
            _second_lookup.calls += 1
            if _second_lookup.calls >= 2:
                return cached
            return None

        _second_lookup.calls = 0

        with patch("agents.job_analyzer.get_cached_job_analysis", side_effect=_second_lookup), \
             patch("agents.job_analyzer.acquire_compute_lock", AsyncMock(return_value=False)), \
             patch("agents.job_analyzer.release_compute_lock", AsyncMock()), \
             patch("agents.job_analyzer.asyncio.sleep", AsyncMock()):
            result = await agent.process(state)
        assert result["job_analysis"]["job_title"] == "Wait Role"

    def test_normalize_string_list_dict_without_known_keys(self):
        assert _normalize_string_list([{"foo": "bar"}]) == []

    def test_normalize_string_list_unsupported_scalar(self):
        assert _normalize_string_list(42) == []

    def test_validate_posted_date_unparseable(self):
        assert _validate_posted_date("not-a-real-date") is None

    def test_validate_posted_date_unexpected_exception(self):
        with patch("agents.job_analyzer.datetime") as mock_dt:
            mock_dt.strptime.side_effect = RuntimeError("boom")
            assert _validate_posted_date("2026-03-01") is None

    @pytest.mark.asyncio
    async def test_process_missing_job_content_raises(self):
        client = AsyncMock()
        agent = JobAnalyzerAgent(gemini_client=client)
        state = {
            "session_id": "s-missing",
            "job_input_data": {
                "input_method": InputMethod.FILE.value,
                "job_content": "",
            },
        }
        with patch("agents.job_analyzer.get_cached_job_analysis", AsyncMock(return_value=None)), \
             patch("agents.job_analyzer.acquire_compute_lock", AsyncMock(return_value=True)), \
             patch("agents.job_analyzer.release_compute_lock", AsyncMock()):
            with pytest.raises(ValueError, match="Job content is required"):
                await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_timeout_propagates(self):
        client = AsyncMock()
        agent = JobAnalyzerAgent(gemini_client=client)
        state = {
            "session_id": "s-timeout",
            "job_input_data": {
                "input_method": InputMethod.MANUAL.value,
                "job_content": "x" * 100,
            },
        }
        with patch(
            "agents.job_analyzer.get_cached_job_analysis",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            with pytest.raises(asyncio.TimeoutError):
                await agent.process(state)

    @pytest.mark.asyncio
    async def test_process_lock_wait_timeout_computes(self):
        client = AsyncMock()
        client.generate.return_value = {
            "response": '{"job_title": "Lock Timeout Role", "company_name": "Co"}',
            "filtered": False,
        }
        agent = JobAnalyzerAgent(gemini_client=client)
        state = {
            "session_id": "s-lock-timeout",
            "job_input_data": {
                "input_method": InputMethod.MANUAL.value,
                "job_content": "z" * 100,
            },
        }
        with patch("agents.job_analyzer.get_cached_job_analysis", AsyncMock(return_value=None)), \
             patch("agents.job_analyzer.acquire_compute_lock", AsyncMock(return_value=False)), \
             patch("agents.job_analyzer.release_compute_lock", AsyncMock()), \
             patch("agents.job_analyzer.cache_job_analysis", AsyncMock()), \
             patch("agents.job_analyzer.asyncio.sleep", AsyncMock()):
            result = await agent.process(state)
        assert result["job_analysis"]["job_title"] == "Lock Timeout Role"
        client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_json_decode_error_wrapped(self):
        client = AsyncMock()
        client.generate.return_value = {"response": "{bad", "filtered": False}
        agent = JobAnalyzerAgent(gemini_client=client)
        agent._current_user_api_key = None
        with patch(
            "agents.job_analyzer.parse_json_from_llm_response",
            side_effect=__import__("json").JSONDecodeError("bad", "", 0),
        ):
            with pytest.raises(ValueError, match="Failed to parse AI response as JSON"):
                await agent._parse_generic_job_content("x" * 100, "manual")

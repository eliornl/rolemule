"""
Unit tests for workflows/state_schema.py — enums, dataclasses, helpers, initial state.
"""

import pytest
from datetime import datetime, timezone

from workflows.state_schema import (
    InputMethod,
    UserProfile,
    JobInputData,
    NodeName,
    WorkflowPhase,
    WorkflowStatus,
    AgentStatus,
    Agent,
    JobAnalysisResult,
    ProfileMatchingResult,
    CompanyResearchResult,
    ResumeRecommendationsResult,
    CoverLetterResult,
    datetime_to_string,
    get_current_time_string,
    agent_to_key,
    key_to_agent,
    REQUIRED_AGENTS,
    DEFAULT_AGENT_STATUS,
    create_initial_state,
    add_error,
    add_warning,
)


def _sample_user_profile() -> UserProfile:
    return UserProfile(
        user_id="u-1",
        full_name="Jane Doe",
        email="jane@example.com",
        city="Austin",
        state="TX",
        country="US",
        years_experience=5,
        is_student=False,
        professional_title="Engineer",
        summary="Experienced builder.",
        work_experience=[{"title": "Dev", "company": "Co"}],
        skills=["Python"],
        desired_salary_range={"min": 100000, "max": 150000},
        desired_company_sizes=["startup"],
        job_types=["full-time"],
        work_arrangements=["remote"],
        willing_to_relocate=False,
        requires_visa_sponsorship=False,
        has_security_clearance=False,
        max_travel_preference="10%",
    )


def _sample_job_input(**overrides) -> JobInputData:
    base = dict(
        input_method=InputMethod.MANUAL,
        job_title="Backend Engineer",
        company_name="Acme",
        job_content="We need a backend engineer with Python and PostgreSQL experience.",
    )
    base.update(overrides)
    return JobInputData(**base)


class TestEnumsAndHelpers:
    def test_input_method_values(self):
        assert InputMethod.TEXT.value == "text"
        assert InputMethod.EXTENSION.value == "extension"

    def test_datetime_to_string_and_current_time(self):
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert datetime_to_string(dt).startswith("2026-01-15")
        assert "T" in get_current_time_string()

    def test_agent_key_roundtrip(self):
        assert agent_to_key(Agent.JOB_ANALYZER) == "job_analyzer"
        assert key_to_agent("cover_letter_writer") == Agent.COVER_LETTER_WRITER

    def test_required_agents_and_defaults(self):
        assert len(REQUIRED_AGENTS) == 5
        assert DEFAULT_AGENT_STATUS[Agent.PROFILE_MATCHING] == AgentStatus.PENDING

    def test_node_and_phase_enums(self):
        assert NodeName.ERROR_HANDLER.value == "error_handler"
        assert WorkflowPhase.COMPLETED.value == "completed"
        assert WorkflowStatus.AWAITING_CONFIRMATION.value == "awaiting_confirmation"


class TestJobInputDataValidation:
    def test_url_method_requires_http_job_url(self):
        with pytest.raises(ValueError, match="job_url is required"):
            JobInputData(
                input_method=InputMethod.URL,
                job_title="Role",
                company_name="Co",
            )

    def test_manual_requires_job_content(self):
        with pytest.raises(ValueError, match="job_content is required"):
            JobInputData(
                input_method=InputMethod.MANUAL,
                job_title="Role",
                company_name="Co",
            )

    def test_invalid_job_url_scheme(self):
        with pytest.raises(ValueError, match="http"):
            JobInputData(
                input_method=InputMethod.URL,
                job_title="Role",
                company_name="Co",
                job_url="ftp://bad.example/job",
            )

    def test_title_and_company_length_limits(self):
        with pytest.raises(ValueError, match="job_title exceeds"):
            JobInputData(
                input_method=InputMethod.MANUAL,
                job_title="x" * 501,
                company_name="Co",
                job_content="Enough text for validation.",
            )
        with pytest.raises(ValueError, match="company_name exceeds"):
            JobInputData(
                input_method=InputMethod.MANUAL,
                job_title="Role",
                company_name="c" * 256,
                job_content="Enough text for validation.",
            )

    def test_to_dict(self):
        data = _sample_job_input()
        d = data.to_dict()
        assert d["company_name"] == "Acme"
        assert d["input_method"] == InputMethod.MANUAL


class TestUserProfileAndResultDataclasses:
    def test_user_profile_to_dict(self):
        profile = _sample_user_profile()
        d = profile.to_dict()
        assert d["email"] == "jane@example.com"
        assert d["skills"] == ["Python"]

    def test_result_dataclass_to_dict(self):
        assert JobAnalysisResult(job_title="Dev").to_dict()["job_title"] == "Dev"
        assert ProfileMatchingResult(overall_score=0.8).to_dict()["overall_score"] == 0.8
        assert CompanyResearchResult(industry="Tech").to_dict()["industry"] == "Tech"
        assert ResumeRecommendationsResult().to_dict()["analysis_method"] == "EXPERT_LLM"
        assert CoverLetterResult(content="Hello").to_dict()["content"] == "Hello"


class TestCreateInitialState:
    def test_creates_full_workflow_state(self):
        profile = _sample_user_profile()
        job = _sample_job_input()
        state = create_initial_state(
            user_id="u-1",
            session_id="sess-1",
            user_profile=profile,
            job_input_data=job,
            user_api_key="key-abc",
            workflow_preferences={"auto_generate_documents": True},
        )
        assert state["session_id"] == "sess-1"
        assert state["user_api_key"] == "key-abc"
        assert state["workflow_preferences"]["auto_generate_documents"] is True
        assert state["workflow_status"] == WorkflowStatus.INITIALIZED
        assert state["agent_status"]["job_analyzer"] == AgentStatus.PENDING
        assert state["job_analysis"] is None

    def test_accepts_dict_inputs(self):
        state = create_initial_state(
            user_id="u-2",
            session_id="sess-2",
            user_profile={"full_name": "Bob"},
            job_input_data={"input_method": "manual", "job_content": "text"},
        )
        assert state["user_profile"]["full_name"] == "Bob"


class TestAddErrorAndWarning:
    def test_add_error_appends_plain_message(self):
        state = create_initial_state(
            user_id="u",
            session_id="s",
            user_profile={"full_name": "A"},
            job_input_data={"input_method": "manual", "job_content": "x" * 80},
        )
        updated = add_error(state, "Something failed", "job_analyzer")
        assert updated["error_messages"] == ["Something failed"]

    def test_add_warning_appends_message(self):
        state = create_initial_state(
            user_id="u",
            session_id="s",
            user_profile={"full_name": "A"},
            job_input_data={"input_method": "manual", "job_content": "x" * 80},
        )
        updated = add_warning(state, "Minor issue")
        assert updated["warning_messages"] == ["Minor issue"]

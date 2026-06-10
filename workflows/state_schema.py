"""
Workflow state schema for LangGraph multi-agent system.
Defines the global state structure shared across all agents.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TypedDict
from enum import Enum
from dataclasses import dataclass, field, asdict


class InputMethod(str, Enum):
    """Input method for job data."""

    URL = "url"
    MANUAL = "manual"
    FILE = "file"
    TEXT = "text"  # Alias for MANUAL (used by API)
    EXTENSION = "extension"  # Content extracted via Chrome extension


@dataclass
class UserProfile:
    """User profile data structure."""

    # Basic user information
    user_id: str
    full_name: str
    email: str
    city: str
    state: str
    country: str
    years_experience: int
    is_student: bool
    professional_title: str
    summary: str

    # Profile sections
    work_experience: List[Dict[str, Any]]
    skills: List[str]

    # Job preferences
    desired_salary_range: Dict[str, Any]
    desired_company_sizes: List[str]
    job_types: List[str]
    work_arrangements: List[str]
    willing_to_relocate: bool
    requires_visa_sponsorship: bool
    has_security_clearance: bool
    max_travel_preference: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert UserProfile to dictionary."""
        return asdict(self)


@dataclass
class JobInputData:
    """Job input data structure."""

    input_method: InputMethod
    job_title: str
    company_name: str
    job_url: Optional[str] = None
    job_content: Optional[str] = None

    _MAX_TITLE_LEN = 500
    _MAX_COMPANY_LEN = 255

    def __post_init__(self):
        """Validate job input data consistency."""
        if self.input_method == InputMethod.URL and not self.job_url:
            raise ValueError("job_url is required when input_method is 'url'")
        if (
            self.input_method in [InputMethod.MANUAL, InputMethod.FILE]
            and not self.job_content
        ):
            raise ValueError(
                "job_content is required when input_method is 'manual' or 'file'"
            )
        if self.job_url and not self.job_url.startswith(("http://", "https://")):
            raise ValueError("job_url must start with http:// or https://")
        if len(self.job_title) > self._MAX_TITLE_LEN:
            raise ValueError(
                f"job_title exceeds maximum length of {self._MAX_TITLE_LEN} characters"
            )
        if len(self.company_name) > self._MAX_COMPANY_LEN:
            raise ValueError(
                f"company_name exceeds maximum length of {self._MAX_COMPANY_LEN} characters"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert JobInputData to dictionary."""
        return asdict(self)


class NodeName(str, Enum):
    """Node names for workflow graph."""

    JOB_ANALYZER = "job_analyzer"
    COMPANY_RESEARCH = "company_research"
    PROFILE_MATCHING = "profile_matching"
    DOCUMENT_GENERATION = "document_generation"
    ANALYSIS_COMPLETE = "analysis_complete"
    ERROR_HANDLER = "error_handler"


class WorkflowPhase(str, Enum):
    """Workflow processing phases."""

    INITIALIZATION = "initialization"
    JOB_ANALYSIS = "job_analysis"
    COMPANY_RESEARCH = "company_research"
    PROFILE_MATCHING = "profile_matching"
    DOCUMENT_GENERATION = "document_generation"
    ANALYSIS_COMPLETE = "analysis_complete"
    COMPLETED = "completed"
    ERROR = "error"


class WorkflowStatus(str, Enum):
    """Overall workflow status."""

    INITIALIZED = "initialized"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Paused at gate, waiting for user
    ANALYSIS_COMPLETE = "analysis_complete"  # Analysis done, documents not generated yet
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(str, Enum):
    """Individual agent processing status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Agent(str, Enum):
    """Available agents in the workflow."""

    JOB_ANALYZER = "job_analyzer"
    COMPANY_RESEARCH = "company_research"
    PROFILE_MATCHING = "profile_matching"
    RESUME_ADVISOR = "resume_advisor"
    COVER_LETTER_WRITER = "cover_letter_writer"


# Helper functions for datetime and agent key conversion


def datetime_to_string(dt: datetime) -> str:
    """Convert datetime to ISO format string for serialization."""
    return dt.isoformat()


def get_current_time_string() -> str:
    """Get current UTC time as ISO format string."""
    return datetime.now(timezone.utc).isoformat()


def agent_to_key(agent: Agent) -> str:
    """Convert Agent enum to string key."""
    return agent.value


def key_to_agent(key: str) -> Agent:
    """Convert string key back to Agent enum."""
    return Agent(key)


# Constants for workflow management
REQUIRED_AGENTS: List[Agent] = [
    Agent.JOB_ANALYZER,
    Agent.COMPANY_RESEARCH,
    Agent.PROFILE_MATCHING,
    Agent.RESUME_ADVISOR,
    Agent.COVER_LETTER_WRITER,
]

# Default agent status mapping for initialization
DEFAULT_AGENT_STATUS: Dict[Agent, AgentStatus] = {
    Agent.JOB_ANALYZER: AgentStatus.PENDING,
    Agent.COMPANY_RESEARCH: AgentStatus.PENDING,
    Agent.PROFILE_MATCHING: AgentStatus.PENDING,
    Agent.RESUME_ADVISOR: AgentStatus.PENDING,
    Agent.COVER_LETTER_WRITER: AgentStatus.PENDING,
}


@dataclass
class JobAnalysisResult:
    """Schema for job analysis results."""

    # Basic information
    source: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    job_city: Optional[str] = None
    job_state: Optional[str] = None
    job_country: Optional[str] = None
    additional_locations: Optional[List[str]] = field(default_factory=list)
    employment_type: Optional[str] = None
    work_arrangement: Optional[str] = None
    salary_range: Optional[Dict[str, Any]] = None
    posted_date: Optional[str] = None
    application_deadline: Optional[str] = None
    benefits: Optional[List[str]] = field(default_factory=list)
    job_type: Optional[str] = None
    is_student_position: Optional[bool] = None
    company_size: Optional[str] = None

    # Skills and qualifications
    required_skills: Optional[List[str]] = field(default_factory=list)
    soft_skills: Optional[List[str]] = field(default_factory=list)
    required_qualifications: Optional[List[str]] = field(default_factory=list)
    preferred_qualifications: Optional[List[str]] = field(default_factory=list)
    education_requirements: Optional[Dict[str, str]] = field(
        default_factory=dict
    )  # Object with institution, degree, and field
    years_experience_required: Optional[int] = None
    language_requirements: Optional[List[Dict[str, str]]] = field(
        default_factory=list
    )  # List of language requirements with proficiency levels

    # Classification and keywords
    industry: Optional[str] = None
    role_classification: Optional[str] = None
    keywords: Optional[List[str]] = field(default_factory=list)
    ats_keywords: Optional[List[str]] = field(default_factory=list)

    # Additional details
    visa_sponsorship: Optional[str] = None
    security_clearance: Optional[str] = None
    max_travel_preference: Optional[str] = None
    contact_information: Optional[str] = None

    # Role context (from LLM analysis)
    responsibilities: Optional[List[str]] = field(default_factory=list)
    team_info: Optional[str] = None
    reporting_to: Optional[str] = None

    # Processing metadata
    processing_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert JobAnalysisResult to dictionary."""
        return asdict(self)


@dataclass
class ProfileMatchingResult:
    """
    Schema for AI-powered profile matching analysis.
    
    This comprehensive analysis compares a candidate's profile against
    job requirements and provides actionable insights for application strategy.
    """

    # Executive Summary
    executive_summary: Dict[str, Any] = field(default_factory=dict)
    # Contains: fit_assessment, recommendation (STRONG_MATCH|GOOD_MATCH|MODERATE_MATCH|WEAK_MATCH|NOT_RECOMMENDED),
    #           confidence_level (HIGH|MEDIUM|LOW), one_line_verdict

    # Detailed Analysis Sections
    qualification_analysis: Dict[str, Any] = field(default_factory=dict)
    # Contains: overall_score, skills_assessment, experience_assessment, education_assessment

    preference_analysis: Dict[str, Any] = field(default_factory=dict)
    # Contains: overall_score, salary_fit, work_arrangement_fit, company_size_fit, job_type_fit, location_fit

    deal_breaker_analysis: Dict[str, Any] = field(default_factory=dict)
    # Contains: all_passed, visa_sponsorship, location_requirements, security_clearance, etc.

    # Strategic Insights
    competitive_positioning: Dict[str, Any] = field(default_factory=dict)
    # Contains: estimated_candidate_pool_percentile, strengths_vs_typical_applicant, unique_value_proposition

    application_strategy: Dict[str, Any] = field(default_factory=dict)
    # Contains: should_apply, application_priority, success_probability, key_talking_points, cover_letter_angle

    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    # Contains: concerns, mitigation_strategies, things_to_research, red_flags_for_candidate

    # Final Scores (0.0-1.0)
    final_scores: Dict[str, float] = field(default_factory=dict)
    # Contains: qualification_score, preference_score, deal_breaker_score, overall_match_score

    # AI Insights
    ai_insights: Dict[str, Any] = field(default_factory=dict)
    # Contains: unexpected_findings, career_advice, similar_roles_to_consider

    # Backward Compatibility Scores (extracted from final_scores)
    qualification_score: float = 0.0
    preference_score: float = 0.0
    deal_breaker_score: float = 0.0
    overall_score: float = 0.0

    # Metadata
    processing_time: float = 0.0
    analysis_method: str = "AI_POWERED"
    model_used: str = "gemini"

    def to_dict(self) -> Dict[str, Any]:
        """Convert ProfileMatchingResult to dictionary."""
        return asdict(self)


@dataclass
class CompanyResearchResult:
    """Schema for company research results from LLM-based research."""

    # Basic company information
    company_size: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    founded_year: Optional[int] = None
    website: Optional[str] = None
    mission_vision: Optional[str] = None
    key_products: List[str] = field(default_factory=list)
    recent_developments: Optional[str] = None

    # Company culture
    core_values: List[str] = field(default_factory=list)
    work_environment: Optional[str] = None
    employee_benefits: List[str] = field(default_factory=list)
    diversity_inclusion: Optional[str] = None
    remote_work_policy: Optional[str] = None
    employee_satisfaction: Optional[str] = None

    # Hiring/Interview information
    typical_interview_process: List[str] = field(default_factory=list)
    hiring_timeline: Optional[str] = None
    interview_format: Optional[str] = None
    assessment_methods: List[str] = field(default_factory=list)
    hiring_volume: Optional[str] = None

    # Leadership information
    leadership_info: List[Dict[str, Any]] = field(
        default_factory=list
    )  # Contains: name, title, background, tenure

    # Competitive landscape
    competitors: List[str] = field(default_factory=list)
    market_position: Optional[str] = None
    competitive_advantages: List[str] = field(default_factory=list)
    market_challenges: List[str] = field(default_factory=list)
    growth_opportunities: List[str] = field(default_factory=list)

    # Recent news
    recent_news: List[Dict[str, Any]] = field(
        default_factory=list
    )  # Contains: title, summary, date, relevance

    # Application insights (for job seekers)
    application_insights: Dict[str, Any] = field(default_factory=dict)
    # Contains: what_to_emphasize, culture_fit_signals, red_flags_to_watch

    # Confidence assessment
    confidence_assessment: Dict[str, Any] = field(default_factory=dict)
    # Contains: overall_confidence (HIGH|MEDIUM|LOW), uncertain_areas, recommendation

    # Research metadata
    research_date: Optional[str] = None
    processing_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert CompanyResearchResult to dictionary."""
        return asdict(self)


@dataclass
class ResumeRecommendationsResult:
    """
    Schema for resume advisory recommendations with comprehensive LLM-generated advice.
    
    Contains structured, actionable advice for optimizing a resume for a specific job.
    """

    # Comprehensive structured advice from LLM
    comprehensive_advice: Dict[str, Any] = field(default_factory=dict)
    # Contains:
    #   strategic_assessment: competitiveness, ats_pass_likelihood, interview_likelihood
    #   professional_summary: current_assessment, recommended_summary, key_elements
    #   experience_optimization: prioritization_strategy, roles_to_highlight, bullet_rewrites
    #   skills_section: must_include_skills, nice_to_have_skills, skills_to_remove
    #   ats_optimization: missing_keywords, keyword_placement_suggestions
    #   quick_wins: list of immediate high-impact changes
    #   red_flags_to_fix: list of concerns and how to address them
    #   final_checklist: before_submitting checks

    # Processing metadata
    processing_time: float = 0.0
    analysis_method: str = "EXPERT_LLM"

    def to_dict(self) -> Dict[str, Any]:
        """Convert ResumeRecommendationsResult to dictionary."""
        return asdict(self)


@dataclass
class CoverLetterResult:
    """Schema for cover letter with LLM-generated content."""

    # Complete cover letter content
    content: str = ""

    # Generation metadata
    generated_at: Optional[str] = None
    processing_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert CoverLetterResult to dictionary."""
        return asdict(self)


class WorkflowState(TypedDict):
    """
    Global state schema for the multi-agent workflow.

    This state is shared and updated by all agents in the LangGraph workflow.
    It contains all information needed to track workflow execution, agent results,
    and user data throughout the job application processing pipeline.
    """

    # Core Identifiers
    user_id: str
    session_id: str

    # User data
    user_profile: Dict[str, Any]

    # User API Key (BYOK - Bring Your Own Key)
    # This is the decrypted API key for LLM calls, passed through the workflow
    user_api_key: Optional[str]

    # Per-user workflow preferences (derived from UserProfile.application_preferences)
    # Keys: workflow_gate_threshold (float), auto_generate_documents (bool)
    workflow_preferences: Optional[Dict[str, Any]]

    # Job Input Data
    job_input_data: Dict[str, Any]

    # Agent Processing Results
    job_analysis: Optional[Dict[str, Any]]
    company_research: Optional[Dict[str, Any]]
    profile_matching: Optional[Dict[str, Any]]
    resume_recommendations: Optional[Dict[str, Any]]
    cover_letter: Optional[Dict[str, Any]]

    # Workflow Control and Status
    current_phase: WorkflowPhase
    workflow_status: WorkflowStatus
    processing_start_time: str
    processing_end_time: Optional[str]

    # Agent Status Tracking
    current_agent: Optional[Agent]
    agent_status: Dict[str, AgentStatus]
    completed_agents: List[Agent]
    failed_agents: List[Agent]

    # Error Handling
    error_messages: List[str]
    warning_messages: List[str]

    # Performance Metrics
    agent_start_times: Dict[str, str]
    agent_durations: Dict[str, float]  # Agent name -> duration in milliseconds


def create_initial_state(
    user_id: str,
    session_id: str,
    user_profile: UserProfile,
    job_input_data: JobInputData,
    user_api_key: Optional[str] = None,
    workflow_preferences: Optional[Dict[str, Any]] = None,
) -> WorkflowState:
    """
    Create initial workflow state for a new job application workflow session.

    This function initializes the complete workflow state with all required
    fields, setting up agent statuses, timestamps, and user data. It serves
    as the entry point for all new workflow executions.

    Args:
        user_id: Unique identifier for the user
        session_id: Unique identifier for this workflow session
        user_profile: User profile data containing all relevant information
        job_input_data: Job input data containing method, content, and metadata
        user_api_key: Optional decrypted user API key for LLM calls (BYOK mode)

    Returns:
        Fully initialized WorkflowState ready for agent processing

    Raises:
        ValueError: If input_method is missing or invalid in job_input_data
    """
    current_time: datetime = datetime.now(timezone.utc)

    # Handle both dict and object inputs for user_profile and job_input_data
    user_profile_dict = (
        user_profile.to_dict() if hasattr(user_profile, 'to_dict') else user_profile
    )
    job_input_data_dict = (
        job_input_data.to_dict() if hasattr(job_input_data, 'to_dict') else job_input_data
    )
    
    return WorkflowState(
        user_id=user_id,
        session_id=session_id,
        # User data
        user_profile=user_profile_dict,
        # User API key (BYOK)
        user_api_key=user_api_key,
        # Per-user workflow preferences
        workflow_preferences=workflow_preferences or {},
        # Job input data
        job_input_data=job_input_data_dict,
        # Agent results (empty initially)
        job_analysis=None,
        company_research=None,
        profile_matching=None,
        resume_recommendations=None,
        cover_letter=None,
        # Workflow control
        current_phase=WorkflowPhase.INITIALIZATION,
        workflow_status=WorkflowStatus.INITIALIZED,
        processing_start_time=datetime_to_string(current_time),
        processing_end_time=None,
        # Agent status - initialize all agents as pending with string keys
        agent_status={
            agent_to_key(agent): AgentStatus.PENDING
            for agent in DEFAULT_AGENT_STATUS.keys()
        },
        completed_agents=[],
        failed_agents=[],
        current_agent=None,
        # Error handling
        error_messages=[],
        warning_messages=[],
        # Performance metrics - initialize empty, will be populated as agents run
        agent_start_times={},
        agent_durations={},
    )


def add_error(
    state: WorkflowState, error_message: str, _agent_name: Optional[str] = None
) -> WorkflowState:
    """
    Add an error message to the workflow state for tracking and reporting.

    Messages are stored as plain user-facing text (no agent prefix). Which agent
    failed is tracked in ``failed_agents`` and server logs.

    Args:
        state: Current workflow state to update
        error_message: Description of the error that occurred
        _agent_name: Reserved for call-site symmetry with ``add_warning``; not
            embedded in ``error_message``.

    Returns:
        Updated workflow state with the new error message
    """
    state["error_messages"].append(error_message)
    return state


def add_warning(
    state: WorkflowState, warning_message: str, _agent_name: Optional[str] = None
) -> WorkflowState:
    """
    Add a warning message to the workflow state for tracking and reporting.

    Messages are stored as plain user-facing text (no agent prefix).

    Args:
        state: Current workflow state to update
        warning_message: Description of the warning condition
        _agent_name: Reserved for call-site symmetry; not embedded in the stored string.

    Returns:
        Updated workflow state with the new warning message
    """
    state["warning_messages"].append(warning_message)
    return state

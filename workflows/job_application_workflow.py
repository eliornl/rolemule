"""
Main LangGraph workflow orchestrator for the ApplyPilot.
Coordinates multi-agent workflow for processing job applications with comprehensive application materials.

WORKFLOW STRUCTURE:
===================
STEP 1: Job Analyzer (Sequential - runs first, critical)
         │
         ▼
STEP 2: Profile Matcher (Sequential - GATE DECISION)
         │
         ├── Match Score >= 50% AND recommendation not (NOT_RECOMMENDED, WEAK_MATCH)
         │   → Continue automatically to Step 3
         │
         └── Match Score < 50% OR recommendation is (NOT_RECOMMENDED, WEAK_MATCH)
         │   → STOP, set status to AWAITING_CONFIRMATION
         │   → Frontend asks user "Continue anyway?"
         │        ├── User clicks "Stop" → End workflow
         │        └── User clicks "Continue" → Call continue_workflow_after_gate() to proceed
         │
         ▼
STEP 3: Company Research (Sequential - needed for personalized documents)
         │
         ▼
STEP 4: Run in PARALLEL (both at same time)
         ┌─────────────────┬─────────────────┐
         │ Resume Advisor  │ Cover Letter    │
         └─────────────────┴─────────────────┘
"""

import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Dict, Any, Optional, Tuple
import asyncio
from copy import deepcopy

from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from utils.logging_config import get_structured_logger, session_id_var, set_request_context, clear_request_context, sanitize_log_value
from api.websocket import (
    broadcast_agent_update,
    broadcast_phase_change,
    broadcast_workflow_complete,
    broadcast_workflow_error,
    broadcast_gate_decision,
)
from workflows.state_schema import (
    NodeName,
    WorkflowState,
    AgentStatus,
    WorkflowPhase,
    WorkflowStatus,
    Agent,
    create_initial_state,
    add_error,
    get_current_time_string,
    key_to_agent,
)

# Default preferences — used when the user has not configured their own
DEFAULT_WORKFLOW_PREFERENCES: dict = {
    "workflow_gate_threshold": 0.5,
    "auto_generate_documents": False,
}
from agents.job_analyzer import JobAnalyzerAgent
from agents.company_research import CompanyResearchAgent
from agents.profile_matching import ProfileMatchingAgent
from agents.resume_advisor import ResumeAdvisorAgent
from agents.cover_letter_writer import CoverLetterWriterAgent
from utils.llm_client import get_llm_client, get_gemini_client, user_facing_message_from_llm_exception  # test-patch alias
from utils.redis_client import get_redis_client
from utils.security import (
    sanitize_job_analysis,
    sanitize_cover_letter,
    sanitize_resume_recommendations,
    sanitize_dict,
)
from config.settings import get_settings
from models.database import WorkflowSession as WorkflowSessionModel, JobApplication as JobApplicationModel
from utils.application_dedupe import find_conflicting_job_application

# =============================================================================
# CONSTANTS
# =============================================================================

# Same user-facing text as POST /workflow/start RES_3002 duplicate response
_DUPLICATE_JOB_USER_MESSAGE = (
    "You already have an application for this job. Open it from your dashboard, "
    "or delete the old one first if you want to start over."
)

# Gate decision threshold for profile matching
MATCH_SCORE_THRESHOLD: float = 0.5  # 50% - below this triggers gate

# Recommendations that trigger gate decision (require user confirmation)
GATE_RECOMMENDATIONS: Tuple[str, ...] = ("NOT_RECOMMENDED", "WEAK_MATCH")

# Agent configuration for generic execution
AGENT_CONFIG: Dict[str, Dict[str, Any]] = {
    "job_analyzer": {
        "phase": WorkflowPhase.JOB_ANALYSIS,
        "display_name": "Job analysis",
    },
    "profile_matching": {
        "phase": WorkflowPhase.PROFILE_MATCHING,
        "display_name": "Profile matching",
    },
    "company_research": {
        "phase": WorkflowPhase.COMPANY_RESEARCH,
        "display_name": "Company research",
    },
    "resume_advisor": {
        "phase": WorkflowPhase.DOCUMENT_GENERATION,
        "display_name": "Resume advisory",
    },
    "cover_letter_writer": {
        "phase": WorkflowPhase.DOCUMENT_GENERATION,
        "display_name": "Cover letter writing",
    },
}

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

# Initialize loggers
logger: logging.Logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# Global workflow singleton instance
_workflow_instance: Optional["JobApplicationWorkflow"] = None


# =============================================================================
# WORKFLOW CLASS
# =============================================================================


class JobApplicationWorkflow:
    """
    Main workflow orchestrator for ApplyPilot.

    This class manages the complete multi-agent workflow using LangGraph,
    coordinating between different specialized agents to generate comprehensive
    job application materials including resume recommendations and cover letters.

    The workflow implements a GATE DECISION after profile matching:
    - If match score >= 50% AND recommendation is positive → continues automatically
    - If match score < 50% OR weak/not recommended → pauses for user confirmation

    Attributes:
        settings: Application settings configuration
        workflow: LangGraph workflow instance (main workflow with gate)
        continuation_workflow: LangGraph workflow for resuming after gate
        job_analyzer: Job analyzer agent instance
        company_research: Company research agent instance
        profile_matching: Profile matching agent instance
        resume_advisor: Resume advisor agent instance
        cover_letter_writer: Cover letter writer agent instance
    """

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        """
        Initialize the workflow orchestrator.

        Args:
            db: Optional database session for state persistence
        """
        self.settings = get_settings()

        # Initialize workflow components
        self.workflow: Optional[StateGraph] = None
        self.continuation_workflow: Optional[StateGraph] = None

        # Database session (passed in or initialized during initialize)
        self.db: Optional[AsyncSession] = db

        # Agent instances (initialized later)
        self.job_analyzer: Optional[JobAnalyzerAgent] = None
        self.company_research: Optional[CompanyResearchAgent] = None
        self.profile_matching: Optional[ProfileMatchingAgent] = None
        self.resume_advisor: Optional[ResumeAdvisorAgent] = None
        self.cover_letter_writer: Optional[CoverLetterWriterAgent] = None

    async def initialize(self) -> None:
        """
        Initialize all required resources and agents.

        This method sets up all required clients and creates agent instances
        with their dependencies. Must be called before executing any workflows.

        Raises:
            RuntimeError: If critical clients (Gemini) fail to initialize
            Exception: If client initialization fails for any other reason
        """
        if self.workflow is not None:
            return  # Already initialized

        # Initialize critical clients - fail fast if they don't work
        try:
            gemini_client = await get_llm_client()
            logger.info("Gemini client initialized successfully")
        except Exception as e:
            logger.error('Failed to initialize Gemini client: %s', sanitize_log_value(e), exc_info=True)
            raise RuntimeError(
                f"Critical dependency failed: Gemini client initialization failed - {e}"
            )

        # Redis is optional (used for caching), allow graceful degradation
        try:
            redis_client = await get_redis_client()
            logger.info("Redis client initialized successfully")
        except Exception as e:
            logger.warning('Redis client initialization failed (non-critical): %s', sanitize_log_value(e))
            redis_client = None

        # Initialize agents with clients
        self.job_analyzer = JobAnalyzerAgent(gemini_client=gemini_client)

        self.company_research = CompanyResearchAgent(
            gemini_client=gemini_client,
            redis_client=redis_client,
        )

        self.profile_matching = ProfileMatchingAgent()

        self.resume_advisor = ResumeAdvisorAgent(gemini_client=gemini_client)

        self.cover_letter_writer = CoverLetterWriterAgent(gemini_client=gemini_client)

        # Build both workflow graphs
        self.workflow = self._build_main_workflow()
        self.continuation_workflow = self._build_continuation_workflow()

    def _build_main_workflow(self) -> StateGraph:
        """
        Build the main workflow graph with gate decision after profile matching.

        Flow: Job Analyzer → Profile Matcher → [GATE] → Company Research → Documents

        Returns:
            StateGraph: Configured workflow graph ready for execution
        """
        workflow: StateGraph = StateGraph(WorkflowState)

        # Add agent nodes
        workflow.add_node(NodeName.JOB_ANALYZER.value, self._job_analyzer_node)
        workflow.add_node(NodeName.PROFILE_MATCHING.value, self._profile_matching_node)
        workflow.add_node(NodeName.COMPANY_RESEARCH.value, self._company_research_node)
        workflow.add_node(
            NodeName.DOCUMENT_GENERATION.value, self._document_generation_parallel_node
        )
        workflow.add_node(NodeName.ANALYSIS_COMPLETE.value, self._analysis_complete_node)
        workflow.add_node(NodeName.ERROR_HANDLER.value, self._error_handler_node)

        # Gate decision node (handles low match score pause)
        workflow.add_node("gate_decision", self._gate_decision_node)

        # Set entry point
        workflow.set_entry_point(NodeName.JOB_ANALYZER.value)

        # Job Analyzer → Profile Matching (or error)
        workflow.add_conditional_edges(
            NodeName.JOB_ANALYZER.value,
            self._route_after_job_analysis,
            {
                "success": NodeName.PROFILE_MATCHING.value,
                "error": NodeName.ERROR_HANDLER.value,
            },
        )

        # Profile Matching → Gate Decision or terminal failure (no partial results)
        workflow.add_conditional_edges(
            NodeName.PROFILE_MATCHING.value,
            self._route_after_profile_matching,
            {
                "success": "gate_decision",
                "error": NodeName.ERROR_HANDLER.value,
            },
        )

        # Gate Decision → Continue or Stop at gate
        workflow.add_conditional_edges(
            "gate_decision",
            self._route_gate_decision,
            {
                "continue": NodeName.COMPANY_RESEARCH.value,
                "await_confirmation": END,  # Stops here, frontend will handle
            },
        )

        # Company Research → Document Generation OR Analysis Complete OR failure
        workflow.add_conditional_edges(
            NodeName.COMPANY_RESEARCH.value,
            self._route_after_company_research,
            {
                "error": NodeName.ERROR_HANDLER.value,
                "generate_documents": NodeName.DOCUMENT_GENERATION.value,
                "analysis_complete": NodeName.ANALYSIS_COMPLETE.value,
            },
        )

        # Document Generation → Complete
        workflow.add_edge(NodeName.DOCUMENT_GENERATION.value, END)

        # Analysis Complete terminal node
        workflow.add_edge(NodeName.ANALYSIS_COMPLETE.value, END)

        # Error handler → End
        workflow.add_edge(NodeName.ERROR_HANDLER.value, END)

        return workflow.compile()

    def _build_continuation_workflow(self) -> StateGraph:
        """
        Build the continuation workflow for resuming after gate confirmation.

        Flow: Company Research → Documents (Resume + Cover Letter parallel)

        This workflow is used when user confirms they want to continue
        despite a low match score.

        Returns:
            StateGraph: Configured continuation workflow graph
        """
        workflow: StateGraph = StateGraph(WorkflowState)

        # Add nodes for continuation (post-gate)
        workflow.add_node(NodeName.COMPANY_RESEARCH.value, self._company_research_node)
        workflow.add_node(
            NodeName.DOCUMENT_GENERATION.value, self._document_generation_parallel_node
        )
        workflow.add_node(NodeName.ANALYSIS_COMPLETE.value, self._analysis_complete_node)
        workflow.add_node(NodeName.ERROR_HANDLER.value, self._error_handler_node)

        # Set entry point for continuation
        workflow.set_entry_point(NodeName.COMPANY_RESEARCH.value)

        # Company Research → Document Generation OR Analysis Complete OR failure
        workflow.add_conditional_edges(
            NodeName.COMPANY_RESEARCH.value,
            self._route_after_company_research,
            {
                "error": NodeName.ERROR_HANDLER.value,
                "generate_documents": NodeName.DOCUMENT_GENERATION.value,
                "analysis_complete": NodeName.ANALYSIS_COMPLETE.value,
            },
        )

        # Document Generation → Complete
        workflow.add_edge(NodeName.DOCUMENT_GENERATION.value, END)

        # Analysis Complete terminal node
        workflow.add_edge(NodeName.ANALYSIS_COMPLETE.value, END)

        # Error handler → End (same as main workflow)
        workflow.add_edge(NodeName.ERROR_HANDLER.value, END)

        return workflow.compile()

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    async def run_initial_workflow(
        self,
        session_id: str,
        user_id: str,
        input_method: str,
        job_input: str,
        user_data: Dict[str, Any],
        user_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the initial workflow from start.

        Args:
            session_id: Workflow session ID
            user_id: User ID
            input_method: How job was input (url, text, file)
            job_input: The job content
            user_data: User profile data
            user_api_key: Optional user-provided API key (BYOK mode)

        Returns:
            Final workflow state as dictionary
        """
        await self.initialize()

        # Set logging context for the entire workflow execution
        context_tokens = set_request_context(
            session_id=session_id,
            user_id=str(user_id) if user_id else None,
        )

        workflow_start = perf_counter()
        safe_session = sanitize_log_value(str(session_id)[:8])
        safe_input_method = sanitize_log_value(str(input_method))
        logger.info('[WORKFLOW] Start  session=%s...  input=%s  byok=%s', sanitize_log_value(safe_session), sanitize_log_value(safe_input_method), sanitize_log_value("yes" if user_api_key else "no"))

        try:
            # Derive workflow preferences from the user's profile data
            workflow_preferences = {
                **DEFAULT_WORKFLOW_PREFERENCES,
                **(user_data.get("application_preferences") or {}),
            }

            # Create initial state
            initial_state: WorkflowState = create_initial_state(
                user_id=user_id,
                session_id=session_id,
                user_profile=user_data,
                job_input_data={
                    "input_method": input_method,
                    "job_content": job_input,  # Agent expects job_content key
                },
                user_api_key=user_api_key,
                workflow_preferences=workflow_preferences,
                llm_provider=user_data.get("llm_provider"),
            )

            # Execute the workflow graph
            if self.workflow is None:
                raise ValueError("Workflow not initialized")

            _WORKFLOW_TOTAL_TIMEOUT_SECONDS = 600  # 10 min hard ceiling
            try:
                final_state: WorkflowState = await asyncio.wait_for(
                    self.workflow.ainvoke(initial_state),
                    timeout=_WORKFLOW_TOTAL_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error('Workflow timed out after %ss (session=%s...)', sanitize_log_value(_WORKFLOW_TOTAL_TIMEOUT_SECONDS), sanitize_log_value(safe_session), exc_info=True)
                raise

            total_ms = (perf_counter() - workflow_start) * 1000
            durations = final_state.get("agent_durations") or {}
            status = final_state.get("workflow_status")
            status_label = status.value if hasattr(status, "value") else str(status)
            duration_parts = "  ".join(
                f"{k}={v/1000:.1f}s" for k, v in durations.items()
            )
            logger.info('[WORKFLOW] Done  session=%s...  status=%s  total=%.1fs  agents=[%s]', sanitize_log_value(safe_session), sanitize_log_value(status_label), total_ms / 1000, sanitize_log_value(duration_parts))

            return self._state_to_dict(final_state)
        except Exception as exc:
            total_ms = (perf_counter() - workflow_start) * 1000
            logger.error('[WORKFLOW] Failed  session=%s...  after=%.1fs  error=%s', sanitize_log_value(safe_session), total_ms / 1000, sanitize_log_value(str(exc)), exc_info=True)
            raise
        finally:
            # Clear logging context
            clear_request_context(context_tokens)

    async def continue_workflow_after_gate(
        self,
        session_id: str,
        user_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Continue a workflow that was paused at the gate decision.

        Args:
            session_id: The session ID of the paused workflow
            user_api_key: Optional user-provided API key (BYOK mode)

        Returns:
            Final workflow state as dictionary
        """
        await self.initialize()

        # Load the paused state
        state = await self._load_workflow_state(session_id, user_api_key=user_api_key)

        if state is None:
            raise ValueError(f"Workflow session not found: {session_id}")

        # Set logging context for the workflow continuation
        user_id = state.get("user_id")
        context_tokens = set_request_context(
            session_id=session_id,
            user_id=str(user_id) if user_id else None,
        )

        try:
            # Verify workflow is in the correct state to resume
            # Note: API endpoint changes status to IN_PROGRESS before calling this background task
            current_status = state.get("workflow_status")
            if current_status not in [WorkflowStatus.AWAITING_CONFIRMATION, WorkflowStatus.IN_PROGRESS]:
                raise ValueError(
                    f"Workflow cannot be continued. Current status: {current_status}"
                )

            # Execute the continuation workflow
            if self.continuation_workflow is None:
                raise ValueError("Continuation workflow not initialized")

            _WORKFLOW_TOTAL_TIMEOUT_SECONDS = 600
            try:
                final_state: WorkflowState = await asyncio.wait_for(
                    self.continuation_workflow.ainvoke(state),
                    timeout=_WORKFLOW_TOTAL_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error('Continuation workflow timed out after %ss', sanitize_log_value(_WORKFLOW_TOTAL_TIMEOUT_SECONDS), exc_info=True)
                raise

            return self._state_to_dict(final_state)
        finally:
            # Clear logging context
            clear_request_context(context_tokens)

    async def run_document_generation(
        self,
        session_id: str,
        user_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate documents for a session that is in ANALYSIS_COMPLETE state.

        Loads the stored state, runs the parallel document generation node, and
        returns the final state dict.  Called from the background task triggered
        by POST /api/v1/workflow/{session_id}/generate-documents.

        Args:
            session_id: The session ID of an ANALYSIS_COMPLETE workflow
            user_api_key: Optional decrypted user API key (BYOK)

        Returns:
            Final workflow state as dictionary
        """
        await self.initialize()

        state = await self._load_workflow_state(session_id, user_api_key=user_api_key)
        if state is None:
            raise ValueError(f"Workflow session not found: {session_id}")

        user_id = state.get("user_id")
        context_tokens = set_request_context(
            session_id=session_id,
            user_id=str(user_id) if user_id else None,
        )

        try:
            current_status = state.get("workflow_status")
            if current_status not in [
                WorkflowStatus.ANALYSIS_COMPLETE,
                WorkflowStatus.IN_PROGRESS,
            ]:
                raise ValueError(
                    f"Documents cannot be generated from status: {current_status}"
                )

            state["workflow_status"] = WorkflowStatus.IN_PROGRESS
            state = await self._document_generation_parallel_node(state)
            return self._state_to_dict(state)
        finally:
            clear_request_context(context_tokens)

    def _state_to_dict(self, state: WorkflowState) -> Dict[str, Any]:
        """Convert workflow state to serializable dictionary with XSS sanitization."""
        # Sanitize LLM outputs before returning
        job_analysis = state.get("job_analysis")
        if job_analysis:
            job_analysis = sanitize_job_analysis(job_analysis)

        cover_letter = state.get("cover_letter")
        if cover_letter:
            cover_letter = sanitize_cover_letter(cover_letter)

        resume_recommendations = state.get("resume_recommendations")
        if resume_recommendations:
            resume_recommendations = sanitize_resume_recommendations(resume_recommendations)

        # Company research may contain scraped content - sanitize it
        company_research = state.get("company_research")
        if company_research:
            company_research = sanitize_dict(company_research)

        return {
            "session_id": state.get("session_id"),
            "user_id": state.get("user_id"),
            "workflow_status": (
                state.get("workflow_status").value
                if hasattr(state.get("workflow_status"), "value")
                else state.get("workflow_status")
            ),
            "current_phase": (
                state.get("current_phase").value
                if hasattr(state.get("current_phase"), "value")
                else state.get("current_phase")
            ),
            "current_agent": (
                state.get("current_agent").value
                if state.get("current_agent") and hasattr(state.get("current_agent"), "value")
                else state.get("current_agent")
            ),
            "agent_status": {
                k: v.value if hasattr(v, "value") else v
                for k, v in (state.get("agent_status") or {}).items()
            },
            "completed_agents": [
                a.value if hasattr(a, "value") else a
                for a in (state.get("completed_agents") or [])
            ],
            "failed_agents": [
                a.value if hasattr(a, "value") else a
                for a in (state.get("failed_agents") or [])
            ],
            "error_messages": state.get("error_messages", []),
            "warning_messages": state.get("warning_messages", []),
            "job_analysis": job_analysis,
            "company_research": company_research,
            "profile_matching": state.get("profile_matching"),
            "resume_recommendations": resume_recommendations,
            "cover_letter": cover_letter,
            "processing_start_time": state.get("processing_start_time"),
            "processing_end_time": state.get("processing_end_time"),
        }

    # =========================================================================
    # AGENT NODE METHODS
    # =========================================================================

    async def _execute_agent_node(
        self,
        state: WorkflowState,
        agent_name: str,
        agent_instance: Optional[Any],
        config: Dict[str, Any],
        save_state: bool = True,
    ) -> WorkflowState:
        """
        Execute an agent node with comprehensive state management and performance logging.
        """
        display_name: str = config["display_name"]
        agent_enum: Agent = key_to_agent(agent_name)
        current_time: str = get_current_time_string()
        workflow_id: str = state.get("session_id", "unknown")

        # Set session context for logging
        session_id_var.set(workflow_id)

        # Log agent start with structured logger
        structured_logger.log_agent_start(agent_name, workflow_id)
        start_time = perf_counter()

        # Update workflow phase if specified (must be first)
        if config["phase"] is not None:
            state["current_phase"] = config["phase"]

        state["current_agent"] = agent_enum
        state["agent_start_times"][agent_name] = current_time

        # Persist current_agent immediately so status polls reflect the running agent name
        # without waiting for the finally-block full save (which only runs after agent completes).
        if self.db is not None:
            try:
                await self.db.execute(
                    update(WorkflowSessionModel)
                    .where(WorkflowSessionModel.session_id == workflow_id)
                    .values(current_agent=agent_name)
                )
                await self.db.commit()
            except Exception as _pre_save_err:
                logger.debug('Pre-agent current_agent flush failed (non-critical): %s', sanitize_log_value(_pre_save_err))

        # Get user_id for WebSocket broadcasts
        user_id = str(state.get("user_id", ""))

        try:
            # Check agent initialization inside try block
            if agent_instance is None:
                logger.error('%s agent not initialized', sanitize_log_value(display_name))
                raise ValueError(f"{display_name} agent not initialized")

            # Set agent status to RUNNING
            state["agent_status"][agent_name] = AgentStatus.RUNNING

            # Broadcast agent started via WebSocket
            await broadcast_agent_update(
                user_id=user_id,
                session_id=workflow_id,
                agent_name=agent_name,
                status="running",
                message=f"{display_name} started",
            )

            # Execute agent processing (agent focuses on business logic only)
            state = await agent_instance.process(state)

            # Calculate duration
            duration_ms = (perf_counter() - start_time) * 1000

            # Save duration to state for tracking
            if "agent_durations" not in state:
                state["agent_durations"] = {}
            state["agent_durations"][agent_name] = duration_ms

            # Workflow manages success state
            state["agent_status"][agent_name] = AgentStatus.COMPLETED

            # Add to completed agents list if not already present
            if agent_enum not in state["completed_agents"]:
                state["completed_agents"].append(agent_enum)

            # Log success with timing
            structured_logger.log_agent_complete(agent_name, workflow_id, duration_ms)

            # Broadcast agent completed via WebSocket
            await broadcast_agent_update(
                user_id=user_id,
                session_id=workflow_id,
                agent_name=agent_name,
                status="completed",
                message=f"{display_name} completed in {duration_ms:.0f}ms",
            )

        except Exception as e:
            # Calculate duration for error case
            duration_ms = (perf_counter() - start_time) * 1000

            # Save duration even for failed agents
            if "agent_durations" not in state:
                state["agent_durations"] = {}
            state["agent_durations"][agent_name] = duration_ms

            # Log error with structured logger
            structured_logger.log_agent_error(agent_name, workflow_id, e, duration_ms)

            # Workflow manages failure state
            state["agent_status"][agent_name] = AgentStatus.FAILED

            # Add to failed agents list if not already present
            if agent_enum not in state["failed_agents"]:
                state["failed_agents"].append(agent_enum)

            # Any agent failure fails the whole workflow — no partial results for the client.
            user_msg = user_facing_message_from_llm_exception(e)
            state = add_error(state, user_msg, agent_name)

            # Broadcast agent failed via WebSocket
            await broadcast_agent_update(
                user_id=user_id,
                session_id=workflow_id,
                agent_name=agent_name,
                status="failed",
                message=user_msg,
            )

        finally:
            # Save state only if requested (to prevent race conditions in parallel nodes)
            if save_state:
                await self._save_workflow_state(state)

        return state

    async def _job_analyzer_node(self, state: WorkflowState) -> WorkflowState:
        """Execute job analyzer agent to analyze job requirements and context."""
        state["workflow_status"] = WorkflowStatus.IN_PROGRESS

        return await self._execute_agent_node(
            state,
            Agent.JOB_ANALYZER.value,
            self.job_analyzer,
            AGENT_CONFIG[Agent.JOB_ANALYZER.value],
        )

    async def _profile_matching_node(self, state: WorkflowState) -> WorkflowState:
        """Execute profile matching to align user qualifications with job requirements."""
        return await self._execute_agent_node(
            state,
            Agent.PROFILE_MATCHING.value,
            self.profile_matching,
            AGENT_CONFIG[Agent.PROFILE_MATCHING.value],
        )

    async def _gate_decision_node(self, state: WorkflowState) -> WorkflowState:
        """Evaluate profile matching results and determine if workflow should continue."""
        logger.info("Evaluating gate decision based on profile matching results")

        # Extract profile matching results
        profile_result = state.get("profile_matching", {})
        if not profile_result:
            # If profile matching failed, continue anyway (no gate)
            logger.warning("No profile matching results - skipping gate decision")
            return state

        # Get the key decision factors
        exec_summary = profile_result.get("executive_summary", {})
        final_scores = profile_result.get("final_scores", {})

        recommendation = exec_summary.get("recommendation", "UNKNOWN")

        # Check multiple possible locations for the overall fit score
        # LLM output format varies: sometimes in final_scores.overall_fit,
        # sometimes as top-level overall_score
        overall_fit = (
            final_scores.get("overall_fit")
            or profile_result.get("overall_score")
            or profile_result.get("overall_fit")
            or exec_summary.get("overall_score")
            or 0.0
        )

        # Ensure overall_fit is a float
        try:
            overall_fit = float(overall_fit)
        except (ValueError, TypeError):
            overall_fit = 0.0

        # Use user's configured threshold (falls back to default if not set)
        prefs = state.get("workflow_preferences") or {}
        gate_threshold = float(
            prefs.get("workflow_gate_threshold", MATCH_SCORE_THRESHOLD)
        )
        # Clamp to valid range
        gate_threshold = max(0.0, min(1.0, gate_threshold))

        logger.info('Gate decision check: recommendation=%s, overall_fit=%s, threshold=%s', sanitize_log_value(recommendation), sanitize_log_value(overall_fit), sanitize_log_value(gate_threshold))

        # Gate decision logic
        should_gate = (
            overall_fit < gate_threshold
            or recommendation in GATE_RECOMMENDATIONS
        )

        # Get user_id for WebSocket broadcasts
        user_id = str(state.get("user_id", ""))
        session_id = state.get("session_id", "")

        if should_gate:
            logger.info('GATE TRIGGERED: Low match score (%s) or weak recommendation (%s). Awaiting user confirmation.', sanitize_log_value(overall_fit), sanitize_log_value(recommendation))
            state["workflow_status"] = WorkflowStatus.AWAITING_CONFIRMATION
            await self._save_workflow_state(state)

            # Broadcast gate decision via WebSocket
            await broadcast_gate_decision(
                user_id=user_id,
                session_id=session_id,
                match_score=overall_fit,
                recommendation=recommendation,
            )
        else:
            logger.info('GATE PASSED: Good match score (%s) and positive recommendation (%s). Continuing workflow.', sanitize_log_value(overall_fit), sanitize_log_value(recommendation))

            # Broadcast phase change via WebSocket
            await broadcast_phase_change(
                user_id=user_id,
                session_id=session_id,
                phase="company_research",
                progress_percentage=40,
            )

        return state

    async def _company_research_node(self, state: WorkflowState) -> WorkflowState:
        """Execute company research to gather organizational context and insights."""
        # If resuming from gate, update status back to IN_PROGRESS
        if state.get("workflow_status") == WorkflowStatus.AWAITING_CONFIRMATION:
            state["workflow_status"] = WorkflowStatus.IN_PROGRESS

        return await self._execute_agent_node(
            state,
            Agent.COMPANY_RESEARCH.value,
            self.company_research,
            AGENT_CONFIG[Agent.COMPANY_RESEARCH.value],
        )

    async def _analysis_complete_node(self, state: WorkflowState) -> WorkflowState:
        """Terminal node when auto_generate_documents is disabled.

        Sets status to ANALYSIS_COMPLETE so the frontend knows analysis is ready
        but documents have not been generated yet.  The user can trigger document
        generation on-demand via POST /api/v1/workflow/{session_id}/generate-documents.
        """
        logger.info("Analysis complete — document generation deferred by user preference")

        state["current_phase"] = WorkflowPhase.ANALYSIS_COMPLETE
        state["workflow_status"] = WorkflowStatus.ANALYSIS_COMPLETE
        state["processing_end_time"] = get_current_time_string()

        await self._save_workflow_state(state)

        user_id = str(state.get("user_id", ""))
        session_id = state.get("session_id", "")

        profile_matching = state.get("profile_matching", {})
        final_scores = (profile_matching or {}).get("final_scores", {})
        result_summary = {
            "status": "analysis_complete",
            "match_score": (
                final_scores.get("overall_fit")
                or (profile_matching or {}).get("overall_score")
                or 0.0
            ),
            "has_resume_recommendations": False,
            "has_cover_letter": False,
            "completed_agents": len(state.get("completed_agents", [])),
        }

        await broadcast_workflow_complete(
            user_id=user_id,
            session_id=session_id,
            result_summary=result_summary,
        )

        return state

    async def _document_generation_parallel_node(
        self, state: WorkflowState
    ) -> WorkflowState:
        """Execute document generation agents in parallel for optimal performance."""
        logger.info("Executing document generation agents in parallel")

        # Update workflow phase to document generation
        state["current_phase"] = WorkflowPhase.DOCUMENT_GENERATION

        ra_key = Agent.RESUME_ADVISOR.value
        cl_key = Agent.COVER_LETTER_WRITER.value

        # Create parallel tasks for document generation agents
        async def run_resume_advisor() -> WorkflowState:
            """Execute resume advisor with deep copy of state."""
            agent_state: WorkflowState = deepcopy(state)
            return await self._execute_agent_node(
                agent_state,
                Agent.RESUME_ADVISOR.value,
                self.resume_advisor,
                AGENT_CONFIG[Agent.RESUME_ADVISOR.value],
                save_state=False,
            )

        async def run_cover_letter_writer() -> WorkflowState:
            """Execute cover letter writer with deep copy of state."""
            agent_state: WorkflowState = deepcopy(state)
            return await self._execute_agent_node(
                agent_state,
                Agent.COVER_LETTER_WRITER.value,
                self.cover_letter_writer,
                AGENT_CONFIG[Agent.COVER_LETTER_WRITER.value],
                save_state=False,
            )

        # Execute both agents in parallel
        results: Tuple[WorkflowState, WorkflowState] = await asyncio.gather(
            run_resume_advisor(),
            run_cover_letter_writer(),
        )

        # Process results from each agent
        resume_state: WorkflowState = results[0]
        cover_letter_state: WorkflowState = results[1]

        ra_ok = resume_state["agent_status"].get(ra_key) == AgentStatus.COMPLETED
        cl_ok = cover_letter_state["agent_status"].get(cl_key) == AgentStatus.COMPLETED
        if not (ra_ok and cl_ok):
            self._merge_parallel_branch_into_main(state, resume_state, ra_key)
            self._merge_parallel_branch_into_main(state, cover_letter_state, cl_key)
            self._clear_agent_outputs_for_failed_workflow(state)
            state["current_phase"] = WorkflowPhase.ERROR
            state["workflow_status"] = WorkflowStatus.FAILED
            state["processing_end_time"] = get_current_time_string()
            await self._save_workflow_state(state)
            err_list = state.get("error_messages") or []
            err_msg = err_list[-1] if err_list else "Document generation failed"
            await broadcast_workflow_error(
                user_id=str(state.get("user_id", "")),
                session_id=str(state.get("session_id", "")),
                error_message=err_msg,
                failed_agent=None,
            )
            return state

        # Merge results into main state (both agents succeeded)
        self._process_parallel_agent_result(
            state, ra_key, resume_state, "resume_recommendations"
        )

        self._process_parallel_agent_result(
            state, cl_key, cover_letter_state, "cover_letter"
        )

        # Set completion status
        state["current_phase"] = WorkflowPhase.COMPLETED
        state["workflow_status"] = WorkflowStatus.COMPLETED
        state["processing_end_time"] = get_current_time_string()

        # Save the final merged state after all parallel operations
        await self._save_workflow_state(state)

        # Broadcast workflow completion via WebSocket
        user_id = str(state.get("user_id", ""))
        session_id = state.get("session_id", "")
        
        # Build result summary for broadcast
        profile_matching = state.get("profile_matching", {})
        final_scores = profile_matching.get("final_scores", {})
        result_summary = {
            "match_score": final_scores.get("overall_fit", 0.0),
            "has_resume_recommendations": bool(state.get("resume_recommendations")),
            "has_cover_letter": bool(state.get("cover_letter")),
            "completed_agents": len(state.get("completed_agents", [])),
        }
        
        await broadcast_workflow_complete(
            user_id=user_id,
            session_id=session_id,
            result_summary=result_summary,
        )

        return state

    async def _error_handler_node(self, state: WorkflowState) -> WorkflowState:
        """Execute error handling and recovery processing."""
        logger.info("Executing error handler")

        self._clear_agent_outputs_for_failed_workflow(state)

        # Update workflow status
        state["current_phase"] = WorkflowPhase.ERROR
        state["workflow_status"] = WorkflowStatus.FAILED

        completed_agents = state.get("completed_agents", [])
        if completed_agents:
            completed_agent_names = [agent.value for agent in completed_agents]
            logger.info('Workflow failed; agents that had completed before failure: %s', sanitize_log_value(completed_agent_names))
        else:
            logger.info("Workflow failed before any agent completed")

        # Always set end time for metrics
        state["processing_end_time"] = get_current_time_string()

        await self._save_workflow_state(state)

        # Broadcast workflow error via WebSocket
        user_id = str(state.get("user_id", ""))
        session_id = state.get("session_id", "")
        error_messages = state.get("error_messages", [])

        error_message = error_messages[-1] if error_messages else "Workflow failed"

        await broadcast_workflow_error(
            user_id=user_id,
            session_id=session_id,
            error_message=error_message,
            failed_agent=None,
        )

        return state

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _clear_agent_outputs_for_failed_workflow(self, state: WorkflowState) -> None:
        """Strip all agent-generated content — failed workflows must not expose partial results."""
        state["job_analysis"] = None
        state["company_research"] = None
        state["profile_matching"] = None
        state["resume_recommendations"] = None
        state["cover_letter"] = None

    def _merge_parallel_branch_into_main(
        self,
        main: WorkflowState,
        branch: WorkflowState,
        agent_key: str,
    ) -> None:
        """Merge status, timings, and messages from one parallel branch into the main state."""
        self._merge_messages(main, branch)
        st = branch.get("agent_status", {}).get(agent_key)
        if st is not None:
            main["agent_status"][agent_key] = st
        start_t = branch.get("agent_start_times", {}).get(agent_key)
        if start_t:
            main["agent_start_times"][agent_key] = start_t
        dur = branch.get("agent_durations", {}).get(agent_key)
        if dur is not None:
            if "agent_durations" not in main:
                main["agent_durations"] = {}
            main["agent_durations"][agent_key] = dur
        for item in branch.get("failed_agents") or []:
            if item not in main["failed_agents"]:
                main["failed_agents"].append(item)
        for item in branch.get("completed_agents") or []:
            if item not in main["completed_agents"]:
                main["completed_agents"].append(item)

    def _process_parallel_agent_result(
        self,
        state: WorkflowState,
        agent_name: str,
        result: WorkflowState,
        result_key: str,
        default_value: Any = None,
    ) -> None:
        """Process result from a parallel agent execution."""
        state["current_phase"] = WorkflowPhase.DOCUMENT_GENERATION
        state["current_agent"] = key_to_agent(agent_name)

        # Safely get agent status with fallback
        agent_status = result.get("agent_status", {}).get(
            agent_name, AgentStatus.FAILED
        )
        state["agent_status"][agent_name] = agent_status

        agent_enum: Agent = key_to_agent(agent_name)
        if agent_status == AgentStatus.COMPLETED:
            if agent_enum not in state["completed_agents"]:
                state["completed_agents"].append(agent_enum)
            logger.info('%s completed successfully', sanitize_log_value(agent_name))
        else:
            if agent_enum not in state["failed_agents"]:
                state["failed_agents"].append(agent_enum)
            logger.warning('%s failed', sanitize_log_value(agent_name))

        self._merge_messages(state, result)

        # Safely get agent start time with fallback
        agent_start_time = result.get("agent_start_times", {}).get(agent_name)
        if agent_start_time:
            state["agent_start_times"][agent_name] = agent_start_time

        # Merge agent duration
        agent_duration = result.get("agent_durations", {}).get(agent_name)
        if agent_duration is not None:
            if "agent_durations" not in state:
                state["agent_durations"] = {}
            state["agent_durations"][agent_name] = agent_duration

        state[result_key] = result.get(result_key, default_value)

    def _merge_messages(
        self, target_state: WorkflowState, source_state: WorkflowState
    ) -> None:
        """Merge error and warning messages from source state into target state."""
        # Merge error messages if they exist in source state
        if source_state.get("error_messages"):
            for error_msg in source_state["error_messages"]:
                if error_msg not in target_state["error_messages"]:
                    target_state["error_messages"].append(error_msg)

        # Merge warning messages if they exist in source state
        if source_state.get("warning_messages"):
            for warning_msg in source_state["warning_messages"]:
                if warning_msg not in target_state["warning_messages"]:
                    target_state["warning_messages"].append(warning_msg)

    # =========================================================================
    # ROUTING FUNCTIONS
    # =========================================================================

    def _route_after_job_analysis(self, state: WorkflowState) -> str:
        """Route workflow after job analysis completion."""
        if state["agent_status"]["job_analyzer"] == AgentStatus.COMPLETED:
            return "success"
        else:
            return "error"

    def _route_after_profile_matching(self, state: WorkflowState) -> str:
        """Route after profile matching — any failure ends the workflow with no partial data."""
        if state["agent_status"].get(Agent.PROFILE_MATCHING.value) == AgentStatus.COMPLETED:
            return "success"
        return "error"

    def _route_gate_decision(self, state: WorkflowState) -> str:
        """Route workflow based on gate decision."""
        if state.get("workflow_status") == WorkflowStatus.AWAITING_CONFIRMATION:
            return "await_confirmation"
        else:
            return "continue"

    def _route_after_company_research(self, state: WorkflowState) -> str:
        """Route after company research: fail fast, or analysis vs document generation."""
        if state["agent_status"].get(Agent.COMPANY_RESEARCH.value) != AgentStatus.COMPLETED:
            return "error"
        prefs = state.get("workflow_preferences") or {}
        if prefs.get("auto_generate_documents", False):
            return "generate_documents"
        return "analysis_complete"

    # =========================================================================
    # STATE PERSISTENCE (PostgreSQL/SQLAlchemy)
    # =========================================================================

    async def _maybe_fail_duplicate_job_after_analyzer(self, state: WorkflowState) -> None:
        """
        After Job Analyzer returns structured title+company, fail this workflow if
        another non-deleted application already has the same normalized pair.

        Extension / manual submit often skip start-time title+company dedupe; this
        catches duplicates once the analyzer output is known (first write wins).
        """
        if self.db is None:
            return
        if state.get("_analyzer_dedupe_checked") is True:
            return
        if state.get("agent_status", {}).get(Agent.JOB_ANALYZER.value) != AgentStatus.COMPLETED:
            return
        ja = state.get("job_analysis")
        if not ja:
            return
        title = ja.get("job_title")
        company = ja.get("company_name")
        if not isinstance(title, str) or not isinstance(company, str):
            return
        try:
            uid = uuid.UUID(str(state["user_id"]))
        except (ValueError, TypeError):
            return

        try:
            conflict = await find_conflicting_job_application(
                self.db,
                user_id=uid,
                session_id=str(state["session_id"]),
                job_title=title,
                company_name=company,
            )
        except Exception as exc:
            logger.debug('Duplicate job check after analyzer failed (non-fatal): %s', sanitize_log_value(exc), exc_info=True)
            return

        if conflict is None:
            state["_analyzer_dedupe_checked"] = True
            return

        logger.info('Duplicate job after analyzer: user=%s session=%s conflicts with application id=%s', sanitize_log_value(uid), sanitize_log_value(state.get("session_id")), sanitize_log_value(conflict.id))

        state["agent_status"][Agent.JOB_ANALYZER.value] = AgentStatus.FAILED
        state["completed_agents"] = [
            a for a in state.get("completed_agents", []) if a != Agent.JOB_ANALYZER
        ]
        if Agent.JOB_ANALYZER not in state.get("failed_agents", []):
            state.setdefault("failed_agents", []).append(Agent.JOB_ANALYZER)

        state["workflow_status"] = WorkflowStatus.FAILED
        state["job_analysis"] = None
        add_error(state, _DUPLICATE_JOB_USER_MESSAGE, Agent.JOB_ANALYZER.value)

        await broadcast_agent_update(
            user_id=str(state.get("user_id", "")),
            session_id=str(state.get("session_id", "")),
            agent_name=Agent.JOB_ANALYZER.value,
            status="failed",
            message=_DUPLICATE_JOB_USER_MESSAGE,
        )

    async def _save_workflow_state(self, state: WorkflowState) -> None:
        """
        Save complete workflow state to PostgreSQL database for persistence and recovery.
        """
        try:
            if self.db is None:
                logger.warning("Database session not available for state persistence")
                return

            session_id = state["session_id"]

            # Query for existing session
            result = await self.db.execute(
                select(WorkflowSessionModel).where(
                    WorkflowSessionModel.session_id == session_id
                )
            )
            workflow_session = result.scalar_one_or_none()

            if workflow_session:
                await self._maybe_fail_duplicate_job_after_analyzer(state)

                # Update existing session
                wf_status_raw = (
                    state["workflow_status"].value
                    if hasattr(state["workflow_status"], "value")
                    else state["workflow_status"]
                )
                workflow_session.workflow_status = wf_status_raw
                wf_status_norm = str(wf_status_raw).strip().lower()
                workflow_session.current_phase = (
                    state["current_phase"].value
                    if hasattr(state["current_phase"], "value")
                    else state["current_phase"]
                )
                workflow_session.current_agent = (
                    state["current_agent"].value
                    if state["current_agent"] and hasattr(state["current_agent"], "value")
                    else state.get("current_agent")
                )
                workflow_session.agent_status = {
                    agent: status.value if hasattr(status, "value") else status
                    for agent, status in state["agent_status"].items()
                }
                workflow_session.completed_agents = [
                    agent.value if hasattr(agent, "value") else agent
                    for agent in state["completed_agents"]
                ]
                workflow_session.failed_agents = [
                    agent.value if hasattr(agent, "value") else agent
                    for agent in state["failed_agents"]
                ]
                workflow_session.error_messages = state["error_messages"]
                workflow_session.warning_messages = state["warning_messages"]
                # Convert ISO string to datetime for database storage
                end_time_str = state.get("processing_end_time")
                if end_time_str:
                    from datetime import datetime as dt
                    try:
                        workflow_session.processing_end_time = dt.fromisoformat(end_time_str)
                    except (ValueError, TypeError):
                        workflow_session.processing_end_time = None
                workflow_session.agent_start_times = state.get("agent_start_times", {})
                workflow_session.agent_durations = state.get("agent_durations", {})
                
                # Force SQLAlchemy to detect mutations on all JSONB fields.
                # Without flag_modified(), SQLAlchemy may skip JSONB fields in
                # the UPDATE statement because dict/list identity hasn't changed.
                from sqlalchemy.orm.attributes import flag_modified
                for _jsonb_field in (
                    "agent_status",
                    "completed_agents",
                    "failed_agents",
                    "error_messages",
                    "warning_messages",
                    "agent_start_times",
                    "agent_durations",
                ):
                    flag_modified(workflow_session, _jsonb_field)

                # Failed workflows: never persist agent output blobs (no partial results).
                if wf_status_norm == WorkflowStatus.FAILED.value:
                    for _col in (
                        "job_analysis",
                        "company_research",
                        "profile_matching",
                        "resume_recommendations",
                        "cover_letter",
                    ):
                        setattr(workflow_session, _col, None)
                        flag_modified(workflow_session, _col)
                else:
                    if state.get("job_analysis"):
                        workflow_session.job_analysis = state["job_analysis"]
                        flag_modified(workflow_session, "job_analysis")

                        # Early-write title/company to job_applications so the dashboard
                        # card shows real names as soon as Job Analyzer finishes (~4 s in).
                        # Use a savepoint so a constraint violation (e.g. duplicate title/company)
                        # only rolls back this inner write and never poisons the outer transaction.
                        _early_title = state["job_analysis"].get("job_title")
                        _early_company = state["job_analysis"].get("company_name")
                        if _early_title or _early_company:
                            _early_vals: Dict[str, Any] = {
                                "updated_at": datetime.now(timezone.utc)
                            }
                            if _early_title:
                                _early_vals["job_title"] = _early_title
                            if _early_company:
                                _early_vals["company_name"] = _early_company
                            try:
                                async with self.db.begin_nested():
                                    await self.db.execute(
                                        update(JobApplicationModel)
                                        .where(JobApplicationModel.session_id == session_id)
                                        .values(**_early_vals)
                                    )
                            except Exception as _upd_err:
                                logger.debug('Early title/company update skipped: %s', sanitize_log_value(_upd_err))
                    if state.get("company_research"):
                        workflow_session.company_research = state["company_research"]
                        flag_modified(workflow_session, "company_research")
                    if state.get("profile_matching"):
                        workflow_session.profile_matching = state["profile_matching"]
                        flag_modified(workflow_session, "profile_matching")
                    if state.get("resume_recommendations"):
                        workflow_session.resume_recommendations = state["resume_recommendations"]
                        flag_modified(workflow_session, "resume_recommendations")
                    if state.get("cover_letter"):
                        workflow_session.cover_letter = state["cover_letter"]
                        flag_modified(workflow_session, "cover_letter")

                await self.db.commit()
                logger.debug('Updated workflow session: %s', sanitize_log_value(session_id))
            else:
                logger.debug('Workflow session not found for update: %s', sanitize_log_value(session_id))

        except Exception as e:
            logger.warning('Failed to save workflow state for session %s: %s', sanitize_log_value(state.get('session_id', 'unknown')), sanitize_log_value(e))
            # Roll back so the session is clean for the next _save_workflow_state call.
            # Without this, a failed transaction leaves the session in an aborted state
            # and every subsequent save instantly fails with InFailedSQLTransactionError.
            try:
                await self.db.rollback()
            except Exception as rb_err:
                logger.debug('Rollback after failed state save: %s', sanitize_log_value(rb_err))
            # Don't raise exception - state saving failures shouldn't break the workflow

    async def _load_workflow_state(
        self, session_id: str, user_api_key: Optional[str] = None
    ) -> Optional[WorkflowState]:
        """
        Load workflow state from PostgreSQL database for resumption.
        
        Args:
            session_id: The session ID to load
            user_api_key: Optional user API key to include in the state (BYOK mode)
        """
        try:
            if self.db is None:
                logger.error("Database session not available")
                return None

            # Expire any cached objects to ensure we get fresh data from DB
            self.db.expire_all()

            result = await self.db.execute(
                select(WorkflowSessionModel).where(
                    WorkflowSessionModel.session_id == session_id
                )
            )
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning(
                    "No workflow state found for session %s",
                    sanitize_log_value(str(session_id)),
                )
                return None

            # Reconstruct WorkflowState from database record
            # Convert datetime to ISO string for workflow state
            start_time = (
                doc.processing_start_time.isoformat()
                if doc.processing_start_time
                else None
            )
            end_time = (
                doc.processing_end_time.isoformat()
                if doc.processing_end_time
                else None
            )
            restored_user_data = doc.user_data or {}
            restored_prefs = {
                **DEFAULT_WORKFLOW_PREFERENCES,
                **(restored_user_data.get("application_preferences") or {}),
            }
            state = WorkflowState(
                user_id=str(doc.user_id),
                session_id=doc.session_id,
                user_profile=restored_user_data,
                user_api_key=user_api_key,  # Include user API key from parameter
                llm_provider=restored_user_data.get("llm_provider"),
                workflow_preferences=restored_prefs,
                job_input_data=doc.job_input_data or {},
                job_analysis=doc.job_analysis,
                company_research=doc.company_research,
                profile_matching=doc.profile_matching,
                resume_recommendations=doc.resume_recommendations,
                cover_letter=doc.cover_letter,
                current_phase=WorkflowPhase(doc.current_phase),
                workflow_status=WorkflowStatus(doc.workflow_status),
                processing_start_time=start_time,
                processing_end_time=end_time,
                current_agent=(
                    Agent(doc.current_agent) if doc.current_agent else None
                ),
                agent_status={
                    k: AgentStatus(v) for k, v in (doc.agent_status or {}).items()
                },
                completed_agents=[
                    Agent(a) for a in (doc.completed_agents or [])
                ],
                failed_agents=[Agent(a) for a in (doc.failed_agents or [])],
                error_messages=doc.error_messages or [],
                warning_messages=doc.warning_messages or [],
                agent_start_times=doc.agent_start_times or {},
                agent_durations=doc.agent_durations or {},
            )

            logger.info(
                "Loaded workflow state for session %s",
                sanitize_log_value(str(session_id)),
            )
            return state

        except Exception as e:
            logger.error(
                "Failed to load workflow state for session %s: %s",
                sanitize_log_value(str(session_id)),
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            return None


# =============================================================================
# PUBLIC FUNCTIONS (Legacy compatibility)
# =============================================================================


async def get_initialized_workflow(db: Optional[AsyncSession] = None) -> "JobApplicationWorkflow":
    """
    Get or create a globally initialized workflow instance.

    Args:
        db: Optional database session

    Returns:
        JobApplicationWorkflow: Initialized workflow instance

    Raises:
        RuntimeError: If workflow initialization fails
    """
    global _workflow_instance

    if _workflow_instance is None:
        _workflow_instance = JobApplicationWorkflow(db)
        await _workflow_instance.initialize()
    elif db is not None:
        _workflow_instance.db = db

    return _workflow_instance

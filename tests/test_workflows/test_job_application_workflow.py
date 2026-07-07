"""
Unit tests for workflows/job_application_workflow.py.

All LLM agents are mocked at the process() level; WebSocket and DB are patched.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from models.database import AuthMethod, JobApplication, User, WorkflowSession
from tests.test_api.conftest import _NullSessionLocal
from workflows.job_application_workflow import JobApplicationWorkflow, DEFAULT_WORKFLOW_PREFERENCES
from workflows.state_schema import (
    Agent,
    AgentStatus,
    WorkflowPhase,
    WorkflowStatus,
    create_initial_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LONG_JOB = (
    "Senior Platform Engineer role requiring Python, distributed systems, "
    "and collaboration across teams. " * 3
)


async def _ensure_user(uid: uuid.UUID) -> None:
    async with _NullSessionLocal() as db:
        from sqlalchemy import select

        existing = await db.execute(select(User).where(User.id == uid))
        if existing.scalar_one_or_none() is None:
            db.add(
                User(
                    id=uid,
                    email=f"wf-unit-{uid.hex[:8]}@example.com",
                    password_hash="$2b$12$placeholder",
                    auth_method=AuthMethod.LOCAL.value,
                    full_name="Unit Test User",
                    profile_completed=True,
                    profile_completion_percentage=100,
                )
            )
            await db.commit()


def _base_state(**overrides) -> Dict[str, Any]:
    state = create_initial_state(
        user_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user_profile={
            "full_name": "Test User",
            "email": "t@example.com",
            "professional_title": "Engineer",
            "years_experience": 5,
            "skills": ["Python"],
            "work_experience": [],
        },
        job_input_data={"input_method": "manual", "job_content": LONG_JOB},
        workflow_preferences=dict(DEFAULT_WORKFLOW_PREFERENCES),
    )
    state.update(overrides)
    return state


class _MockAgent:
    """Minimal agent stub with async process()."""

    def __init__(self, result_key: str, payload: Dict[str, Any], *, fail: bool = False):
        self.result_key = result_key
        self.payload = payload
        self.fail = fail

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail:
            raise RuntimeError("agent failed")
        state[self.result_key] = self.payload
        return state


@pytest.fixture
def mock_ws():
    with patch("workflows.job_application_workflow.broadcast_agent_update", AsyncMock()), \
         patch("workflows.job_application_workflow.broadcast_phase_change", AsyncMock()), \
         patch("workflows.job_application_workflow.broadcast_workflow_complete", AsyncMock()), \
         patch("workflows.job_application_workflow.broadcast_workflow_error", AsyncMock()), \
         patch("workflows.job_application_workflow.broadcast_gate_decision", AsyncMock()):
        yield


@pytest.fixture
async def workflow_with_db():
    async with _NullSessionLocal() as db:
        wf = JobApplicationWorkflow(db)
        wf.job_analyzer = _MockAgent(
            "job_analysis",
            {"job_title": "Engineer", "company_name": "Acme Corp"},
        )
        wf.profile_matching = _MockAgent(
            "profile_matching",
            {
                "executive_summary": {"recommendation": "GOOD_MATCH"},
                "final_scores": {"overall_fit": 0.85},
            },
        )
        wf.company_research = _MockAgent("company_research", {"industry": "Tech"})
        wf.resume_advisor = _MockAgent("resume_recommendations", {"comprehensive_advice": {}})
        wf.cover_letter_writer = _MockAgent("cover_letter", {"content": "Dear team,"})
        wf.workflow = MagicMock()
        wf.continuation_workflow = MagicMock()
        yield wf, db


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRoutingFunctions:
    def test_route_after_job_analysis(self):
        wf = JobApplicationWorkflow()
        ok = _base_state(agent_status={"job_analyzer": AgentStatus.COMPLETED})
        bad = _base_state(agent_status={"job_analyzer": AgentStatus.FAILED})
        assert wf._route_after_job_analysis(ok) == "success"
        assert wf._route_after_job_analysis(bad) == "error"

    def test_route_after_profile_matching(self):
        wf = JobApplicationWorkflow()
        ok = _base_state(agent_status={Agent.PROFILE_MATCHING.value: AgentStatus.COMPLETED})
        assert wf._route_after_profile_matching(ok) == "success"
        assert wf._route_after_profile_matching(_base_state()) == "error"

    def test_route_gate_decision(self):
        wf = JobApplicationWorkflow()
        gated = _base_state(workflow_status=WorkflowStatus.AWAITING_CONFIRMATION)
        assert wf._route_gate_decision(gated) == "await_confirmation"
        assert wf._route_gate_decision(_base_state()) == "continue"

    def test_route_after_company_research(self):
        wf = JobApplicationWorkflow()
        ok = _base_state(
            agent_status={Agent.COMPANY_RESEARCH.value: AgentStatus.COMPLETED},
            workflow_preferences={"auto_generate_documents": False},
        )
        docs = _base_state(
            agent_status={Agent.COMPANY_RESEARCH.value: AgentStatus.COMPLETED},
            workflow_preferences={"auto_generate_documents": True},
        )
        fail = _base_state(agent_status={Agent.COMPANY_RESEARCH.value: AgentStatus.FAILED})
        assert wf._route_after_company_research(ok) == "analysis_complete"
        assert wf._route_after_company_research(docs) == "generate_documents"
        assert wf._route_after_company_research(fail) == "error"


# ---------------------------------------------------------------------------
# Gate decision + error handler
# ---------------------------------------------------------------------------


class TestGateAndErrorNodes:
    @pytest.mark.asyncio
    async def test_gate_passes_high_match(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={
                "executive_summary": {"recommendation": "GOOD_MATCH"},
                "final_scores": {"overall_fit": 0.9},
            }
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()) as save_mock:
            out = await wf._gate_decision_node(state)
        assert out["workflow_status"] != WorkflowStatus.AWAITING_CONFIRMATION
        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_gate_triggers_low_match(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={
                "executive_summary": {"recommendation": "WEAK_MATCH"},
                "final_scores": {"overall_fit": 0.2},
            }
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()) as save_mock:
            out = await wf._gate_decision_node(state)
        assert out["workflow_status"] == WorkflowStatus.AWAITING_CONFIRMATION
        save_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_gate_skips_when_no_profile_matching(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(profile_matching=None)
        out = await wf._gate_decision_node(state)
        assert out.get("profile_matching") is None

    @pytest.mark.asyncio
    async def test_error_handler_clears_outputs(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            job_analysis={"job_title": "X"},
            error_messages=["Failed"],
            completed_agents=[Agent.JOB_ANALYZER],
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._error_handler_node(state)
        assert out["workflow_status"] == WorkflowStatus.FAILED
        assert out["job_analysis"] is None
        assert out["processing_end_time"]


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


class TestExecuteAgentNode:
    @pytest.mark.asyncio
    async def test_agent_success_updates_status(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        out = await wf._execute_agent_node(
            state,
            Agent.JOB_ANALYZER.value,
            wf.job_analyzer,
            cfg,
            save_state=False,
        )
        assert out["agent_status"][Agent.JOB_ANALYZER.value] == AgentStatus.COMPLETED
        assert Agent.JOB_ANALYZER in out["completed_agents"]
        assert out["job_analysis"]["job_title"] == "Engineer"

    @pytest.mark.asyncio
    async def test_agent_failure_marks_failed(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        wf.job_analyzer = _MockAgent("job_analysis", {}, fail=True)
        state = _base_state()
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._execute_agent_node(
                state,
                Agent.JOB_ANALYZER.value,
                wf.job_analyzer,
                cfg,
            )
        assert out["agent_status"][Agent.JOB_ANALYZER.value] == AgentStatus.FAILED
        assert out["error_messages"]

    @pytest.mark.asyncio
    async def test_uninitialized_agent_raises(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._execute_agent_node(
                state,
                Agent.JOB_ANALYZER.value,
                None,
                cfg,
            )
        assert out["agent_status"][Agent.JOB_ANALYZER.value] == AgentStatus.FAILED


# ---------------------------------------------------------------------------
# Parallel document generation
# ---------------------------------------------------------------------------


class TestDocumentGenerationParallel:
    @pytest.mark.asyncio
    async def test_parallel_success_completes_workflow(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={"final_scores": {"overall_fit": 0.8}},
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._document_generation_parallel_node(state)
        assert out["workflow_status"] == WorkflowStatus.COMPLETED
        assert out["resume_recommendations"]
        assert out["cover_letter"]

    @pytest.mark.asyncio
    async def test_parallel_failure_clears_outputs(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        wf.resume_advisor = _MockAgent("resume_recommendations", {}, fail=True)
        state = _base_state()
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._document_generation_parallel_node(state)
        assert out["workflow_status"] == WorkflowStatus.FAILED
        assert out["resume_recommendations"] is None


# ---------------------------------------------------------------------------
# Duplicate after analyzer + save state
# ---------------------------------------------------------------------------


class TestDuplicateAndSaveState:
    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_after_analyzer(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        other_session = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=other_session,
                    user_id=uid,
                    workflow_status=WorkflowStatus.COMPLETED.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=other_session,
                    job_title="Engineer",
                    company_name="Acme Corp",
                    status="completed",
                )
            )
            await db.commit()

            wf = JobApplicationWorkflow(db)
            state = _base_state(
                user_id=str(uid),
                session_id=session_id,
                agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
                job_analysis={"job_title": "Engineer", "company_name": "Acme Corp"},
                completed_agents=[Agent.JOB_ANALYZER],
            )
            await wf._maybe_fail_duplicate_job_after_analyzer(state)
            assert state["workflow_status"] == WorkflowStatus.FAILED
            assert state["job_analysis"] is None
            assert any("already have an application" in m for m in state["error_messages"])

    @pytest.mark.asyncio
    async def test_save_workflow_state_persists_success(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=session_id,
                    status="processing",
                )
            )
            await db.commit()

            wf = JobApplicationWorkflow(db)
            state = _base_state(
                user_id=str(uid),
                session_id=session_id,
                workflow_status=WorkflowStatus.IN_PROGRESS,
                current_phase=WorkflowPhase.JOB_ANALYSIS,
                agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
                completed_agents=[Agent.JOB_ANALYZER],
                job_analysis={"job_title": "New Role", "company_name": "Fresh Inc"},
            )
            await wf._save_workflow_state(state)

            row = (
                await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
            ).scalar_one()
            assert row.job_analysis["job_title"] == "New Role"

    @pytest.mark.asyncio
    async def test_save_workflow_state_strips_outputs_on_failed(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_analysis={"job_title": "Old"},
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            wf = JobApplicationWorkflow(db)
            state = _base_state(
                user_id=str(uid),
                session_id=session_id,
                workflow_status=WorkflowStatus.FAILED,
                current_phase=WorkflowPhase.ERROR,
                job_analysis={"job_title": "Should not persist"},
            )
            await wf._save_workflow_state(state)

            row = (
                await db.execute(
                    select(WorkflowSession).where(WorkflowSession.session_id == session_id)
                )
            ).scalar_one()
            assert row.job_analysis is None


# ---------------------------------------------------------------------------
# Initialize + run_initial_workflow (mocked graph)
# ---------------------------------------------------------------------------


class TestInitializeAndRun:
    @pytest.mark.asyncio
    async def test_initialize_short_circuits_when_built(self):
        wf = JobApplicationWorkflow()
        wf.workflow = MagicMock()
        with patch("workflows.job_application_workflow.get_gemini_client", AsyncMock()) as gem:
            await wf.initialize()
            gem.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_initial_workflow_invokes_graph(self, mock_ws):
        wf = JobApplicationWorkflow()
        final = _base_state(workflow_status=WorkflowStatus.ANALYSIS_COMPLETE)
        wf.workflow = MagicMock()
        wf.workflow.ainvoke = AsyncMock(return_value=final)

        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_save_workflow_state", AsyncMock()):
            result = await wf.run_initial_workflow(
                session_id=final["session_id"],
                user_id=final["user_id"],
                input_method="manual",
                job_input=LONG_JOB,
                user_data={"full_name": "U", "application_preferences": {}},
            )
        assert result["workflow_status"] == WorkflowStatus.ANALYSIS_COMPLETE

    @pytest.mark.asyncio
    async def test_load_workflow_state_from_db(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.ANALYSIS_COMPLETE.value,
                    current_phase=WorkflowPhase.ANALYSIS_COMPLETE.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U", "application_preferences": {}},
                    job_analysis={"job_title": "Loaded"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            wf = JobApplicationWorkflow(db)
            loaded = await wf._load_workflow_state(session_id, user_api_key="k")
            assert loaded is not None
            assert loaded["job_analysis"]["job_title"] == "Loaded"
            assert loaded["user_api_key"] == "k"


class TestHelperMerges:
    def test_merge_messages_dedupes(self):
        wf = JobApplicationWorkflow()
        main = _base_state(error_messages=["a"], warning_messages=["w1"])
        src = _base_state(error_messages=["a", "b"], warning_messages=["w2"])
        wf._merge_messages(main, src)
        assert main["error_messages"] == ["a", "b"]
        assert main["warning_messages"] == ["w1", "w2"]

    def test_clear_agent_outputs(self):
        wf = JobApplicationWorkflow()
        state = _base_state(job_analysis={"x": 1}, cover_letter={"content": "Hi"})
        wf._clear_agent_outputs_for_failed_workflow(state)
        assert state["job_analysis"] is None
        assert state["cover_letter"] is None


class TestInitializeBuildAndPublicMethods:
    @pytest.mark.asyncio
    async def test_initialize_builds_workflow_graphs(self, mock_ws):
        wf = JobApplicationWorkflow()
        with patch("workflows.job_application_workflow.get_gemini_client", AsyncMock(return_value=MagicMock())), \
             patch("workflows.job_application_workflow.get_redis_client", AsyncMock(return_value=None)):
            await wf.initialize()
        assert wf.workflow is not None
        assert wf.continuation_workflow is not None
        assert wf.job_analyzer is not None

    @pytest.mark.asyncio
    async def test_initialize_gemini_failure_raises(self):
        wf = JobApplicationWorkflow()
        with patch(
            "workflows.job_application_workflow.get_gemini_client",
            AsyncMock(side_effect=RuntimeError("no gemini")),
        ):
            with pytest.raises(RuntimeError, match="Gemini"):
                await wf.initialize()

    def test_state_to_dict_serializes_enums(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state(
            workflow_status=WorkflowStatus.COMPLETED,
            current_phase=WorkflowPhase.COMPLETED,
            current_agent=Agent.JOB_ANALYZER,
            agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
            completed_agents=[Agent.JOB_ANALYZER],
            job_analysis={"job_title": "Dev"},
            company_research={"industry": "Tech"},
            cover_letter={"content": "Hello"},
            resume_recommendations={"comprehensive_advice": {}},
        )
        d = wf._state_to_dict(state)
        assert d["workflow_status"] == "completed"
        assert d["job_analysis"]["job_title"] == "Dev"

    @pytest.mark.asyncio
    async def test_continue_workflow_after_gate(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    current_phase=WorkflowPhase.PROFILE_MATCHING.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U", "application_preferences": {}},
                    profile_matching={"final_scores": {"overall_fit": 0.8}},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()

            wf = JobApplicationWorkflow(db)
            final = _base_state(
                user_id=str(uid),
                session_id=session_id,
                workflow_status=WorkflowStatus.COMPLETED,
            )
            wf.continuation_workflow = MagicMock()
            wf.continuation_workflow.ainvoke = AsyncMock(return_value=final)

            with patch.object(wf, "initialize", AsyncMock()):
                result = await wf.continue_workflow_after_gate(session_id)
            assert result["workflow_status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_document_generation(self, mock_ws, workflow_with_db):
        wf, db = workflow_with_db
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)

        async with _NullSessionLocal() as session:
            session.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.ANALYSIS_COMPLETE.value,
                    current_phase=WorkflowPhase.ANALYSIS_COMPLETE.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U", "application_preferences": {}},
                    profile_matching={"final_scores": {"overall_fit": 0.8}},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        wf.db = db
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=_base_state(
                 user_id=str(uid),
                 session_id=session_id,
                 workflow_status=WorkflowStatus.ANALYSIS_COMPLETE,
                 profile_matching={"final_scores": {"overall_fit": 0.8}},
             ))), \
             patch.object(wf, "_document_generation_parallel_node", AsyncMock(return_value=_base_state(
                 user_id=str(uid),
                 session_id=session_id,
                 workflow_status=WorkflowStatus.COMPLETED,
                 resume_recommendations={"comprehensive_advice": {}},
                 cover_letter={"content": "Hi"},
             ))):
            result = await wf.run_document_generation(session_id)
        assert result["workflow_status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_initialized_workflow_singleton(self, mock_ws):
        from workflows import job_application_workflow as jaw

        jaw._workflow_instance = None
        with patch.object(JobApplicationWorkflow, "initialize", AsyncMock()):
            w1 = await jaw.get_initialized_workflow()
            w2 = await jaw.get_initialized_workflow()
            assert w1 is w2
        jaw._workflow_instance = None


class TestJobApplicationWorkflowCoverage:
    @pytest.mark.asyncio
    async def test_initialize_redis_failure_non_critical(self, mock_ws):
        wf = JobApplicationWorkflow()
        with patch(
            "workflows.job_application_workflow.get_gemini_client",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "workflows.job_application_workflow.get_redis_client",
            AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            await wf.initialize()
        assert wf.workflow is not None

    @pytest.mark.asyncio
    async def test_run_initial_workflow_not_initialized(self, mock_ws):
        wf = JobApplicationWorkflow()
        wf.workflow = None
        with patch.object(wf, "initialize", AsyncMock()):
            with pytest.raises(ValueError, match="not initialized"):
                await wf.run_initial_workflow(
                    session_id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    input_method="manual",
                    job_input=LONG_JOB,
                    user_data={"full_name": "U", "application_preferences": {}},
                )

    @pytest.mark.asyncio
    async def test_run_initial_workflow_timeout(self, mock_ws):
        wf = JobApplicationWorkflow()
        wf.workflow = MagicMock()
        wf.workflow.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch.object(wf, "initialize", AsyncMock()):
            with pytest.raises(asyncio.TimeoutError):
                await wf.run_initial_workflow(
                    session_id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    input_method="manual",
                    job_input=LONG_JOB,
                    user_data={"full_name": "U", "application_preferences": {}},
                )

    @pytest.mark.asyncio
    async def test_run_initial_workflow_logs_failure(self, mock_ws):
        wf = JobApplicationWorkflow()
        wf.workflow = MagicMock()
        wf.workflow.ainvoke = AsyncMock(side_effect=RuntimeError("graph failed"))

        with patch.object(wf, "initialize", AsyncMock()):
            with pytest.raises(RuntimeError, match="graph failed"):
                await wf.run_initial_workflow(
                    session_id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    input_method="manual",
                    job_input=LONG_JOB,
                    user_data={"full_name": "U", "application_preferences": {}},
                )

    @pytest.mark.asyncio
    async def test_continue_workflow_session_not_found(self, mock_ws):
        wf = JobApplicationWorkflow()
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await wf.continue_workflow_after_gate(str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_continue_workflow_wrong_status(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state(workflow_status=WorkflowStatus.COMPLETED)
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=state)):
            with pytest.raises(ValueError, match="cannot be continued"):
                await wf.continue_workflow_after_gate(state["session_id"])

    @pytest.mark.asyncio
    async def test_continue_workflow_not_initialized(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state(workflow_status=WorkflowStatus.IN_PROGRESS)
        wf.continuation_workflow = None
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=state)):
            with pytest.raises(ValueError, match="Continuation workflow"):
                await wf.continue_workflow_after_gate(state["session_id"])

    @pytest.mark.asyncio
    async def test_continue_workflow_timeout(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state(workflow_status=WorkflowStatus.IN_PROGRESS)
        wf.continuation_workflow = MagicMock()
        wf.continuation_workflow.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=state)):
            with pytest.raises(asyncio.TimeoutError):
                await wf.continue_workflow_after_gate(state["session_id"])

    @pytest.mark.asyncio
    async def test_run_document_generation_not_found(self, mock_ws):
        wf = JobApplicationWorkflow()
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="not found"):
                await wf.run_document_generation(str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_run_document_generation_wrong_status(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state(workflow_status=WorkflowStatus.COMPLETED)
        with patch.object(wf, "initialize", AsyncMock()), \
             patch.object(wf, "_load_workflow_state", AsyncMock(return_value=state)):
            with pytest.raises(ValueError, match="cannot be generated"):
                await wf.run_document_generation(state["session_id"])

    @pytest.mark.asyncio
    async def test_agent_success_records_duration(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        out = await wf._execute_agent_node(
            state,
            Agent.JOB_ANALYZER.value,
            wf.job_analyzer,
            cfg,
            save_state=False,
        )
        assert Agent.JOB_ANALYZER.value in out["agent_durations"]

    @pytest.mark.asyncio
    async def test_agent_failure_records_duration(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        wf.job_analyzer = _MockAgent("job_analysis", {}, fail=True)
        state = _base_state()
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._execute_agent_node(
                state,
                Agent.JOB_ANALYZER.value,
                wf.job_analyzer,
                cfg,
            )
        assert Agent.JOB_ANALYZER.value in out["agent_durations"]

    @pytest.mark.asyncio
    async def test_job_analyzer_node_sets_in_progress(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        with patch.object(wf, "_execute_agent_node", AsyncMock(return_value=state)) as exec_node:
            await wf._job_analyzer_node(state)
        exec_node.assert_awaited_once()
        assert state["workflow_status"] == WorkflowStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_profile_matching_node(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        with patch.object(wf, "_execute_agent_node", AsyncMock(return_value=state)) as exec_node:
            await wf._profile_matching_node(state)
        exec_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gate_pass_broadcasts_phase_change(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={
                "executive_summary": {"recommendation": "GOOD_MATCH"},
                "final_scores": {"overall_fit": 0.9},
            }
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            await wf._gate_decision_node(state)

    @pytest.mark.asyncio
    async def test_company_research_resumes_from_gate(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(workflow_status=WorkflowStatus.AWAITING_CONFIRMATION)
        with patch.object(wf, "_execute_agent_node", AsyncMock(return_value=state)) as exec_node:
            await wf._company_research_node(state)
        assert state["workflow_status"] == WorkflowStatus.IN_PROGRESS
        exec_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_analysis_complete_node(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={"final_scores": {"overall_fit": 0.75}},
            completed_agents=[Agent.JOB_ANALYZER, Agent.PROFILE_MATCHING, Agent.COMPANY_RESEARCH],
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._analysis_complete_node(state)
        assert out["workflow_status"] == WorkflowStatus.ANALYSIS_COMPLETE

    @pytest.mark.asyncio
    async def test_error_handler_no_completed_agents(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(error_messages=["Failed"], completed_agents=[])
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._error_handler_node(state)
        assert out["workflow_status"] == WorkflowStatus.FAILED

    @pytest.mark.asyncio
    async def test_merge_parallel_branch_durations(self):
        wf = JobApplicationWorkflow()
        main = _base_state(agent_durations={})
        branch = _base_state(
            agent_durations={Agent.RESUME_ADVISOR.value: 123.0},
            failed_agents=[Agent.RESUME_ADVISOR],
            completed_agents=[Agent.RESUME_ADVISOR],
        )
        wf._merge_parallel_branch_into_main(main, branch, Agent.RESUME_ADVISOR.value)
        assert main["agent_durations"][Agent.RESUME_ADVISOR.value] == 123.0

    def test_process_parallel_agent_result_failure(self):
        wf = JobApplicationWorkflow()
        main = _base_state()
        branch = _base_state(
            agent_status={Agent.RESUME_ADVISOR.value: AgentStatus.FAILED},
            error_messages=["bad"],
        )
        wf._process_parallel_agent_result(
            main,
            Agent.RESUME_ADVISOR.value,
            branch,
            "resume_recommendations",
        )
        assert Agent.RESUME_ADVISOR in main["failed_agents"]

    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_early_returns(self, mock_ws):
        wf = JobApplicationWorkflow()
        state = _base_state()
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

        wf.db = MagicMock()
        state["_analyzer_dedupe_checked"] = True
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

        state.pop("_analyzer_dedupe_checked")
        state["job_analysis"] = None
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

        state["job_analysis"] = {"job_title": 1, "company_name": "Acme"}
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_check_exception(self, mock_ws):
        wf = JobApplicationWorkflow()
        wf.db = MagicMock()
        state = _base_state(
            agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
            job_analysis={"job_title": "Engineer", "company_name": "Acme"},
        )
        with patch(
            "workflows.job_application_workflow.find_conflicting_job_application",
            AsyncMock(side_effect=RuntimeError("db")),
        ):
            await wf._maybe_fail_duplicate_job_after_analyzer(state)

    @pytest.mark.asyncio
    async def test_save_workflow_state_without_db(self, mock_ws):
        wf = JobApplicationWorkflow(db=None)
        await wf._save_workflow_state(_base_state())

    @pytest.mark.asyncio
    async def test_save_workflow_state_invalid_end_time(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            wf = JobApplicationWorkflow(db)
            state = _base_state(
                user_id=str(uid),
                session_id=session_id,
                workflow_status=WorkflowStatus.COMPLETED,
                current_phase=WorkflowPhase.COMPLETED,
                processing_end_time="not-a-date",
                job_analysis={"job_title": "Role", "company_name": "Co"},
                company_research={"industry": "Tech"},
                profile_matching={"final_scores": {}},
                resume_recommendations={"comprehensive_advice": {}},
                cover_letter={"content": "Hi"},
            )
            await wf._save_workflow_state(state)

    @pytest.mark.asyncio
    async def test_save_workflow_state_early_update_exception(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            db.add(
                JobApplication(
                    id=uuid.uuid4(),
                    user_id=uid,
                    session_id=session_id,
                    status="processing",
                )
            )
            await db.commit()
            wf = JobApplicationWorkflow(db)
            state = _base_state(
                user_id=str(uid),
                session_id=session_id,
                workflow_status=WorkflowStatus.IN_PROGRESS,
                current_phase=WorkflowPhase.JOB_ANALYSIS,
                agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
                job_analysis={"job_title": "Role", "company_name": "Co"},
            )

            @asynccontextmanager
            async def _fail_nested():
                raise RuntimeError("constraint")
                yield  # pragma: no cover

            with patch.object(db, "begin_nested", _fail_nested):
                await wf._save_workflow_state(state)

    @pytest.mark.asyncio
    async def test_save_workflow_state_missing_session(self, mock_ws):
        wf = JobApplicationWorkflow()
        async with _NullSessionLocal() as db:
            wf.db = db
            await wf._save_workflow_state(
                _base_state(session_id=str(uuid.uuid4()))
            )

    @pytest.mark.asyncio
    async def test_save_workflow_state_rollback_on_error(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            wf = JobApplicationWorkflow(db)
            with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("commit fail"))):
                await wf._save_workflow_state(_base_state(user_id=str(uid), session_id=session_id))

    @pytest.mark.asyncio
    async def test_load_workflow_state_no_db(self, mock_ws):
        wf = JobApplicationWorkflow(db=None)
        assert await wf._load_workflow_state(str(uuid.uuid4())) is None

    @pytest.mark.asyncio
    async def test_load_workflow_state_not_found(self, mock_ws):
        async with _NullSessionLocal() as db:
            wf = JobApplicationWorkflow(db)
            assert await wf._load_workflow_state(str(uuid.uuid4())) is None

    @pytest.mark.asyncio
    async def test_load_workflow_state_exception(self, mock_ws):
        async with _NullSessionLocal() as db:
            wf = JobApplicationWorkflow(db)
            with patch.object(db, "expire_all", side_effect=RuntimeError("boom")):
                assert await wf._load_workflow_state(str(uuid.uuid4())) is None

    @pytest.mark.asyncio
    async def test_get_initialized_workflow_updates_db(self, mock_ws):
        from workflows import job_application_workflow as jaw

        jaw._workflow_instance = None
        async with _NullSessionLocal() as db:
            with patch.object(JobApplicationWorkflow, "initialize", AsyncMock()):
                inst = await jaw.get_initialized_workflow(db)
                assert inst.db is db
        jaw._workflow_instance = None


class TestJobApplicationWorkflowRemainingCoverage:
    @pytest.mark.asyncio
    async def test_gate_non_numeric_fit_defaults_zero(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state(
            profile_matching={
                "executive_summary": {"recommendation": "WEAK_MATCH"},
                "final_scores": {"overall_fit": "not-a-number"},
            }
        )
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._gate_decision_node(state)
        assert out["workflow_status"] == WorkflowStatus.AWAITING_CONFIRMATION

    @pytest.mark.asyncio
    async def test_execute_agent_initializes_durations_on_success(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        state = _base_state()
        state.pop("agent_durations", None)
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        out = await wf._execute_agent_node(
            state,
            Agent.JOB_ANALYZER.value,
            wf.job_analyzer,
            cfg,
            save_state=False,
        )
        assert "agent_durations" in out

    @pytest.mark.asyncio
    async def test_execute_agent_initializes_durations_on_failure(self, workflow_with_db, mock_ws):
        wf, db = workflow_with_db
        wf.job_analyzer = _MockAgent("job_analysis", {}, fail=True)
        state = _base_state()
        state.pop("agent_durations", None)
        cfg = {"display_name": "Job analysis", "phase": WorkflowPhase.JOB_ANALYSIS}
        with patch.object(wf, "_save_workflow_state", AsyncMock()):
            out = await wf._execute_agent_node(
                state,
                Agent.JOB_ANALYZER.value,
                wf.job_analyzer,
                cfg,
            )
        assert "agent_durations" in out

    @pytest.mark.asyncio
    async def test_merge_parallel_branch_with_duration(self):
        wf = JobApplicationWorkflow()
        main = _base_state()
        main.pop("agent_durations", None)
        branch = _base_state(agent_durations={Agent.COVER_LETTER_WRITER.value: 50.0})
        wf._merge_parallel_branch_into_main(main, branch, Agent.COVER_LETTER_WRITER.value)
        assert main["agent_durations"][Agent.COVER_LETTER_WRITER.value] == 50.0

    def test_process_parallel_agent_result_merges_duration(self):
        wf = JobApplicationWorkflow()
        main = _base_state()
        main.pop("agent_durations", None)
        branch = _base_state(
            agent_status={Agent.COVER_LETTER_WRITER.value: AgentStatus.COMPLETED},
            agent_durations={Agent.COVER_LETTER_WRITER.value: 99.0},
        )
        wf._process_parallel_agent_result(
            main,
            Agent.COVER_LETTER_WRITER.value,
            branch,
            "cover_letter",
        )
        assert main["agent_durations"][Agent.COVER_LETTER_WRITER.value] == 99.0

    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_invalid_user_id(self, mock_ws):
        wf = JobApplicationWorkflow(db=MagicMock())
        state = _base_state(
            user_id="not-a-uuid",
            agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
            job_analysis={"job_title": "Engineer", "company_name": "Acme"},
        )
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_empty_job_analysis_dict(self, mock_ws):
        wf = JobApplicationWorkflow(db=MagicMock())
        state = _base_state(
            agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
            job_analysis={},
        )
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

    @pytest.mark.asyncio
    async def test_maybe_fail_duplicate_non_string_company(self, mock_ws):
        wf = JobApplicationWorkflow(db=MagicMock())
        state = _base_state(
            agent_status={Agent.JOB_ANALYZER.value: AgentStatus.COMPLETED},
            job_analysis={"job_title": "Engineer", "company_name": 123},
        )
        await wf._maybe_fail_duplicate_job_after_analyzer(state)

    @pytest.mark.asyncio
    async def test_save_workflow_state_rollback_failure_logged(self, mock_ws):
        uid = uuid.uuid4()
        session_id = str(uuid.uuid4())
        await _ensure_user(uid)
        async with _NullSessionLocal() as db:
            db.add(
                WorkflowSession(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    user_id=uid,
                    workflow_status=WorkflowStatus.IN_PROGRESS.value,
                    job_input_data={"input_method": "manual"},
                    user_data={"full_name": "U"},
                    processing_start_time=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            wf = JobApplicationWorkflow(db)
            with patch.object(db, "commit", AsyncMock(side_effect=RuntimeError("commit fail"))), \
                 patch.object(db, "rollback", AsyncMock(side_effect=RuntimeError("rollback fail"))):
                await wf._save_workflow_state(
                    _base_state(user_id=str(uid), session_id=session_id)
                )

    @pytest.mark.asyncio
    async def test_get_initialized_workflow_reuses_instance_with_db(self, mock_ws):
        from workflows import job_application_workflow as jaw

        async with _NullSessionLocal() as db:
            existing = JobApplicationWorkflow(db)
            existing.workflow = MagicMock()
            jaw._workflow_instance = existing
            inst = await jaw.get_initialized_workflow(db)
            assert inst is existing
            assert inst.db is db
        jaw._workflow_instance = None

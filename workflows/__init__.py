"""
LangGraph workflow modules for RoleMule.

- job_application_workflow: Main workflow with 5 agents
- state_schema: Workflow state TypedDict and enums
"""

from .state_schema import (
    WorkflowState,
    InputMethod,
    NodeName,
    WorkflowPhase,
    WorkflowStatus,
    AgentStatus,
)
from .job_application_workflow import JobApplicationWorkflow, get_initialized_workflow

__all__ = [
    "WorkflowState",
    "InputMethod",
    "NodeName",
    "WorkflowPhase",
    "WorkflowStatus",
    "AgentStatus",
    "JobApplicationWorkflow",
    "get_initialized_workflow",
]

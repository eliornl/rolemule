"""
FastAPI API Routers for RoleMule.

Routers:
- auth: Authentication, OAuth, email verification, password reset
- profile: User profile, API keys (BYOK), GDPR compliance
- applications: Job application CRUD and tracking
- workflow: LangGraph workflow orchestration
- websocket: Real-time WebSocket updates
- interview_prep: Interview preparation generation
- tools: Career communication tools (6 tools)
- admin: Admin endpoints (maintenance mode)
"""

from .auth import router as auth_router
from .profile import router as profile_router
from .applications import router as applications_router
from .workflow import router as workflow_router
from .websocket import router as websocket_router
from .interview_prep import router as interview_prep_router
from .tools import router as tools_router
from .admin import router as admin_router

__all__ = [
    "auth_router",
    "profile_router",
    "applications_router",
    "workflow_router",
    "websocket_router",
    "interview_prep_router",
    "tools_router",
    "admin_router",
]

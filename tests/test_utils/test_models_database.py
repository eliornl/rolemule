"""Unit tests for models.database to_dict helpers and UUID utilities."""

import uuid
from datetime import datetime, timezone

from models.database import (
    AuthMethod,
    JobApplication,
    User,
    UserProfile,
    UserResumeAsset,
    UserWorkflowPreferences,
    str_to_uuid,
    uuid_to_str,
)


def test_user_to_dict() -> None:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    user = User(
        id=uid,
        email="u@example.com",
        password_hash="hash",
        auth_method=AuthMethod.LOCAL.value,
        full_name="Test User",
        profile_completed=True,
        profile_completion_percentage=100,
        is_admin=False,
        email_verified=True,
        last_login=now,
        created_at=now,
        updated_at=now,
    )
    d = user.to_dict()
    assert d["id"] == str(uid)
    assert d["email"] == "u@example.com"
    assert d["has_gemini_api_key"] is False


def test_user_resume_asset_to_dict() -> None:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    asset = UserResumeAsset(
        id=uuid.uuid4(),
        user_id=uid,
        original_filename="cv.pdf",
        mime_type="application/pdf",
        byte_size=1024,
        sha256_hex="abc",
        created_at=now,
        updated_at=now,
    )
    d = asset.to_dict()
    assert d["original_filename"] == "cv.pdf"
    assert d["user_id"] == str(uid)


def test_user_workflow_preferences_to_dict() -> None:
    prefs = UserWorkflowPreferences(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        workflow_gate_threshold=0.6,
        auto_generate_documents=True,
        cover_letter_tone="professional",
        resume_length="concise",
        preferred_model="gemini-3.5-flash",
    )
    d = prefs.to_dict()
    assert d["workflow_gate_threshold"] == 0.6
    assert d["preferred_model"] == "gemini-3.5-flash"


def test_uuid_helpers() -> None:
    uid = uuid.uuid4()
    assert uuid_to_str(uid) == str(uid)
    assert uuid_to_str(None) is None
    assert str_to_uuid(str(uid)) == uid
    assert str_to_uuid("") is None
    assert str_to_uuid("not-a-uuid") is None


def test_user_profile_to_dict() -> None:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    profile = UserProfile(
        id=uuid.uuid4(),
        user_id=uid,
        city="Toronto",
        state="ON",
        country="Canada",
        professional_title="Engineer",
        years_experience=5,
        summary="Summary text",
        work_experience=None,
        education=None,
        skills=None,
        created_at=now,
        updated_at=now,
    )
    d = profile.to_dict()
    assert d["user_id"] == str(uid)
    assert d["work_experience"] == []
    assert d["education"] == []
    assert d["skills"] == []


def test_workflow_session_to_dict() -> None:
    from models.database import WorkflowSession

    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    session = WorkflowSession(
        id=uuid.uuid4(),
        session_id="sess-123",
        user_id=uid,
        workflow_status="completed",
        current_phase="done",
        current_agent=None,
        agent_status=None,
        completed_agents=None,
        failed_agents=None,
        error_messages=None,
        warning_messages=None,
        job_input_data=None,
        created_at=now,
        updated_at=now,
    )
    d = session.to_dict()
    assert d["session_id"] == "sess-123"
    assert d["agent_status"] == {}
    assert d["completed_agents"] == []


def test_job_application_to_dict() -> None:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    app = JobApplication(
        id=uuid.uuid4(),
        user_id=uid,
        session_id="sess-456",
        job_title="Engineer",
        company_name="Acme",
        job_url="https://example.com/jobs/1",
        match_score=0.85,
        status="applied",
        applied_date=now,
        response_date=None,
        notes="Follow up",
        created_at=now,
        updated_at=now,
    )
    d = app.to_dict()
    assert d["job_title"] == "Engineer"
    assert d["applied_date"] is not None
    assert d["response_date"] is None

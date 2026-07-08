"""Shared helpers for CLI command tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


def build_mock_client() -> MagicMock:
    """Return a MagicMock with happy-path defaults for every CLI resource."""
    client = MagicMock()

    client.auth.login.return_value = {
        "access_token": "jwt-login",
        "user": {"email": "user@example.com"},
    }
    client.auth.verify.return_value = {
        "email": "user@example.com",
        "success": True,
        "profile_completed": True,
    }
    client.auth.refresh.return_value = {"access_token": "jwt-refreshed", "expires_in": 3600}
    client.auth.register.return_value = {"message": "Registration successful"}
    client.auth.verify_code.return_value = {"access_token": "jwt-verified", "message": "Verified"}
    client.auth.resend_verification.return_value = {"message": "If applicable, email sent"}
    client.auth.verification_status.return_value = {"email_verified": True}
    client.auth.extension_status.return_value = {"authenticated": True, "profile_completed": True}
    client.auth.email_status.return_value = {"smtp_configured": False}
    client.auth.oauth_status.return_value = {"google_oauth_enabled": True}
    client.auth.change_password.return_value = {"message": "Password changed"}
    client.auth.logout.return_value = {}
    client.auth.create_pat.return_value = {
        "id": "pat-1",
        "name": "CLI",
        "token_prefix": "ap_pat_ab",
        "token": "ap_pat_secret_token_value",
        "expires_at": None,
        "created_at": "2026-07-08T00:00:00Z",
    }
    client.auth.list_pats.return_value = {
        "tokens": [
            {"id": "pat-1", "name": "CLI", "token_prefix": "ap_pat_ab", "active": True},
        ]
    }
    client.auth.revoke_pat.return_value = {"message": "Token revoked", "id": "pat-1"}

    client.profile.show.return_value = {"profile_data": {"city": "Austin"}}
    client.profile.status.return_value = {"profile_completed": True, "completion_percentage": 100}
    client.profile.complete.return_value = {"profile_completed": True}
    client.profile.update_basic_info.return_value = {"updated": True}
    client.profile.update_work_experience.return_value = {"updated": True}
    client.profile.update_education.return_value = {"updated": True}
    client.profile.update_skills.return_value = {"updated": True}
    client.profile.update_career_preferences.return_value = {"updated": True}
    client.profile.update_notifications.return_value = {"updated": True}
    client.profile.parse_resume.return_value = {"parsed": True}
    client.profile.download_resume.return_value = (b"%PDF-resume", {"content-disposition": 'attachment; filename="resume.pdf"'})
    client.profile.delete_resume.return_value = {"deleted": True}
    client.profile.api_key_status.return_value = {"has_user_key": True, "key_preview": "Gsk-…abc"}
    client.profile.api_key_set.return_value = {"has_user_key": True}
    client.profile.api_key_delete.return_value = {"deleted": True}
    client.profile.api_key_validate.return_value = {"valid": True, "message": "Valid key"}
    client.profile.workflow_preferences_show.return_value = {"preferences": {}}
    client.profile.workflow_preferences_set.return_value = {"updated": True}
    client.profile.export_data.return_value = (b'{"export": true}', {"content-disposition": 'attachment; filename="export.json"'})
    client.profile.clear_data.return_value = {"cleared": True}
    client.profile.delete_account.return_value = {"deleted": True}

    client.workflow.start.return_value = {"session_id": "sess-1", "status": "initialized", "message": "Started"}
    client.workflow.get_status.return_value = {"session_id": "sess-1", "status": "completed", "progress_percentage": 100}
    client.workflow.get_results.return_value = {
        "session_id": "sess-1",
        "status": "completed",
        "cover_letter": {"content": "Dear hiring manager"},
        "job_analysis": {"job_title": "Engineer"},
    }
    client.workflow.history.return_value = {"sessions": [], "total": 0}
    client.workflow.continue_workflow.return_value = {"session_id": "sess-1", "status": "in_progress", "message": "Resumed"}
    client.workflow.generate_documents.return_value = {"message": "Generating documents"}
    client.workflow.regenerate_cover_letter.return_value = {"message": "Cover letter regenerated"}
    client.workflow.regenerate_resume.return_value = {"message": "Resume regenerated"}
    client.workflow.generate_interview_prep.return_value = {"message": "Interview prep started"}

    client.applications.list.return_value = {"applications": [], "total": 0}
    client.applications.get.return_value = {
        "id": "app-1",
        "job_title": "Engineer",
        "company_name": "Acme",
        "status": "completed",
        "match_score": 0.9,
        "workflow_session_id": "sess-1",
    }
    client.applications.stats.return_value = {"total": 0, "applied": 0}
    client.applications.update_status.return_value = {"updated": True}
    client.applications.update_notes.return_value = {"updated": True}
    client.applications.delete.return_value = {"deleted": True, "message": "Application deleted."}
    client.applications.download.return_value = (b"zip-bytes", {"content-disposition": 'attachment; filename="app.zip"'})

    client.interview_prep.show.return_value = {
        "session_id": "sess-1",
        "has_interview_prep": True,
        "interview_prep": {"confidence_boosters": ["You got this"]},
    }
    client.interview_prep.status.return_value = {"session_id": "sess-1", "is_generating": False, "has_interview_prep": True}
    client.interview_prep.generate.return_value = {"session_id": "sess-1", "status": "generating", "message": "Started"}
    client.interview_prep.delete.return_value = None

    client.cv_optimizer.start.return_value = {"session_id": "sess-1", "status": "started", "message": "Started"}
    client.cv_optimizer.show.return_value = {"session_id": "sess-1", "has_result": True, "result": {"best_score": 8.0}}
    client.cv_optimizer.status.return_value = {"session_id": "sess-1", "is_running": False}
    client.cv_optimizer.download_cv.return_value = (b"odt", {"content-disposition": 'attachment; filename="cv.odt"'})
    client.cv_optimizer.clear.return_value = {"cleared": True}

    client.tools.followup_stages.return_value = {"stages": [{"value": "after_interview", "label": "After interview"}]}
    client.tools.thank_you.return_value = {"subject_line": "Thanks", "email_body": "Dear Jane"}
    client.tools.followup.return_value = {"subject_line": "Follow up", "email_body": "Checking in"}
    client.tools.salary_coach.return_value = {"job_title": "Eng", "strategy_overview": {"recommended_approach": "Collaborative"}}
    client.tools.rejection_analysis.return_value = {"analysis_summary": "Gap", "likely_reasons": []}
    client.tools.reference_request.return_value = {"subject_line": "Reference", "email_body": "Dear Alex"}
    client.tools.job_comparison.return_value = {"recommended_job": "Job A", "executive_summary": "Better fit", "jobs_analysis": []}

    client.extension.autofill_map.return_value = {
        "assignments": [{"field_uid": "0", "value": "Jane", "label_text": "Name"}],
        "skipped": [],
        "warnings": [],
    }

    client.admin.maintenance_status.return_value = {"enabled": False, "message": None, "estimated_end": None}
    client.admin.set_maintenance.return_value = {"enabled": True, "message": "Up", "estimated_end": "1h"}
    client.admin.clear_maintenance.return_value = {"message": "Maintenance mode disabled successfully"}
    client.admin.metrics.return_value = {
        "generated_at": "2026-07-08T00:00:00+00:00",
        "users": {"total": 1, "new_last_30d": 0, "active_last_7d": 1, "email_verified": 1},
        "workflows": {"total": 1, "completed": 1, "failed": 0, "in_progress": 0, "success_rate_pct": 100.0},
        "applications": {"total": 1, "new_last_30d": 0},
    }
    client.admin.cache_stats.return_value = {"status": "ok"}

    client.health.return_value = {"status": "healthy"}
    client.verify_token.return_value = {"success": True, "email": "user@example.com", "profile_completed": True}

    return client


def write_json_file(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path

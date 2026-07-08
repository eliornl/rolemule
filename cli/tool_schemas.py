# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "thank-you": {
        "interviewer_name": "Jane Smith",
        "interview_type": "video",
        "company_name": "Acme Corp",
        "job_title": "Senior Engineer",
        "key_discussion_points": ["Led migration project", "Discussed team structure"],
    },
    "followup": {
        "stage": "after_interview",
        "company_name": "Acme Corp",
        "job_title": "Senior Engineer",
        "contact_name": "Jane Smith",
        "days_since_contact": 5,
    },
    "salary-coach": {
        "job_title": "Senior Engineer",
        "company_name": "Acme Corp",
        "offered_salary": "$155,000",
        "target_range": "$165,000–$175,000",
    },
    "rejection-analysis": {
        "rejection_email": "Dear candidate, thank you for your interest. We have decided to move forward with other applicants.",
        "job_title": "Senior Engineer",
        "company_name": "Acme Corp",
    },
    "reference-request": {
        "reference_name": "Alex Rivera",
        "reference_relationship": "Former manager",
        "target_job_title": "Senior Engineer",
        "target_company": "Acme Corp",
    },
    "job-comparison": {
        "jobs": [
            {
                "title": "Senior Engineer",
                "company": "Acme Corp",
                "location": "Remote",
                "salary": "$160k",
                "description": "Build platform services…",
            },
            {
                "title": "Staff Engineer",
                "company": "Beta Inc",
                "location": "Hybrid — NYC",
                "salary": "$185k",
                "description": "Lead architecture for data pipeline…",
            },
        ],
        "user_context": {
            "priorities": "Growth, remote flexibility, compensation",
        },
    },
}

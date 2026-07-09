# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _truncate(value: str, width: int) -> str:
    text = value or ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _score_label(match_score: Any) -> str:
    if match_score is None:
        return "-"
    try:
        value = float(match_score)
    except (TypeError, ValueError):
        return "-"
    if value <= 1.0:
        return f"{round(value * 100)}%"
    return f"{round(value)}%"


def format_applications_table(data: Dict[str, Any]) -> str:
    """Render paginated application list as a fixed-width table."""
    apps: List[Dict[str, Any]] = data.get("applications") or []
    if not apps:
        return "No applications found."

    col_status = 12
    col_score = 6
    col_company = 24
    col_title = 32

    lines = [
        f"{'STATUS':<{col_status}} {'SCORE':<{col_score}} "
        f"{'COMPANY':<{col_company}} {'TITLE':<{col_title}} ID",
        "-" * 96,
    ]

    for app in apps:
        status = _truncate(str(app.get("status") or ""), col_status)
        score = _score_label(app.get("match_score"))
        company = _truncate(str(app.get("company_name") or ""), col_company)
        title = _truncate(str(app.get("job_title") or ""), col_title)
        app_id = str(app.get("id") or "")
        lines.append(
            f"{status:<{col_status}} {score:<{col_score}} "
            f"{company:<{col_company}} {title:<{col_title}} {app_id}"
        )

    total = data.get("total", len(apps))
    page = data.get("page", 1)
    data.get("per_page", len(apps))
    lines.append("")
    lines.append(f"Showing page {page} ({len(apps)} of {total} applications)")
    if data.get("has_next"):
        lines.append(f"Next page: --page {page + 1}")
    return "\n".join(lines)


def format_stats_human(data: Dict[str, Any]) -> str:
    """Render dashboard funnel stats."""
    return (
        f"Total: {data.get('total', 0)}  "
        f"Applied: {data.get('applied', 0)}  "
        f"Interviews: {data.get('interviews', 0)}  "
        f"Response rate: {data.get('response_rate', 0)}%"
    )


def format_application_show(data: Dict[str, Any]) -> str:
    """Render a single application summary for apps show."""
    lines = [
        f"ID: {data.get('id', '')}",
        f"Title: {data.get('job_title') or '—'}",
        f"Company: {data.get('company_name') or '—'}",
        f"Status: {data.get('status') or '—'}",
        f"Match: {_score_label(data.get('match_score'))}",
    ]
    if data.get("job_url"):
        lines.append(f"Posting: {data['job_url']}")
    if data.get("workflow_session_id"):
        lines.append(f"Session: {data['workflow_session_id']}")
        lines.append(f"  → applypilot workflow results {data['workflow_session_id']}")
    if data.get("notes"):
        lines.append(f"Notes: {data['notes']}")
    if data.get("created_at"):
        lines.append(f"Created: {data['created_at']}")
    return "\n".join(lines)

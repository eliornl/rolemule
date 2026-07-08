# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def format_email_result(data: Dict[str, Any]) -> str:
    """Format tool output with subject + body fields."""
    subject = data.get("subject_line") or data.get("subject") or ""
    body = data.get("email_body") or data.get("body") or ""
    lines = []
    if subject:
        lines.append(f"**Subject:** {subject}")
    if body:
        lines.append("\n**Body:**\n")
        lines.append(body)
    tone = data.get("tone")
    if tone:
        lines.append(f"\n_Tone: {tone}_")
    return "\n".join(lines) if lines else str(data)


def format_rejection_analysis(data: Dict[str, Any]) -> str:
    lines = ["# Rejection analysis", "", data.get("analysis_summary", "")]
    reasons = data.get("likely_reasons") or []
    if reasons:
        lines.extend(["", "## Likely reasons", *[f"- {r}" for r in reasons]])
    suggestions = data.get("improvement_suggestions") or []
    if suggestions:
        lines.extend(["", "## Suggestions", *[f"- {s}" for s in suggestions]])
    if data.get("follow_up_recommended") and data.get("follow_up_template"):
        lines.extend(["", "## Follow-up template", data["follow_up_template"]])
    return "\n".join(lines)


def format_job_comparison(data: Dict[str, Any]) -> str:
    lines = [
        "# Job comparison",
        "",
        f"**Recommendation:** {data.get('recommended_job', 'N/A')}",
        "",
        data.get("executive_summary") or data.get("recommendation_reasoning") or "",
    ]
    for job in data.get("jobs_analysis") or []:
        if not isinstance(job, dict):
            continue
        lines.append(
            f"\n## {job.get('title', '?')} @ {job.get('company', '?')} — {job.get('overall_score', '?')}/100"
        )
    advice = data.get("final_advice")
    if advice:
        lines.extend(["", "## Final advice", advice])
    return "\n".join(lines)


def format_salary_coach(data: Dict[str, Any]) -> str:
    lines = [
        "# Salary coach",
        "",
        f"**Role:** {data.get('job_title', '')} @ {data.get('company_name', '')}",
        f"**Offer:** {data.get('offered_salary', '')}",
    ]
    strategy = data.get("strategy_overview") or {}
    if isinstance(strategy, dict) and strategy.get("recommended_approach"):
        lines.extend(["", "## Strategy", strategy["recommended_approach"]])
    script = data.get("main_script") or {}
    if isinstance(script, dict):
        if script.get("counter_offer"):
            lines.extend(["", "## Counter-offer script", script["counter_offer"]])
    email = data.get("email_template") or {}
    if isinstance(email, dict) and email.get("body"):
        lines.extend(["", "## Email template", f"Subject: {email.get('subject', '')}", "", email["body"]])
    walk = data.get("walk_away_point")
    if walk:
        lines.extend(["", f"**Walk-away point:** {walk}"])
    return "\n".join(lines)


def format_reference_request(data: Dict[str, Any]) -> str:
    text = format_email_result(data)
    tips = data.get("tips") or []
    if tips:
        text += "\n\n**Tips:**\n" + "\n".join(f"- {t}" for t in tips)
    return text


def format_tool_result(tool: str, data: Dict[str, Any]) -> Optional[str]:
    """Pick a human formatter for a tool response."""
    if tool in ("thank-you", "followup"):
        return format_email_result(data)
    if tool == "rejection-analysis":
        return format_rejection_analysis(data)
    if tool == "reference-request":
        return format_reference_request(data)
    if tool == "job-comparison":
        return format_job_comparison(data)
    if tool == "salary-coach":
        return format_salary_coach(data)
    return None

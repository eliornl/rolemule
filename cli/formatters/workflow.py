# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional


VALID_SECTIONS = frozenset({"all", "fit", "company", "cover-letter", "resume"})


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _match_score(profile_matching: Optional[Dict[str, Any]]) -> Optional[float]:
    if not profile_matching:
        return None
    final_scores = profile_matching.get("final_scores") or {}
    score = (
        final_scores.get("overall_match_score")
        or profile_matching.get("overall_match_score")
        or profile_matching.get("overall_score")
    )
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value <= 1.0:
        return round(value * 100, 1)
    return round(value, 1)


def format_workflow_results(results: Dict[str, Any], section: str = "all") -> str:
    """Render workflow results as human-readable markdown sections."""
    if section not in VALID_SECTIONS:
        section = "all"

    parts: List[str] = []
    status = results.get("status") or "unknown"
    session_id = results.get("session_id") or ""
    parts.append(f"# Workflow {session_id}\nStatus: **{status}**")

    if section in ("all", "fit"):
        pm = results.get("profile_matching") or {}
        score = _match_score(pm)
        fit_lines = ["## Fit Score"]
        if score is not None:
            fit_lines.append(f"**Match score:** {score}%")
        summary = pm.get("match_summary") or pm.get("summary")
        if summary:
            fit_lines.append(str(summary))
        positioning = pm.get("competitive_positioning")
        if positioning:
            fit_lines.append(f"\n{positioning}")
        if len(fit_lines) > 1:
            parts.append("\n".join(fit_lines))

    if section in ("all", "company"):
        cr = results.get("company_research") or {}
        if cr:
            company_lines = ["## Company Research"]
            name = cr.get("company_name") or cr.get("name")
            if name:
                company_lines.append(f"**{name}**")
            overview = cr.get("company_overview") or cr.get("overview")
            if overview:
                company_lines.append(str(overview))
            parts.append("\n".join(company_lines))

    if section in ("all", "cover-letter"):
        cl = results.get("cover_letter") or {}
        content = cl.get("content") or cl.get("cover_letter") or cl.get("body")
        if content:
            parts.append(f"## Cover Letter\n{content}")

    if section in ("all", "resume"):
        rr = results.get("resume_recommendations") or {}
        advice = rr.get("comprehensive_advice") or rr
        tips = advice.get("quick_wins") or advice.get("tips") or []
        resume_lines = ["## Resume Tips"]
        if isinstance(tips, list) and tips:
            resume_lines.extend(f"- {tip}" for tip in tips)
        elif isinstance(advice, dict) and advice:
            resume_lines.append(str(advice))
        if len(resume_lines) > 1:
            parts.append("\n".join(resume_lines))

    errors = results.get("error_messages") or []
    if errors:
        parts.append("## Errors\n" + "\n".join(f"- {msg}" for msg in errors))

    return "\n\n".join(parts)

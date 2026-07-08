# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _ensure_list(value: Any) -> List[Any]:
    """Normalize list fields from LLM output (mirrors UI ensureArray)."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _question_lines(items: List[Any], limit: int = 5) -> List[str]:
    lines: List[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            text = item.get("question") or item.get("text") or str(item)
        else:
            text = str(item)
        lines.append(f"- {text}")
    return lines


def format_interview_prep(data: Dict[str, Any]) -> str:
    """Render interview prep as human-readable markdown sections."""
    prep = data.get("interview_prep") or {}
    if not prep:
        return "No interview prep available."

    parts: List[str] = [f"# Interview Prep — {data.get('session_id', '')}"]

    process = prep.get("interview_process") or {}
    rounds = _ensure_list(process.get("typical_rounds") or prep.get("interview_stages"))
    if rounds:
        lines = ["## Process"]
        for idx, rnd in enumerate(rounds[:6], start=1):
            if isinstance(rnd, dict):
                title = rnd.get("type") or rnd.get("stage") or f"Round {idx}"
                focus = rnd.get("focus") or rnd.get("description") or ""
                lines.append(f"**{idx}. {title}**")
                if focus:
                    lines.append(str(focus))
            else:
                lines.append(f"- {rnd}")
        parts.append("\n".join(lines))

    predicted = prep.get("predicted_questions") or {}
    question_sections = [
        ("Behavioral", _ensure_list(predicted.get("behavioral"))),
        ("Technical", _ensure_list(predicted.get("technical"))),
        ("Role-specific", _ensure_list(predicted.get("role_specific"))),
    ]
    q_lines = ["## Questions"]
    has_questions = False
    for label, items in question_sections:
        if items:
            has_questions = True
            q_lines.append(f"### {label}")
            q_lines.extend(_question_lines(items))
    if not has_questions:
        legacy = _ensure_list(prep.get("likely_questions"))
        if legacy:
            q_lines.extend(_question_lines(legacy))
            has_questions = True
    if has_questions:
        parts.append("\n".join(q_lines))

    checklist = _ensure_list(
        prep.get("day_before_checklist")
        or prep.get("preparation_checklist")
        or prep.get("day_of_tips")
    )
    boosters = _ensure_list(prep.get("confidence_boosters"))
    prep_lines = ["## Preparation"]
    if checklist:
        prep_lines.append("### Day-before checklist")
        prep_lines.extend(f"- {item}" for item in checklist[:10])
    if boosters:
        prep_lines.append("### Confidence boosters")
        prep_lines.extend(f"- {item}" for item in boosters[:8])
    qrc = prep.get("quick_reference_card") or {}
    pitch = qrc.get("elevator_pitch")
    if pitch:
        prep_lines.append("### Elevator pitch")
        prep_lines.append(str(pitch))
    if len(prep_lines) > 1:
        parts.append("\n".join(prep_lines))

    logistics = prep.get("logistics") or {}
    tips = _ensure_list(logistics.get("virtual_interview_tips"))
    bring = _ensure_list(logistics.get("what_to_bring"))
    if tips or bring:
        log_lines = ["## Logistics"]
        if bring:
            log_lines.append("**Bring:** " + ", ".join(str(x) for x in bring))
        if tips:
            log_lines.append("**Virtual tips:**")
            log_lines.extend(f"- {tip}" for tip in tips[:5])
        parts.append("\n".join(log_lines))

    return "\n\n".join(parts)

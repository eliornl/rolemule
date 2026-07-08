# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List


# =============================================================================
# CLASSES/FUNCTIONS
# =============================================================================


def _ensure_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def format_cv_result(data: Dict[str, Any]) -> str:
    """Render CV optimization result for human-readable CLI output."""
    result = data.get("result") or {}
    if not result:
        return "No CV optimization result available."

    lines: List[str] = [f"# CV Optimization — {data.get('session_id', '')}"]

    if result.get("status") == "partial":
        lines.append(
            "**Note:** Partial result — API quota was reached before the loop finished. "
            "Download the best CV produced so far."
        )

    best_score = result.get("best_score")
    if best_score is not None:
        lines.append(f"**Best score:** {best_score}/10")

    stop_reason = result.get("stop_reason")
    if stop_reason:
        lines.append(f"**Stop reason:** {stop_reason.replace('_', ' ')}")

    completed_at = result.get("completed_at")
    if completed_at:
        lines.append(f"**Completed:** {completed_at}")

    history = _ensure_list(result.get("iteration_history"))
    if history:
        lines.append("\n## Iterations")
        for record in history:
            if not isinstance(record, dict):
                lines.append(f"- {record}")
                continue
            iteration = record.get("iteration", "?")
            score = record.get("score")
            phase = record.get("phase") or record.get("action") or ""
            if score is not None:
                lines.append(f"- Iteration {iteration}: score {score}" + (f" ({phase})" if phase else ""))
            else:
                lines.append(f"- Iteration {iteration}" + (f" ({phase})" if phase else ""))

    gaps = _ensure_list(result.get("gap_analysis"))
    if gaps:
        lines.append("\n## Gap analysis")
        lines.extend(f"- {item}" for item in gaps[:8])

    cv_text = result.get("optimized_cv")
    if cv_text:
        preview = str(cv_text).strip()
        if len(preview) > 400:
            preview = preview[:400] + "…"
        lines.append("\n## Optimized CV (preview)")
        lines.append(preview)

    cover = result.get("cover_letter")
    if cover:
        lines.append("\n## Cover letter")
        lines.append("Included in result (use --format json for full text).")

    return "\n".join(lines)

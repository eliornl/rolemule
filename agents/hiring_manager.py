"""
AI Hiring Manager agent for evaluating CV fit against a job description.

Standalone agent used by the CV optimization loop. NOT part of the main
LangGraph workflow. Uses chain-of-thought scoring to produce a structured
evaluation with a numeric score, strengths, gaps, and action items.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.llm_client import get_gemini_client
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

LLM_TEMPERATURE: float = 0.2  # Low for consistent, reproducible scoring
LLM_MAX_TOKENS: int = 16000

SYSTEM_CONTEXT: str = """You are a senior hiring manager with 20+ years of experience across technology, finance, and consulting. You evaluate candidates rigorously and fairly.

## YOUR ROLE
You evaluate a candidate's CV against a specific job description. Your goal is to produce an honest, structured assessment that identifies both strengths and gaps.

## SCORING PRINCIPLES
- Score is 0.0–10.0 (one decimal place)
- 0.0–4.9: Significant gaps — would not advance to interview
- 5.0–6.9: Partial match — might advance with reservations
- 7.0–8.4: Good match — strong interview candidate
- 8.5–10.0: Excellent match — priority candidate
- Score based on substance, not presentation style
- Never inflate scores — a 9.0+ requires near-perfect alignment

## EVALUATION METHODOLOGY
Step 1: Extract the top 5–7 requirements from the job description (must-have skills, experience level, domain knowledge)
Step 2: Score each requirement: fully met (1.0), partially met (0.5), not met (0.0)
Step 3: Weight required qualifications 2x over preferred qualifications
Step 4: Aggregate into a 0–10 score
Step 5: Identify 3–5 specific strengths and 3–5 specific gaps
Step 6: Provide concrete, actionable improvement items (what could be rephrased/reordered, not fabricated)

## CONSTRAINTS
- Only evaluate what is written in the CV — do not assume unlisted experience
- Action items must only suggest rephrasing, reordering, or emphasizing existing content
- Never suggest fabricating experience, degrees, or skills
- Be specific: "Quantify the impact of the migration project in the 2022 role" is better than "Add metrics"
"""

EVALUATION_PROMPT_TEMPLATE: str = """# CV Evaluation — Iteration {iteration}

## JOB DESCRIPTION
{job_description}

## KEY REQUIREMENTS EXTRACTED FROM JOB ANALYSIS
{requirements_summary}

## CANDIDATE CV
{cv_text}

{previous_context}

## YOUR TASK
Evaluate this CV against the job description using the chain-of-thought methodology described in your instructions.

Respond with a JSON object in this exact format:
{{
  "requirement_scores": [
    {{"requirement": "...", "status": "fully_met|partially_met|not_met", "evidence": "...", "weight": "required|preferred"}}
  ],
  "score": <float 0.0-10.0>,
  "strengths": ["<specific strength 1>", "<specific strength 2>", "<specific strength 3>"],
  "gaps": ["<specific gap 1>", "<specific gap 2>", "<specific gap 3>"],
  "action_items": ["<specific actionable item 1>", "<specific actionable item 2>", "<specific actionable item 3>"],
  "reasoning": "<2-3 sentence summary of the overall assessment>"
}}

Return only the JSON object, no other text.
"""


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class HiringManagerEvaluation:
    """Structured evaluation output from the HiringManagerAgent."""

    score: float
    strengths: List[str]
    gaps: List[str]
    action_items: List[str]
    reasoning: str
    requirement_scores: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "score": self.score,
            "strengths": self.strengths,
            "gaps": self.gaps,
            "action_items": self.action_items,
            "reasoning": self.reasoning,
            "requirement_scores": self.requirement_scores,
        }


# =============================================================================
# AGENT
# =============================================================================


class HiringManagerAgent:
    """
    Evaluates a CV against a job description using chain-of-thought scoring.

    Standalone agent — not part of the main LangGraph workflow.
    Always requires a BYOK user API key.
    """

    def __init__(self) -> None:
        self.gemini_client = None

    async def evaluate(
        self,
        cv_text: str,
        job_description: str,
        job_analysis: Dict[str, Any],
        iteration: int,
        previous_score: Optional[float] = None,
        user_api_key: Optional[str] = None,
    ) -> HiringManagerEvaluation:
        """
        Score a CV against the job description and return structured feedback.

        Args:
            cv_text: Current CV content as plain text or markdown
            job_description: Full job description text
            job_analysis: Structured job analysis from the main workflow (used to extract requirements)
            iteration: Current loop iteration number (0-indexed)
            previous_score: Score from the previous iteration, if any
            user_api_key: BYOK Gemini API key

        Returns:
            HiringManagerEvaluation with score, strengths, gaps, and action items

        Raises:
            Exception: On LLM failure after retries
        """
        self.gemini_client = await get_gemini_client()

        requirements_summary = self._format_requirements(job_analysis)
        previous_context = self._format_previous_context(previous_score)

        prompt = EVALUATION_PROMPT_TEMPLATE.format(
            iteration=iteration,
            job_description=job_description[:8000],
            requirements_summary=requirements_summary,
            cv_text=cv_text[:10000],
            previous_context=previous_context,
        )

        structured_logger.log_agent_start("hiring_manager", None)
        start_time = time.monotonic()

        response = await self.gemini_client.generate(
            prompt=prompt,
            system=SYSTEM_CONTEXT,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            user_api_key=user_api_key,
        )

        duration_ms = (time.monotonic() - start_time) * 1000

        if response.get("filtered"):
            logger.warning("HiringManagerAgent: content filtered at iteration %d", iteration)
            return self._fallback_evaluation(iteration)

        parsed = parse_json_from_llm_response(response.get("response", ""))
        if not parsed:
            logger.warning(
                "HiringManagerAgent: JSON parse failed at iteration %d, using fallback",
                iteration,
            )
            return self._fallback_evaluation(iteration)

        evaluation = self._build_evaluation(parsed)
        structured_logger.log_agent_complete("hiring_manager", None, duration_ms)
        return evaluation

    def _format_requirements(self, job_analysis: Dict[str, Any]) -> str:
        """Extract a human-readable requirements summary from job_analysis."""
        required = job_analysis.get("required_qualifications") or []
        preferred = job_analysis.get("preferred_qualifications") or []
        required_skills = job_analysis.get("required_skills") or []

        lines: List[str] = []
        if required_skills:
            lines.append("Required Skills: " + ", ".join(required_skills[:10]))
        for q in required[:5]:
            lines.append(f"REQUIRED: {q}")
        for q in preferred[:5]:
            lines.append(f"PREFERRED: {q}")
        return "\n".join(lines) if lines else "See job description above."

    def _format_previous_context(self, previous_score: Optional[float]) -> str:
        """Add context about the previous score when applicable."""
        if previous_score is None:
            return ""
        return (
            f"## CONTEXT\nPrevious iteration score: {previous_score:.1f}/10. "
            "Revisions have been made. Re-evaluate the updated CV from scratch."
        )

    def _build_evaluation(self, parsed: Dict[str, Any]) -> HiringManagerEvaluation:
        """Validate and build a HiringManagerEvaluation from parsed JSON."""
        try:
            score = float(parsed.get("score", 5.0))
            score = max(0.0, min(10.0, score))
            score = round(score, 1)
        except (TypeError, ValueError):
            score = 5.0

        strengths = self._extract_list(parsed, "strengths", 3, 5)
        gaps = self._extract_list(parsed, "gaps", 3, 5)
        action_items = self._extract_list(parsed, "action_items", 1, 10)
        reasoning = str(parsed.get("reasoning", ""))[:500]
        requirement_scores = parsed.get("requirement_scores") or []
        if not isinstance(requirement_scores, list):
            requirement_scores = []

        return HiringManagerEvaluation(
            score=score,
            strengths=strengths,
            gaps=gaps,
            action_items=action_items,
            reasoning=reasoning,
            requirement_scores=requirement_scores,
        )

    def _extract_list(
        self, parsed: Dict[str, Any], key: str, min_items: int, max_items: int
    ) -> List[str]:
        """Safely extract a string list from parsed JSON."""
        raw = parsed.get(key) or []
        if not isinstance(raw, list):
            return [f"Unable to parse {key}"]
        items = [str(item).strip() for item in raw if item and str(item).strip()]
        if not items:
            return [f"No {key} identified"]
        return items[:max_items]

    def _fallback_evaluation(self, iteration: int) -> HiringManagerEvaluation:
        """Return a safe default evaluation when LLM output cannot be parsed."""
        return HiringManagerEvaluation(
            score=5.0,
            strengths=["Unable to evaluate — content filtering or parse error"],
            gaps=["Unable to evaluate — content filtering or parse error"],
            action_items=["Retry optimization or review CV content"],
            reasoning=f"Evaluation failed at iteration {iteration}; using neutral score.",
        )

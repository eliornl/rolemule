"""
CV Optimization Loop agents and orchestrator.

Contains three components:
- CVOptimizerAgent: Revises a CV based on hiring manager feedback
- CoverLetterFinalizer: Generates a cover letter from the optimized CV
- CVOptimizationOrchestrator: Runs the full evaluate→revise loop until convergence

All agents are standalone and NOT part of the main LangGraph workflow.
All agents require a BYOK user API key.
"""

import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional

from agents.hiring_manager import HiringManagerAgent, HiringManagerEvaluation
from utils.llm_client import get_gemini_client
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

CV_OPTIMIZER_TEMPERATURE: float = 0.4
CV_OPTIMIZER_MAX_TOKENS: int = 16000

COVER_LETTER_TEMPERATURE: float = 0.5
COVER_LETTER_MAX_TOKENS: int = 16000

# Convergence constants (fixed — not user-configurable)
SCORE_DECREASE_TOLERANCE: float = 0.5   # stop if current < best - this value
SCORE_PLATEAU_TOLERANCE: float = 0.3    # considered plateaued if delta <= this
SCORE_PLATEAU_ITERATIONS: int = 2       # consecutive plateau iterations to trigger stop

CV_OPTIMIZER_SYSTEM_CONTEXT: str = """You are an expert CV writer helping a job seeker improve their application for a specific role.

## YOUR ROLE
Revise the candidate's CV to better match the job requirements based on feedback from the hiring manager. You are making the SAME person look more relevant — not creating a different person.

## STRICT RULES — NEVER VIOLATE
1. NEVER fabricate experience, degrees, certifications, skills, or achievements
2. NEVER add companies, roles, or dates the candidate did not hold
3. NEVER change factual information (employment dates, job titles, educational institutions)
4. If you are uncertain whether something is true, flag it with [NEEDS CLARIFICATION: ...]
5. Only revise sections mentioned in the action items

## WHAT YOU CAN DO
- Rephrase bullet points to highlight relevant skills and impact
- Reorder sections or bullet points for better emphasis
- Add or expand on skills that ARE listed (if supporting evidence exists in the CV)
- Remove or de-emphasize irrelevant content
- Strengthen weak or vague language ("worked on" → "led", "helped with" → "implemented")
- Quantify existing achievements if numbers are implied (e.g. "managed a team" → "managed a team of 6")
- Improve the professional summary to match the target role

## OUTPUT FORMAT
Return the complete revised CV as plain markdown text. Do not include any explanation or commentary — only the CV content.
"""

CV_OPTIMIZER_PROMPT_TEMPLATE: str = """# CV Revision — Iteration {iteration}

## JOB DESCRIPTION
{job_description}

## HIRING MANAGER FEEDBACK (Score: {score}/10)

### Gaps to address:
{gaps}

### Specific action items:
{action_items}

## CURRENT CV
{cv_text}

## YOUR TASK
Revise the CV above following your system instructions. Only modify sections relevant to the action items. Return the complete revised CV as markdown text.
"""

COVER_LETTER_SYSTEM_CONTEXT: str = """You are an expert cover letter writer who creates compelling, authentic applications.

## YOUR ROLE
Write a professional cover letter that bridges the candidate's optimized CV with the specific job opportunity.

## WRITING RULES
- Address the letter to "Dear Hiring Team," (never "Dear Hiring Manager," or "To Whom It May Concern")
- Use the candidate's first name only in the opening if referencing themselves (never full name in body)
- Write in a professional but human tone — avoid corporate buzzwords
- Reference specific job requirements and company context where available
- Keep to 3–4 paragraphs, approximately 300–400 words
- End with "Best regards," and leave the name line blank (do not write the candidate's name)
- NEVER use placeholder brackets like [Company Name] or [Your Name] — use actual values
"""

COVER_LETTER_PROMPT_TEMPLATE: str = """# Cover Letter Generation

## JOB DETAILS
Title: {job_title}
Company: {company_name}
{job_description_section}

{company_context_section}

## CANDIDATE'S OPTIMIZED CV
{optimized_cv}

## YOUR TASK
Write a compelling cover letter for this candidate applying to this specific role.
Return only the cover letter text — no JSON, no commentary.
"""


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class OptimizationConfig:
    """User-configurable parameters for the optimization loop."""

    max_iterations: int = 5      # 1–7
    score_threshold: float = 8.5  # 7.0–9.5


@dataclass
class IterationRecord:
    """State snapshot for a single optimization iteration."""

    iteration: int
    score: float
    strengths: List[str]
    gaps: List[str]
    action_items: List[str]
    cv_snapshot: str
    processing_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return asdict(self)


@dataclass
class OptimizationResult:
    """Full result of the CV optimization loop."""

    status: str  # "completed" | "failed"
    started_at: str
    completed_at: str
    stop_reason: str
    config: Dict[str, Any]
    iteration_history: List[IterationRecord] = field(default_factory=list)
    best_iteration: int = 0
    best_score: float = 0.0
    optimized_cv: str = ""
    cover_letter: str = ""
    gap_analysis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stop_reason": self.stop_reason,
            "config": self.config,
            "iteration_history": [r.to_dict() for r in self.iteration_history],
            "best_iteration": self.best_iteration,
            "best_score": self.best_score,
            "optimized_cv": self.optimized_cv,
            "cover_letter": self.cover_letter,
            "gap_analysis": self.gap_analysis,
        }


# =============================================================================
# HELPERS
# =============================================================================


def _compose_cv_from_profile(user_profile: Dict[str, Any]) -> str:
    """
    Compose a plain-text markdown CV from structured profile data.

    Used as the iteration-0 starting point. Mirrors the data available to
    the existing ResumeAdvisorAgent and CoverLetterWriterAgent.

    Args:
        user_profile: Serialized UserProfile dict from WorkflowSession.user_data

    Returns:
        Markdown-formatted CV string
    """
    lines: List[str] = []

    full_name = user_profile.get("full_name", "Candidate")
    professional_title = user_profile.get("professional_title", "")
    email = user_profile.get("email", "")
    city = user_profile.get("city", "")
    state = user_profile.get("state", "")
    country = user_profile.get("country", "")

    location_parts = [p for p in [city, state, country] if p]
    location = ", ".join(location_parts)

    lines.append(f"# {full_name}")
    if professional_title:
        lines.append(f"**{professional_title}**")
    contact_parts = [p for p in [email, location] if p]
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    summary = user_profile.get("summary", "")
    if summary:
        lines.append("## Professional Summary")
        lines.append(summary)
        lines.append("")

    work_experience = user_profile.get("work_experience") or []
    if work_experience:
        lines.append("## Work Experience")
        for role in work_experience:
            title = role.get("title", "")
            company = role.get("company", "")
            start_date = role.get("start_date", "")
            end_date = role.get("end_date", "") or ("Present" if role.get("is_current") else "")
            date_range = f"{start_date}–{end_date}".strip("–")

            lines.append(f"### {title} — {company}")
            if date_range:
                lines.append(f"*{date_range}*")

            accomplishments = role.get("accomplishments") or role.get("description") or []
            if isinstance(accomplishments, list):
                for acc in accomplishments:
                    if acc:
                        lines.append(f"- {acc}")
            elif isinstance(accomplishments, str) and accomplishments:
                lines.append(accomplishments)
            lines.append("")

    education = user_profile.get("education") or []
    if education:
        lines.append("## Education")
        for edu in education:
            institution = edu.get("institution", "")
            degree = edu.get("degree", "")
            field_of_study = edu.get("field_of_study", "")
            start_date = edu.get("start_date", "")
            end_date = edu.get("end_date", "") or ("Present" if edu.get("is_current") else "")
            date_range = f"{start_date}–{end_date}".strip("–")

            degree_line = " in ".join(p for p in [degree, field_of_study] if p)
            lines.append(f"### {degree_line} — {institution}")
            if date_range:
                lines.append(f"*{date_range}*")
            lines.append("")

    skills = user_profile.get("skills") or []
    if skills:
        lines.append("## Skills")
        lines.append(", ".join(skills))
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# CV OPTIMIZER AGENT
# =============================================================================


class CVOptimizerAgent:
    """
    Revises a CV based on hiring manager feedback.

    Constraints: cannot fabricate; can only rephrase/reorder/emphasize
    existing content. Standalone agent — not part of the LangGraph workflow.
    """

    def __init__(self) -> None:
        self.gemini_client = None

    async def revise(
        self,
        cv_text: str,
        job_description: str,
        evaluation: HiringManagerEvaluation,
        iteration: int,
        user_api_key: Optional[str] = None,
    ) -> str:
        """
        Revise the CV based on hiring manager feedback.

        Args:
            cv_text: Current CV as markdown text
            job_description: Full job description text
            evaluation: HiringManagerEvaluation from the current iteration
            iteration: Current iteration number (1-indexed when used in loop)
            user_api_key: BYOK Gemini API key

        Returns:
            Revised CV as markdown text. Falls back to the original on error.
        """
        self.gemini_client = await get_gemini_client()

        gaps_text = "\n".join(f"- {g}" for g in evaluation.gaps)
        action_items_text = "\n".join(f"- {a}" for a in evaluation.action_items)

        prompt = CV_OPTIMIZER_PROMPT_TEMPLATE.format(
            iteration=iteration,
            job_description=job_description[:6000],
            score=evaluation.score,
            gaps=gaps_text,
            action_items=action_items_text,
            cv_text=cv_text[:10000],
        )

        structured_logger.log_agent_start("cv_optimizer", None)
        _t0 = perf_counter()

        response = await self.gemini_client.generate(
            prompt=prompt,
            system=CV_OPTIMIZER_SYSTEM_CONTEXT,
            temperature=CV_OPTIMIZER_TEMPERATURE,
            max_tokens=CV_OPTIMIZER_MAX_TOKENS,
            user_api_key=user_api_key,
        )

        _dur_ms = (perf_counter() - _t0) * 1000

        if response.get("filtered"):
            logger.warning(
                "CVOptimizerAgent: content filtered at iteration %d, keeping original",
                iteration,
            )
            return cv_text

        revised = response.get("response", "").strip()
        if not revised:
            logger.warning(
                "CVOptimizerAgent: empty response at iteration %d, keeping original",
                iteration,
            )
            return cv_text

        structured_logger.log_agent_complete("cv_optimizer", None, _dur_ms)
        return revised


# =============================================================================
# COVER LETTER FINALIZER
# =============================================================================


class CoverLetterFinalizer:
    """
    Generates a cover letter from the final optimized CV.

    Called exactly once after the optimization loop converges.
    """

    def __init__(self) -> None:
        self.gemini_client = None

    async def generate_cover_letter(
        self,
        optimized_cv: str,
        job_description: str,
        job_analysis: Dict[str, Any],
        company_research: Optional[Dict[str, Any]],
        user_api_key: str,
    ) -> str:
        """
        Generate a cover letter for the optimized CV.

        Args:
            optimized_cv: Best-scoring CV text from the optimization loop
            job_description: Full job description text
            job_analysis: Structured job analysis (title, company, requirements)
            company_research: Optional company research data for personalization
            user_api_key: BYOK Gemini API key

        Returns:
            Cover letter as plain text. Returns empty string on failure.
        """
        self.gemini_client = await get_gemini_client()

        job_title = job_analysis.get("job_title") or "the advertised position"
        company_name = job_analysis.get("company_name") or "your organization"

        job_description_section = (
            f"Job Description (excerpt):\n{job_description[:4000]}"
        )

        company_context_section = ""
        if company_research:
            overview = company_research.get("company_overview", "")
            culture = company_research.get("culture_and_values", "")
            if overview:
                company_context_section = f"## COMPANY CONTEXT\n{overview[:1000]}"
            if culture:
                company_context_section += f"\n\nCulture: {culture[:500]}"

        prompt = COVER_LETTER_PROMPT_TEMPLATE.format(
            job_title=job_title,
            company_name=company_name,
            job_description_section=job_description_section,
            company_context_section=company_context_section,
            optimized_cv=optimized_cv[:8000],
        )

        structured_logger.log_agent_start("cover_letter_finalizer", None)
        _t0 = perf_counter()

        response = await self.gemini_client.generate(
            prompt=prompt,
            system=COVER_LETTER_SYSTEM_CONTEXT,
            temperature=COVER_LETTER_TEMPERATURE,
            max_tokens=COVER_LETTER_MAX_TOKENS,
            user_api_key=user_api_key,
        )

        _dur_ms = (perf_counter() - _t0) * 1000

        if response.get("filtered"):
            logger.warning("CoverLetterFinalizer: content filtered, returning empty string")
            return ""

        cover_letter = response.get("response", "").strip()
        structured_logger.log_agent_complete("cover_letter_finalizer", None, _dur_ms)
        return cover_letter


# =============================================================================
# ORCHESTRATOR
# =============================================================================


class CVOptimizationOrchestrator:
    """
    Runs the full CV optimization loop until a convergence condition is met.

    Loop flow:
      1. Evaluate current CV (HiringManagerAgent)
      2. Check convergence — if met, break
      3. Revise CV (CVOptimizerAgent)
      4. Repeat from step 1

    After the loop: generate cover letter (CoverLetterFinalizer).
    """

    def __init__(self) -> None:
        self._hiring_manager = HiringManagerAgent()
        self._cv_optimizer = CVOptimizerAgent()
        self._cover_letter_finalizer = CoverLetterFinalizer()

    async def run(
        self,
        session_id: str,
        user_id: str,
        initial_cv: str,
        job_description: str,
        job_analysis: Dict[str, Any],
        company_research: Optional[Dict[str, Any]],
        config: OptimizationConfig,
        user_api_key: str,
        broadcast_iteration_fn: Callable,
    ) -> OptimizationResult:
        """
        Execute the optimization loop.

        Args:
            session_id: Workflow session ID (for logging)
            user_id: User ID (for logging)
            initial_cv: Starting CV text composed from the user profile
            job_description: Full job description text
            job_analysis: Structured job analysis dict
            company_research: Optional company research dict
            config: OptimizationConfig (max_iterations, score_threshold)
            user_api_key: BYOK Gemini API key (required)
            broadcast_iteration_fn: Async callable(iteration_record) broadcast per iteration

        Returns:
            OptimizationResult with all artifacts
        """
        started_at = datetime.now(timezone.utc).isoformat()
        iteration_history: List[IterationRecord] = []
        current_cv = initial_cv
        best_cv = initial_cv
        best_score: float = 0.0
        best_iteration: int = 0
        stop_reason = "max_iterations"
        plateau_count: int = 0
        previous_score: Optional[float] = None

        logger.info(
            "CVOptimizationOrchestrator: starting loop session=%s max_iter=%d threshold=%.1f",
            session_id,
            config.max_iterations,
            config.score_threshold,
        )

        for iteration in range(config.max_iterations):
            iter_start = perf_counter()

            # --- Evaluate ---
            evaluation = await self._hiring_manager.evaluate(
                cv_text=current_cv,
                job_description=job_description,
                job_analysis=job_analysis,
                iteration=iteration,
                previous_score=previous_score,
                user_api_key=user_api_key,
            )

            processing_time_ms = (perf_counter() - iter_start) * 1000

            record = IterationRecord(
                iteration=iteration,
                score=evaluation.score,
                strengths=evaluation.strengths,
                gaps=evaluation.gaps,
                action_items=evaluation.action_items,
                cv_snapshot=current_cv,
                processing_time_ms=round(processing_time_ms, 1),
            )
            iteration_history.append(record)

            # Track best
            if evaluation.score > best_score:
                best_score = evaluation.score
                best_cv = current_cv
                best_iteration = iteration

            # Broadcast iteration result
            try:
                await broadcast_iteration_fn(record)
            except Exception as broadcast_err:
                logger.warning(
                    "CVOptimizationOrchestrator: broadcast failed at iteration %d: %s",
                    iteration,
                    broadcast_err,
                )

            # --- Convergence checks ---
            if evaluation.score >= config.score_threshold:
                stop_reason = "score_threshold"
                logger.info(
                    "CVOptimizationOrchestrator: score %.1f >= threshold %.1f, stopping",
                    evaluation.score,
                    config.score_threshold,
                )
                break

            if previous_score is not None and evaluation.score < best_score - SCORE_DECREASE_TOLERANCE:
                stop_reason = "score_decrease"
                logger.info(
                    "CVOptimizationOrchestrator: score decreased from best %.1f to %.1f, stopping",
                    best_score,
                    evaluation.score,
                )
                break

            if previous_score is not None:
                delta = abs(evaluation.score - previous_score)
                if delta <= SCORE_PLATEAU_TOLERANCE:
                    plateau_count += 1
                    if plateau_count >= SCORE_PLATEAU_ITERATIONS:
                        stop_reason = "score_plateau"
                        logger.info(
                            "CVOptimizationOrchestrator: plateau detected (%d iters), stopping",
                            plateau_count,
                        )
                        break
                else:
                    plateau_count = 0

            previous_score = evaluation.score

            # Last iteration — no point revising
            if iteration == config.max_iterations - 1:
                break

            # --- Revise ---
            current_cv = await self._cv_optimizer.revise(
                cv_text=current_cv,
                job_description=job_description,
                evaluation=evaluation,
                iteration=iteration + 1,
                user_api_key=user_api_key,
            )

        # --- Generate cover letter from best CV ---
        cover_letter = await self._cover_letter_finalizer.generate_cover_letter(
            optimized_cv=best_cv,
            job_description=job_description,
            job_analysis=job_analysis,
            company_research=company_research,
            user_api_key=user_api_key,
        )

        # --- Compute gap analysis: gaps from final evaluation ---
        gap_analysis = self._compute_gap_analysis(iteration_history)

        completed_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "CVOptimizationOrchestrator: done session=%s best_score=%.1f stop=%s iterations=%d",
            session_id,
            best_score,
            stop_reason,
            len(iteration_history),
        )

        return OptimizationResult(
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            stop_reason=stop_reason,
            config={"max_iterations": config.max_iterations, "score_threshold": config.score_threshold},
            iteration_history=iteration_history,
            best_iteration=best_iteration,
            best_score=best_score,
            optimized_cv=best_cv,
            cover_letter=cover_letter,
            gap_analysis=gap_analysis,
        )

    def _compute_gap_analysis(self, history: List[IterationRecord]) -> List[str]:
        """
        Return the final iteration's gaps as the persistent gap analysis.

        These are gaps that remained after all revision attempts — i.e., issues
        that cannot be resolved through rephrasing alone (missing experience,
        missing credentials, etc.).
        """
        if not history:
            return []
        return history[-1].gaps

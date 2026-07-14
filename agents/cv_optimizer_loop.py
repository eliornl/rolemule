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
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.hiring_manager import HiringManagerAgent, HiringManagerEvaluation
from utils.llm_client import get_llm_client, get_gemini_client, is_llm_quota_or_rate_limit_exception  # test-patch alias
from utils.logging_config import get_structured_logger
from utils.logging_config import sanitize_log_value

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

## SOURCE OF TRUTH
The read-only CANDIDATE PROFILE section in the prompt is the only authoritative record of facts. Every company, role, date, metric, skill, and achievement in your output must be traceable to that profile or to the current CV derived from it.

## STRICT RULES — NEVER VIOLATE
1. NEVER fabricate experience, degrees, certifications, skills, metrics, or achievements
2. NEVER add companies, roles, or dates the candidate did not hold
3. NEVER change employment dates, job titles, or educational institutions
4. NEVER invent numbers (team sizes, transaction volumes, customer counts, percentages) unless that exact figure appears in the profile
5. NEVER use meta-commentary, editor notes, or bracketed annotations (no [NEEDS CLARIFICATION], no "adjusted date", no internal reasoning)
6. If a gap cannot be fixed without inventing facts, leave the gap — do not stretch the truth
7. Only revise sections mentioned in the action items when possible

## WHAT YOU CAN DO
- Rephrase bullet points to highlight relevant skills and impact using existing facts only
- Reorder sections or bullet points for better emphasis
- Add skills to the skills list only when clearly supported by work history in the profile
- Remove or de-emphasize irrelevant content
- Strengthen weak language using verbs that match the candidate's actual scope (do not upgrade "assisted" to "led" unless the profile supports leadership)
- Improve the professional summary using only facts from the profile

## OUTPUT FORMAT
Return the complete revised CV as plain markdown text. No explanation, no commentary, no bracketed notes — only CV content the candidate could submit.
"""

CV_OPTIMIZER_PROMPT_TEMPLATE: str = """# CV Revision — Iteration {iteration}

## SOURCE OF TRUTH — CANDIDATE PROFILE (read-only; do not add facts beyond this)
{profile_source_cv}

## JOB DESCRIPTION
{job_description}

## HIRING MANAGER FEEDBACK (Score: {score}/10)

### Gaps to address:
{gaps}

### Specific action items:
{action_items}

## CURRENT CV (tailored draft — do not add facts beyond the profile)
{cv_text}

## YOUR TASK
Revise the current CV following your system instructions. Only rephrase, reorder, or emphasize content supported by the profile. Return the complete revised CV as markdown text.
"""

COVER_LETTER_SYSTEM_CONTEXT: str = """You are an expert cover letter writer who creates compelling, authentic applications.

## YOUR ROLE
Write a professional cover letter grounded in the candidate's verified profile — not in speculative or exaggerated tailoring.

## STRICT FACT RULES — NEVER VIOLATE
1. Only mention accomplishments, metrics, skills, and tenure supported by the candidate profile source of truth
2. Do not invent numbers, product details, or responsibilities to match the job posting
3. Do not treat the tailored CV as authoritative if it claims something absent from the profile
4. It is fine to acknowledge fit honestly without overstating experience

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

## SOURCE OF TRUTH — CANDIDATE PROFILE (read-only)
{profile_source_cv}

## TAILORED CV (for phrasing ideas only — verify every claim against the profile above)
{optimized_cv}

## YOUR TASK
Write a compelling, factually accurate cover letter for this candidate applying to this specific role.
Return only the cover letter text — no JSON, no commentary.
"""


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class OptimizationConfig:
    """User-configurable parameters for the optimization loop."""

    max_iterations: int = 5      # 2–7 (1 evaluates only, never revises)
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

    started_at: str
    completed_at: str
    stop_reason: str
    config: Dict[str, Any]
    status: str = "completed"
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


_NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS\s+CLARIFICATION[^\]]*\]", re.IGNORECASE)
# Bracketed editor notes the model sometimes emits instead of NEEDS CLARIFICATION
_EDITOR_NOTE_RE = re.compile(r"\[(?:adjusted|confirm|clarification)[^\]]*\]", re.IGNORECASE)


def _strip_editor_annotations(text: str) -> str:
    """Remove bracketed editor/meta annotations from user-facing CV or cover letter text."""
    if not text:
        return text
    cleaned = _NEEDS_CLARIFICATION_RE.sub("", text)
    cleaned = _EDITOR_NOTE_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +\n", "\n", cleaned)
    return cleaned.strip()


def sanitize_application_text(text: str) -> str:
    """Public sanitizer for optimized CV / cover letter output."""
    return _strip_editor_annotations(text)


def _profile_date_markers(user_profile: Dict[str, Any]) -> List[str]:
    """Date substrings from profile work/education that must survive CV revisions."""
    markers: List[str] = []
    for role in user_profile.get("work_experience") or []:
        start = (role.get("start_date") or "").strip()
        end = (role.get("end_date") or "").strip()
        if role.get("is_current") and not end:
            end = "Present"
        if start:
            markers.append(start)
        if end:
            markers.append(end)
        if start or end:
            markers.append(f"{start}–{end}".strip("–"))
    for edu in user_profile.get("education") or []:
        start = (edu.get("start_date") or "").strip()
        end = (edu.get("end_date") or "").strip()
        if edu.get("is_current") and not end:
            end = "Present"
        if start:
            markers.append(start)
        if end:
            markers.append(end)
        if start or end:
            markers.append(f"{start}–{end}".strip("–"))
    return [m for m in markers if m]


def _employment_dates_preserved(
    profile_source_cv: str,
    revised_cv: str,
    user_profile: Dict[str, Any],
) -> bool:
    """Return False if a profile date marker present in the baseline CV is missing from revision."""
    markers = _profile_date_markers(user_profile)
    if not markers:
        return True
    baseline_lower = profile_source_cv.lower()
    revised_lower = revised_cv.lower()
    for marker in markers:
        key = marker.lower()
        if key in baseline_lower and key not in revised_lower:
            return False
    return True


def _accept_cv_revision(
    previous_cv: str,
    revised_cv: str,
    profile_source_cv: str,
    user_profile: Dict[str, Any],
) -> Tuple[str, bool]:
    """
    Sanitize and validate a CV revision.

    Returns:
        Tuple of (cv_to_use, was_accepted). Rejects revisions that drop profile dates.
    """
    sanitized = _strip_editor_annotations(revised_cv)
    if not sanitized:
        return previous_cv, False
    if user_profile and profile_source_cv:
        if not _employment_dates_preserved(profile_source_cv, sanitized, user_profile):
            return previous_cv, False
    return sanitized, True


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
        profile_source_cv: str = "",
        user_profile: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> str:
        """
        Revise the CV based on hiring manager feedback.

        Args:
            cv_text: Current CV as markdown text
            job_description: Full job description text
            evaluation: HiringManagerEvaluation from the current iteration
            iteration: Current iteration number (1-indexed when used in loop)
            user_api_key: BYOK Gemini API key
            profile_source_cv: Read-only baseline CV composed from user profile
            user_profile: Structured profile dict for date validation
            model: Optional BYOK preferred Gemini model from Settings
            llm_provider: Active provider name for generate() routing

        Returns:
            Revised CV as markdown text. Falls back to the original on error or invalid revision.
        """
        self._current_llm_provider = llm_provider
        self.gemini_client = await get_llm_client()
        user_profile = user_profile or {}

        gaps_text = "\n".join(f"- {g}" for g in evaluation.gaps)
        action_items_text = "\n".join(f"- {a}" for a in evaluation.action_items)
        source_cv = profile_source_cv or cv_text

        prompt = CV_OPTIMIZER_PROMPT_TEMPLATE.format(
            iteration=iteration,
            profile_source_cv=source_cv[:10000],
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
            model=model,
            provider=getattr(self, "_current_llm_provider", None),
        )

        _dur_ms = (perf_counter() - _t0) * 1000

        if response.get("filtered"):
            logger.warning('CVOptimizerAgent: content filtered at iteration %d, keeping original', iteration)
            return cv_text

        revised = response.get("response", "").strip()
        if not revised:
            logger.warning('CVOptimizerAgent: empty response at iteration %d, keeping original', iteration)
            return cv_text

        accepted_cv, accepted = _accept_cv_revision(
            cv_text, revised, source_cv, user_profile
        )
        if not accepted:
            logger.warning('CVOptimizerAgent: invalid revision at iteration %d, keeping previous CV', iteration)

        structured_logger.log_agent_complete("cv_optimizer", None, _dur_ms)
        return accepted_cv


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
        profile_source_cv: str = "",
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> str:
        """
        Generate a cover letter for the optimized CV.

        Args:
            optimized_cv: Best-scoring CV text from the optimization loop
            job_description: Full job description text
            job_analysis: Structured job analysis (title, company, requirements)
            company_research: Optional company research data for personalization
            user_api_key: BYOK Gemini API key
            profile_source_cv: Read-only baseline CV composed from user profile
            model: Optional BYOK preferred Gemini model from Settings
            llm_provider: Active provider name for generate() routing

        Returns:
            Cover letter as plain text. Returns empty string on failure.
        """
        self._current_llm_provider = llm_provider
        self.gemini_client = await get_llm_client()

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

        source_cv = profile_source_cv or optimized_cv

        prompt = COVER_LETTER_PROMPT_TEMPLATE.format(
            job_title=job_title,
            company_name=company_name,
            job_description_section=job_description_section,
            company_context_section=company_context_section,
            profile_source_cv=source_cv[:8000],
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
            model=model,
            provider=getattr(self, "_current_llm_provider", None),
        )

        _dur_ms = (perf_counter() - _t0) * 1000

        if response.get("filtered"):
            logger.warning("CoverLetterFinalizer: content filtered, returning empty string")
            return ""

        cover_letter = response.get("response", "").strip()
        cover_letter = _strip_editor_annotations(cover_letter)
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
        user_profile: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
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
            user_profile: Structured profile dict — source of truth for fact validation
            model: Optional BYOK preferred Gemini model from Settings

        Returns:
            OptimizationResult with all artifacts
        """
        started_at = datetime.now(timezone.utc).isoformat()
        iteration_history: List[IterationRecord] = []
        profile_source_cv = initial_cv
        user_profile = user_profile or {}
        current_cv = initial_cv
        best_cv = initial_cv
        best_score: float = 0.0
        best_iteration: int = 0
        stop_reason = "max_iterations"
        plateau_count: int = 0
        previous_score: Optional[float] = None

        logger.info('CVOptimizationOrchestrator: starting loop session=%s max_iter=%d threshold=%.1f', sanitize_log_value(session_id), config.max_iterations, config.score_threshold)

        for iteration in range(config.max_iterations):
            iter_start = perf_counter()

            # --- Evaluate ---
            try:
                evaluation = await self._hiring_manager.evaluate(
                    cv_text=current_cv,
                    job_description=job_description,
                    job_analysis=job_analysis,
                    iteration=iteration,
                    previous_score=previous_score,
                    user_api_key=user_api_key,
                    model=model,
                    llm_provider=llm_provider,
                )
            except Exception as exc:
                if iteration_history and is_llm_quota_or_rate_limit_exception(exc):
                    stop_reason = "api_rate_limit"
                    logger.warning('CVOptimizationOrchestrator: API rate limit at evaluate iteration %d session=%s — returning partial result (%d iterations)', iteration, sanitize_log_value(session_id), len(iteration_history))
                    break
                raise

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
                logger.warning('CVOptimizationOrchestrator: broadcast failed at iteration %d: %s', iteration, sanitize_log_value(broadcast_err))

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
                delta = evaluation.score - previous_score
                if delta < SCORE_PLATEAU_TOLERANCE:
                    plateau_count += 1
                    if plateau_count >= SCORE_PLATEAU_ITERATIONS:
                        stop_reason = "score_plateau"
                        logger.info('CVOptimizationOrchestrator: plateau detected (%d iters), stopping', plateau_count)
                        break
                else:
                    plateau_count = 0

            previous_score = evaluation.score

            # Last iteration — no point revising
            if iteration == config.max_iterations - 1:
                break

            # --- Revise ---
            try:
                current_cv = await self._cv_optimizer.revise(
                    cv_text=current_cv,
                    job_description=job_description,
                    evaluation=evaluation,
                    iteration=iteration + 1,
                    user_api_key=user_api_key,
                    profile_source_cv=profile_source_cv,
                    user_profile=user_profile,
                    model=model,
                    llm_provider=llm_provider,
                )
            except Exception as exc:
                if is_llm_quota_or_rate_limit_exception(exc):
                    stop_reason = "api_rate_limit"
                    logger.warning('CVOptimizationOrchestrator: API rate limit at revise iteration %d session=%s — returning partial result (%d iterations)', iteration + 1, sanitize_log_value(session_id), len(iteration_history))
                    break
                raise

        # --- Generate cover letter from best CV (skip when quota already hit) ---
        best_cv = _strip_editor_annotations(best_cv)
        cover_letter = ""
        if stop_reason != "api_rate_limit":
            try:
                cover_letter = await self._cover_letter_finalizer.generate_cover_letter(
                    optimized_cv=best_cv,
                    job_description=job_description,
                    job_analysis=job_analysis,
                    company_research=company_research,
                    user_api_key=user_api_key,
                    profile_source_cv=profile_source_cv,
                    model=model,
                    llm_provider=llm_provider,
                )
            except Exception as exc:
                if iteration_history and is_llm_quota_or_rate_limit_exception(exc):
                    stop_reason = "api_rate_limit"
                    logger.warning('CVOptimizationOrchestrator: API rate limit during cover letter session=%s — returning partial result', sanitize_log_value(session_id))
                    cover_letter = ""
                else:
                    raise
        else:
            cover_letter = ""

        # --- Compute gap analysis: gaps from the best iteration's evaluation ---
        gap_analysis = self._compute_gap_analysis(iteration_history, best_iteration)

        completed_at = datetime.now(timezone.utc).isoformat()

        logger.info('CVOptimizationOrchestrator: done session=%s best_score=%.1f stop=%s iterations=%d', sanitize_log_value(session_id), best_score, sanitize_log_value(stop_reason), len(iteration_history))

        return OptimizationResult(
            status="partial" if stop_reason == "api_rate_limit" else "completed",
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

    def _compute_gap_analysis(
        self, history: List[IterationRecord], best_iteration_idx: int
    ) -> List[str]:
        """
        Return gaps from the best-scoring iteration as the persistent gap analysis.

        Using the best iteration keeps gap_analysis consistent with the displayed
        optimized_cv (which is also sourced from the best iteration).
        """
        if not history:
            return []
        return history[best_iteration_idx].gaps

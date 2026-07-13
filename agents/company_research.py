"""
Company Research Agent for ApplyPilot.
Uses Gemini LLM with job-posting context, optional disambiguation, and optional
Google Search grounding for employer-specific research.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from config.settings import get_settings
from workflows.state_schema import WorkflowState, CompanyResearchResult
from utils.llm_parsing import parse_json_from_llm_response
from utils.llm_preferences import preferred_model_from_state
from utils.logging_config import sanitize_log_value
from utils.employer_disambiguation import (
    build_company_research_cache_disambiguators,
    build_primary_location,
    format_url_signals_block,
    is_generic_company_name,
    should_skip_disambiguation_step,
)
from utils.cache import (
    get_cached_company_research,
    cache_company_research,
    acquire_compute_lock,
    release_compute_lock,
    _get_company_research_cache_key,
)

logger: logging.Logger = logging.getLogger(__name__)

# LLM settings
LLM_TEMPERATURE: float = 0.3
LLM_MAX_TOKENS: int = 16000

_CONFIDENCE_RANK: Dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_CONTEXT: str = """You are an elite company research analyst specializing in helping job seekers prepare for applications and interviews.

## YOUR EXPERTISE:

**Company Intelligence:**
- You have deep knowledge of major companies across all industries
- You understand corporate structures, cultures, and hiring practices
- You know what information matters most for job applicants
- You can identify company values and culture from public information

**Interview Preparation:**
- You know typical interview processes for different company types
- You understand what hiring managers look for at different companies
- You can predict common interview questions based on company culture
- You know insider tips that help candidates stand out

**Strategic Analysis:**
- You understand competitive landscapes and market positioning
- You can identify company strengths and challenges
- You know how to frame company knowledge in interviews
- You understand what cultural fit means at different organizations

## YOUR PRINCIPLES:
- Provide ACCURATE information based on your knowledge and any search results provided
- Be SPECIFIC with details - avoid vague generalizations
- Focus on what's USEFUL for job applicants
- If you're uncertain about something, say so clearly
- Provide ACTIONABLE insights, not just facts
- Think about what would help someone ACE their interview
- When job context contradicts a famous namesake company, trust the JOB CONTEXT"""

COMPANY_RESEARCH_DISAMBIGUATION_RULES: str = """### DISAMBIGUATION RULES (mandatory)
- Research the employer FOR THIS JOB POSTING only.
- Cross-check: industry, location, and products in your answer MUST align with JOB CONTEXT below.
- If JOB CONTEXT contradicts your knowledge of the named company, set confidence_assessment.overall_confidence to LOW
  and explain the mismatch in uncertain_areas.
- Do NOT substitute a famous namesake company.
- Do NOT invent company names, websites, or leadership not supported by JOB CONTEXT or verified knowledge."""

EMPLOYER_DISAMBIGUATION_PROMPT: str = """Identify the correct employer for THIS job posting before detailed research.

EMPLOYER NAME (from job analysis): {company_name}

### JOB CONTEXT
{job_context}

### POSTING URL SIGNALS
{url_signals}

Respond with ONLY valid JSON:
{{
    "resolved_company_name": "<best employer name for THIS posting or null>",
    "confidence": "HIGH | MEDIUM | LOW",
    "employer_type": "direct | staffing_agency | confidential | unknown",
    "disambiguation_signals": ["<signal used>", "<signal 2>"],
    "rejected_matches": ["<wrong famous company rejected because...>"],
    "notes": "<one sentence>"
}}"""

COMPANY_RESEARCH_PROMPT: str = """Research this company comprehensively for a job applicant.

COMPANY NAME: {company_name}

Provide detailed, accurate information about this company. If you're not certain about specific details, indicate that clearly. Focus on information that would help a job applicant prepare for their application and interview.

Respond with ONLY valid JSON in this exact structure:

{{
    "company_overview": {{
        "company_size": "<employee count range, e.g., '10,000-50,000 employees' or 'Unknown'>",
        "industry": "<primary industry and sub-sector>",
        "headquarters": "<city, state/country>",
        "founded_year": <year as number or null if unknown>,
        "website": "<official website URL or 'Unknown'>",
        "mission_vision": "<company's stated mission or vision, be specific>",
        "key_products_services": ["<main product/service 1>", "<product 2>", "<product 3> — do NOT repeat items here that appear in growth_opportunities"],
        "business_model": "<brief description of how they make money>",
        "notable_facts": ["<interesting fact 1>", "<fact 2>"]
    }},

    "culture_and_values": {{
        "core_values": [
            "<ValueName>: <1-sentence description of how this company actually lives this value in practice>",
            "<ValueName>: <description>",
            "<ValueName>: <description>"
        ],
        "work_environment": "<description of what it's like to work there>",
        "employee_benefits": ["<notable benefit 1>", "<benefit 2>", "<benefit 3>"],
        "diversity_inclusion": "<their approach to D&I>",
        "remote_work_policy": "<current remote/hybrid/office policy>",
        "employee_satisfaction": "<If an employee review site rating is known, start with it (e.g. '4.2/5'). Otherwise write: 'Insufficient public data — in your interview, ask about work-life balance, team autonomy, and growth opportunities.' Be direct and actionable, never just hedge.>",
        "culture_keywords": ["<keyword that describes culture>", "<keyword 2>"]
    }},

    "interview_intelligence": {{
        "typical_process": ["<step 1, e.g., 'Phone screen with recruiter'>", "<step 2>", "<step 3>"],
        "timeline": "<typical hiring timeline>",
        "interview_format": "<virtual/in-person/hybrid, panel vs 1:1>",
        "assessment_methods": ["<e.g., 'Technical coding interview'>", "<'Behavioral questions'>"],
        "common_questions": [
            "<likely interview question 1>",
            "<likely interview question 2>",
            "<likely interview question 3>"
        ],
        "tips_for_success": [
            "<specific tip for this company>",
            "<another tip>",
            "<third tip>"
        ],
        "what_they_look_for": ["<trait 1>", "<trait 2>", "<trait 3>"]
    }},

    "leadership_info": [
        {{
            "name": "<CEO or key leader name>",
            "title": "<their title>",
            "background": "<brief background>",
            "tenure": "<how long in role>"
        }}
    ],

    "competitive_landscape": {{
        "competitors": ["<competitor 1>", "<competitor 2>", "<competitor 3>"],
        "market_position": "<their position in the market - leader, challenger, etc.>",
        "competitive_advantages": ["<advantage 1>", "<advantage 2>"],
        "market_challenges": ["<challenge they face>", "<another challenge>"],
        "growth_opportunities": ["<growth area 1 — must be distinct from key_products_services items>", "<growth area 2>"],
        "recent_developments": "<Key recent news — funding rounds, product launches, leadership changes, partnerships, controversies. If uncertain about recency say so. This helps candidates impress interviewers with current knowledge.>"
    }},

    "application_insights": {{
        "what_to_emphasize": [
            "<specific skill, trait, or experience candidates MUST highlight — tie it to this company's priorities>",
            "<second thing to emphasize>",
            "<third>",
            "<fourth>",
            "<fifth — aim for 4-6 specific, actionable items>"
        ],
        "culture_fit_signals": [
            "<concrete behavior or statement that demonstrates you fit their culture>",
            "<another signal>"
        ],
        "red_flags_to_watch": [
            "<behavior, mindset, or signal that would DISQUALIFY a candidate at this company — something you must avoid showing in your application or interviews>"
        ],
        "talking_points_for_interview": [
            "<something impressive to mention about the company>",
            "<another talking point>"
        ],
        "questions_to_ask_them": [
            "<smart question to ask the interviewer>",
            "<another good question>"
        ]
    }},

    "confidence_assessment": {{
        "overall_confidence": "<HIGH | MEDIUM | LOW - how confident you are in this information>",
        "uncertain_areas": ["<area where info might be outdated or uncertain>"],
        "recommendation": "<brief recommendation for the job applicant>"
    }}
}}

Be thorough, specific, and focus on information that will help someone succeed in their job application. If the company is not well-known, provide what you can and clearly indicate uncertainty."""

_GROUNDING_SEARCH_HINT: str = """
Use Google Search to verify company facts when needed. Search queries MUST include employer name + industry + job title + posting domain when available — never search a generic name alone.
"""


def _has_usable_company_name(name: Optional[str]) -> bool:
    """False for empty, whitespace, or common LLM placeholders when no real employer is named."""
    if not name or not str(name).strip():
        return False
    s = str(name).strip()
    if re.fullmatch(r"[\s\-–—−]+", s):
        return False
    lowered = s.lower()
    if lowered in (
        "null",
        "none",
        "n/a",
        "na",
        "unknown",
        "not specified",
        "not stated",
        "tbd",
        "confidential",
        "undisclosed",
    ):
        return False
    return True


def _format_job_context_for_research(
    job_analysis: Dict[str, Any],
    job_input_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build job posting context for company research prompts.

    Args:
        job_analysis: Job analyzer output
        job_input_data: Optional workflow job input (for URL signals line)

    Returns:
        Multi-line context block
    """
    title = (job_analysis.get("job_title") or "").strip() or "Unknown title"
    location = build_primary_location(job_analysis)
    industry = (job_analysis.get("industry") or "").strip() or "Not specified"
    role_class = (job_analysis.get("role_classification") or "").strip()
    company_size = (job_analysis.get("company_size") or "").strip()
    team_info = (job_analysis.get("team_info") or "").strip()
    reporting_to = (job_analysis.get("reporting_to") or "").strip()
    responsibilities = job_analysis.get("responsibilities") or []
    required_skills = job_analysis.get("required_skills") or []
    keywords = job_analysis.get("keywords") or []

    lines: List[str] = [
        f"Job title: {title}",
        f"Location: {location}",
        f"Industry (from posting): {industry}",
    ]
    if role_class:
        lines.append(f"Role classification: {role_class}")
    if company_size:
        lines.append(f"Company size (from posting): {company_size}")
    if team_info:
        lines.append(f"Team / role context: {team_info[:2500]}")
    if reporting_to:
        lines.append(f"Reports to: {reporting_to[:500]}")
    if isinstance(responsibilities, list) and responsibilities:
        lines.append("Responsibilities (excerpt):")
        for item in responsibilities[:15]:
            lines.append(f"  • {str(item)[:500]}")
    skill_items: List[str] = []
    if isinstance(required_skills, list):
        skill_items.extend(str(s) for s in required_skills[:12] if s)
    if isinstance(keywords, list):
        skill_items.extend(str(k) for k in keywords[:8] if k)
    if skill_items:
        lines.append(f"Key skills / keywords: {', '.join(skill_items[:20])}")
    if job_input_data:
        url_block = format_url_signals_block(job_input_data)
        if url_block != "Not available":
            lines.append(f"URL signals: {url_block.replace(chr(10), '; ')}")
    return "\n".join(lines)


def _should_use_unnamed_research_path(
    job_analysis: Dict[str, Any],
    raw_company: Optional[str],
) -> bool:
    """True when employer should be researched from job context only."""
    if not _has_usable_company_name(raw_company):
        return True
    employer_type = (job_analysis.get("employer_type") or "").lower()
    return employer_type in ("staffing_agency", "confidential")


def _extract_posting_agency_name(
    job_input_data: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Recruiter/poster name from optional submit header or extension metadata."""
    if not job_input_data or not isinstance(job_input_data, dict):
        return None
    raw = job_input_data.get("detected_company")
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped if stripped else None
    return None


_POSTING_AGENCY_RESEARCH_PREFIX: str = """### RECRUITING AGENCY POSTING
The end hiring employer is NOT named in this job listing. Research the RECRUITING AGENCY / POSTER named below.
Distinguish agency facts from the unknown end-client employer in mission_vision and application_insights.
Do NOT invent an end-client company name, website, or leadership.

"""


def _normalize_confidence(value: Optional[str]) -> str:
    """Normalize confidence string to HIGH, MEDIUM, or LOW."""
    upper = (value or "").upper().strip()
    if upper in _CONFIDENCE_RANK:
        return upper
    return "MEDIUM"


def _cap_confidence_at(
    assessment: Dict[str, Any],
    max_level: str,
) -> Dict[str, Any]:
    """Cap overall_confidence in assessment dict to max_level."""
    if not assessment:
        return {"overall_confidence": max_level, "uncertain_areas": [], "recommendation": ""}
    current = _normalize_confidence(assessment.get("overall_confidence"))
    max_norm = _normalize_confidence(max_level)
    if _CONFIDENCE_RANK.get(current, 1) > _CONFIDENCE_RANK.get(max_norm, 1):
        assessment = dict(assessment)
        assessment["overall_confidence"] = max_norm
    return assessment


def _derive_research_quality(
    *,
    unnamed: bool,
    disambiguation_confidence: Optional[str],
    final_confidence: Optional[str],
) -> str:
    """
    Derive research_quality for UI (#7).

    Returns:
        verified | uncertain | posting_only
    """
    if unnamed:
        return "posting_only"
    disambig = _normalize_confidence(disambiguation_confidence)
    final = _normalize_confidence(final_confidence)
    if disambig == "LOW" or final == "LOW":
        return "uncertain"
    return "verified"


def _should_enable_grounding(
    *,
    company_name: str,
    job_analysis: Dict[str, Any],
    disambiguation_confidence: Optional[str],
) -> bool:
    """Return True when Google Search grounding should be used for this research call."""
    settings = get_settings()
    if not getattr(settings, "company_research_grounding_enabled", False):
        return False
    if is_generic_company_name(company_name):
        return True
    min_conf = (
        getattr(settings, "company_research_grounding_min_confidence", "MEDIUM") or "MEDIUM"
    ).upper()
    disambig = disambiguation_confidence or job_analysis.get("company_name_confidence")
    level = _normalize_confidence(disambig)
    return _CONFIDENCE_RANK.get(level, 1) <= _CONFIDENCE_RANK.get(min_conf, 1)


class CompanyResearchAgent:
    """
    Agent for conducting comprehensive company research using Gemini LLM.

    Provides strategic insights for job applicants including company culture,
    interview preparation tips, competitive landscape, and application advice.
    Results are cached in Redis with posting-context-aware keys.
    """

    def __init__(self, gemini_client: Any, redis_client: Any = None) -> None:
        """
        Initialize the company research agent.

        Args:
            gemini_client: Gemini client for AI-powered research
            redis_client: Deprecated — caching now uses shared utils/cache.py helpers.
        """
        if gemini_client is None:
            raise TypeError("gemini_client cannot be None")

        self.gemini_client: Any = gemini_client
        self._current_user_api_key: Optional[str] = None
        self._current_user_model: Optional[str] = None
        logger.info("Company Research Agent initialized (Gemini-powered)")

    async def process(self, state: WorkflowState) -> WorkflowState:
        """
        Research company information based on job posting data.

        Args:
            state: Current workflow state with job analysis results

        Returns:
            Updated workflow state with company research results
        """
        logger.info("Starting company research process")
        self._current_user_api_key = state.get("user_api_key")
        self._current_user_model = preferred_model_from_state(
            state, self._current_user_api_key
        )

        try:
            job_analysis: Optional[Dict[str, Any]] = state.get("job_analysis")
            if job_analysis is None:
                raise ValueError("Job analysis is required for company research")

            job_input_data: Dict[str, Any] = state.get("job_input_data") or {}
            raw_company: Optional[str] = job_analysis.get("company_name")

            posting_agency_mode = False
            if _should_use_unnamed_research_path(job_analysis, raw_company):
                posting_agency = _extract_posting_agency_name(job_input_data)
                if _has_usable_company_name(posting_agency):
                    company_name = str(posting_agency).strip()
                    posting_agency_mode = True
                    logger.info(
                        "Using posting-agency company research for %s",
                        sanitize_log_value(company_name),
                    )
                else:
                    logger.info(
                        "Using unnamed-posting company research (missing name, staffing, or confidential)"
                    )
                    research_result = await self._research_company_with_llm(
                        "Employer not stated in posting",
                        job_analysis=job_analysis,
                        job_input_data=job_input_data,
                        unnamed=True,
                    )
                    state["company_research"] = research_result.to_dict()
                    return state
            else:
                company_name = str(raw_company).strip()
            disambiguators = build_company_research_cache_disambiguators(
                company_name, job_analysis, job_input_data
            )
            skip_cache = is_generic_company_name(company_name) and not disambiguators.get(
                "url_domain"
            )

            cached_result: Optional[Dict[str, Any]] = None
            if not skip_cache:
                cached_result = await get_cached_company_research(
                    company_name, disambiguators=disambiguators
                )
            if cached_result:
                logger.info("Using cached research for %s", sanitize_log_value(company_name))
                state["company_research"] = cached_result
                return state

            cache_key = _get_company_research_cache_key(
                company_name, disambiguators=disambiguators
            )
            lock_claimed = await acquire_compute_lock(cache_key)

            if not lock_claimed:
                import asyncio as _asyncio

                logger.info(
                    "Compute lock busy for %s, waiting for cache population",
                    sanitize_log_value(company_name),
                )
                for _ in range(6):
                    await _asyncio.sleep(0.5)
                    if not skip_cache:
                        cached_result = await get_cached_company_research(
                            company_name, disambiguators=disambiguators
                        )
                        if cached_result:
                            state["company_research"] = cached_result
                            return state
                logger.warning(
                    "Compute lock wait timed out for %s, computing independently",
                    sanitize_log_value(company_name),
                )

            try:
                research_result = await self._research_company_with_llm(
                    company_name,
                    job_analysis=job_analysis,
                    job_input_data=job_input_data,
                    unnamed=False,
                    posting_agency_mode=posting_agency_mode,
                )
                result_dict = research_result.to_dict()
                if not skip_cache:
                    await cache_company_research(
                        company_name,
                        result_dict,
                        disambiguators=disambiguators,
                    )
                state["company_research"] = result_dict
            finally:
                if lock_claimed:
                    await release_compute_lock(cache_key)

            return state

        except asyncio.TimeoutError:
            logger.error("Company research timed out", exc_info=True)
            raise
        except Exception as e:
            logger.error(
                "Company research failed: %s",
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            raise

    async def _run_disambiguation_step(
        self,
        company_name: str,
        job_analysis: Dict[str, Any],
        job_input_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Run lightweight employer disambiguation before full research.

        Returns:
            Parsed JSON dict or None on failure
        """
        job_context = _format_job_context_for_research(job_analysis, job_input_data)
        url_signals = format_url_signals_block(job_input_data)
        prompt = EMPLOYER_DISAMBIGUATION_PROMPT.format(
            company_name=company_name,
            job_context=job_context,
            url_signals=url_signals,
        )
        try:
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=2048,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
            )
            if response.get("filtered"):
                return None
            parsed = parse_json_from_llm_response(response.get("response", ""))
            return parsed if isinstance(parsed, dict) else None
        except Exception as e:
            logger.warning(
                "Employer disambiguation step failed for %s: %s",
                sanitize_log_value(company_name),
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            return None

    def _build_research_prompt(
        self,
        company_name: str,
        job_analysis: Dict[str, Any],
        job_input_data: Dict[str, Any],
        *,
        unnamed: bool,
        disambiguation: Optional[Dict[str, Any]] = None,
        use_grounding: bool = False,
        posting_agency_mode: bool = False,
    ) -> str:
        """Assemble the full research prompt with context and optional disambiguation."""
        job_context = _format_job_context_for_research(job_analysis, job_input_data)
        url_signals = format_url_signals_block(job_input_data)

        if unnamed:
            prefix = (
                "### EMPLOYER NOT NAMED IN POSTING\n"
                "The listing does not state a company name (common for founding teams, confidential searches, "
                "staffing posts, or short descriptions).\n"
                "Do NOT invent a company name, website, or leadership that is not implied by the text.\n"
                "Fill the JSON with: (1) clear \"employer not disclosed\" language in company_overview; "
                "(2) interview and application guidance tailored to THIS role, industry, and stage "
                "using the job context only.\n\n"
                f"{COMPANY_RESEARCH_DISAMBIGUATION_RULES}\n\n"
                f"### JOB CONTEXT\n{job_context}\n\n"
                f"### POSTING URL SIGNALS\n{url_signals}\n\n---\n\n"
            )
        else:
            disambig_block = ""
            if disambiguation:
                resolved = disambiguation.get("resolved_company_name") or company_name
                signals = disambiguation.get("disambiguation_signals") or []
                rejected = disambiguation.get("rejected_matches") or []
                disambig_block = (
                    f"### EMPLOYER RESOLUTION (pre-step)\n"
                    f"Resolved employer: {resolved}\n"
                    f"Disambiguation confidence: {disambiguation.get('confidence', 'MEDIUM')}\n"
                )
                if signals:
                    disambig_block += "Signals: " + "; ".join(str(s) for s in signals[:5]) + "\n"
                if rejected:
                    disambig_block += "Rejected wrong matches: " + "; ".join(
                        str(r) for r in rejected[:3]
                    ) + "\n"
                disambig_block += "\n"
            agency_block = (
                _POSTING_AGENCY_RESEARCH_PREFIX if posting_agency_mode else ""
            )
            prefix = (
                f"{agency_block}"
                f"{COMPANY_RESEARCH_DISAMBIGUATION_RULES}\n\n"
                f"### EMPLOYER NAME (from job analysis)\n{company_name}\n\n"
                f"{disambig_block}"
                f"### JOB CONTEXT\n{job_context}\n\n"
                f"### POSTING URL SIGNALS\n{url_signals}\n\n"
                "---\n\n"
            )

        body = COMPANY_RESEARCH_PROMPT.format(company_name=company_name)
        if use_grounding:
            body = _GROUNDING_SEARCH_HINT + "\n" + body
        return prefix + body

    async def _research_company_with_llm(
        self,
        company_name: str,
        *,
        job_analysis: Optional[Dict[str, Any]] = None,
        job_input_data: Optional[Dict[str, Any]] = None,
        unnamed: bool = False,
        posting_agency_mode: bool = False,
    ) -> CompanyResearchResult:
        """
        Research company using Gemini LLM with optional disambiguation and grounding.

        Args:
            company_name: Employer name or placeholder
            job_analysis: Job analyzer output (required)
            job_input_data: Workflow job input
            unnamed: True for posting-only research path

        Returns:
            CompanyResearchResult
        """
        if job_analysis is None:
            job_analysis = {}
        job_input_data = job_input_data or {}

        if unnamed:
            logger.info("Researching unnamed employer using job-context-only prompt")
        else:
            logger.info("Researching company with Gemini: %s", sanitize_log_value(company_name))

        start_time: datetime = datetime.now(timezone.utc)
        disambiguation: Optional[Dict[str, Any]] = None
        disambiguation_confidence: Optional[str] = None

        if not unnamed:
            disambiguators = build_company_research_cache_disambiguators(
                company_name, job_analysis, job_input_data
            )
            if not should_skip_disambiguation_step(company_name, job_analysis, disambiguators):
                disambiguation = await self._run_disambiguation_step(
                    company_name, job_analysis, job_input_data
                )
                if disambiguation:
                    disambiguation_confidence = disambiguation.get("confidence")

        use_grounding = _should_enable_grounding(
            company_name=company_name,
            job_analysis=job_analysis,
            disambiguation_confidence=disambiguation_confidence,
        )

        try:
            prompt = self._build_research_prompt(
                company_name,
                job_analysis,
                job_input_data,
                unnamed=unnamed,
                disambiguation=disambiguation,
                use_grounding=use_grounding,
                posting_agency_mode=posting_agency_mode,
            )

            response = await self._generate_research(
                prompt=prompt,
                use_google_search_grounding=use_grounding,
            )

            if response.get("filtered"):
                logger.warning("Response was filtered by safety settings")
                return self._create_fallback_result(
                    company_name, start_time, unnamed=unnamed
                )

            research_data = parse_json_from_llm_response(response.get("response", ""))
            if not research_data:
                logger.warning("Failed to parse LLM response, using fallback")
                return self._create_fallback_result(
                    company_name, start_time, unnamed=unnamed
                )

            result = self._map_to_result(research_data)

            if disambiguation_confidence and _normalize_confidence(disambiguation_confidence) == "LOW":
                result.confidence_assessment = _cap_confidence_at(
                    result.confidence_assessment or {},
                    "LOW",
                )

            final_conf = (result.confidence_assessment or {}).get("overall_confidence")
            result.research_quality = _derive_research_quality(
                unnamed=unnamed,
                disambiguation_confidence=disambiguation_confidence,
                final_confidence=final_conf,
            )
            if posting_agency_mode:
                if result.research_quality == "verified":
                    result.research_quality = "uncertain"
                result.employer_type = "staffing_agency"
                result.disambiguation_notes = (
                    "Research reflects the recruiting agency that posted this role; "
                    "the actual hiring employer was not stated in the posting."
                )
            if disambiguation:
                result.resolved_company_name = disambiguation.get("resolved_company_name")
                if not posting_agency_mode:
                    result.employer_type = disambiguation.get("employer_type")
                notes = disambiguation.get("notes")
                if notes and not posting_agency_mode:
                    result.disambiguation_notes = str(notes)

            result.processing_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()
            logger.info(
                "Company research completed for %s in %.2fs (quality=%s)",
                sanitize_log_value(company_name),
                result.processing_time,
                result.research_quality,
            )
            return result

        except Exception as e:
            logger.error(
                "Error researching company %s: %s",
                sanitize_log_value(company_name),
                sanitize_log_value(str(e)),
                exc_info=True,
            )
            return self._create_fallback_result(company_name, start_time, unnamed=unnamed)

    async def _generate_research(
        self,
        prompt: str,
        *,
        use_google_search_grounding: bool,
    ) -> Dict[str, Any]:
        """
        Call Gemini for research; retry without grounding if grounding fails.

        Args:
            prompt: Full research prompt
            use_google_search_grounding: Whether to enable Google Search tool

        Returns:
            LLM response dict
        """
        try:
            return await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                use_google_search_grounding=use_google_search_grounding,
            )
        except Exception as grounding_exc:
            if not use_google_search_grounding:
                raise
            logger.warning(
                "Grounded company research failed, retrying without grounding: %s",
                sanitize_log_value(str(grounding_exc)),
                exc_info=True,
            )
            return await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                use_google_search_grounding=False,
            )

    def _map_to_result(self, data: Dict[str, Any]) -> CompanyResearchResult:
        """Map LLM response data to CompanyResearchResult schema."""
        result = CompanyResearchResult()

        overview = data.get("company_overview", {})
        result.company_size = overview.get("company_size")
        result.industry = overview.get("industry")
        result.headquarters = overview.get("headquarters")
        result.founded_year = overview.get("founded_year")
        result.website = overview.get("website")
        result.mission_vision = overview.get("mission_vision")
        result.key_products = overview.get("key_products_services", [])

        culture = data.get("culture_and_values", {})
        result.core_values = culture.get("core_values", [])
        result.work_environment = culture.get("work_environment")
        result.employee_benefits = culture.get("employee_benefits", [])
        result.diversity_inclusion = culture.get("diversity_inclusion")
        result.remote_work_policy = culture.get("remote_work_policy")
        result.employee_satisfaction = culture.get("employee_satisfaction")

        interview = data.get("interview_intelligence", {})
        result.typical_interview_process = interview.get("typical_process", [])
        result.hiring_timeline = interview.get("timeline")
        result.interview_format = interview.get("interview_format")
        result.assessment_methods = interview.get("assessment_methods", [])

        result.leadership_info = data.get("leadership_info", [])

        competitive = data.get("competitive_landscape", {})
        result.competitors = competitive.get("competitors", [])
        result.market_position = competitive.get("market_position")
        result.competitive_advantages = competitive.get("competitive_advantages", [])
        result.market_challenges = competitive.get("market_challenges", [])
        result.growth_opportunities = competitive.get("growth_opportunities", [])
        result.recent_developments = competitive.get("recent_developments")

        result.application_insights = data.get("application_insights", {})
        result.confidence_assessment = data.get("confidence_assessment", {})
        result.research_date = datetime.now(timezone.utc).strftime("%b %Y")

        return result

    def _create_fallback_result(
        self,
        company_name: str,
        start_time: datetime,
        *,
        unnamed: bool = False,
    ) -> CompanyResearchResult:
        """Create a minimal fallback result when research fails."""
        result = CompanyResearchResult()
        result.processing_time = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()
        result.mission_vision = (
            f"Unable to complete research for {company_name}. Please research manually."
        )
        result.research_quality = "posting_only" if unnamed else "uncertain"
        result.confidence_assessment = {
            "overall_confidence": "LOW",
            "uncertain_areas": ["Research could not be completed"],
            "recommendation": "Verify employer details manually before your interview.",
        }
        return result

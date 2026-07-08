"""
Agent for advanced job posting analysis and extraction from URLs and text.
Uses AI-powered content analysis to generate structured job data for application workflows.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from utils.text_processing import clean_text
from workflows.state_schema import WorkflowState, InputMethod, JobAnalysisResult
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import sanitize_log_value
from utils.cache import (
    get_cached_job_analysis,
    cache_job_analysis,
    acquire_compute_lock,
    release_compute_lock,
    _get_job_cache_key,
)

logger: logging.Logger = logging.getLogger(__name__)

_INFORMAL_TITLE_RE = re.compile(
    r"(?i)\b(we(?:'|&#x27;|')?re looking|looking to hire|seeking|join us as|hiring)\b"
)
_UNRELIABLE_DETECTED_TITLE_RE = re.compile(
    r"(?i)(linkedin|indeed|glassdoor|ziprecruiter|monster|careerbuilder|\(\d+\)\s*$|^search\s*\|)"
)


def _is_informal_job_title(title: Optional[str]) -> bool:
    """True when the extracted title looks like body copy, not a formal posting header."""
    if not title:
        return True
    t = str(title).strip()
    if not t:
        return True
    if t == t.lower() and any(c.isalpha() for c in t):
        return True
    if _INFORMAL_TITLE_RE.search(t):
        return True
    return False


def _is_reliable_detected_title(title: Optional[str]) -> bool:
    """True when extension/manual header is safe to prefer over LLM paraphrase."""
    if not title:
        return False
    t = str(title).strip()
    if len(t) < 3:
        return False
    if _UNRELIABLE_DETECTED_TITLE_RE.search(t):
        return False
    return True


def _prefer_job_title(
    extracted: Optional[str],
    detected: Optional[str],
) -> Optional[str]:
    """Prefer extension/manual header over informal or paraphrased LLM titles."""
    ext = (extracted or "").strip() or None
    det = (detected or "").strip() or None
    if det and _is_reliable_detected_title(det):
        if _is_informal_job_title(ext) or not ext:
            return det
        if ext.lower() != det.lower():
            return det
    if det and _is_informal_job_title(ext):
        return det
    return ext or det


def _build_title_hint_block(
    detected_title: Optional[str],
    detected_company: Optional[str],
) -> str:
    """Optional prompt section when submitter supplied a known header."""
    title = (detected_title or "").strip()
    company = (detected_company or "").strip()
    if not title and not company:
        return ""
    lines = ["=== KNOWN HEADER (from submission — prefer over informal body copy) ==="]
    if title:
        lines.append(f"Job title: {title}")
    if company:
        lines.append(f"Company: {company}")
    lines.append("")
    return "\n".join(lines)


def _normalize_string_list(val: Any, *, split_lines: bool = False) -> List[str]:
    """Coerce LLM output to List[str]; models often emit a prose string instead of an array."""

    def _flatten_dict(obj: Dict[str, Any]) -> Optional[str]:
        for key in (
            "qualification",
            "requirement",
            "duty",
            "responsibility",
            "text",
            "description",
            "item",
            "skill",
            "name",
        ):
            raw = obj.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        return None

    if val is None:
        return []
    if isinstance(val, list):
        out: List[str] = []
        for item in val:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
            elif isinstance(item, dict):
                t = _flatten_dict(item)
                if t:
                    out.append(t)
        return out
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if split_lines and ("\n" in s or "\r" in s):
            lines = [ln.strip() for ln in re.split(r"\r?\n+", s) if ln.strip()]
            if len(lines) > 1:
                return lines
        return [s]
    return []

# =============================================================================
# CONSTANTS
# =============================================================================

# Content processing constraints
MIN_JOB_TEXT_LENGTH: int = 50  # Minimum characters for valid job posting
MAX_CONTENT_LENGTH_FOR_AI: int = 50000  # Align with extension cap / cache key normalization

# AI processing parameters
AI_TEMPERATURE: float = 0.1  # Low temperature for consistent extraction
AI_MAX_TOKENS: int = 16000  # Aligned with unified agent output cap

# =============================================================================
# PROMPTS
# =============================================================================

AI_SYSTEM_CONTEXT: str = """You are an expert job posting analyst with 15+ years of experience in HR, recruiting, and ATS systems.

## YOUR EXPERTISE:

**Job Posting Analysis:**
- You can extract structured data from any job posting format
- You understand industry-specific terminology across all sectors
- You recognize implicit requirements that aren't explicitly stated
- You know the difference between "required" and "nice-to-have" qualifications

**ATS Knowledge:**
- You understand how Applicant Tracking Systems parse job postings
- You know which keywords recruiters search for
- You can identify ATS-optimized terms vs. casual language
- You understand keyword variations (e.g., "JS" = "JavaScript")

**Industry Intelligence:**
- You recognize company sizes from context clues
- You understand salary ranges by role and location
- You can classify roles accurately across industries
- You identify remote vs. hybrid vs. onsite from subtle cues

## YOUR PRINCIPLES:
- Extract EXACTLY what's stated - don't infer unless obvious
- Be PRECISE with skills - "Python" and "Python 3" are different
- Distinguish REQUIRED vs PREFERRED qualifications carefully
- When uncertain, use null rather than guessing
- Capture ALL skills mentioned, even in passing
- Capture ALL listed locations — many postings offer several offices; never drop any
- Identify HIDDEN requirements (e.g., "fast-paced" = adaptability needed)"""

JOB_ANALYSIS_PROMPT: str = """Analyze this job posting and extract ALL structured information.

{title_hint_block}=== JOB POSTING CONTENT ===
{content}

=== EXTRACTION INSTRUCTIONS ===

Extract information into this EXACT JSON structure. Output ONLY valid JSON, no explanations.

{{
    "company_name": "<company/organization name or null>",
    "job_title": "<formal role title from the posting header/H1/title line — see rules 1–1c>",
    "job_city": "<primary city (first listed) or null if remote/not specified>",
    "job_state": "<state/province of the primary city or null>",
    "job_country": "<country or null>",
    "additional_locations": ["<'City, State' or 'City, Country' for EVERY other location the posting lists beyond the primary — postings often list several offices (e.g. 'San Francisco, CA | New York City, NY'); empty array if only one location>"],
    "employment_type": "<full-time | part-time | contract | temporary | internship | null>",
    "work_arrangement": "<onsite | remote | hybrid | null>",
    "salary_range": {{
        "min": <number or null>,
        "max": <number or null>,
        "currency": "<USD | EUR | GBP | etc. or null>",
        "period": "<yearly | monthly | hourly | null>"
    }},
    "is_student_position": <true if internship/entry-level/new-grad, false otherwise, null if unclear>,
    "company_size": "<Startup (1-50) | Small (51-200) | Medium (201-1000) | Large (1000+) | Enterprise (10000+) | null>",
    "posted_date": "<YYYY-MM-DD if the posting date is explicitly stated; must be between 2026-01-01 and today (inclusive); null if absent, unclear, or would violate those constraints>",
    "application_deadline": "<date string or null>",
    "benefits": ["<benefit 1>", "<benefit 2>"],
    
    "required_skills": [
        "<technical skill 1 - be specific, e.g., 'Python 3' not just 'Python'>",
        "<technical skill 2>",
        "<framework/tool>"
    ],
    "soft_skills": [
        "<soft skill 1, e.g., 'Communication'>",
        "<soft skill 2, e.g., 'Problem-solving'>"
    ],
    "required_qualifications": [
        "<MUST-HAVE qualification 1>",
        "<MUST-HAVE qualification 2>"
    ],
    "preferred_qualifications": [
        "<NICE-TO-HAVE qualification 1>",
        "<NICE-TO-HAVE qualification 2>"
    ],
    "education_requirements": {{
        "degree": "<High School | Associate | Bachelor's | Master's | PhD | null — if the posting says 'degree required' without specifying level, write Bachelor's>",
        "field": "<field of study, e.g. 'Computer Science', 'Engineering', or null if not specified>",
        "required": <true | false — false only if the posting explicitly says degree is NOT required>
    }},
    "years_experience_required": <number or null>,
    "language_requirements": [
        {{"language": "<language>", "proficiency": "<Native | Fluent | Intermediate | Basic>"}}
    ],
    
    "industry": "<Technology | Healthcare | Finance | Education | Retail | Manufacturing | etc.>",
    "role_classification": "<Engineering | Sales | Marketing | Operations | Management | Design | Data | Support | etc.>",
    "keywords": ["<important keyword 1>", "<keyword 2>", "<keyword 3>"],
    "ats_keywords": [
        "<ATS-optimized keyword that recruiters search for>",
        "<another ATS keyword>",
        "<skill variation, e.g., both 'JavaScript' and 'JS'>"
    ],
    
    "visa_sponsorship": <true | false | null if not mentioned>,
    "security_clearance": <true | false | null if not mentioned>,
    "max_travel_preference": <0 | 25 | 50 | 75 | 100 | null>,
    "contact_information": "<recruiter name/email or null>",
    
    "responsibilities": [
        "<key responsibility 1>",
        "<key responsibility 2>"
    ],
    "team_info": "<information about the team or null>",
    "reporting_to": "<who this role reports to or null>",
    "employer_type": "<direct | staffing_agency | confidential | null if unclear>",
    "company_name_confidence": "<HIGH | MEDIUM | LOW — LOW when name is generic, ambiguous, or from a staffing header only>"
}}

## EXTRACTION RULES:
1. job_title must be the FORMAL ROLE TITLE (page header, H1, first title line, or "Job Title:" field) — never informal hiring prose from the body (e.g. do NOT use "we're looking to hire senior backend engineers" as job_title).
1a. Preserve exact capitalization, punctuation, and qualifiers (e.g. "Senior Backend Engineer - Product", not "senior backend engineers").
1b. When the formal title is absent from the pasted text but the body states seniority and team/function (e.g. "product engineering group" + "senior backend engineers"), synthesize the best formal title in Title Case with singular role noun and team qualifier when stated (e.g. "Senior Backend Engineer - Product").
1c. When a KNOWN HEADER block appears above the posting content, treat it as authoritative for job_title (and company_name when provided).
2. Extract ALL technical skills mentioned anywhere in the posting
3. Separate REQUIRED from PREFERRED qualifications carefully
4. For ATS keywords, include variations (React, React.js, ReactJS)
5. Set to null if information is not present - don't guess
6. For salary, extract numbers only if explicitly stated
7. Look for hidden skills in responsibilities section
8. Include soft skills mentioned in "ideal candidate" sections
9. responsibilities MUST be a JSON array of strings — never one long prose paragraph as a substitute. Break "What you'll do" into one element per bullet or discrete duty (minimum 3 items when the posting lists multiple duties).
10. company_name: use the ACTUAL HIRING EMPLOYER named in the posting header, "Company:", or overview — not the ATS vendor (Greenhouse, Lever, Workday), not a job board site name, and not a staffing agency when a client is named. If posted by a staffing agency "on behalf of" a client and the client is unnamed, use null. If both agency and client are named, use the CLIENT. For confidential posts with no legal entity, use null — do not invent a company (the dashboard will show "Unknown").
11. employer_type: "direct" for the actual hiring company; "staffing_agency" when a recruiter/agency posted on behalf of someone else; "confidential" when the employer is intentionally hidden; null if unclear.
12. company_name_confidence: HIGH when the legal employer is clearly stated; MEDIUM when plausible but ambiguous; LOW when generic, staffing-only, or conflicting signals in the posting.
"""


def _validate_posted_date(date_str: Optional[str]) -> Optional[str]:
    """Validate and normalise an LLM-extracted posted_date.

    Accepts any common date string and returns it in YYYY-MM-DD format only if:
      - It can be parsed
      - It is not in the future (> today)
      - It is not before 2026-01-01 (avoids stale / hallucinated dates)

    Returns None for any invalid, future, or too-old input.

    Args:
        date_str: Raw date string from LLM output.

    Returns:
        Normalised YYYY-MM-DD string or None.
    """
    if not date_str:
        return None
    try:
        raw = str(date_str).strip()
        parsed = None
        for fmt in ("%Y-%m-%d", "%Y-%m", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
        now = datetime.now(timezone.utc)
        min_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        if parsed > now:
            return None
        if parsed < min_date:
            return None
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


class JobAnalyzerAgent:
    """
    Job Analyzer Agent for extracting structured data from job postings.

    Supports pasted text and Chrome extension-extracted content, and uses AI-powered
    analysis to extract comprehensive job information including requirements,
    qualifications, and ATS-optimized keywords.

    Attributes:
        gemini_client: AI analysis client for content parsing
    """

    def __init__(self, gemini_client: Any):
        """
        Initialize JobAnalyzerAgent with required clients.

        Args:
            gemini_client: Gemini client for AI text generation

        Raises:
            TypeError: If client is None
        """
        if gemini_client is None:
            raise TypeError("Gemini client is required")

        self.gemini_client = gemini_client

    async def process(self, state: WorkflowState) -> WorkflowState:
        """
        Process job posting and extract structured data.

        Routes to the appropriate processing method based on input type (file/manual/extension),
        performs AI-powered analysis, and updates workflow state with results.
        Utilizes caching to avoid redundant LLM calls for the same job posting.

        Args:
            state: Workflow state containing job input data and processing status

        Returns:
            Updated workflow state with job analysis results or error information

        Raises:
            ValueError: If input method is invalid or required data is missing
            Exception: Any exception will be caught by _execute_agent_node
        """
        session_id = sanitize_log_value(str(state.get("session_id", "unknown")))
        logger.info('Starting job analysis for session %s', sanitize_log_value(session_id))
        start_time: datetime = datetime.now(timezone.utc)

        # Store user API key for use in LLM calls (BYOK mode)
        self._current_user_api_key = state.get("user_api_key")

        try:
            analysis_result: JobAnalysisResult

            # Get job input data from state
            job_input_data = state.get("job_input_data")
            if not job_input_data:
                raise ValueError("Job input data is required for processing")
            input_method = job_input_data.get("input_method")

            # Determine cache lookup parameters
            job_url: Optional[str] = job_input_data.get("job_url")
            job_content: Optional[str] = job_input_data.get("job_content")

            # Check cache first
            cached_analysis = await get_cached_job_analysis(
                job_url=job_url,
                job_content=job_content,
            )
            if cached_analysis:
                logger.info("Using cached job analysis result")
                state["job_analysis"] = cached_analysis
                state["job_analysis"]["from_cache"] = True
                return state

            # Stampede protection: only one coroutine should compute for this job at a time
            cache_key = _get_job_cache_key(job_url, job_content)
            lock_claimed = await acquire_compute_lock(cache_key) if cache_key else True

            if not lock_claimed:
                import asyncio as _asyncio
                logger.info("Compute lock busy for job analysis, waiting for cache population")
                for _ in range(6):  # up to ~3 seconds
                    await _asyncio.sleep(0.5)
                    cached_analysis = await get_cached_job_analysis(job_url=job_url, job_content=job_content)
                    if cached_analysis:
                        logger.info("Using cached job analysis result (lock wait)")
                        state["job_analysis"] = cached_analysis
                        state["job_analysis"]["from_cache"] = True
                        return state
                logger.warning("Compute lock wait timed out for job analysis, computing independently")

            try:
                # Process input based on input method
                if input_method in (InputMethod.FILE, InputMethod.MANUAL, InputMethod.EXTENSION):
                    # For file, manual text, and extension-extracted content
                    if not job_content:
                        raise ValueError(
                            "Job content is required for file/manual/extension input method"
                        )
                    # For extension, use "extension" as source type
                    source_type = "extension" if input_method == InputMethod.EXTENSION else "manual"
                    analysis_result = await self._process_manual_input(
                        job_content,
                        source_type,
                        detected_title=job_input_data.get("detected_title"),
                        detected_company=job_input_data.get("detected_company"),
                    )
                else:
                    raise ValueError(f"Unknown job input method: {input_method}")

                # Calculate and record processing time
                processing_time: float = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
                analysis_result.processing_time = processing_time
                logger.info("Job analysis completed in %.2f seconds", processing_time)

                # Update state with successful results
                analysis_dict = analysis_result.to_dict()
                state["job_analysis"] = analysis_dict

                # Cache the result for future requests
                await cache_job_analysis(
                    analysis=analysis_dict,
                    job_url=job_url,
                    job_content=job_content,
                )
            finally:
                if lock_claimed and cache_key:
                    await release_compute_lock(cache_key)

            logger.info("Job analysis completed successfully and cached")

        except asyncio.TimeoutError:
            logger.error("Job analyzer timed out", exc_info=True)
            raise
        except Exception as e:
            logger.error("Job analyzer failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

        return state

    async def _process_manual_input(
        self,
        job_text: str,
        source_type: str = "manual",
        detected_title: Optional[str] = None,
        detected_company: Optional[str] = None,
    ) -> JobAnalysisResult:
        """
        Process manually entered or extension-extracted job posting text.

        Args:
            job_text: Raw job posting text entered by user or extracted by extension
            source_type: Source type ("manual", "file", or "extension")

        Returns:
            Structured job analysis result from text input

        Raises:
            ValueError: If job text is too short or processing fails
        """
        logger.info("Processing %s job input", sanitize_log_value(str(source_type)))

        # Validate minimum content length to ensure quality analysis
        if not job_text or len(job_text.strip()) < MIN_JOB_TEXT_LENGTH:
            raise ValueError(
                "Job posting text is too short. Please paste the complete job posting including title, company, description, and any other details."
            )

        # Process the validated text using AI extraction
        analysis_result: JobAnalysisResult = await self._parse_generic_job_content(
            job_text,
            source_type,
            detected_title=detected_title,
            detected_company=detected_company,
        )
        return analysis_result

    async def _parse_generic_job_content(
        self,
        content: str,
        source: str,
        detected_title: Optional[str] = None,
        detected_company: Optional[str] = None,
    ) -> JobAnalysisResult:
        """
        Parse job content using AI to extract structured information.

        Args:
            content: Raw job posting content
            source: Source type ("file", "manual", or "extension")

        Returns:
            Structured job analysis result

        Raises:
            ValueError: If AI parsing fails or returns invalid data
        """
        logger.info("Processing job content using AI")

        # Clean and truncate the content
        cleaned_content: str = clean_text(content)
        truncated_content = cleaned_content[:MAX_CONTENT_LENGTH_FOR_AI]

        try:
            title_hint_block = _build_title_hint_block(detected_title, detected_company)
            # Build prompt by replacing the content placeholder
            prompt: str = (
                JOB_ANALYSIS_PROMPT.replace("{title_hint_block}", title_hint_block)
                .replace("{content}", truncated_content)
            )

            # Generate AI analysis with expert system context
            response: Dict[str, Any] = await self.gemini_client.generate(
                prompt=prompt,
                system=AI_SYSTEM_CONTEXT,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
            )

            # Use our shared utility function to parse JSON from LLM response
            parsed_data: Dict[str, Any] = parse_json_from_llm_response(response)

            # Validate parsed data
            if not parsed_data:
                raise ValueError("No valid JSON response received from AI")

            # Helper to safely get string values
            def get_str(key: str, default: str = "") -> str:
                val = parsed_data.get(key)
                return str(val).strip() if val else default

            # Helper to safely get list values
            def get_list(key: str) -> List[Any]:
                val = parsed_data.get(key)
                return val if isinstance(val, list) else []

            def get_optional_str(key: str) -> Optional[str]:
                val = parsed_data.get(key)
                if val is None:
                    return None
                s = str(val).strip()
                if not s or s.lower() in ("null", "none"):
                    return None
                return s

            def get_confidence(key: str) -> Optional[str]:
                val = get_optional_str(key)
                if val and val.upper() in ("HIGH", "MEDIUM", "LOW"):
                    return val.upper()
                return None

            def get_employer_type(key: str) -> Optional[str]:
                val = get_optional_str(key)
                if not val:
                    return None
                lowered = val.lower()
                if lowered in ("direct", "staffing_agency", "confidential"):
                    return lowered
                return None

            # Create structured result from flat JSON (new format)
            resolved_title = _prefer_job_title(
                get_optional_str("job_title"),
                detected_title,
            )
            job_analysis_result = JobAnalysisResult(
                source=source,
                # Basic information
                job_title=resolved_title or get_str("job_title"),
                company_name=get_optional_str("company_name"),
                job_city=parsed_data.get("job_city"),
                job_state=parsed_data.get("job_state"),
                job_country=parsed_data.get("job_country"),
                additional_locations=_normalize_string_list(
                    parsed_data.get("additional_locations")
                ),
                employment_type=parsed_data.get("employment_type"),
                work_arrangement=parsed_data.get("work_arrangement"),
                salary_range=parsed_data.get("salary_range") or {},
                posted_date=_validate_posted_date(parsed_data.get("posted_date")),
                application_deadline=parsed_data.get("application_deadline"),
                benefits=_normalize_string_list(parsed_data.get("benefits")),
                is_student_position=parsed_data.get("is_student_position"),
                company_size=parsed_data.get("company_size"),
                employer_type=get_employer_type("employer_type"),
                company_name_confidence=get_confidence("company_name_confidence"),
                # Skills and qualifications
                required_skills=get_list("required_skills"),
                soft_skills=_normalize_string_list(parsed_data.get("soft_skills")),
                required_qualifications=_normalize_string_list(
                    parsed_data.get("required_qualifications")
                ),
                preferred_qualifications=_normalize_string_list(
                    parsed_data.get("preferred_qualifications")
                ),
                education_requirements=parsed_data.get("education_requirements") or {},
                years_experience_required=parsed_data.get("years_experience_required"),
                language_requirements=get_list("language_requirements"),
                # Classification and keywords
                industry=parsed_data.get("industry"),
                role_classification=parsed_data.get("role_classification"),
                keywords=get_list("keywords"),
                ats_keywords=get_list("ats_keywords"),
                # Additional details
                visa_sponsorship=parsed_data.get("visa_sponsorship"),
                security_clearance=parsed_data.get("security_clearance"),
                max_travel_preference=parsed_data.get("max_travel_preference"),
                contact_information=get_str("contact_information"),
                # Role context
                responsibilities=_normalize_string_list(
                    parsed_data.get("responsibilities"), split_lines=True
                ),
                team_info=parsed_data.get("team_info"),
                reporting_to=parsed_data.get("reporting_to"),
            )

            return job_analysis_result

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")
        except Exception as e:
            raise ValueError(f"AI extraction failed: {str(e)}")

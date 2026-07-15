"""
Hiring Outreach Agent for ApplyPilot.

Standalone agent (not LangGraph) that finds hiring contacts via public web search
grounding and drafts personalized outreach emails after applying.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from utils.llm_client import get_gemini_client  # noqa: F401  # test-patch alias
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger, sanitize_log_value
from utils.security import sanitize_llm_output

from agents.company_research import (
    _grounding_hint_for_provider,
    _has_usable_company_name,
)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

LLM_TEMPERATURE: float = 0.4
LLM_MAX_TOKENS: int = 16000

MAX_CONTACTS: int = 4
VALID_ROLE_TYPES = frozenset({"hiring_manager", "recruiter", "team_peer", "generic"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
VALID_SOURCE_HINTS = frozenset({"company website", "news", "other_public"})

_LINKEDIN_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:linkedin\.com|lnkd\.in)\S*",
    re.IGNORECASE,
)
_BRACKET_PLACEHOLDER_PATTERN = re.compile(r"\[[^\]]+\]")

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT: str = """You are an expert career coach specializing in professional outreach \
after job applications. You help candidates identify relevant hiring contacts using **public web \
signals only** (company websites, news articles, press releases, team pages) and draft polished \
outreach messages that are ready to send immediately.

## YOUR PRINCIPLES:
- Prefer hiring manager, recruiter, or relevant team peer for **this specific role**
- Set confidence honestly — prefer fewer high-quality contacts over many guesses
- Never invent personal email addresses; drafts may omit a To: line
- Do NOT use or cite professional networking profile URLs — omit them entirely if search returns them
- Never mention professional networking sites by name in your output
- YEARS OF EXPERIENCE RULE: The "Years Experience" field is TOTAL career years — NEVER use it as \
domain-specific experience. When referencing tenure, derive counts only from relevant work history \
entries. If uncertain, say "experience with [skill]" without a specific year count.

## CRITICAL WRITING RULES — every rule is mandatory:
1. Write COMPLETE, polished emails and short messages with zero placeholder text.
2. NEVER use square brackets like [Your Name], [Recruiter Name], [Company], or any fill-in-the-blank \
markers. If you lack a detail, omit the reference rather than inserting a bracket.
3. Address contacts by FIRST NAME ONLY when a name is known (e.g., "Hi Sarah,"). Otherwise use \
"Hi there," or "Dear Hiring Team,".
4. Close every email with "Best regards," on its own line — do NOT add the sender's full name below it.
5. Subject lines must be specific to this role and company — not generic, and must NOT include the \
sender's name.
6. short_message must be ≤300 characters, concrete, and ready to paste into a brief note field."""

HIRING_OUTREACH_PROMPT: str = """Find up to {max_contacts} relevant hiring contacts for this job application \
and draft personalized outreach for each. Use public web sources only.

=== JOB ===
{job_info}

=== COMPANY RESEARCH (summary) ===
{company_info}

=== CANDIDATE FIT HIGHLIGHTS (for drafting only — do not invent facts) ===
{matching_highlights}

=== CANDIDATE PROFILE (for drafting only) ===
{profile_summary}

=== TASK ===
Search public sources when available to identify real people who may be involved in hiring for this role. \
Prefer evidence-backed contacts. role_type must be one of: hiring_manager, recruiter, team_peer, generic. \
confidence must be high, medium, or low. source_hint must be company website, news, or other_public.

IMPORTANT: Your response must be ONLY valid JSON. No markdown, no explanation outside JSON.

{{
    "summary": "<1-3 sentences on search quality, caveats, or why contacts may be limited>",
    "contacts": [
        {{
            "name": "<full name or null if unknown>",
            "role_type": "hiring_manager|recruiter|team_peer|generic",
            "likely_title": "<job title as publicly listed>",
            "why_them": "<why this person is relevant to this posting>",
            "confidence": "high|medium|low",
            "evidence": "<public evidence — team page, press quote, etc.; no private data>",
            "source_hint": "company website|news|other_public",
            "short_message": "<≤300 char outreach note, no placeholders>",
            "subject_line": "<specific email subject>",
            "email_body": "<complete email body; first-name greeting when name known; close with Best regards,>"
        }}
    ]
}}

If you cannot identify any credible contacts from public sources, return an empty contacts array and \
explain why in summary."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _should_enable_grounding(llm_provider: Optional[str]) -> bool:
    """
    Return True when web search grounding should be used for hiring outreach.

    Args:
        llm_provider: Resolved LLM provider name

    Returns:
        Whether to pass use_google_search_grounding=True to generate()
    """
    if llm_provider == "ollama":
        return False
    settings = get_settings()
    return bool(getattr(settings, "hiring_outreach_grounding_enabled", True))


def _strip_linkedin_urls(text: str) -> str:
    """Remove linkedin.com and lnkd.in URLs from a string."""
    if not text:
        return text
    cleaned = _LINKEDIN_URL_PATTERN.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _reject_placeholders(text: str) -> str:
    """Strip bracket placeholders like [Your Name] from user-facing strings."""
    if not text:
        return text
    cleaned = _BRACKET_PLACEHOLDER_PATTERN.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _sanitize_string_field(value: Any) -> Any:
    """Apply LinkedIn strip and placeholder rejection to a string field."""
    if not isinstance(value, str):
        return value
    return _reject_placeholders(_strip_linkedin_urls(value))


def _normalize_confidence(value: Any) -> str:
    """Normalize confidence to high|medium|low."""
    if not value:
        return "low"
    normalized = str(value).strip().lower()
    if normalized in VALID_CONFIDENCE:
        return normalized
    if normalized in ("h", "strong", "very high"):
        return "high"
    if normalized in ("m", "moderate", "med"):
        return "medium"
    return "low"


def _normalize_role_type(value: Any) -> str:
    """Normalize role_type to a known enum value."""
    if not value:
        return "generic"
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in VALID_ROLE_TYPES:
        return normalized
    if "recruit" in normalized:
        return "recruiter"
    if "manager" in normalized or "hiring" in normalized:
        return "hiring_manager"
    if "peer" in normalized or "team" in normalized:
        return "team_peer"
    return "generic"


def _normalize_source_hint(value: Any) -> str:
    """Normalize source_hint to a known value."""
    if not value:
        return "other_public"
    normalized = str(value).strip().lower()
    if normalized in VALID_SOURCE_HINTS:
        return normalized
    if "news" in normalized or "press" in normalized:
        return "news"
    if "website" in normalized or "company" in normalized:
        return "company website"
    return "other_public"


def _build_generic_fallback(
    *,
    company_name: str,
    job_title: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Build generic outreach drafts when no contacts are found or parsing fails.

    Args:
        company_name: Employer display name
        job_title: Role title
        reason: Why fallback was used

    Returns:
        Fallback sub-object for the response schema
    """
    employer = company_name or "the company"
    role = job_title or "the role"
    subject_line = f"Interest in {role} opportunity at {employer}"
    email_body = (
        "Dear Hiring Team,\n\n"
        f"I recently applied for the {role} position at {employer} and wanted to express my "
        "continued interest. My background aligns well with the requirements described in the "
        "posting, and I would welcome the chance to discuss how I can contribute to the team.\n\n"
        "Thank you for your time and consideration.\n\n"
        "Best regards,"
    )
    short_message = (
        f"I applied for the {role} role at {employer} and would love to connect about the opportunity."
    )[:300]
    return {
        "used": True,
        "reason": reason,
        "subject_line": subject_line,
        "email_body": email_body,
        "short_message": short_message,
    }


def _empty_fallback() -> Dict[str, Any]:
    """Return an unused fallback object."""
    return {
        "used": False,
        "reason": None,
        "subject_line": None,
        "email_body": None,
        "short_message": None,
    }


# =============================================================================
# AGENT CLASS
# =============================================================================


class HiringOutreachAgent:
    """
    Finds hiring contacts via public web grounding and drafts outreach emails.

    Standalone agent — not part of the LangGraph workflow.
    """

    def __init__(self) -> None:
        """Initialize HiringOutreachAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None
        self._current_llm_provider: Optional[str] = None
        self._current_user_model: Optional[str] = None

    async def generate(
        self,
        job_analysis: Dict[str, Any],
        company_research: Dict[str, Any],
        profile_matching: Dict[str, Any],
        user_profile: Dict[str, Any],
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate hiring outreach contacts and draft messages.

        Args:
            job_analysis: Job analyzer output from workflow
            company_research: Company research output from workflow
            profile_matching: Profile matching output (fit highlights)
            user_profile: User profile data for drafting context
            user_api_key: Optional decrypted BYOK API key
            model: Optional preferred model from Settings
            llm_provider: Resolved LLM provider (gemini, openai, anthropic, ollama)

        Returns:
            Hiring outreach result matching the version-1 JSON schema

        Raises:
            Exception: If the LLM call fails after grounding failover
        """
        structured_logger.log_agent_start("hiring_outreach", None)
        start_time = datetime.now(timezone.utc)

        self._current_user_api_key = user_api_key
        self._current_llm_provider = llm_provider
        self._current_user_model = model
        self.gemini_client = await get_gemini_client()

        job_analysis = job_analysis or {}
        company_research = company_research or {}
        profile_matching = profile_matching or {}
        user_profile = user_profile or {}

        raw_company = (job_analysis.get("company_name") or "").strip()
        company_usable = _has_usable_company_name(raw_company)
        company_name = raw_company if company_usable else "Unknown employer"
        job_title = (job_analysis.get("job_title") or "").strip() or "the open role"

        degraded_note = ""
        if not company_usable:
            degraded_note = (
                "Employer name was missing or unclear from the job posting; "
                "contact discovery may be limited."
            )

        use_grounding = _should_enable_grounding(llm_provider) and company_usable
        grounding_used = False

        try:
            prompt = self._build_prompt(
                job_analysis=job_analysis,
                company_research=company_research,
                profile_matching=profile_matching,
                user_profile=user_profile,
                use_grounding=use_grounding,
            )

            response, grounding_used = await self._generate_with_grounding_failover(
                prompt=prompt,
                use_grounding=use_grounding,
            )

            if response.get("filtered"):
                duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                structured_logger.log_agent_complete("hiring_outreach", None, duration_ms)
                return self._build_result(
                    company_name=company_name,
                    job_title=job_title,
                    summary=degraded_note or "Content generation was filtered.",
                    contacts=[],
                    fallback_reason="Content was filtered by safety settings.",
                    grounding_used=grounding_used,
                )

            parsed = parse_json_from_llm_response(response.get("response", ""))
            if not parsed:
                logger.error(
                    "Failed to parse hiring outreach response: %s",
                    sanitize_log_value(str(response.get("response", ""))[:200]),
                )
                duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                structured_logger.log_agent_complete("hiring_outreach", None, duration_ms)
                return self._build_result(
                    company_name=company_name,
                    job_title=job_title,
                    summary=degraded_note or "Could not parse outreach response.",
                    contacts=[],
                    fallback_reason="Could not parse AI response.",
                    grounding_used=grounding_used,
                )

            summary = _sanitize_string_field(parsed.get("summary") or "")
            if degraded_note:
                summary = f"{degraded_note} {summary}".strip()

            contacts = self._normalize_contacts(parsed.get("contacts") or [])

            fallback = _empty_fallback()
            if not contacts:
                fallback = _build_generic_fallback(
                    company_name=company_name,
                    job_title=job_title,
                    reason="No credible public contacts were identified.",
                )

            result: Dict[str, Any] = {
                "version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "grounding_used": grounding_used,
                "company_name": company_name,
                "job_title": job_title,
                "summary": summary or "Outreach suggestions generated from available context.",
                "contacts": contacts,
                "fallback": fallback,
            }

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            structured_logger.log_agent_complete("hiring_outreach", None, duration_ms)
            return sanitize_llm_output(result)

        except Exception as exc:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            structured_logger.log_agent_error("hiring_outreach", None, exc, duration_ms)
            logger.error(
                "Hiring outreach generation failed: %s",
                sanitize_log_value(str(exc)),
                exc_info=True,
            )
            raise

    async def _generate_with_grounding_failover(
        self,
        *,
        prompt: str,
        use_grounding: bool,
    ) -> tuple[Dict[str, Any], bool]:
        """
        Call the LLM; retry once without grounding if grounded call fails.

        Args:
            prompt: Full user prompt
            use_grounding: Whether to attempt grounded generation first

        Returns:
            Tuple of (LLM response dict, grounding_used flag)
        """
        try:
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                provider=self._current_llm_provider,
                use_google_search_grounding=use_grounding,
            )
            return response, use_grounding
        except Exception as grounding_exc:
            if not use_grounding:
                raise
            logger.warning(
                "Grounded hiring outreach failed, retrying without grounding: %s",
                sanitize_log_value(str(grounding_exc)),
                exc_info=True,
            )
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                provider=self._current_llm_provider,
                use_google_search_grounding=False,
            )
            return response, False

    def _build_prompt(
        self,
        *,
        job_analysis: Dict[str, Any],
        company_research: Dict[str, Any],
        profile_matching: Dict[str, Any],
        user_profile: Dict[str, Any],
        use_grounding: bool,
    ) -> str:
        """Assemble the full LLM prompt with optional grounding hint."""
        body = HIRING_OUTREACH_PROMPT.format(
            max_contacts=MAX_CONTACTS,
            job_info=self._format_job_info(job_analysis),
            company_info=self._format_company_info(company_research),
            matching_highlights=self._format_matching_highlights(profile_matching),
            profile_summary=self._format_profile_summary(user_profile),
        )
        if use_grounding:
            hint = _grounding_hint_for_provider(self._current_llm_provider)
            body = hint + "\n" + body
        return body

    def _normalize_contacts(self, raw_contacts: List[Any]) -> List[Dict[str, Any]]:
        """
        Normalize, sanitize, and clamp contacts to MAX_CONTACTS.

        Args:
            raw_contacts: Parsed contacts list from LLM JSON

        Returns:
            Sanitized contact dicts
        """
        contacts: List[Dict[str, Any]] = []
        for item in raw_contacts[:MAX_CONTACTS]:
            if not isinstance(item, dict):
                continue
            name_raw = item.get("name")
            name = _sanitize_string_field(name_raw) if name_raw else None
            if isinstance(name, str) and not name.strip():
                name = None

            contact = {
                "name": name,
                "role_type": _normalize_role_type(item.get("role_type")),
                "likely_title": _sanitize_string_field(item.get("likely_title") or ""),
                "why_them": _sanitize_string_field(item.get("why_them") or ""),
                "confidence": _normalize_confidence(item.get("confidence")),
                "evidence": _sanitize_string_field(item.get("evidence") or ""),
                "source_hint": _normalize_source_hint(item.get("source_hint")),
                "short_message": _sanitize_string_field(item.get("short_message") or "")[:300],
                "subject_line": _sanitize_string_field(item.get("subject_line") or ""),
                "email_body": _sanitize_string_field(item.get("email_body") or ""),
            }
            contacts.append(contact)
        return contacts

    def _build_result(
        self,
        *,
        company_name: str,
        job_title: str,
        summary: str,
        contacts: List[Dict[str, Any]],
        fallback_reason: str,
        grounding_used: bool,
    ) -> Dict[str, Any]:
        """Build a complete result dict with fallback when contacts are empty."""
        fallback = _build_generic_fallback(
            company_name=company_name,
            job_title=job_title,
            reason=fallback_reason,
        )
        result: Dict[str, Any] = {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "grounding_used": grounding_used,
            "company_name": company_name,
            "job_title": job_title,
            "summary": summary,
            "contacts": contacts,
            "fallback": fallback,
        }
        return sanitize_llm_output(result)

    def _format_job_info(self, job: Dict[str, Any]) -> str:
        """Format job analysis for the prompt."""
        title = (job.get("job_title") or "Not specified").strip()
        company = (job.get("company_name") or "Not specified").strip()
        lines = [
            f"Title: {title}",
            f"Company: {company}",
            f"Location: {job.get('job_city', 'N/A')}, {job.get('job_state', 'N/A')}, "
            f"{job.get('job_country', 'N/A')}",
            f"Work arrangement: {job.get('work_arrangement', 'Not specified')}",
            f"Industry: {job.get('industry', 'Not specified')}",
        ]
        required_skills = job.get("required_skills") or []
        if isinstance(required_skills, list) and required_skills:
            lines.append(f"Key requirements: {', '.join(str(s) for s in required_skills[:12])}")
        responsibilities = job.get("responsibilities") or []
        if isinstance(responsibilities, list) and responsibilities:
            lines.append("Responsibilities (excerpt):")
            for item in responsibilities[:8]:
                lines.append(f"  • {str(item)[:400]}")
        reporting_to = (job.get("reporting_to") or "").strip()
        if reporting_to:
            lines.append(f"Reports to: {reporting_to[:300]}")
        return "\n".join(lines)

    def _format_company_info(self, company: Dict[str, Any]) -> str:
        """Format company research summary for the prompt."""
        if not company:
            return "No company research available."

        overview = company.get("company_overview") or {}
        if isinstance(overview, dict):
            mission = overview.get("mission_vision") or ""
            industry = overview.get("industry") or company.get("industry") or "N/A"
            website = overview.get("website") or "Unknown"
        else:
            mission = ""
            industry = company.get("industry") or "N/A"
            website = "Unknown"

        lines = [
            f"Industry: {industry}",
            f"Website: {website}",
        ]
        if mission:
            lines.append(f"Mission / overview: {str(mission)[:800]}")

        leadership = company.get("leadership_info") or []
        if isinstance(leadership, list) and leadership:
            lines.append("Leadership (public):")
            for leader in leadership[:4]:
                if not isinstance(leader, dict):
                    continue
                name = leader.get("name") or "Unknown"
                title = leader.get("title") or ""
                lines.append(f"  • {name} — {title}")

        app_insights = company.get("application_insights") or {}
        if isinstance(app_insights, dict):
            emphasize = app_insights.get("what_to_emphasize") or []
            if isinstance(emphasize, list) and emphasize:
                lines.append(f"Application emphasis: {', '.join(str(x) for x in emphasize[:5])}")

        return "\n".join(lines)

    def _format_matching_highlights(self, matching: Dict[str, Any]) -> str:
        """Format profile matching highlights for drafting context."""
        if not matching:
            return "No profile matching insights available."

        lines: List[str] = []
        score = matching.get("overall_match_score")
        if score is not None:
            lines.append(f"Overall match score: {score}")

        strengths = matching.get("key_strengths") or matching.get("strengths") or []
        if isinstance(strengths, list) and strengths:
            lines.append("Key strengths:")
            for item in strengths[:6]:
                lines.append(f"  • {str(item)[:300]}")

        positioning = matching.get("competitive_positioning")
        if positioning:
            lines.append(f"Competitive positioning: {str(positioning)[:600]}")

        strategy = matching.get("application_strategy")
        if strategy:
            lines.append(f"Application strategy: {str(strategy)[:600]}")

        return "\n".join(lines) if lines else "No specific matching highlights."

    def _format_profile_summary(self, profile: Dict[str, Any]) -> str:
        """Format candidate profile summary for drafting context."""
        if not profile:
            return "No profile available."

        lines = [
            f"Professional title: {profile.get('professional_title', 'N/A')}",
            f"Years experience (total career): {profile.get('years_experience', 0)}",
        ]
        summary = profile.get("summary")
        if summary:
            lines.append(f"Summary: {str(summary)[:600]}")
        skills = profile.get("skills") or []
        if isinstance(skills, list) and skills:
            lines.append(f"Skills: {', '.join(str(s) for s in skills[:15])}")
        return "\n".join(lines)

"""
Job Finder Careers Resolver Agent.

Resolves a company name to candidate company careers / ATS board URLs via
optional web-search grounding. Orchestrator MUST verify candidates via
ProviderRegistry before accepting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from utils.job_finder.blocklists import url_host_is_blocked
from utils.llm_client import get_llm_client
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger, sanitize_log_value
from utils.security import sanitize_llm_output

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 4000

SYSTEM_CONTEXT = """You help RoleMule find a company's official careers / ATS job board URL.
Return ONLY JSON. Prefer Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Teamtailor,
Recruitee, BambooHR, Workable, Breezy, Pinpoint, or Rippling board URLs when they exist.
Never return job aggregator / job board listing sites. Never invent URLs you did not find.
If unsure, return fewer candidates with lower confidence.
"""

RESOLVE_PROMPT = """Find official careers / ATS job board URLs for this company.

Company name: {company_name}
User location hint: {location_hint}
Role focus (optional): {title_hint}

Return JSON:
{{
  "company_name": "normalized company name",
  "candidates": [
    {{
      "url": "https://...",
      "provider_hint": "greenhouse|ashby|lever|workday|smartrecruiters|teamtailor|recruitee|bamboohr|workable|breezy|pinpoint|rippling|unknown",
      "confidence": "high|medium|low"
    }}
  ],
  "notes": "short note"
}}

Rules:
- Max 5 candidates
- HTTPS URLs only
- Prefer company-hosted ATS boards over aggregators
- Do not include LinkedIn, Indeed, Glassdoor, ZipRecruiter, or similar aggregators
"""


class JobFinderResolverAgent:
    """Resolve company name → careers board URL candidates."""

    def __init__(self) -> None:
        self._current_user_api_key: Optional[str] = None
        self._current_user_model: Optional[str] = None
        self._current_llm_provider: Optional[str] = None

    def _should_enable_grounding(self) -> bool:
        if self._current_llm_provider == "ollama":
            return False
        settings = get_settings()
        return bool(getattr(settings, "job_finder_grounding_enabled", True))

    async def resolve(
        self,
        company_name: str,
        *,
        location_hint: str = "",
        title_hint: str = "",
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve careers board candidates for a company.

        Args:
            company_name: Company to search
            location_hint: Optional user location
            title_hint: Optional role title for search phrasing
            user_api_key: BYOK key
            model: Preferred model
            llm_provider: Active provider

        Returns:
            Sanitized dict with company_name, candidates, notes, grounding_used
        """
        self._current_user_api_key = user_api_key
        self._current_user_model = model
        self._current_llm_provider = llm_provider

        name = (company_name or "").strip()
        if not name:
            return {
                "company_name": "",
                "candidates": [],
                "notes": "Missing company name",
                "grounding_used": False,
            }

        use_grounding = self._should_enable_grounding()
        prompt = RESOLVE_PROMPT.format(
            company_name=name,
            location_hint=location_hint or "unspecified",
            title_hint=title_hint or "unspecified",
        )
        client = await get_llm_client()
        try:
            response = await client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                provider=self._current_llm_provider,
                use_google_search_grounding=use_grounding,
            )
        except Exception as grounding_exc:
            if not use_grounding:
                raise
            logger.warning(
                "Grounded job finder resolve failed, retrying without grounding: %s",
                sanitize_log_value(str(grounding_exc)),
                exc_info=True,
            )
            use_grounding = False
            response = await client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                provider=self._current_llm_provider,
                use_google_search_grounding=False,
            )

        if response.get("filtered"):
            return {
                "company_name": name,
                "candidates": [],
                "notes": "Response filtered",
                "grounding_used": use_grounding,
            }

        parsed = parse_json_from_llm_response(response.get("response", "")) or {}
        cleaned = self._normalize_result(parsed, fallback_name=name)
        cleaned["grounding_used"] = use_grounding
        return sanitize_llm_output(cleaned)

    def _normalize_result(
        self, data: Dict[str, Any], *, fallback_name: str
    ) -> Dict[str, Any]:
        candidates_in = data.get("candidates") or []
        candidates: List[Dict[str, Any]] = []
        if isinstance(candidates_in, list):
            for c in candidates_in[:5]:
                if not isinstance(c, dict):
                    continue
                url = str(c.get("url") or "").strip()
                if not url.startswith("https://"):
                    continue
                if url_host_is_blocked(url):
                    continue
                conf = str(c.get("confidence") or "medium").lower()
                if conf not in ("high", "medium", "low"):
                    conf = "medium"
                hint = str(c.get("provider_hint") or "unknown").lower()
                candidates.append(
                    {
                        "url": url,
                        "provider_hint": hint,
                        "confidence": conf,
                    }
                )
        return {
            "company_name": str(data.get("company_name") or fallback_name).strip()
            or fallback_name,
            "candidates": candidates,
            "notes": str(data.get("notes") or "")[:500],
        }

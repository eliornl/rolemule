"""
Employer disambiguation helpers for company research.

Parses job posting URL signals and builds cache disambiguators without fetching URLs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Generic employer names that collide across industries (lowercase)
_GENERIC_NAME_BLOCKLIST: frozenset[str] = frozenset(
    {
        "atlas",
        "apex",
        "summit",
        "meridian",
        "nova",
        "pulse",
        "vertex",
        "horizon",
        "pioneer",
        "nexus",
        "prime",
        "unity",
        "delta",
        "alpha",
        "beta",
        "gamma",
        "orbit",
        "spark",
        "bridge",
        "catalyst",
        "frontier",
    }
)

# Hostnames where the employer is usually not the site brand
_JOB_BOARD_HOST_FRAGMENTS: frozenset[str] = frozenset(
    {
        "indeed.",
        "glassdoor.",
        "ziprecruiter.",
        "monster.",
        "careerbuilder.",
        "simplyhired.",
    }
)


@dataclass
class EmployerUrlSignals:
    """Parsed signals from a job posting URL (no HTTP fetch)."""

    hostname: str
    registrable_domain: str
    ats_platform: Optional[str]
    ats_slug: Optional[str]
    is_job_board_host: bool


def _extract_registrable_domain(hostname: str) -> str:
    """Best-effort registrable domain (hostname minus common ATS subdomain)."""
    host = hostname.lower().strip(".")
    if host.endswith(".myworkdayjobs.com"):
        return host
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _first_path_segment(path: str) -> Optional[str]:
    """Return first non-empty path segment."""
    segments = [s for s in path.split("/") if s]
    return segments[0] if segments else None


def _workday_slug(path: str) -> Optional[str]:
    """
    Extract employer slug from Workday paths.

    Examples:
        /en-US/acme/job/... -> acme
        /acme/job/... -> acme
    """
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    locale_re = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
    if locale_re.match(segments[0]) and len(segments) > 1:
        return segments[1]
    return segments[0]


def parse_job_url_signals(job_url: Optional[str]) -> Optional[EmployerUrlSignals]:
    """
    Parse employer hints from a job posting URL without fetching it.

    Args:
        job_url: Optional http(s) posting URL

    Returns:
        EmployerUrlSignals or None when URL is missing or invalid
    """
    if not job_url or not str(job_url).strip():
        return None
    raw = str(job_url).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return None
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    is_job_board = any(frag in hostname for frag in _JOB_BOARD_HOST_FRAGMENTS)
    registrable = _extract_registrable_domain(hostname)
    path = parsed.path or ""
    ats_platform: Optional[str] = None
    ats_slug: Optional[str] = None

    if hostname == "jobs.lever.co":
        ats_platform = "lever"
        ats_slug = _first_path_segment(path)
    elif hostname == "boards.greenhouse.io":
        ats_platform = "greenhouse"
        ats_slug = _first_path_segment(path)
    elif hostname.endswith(".myworkdayjobs.com"):
        ats_platform = "workday"
        ats_slug = _workday_slug(path)
    elif hostname == "jobs.ashbyhq.com":
        ats_platform = "ashby"
        ats_slug = _first_path_segment(path)
    elif hostname.endswith(".icims.com"):
        ats_platform = "icims"
        ats_slug = _first_path_segment(path)

    return EmployerUrlSignals(
        hostname=hostname,
        registrable_domain=registrable,
        ats_platform=ats_platform,
        ats_slug=ats_slug,
        is_job_board_host=is_job_board,
    )


def build_primary_location(job_analysis: Dict[str, Any]) -> str:
    """
    Build a primary location string from job analysis fields.

    Args:
        job_analysis: Job analyzer output dict

    Returns:
        Location string for cache keys and prompts
    """
    city = (job_analysis.get("job_city") or "").strip()
    state = (job_analysis.get("job_state") or "").strip()
    country = (job_analysis.get("job_country") or "").strip()
    parts = [p for p in (city, state, country) if p]
    primary = ", ".join(parts) if parts else ""
    extras = job_analysis.get("additional_locations") or []
    if isinstance(extras, list) and extras:
        extra_str = " | ".join(str(x).strip() for x in extras[:3] if x)
        if extra_str:
            return f"{primary} | {extra_str}" if primary else extra_str
    return primary or "not_specified"


def is_generic_company_name(name: str) -> bool:
    """
    Return True when the employer name is too ambiguous to cache by name alone.

    Args:
        name: Company name from job analysis

    Returns:
        True for short or blocklisted generic names
    """
    if not name or not str(name).strip():
        return True
    s = str(name).strip()
    lowered = s.lower()
    if lowered in _GENERIC_NAME_BLOCKLIST:
        return True
    # Very short single-token names collide often (e.g. Atlas, Apex)
    if len(s) <= 5 and " " not in s:
        return True
    return False


def format_url_signals_block(job_input_data: Dict[str, Any]) -> str:
    """
    Format URL signals for LLM prompts.

    Args:
        job_input_data: Workflow job input dict

    Returns:
        Human-readable block for prompts
    """
    job_url = job_input_data.get("job_url") or job_input_data.get("source_url")
    signals = parse_job_url_signals(job_url)
    if not signals:
        return "Not available"
    lines = [
        f"Posting URL hostname: {signals.hostname}",
        f"Registrable domain: {signals.registrable_domain}",
    ]
    if signals.ats_platform:
        lines.append(f"ATS platform: {signals.ats_platform}")
    if signals.ats_slug:
        lines.append(f"ATS employer slug: {signals.ats_slug}")
    if signals.is_job_board_host:
        lines.append(
            "Note: URL appears to be a generic job board host — prefer employer named in posting body."
        )
    return "\n".join(lines)


def build_company_research_cache_disambiguators(
    company_name: str,
    job_analysis: Dict[str, Any],
    job_input_data: Dict[str, Any],
) -> Dict[str, str]:
    """
    Build stable cache key components for company research.

    Args:
        company_name: Employer name from job analysis
        job_analysis: Full job analysis dict
        job_input_data: Workflow job input dict

    Returns:
        Dict with normalized_name, url_domain, industry, primary_location
    """
    normalized_name = company_name.lower().strip()
    industry = (job_analysis.get("industry") or "not_specified").lower().strip()
    primary_location = build_primary_location(job_analysis).lower().strip()

    job_url = job_input_data.get("job_url") or job_input_data.get("source_url")
    signals = parse_job_url_signals(job_url)
    if signals:
        if signals.ats_slug:
            url_domain = f"{signals.ats_platform}:{signals.ats_slug}".lower()
        else:
            url_domain = signals.registrable_domain.lower()
    else:
        url_domain = ""

    return {
        "normalized_name": normalized_name,
        "url_domain": url_domain,
        "industry": industry,
        "primary_location": primary_location,
    }


def should_skip_disambiguation_step(
    company_name: str,
    job_analysis: Dict[str, Any],
    disambiguators: Dict[str, str],
) -> bool:
    """
    Return True when the lightweight disambiguation LLM call can be skipped.

    Args:
        company_name: Employer name
        job_analysis: Job analysis dict
        disambiguators: Cache disambiguator dict

    Returns:
        True for HIGH-confidence specific employers with strong URL signal
    """
    employer_type = (job_analysis.get("employer_type") or "").lower()
    if employer_type in ("staffing_agency", "confidential"):
        return False
    if is_generic_company_name(company_name):
        return False
    confidence = (job_analysis.get("company_name_confidence") or "").upper()
    if confidence == "LOW":
        return False
    if confidence == "MEDIUM":
        return False
    if confidence == "HIGH":
        return True
    # Missing confidence: skip only when specific name + URL domain present
    return bool(disambiguators.get("url_domain")) and not is_generic_company_name(company_name)

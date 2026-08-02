"""Generic JSON-LD JobPosting extractor for custom careers pages."""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse

from utils.job_finder.http import fetch_text
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob

_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def extract_from_html(
    html: str,
    page_url: str,
    company_name: Optional[str] = None,
) -> List[NormalizedJob]:
    """
    Extract NormalizedJob entries from JSON-LD JobPosting blocks in HTML.

    Args:
        html: Raw HTML document text
        page_url: Absolute page URL (used to resolve relative job URLs)
        company_name: Optional display company name override

    Returns:
        List of normalized jobs found in ``application/ld+json`` scripts
    """
    company = company_name or ""
    try:
        host_hint = (urlparse(page_url).hostname or "").split(".")[0]
        if not company and host_hint:
            company = host_hint.replace("-", " ").title()
    except Exception:
        pass

    out: List[NormalizedJob] = []
    seen: set[str] = set()

    for match in _SCRIPT_RE.finditer(html or ""):
        raw = (match.group(1) or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Some pages embed multiple JSON objects; skip unparsable blocks
            continue
        for node in _iter_job_postings(payload):
            job = _job_from_ld(node, page_url=page_url, company=company)
            if job is None:
                continue
            if job.url in seen:
                continue
            seen.add(job.url)
            out.append(job)
    return out


def _iter_job_postings(payload: Any) -> List[dict]:
    """
    Walk a JSON-LD payload and collect JobPosting objects.

    Args:
        payload: Parsed JSON-LD value (dict, list, or nested @graph)

    Returns:
        Flat list of JobPosting dicts
    """
    found: List[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type") or node.get("type")
        type_list: List[str] = []
        if isinstance(types, str):
            type_list = [types]
        elif isinstance(types, list):
            type_list = [str(t) for t in types]
        if any(t.lower() == "jobposting" for t in type_list):
            found.append(node)
        # ItemList / graph containers
        if "@graph" in node:
            walk(node["@graph"])
        if "itemListElement" in node:
            walk(node["itemListElement"])
        if "item" in node:
            walk(node["item"])
        # Some embeds nest the posting under mainEntity
        if "mainEntity" in node:
            walk(node["mainEntity"])

    walk(payload)
    return found


def _job_from_ld(
    node: dict,
    *,
    page_url: str,
    company: str,
) -> Optional[NormalizedJob]:
    """
    Convert a single JSON-LD JobPosting dict into NormalizedJob.

    Args:
        node: JobPosting object
        page_url: Page URL for resolving relative links
        company: Fallback company name

    Returns:
        NormalizedJob, or None if URL/title unusable
    """
    title = str(node.get("title") or node.get("name") or "").strip()
    url_raw = (
        node.get("url")
        or node.get("sameAs")
        or node.get("mainEntityOfPage")
        or page_url
    )
    if isinstance(url_raw, dict):
        url_raw = url_raw.get("@id") or url_raw.get("url") or ""
    job_url = str(url_raw or "").strip()
    if job_url and not job_url.startswith("https://"):
        if job_url.startswith("http://"):
            return None
        job_url = urljoin(page_url if page_url.startswith("https://") else "", job_url)
    if not job_url.startswith("https://"):
        return None
    if not title:
        title = "Untitled"

    org = node.get("hiringOrganization") or {}
    if isinstance(org, dict):
        org_name = org.get("name") or company
    else:
        org_name = str(org) if org else company

    loc = ""
    jl = node.get("jobLocation")
    if isinstance(jl, list) and jl:
        jl = jl[0]
    if isinstance(jl, dict):
        addr = jl.get("address") or jl
        if isinstance(addr, dict):
            parts = [
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("addressCountry"),
            ]
            loc = ", ".join(str(p) for p in parts if p)
        else:
            loc = str(jl.get("name") or "")
    elif isinstance(jl, str):
        loc = jl

    desc = node.get("description") or ""
    external_id = str(node.get("identifier") or node.get("@id") or job_url)
    if isinstance(node.get("identifier"), dict):
        external_id = str(
            node["identifier"].get("value")
            or node["identifier"].get("name")
            or job_url
        )

    return NormalizedJob(
        provider="jsonld_generic",
        external_id=external_id,
        title=title,
        company=str(org_name or company or ""),
        location=str(loc),
        url=job_url,
        description_html=str(desc) if desc else None,
        description_text=html_to_text(str(desc)) if desc else None,
        posted_at=parse_iso_datetime(node.get("datePosted")),
    )


class JsonLdGenericProvider:
    """
    Generic careers fallback: fetch HTML and extract JSON-LD JobPosting.

    ``detect`` always returns False so the registry only invokes this explicitly.
    """

    id = "jsonld_generic"

    def detect(self, url: str) -> bool:
        """
        Never auto-claim URLs; registry calls this provider explicitly.

        Args:
            url: Careers page URL (ignored)

        Returns:
            Always False
        """
        return False

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch page HTML and extract JSON-LD JobPosting listings.

        Args:
            url: Absolute https careers page URL
            company_name: Optional display company name override

        Returns:
            Normalized jobs from JSON-LD, possibly empty
        """
        if not url.startswith("https://"):
            return []
        html = await fetch_text(url, allow_careers_heuristic=True)
        return extract_from_html(html, url, company_name)

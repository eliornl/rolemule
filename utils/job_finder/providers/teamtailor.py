"""Teamtailor careers board provider (JSON API or RSS)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json, fetch_text
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)


class TeamtailorProvider:
    """Fetch jobs from Teamtailor careers sites via JSON or RSS."""

    id = "teamtailor"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL is a Teamtailor careers host.

        Args:
            url: Careers or board URL

        Returns:
            True if teamtailor.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "teamtailor.com")

    def _host(self, url: str) -> Optional[str]:
        """
        Extract hostname from URL.

        Args:
            url: Absolute careers URL

        Returns:
            Lowercased hostname, or None
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return None
        return host or None

    def _slug(self, host: str) -> str:
        """
        Derive company slug from ``{slug}.teamtailor.com``.

        Args:
            host: Teamtailor hostname

        Returns:
            Slug string (may be empty)
        """
        if host.endswith(".teamtailor.com"):
            return host[: -len(".teamtailor.com")].split(".")[0]
        return ""

    def _normalize_from_json(
        self,
        jobs: list,
        *,
        company: str,
        host: str,
    ) -> List[NormalizedJob]:
        """
        Normalize Teamtailor JSON job objects.

        Args:
            jobs: List of job dicts
            company: Display company name
            host: Board hostname for relative URL fallback

        Returns:
            Normalized jobs
        """
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            # Nested data/attributes shape
            attrs = j.get("attributes") if isinstance(j.get("attributes"), dict) else j
            job_url = attrs.get("url") or attrs.get("apply_url") or attrs.get("careers_url") or ""
            links = attrs.get("links")
            if not job_url and isinstance(links, dict):
                job_url = links.get("careersite-job-url") or links.get("self") or ""
            if not job_url and attrs.get("id"):
                job_url = f"https://{host}/jobs/{attrs.get('id')}"
            if not str(job_url).startswith("https://"):
                continue
            html = (
                attrs.get("body")
                or attrs.get("description")
                or attrs.get("pitch")
                or ""
            )
            loc = attrs.get("location") or attrs.get("human_status") or ""
            if isinstance(loc, dict):
                loc = loc.get("name") or loc.get("city") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(attrs.get("id") or j.get("id") or job_url),
                    title=str(attrs.get("title") or "").strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        attrs.get("created_at") or attrs.get("published_at")
                    ),
                )
            )
        return out

    def _normalize_from_rss(
        self,
        rss_text: str,
        *,
        company: str,
    ) -> List[NormalizedJob]:
        """
        Parse a simple RSS/Atom feed into NormalizedJob entries.

        Args:
            rss_text: Raw RSS/XML body
            company: Display company name

        Returns:
            Normalized jobs from ``item`` / ``entry`` elements
        """
        try:
            root = ET.fromstring(rss_text)
        except ET.ParseError:
            return []
        # Handle default namespaces lightly by local-name matching
        items = []
        for el in root.iter():
            tag = el.tag.split("}")[-1].lower() if isinstance(el.tag, str) else ""
            if tag in ("item", "entry"):
                items.append(el)
        out: List[NormalizedJob] = []
        for item in items:
            title = ""
            link = ""
            description = ""
            pub = ""
            for child in list(item):
                ctag = (
                    child.tag.split("}")[-1].lower()
                    if isinstance(child.tag, str)
                    else ""
                )
                text = (child.text or "").strip()
                if ctag == "title" and text:
                    title = text
                elif ctag == "link":
                    href = child.attrib.get("href") or text
                    if href:
                        link = href.strip()
                elif ctag in ("description", "summary", "content") and text:
                    description = text
                elif ctag in ("pubdate", "published", "updated") and text:
                    pub = text
            if not link.startswith("https://"):
                continue
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=link,
                    title=title.strip() or "Untitled",
                    company=company,
                    location="",
                    url=link,
                    description_html=description or None,
                    description_text=html_to_text(description) if description else None,
                    posted_at=parse_iso_datetime(pub) if pub else None,
                )
            )
        return out

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch Teamtailor jobs, preferring JSON API then RSS.

        Args:
            url: Teamtailor careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When host cannot be parsed
        """
        host = self._host(url)
        if not host or not host_matches_domain(host, "teamtailor.com"):
            raise UnsupportedCareersPageError("Could not parse Teamtailor host")
        slug = self._slug(host)
        company = company_name or (slug.replace("-", " ").title() if slug else host)
        allowed = {host}

        # Prefer JSON endpoints when available
        for api in (
            f"https://{host}/api/jobs",
            f"https://{host}/jobs.json",
        ):
            try:
                data = await fetch_json(
                    api,
                    allowed_hosts=allowed,
                    allow_careers_heuristic=False,
                )
            except Exception as exc:
                logger.debug(
                    "Teamtailor JSON fetch failed for %s: %s",
                    sanitize_log_value(api),
                    sanitize_log_value(str(exc)),
                    exc_info=True,
                )
                continue
            jobs: list = []
            if isinstance(data, list):
                jobs = data
            elif isinstance(data, dict):
                jobs = (
                    data.get("jobs")
                    or data.get("data")
                    or data.get("items")
                    or []
                )
            if isinstance(jobs, list) and jobs:
                return self._normalize_from_json(jobs, company=company, host=host)

        # Fallback: RSS
        rss_url = f"https://{host}/jobs.rss"
        try:
            rss_text = await fetch_text(
                rss_url,
                allowed_hosts=allowed,
                allow_careers_heuristic=False,
            )
        except Exception as exc:
            raise UnsupportedCareersPageError(
                "Could not fetch Teamtailor jobs feed"
            ) from exc
        return self._normalize_from_rss(rss_text, company=company)

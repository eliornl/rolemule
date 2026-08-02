"""Workable public widget accounts provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {"apply.workable.com"}

_SLUG_RE = re.compile(r"apply\.workable\.com/([^/?#]+)", re.I)


class WorkableProvider:
    """Fetch jobs from Workable public widget accounts API."""

    id = "workable"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL is an apply.workable.com board.

        Args:
            url: Careers or board URL

        Returns:
            True if apply.workable.com is the host (or subdomain)
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host == "apply.workable.com" or host.endswith(".apply.workable.com")

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse account slug from a Workable careers URL.

        Args:
            url: Workable apply URL

        Returns:
            Slug string, or None
        """
        m = _SLUG_RE.search(url)
        if m:
            slug = m.group(1)
            # Skip known path prefixes that are not account slugs
            if slug.lower() in ("api", "j", "jobs", "widgets"):
                m2 = re.search(r"/accounts/([^/?#]+)", url, re.I)
                return m2.group(1) if m2 else None
            return slug
        m2 = re.search(r"/accounts/([^/?#]+)", url, re.I)
        return m2.group(1) if m2 else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch jobs from ``https://apply.workable.com/api/v1/widget/accounts/{slug}``.

        Args:
            url: Workable apply URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Workable account slug")
        api = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        jobs = []
        if isinstance(data, dict):
            jobs = data.get("jobs") or data.get("results") or []
            name_from_api = data.get("name") or data.get("title")
        else:
            name_from_api = None
            if isinstance(data, list):
                jobs = data
        if not isinstance(jobs, list):
            return []
        company = (
            company_name
            or (str(name_from_api) if name_from_api else None)
            or slug.replace("-", " ").title()
        )
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            shortcode = j.get("shortcode") or j.get("code") or ""
            job_url = j.get("url") or j.get("application_url") or ""
            if not job_url and shortcode:
                job_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"
            if not str(job_url).startswith("https://"):
                continue
            loc = j.get("location") or j.get("city") or ""
            if isinstance(loc, dict):
                parts = [
                    loc.get("city"),
                    loc.get("region"),
                    loc.get("country"),
                ]
                loc = ", ".join(str(p) for p in parts if p)
            html = j.get("description") or j.get("full_description") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or shortcode or job_url),
                    title=str(j.get("title") or "").strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("created_at") or j.get("published_on")
                    ),
                )
            )
        return out

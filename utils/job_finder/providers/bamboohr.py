"""BambooHR public careers list provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

_SLUG_RE = re.compile(r"([a-z0-9-]+)\.bamboohr\.com", re.I)


class BambooHRProvider:
    """Fetch jobs from BambooHR public careers list API."""

    id = "bamboohr"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is BambooHR.

        Args:
            url: Careers or board URL

        Returns:
            True if bamboohr.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "bamboohr.com")

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse company slug from a BambooHR careers URL.

        Args:
            url: BambooHR careers URL

        Returns:
            Slug string, or None
        """
        m = _SLUG_RE.search(url)
        return m.group(1) if m else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch openings from ``https://{slug}.bamboohr.com/careers/list``.

        Args:
            url: BambooHR careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse BambooHR slug")
        host = f"{slug}.bamboohr.com"
        api = f"https://{host}/careers/list"
        data = await fetch_json(api, allowed_hosts={host})
        result: list = []
        if isinstance(data, dict):
            raw = data.get("result")
            if isinstance(raw, list):
                result = raw
            else:
                result = data.get("jobs") or []
        elif isinstance(data, list):
            result = data
        if not isinstance(result, list):
            return []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in result:
            if not isinstance(j, dict):
                continue
            job_id = j.get("id") or j.get("jobOpeningId") or j.get("atsJobId")
            job_url = j.get("jobOpeningShareUrl") or j.get("url") or ""
            if not job_url and job_id:
                job_url = f"https://{host}/careers/{job_id}"
            if not str(job_url).startswith("https://"):
                continue
            title = (
                j.get("jobOpeningName")
                or j.get("jobTitle")
                or j.get("title")
                or ""
            )
            loc = ""
            location = j.get("location") or j.get("atsLocation")
            if isinstance(location, dict):
                parts = [
                    location.get("city"),
                    location.get("state"),
                    location.get("addressCountry") or location.get("country"),
                ]
                loc = ", ".join(str(p) for p in parts if p)
            elif location:
                loc = str(location)
            if not loc:
                loc = str(j.get("locationLabel") or j.get("departmentLabel") or "")
            html = j.get("description") or j.get("jobDescription") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(job_id or job_url),
                    title=str(title).strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("postedDate") or j.get("datePosted")
                    ),
                )
            )
        return out

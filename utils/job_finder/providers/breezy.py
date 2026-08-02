"""Breezy HR public JSON board provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

_SLUG_RE = re.compile(r"([a-z0-9-]+)\.breezy\.hr", re.I)


class BreezyProvider:
    """Fetch jobs from Breezy HR public JSON endpoint."""

    id = "breezy"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is Breezy HR.

        Args:
            url: Careers or board URL

        Returns:
            True if breezy.hr is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "breezy.hr")

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse company slug from a Breezy careers URL.

        Args:
            url: Breezy careers URL

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
        Fetch openings from ``https://{slug}.breezy.hr/json``.

        Args:
            url: Breezy careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Breezy slug")
        host = f"{slug}.breezy.hr"
        api = f"https://{host}/json"
        data = await fetch_json(api, allowed_hosts={host})
        jobs = data if isinstance(data, list) else []
        if isinstance(data, dict):
            jobs = data.get("positions") or data.get("jobs") or []
        if not isinstance(jobs, list):
            return []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in jobs:
            if not isinstance(j, dict):
                continue
            job_url = j.get("url") or j.get("friendly_id") or ""
            if job_url and not str(job_url).startswith("https://"):
                # relative path or friendly id
                path = str(job_url).lstrip("/")
                if path.startswith("p/") or "/" in path:
                    job_url = f"https://{host}/{path}"
                else:
                    job_url = f"https://{host}/p/{path}"
            if not job_url and j.get("id"):
                job_url = f"https://{host}/p/{j.get('id')}"
            if not str(job_url).startswith("https://"):
                continue
            loc = j.get("location") or ""
            if isinstance(loc, dict):
                loc = loc.get("name") or loc.get("city") or ""
            html = j.get("description") or j.get("education") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or j.get("_id") or job_url),
                    title=str(j.get("name") or j.get("title") or "").strip()
                    or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("created_date") or j.get("updated_date")
                    ),
                )
            )
        return out

"""Recruitee public offers API provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

_SLUG_RE = re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I)


class RecruiteeProvider:
    """Fetch jobs from Recruitee public offers API."""

    id = "recruitee"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is Recruitee.

        Args:
            url: Careers or board URL

        Returns:
            True if recruitee.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "recruitee.com")

    def _slug(self, url: str) -> Optional[str]:
        """
        Parse company slug from a Recruitee careers URL.

        Args:
            url: Recruitee careers URL

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
        Fetch open offers from ``https://{slug}.recruitee.com/api/offers/``.

        Args:
            url: Recruitee careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When slug cannot be parsed
        """
        slug = self._slug(url)
        if not slug:
            raise UnsupportedCareersPageError("Could not parse Recruitee slug")
        host = f"{slug}.recruitee.com"
        api = f"https://{host}/api/offers/"
        data = await fetch_json(api, allowed_hosts={host})
        offers = data.get("offers") if isinstance(data, dict) else None
        if not isinstance(offers, list):
            offers = data if isinstance(data, list) else []
        company = company_name or slug.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in offers:
            if not isinstance(j, dict):
                continue
            job_url = (
                j.get("careers_url")
                or j.get("careers_apply_url")
                or j.get("url")
                or ""
            )
            if not job_url and j.get("slug"):
                job_url = f"https://{host}/o/{j.get('slug')}"
            if not str(job_url).startswith("https://"):
                continue
            html = j.get("description") or j.get("requirements") or ""
            loc = j.get("location") or j.get("city") or ""
            if isinstance(loc, dict):
                loc = loc.get("city") or loc.get("name") or ""
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or j.get("slug") or job_url),
                    title=str(j.get("title") or "").strip() or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("created_at") or j.get("published_at")
                    ),
                )
            )
        return out

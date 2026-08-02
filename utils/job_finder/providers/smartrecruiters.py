"""SmartRecruiters public postings provider."""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from utils.job_finder.blocklists import host_matches_domain
from utils.job_finder.http import fetch_json
from utils.job_finder.normalize import html_to_text, parse_iso_datetime
from utils.job_finder.types import NormalizedJob, UnsupportedCareersPageError

ALLOWED_HOSTS = {
    "api.smartrecruiters.com",
    "jobs.smartrecruiters.com",
    "careers.smartrecruiters.com",
}

# careers / jobs.smartrecruiters.com/{companyId}/...
_COMPANY_RE = re.compile(
    r"(?:jobs|careers)\.smartrecruiters\.com/([^/?#]+)",
    re.I,
)


class SmartRecruitersProvider:
    """Fetch jobs from the SmartRecruiters public postings API."""

    id = "smartrecruiters"

    def detect(self, url: str) -> bool:
        """
        Return True when the URL host is SmartRecruiters.

        Args:
            url: Careers or board URL

        Returns:
            True if smartrecruiters.com is in the hostname
        """
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return host_matches_domain(host, "smartrecruiters.com")

    def _company_id(self, url: str) -> Optional[str]:
        """
        Parse company id from a SmartRecruiters careers URL.

        Args:
            url: Careers URL containing the company slug/id

        Returns:
            Company id string, or None
        """
        m = _COMPANY_RE.search(url)
        if m:
            return m.group(1)
        # api path /v1/companies/{id}/postings
        m2 = re.search(r"/companies/([^/?#]+)/postings", url, re.I)
        return m2.group(1) if m2 else None

    async def fetch(
        self,
        url: str,
        *,
        company_name: Optional[str] = None,
    ) -> List[NormalizedJob]:
        """
        Fetch open postings for a SmartRecruiters company board.

        Args:
            url: SmartRecruiters careers URL
            company_name: Optional display company name override

        Returns:
            Normalized open roles

        Raises:
            UnsupportedCareersPageError: When company id cannot be parsed
        """
        company_id = self._company_id(url)
        if not company_id:
            raise UnsupportedCareersPageError(
                "Could not parse SmartRecruiters company id"
            )
        api = (
            f"https://api.smartrecruiters.com/v1/companies/"
            f"{company_id}/postings"
        )
        data = await fetch_json(api, allowed_hosts=ALLOWED_HOSTS)
        content = []
        if isinstance(data, dict):
            content = data.get("content") or data.get("postings") or []
        elif isinstance(data, list):
            content = data
        if not isinstance(content, list):
            return []
        company = company_name or company_id.replace("-", " ").title()
        out: List[NormalizedJob] = []
        for j in content:
            if not isinstance(j, dict):
                continue
            job_url = (
                j.get("postingUrl")
                or j.get("applyUrl")
                or j.get("url")
                or ""
            )
            if not job_url and j.get("id"):
                job_url = (
                    f"https://jobs.smartrecruiters.com/{company_id}/{j.get('id')}"
                )
            if not str(job_url).startswith("https://"):
                continue
            loc = ""
            location = j.get("location")
            if isinstance(location, dict):
                parts = [
                    location.get("city"),
                    location.get("region"),
                    location.get("country"),
                ]
                loc = ", ".join(str(p) for p in parts if p)
            elif location:
                loc = str(location)
            html = j.get("jobAd") or j.get("description") or ""
            if isinstance(html, dict):
                html = html.get("sections") or html.get("text") or ""
                if isinstance(html, list):
                    html = " ".join(str(s) for s in html)
            out.append(
                NormalizedJob(
                    provider=self.id,
                    external_id=str(j.get("id") or j.get("uuid") or job_url),
                    title=str(j.get("name") or j.get("title") or "").strip()
                    or "Untitled",
                    company=company,
                    location=str(loc),
                    url=str(job_url),
                    description_html=str(html) if html else None,
                    description_text=html_to_text(str(html)) if html else None,
                    posted_at=parse_iso_datetime(
                        j.get("releasedDate") or j.get("createdOn")
                    ),
                )
            )
        return out

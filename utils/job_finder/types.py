"""Job Finder — shared types and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


MAX_LISTINGS_PERSIST = 100
MAX_DESCRIPTION_CHARS = 8000
USER_AGENT = (
    "RoleMuleJobFinder/1.0 (+https://rolemule.com; careers-board fetch; not a job-board scraper)"
)


@dataclass(frozen=True)
class NormalizedJob:
    """Canonical job listing from an ATS / careers provider."""

    provider: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    posted_at: Optional[datetime] = None

    @property
    def job_id(self) -> str:
        return f"{self.provider}:{self.external_id}"

    def to_client_dict(self, *, include_description: bool = True) -> Dict[str, Any]:
        """Serialize for API / chat picker (no huge raw payloads)."""
        desc = self.description_text or ""
        if len(desc) > MAX_DESCRIPTION_CHARS:
            desc = desc[:MAX_DESCRIPTION_CHARS]
        data: Dict[str, Any] = {
            "id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "provider": self.provider,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
        }
        if include_description:
            data["description_text"] = desc
        return data


@dataclass
class SearchFilters:
    """Confirmed search filters for listing and chat."""

    title: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    job_types: List[str] = field(default_factory=list)
    work_arrangements: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "keywords": list(self.keywords),
            "locations": list(self.locations),
            "job_types": list(self.job_types),
            "work_arrangements": list(self.work_arrangements),
            "extras": dict(self.extras),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SearchFilters":
        if not data:
            return cls()
        return cls(
            title=(data.get("title") or None),
            keywords=list(data.get("keywords") or []),
            locations=list(data.get("locations") or []),
            job_types=list(data.get("job_types") or []),
            work_arrangements=list(data.get("work_arrangements") or []),
            extras=dict(data.get("extras") or {}),
        )


class BoardNotFoundError(Exception):
    """No usable careers / ATS board found for the company."""


class UnsupportedCareersPageError(Exception):
    """URL is not a supported careers / ATS board."""


class BlockedHostError(Exception):
    """Host is a job board / shortener and is not allowed."""


class SsrfBlockedError(Exception):
    """URL failed SSRF validation."""

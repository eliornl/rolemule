"""Filter NormalizedJob lists using confirmed SearchFilters."""

from __future__ import annotations

from typing import List

from utils.job_finder.types import NormalizedJob, SearchFilters


def _haystack(job: NormalizedJob) -> str:
    return " ".join(
        [
            job.title or "",
            job.location or "",
            job.company or "",
            (job.description_text or "")[:2000],
        ]
    ).lower()


def apply_filters(jobs: List[NormalizedJob], filters: SearchFilters) -> List[NormalizedJob]:
    """
    Apply keyword / location / arrangement filters client-side.

    Empty filter fields are ignored (no-op).
    """
    if not jobs:
        return []

    title = (filters.title or "").strip().lower()
    keywords = [k.strip().lower() for k in filters.keywords if k and k.strip()]
    locations = [loc.strip().lower() for loc in filters.locations if loc and loc.strip()]
    arrangements = [
        a.strip().lower() for a in filters.work_arrangements if a and a.strip()
    ]
    job_types = [t.strip().lower() for t in filters.job_types if t and t.strip()]

    out: List[NormalizedJob] = []
    for job in jobs:
        hay = _haystack(job)

        if title:
            # Soft: all significant tokens from title should appear
            tokens = [t for t in title.replace("/", " ").split() if len(t) > 2]
            if tokens and not all(t in hay for t in tokens[:4]):
                # Fallback: any token match
                if not any(t in hay for t in tokens):
                    continue

        if keywords:
            if not all(k in hay for k in keywords):
                continue

        if locations:
            loc_hay = (job.location or "").lower() + " " + hay
            if not any(loc in loc_hay for loc in locations):
                # Allow remote match if user wants remote and posting says remote
                if not (
                    any("remote" in loc for loc in locations)
                    and "remote" in loc_hay
                ):
                    continue

        if arrangements:
            # Map prefs to tokens often found in postings
            needed_any = False
            matched = False
            for arr in arrangements:
                needed_any = True
                if arr in ("remote", "hybrid", "onsite", "on-site", "in-office"):
                    token = "on-site" if arr in ("onsite", "on-site", "in-office") else arr
                    if token.replace("-", " ") in hay or token in hay or (
                        arr == "onsite" and ("on-site" in hay or "office" in hay)
                    ):
                        matched = True
                        break
                elif arr in hay:
                    matched = True
                    break
            if needed_any and not matched and arrangements:
                # Soft fail: if arrangement keywords absent, still keep (many boards omit)
                pass

        if job_types:
            # Soft filter — keep unless posting clearly contradicts (skip hard filter)
            pass

        out.append(job)

    return out

"""Job Finder conversation orchestrator (state machine)."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.job_finder_resolver import JobFinderResolverAgent
from utils.cache import (
    cache_job_finder_board,
    cache_job_finder_company,
    get_cached_job_finder_board,
    get_cached_job_finder_company,
)
from utils.job_finder.blocklists import url_host_is_blocked
from utils.job_finder.filters import apply_filters
from utils.job_finder.registry import get_provider_registry
from utils.job_finder.types import (
    BlockedHostError,
    MAX_LISTINGS_PERSIST,
    NormalizedJob,
    SearchFilters,
    UnsupportedCareersPageError,
)
from utils.logging_config import sanitize_log_value
from utils.security import sanitize_text

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https://[^\s<>\"']+", re.I)


def seed_filters_from_profile(profile: Dict[str, Any]) -> SearchFilters:
    """Build proposed filters from UserProfile fields."""
    locations: List[str] = []
    for part in (profile.get("city"), profile.get("state"), profile.get("country")):
        if part and str(part).strip():
            locations.append(str(part).strip())
    arrangements = list(profile.get("work_arrangements") or [])
    job_types = list(profile.get("job_types") or [])
    title = (profile.get("professional_title") or "").strip() or None
    return SearchFilters(
        title=title,
        locations=locations,
        work_arrangements=arrangements,
        job_types=job_types,
        keywords=[],
        extras={},
    )


def filters_proposal_text(filters: SearchFilters) -> str:
    """Human-readable filter confirmation prompt."""
    bits: List[str] = []
    if filters.title:
        bits.append(f"**{filters.title}**")
    if filters.work_arrangements:
        bits.append(", ".join(filters.work_arrangements))
    if filters.job_types:
        bits.append(", ".join(filters.job_types))
    if filters.locations:
        bits.append(" · ".join(filters.locations))
    summary = "; ".join(bits) if bits else "your saved preferences"
    return (
        f"I'll search company careers pages using: {summary}.\n\n"
        "Does that look right? Reply **yes** to confirm, or tell me what to change "
        "(title, remote/hybrid, location, keywords)."
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_message(
    role: str,
    content: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a chat message dict."""
    return {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": sanitize_text(content),
        "created_at": _now_iso(),
        "meta": meta or {"type": "text"},
    }


def _company_cache_key(company: str) -> str:
    return hashlib.sha256(company.strip().lower().encode("utf-8")).hexdigest()[:32]


class JobFinderOrchestrator:
    """Drive Job Finder chat turns."""

    def __init__(self) -> None:
        self._resolver = JobFinderResolverAgent()
        self._registry = get_provider_registry()

    def initial_assistant_messages(
        self, profile: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], SearchFilters, str]:
        """
        Create opening messages + proposed filters.

        Returns:
            messages, proposed_filters, phase
        """
        proposed = seed_filters_from_profile(profile)
        greeting = (
            "Welcome to **Find jobs**. I'll look for open roles on company careers pages "
            "(not job boards), then you can add them to Applications for analysis.\n\n"
            "RoleMule does **not** apply for you — you review and apply yourself."
        )
        msgs = [
            make_message("assistant", greeting, meta={"type": "text"}),
            make_message(
                "assistant",
                filters_proposal_text(proposed),
                meta={"type": "filter_proposal", "filters": proposed.to_dict()},
            ),
        ]
        return msgs, proposed, "await_filter_confirm"

    async def handle_user_message(
        self,
        *,
        user_text: str,
        phase: str,
        confirmed_filters: Optional[Dict[str, Any]],
        last_listings: Optional[List[Dict[str, Any]]],
        profile: Dict[str, Any],
        user_api_key: Optional[str],
        model: Optional[str],
        llm_provider: Optional[str],
    ) -> Dict[str, Any]:
        """
        Process one user turn.

        Returns dict with keys:
          assistant_messages, phase, confirmed_filters, last_board, last_listings
        """
        text = (user_text or "").strip()
        filters = SearchFilters.from_dict(confirmed_filters)
        listings = list(last_listings or [])

        if phase == "await_filter_confirm":
            return self._handle_filter_confirm(text, filters, profile)

        if phase in ("await_company", "await_selection", "post_select"):
            # Careers URL paste shortcut
            url_m = _URL_RE.search(text)
            if url_m:
                url = url_m.group(0).rstrip(".,)")
                return await self._handle_careers_url(
                    url,
                    company_name=self._guess_company_from_text(text),
                    filters=filters,
                )

            lower = text.lower().strip()
            if lower in ("done", "stop", "thanks", "thank you"):
                return {
                    "assistant_messages": [
                        make_message(
                            "assistant",
                            "Sounds good. Open **Applications** anytime — or send another company name to keep hunting.",
                        )
                    ],
                    "phase": "await_company",
                    "confirmed_filters": filters.to_dict(),
                    "last_board": None,
                    "last_listings": listings,
                }

            # Filter tweak while listings exist
            if listings and self._looks_like_filter_tweak(lower):
                return self._refilter_listings(text, filters, listings)

            company = self._extract_company(text)
            if not company:
                return {
                    "assistant_messages": [
                        make_message(
                            "assistant",
                            "Which **company** should I search next? "
                            "You can also paste a company careers page URL.",
                        )
                    ],
                    "phase": "await_company",
                    "confirmed_filters": filters.to_dict(),
                    "last_board": None,
                    "last_listings": listings,
                }

            return await self._resolve_and_list(
                company=company,
                filters=filters,
                profile=profile,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )

        # Default recovery
        return {
            "assistant_messages": [
                make_message(
                    "assistant",
                    "Let's continue — which company should I search?",
                )
            ],
            "phase": "await_company",
            "confirmed_filters": filters.to_dict(),
            "last_board": None,
            "last_listings": listings,
        }

    def _handle_filter_confirm(
        self,
        text: str,
        filters: SearchFilters,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        lower = text.lower().strip()
        if lower in ("yes", "y", "ok", "okay", "confirm", "looks good", "good", "sure"):
            return {
                "assistant_messages": [
                    make_message(
                        "assistant",
                        "Great. Which **company** first? "
                        "(One at a time — add filters like “remote” if you want.)",
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": None,
                "last_listings": [],
            }

        # Parse simple overrides
        updated = SearchFilters.from_dict(filters.to_dict())
        if "remote" in lower and "remote" not in [
            a.lower() for a in updated.work_arrangements
        ]:
            updated.work_arrangements = list(updated.work_arrangements) + ["remote"]
        if "hybrid" in lower and "hybrid" not in [
            a.lower() for a in updated.work_arrangements
        ]:
            updated.work_arrangements = list(updated.work_arrangements) + ["hybrid"]
        # Title override: "title: X" or "looking for X"
        m = re.search(
            r"(?:title|role|looking for|search for)\s*[:\-]?\s*(.+)$",
            text,
            re.I,
        )
        if m:
            updated.title = m.group(1).strip()[:120]
        elif len(text) < 80 and lower not in ("no", "n"):
            # Treat short reply as new title if not a naked no
            if not any(w in lower for w in ("remote", "hybrid", "onsite", "location")):
                updated.title = text.strip()[:120]

        if lower in ("no", "n") and not m:
            # Ask explicitly
            return {
                "assistant_messages": [
                    make_message(
                        "assistant",
                        "No problem — what **title**, **location**, and **work arrangement** "
                        "(remote / hybrid / onsite) should I use?",
                        meta={"type": "filter_proposal", "filters": updated.to_dict()},
                    )
                ],
                "phase": "await_filter_confirm",
                "confirmed_filters": updated.to_dict(),
                "last_board": None,
                "last_listings": [],
            }

        return {
            "assistant_messages": [
                make_message(
                    "assistant",
                    filters_proposal_text(updated)
                    + "\n\nReply **yes** when ready.",
                    meta={"type": "filter_proposal", "filters": updated.to_dict()},
                )
            ],
            "phase": "await_filter_confirm",
            "confirmed_filters": updated.to_dict(),
            "last_board": None,
            "last_listings": [],
        }

    def _extract_company(self, text: str) -> str:
        cleaned = _URL_RE.sub("", text).strip()
        # Strip common filter words for company extraction
        cleaned = re.sub(
            r"\b(remote|hybrid|onsite|on-site|full-?time|part-?time)\b",
            "",
            cleaned,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
        # "at Acme" / "for Acme"
        m = re.search(r"\b(?:at|for|company)\s+(.+)$", cleaned, re.I)
        if m:
            return m.group(1).strip()[:120]
        return cleaned[:120]

    def _guess_company_from_text(self, text: str) -> str:
        without = _URL_RE.sub("", text).strip()
        return without[:80] if without else "Company"

    def _looks_like_filter_tweak(self, lower: str) -> bool:
        return any(
            k in lower
            for k in (
                "only remote",
                "remote only",
                "filter",
                "show remote",
                "hybrid only",
                "relax",
            )
        )

    def _refilter_listings(
        self,
        text: str,
        filters: SearchFilters,
        listings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        updated = SearchFilters.from_dict(filters.to_dict())
        lower = text.lower()
        if "remote" in lower:
            updated.work_arrangements = ["remote"]
            updated.locations = ["remote"]
        jobs = [
            NormalizedJob(
                provider=str(j.get("provider") or "unknown"),
                external_id=str(j.get("id") or "").split(":", 1)[-1],
                title=str(j.get("title") or ""),
                company=str(j.get("company") or ""),
                location=str(j.get("location") or ""),
                url=str(j.get("url") or ""),
                description_text=j.get("description_text"),
            )
            for j in listings
            if j.get("url")
        ]
        filtered = apply_filters(jobs, updated)
        client_jobs = [j.to_client_dict() for j in filtered[:MAX_LISTINGS_PERSIST]]
        if not client_jobs:
            return {
                "assistant_messages": [
                    make_message(
                        "assistant",
                        "No roles matched those filters. Want to relax them, or try another company?",
                    )
                ],
                "phase": "await_selection",
                "confirmed_filters": updated.to_dict(),
                "last_board": None,
                "last_listings": listings,
            }
        return {
            "assistant_messages": [
                make_message(
                    "assistant",
                    f"Filtered to **{len(client_jobs)}** role(s). Select any to add to Applications.",
                    meta={"type": "job_picker", "jobs": client_jobs},
                )
            ],
            "phase": "await_selection",
            "confirmed_filters": updated.to_dict(),
            "last_board": None,
            "last_listings": client_jobs,
        }

    async def _resolve_and_list(
        self,
        *,
        company: str,
        filters: SearchFilters,
        profile: Dict[str, Any],
        user_api_key: Optional[str],
        model: Optional[str],
        llm_provider: Optional[str],
    ) -> Dict[str, Any]:
        location_hint = ", ".join(
            p
            for p in (
                profile.get("city"),
                profile.get("state"),
                profile.get("country"),
            )
            if p
        )
        cache_key = _company_cache_key(company)
        cached = await get_cached_job_finder_company(cache_key)
        board_url = None
        provider_id = None
        if cached and cached.get("board_url"):
            board_url = cached["board_url"]
            provider_id = cached.get("provider")

        status_msgs: List[Dict[str, Any]] = [
            make_message(
                "assistant",
                f"Looking up careers pages for **{sanitize_text(company)}**…",
                meta={"type": "status"},
            )
        ]

        if not board_url:
            resolved = await self._resolver.resolve(
                company,
                location_hint=location_hint,
                title_hint=filters.title or "",
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )
            for cand in resolved.get("candidates") or []:
                url = cand.get("url") or ""
                if not url or url_host_is_blocked(url):
                    continue
                try:
                    jobs = await self._registry.fetch_jobs(
                        url, company_name=resolved.get("company_name") or company
                    )
                    board_url = url
                    provider_id = self._registry.detect_provider_id(url) or cand.get(
                        "provider_hint"
                    )
                    await cache_job_finder_company(
                        cache_key,
                        {
                            "board_url": board_url,
                            "provider": provider_id,
                            "company_name": resolved.get("company_name") or company,
                        },
                    )
                    return self._listings_response(
                        company=resolved.get("company_name") or company,
                        board_url=board_url,
                        provider_id=provider_id or "unknown",
                        jobs=jobs,
                        filters=filters,
                        prefix_messages=status_msgs,
                    )
                except (BlockedHostError, UnsupportedCareersPageError) as exc:
                    logger.info(
                        "Candidate board rejected: %s",
                        sanitize_log_value(str(exc)),
                    )
                    continue
                except Exception as exc:
                    logger.info(
                        "Candidate fetch failed: %s",
                        sanitize_log_value(str(exc)),
                        exc_info=True,
                    )
                    continue

            return {
                "assistant_messages": status_msgs
                + [
                    make_message(
                        "assistant",
                        f"I couldn't find a readable careers board for **{sanitize_text(company)}**. "
                        "Paste their careers page URL, or try another company. "
                        "You can also use **New Application** to paste a job description.",
                        meta={"type": "error"},
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": None,
                "last_listings": [],
            }

        # Cached board path
        try:
            slug = board_url.rstrip("/").split("/")[-1]
            cached_board = await get_cached_job_finder_board(
                provider_id or "unknown", slug
            )
            if cached_board and cached_board.get("jobs"):
                jobs = [
                    NormalizedJob(
                        provider=str(j.get("provider") or provider_id or "unknown"),
                        external_id=str(j.get("id") or "").split(":", 1)[-1],
                        title=str(j.get("title") or ""),
                        company=str(j.get("company") or company),
                        location=str(j.get("location") or ""),
                        url=str(j.get("url") or ""),
                        description_text=j.get("description_text"),
                    )
                    for j in cached_board["jobs"]
                    if j.get("url")
                ]
            else:
                jobs = await self._registry.fetch_jobs(
                    board_url, company_name=company
                )
                await cache_job_finder_board(
                    provider_id or "unknown",
                    slug,
                    {"jobs": [j.to_client_dict() for j in jobs[:MAX_LISTINGS_PERSIST]]},
                )
            return self._listings_response(
                company=company,
                board_url=board_url,
                provider_id=provider_id or "unknown",
                jobs=jobs,
                filters=filters,
                prefix_messages=status_msgs,
            )
        except Exception as exc:
            logger.info(
                "Cached board fetch failed: %s",
                sanitize_log_value(str(exc)),
                exc_info=True,
            )
            return {
                "assistant_messages": status_msgs
                + [
                    make_message(
                        "assistant",
                        "That careers page didn't load. Paste a careers URL or try another company.",
                        meta={"type": "error"},
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": None,
                "last_listings": [],
            }

    async def _handle_careers_url(
        self,
        url: str,
        *,
        company_name: str,
        filters: SearchFilters,
    ) -> Dict[str, Any]:
        if url_host_is_blocked(url):
            return {
                "assistant_messages": [
                    make_message(
                        "assistant",
                        "That looks like a job board link. Please paste the company's own careers page URL instead.",
                        meta={"type": "error"},
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": None,
                "last_listings": [],
            }
        try:
            jobs = await self._registry.fetch_jobs(url, company_name=company_name)
            provider_id = self._registry.detect_provider_id(url) or "unknown"
            return self._listings_response(
                company=company_name,
                board_url=url,
                provider_id=provider_id,
                jobs=jobs,
                filters=filters,
                prefix_messages=[],
            )
        except Exception as exc:
            logger.info(
                "Manual careers URL failed: %s",
                sanitize_log_value(str(exc)),
                exc_info=True,
            )
            return {
                "assistant_messages": [
                    make_message(
                        "assistant",
                        "I couldn't read open roles from that URL. Try another careers link, "
                        "or use New Application to paste the job text.",
                        meta={"type": "error"},
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": None,
                "last_listings": [],
            }

    def _listings_response(
        self,
        *,
        company: str,
        board_url: str,
        provider_id: str,
        jobs: List[NormalizedJob],
        filters: SearchFilters,
        prefix_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        filtered = apply_filters(jobs, filters)
        client_jobs = [j.to_client_dict() for j in filtered[:MAX_LISTINGS_PERSIST]]
        board = {
            "provider": provider_id,
            "board_url": board_url,
            "company_name": company,
            "fetched_at": _now_iso(),
        }
        if not client_jobs:
            total = len(jobs)
            msg = (
                f"Found **{total}** open role(s) at **{sanitize_text(company)}**, "
                "but none matched your filters. "
                "Reply to relax filters (e.g. “show all”) or try another company."
            )
            # If filters wiped everything, offer unfiltered
            if total > 0:
                client_jobs = [j.to_client_dict() for j in jobs[:MAX_LISTINGS_PERSIST]]
                msg = (
                    f"Found **{len(client_jobs)}** open role(s) at **{sanitize_text(company)}** "
                    "(showing all — none matched your filters tightly). "
                    "Select any to **Add to applications**."
                )
                return {
                    "assistant_messages": prefix_messages
                    + [
                        make_message(
                            "assistant",
                            msg,
                            meta={"type": "job_picker", "jobs": client_jobs},
                        )
                    ],
                    "phase": "await_selection",
                    "confirmed_filters": filters.to_dict(),
                    "last_board": board,
                    "last_listings": client_jobs,
                }
            return {
                "assistant_messages": prefix_messages
                + [
                    make_message(
                        "assistant",
                        f"No open roles on that careers page for **{sanitize_text(company)}**. "
                        "Try another company?",
                    )
                ],
                "phase": "await_company",
                "confirmed_filters": filters.to_dict(),
                "last_board": board,
                "last_listings": [],
            }

        return {
            "assistant_messages": prefix_messages
            + [
                make_message(
                    "assistant",
                    f"Found **{len(client_jobs)}** matching role(s) at **{sanitize_text(company)}**. "
                    "Select any to **Add to applications** (we'll analyze them — we won't apply for you).",
                    meta={"type": "job_picker", "jobs": client_jobs},
                )
            ],
            "phase": "await_selection",
            "confirmed_filters": filters.to_dict(),
            "last_board": board,
            "last_listings": client_jobs,
        }

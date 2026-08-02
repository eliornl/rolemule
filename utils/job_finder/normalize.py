"""Normalize ATS HTML/text into clean job description text."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Optional

from utils.security import sanitize_html, sanitize_text

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(raw_html: Optional[str]) -> str:
    """Convert HTML job description to plain text."""
    if not raw_html:
        return ""
    cleaned = sanitize_html(raw_html)
    # Drop remaining tags after bleach
    text = _TAG_RE.sub(" ", cleaned)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return sanitize_text(text)


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    """Parse common ISO-ish timestamps to aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        # Heuristic: ms vs s
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None

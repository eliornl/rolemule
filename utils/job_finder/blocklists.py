"""Job-board host blocklists and private IP ranges for Job Finder."""

from __future__ import annotations

import ipaddress
from typing import List
from urllib.parse import urlparse

# Aggregators / job boards — never use as "company careers" sources.
# Do not echo these names in user-facing errors.
JOB_BOARD_HOST_SUFFIXES: List[str] = [
    "indeed.com",
    "indeed.co.uk",
    "linkedin.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "simplyhired.com",
    "careerbuilder.com",
    "dice.com",
    "reed.co.uk",
    "totaljobs.com",
    "stepstone.de",
    "seek.com.au",
    "naukri.com",
    "wellfound.com",
    "angel.co",
    "otta.com",
    "hired.com",
    "levels.fyi",
    "builtin.com",
    "flexjobs.com",
    "remoteok.com",
    "weworkremotely.com",
    "remotive.com",
    "jobspy.com",
]

URL_SHORTENER_SUFFIXES: List[str] = [
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "forms.gle",
    "goo.gl",
    "shorturl.at",
    "rebrand.ly",
    "cutt.ly",
    "ow.ly",
    "buff.ly",
]

_INTERNAL_RANGES = [
    ipaddress.ip_network(r)
    for r in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",  # CGNAT
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",  # benchmarking
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "::ffff:0:0/96",  # IPv4-mapped IPv6 prefix (also unwrapped below)
    )
]


def hostname_matches_suffix(hostname: str, suffixes: List[str]) -> bool:
    """Return True if hostname equals or is a subdomain of any suffix."""
    host = (hostname or "").lower().rstrip(".")
    if not host:
        return False
    for suffix in suffixes:
        s = suffix.lower()
        if host == s or host.endswith("." + s):
            return True
    return False


def is_blocked_job_board_host(hostname: str) -> bool:
    """True when host is a known job board / aggregator."""
    return hostname_matches_suffix(hostname, JOB_BOARD_HOST_SUFFIXES)


def is_url_shortener_host(hostname: str) -> bool:
    """True when host is a URL shortener."""
    return hostname_matches_suffix(hostname, URL_SHORTENER_SUFFIXES)


def is_blocked_host(hostname: str) -> bool:
    """True when host must not be fetched by Job Finder."""
    return is_blocked_job_board_host(hostname) or is_url_shortener_host(hostname)


def is_private_ip(ip_str: str) -> bool:
    """True when IP is loopback / link-local / private / metadata-adjacent."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Unwrap IPv4-mapped IPv6 (::ffff:10.0.0.1) before range checks
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    return any(ip in net for net in _INTERNAL_RANGES)


def host_matches_domain(hostname: str, domain: str) -> bool:
    """True when hostname equals domain or is a subdomain of it (suffix-safe)."""
    host = (hostname or "").lower().rstrip(".")
    d = (domain or "").lower().rstrip(".")
    if not host or not d:
        return False
    return host == d or host.endswith("." + d)


def url_host_is_blocked(url: str) -> bool:
    """Parse URL and check blocklists (False if unparseable)."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return bool(host) and is_blocked_host(host)
    except Exception:
        return True

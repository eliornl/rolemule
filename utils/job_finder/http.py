"""SSRF-safe HTTP helpers for Job Finder ATS fetches."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import ssl
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from utils.job_finder.blocklists import is_blocked_host, is_private_ip
from utils.job_finder.types import SsrfBlockedError, USER_AGENT
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=3.0)
WORKDAY_TIMEOUT = httpx.Timeout(20.0, connect=3.0)
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MAX_HEADER_BYTES = 64 * 1024


def _validate_url_for_fetch(
    url: str,
    *,
    allowed_hosts: Optional[set[str]] = None,
    allow_careers_heuristic: bool = False,
) -> str:
    """
    Validate URL scheme/host before fetch (DNS checked separately).

    Args:
        url: Absolute URL
        allowed_hosts: If set, hostname must match exactly or be subdomain of one entry
        allow_careers_heuristic: Allow generic https hosts that are not blocklisted

    Returns:
        Normalized URL string

    Raises:
        SsrfBlockedError: When URL is unsafe or disallowed
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SsrfBlockedError(f"Invalid URL: {exc}") from exc

    if parsed.scheme != "https":
        raise SsrfBlockedError("Only HTTPS URLs are allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SsrfBlockedError("URL missing hostname")
    if is_blocked_host(host):
        raise SsrfBlockedError("Host is not allowed for careers fetches")

    # Literal IP in hostname
    if is_private_ip(host):
        raise SsrfBlockedError("Private IP addresses are not allowed")

    if allowed_hosts:
        ok = False
        for allowed in allowed_hosts:
            a = allowed.lower()
            if host == a or host.endswith("." + a):
                ok = True
                break
        if not ok:
            raise SsrfBlockedError(f"Host not in provider allowlist: {host}")
    elif not allow_careers_heuristic:
        raise SsrfBlockedError("Host not allowlisted")

    return url


async def _resolve_public_ips(host: str) -> List[str]:
    """
    Resolve hostname and reject any private / link-local answers.

    Returns:
        List of public IP strings (IPv4 or IPv6)

    Raises:
        SsrfBlockedError: DNS failure or private resolution
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SsrfBlockedError(f"DNS resolution failed: {exc}") from exc

    ips: List[str] = []
    for info in infos:
        addr = info[4][0]
        if is_private_ip(addr):
            raise SsrfBlockedError("Resolved to private IP")
        if addr not in ips:
            ips.append(addr)
    if not ips:
        raise SsrfBlockedError("DNS resolution returned no addresses")
    return ips


async def _read_exactly_limited(
    reader: asyncio.StreamReader,
    n: int,
    *,
    total_so_far: int,
    max_bytes: int,
) -> bytes:
    """Read exactly n bytes, enforcing a global body size cap."""
    if total_so_far + n > max_bytes:
        raise SsrfBlockedError("Response too large")
    try:
        data = await reader.readexactly(n)
    except asyncio.IncompleteReadError as exc:
        data = exc.partial
    if total_so_far + len(data) > max_bytes:
        raise SsrfBlockedError("Response too large")
    return data


async def _read_until_headers(reader: asyncio.StreamReader) -> bytes:
    """Read HTTP headers up to CRLFCRLF with a hard size cap."""
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > _MAX_HEADER_BYTES:
            raise SsrfBlockedError("Response headers too large")
    return bytes(buf)


async def _read_chunked_body(
    reader: asyncio.StreamReader,
    *,
    max_bytes: int,
) -> bytes:
    """Decode a chunked transfer body with a size cap."""
    out = bytearray()
    while True:
        size_line = await reader.readline()
        if not size_line:
            break
        try:
            size = int(size_line.split(b";", 1)[0].strip(), 16)
        except ValueError as exc:
            raise SsrfBlockedError("Invalid chunked response") from exc
        if size == 0:
            # Trailer headers until blank line
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"", b"\n"):
                    break
            break
        chunk = await _read_exactly_limited(
            reader, size, total_so_far=len(out), max_bytes=max_bytes
        )
        out.extend(chunk)
        # Consume trailing CRLF
        await reader.readexactly(2)
        if len(out) > max_bytes:
            raise SsrfBlockedError("Response too large")
    return bytes(out)


async def _pinned_https_request(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = 15.0,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Tuple[int, bytes]:
    """
    HTTPS request pinned to a pre-validated DNS IP (SSRF-safe).

    Connects to the resolved IP while using the original hostname for SNI and
    the Host header, so DNS rebinding after validation cannot redirect the
    TCP connection to a private address.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise SsrfBlockedError("URL missing hostname")
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    ips = await _resolve_public_ips(host)
    ip = ips[0]

    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Connection": "close",
        "Host": host,
    }
    if headers:
        for key, value in headers.items():
            if key.lower() == "host":
                continue
            req_headers[key] = value
    if body is not None:
        req_headers.setdefault("Content-Length", str(len(body)))

    header_lines = [f"{method.upper()} {path} HTTP/1.1"]
    for key, value in req_headers.items():
        header_lines.append(f"{key}: {value}")
    request_bytes = ("\r\n".join(header_lines) + "\r\n\r\n").encode("utf-8")
    if body:
        request_bytes += body

    ctx = ssl.create_default_context()
    try:
        connect_coro = asyncio.open_connection(
            ip,
            port,
            ssl=ctx,
            server_hostname=host,
        )
        reader, writer = await asyncio.wait_for(connect_coro, timeout=timeout)
    except SsrfBlockedError:
        raise
    except Exception as exc:
        raise SsrfBlockedError(f"Connection failed: {exc}") from exc

    try:
        writer.write(request_bytes)
        await asyncio.wait_for(writer.drain(), timeout=timeout)

        raw_headers = await asyncio.wait_for(
            _read_until_headers(reader), timeout=timeout
        )
        if b"\r\n\r\n" not in raw_headers:
            raise SsrfBlockedError("Incomplete HTTP response")
        header_blob, remainder = raw_headers.split(b"\r\n\r\n", 1)
        header_text = header_blob.decode("latin-1", errors="replace")
        lines = header_text.split("\r\n")
        if not lines:
            raise SsrfBlockedError("Empty HTTP response")
        status_parts = lines[0].split(" ", 2)
        try:
            status_code = int(status_parts[1])
        except (IndexError, ValueError) as exc:
            raise SsrfBlockedError("Invalid HTTP status line") from exc

        header_map: Dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            header_map[k.strip().lower()] = v.strip()

        if status_code in (301, 302, 303, 307, 308):
            raise SsrfBlockedError("Redirects are not followed for SSRF safety")

        te = header_map.get("transfer-encoding", "").lower()
        body_out = bytearray(remainder)

        if "chunked" in te:
            # Remainder may already include the start of the chunk stream
            if remainder:
                # Put remainder back by concatenating with further reads via a buffer
                # Simplest: prepend by using a custom approach — read more into buffer
                extra = await _read_chunked_body_from_buffer(
                    reader, initial=remainder, max_bytes=max_bytes
                )
                body_out = bytearray(extra)
            else:
                body_out = bytearray(
                    await _read_chunked_body(reader, max_bytes=max_bytes)
                )
        elif "content-length" in header_map:
            try:
                length = int(header_map["content-length"])
            except ValueError as exc:
                raise SsrfBlockedError("Invalid Content-Length") from exc
            if length < 0 or length > max_bytes:
                raise SsrfBlockedError("Response too large")
            while len(body_out) < length:
                chunk = await reader.read(min(65536, length - len(body_out)))
                if not chunk:
                    break
                body_out.extend(chunk)
                if len(body_out) > max_bytes:
                    raise SsrfBlockedError("Response too large")
            body_out = body_out[:length]
        else:
            # Read until EOF with size cap
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                body_out.extend(chunk)
                if len(body_out) > max_bytes:
                    raise SsrfBlockedError("Response too large")

        return status_code, bytes(body_out)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            logger.debug("Failed closing SSRF HTTP connection", exc_info=True)


async def _read_chunked_body_from_buffer(
    reader: asyncio.StreamReader,
    *,
    initial: bytes,
    max_bytes: int,
) -> bytes:
    """Decode chunked body when some bytes were already read with headers."""
    buf = bytearray(initial)
    out = bytearray()

    async def _ensure(n: int) -> None:
        while len(buf) < n:
            chunk = await reader.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) + len(out) > max_bytes + _MAX_HEADER_BYTES:
                raise SsrfBlockedError("Response too large")

    while True:
        # Need a full size line
        while b"\r\n" not in buf:
            chunk = await reader.read(1024)
            if not chunk:
                raise SsrfBlockedError("Incomplete chunked response")
            buf.extend(chunk)
        idx = buf.find(b"\r\n")
        size_line = bytes(buf[:idx])
        del buf[: idx + 2]
        try:
            size = int(size_line.split(b";", 1)[0].strip(), 16)
        except ValueError as exc:
            raise SsrfBlockedError("Invalid chunked response") from exc
        if size == 0:
            # Consume trailers
            while True:
                while b"\r\n" not in buf:
                    chunk = await reader.read(1024)
                    if not chunk:
                        return bytes(out)
                    buf.extend(chunk)
                tidx = buf.find(b"\r\n")
                line = bytes(buf[:tidx])
                del buf[: tidx + 2]
                if line == b"":
                    break
            break
        await _ensure(size + 2)
        if len(buf) < size + 2:
            raise SsrfBlockedError("Incomplete chunked response")
        out.extend(buf[:size])
        del buf[: size + 2]
        if len(out) > max_bytes:
            raise SsrfBlockedError("Response too large")
    return bytes(out)


def _timeout_seconds(timeout: Optional[httpx.Timeout]) -> float:
    """Extract a scalar timeout seconds value from httpx.Timeout."""
    if timeout is None:
        return 15.0
    # httpx.Timeout stores read/connect; prefer read then pool then connect
    for attr in ("read", "pool", "write", "connect"):
        val = getattr(timeout, attr, None)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    return 15.0


async def fetch_json(
    url: str,
    *,
    allowed_hosts: Optional[set[str]] = None,
    allow_careers_heuristic: bool = False,
    method: str = "GET",
    json_body: Optional[Dict[str, Any]] = None,
    timeout: Optional[httpx.Timeout] = None,
) -> Any:
    """
    Fetch JSON from an allowlisted HTTPS URL with SSRF guards.

    Redirects are rejected. Connections are pinned to validated DNS IPs.
    """
    safe_url = _validate_url_for_fetch(
        url,
        allowed_hosts=allowed_hosts,
        allow_careers_heuristic=allow_careers_heuristic,
    )
    headers = {"Accept": "application/json"}
    body: Optional[bytes] = None
    if method.upper() == "POST":
        body = json.dumps(json_body or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    status, content = await _pinned_https_request(
        safe_url,
        method=method.upper(),
        headers=headers,
        body=body,
        timeout=_timeout_seconds(timeout or DEFAULT_TIMEOUT),
    )
    if status >= 400:
        raise SsrfBlockedError(f"Upstream HTTP {status}")
    try:
        return json.loads(content.decode("utf-8"))
    except Exception as exc:
        raise SsrfBlockedError(f"Invalid JSON response: {exc}") from exc


async def fetch_text(
    url: str,
    *,
    allowed_hosts: Optional[set[str]] = None,
    allow_careers_heuristic: bool = False,
    timeout: Optional[httpx.Timeout] = None,
) -> str:
    """Fetch text/HTML from an allowlisted HTTPS URL with SSRF guards."""
    safe_url = _validate_url_for_fetch(
        url,
        allowed_hosts=allowed_hosts,
        allow_careers_heuristic=allow_careers_heuristic,
    )
    status, content = await _pinned_https_request(
        safe_url,
        method="GET",
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=_timeout_seconds(timeout or DEFAULT_TIMEOUT),
    )
    if status >= 400:
        raise SsrfBlockedError(f"Upstream HTTP {status}")
    return content.decode("utf-8", errors="replace")


async def fetch_json_safe(
    url: str,
    **kwargs: Any,
) -> Optional[Any]:
    """Like fetch_json but returns None on failure (logs at debug)."""
    try:
        return await fetch_json(url, **kwargs)
    except Exception as exc:
        logger.debug(
            "Job finder fetch_json failed for %s: %s",
            sanitize_log_value(url[:120]),
            sanitize_log_value(str(exc)),
            exc_info=True,
        )
        return None

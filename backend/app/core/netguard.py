"""SSRF guard for admin-configured provider URLs (GitLab / Elasticsearch).

This is a self-hosted tool whose whole job is to reach *internal* infrastructure,
so private/RFC1918 ranges are intentionally allowed. We only reject the genuinely
dangerous targets: loopback and link-local — the latter covers the cloud metadata
endpoint (169.254.169.254 / fd00:ec2::254) used in classic SSRF credential theft.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import get_settings

settings = get_settings()


class UnsafeUrlError(ValueError):
    """Raised when a configured URL resolves to a blocked address."""


def _blocked(ip: ipaddress._BaseAddress) -> str | None:
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:  # 169.254.0.0/16 + fe80::/10 (incl. cloud metadata)
        return "link-local / cloud-metadata address"
    if ip.is_unspecified:
        return "unspecified address (0.0.0.0/::)"
    return None


def assert_safe_url(url: str) -> None:
    """Validate an outbound base URL. Raises UnsafeUrlError if it must be blocked.

    Resolves the hostname and checks every returned address, so a name that points
    at 127.0.0.1 / 169.254.169.254 is caught even if it isn't a literal IP.
    """
    if not settings.mcp_block_link_local:
        return
    parts = urlsplit(url if "://" in url else f"//{url}", scheme="https")
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"unsupported URL scheme: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL has no host")

    # Literal IP?
    try:
        ip = ipaddress.ip_address(host)
        reason = _blocked(ip)
        if reason:
            raise UnsafeUrlError(f"{host} is a {reason}")
        return
    except ValueError:
        pass  # it's a hostname — resolve it

    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"could not resolve host {host!r}: {exc}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _blocked(ip)
        if reason:
            raise UnsafeUrlError(f"{host} resolves to {addr} ({reason})")

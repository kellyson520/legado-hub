"""Shared server-side URL safety policy.

The policy is intentionally dependency-free so application tools and HTTP
adapters can apply the same checks without importing one another.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from urllib.parse import urlparse


_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def public_http_url_error(value: object) -> str | None:
    """Return ``invalid`` or ``unsafe`` for URLs that must not be fetched."""
    if not isinstance(value, str) or not value.strip():
        return "invalid"
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "invalid"
    if parsed.username is not None or parsed.password is not None:
        return "unsafe"
    try:
        port = parsed.port
    except ValueError:
        return "unsafe"
    if port is not None and not 1 <= port <= 65535:
        return "unsafe"
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith((".local", ".localhost", ".internal")):
        return "unsafe"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return "unsafe"
    return None


def is_public_ip(value: object) -> bool:
    """Return whether a resolved IP address is safe for outbound fetching."""
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def http_origin(value: object) -> tuple[str, str, int] | None:
    """Return a normalized HTTP origin for redirect policy comparisons."""
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def headers_for_redirect(
    headers: Mapping[str, object],
    current_url: str,
    next_url: str,
) -> dict[str, object]:
    """Drop credentials when a redirect changes origin."""
    if http_origin(current_url) == http_origin(next_url):
        return dict(headers)
    return {
        key: value
        for key, value in headers.items()
        if str(key).lower() not in {"authorization", "proxy-authorization", "cookie", "host"}
    }

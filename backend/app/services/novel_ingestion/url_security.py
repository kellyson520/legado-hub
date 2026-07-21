from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx


class NovelUrlSecurityError(ValueError):
    code = "unsafe_url"


@dataclass(frozen=True)
class UrlFetchResult:
    url: str
    content: bytes
    media_type: str
    status_code: int
    headers: dict[str, str]


class NovelUrlPolicy:
    """Validate and fetch public HTTP(S) documents with redirect re-checks."""

    BLOCKED_HOSTNAMES = {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google.internal.",
        "169.254.169.254",
    }

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        max_redirects: int = 3,
        max_bytes: int = 16 * 1024 * 1024,
        allowed_media_types: set[str] | None = None,
    ):
        self._client = client
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self.allowed_media_types = allowed_media_types or {
            "text/plain",
            "text/markdown",
            "text/html",
            "application/xhtml+xml",
            "application/epub+zip",
            "application/zip",
        }

    def validate(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise NovelUrlSecurityError("only HTTP and HTTPS URLs are allowed")
        if parsed.username or parsed.password:
            raise NovelUrlSecurityError("URL credentials are not allowed")
        if parsed.fragment:
            raise NovelUrlSecurityError("URL fragments are not allowed")
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if not hostname or hostname in self.BLOCKED_HOSTNAMES:
            raise NovelUrlSecurityError("URL hostname is not allowed")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None:
            self._validate_ip(address)
        else:
            self._validate_hostname(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        return parsed.geturl()

    async def fetch(self, url: str) -> UrlFetchResult:
        current = self.validate(url)
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        try:
            for redirect_count in range(self.max_redirects + 1):
                response = await client.get(current, follow_redirects=False, timeout=self.timeout)
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        raise NovelUrlSecurityError("redirect response has no location")
                    if redirect_count >= self.max_redirects:
                        raise NovelUrlSecurityError("too many redirects")
                    current = self.validate(urljoin(current, location))
                    continue
                if response.status_code >= 400:
                    raise NovelUrlSecurityError(f"remote document returned HTTP {response.status_code}")
                content = response.content
                if len(content) > self.max_bytes:
                    raise NovelUrlSecurityError("remote document exceeds the size limit")
                media_type = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                if media_type and media_type not in self.allowed_media_types:
                    raise NovelUrlSecurityError(f"remote media type is not allowed: {media_type}")
                return UrlFetchResult(current, content, media_type, response.status_code, dict(response.headers))
            raise NovelUrlSecurityError("redirect policy failed")
        finally:
            if close_client:
                await client.aclose()

    def _validate_hostname(self, hostname: str, port: int) -> None:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise NovelUrlSecurityError("unable to resolve URL hostname") from exc
        if not addresses:
            raise NovelUrlSecurityError("URL hostname has no address")
        for address in addresses:
            self._validate_ip(ipaddress.ip_address(address))

    @staticmethod
    def _validate_ip(address: ipaddress._BaseAddress) -> None:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            raise NovelUrlSecurityError("private or special network addresses are not allowed")

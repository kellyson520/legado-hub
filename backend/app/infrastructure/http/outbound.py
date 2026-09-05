from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Mapping
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.application.ports.http import OutboundHttpResponse
from app.core.url_safety import headers_for_redirect, http_origin, is_public_ip, public_http_url_error
from app.domain.entities.event_delivery import EventDelivery


AddressResolver = Callable[..., list[tuple]]
_MAX_REDIRECTS = 5


def _resolve_public_ip(
    url: str,
    *,
    resolver: AddressResolver = socket.getaddrinfo,
) -> tuple[str | None, str | None]:
    """Validate a URL and return the public address used for the connection."""
    error = public_http_url_error(url)
    if error is not None:
        return error, None

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "invalid", None

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return (None, hostname) if is_public_ip(hostname) else ("unsafe", None)

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        records = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        return "unresolvable", None

    addresses: list[str] = []
    for record in records:
        if len(record) <= 4 or not record[4]:
            continue
        address = str(record[4][0])
        if address not in addresses:
            addresses.append(address)
    if not addresses or any(not is_public_ip(address) for address in addresses):
        return "unsafe", None
    return None, addresses[0]


def _resolved_public_url_error(
    url: str,
    *,
    resolver: AddressResolver = socket.getaddrinfo,
) -> str | None:
    """Compatibility helper returning only the URL validation error."""
    error, _ = _resolve_public_ip(url, resolver=resolver)
    return error


def _pinned_url(url: str, address: str) -> str:
    parsed = urlparse(url)
    host = f"[{address}]" if ":" in address else address
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=host))


def _logical_host(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return hostname


def _network_request(request: httpx.Request, address: str) -> httpx.Request:
    """Build a one-shot request to the pinned address without changing its SNI."""
    headers = httpx.Headers(request.headers)
    if "host" not in headers:
        headers["Host"] = _logical_host(str(request.url))
    extensions = dict(request.extensions)
    if request.url.scheme in {"https", "wss"}:
        extensions["sni_hostname"] = request.url.host
    return httpx.Request(
        request.method,
        _pinned_url(str(request.url), address),
        headers=headers,
        stream=request.stream,
        extensions=extensions,
    )


class _PinnedSyncTransport(httpx.HTTPTransport):
    """HTTPX transport that connects to the validated address, not a hostname."""

    def __init__(
        self,
        *,
        verify: httpx.VerifyTypes = True,
        trust_env: bool = True,
        resolver: AddressResolver = socket.getaddrinfo,
    ):
        super().__init__(verify=verify, trust_env=trust_env)
        self._resolver = resolver

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        error, address = _resolve_public_ip(str(request.url), resolver=self._resolver)
        if error is not None or address is None:
            raise ValueError(f"unsafe outbound URL: {error or 'unresolvable'}")
        return super().handle_request(_network_request(request, address))


class _PinnedAsyncTransport(httpx.AsyncHTTPTransport):
    """Async counterpart of :class:`_PinnedSyncTransport`."""

    def __init__(
        self,
        *,
        verify: httpx.VerifyTypes = True,
        trust_env: bool = True,
        resolver: AddressResolver = socket.getaddrinfo,
    ):
        super().__init__(verify=verify, trust_env=trust_env)
        self._resolver = resolver

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        error, address = _resolve_public_ip(str(request.url), resolver=self._resolver)
        if error is not None or address is None:
            raise ValueError(f"unsafe outbound URL: {error or 'unresolvable'}")
        return await super().handle_async_request(_network_request(request, address))


def _redirect_request(
    method: str,
    kwargs: Mapping[str, object],
    status_code: int,
    *,
    current_url: str,
    next_url: str,
) -> tuple[str, dict]:
    next_kwargs = dict(kwargs)
    next_method = method
    if status_code in {301, 302, 303} and method.upper() not in {"GET", "HEAD"}:
        next_method = "GET"
        for key in ("content", "data", "files", "json"):
            next_kwargs.pop(key, None)
    next_kwargs.pop("params", None)
    origin_changed = http_origin(current_url) != http_origin(next_url)
    if isinstance(next_kwargs.get("headers"), Mapping):
        redirected_headers = headers_for_redirect(
            next_kwargs["headers"],
            current_url,
            next_url,
        )
        if redirected_headers:
            next_kwargs["headers"] = redirected_headers
        else:
            next_kwargs.pop("headers", None)
    # ``headers_for_redirect`` handles header credentials; remove auxiliary
    # credential providers when the origin changes as well, even when the
    # caller did not provide a headers mapping.
    if origin_changed:
        for key in ("auth", "cookies"):
            next_kwargs.pop(key, None)
    return next_method, next_kwargs


def _close_sync_response(response: object) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


async def _close_async_response(response: object) -> None:
    close = getattr(response, "aclose", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            await result


class SafeSyncHttpClient:
    """Synchronous HTTPX adapter with one outbound URL policy."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        follow_redirects: bool = False,
        verify: httpx.VerifyTypes = True,
        trust_env: bool = True,
        resolver: AddressResolver = socket.getaddrinfo,
    ):
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._verify = verify
        self._trust_env = trust_env
        self._resolver = resolver
        self._client: httpx.Client | None = None

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            follow_redirects=False,
            timeout=self._timeout,
            transport=_PinnedSyncTransport(
                verify=self._verify,
                trust_env=self._trust_env,
                resolver=self._resolver,
            ),
        )

    def __enter__(self) -> "SafeSyncHttpClient":
        self._client = self._new_client()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None

    def request(self, method: str, url: str, **kwargs):
        self._ensure_safe_url(url)
        follow_redirects = bool(kwargs.pop("follow_redirects", self._follow_redirects))
        client = self._client or self._new_client()
        owns_client = self._client is None
        current_method = method
        current_url = url
        current_kwargs = dict(kwargs)
        try:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                self._ensure_safe_url(current_url)
                response = client.request(current_method, current_url, **current_kwargs)
                location = getattr(response, "headers", {}).get("location")
                status_code = int(getattr(response, "status_code", 0) or 0)
                if not follow_redirects or not location or not 300 <= status_code < 400:
                    return response
                if redirect_count >= _MAX_REDIRECTS:
                    _close_sync_response(response)
                    raise ValueError("too many redirects")
                next_url = urljoin(current_url, str(location))
                _close_sync_response(response)
                current_method, current_kwargs = _redirect_request(
                    current_method,
                    current_kwargs,
                    status_code,
                    current_url=current_url,
                    next_url=next_url,
                )
                current_url = next_url
        finally:
            if owns_client:
                client.close()

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def _ensure_safe_url(self, url: str) -> None:
        error = _resolved_public_url_error(url, resolver=self._resolver)
        if error is not None:
            raise ValueError(f"unsafe outbound URL: {error}")


class SafeAsyncHttpClient:
    """Asynchronous HTTPX adapter sharing the same URL policy."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        follow_redirects: bool = False,
        verify: httpx.VerifyTypes = True,
        trust_env: bool = True,
        resolver: AddressResolver = socket.getaddrinfo,
    ):
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._verify = verify
        self._trust_env = trust_env
        self._resolver = resolver
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            transport=_PinnedAsyncTransport(
                verify=verify,
                trust_env=trust_env,
                resolver=resolver,
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, **kwargs):
        self._ensure_safe_url(url)
        follow_redirects = bool(kwargs.pop("follow_redirects", self._follow_redirects))
        current_method = method
        current_url = url
        current_kwargs = dict(kwargs)
        for redirect_count in range(_MAX_REDIRECTS + 1):
            self._ensure_safe_url(current_url)
            response = await self._client.request(current_method, current_url, **current_kwargs)
            location = getattr(response, "headers", {}).get("location")
            status_code = int(getattr(response, "status_code", 0) or 0)
            if not follow_redirects or not location or not 300 <= status_code < 400:
                return response
            if redirect_count >= _MAX_REDIRECTS:
                await _close_async_response(response)
                raise ValueError("too many redirects")
            next_url = urljoin(current_url, str(location))
            await _close_async_response(response)
            current_method, current_kwargs = _redirect_request(
                current_method,
                current_kwargs,
                status_code,
                current_url=current_url,
                next_url=next_url,
            )
            current_url = next_url

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    def _ensure_safe_url(self, url: str) -> None:
        error = _resolved_public_url_error(url, resolver=self._resolver)
        if error is not None:
            raise ValueError(f"unsafe outbound URL: {error}")


class SafeWebhookSender:
    """Concrete sender injected into the event delivery application service."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        verify: httpx.VerifyTypes = True,
        resolver: AddressResolver = socket.getaddrinfo,
    ):
        self._timeout = timeout
        self._verify = verify
        self._resolver = resolver

    def __call__(self, delivery: EventDelivery) -> OutboundHttpResponse:
        with SafeSyncHttpClient(
            timeout=self._timeout,
            follow_redirects=False,
            verify=self._verify,
            resolver=self._resolver,
        ) as client:
            response = client.post(
                delivery.target_url,
                content=delivery.body.encode("utf-8"),
                headers=dict(delivery.headers),
            )
        return OutboundHttpResponse(status_code=response.status_code, text=response.text)

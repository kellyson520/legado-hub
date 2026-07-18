from __future__ import annotations

import asyncio
import base64
import json
import threading
from typing import Any


class RuntimeBridge:
    """Synchronous bridge used by the JVM stdio loop to call platform HTTP."""

    def __init__(self, http_client, *, cache: dict[str, Any] | None = None, timeout: float = 15.0):
        self.http_client = http_client
        self.cache = cache if cache is not None else {}
        self.timeout = timeout
        self._cache_lock = threading.RLock()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        url = str(request.get("url", "") or "")
        if not url:
            return {"status": 400, "text": "empty url", "headers": {}, "error_code": "EMPTY_URL"}

        method = str(request.get("method", "GET") or "GET").upper()
        headers = {str(k): str(v) for k, v in (request.get("headers") or {}).items()}
        origin = str(request.get("origin", "") or "")
        if origin and not any(key.lower() == "origin" for key in headers):
            headers["Origin"] = origin
        body = request.get("body")
        timeout = float(request.get("timeout_ms", self.timeout * 1000) or self.timeout * 1000) / 1000
        follow_redirects = bool(request.get("follow_redirects", True))
        charset = str(request.get("charset", "") or "") or None
        content_type = str(request.get("content_type", "") or "") or None
        proxy = str(request.get("proxy", "") or "") or None
        dns_ip = str(request.get("dns_ip", "") or "") or None
        server_id = request.get("server_id")
        accept_bytes = bool(request.get("accept_bytes", False))
        result: list[dict[str, Any]] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(asyncio.wait_for(
                    self._request(
                        method,
                        url,
                        headers,
                        body,
                        timeout,
                        follow_redirects,
                        charset=charset,
                        content_type=content_type,
                        proxy=proxy,
                        dns_ip=dns_ip,
                        server_id=server_id,
                        accept_bytes=accept_bytes,
                    ),
                    timeout=timeout,
                )))
            except BaseException as exc:  # noqa: BLE001 - converted to a stable bridge error below
                failure.append(exc)

        thread = threading.Thread(target=runner, name="legado-runtime-bridge", daemon=True)
        thread.start()
        thread.join(timeout=max(timeout, 0.01) + 0.05)
        if thread.is_alive():
            return {"status": 599, "text": "bridge request timed out", "headers": {}, "error_code": "BRIDGE_TIMEOUT"}
        if failure:
            if isinstance(failure[0], (asyncio.TimeoutError, TimeoutError)):
                return {"status": 599, "text": "bridge request timed out", "headers": {}, "error_code": "BRIDGE_TIMEOUT"}
            return {"status": 599, "text": str(failure[0]), "headers": {}, "error_code": "BRIDGE_ERROR"}
        return result[0] if result else {"status": 599, "text": "bridge returned no response", "headers": {}, "error_code": "BRIDGE_ERROR"}

    def handle_cache(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = str(request.get("op", "get") or "get").lower()
        scope = str(request.get("scope", "default") or "default")
        key = str(request.get("key", "") or "")
        if not key:
            return {"found": False, "error_code": "EMPTY_CACHE_KEY"}
        cache_key = f"{scope}\x00{key}"
        with self._cache_lock:
            if operation == "get":
                if cache_key not in self.cache:
                    return {"found": False}
                return {"found": True, "value": self.cache[cache_key]}
            if operation == "put":
                self.cache[cache_key] = request.get("value")
                return {"found": True}
            if operation == "delete":
                self.cache.pop(cache_key, None)
                return {"found": False}
            return {"found": False, "error_code": "UNSUPPORTED_CACHE_OPERATION"}

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
        timeout: float,
        follow_redirects: bool,
        *,
        charset: str | None = None,
        content_type: str | None = None,
        proxy: str | None = None,
        dns_ip: str | None = None,
        server_id: Any = None,
        accept_bytes: bool = False,
    ) -> dict[str, Any]:
        if method == "POST":
            if content_type and content_type.lower().startswith("multipart/"):
                headers = {
                    key: value
                    for key, value in headers.items()
                    if key.lower() != "content-type"
                }
                response = await self._call_http(
                    "post",
                    url,
                    data=self._multipart_data(body),
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=follow_redirects,
                    encoding=charset,
                    proxy=proxy,
                    dns_ip=dns_ip,
                )
            elif isinstance(body, (dict, list)):
                response = await self._call_http("post", url, json_data=body, headers=headers, timeout=timeout, allow_redirects=follow_redirects, encoding=charset, proxy=proxy, dns_ip=dns_ip)
            else:
                response = await self._call_http("post", url, data=body, headers=headers, timeout=timeout, allow_redirects=follow_redirects, encoding=charset, proxy=proxy, dns_ip=dns_ip)
        elif method == "HEAD":
            response = await self._call_http("head", url, headers=headers, timeout=timeout, allow_redirects=follow_redirects, encoding=charset, proxy=proxy, dns_ip=dns_ip)
        else:
            response = await self._call_http("get", url, headers=headers, timeout=timeout, allow_redirects=follow_redirects, encoding=charset, proxy=proxy, dns_ip=dns_ip)
        result = {
            "status": response.status,
            "text": response.text,
            "body": response.text,
            "headers": dict(response.headers),
            "final_url": response.url,
            "charset": getattr(response, "charset", None),
            "elapsed_ms": response.elapsed_ms,
            "is_json": response.is_json,
            "is_html": response.is_html,
            "error_code": "HTTP_ERROR" if not response.success else None,
        }
        response_content = getattr(response, "content", b"") or b""
        if isinstance(response_content, str):
            response_content = response_content.encode("utf-8")
        if accept_bytes and response_content:
            result["body_base64"] = base64.b64encode(response_content).decode("ascii")
        if dns_ip:
            result["dns_ip"] = dns_ip
        if server_id is not None:
            result["server_id"] = server_id
        return result

    @staticmethod
    def _multipart_data(body: Any) -> Any:
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (TypeError, ValueError):
                return body
        if not isinstance(body, dict):
            return body
        try:
            import aiohttp

            form = aiohttp.FormData()
            for key, value in body.items():
                if isinstance(value, dict):
                    file_value = value.get("file", "")
                    if isinstance(file_value, list) and all(isinstance(item, int) and 0 <= item <= 255 for item in file_value):
                        file_value = bytes(file_value)
                    form.add_field(
                        str(key),
                        file_value,
                        filename=str(value.get("fileName", "upload")),
                        content_type=str(value.get("contentType", "application/octet-stream")),
                    )
                else:
                    form.add_field(str(key), str(value))
            return form
        except ImportError:
            return body

    async def _call_http(self, operation: str, url: str, **kwargs: Any):
        method = getattr(self.http_client, operation, None)
        if method is None and operation == "head":
            method = getattr(self.http_client, "get")
        # Lightweight test clients and older adapters may not expose every
        # per-request transport keyword; the outer wait_for still enforces it.
        while True:
            try:
                return await method(url, **kwargs)
            except TypeError as exc:
                message = str(exc)
                unsupported = [
                    name for name in ("timeout", "allow_redirects", "encoding", "proxy", "dns_ip")
                    if name in kwargs and name in message
                ]
                if not unsupported:
                    raise
                for name in unsupported:
                    kwargs.pop(name, None)

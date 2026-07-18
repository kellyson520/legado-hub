from __future__ import annotations

import asyncio
import threading
from typing import Any


class RuntimeBridge:
    """Synchronous bridge used by the JVM stdio loop to call platform HTTP."""

    def __init__(self, http_client, *, cache: dict[str, Any] | None = None, timeout: float = 15.0):
        self.http_client = http_client
        self.cache = cache if cache is not None else {}
        self.timeout = timeout

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        url = str(request.get("url", "") or "")
        if not url:
            return {"status": 400, "text": "empty url", "headers": {}, "error_code": "EMPTY_URL"}

        method = str(request.get("method", "GET") or "GET").upper()
        headers = {str(k): str(v) for k, v in (request.get("headers") or {}).items()}
        body = request.get("body")
        timeout = float(request.get("timeout_ms", self.timeout * 1000) or self.timeout * 1000) / 1000
        follow_redirects = bool(request.get("follow_redirects", True))
        result: list[dict[str, Any]] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(asyncio.wait_for(self._request(method, url, headers, body, timeout, follow_redirects), timeout=timeout)))
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
    ) -> dict[str, Any]:
        if method == "POST":
            if isinstance(body, (dict, list)):
                response = await self._call_http("post", url, json_data=body, headers=headers, timeout=timeout, allow_redirects=follow_redirects)
            else:
                response = await self._call_http("post", url, data=body, headers=headers, timeout=timeout, allow_redirects=follow_redirects)
        elif method == "HEAD":
            response = await self._call_http("head", url, headers=headers, timeout=timeout, allow_redirects=follow_redirects)
        else:
            response = await self._call_http("get", url, headers=headers, timeout=timeout, allow_redirects=follow_redirects)
        return {
            "status": response.status,
            "text": response.text,
            "body": response.text,
            "headers": dict(response.headers),
            "final_url": response.url,
            "elapsed_ms": response.elapsed_ms,
            "is_json": response.is_json,
            "is_html": response.is_html,
            "error_code": "HTTP_ERROR" if not response.success else None,
        }

    async def _call_http(self, operation: str, url: str, **kwargs: Any):
        method = getattr(self.http_client, operation, None)
        if method is None and operation == "head":
            method = getattr(self.http_client, "get")
        try:
            return await method(url, **kwargs)
        except TypeError as exc:
            # Lightweight test clients and older adapters may not expose the
            # per-request timeout keyword; the outer wait_for still enforces it.
            if "timeout" not in str(exc):
                if "allow_redirects" not in str(exc):
                    raise
            kwargs.pop("timeout", None)
            kwargs.pop("allow_redirects", None)
            return await method(url, **kwargs)

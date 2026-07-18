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
        result: list[dict[str, Any]] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(asyncio.wait_for(self._request(method, url, headers, body), timeout=timeout)))
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

    async def _request(self, method: str, url: str, headers: dict[str, str], body: Any) -> dict[str, Any]:
        if method == "POST":
            if isinstance(body, (dict, list)):
                response = await self.http_client.post(url, json_data=body, headers=headers)
            else:
                response = await self.http_client.post(url, data=body, headers=headers)
        else:
            response = await self.http_client.get(url, headers=headers)
        return {
            "status": response.status,
            "text": response.text,
            "headers": dict(response.headers),
            "final_url": response.url,
            "elapsed_ms": response.elapsed_ms,
            "is_json": response.is_json,
            "is_html": response.is_html,
            "error_code": "HTTP_ERROR" if not response.success else None,
        }

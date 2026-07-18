from __future__ import annotations

from typing import Any

from .native_runtime_client import NativeRuntimeClient


class RuntimeProcessManager:
    """Lazily probes and closes the in-container native runtime client."""

    def __init__(self, client: NativeRuntimeClient | Any | None = None):
        self.client = client or NativeRuntimeClient()
        self._last_status: dict[str, Any] = {
            "state": "not_started",
            "engine": "",
            "protocol_version": 1,
            "restart_count": 0,
        }

    def health(self) -> dict[str, Any]:
        result = self.client.ping()
        trace = result.trace if isinstance(result.trace, dict) else {}
        if result.success:
            self._last_status = {
                "state": "ready",
                "engine": trace.get("engine", ""),
                "protocol_version": 1,
                "restart_count": int(getattr(self.client, "restart_count", 0)),
                "error_code": None,
            }
        else:
            self._last_status = {
                "state": "unavailable",
                "engine": trace.get("engine", ""),
                "protocol_version": 1,
                "restart_count": int(getattr(self.client, "restart_count", 0)),
                "error_code": result.error_code,
                "error": result.error,
            }
        return dict(self._last_status)

    def status(self) -> dict[str, Any]:
        return dict(self._last_status)

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

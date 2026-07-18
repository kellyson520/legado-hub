from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeResult:
    success: bool
    value: Any = None
    value_type: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RuntimeResult":
        error = payload.get("error")
        if isinstance(error, dict):
            error_code = error.get("code")
            error_message = error.get("message")
        else:
            error_code = payload.get("error_code")
            error_message = error if isinstance(error, str) else None
        return cls(
            success=bool(payload.get("success")),
            value=payload.get("value"),
            value_type=payload.get("value_type"),
            trace=payload.get("trace") if isinstance(payload.get("trace"), dict) else {},
            error_code=error_code,
            error=error_message,
        )


@dataclass
class RuntimeCapabilities:
    engine: str = ""
    engine_commit: str = ""
    protocol_version: int = 1
    operations: list[str] = field(default_factory=list)


class NativeRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

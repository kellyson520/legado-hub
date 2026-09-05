from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from pydantic import ValidationError

from .models import HarnessError, OpenHarnessRequest, OpenHarnessResponse, OpenHarnessResponseBody


OPENHARNESS_PROTOCOL_VERSION = "1.0.0"
SUPPORTED_CAPABILITIES = {
    "openharness.ui.approval": True,
    "openharness.ui.rich_cards": False,
    "openharness.actions.parallel": False,
}
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


class OpenHarnessProtocolError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.correlation_id = correlation_id
        self.retryable = retryable


def _request_ids(payload: object) -> tuple[str | None, str | None]:
    if not isinstance(payload, Mapping):
        return None, None
    request_id = payload.get("request_id")
    correlation_id = payload.get("correlation_id")
    return (
        request_id if isinstance(request_id, str) else None,
        correlation_id if isinstance(correlation_id, str) else None,
    )


def _major_version(version: object) -> str | None:
    if not isinstance(version, str):
        return None
    parts = version.split(".", 1)
    return parts[0] if parts[0].isdigit() else None


def parse_request(payload: object) -> OpenHarnessRequest:
    request_id, correlation_id = _request_ids(payload)
    if not isinstance(payload, Mapping):
        raise OpenHarnessProtocolError(
            "invalid_request",
            "OpenHarness request must be a JSON object.",
            request_id=request_id,
            correlation_id=correlation_id,
        )

    version = payload.get("protocol_version")
    if not isinstance(version, str) or not _SEMVER_RE.fullmatch(version) or _major_version(version) != "1":
        raise OpenHarnessProtocolError(
            "protocol_version_unsupported",
            "The requested OpenHarness protocol version is not supported.",
            request_id=request_id,
            correlation_id=correlation_id,
        )

    try:
        request = OpenHarnessRequest.model_validate(payload)
    except ValidationError as exc:
        raise OpenHarnessProtocolError(
            "invalid_request",
            "The OpenHarness request does not match the supported schema.",
            request_id=request_id,
            correlation_id=correlation_id,
        ) from exc
    return request


def error_response(
    *,
    request_id: str | None,
    correlation_id: str | None,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> OpenHarnessResponse:
    return OpenHarnessResponse(
        request_id=request_id,
        correlation_id=correlation_id,
        supported_capabilities=dict(SUPPORTED_CAPABILITIES),
        response=OpenHarnessResponseBody(
            status="error",
            error=HarnessError(
                code=code,
                message=message,
                retryable=retryable,
                details=details,
            ),
        ),
    )

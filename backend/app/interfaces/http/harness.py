from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from app.core.permissions import Permission
from app.infrastructure.harness.openharness.protocol import (
    OpenHarnessProtocolError,
    error_response,
    parse_request,
)
from app.infrastructure.persistence.factory import build_openharness_service
from app.interfaces.http.deps import owner_scope_for, require_principal_permission


router = APIRouter()


def _protocol_ids(payload: object) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    request_id = payload.get("request_id")
    correlation_id = payload.get("correlation_id")
    return (
        request_id if isinstance(request_id, str) else None,
        correlation_id if isinstance(correlation_id, str) else None,
    )


@router.post("/v1/execute")
async def execute_openharness(
    payload: Any = Body(...),
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    request_id, correlation_id = _protocol_ids(payload)
    try:
        request = parse_request(payload)
    except OpenHarnessProtocolError as exc:
        return error_response(
            request_id=exc.request_id or request_id,
            correlation_id=exc.correlation_id or correlation_id,
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
        ).model_dump(exclude_none=True)

    response = await build_openharness_service().execute(
        request,
        tenant_id=owner_scope_for(identity),
    )
    return response.model_dump(exclude_none=True)

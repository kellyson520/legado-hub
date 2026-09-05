from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from app.application.ports.provider import PROVIDER_ROUTE_GROUPS
from app.infrastructure.harness.openharness.models import (
    ActionDirective,
    OpenHarnessRequest,
    OpenHarnessResponse,
    OpenHarnessResponseBody,
)
from app.infrastructure.harness.openharness.protocol import (
    SUPPORTED_CAPABILITIES,
    error_response,
)


class OpenHarnessEngineService:
    """Translate OpenHarness requests into the existing provider engine."""

    def __init__(self, *, provider_platform, agent_runtime=None):
        self._provider_platform = provider_platform
        self._agent_runtime = agent_runtime

    async def execute(self, request: OpenHarnessRequest, *, tenant_id: str) -> OpenHarnessResponse:
        started = time.perf_counter()
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            return error_response(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                code="tenant_required",
                message="An authenticated tenant is required.",
            )

        intent = self._intent_text(request)
        if not intent:
            return error_response(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                code="invalid_request",
                message="request.context.user_intent is required.",
            )

        provider_group, model = self._route_hint(request)
        if provider_group not in PROVIDER_ROUTE_GROUPS:
            provider_group = "ai"
        quota_scope = self._quota_scope(tenant_id)
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the Legado Hub Harness Engine. Answer the user's intent "
                        "using only the capabilities available to this request."
                    ),
                },
                {"role": "user", "content": intent},
            ],
        }

        try:
            result = await self._provider_platform.invoke_chat(
                provider_group=provider_group,
                model=model,
                payload=payload,
                quota_scope=quota_scope,
            )
        except Exception:
            return error_response(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                code="engine_failure",
                message="The Harness Engine could not complete the request.",
                retryable=True,
            )

        response = self._response_from_result(request, result, started)
        self._record_run(request, tenant_id, result, response)
        return response

    @staticmethod
    def _intent_text(request: OpenHarnessRequest) -> str:
        intent = request.request.context.user_intent if request.request.context else None
        if isinstance(intent, str):
            return intent.strip()
        return ""

    @staticmethod
    def _route_hint(request: OpenHarnessRequest) -> tuple[str, str | None]:
        hint = (request.request.context.task_hint if request.request.context else None) or {}
        group = str(hint.get("provider_group") or "ai").strip()
        model = str(hint.get("model") or "").strip() or None
        return group, model

    @staticmethod
    def _quota_scope(tenant_id: str) -> tuple[str, str]:
        if ":" in tenant_id:
            scope_type, scope_id = tenant_id.split(":", 1)
            if scope_type and scope_id:
                return scope_type, scope_id
        return "tenant", tenant_id

    def _response_from_result(
        self,
        request: OpenHarnessRequest,
        result: dict[str, Any],
        started: float,
    ) -> OpenHarnessResponse:
        output = result.get("output") if isinstance(result, dict) else {}
        output = output if isinstance(output, dict) else {}
        text = str(output.get("text") or "")
        directives: list[ActionDirective] = []
        if text:
            directives.append(
                ActionDirective(
                    action_type="render_message",
                    priority="normal",
                    risk_tier="safe",
                    payload={"message": text, "format": "text"},
                )
            )

        for tool_call in self._tool_calls(output, result):
            function = tool_call.get("function") if isinstance(tool_call, dict) else {}
            function = function if isinstance(function, dict) else {}
            arguments = self._tool_arguments(function.get("arguments"))
            directives.append(
                ActionDirective(
                    action_type="com.legadohub.tool_call",
                    priority="high",
                    risk_tier="caution",
                    requires_user_approval=True,
                    payload={
                        "call_id": str(tool_call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "arguments": arguments,
                    },
                )
            )

        denials = self._capability_denials(request)
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return OpenHarnessResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            supported_capabilities=dict(SUPPORTED_CAPABILITIES),
            capability_denials=denials,
            response=OpenHarnessResponseBody(
                status="success",
                engine_latency_ms=latency_ms,
                action_directives=directives,
            ),
        )

    @staticmethod
    def _tool_calls(output: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
        calls = output.get("tool_calls") or result.get("tool_calls") or []
        return [item for item in calls if isinstance(item, dict)] if isinstance(calls, list) else []

    @staticmethod
    def _tool_arguments(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {"raw": value[:4000]}
            return dict(parsed) if isinstance(parsed, Mapping) else {"value": parsed}
        return {}

    @staticmethod
    def _capability_denials(request: OpenHarnessRequest) -> list[dict[str, Any]]:
        denials = []
        for capability, requested in request.capabilities.items():
            if not requested:
                continue
            if not SUPPORTED_CAPABILITIES.get(capability, False):
                denials.append({
                    "capability": capability,
                    "code": "not_supported",
                    "message": "The requested capability is not enabled by this Engine.",
                })
        return denials

    def _record_run(
        self,
        request: OpenHarnessRequest,
        tenant_id: str,
        result: dict[str, Any],
        response: OpenHarnessResponse,
    ) -> None:
        if self._agent_runtime is None:
            return
        try:
            run = self._agent_runtime.create_run(
                tenant_id=tenant_id,
                agent_kind="openharness",
                input_payload={
                    "protocol_version": request.protocol_version,
                    "request_id": request.request_id,
                    "conversation_id": request.request.context.conversation_id if request.request.context else None,
                },
            )
            usage = result.get("usage") if isinstance(result, dict) else {}
            usage = usage if isinstance(usage, dict) else {}
            self._agent_runtime.record_request(
                run_id=run.id,
                tenant_id=tenant_id,
                owner_scope=tenant_id,
                book_id=None,
                chapter_id=None,
                entrypoint="openharness",
                conversation_id=(request.request.context.conversation_id if request.request.context else "") or "",
                provider=str(result.get("provider_name") or ""),
                model=str(result.get("model") or ""),
                attempts=int(result.get("attempt_count") or 0),
                cache_hit=False,
                usage=usage,
                tool_names=[
                    str(item.payload.get("name") or "")
                    for item in response.response.action_directives
                    if item.action_type == "com.legadohub.tool_call"
                ],
            )
        except Exception:
            # Audit persistence must not turn a successful model response into
            # a provider failure. The normal AgentRuntime path remains the
            # source of truth for durable traces.
            return

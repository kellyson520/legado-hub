from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenHarnessModel(BaseModel):
    """OpenHarness objects ignore unknown fields for forward compatibility."""

    model_config = ConfigDict(extra="ignore")


class ShellIdentity(OpenHarnessModel):
    shell_kind: str | None = Field(default=None, min_length=1, max_length=120)
    shell_version: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=80)


class AttachmentReference(OpenHarnessModel):
    ref_id: str | None = Field(default=None, max_length=200)
    uri: str | None = Field(default=None, max_length=2000)
    asset_id: str | None = Field(default=None, max_length=200)
    mime_type: str | None = Field(default=None, max_length=120)
    filename: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)


class Continuation(OpenHarnessModel):
    run_id: str | None = Field(default=None, max_length=120)
    sop_id: str | None = Field(default=None, max_length=200)
    continuation_token: str | None = Field(default=None, max_length=2000)


class HarnessContext(OpenHarnessModel):
    session_id: str | None = Field(default=None, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=200)
    user_intent: str | None = Field(default=None, max_length=20_000)
    task_hint: dict[str, Any] | None = None
    continuation: Continuation | None = None
    environment_state: dict[str, Any] | None = None
    attachments: list[AttachmentReference] = Field(default_factory=list)
    shell: ShellIdentity | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class HarnessRequestPayload(OpenHarnessModel):
    auth: dict[str, Any] = Field(default_factory=dict)
    context: HarnessContext | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class OpenHarnessRequest(OpenHarnessModel):
    protocol_version: str = Field(min_length=1, max_length=64)
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=200)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    request: HarnessRequestPayload


class HarnessError(OpenHarnessModel):
    code: str = Field(min_length=1, max_length=120)
    message: str | None = Field(default=None, max_length=1000)
    retryable: bool | None = None
    details: dict[str, Any] | None = None


class ActionDirective(OpenHarnessModel):
    action_type: str = Field(min_length=1, max_length=200)
    priority: Literal["low", "normal", "high", "critical"] | None = None
    execution: Literal["sequential", "parallel"] | None = None
    risk_tier: Literal["safe", "caution", "dangerous"] | None = None
    requires_user_approval: bool = False
    deadline_ms: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class OpenHarnessResponseBody(OpenHarnessModel):
    status: Literal["success", "error"]
    error: HarnessError | None = None
    engine_latency_ms: int | None = Field(default=None, ge=0)
    action_directives: list[ActionDirective] = Field(default_factory=list)


class OpenHarnessResponse(OpenHarnessModel):
    protocol_version: str = "1.0.0"
    request_id: str | None = None
    correlation_id: str | None = None
    supported_protocol_versions: list[str] = Field(default_factory=lambda: ["1.0.0"])
    supported_capabilities: dict[str, Any] = Field(default_factory=dict)
    capability_denials: list[dict[str, Any]] = Field(default_factory=list)
    response: OpenHarnessResponseBody

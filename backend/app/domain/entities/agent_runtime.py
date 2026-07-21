from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal


ToolCategory = Literal['read', 'propose', 'operate']


@dataclass(frozen=True)
class ToolResult:
    status: Literal['accepted', 'rejected']
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    id: str | None = None
    tool_invocation_id: str | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ToolEvidence:
    id: str
    tool_invocation_id: str
    tenant_id: str
    evidence_type: str
    resource_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class ToolInvocation:
    id: str
    agent_run_id: str
    tenant_id: str
    tool_name: str
    category: ToolCategory
    arguments: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    result: ToolResult | None = None
    evidence: list[ToolEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRun:
    id: str
    tenant_id: str
    agent_kind: str
    input_payload: dict[str, Any] = field(default_factory=dict)
    request_metadata: dict[str, Any] = field(default_factory=dict)
    status: Literal['candidate'] = 'candidate'
    created_at: datetime | None = None


@dataclass(frozen=True)
class AgentTool:
    name: str
    category: ToolCategory
    allowed_agent_kinds: frozenset[str]
    handler: Callable[[dict[str, Any]], ToolResult] | None = None

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AIConversationAuthorizationRequest:
    id: str
    actor_id: str
    conversation_id: str
    message_id: str
    requested_tools: list[str]
    requested_calls: list[dict]
    purpose: str
    continuation: dict
    status: str = "pending"
    decision: str | None = None
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    result_message_id: str | None = None
    claim_token: str | None = None
    claim_expires_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIConversationAuthorizationGrant:
    id: str
    actor_id: str
    conversation_id: str | None
    scope: str
    tool_names: list[str]
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

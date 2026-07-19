from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AIConversation:
    id: str
    actor_id: str
    title: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIConversationMessage:
    id: str
    conversation_id: str
    role: str
    mode: str
    content: str
    status: str = "succeeded"
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

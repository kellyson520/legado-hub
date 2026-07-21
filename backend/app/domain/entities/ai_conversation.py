from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AIConversation:
    id: str
    actor_id: str
    title: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    owner_scope: str = "legacy"
    book_id: int | None = None
    entrypoint: str = "workspace"
    context_range: str = "book"
    model_ref: str | None = None
    knowledge_version: str = ""
    toolset_version: str = ""


@dataclass
class AIConversationMessage:
    id: str
    conversation_id: str
    role: str
    mode: str
    content: str
    status: str = "succeeded"
    tool_calls: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    owner_scope: str = "legacy"
    entrypoint: str = "workspace"
    book_id: int | None = None
    chapter_id: int | None = None

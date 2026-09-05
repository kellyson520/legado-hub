from abc import ABC, abstractmethod

from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage


class AIConversationRepository(ABC):
    @abstractmethod
    def create_conversation(self, conversation: AIConversation) -> AIConversation:
        raise NotImplementedError

    @abstractmethod
    def list_conversations(self, actor_id: str, owner_scope: str | None = None) -> list[AIConversation]:
        raise NotImplementedError

    @abstractmethod
    def list_conversations_page(
        self,
        actor_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        owner_scope: str | None = None,
    ) -> tuple[list[AIConversation], int]:
        raise NotImplementedError

    @abstractmethod
    def get_conversation(self, conversation_id: str, actor_id: str, owner_scope: str | None = None) -> AIConversation | None:
        raise NotImplementedError

    @abstractmethod
    def append_message(self, message: AIConversationMessage) -> AIConversationMessage:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, conversation_id: str, owner_scope: str | None = None) -> list[AIConversationMessage]:
        raise NotImplementedError

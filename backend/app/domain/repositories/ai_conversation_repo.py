from abc import ABC, abstractmethod

from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage


class AIConversationRepository(ABC):
    @abstractmethod
    def create_conversation(self, conversation: AIConversation) -> AIConversation:
        raise NotImplementedError

    @abstractmethod
    def list_conversations(self, actor_id: str) -> list[AIConversation]:
        raise NotImplementedError

    @abstractmethod
    def get_conversation(self, conversation_id: str, actor_id: str) -> AIConversation | None:
        raise NotImplementedError

    @abstractmethod
    def append_message(self, message: AIConversationMessage) -> AIConversationMessage:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, conversation_id: str) -> list[AIConversationMessage]:
        raise NotImplementedError

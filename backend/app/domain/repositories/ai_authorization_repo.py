from abc import ABC, abstractmethod

from app.domain.entities.ai_authorization import (
    AIConversationAuthorizationGrant,
    AIConversationAuthorizationRequest,
)


class AIAuthorizationRepository(ABC):
    @abstractmethod
    def create_request(self, request: AIConversationAuthorizationRequest) -> AIConversationAuthorizationRequest:
        raise NotImplementedError

    @abstractmethod
    def get_request(self, request_id: str, actor_id: str, conversation_id: str | None = None) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def get_active_request(self, actor_id: str, conversation_id: str) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def list_requests(self, actor_id: str, conversation_id: str, status: str | None = None) -> list[AIConversationAuthorizationRequest]:
        raise NotImplementedError

    @abstractmethod
    def claim_request(self, request_id: str, actor_id: str, conversation_id: str, decision: str) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def renew_claim(
        self,
        request_id: str,
        actor_id: str,
        claim_token: str,
        *,
        lease_seconds: int = 300,
    ) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def finalize_request(self, request_id: str, actor_id: str, status: str, *, claim_token: str | None = None, result_message_id: str | None = None) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def set_result_message_id(
        self,
        request_id: str,
        actor_id: str,
        result_message_id: str,
    ) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def expire_request(self, request_id: str, actor_id: str, conversation_id: str) -> AIConversationAuthorizationRequest | None:
        raise NotImplementedError

    @abstractmethod
    def create_grant(self, grant: AIConversationAuthorizationGrant) -> AIConversationAuthorizationGrant:
        raise NotImplementedError

    @abstractmethod
    def list_active_grants(self, actor_id: str, conversation_id: str | None = None) -> list[AIConversationAuthorizationGrant]:
        raise NotImplementedError

    @abstractmethod
    def revoke_grant(self, grant_id: str, actor_id: str) -> AIConversationAuthorizationGrant | None:
        raise NotImplementedError

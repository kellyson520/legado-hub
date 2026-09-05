from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.interactive_browser import (
    InteractiveBrowserEvent,
    InteractiveBrowserSession,
)


class InteractiveBrowserRepository(ABC):
    @abstractmethod
    def create(self, session: InteractiveBrowserSession) -> InteractiveBrowserSession:
        raise NotImplementedError

    @abstractmethod
    def get(self, session_id: str) -> InteractiveBrowserSession | None:
        raise NotImplementedError

    @abstractmethod
    def get_for_owner(self, session_id: str, owner_id: str) -> InteractiveBrowserSession | None:
        raise NotImplementedError

    @abstractmethod
    def find_active_for_source(
        self,
        source_version_id: str,
        owner_id: str,
    ) -> InteractiveBrowserSession | None:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> list[InteractiveBrowserSession]:
        raise NotImplementedError

    @abstractmethod
    def update_state(
        self,
        session_id: str,
        *,
        state,
        automatic_attempted: bool | None = None,
        terminal_reason: str | None = None,
        closed_at: datetime | None = None,
    ) -> InteractiveBrowserSession:
        raise NotImplementedError

    @abstractmethod
    def transition_state(
        self,
        session_id: str,
        *,
        expected_states,
        state,
        automatic_attempted: bool | None = None,
        terminal_reason: str | None = None,
        closed_at: datetime | None = None,
    ) -> InteractiveBrowserSession | None:
        raise NotImplementedError

    @abstractmethod
    def count_active(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def issue_relay_token(
        self,
        *,
        session_id: str,
        owner_id: str,
        raw_token: str,
        expires_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def consume_relay_token(self, raw_token: str, *, owner_id: str) -> InteractiveBrowserSession | None:
        raise NotImplementedError

    @abstractmethod
    def record_event(
        self,
        *,
        session_id: str,
        event_type: str,
        actor_id: str,
        detail: dict,
    ) -> InteractiveBrowserEvent:
        raise NotImplementedError

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility.
    class StrEnum(str, Enum):
        def __str__(self) -> str:
            return self.value


class InteractiveBrowserState(StrEnum):
    PENDING = 'pending'
    AUTOMATIC_RUNNING = 'automatic_running'
    AWAITING_MANUAL = 'awaiting_manual_verification'
    VALIDATING = 'validating'
    SUCCEEDED = 'succeeded'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'
    FAILED = 'failed'


@dataclass(frozen=True)
class InteractiveBrowserSession:
    id: str
    source_version_id: str
    owner_id: str
    allowed_origins: list[str] = field(default_factory=list)
    state: InteractiveBrowserState = InteractiveBrowserState.PENDING
    automatic_attempted: bool = False
    expires_at: datetime | None = None
    closed_at: datetime | None = None
    terminal_reason: str | None = None
    created_at: datetime | None = None

    @classmethod
    def new(
        cls,
        *,
        source_version_id: str,
        owner_id: str,
        allowed_origins: list[str],
        expires_at: datetime,
    ) -> 'InteractiveBrowserSession':
        return cls(
            id=uuid4().hex,
            source_version_id=source_version_id,
            owner_id=owner_id,
            allowed_origins=list(allowed_origins),
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class InteractiveBrowserEvent:
    id: int = 0
    session_id: str = ''
    event_type: str = ''
    actor_id: str = ''
    detail: dict = field(default_factory=dict)
    created_at: datetime | None = None

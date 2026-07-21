from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VersionedSetting:
    value: dict[str, object]
    version: str | None
    updated_at: datetime | None


class ConcurrentSettingsUpdateError(RuntimeError):
    pass


class SystemSettingsRepository(ABC):
    @abstractmethod
    def get_bool(self, key: str, default: bool = False) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_bool(self, key: str, value: bool) -> None:
        raise NotImplementedError

    # These helpers are optional for legacy adapters; novel settings use them
    # when available while the versioned settings contract remains intact.
    def get_value(self, key: str, default: str | None = None) -> str | None:
        raise NotImplementedError

    def set_value(self, key: str, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_int(self, key: str, default: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def set_int(self, key: str, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_json(self, key: str, default: dict[str, object]) -> VersionedSetting:
        raise NotImplementedError

    @abstractmethod
    def put_json(
        self,
        key: str,
        value: dict[str, object],
        expected_version: str | None,
    ) -> VersionedSetting:
        raise NotImplementedError

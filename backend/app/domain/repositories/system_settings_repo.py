from abc import ABC, abstractmethod


class SystemSettingsRepository(ABC):
    @abstractmethod
    def get_bool(self, key: str, default: bool = False) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_bool(self, key: str, value: bool) -> None:
        raise NotImplementedError

    # Generic settings are intentionally optional on the legacy port.  Older
    # test doubles and deployments only implement the boolean source-agent
    # setting methods above; the novel settings service feature-detects these
    # helpers and keeps that contract compatible.
    def get_value(self, key: str, default: str | None = None) -> str | None:
        raise NotImplementedError

    def set_value(self, key: str, value: str) -> None:
        raise NotImplementedError

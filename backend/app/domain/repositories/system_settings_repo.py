from abc import ABC, abstractmethod


class SystemSettingsRepository(ABC):
    @abstractmethod
    def get_bool(self, key: str, default: bool = False) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_bool(self, key: str, value: bool) -> None:
        raise NotImplementedError

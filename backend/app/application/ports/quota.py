from typing import Protocol


class QuotaStore(Protocol):
    async def reset_quota(self, key_id: int, metric: str) -> None:
        ...

    async def get_quota(self, key_id: int, metric: str) -> int | float:
        ...

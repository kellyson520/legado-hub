from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DiscoveryCandidate:
    url: str
    attempts: int = 0
    next_attempt_at: datetime | None = None
    priority: int = 0
    sequence: int = 0


class SourceDiscoveryService:
    def __init__(
        self,
        *,
        origin_budget: int = 1,
        cooldown_seconds: int = 300,
        retry_base_seconds: int = 30,
    ):
        self._origin_budget = max(origin_budget, 1)
        self._cooldown_seconds = max(cooldown_seconds, 1)
        self._retry_base_seconds = max(retry_base_seconds, 1)
        self._candidates: dict[str, DiscoveryCandidate] = {}
        self._blocked_origins: dict[str, datetime] = {}
        self._sequence = 0

    def enqueue_candidate(self, url: str, *, priority: int = 0) -> None:
        existing = self._candidates.get(url)
        if existing is not None:
            existing.priority = max(existing.priority, int(priority or 0))
            return
        self._sequence += 1
        self._candidates[url] = DiscoveryCandidate(
            url=url,
            priority=int(priority or 0),
            sequence=self._sequence,
        )

    def mark_origin_blocked(self, url: str, *, now: datetime | None = None) -> None:
        moment = now or _utcnow()
        self._blocked_origins[self._origin(url)] = moment + timedelta(seconds=self._cooldown_seconds)

    def record_result(self, url: str, *, success: bool, now: datetime | None = None) -> None:
        moment = now or _utcnow()
        candidate = self._candidates.setdefault(url, DiscoveryCandidate(url=url))
        if success:
            candidate.attempts = 0
            candidate.next_attempt_at = None
            return

        candidate.attempts += 1
        delay_seconds = self._retry_base_seconds * (2 ** max(candidate.attempts - 1, 0))
        candidate.next_attempt_at = moment + timedelta(seconds=delay_seconds)

    def next_jobs(self, *, now: datetime | None = None) -> list[str]:
        moment = now or _utcnow()
        jobs: list[str] = []
        by_origin: dict[str, int] = {}
        ordered = sorted(
            self._candidates.items(),
            key=lambda item: (-item[1].priority, item[1].sequence),
        )
        for url, candidate in ordered:
            origin = self._origin(url)
            blocked_until = self._blocked_origins.get(origin)
            if blocked_until is not None and blocked_until > moment:
                continue
            if candidate.next_attempt_at is not None and candidate.next_attempt_at > moment:
                continue
            used = by_origin.get(origin, 0)
            if used >= self._origin_budget:
                continue
            jobs.append(url)
            by_origin[origin] = used + 1
        return jobs

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return f'{parts.scheme.lower()}://{parts.netloc.lower()}'

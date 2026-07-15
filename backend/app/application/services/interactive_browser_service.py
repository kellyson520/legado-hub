from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.domain.entities.interactive_browser import (
    InteractiveBrowserSession,
    InteractiveBrowserState,
)


@dataclass(frozen=True)
class BrowserAttemptResult:
    state: str
    reason: str = ''

    @classmethod
    def needs_manual(cls, reason: str) -> 'BrowserAttemptResult':
        return cls(state='needs_manual', reason=reason)

    @classmethod
    def succeeded(cls) -> 'BrowserAttemptResult':
        return cls(state='succeeded')


class BrowserSessionDriver(Protocol):
    async def start(self, *, profile_dir: Path, initial_url: str, allowed_origins: set[str]) -> Any:
        raise NotImplementedError

    async def automatic_probe(self, handle: Any) -> BrowserAttemptResult:
        raise NotImplementedError

    async def close(self, handle: Any) -> None:
        raise NotImplementedError


class InteractiveBrowserUnavailableError(RuntimeError):
    pass


class InteractiveBrowserService:
    def __init__(self, *, repo, driver: BrowserSessionDriver, settings, profile_root: Path | str):
        self._repo = repo
        self._driver = driver
        self._settings = settings
        self._profile_root = Path(profile_root)
        self._handles: dict[str, Any] = {}

    async def start_or_resume(
        self,
        *,
        source_version_id: str,
        owner_id: str,
        target_url: str,
    ) -> InteractiveBrowserSession:
        config = self._settings.get_interactive_browser_settings()
        if not bool(config.get('enabled', False)):
            raise InteractiveBrowserUnavailableError('interactive_browser_disabled')
        allowed_origins = self._allowed_origins(target_url)
        existing = self._repo.find_active_for_source(source_version_id, owner_id)
        if existing is not None:
            return existing
        max_sessions = int(config.get('max_sessions', 1) or 1)
        if self._repo.count_active() >= max_sessions:
            raise InteractiveBrowserUnavailableError('interactive_browser_capacity_reached')

        now = datetime.now(timezone.utc)
        timeout_seconds = int(config.get('session_timeout_seconds', 300) or 300)
        session = self._repo.create(
            InteractiveBrowserSession.new(
                source_version_id=source_version_id,
                owner_id=owner_id,
                allowed_origins=sorted(allowed_origins),
                expires_at=now + timedelta(seconds=timeout_seconds),
            )
        )
        self._repo.record_event(
            session_id=session.id,
            event_type='session_created',
            actor_id=owner_id,
            detail={'target_origin': next(iter(allowed_origins))},
        )
        if not bool(config.get('automatic_enabled', True)):
            return self._await_manual(session, reason='automatic_attempt_disabled')
        return await self._attempt_automatic(session, target_url=target_url)

    async def _attempt_automatic(
        self,
        session: InteractiveBrowserSession,
        *,
        target_url: str,
    ) -> InteractiveBrowserSession:
        running = self._repo.update_state(
            session.id,
            state=InteractiveBrowserState.AUTOMATIC_RUNNING,
            automatic_attempted=True,
        )
        profile_dir = self._profile_root / running.id
        profile_dir.mkdir(parents=True, exist_ok=False)
        handle = None
        try:
            handle = await self._driver.start(
                profile_dir=profile_dir,
                initial_url=target_url,
                allowed_origins=set(running.allowed_origins),
            )
            self._handles[running.id] = handle
            result = await self._driver.automatic_probe(handle)
        except Exception as exc:
            if handle is not None:
                await self._close_handle(running.id)
            failed = self._repo.update_state(
                running.id,
                state=InteractiveBrowserState.FAILED,
                terminal_reason='browser_unavailable',
                closed_at=datetime.now(timezone.utc),
            )
            self._repo.record_event(
                session_id=failed.id,
                event_type='automatic_attempt_failed',
                actor_id=failed.owner_id,
                detail={'reason': 'browser_unavailable'},
            )
            return failed

        if result.state == 'needs_manual':
            return self._await_manual(running, reason=result.reason or 'verification_required')
        succeeded = self._repo.update_state(
            running.id,
            state=InteractiveBrowserState.SUCCEEDED,
            terminal_reason=None,
        )
        self._repo.record_event(
            session_id=succeeded.id,
            event_type='automatic_attempt_succeeded',
            actor_id=succeeded.owner_id,
            detail={},
        )
        return succeeded

    def _await_manual(self, session: InteractiveBrowserSession, *, reason: str) -> InteractiveBrowserSession:
        awaiting = self._repo.update_state(
            session.id,
            state=InteractiveBrowserState.AWAITING_MANUAL,
            automatic_attempted=True,
            terminal_reason=reason,
        )
        self._repo.record_event(
            session_id=awaiting.id,
            event_type='manual_verification_required',
            actor_id=awaiting.owner_id,
            detail={'reason': reason},
        )
        return awaiting

    async def _close_handle(self, session_id: str) -> None:
        handle = self._handles.pop(session_id, None)
        if handle is not None:
            await self._driver.close(handle)

    @staticmethod
    def _allowed_origins(target_url: str) -> set[str]:
        parsed = urlsplit(target_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('target_url must be an absolute HTTP URL')
        return {f'{parsed.scheme}://{parsed.netloc}'}

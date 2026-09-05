from __future__ import annotations

import asyncio
import inspect
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.application.ports.browser import BrowserAttemptResult, BrowserValidationResult
from app.domain.entities.interactive_browser import (
    InteractiveBrowserSession,
    InteractiveBrowserState,
)


ACTIVE_BROWSER_STATES = frozenset({
    InteractiveBrowserState.PENDING,
    InteractiveBrowserState.AUTOMATIC_RUNNING,
    InteractiveBrowserState.AWAITING_MANUAL,
    InteractiveBrowserState.VALIDATING,
})


@dataclass(frozen=True)
class BrowserVerificationResult:
    state: str
    session_id: str | None = None
    reason: str = ''
    validation: 'BrowserValidationResult | None' = None

    @classmethod
    def needs_manual(cls, session_id: str, reason: str) -> 'BrowserVerificationResult':
        return cls(state='needs_manual', session_id=session_id, reason=reason)

    @classmethod
    def unavailable(cls, reason: str) -> 'BrowserVerificationResult':
        return cls(state='unavailable', reason=reason)

    @classmethod
    def standard_browser_ready(cls, session_id: str) -> 'BrowserVerificationResult':
        return cls(state='standard_browser_ready', session_id=session_id)

    @classmethod
    def validated(
        cls,
        session_id: str,
        validation: 'BrowserValidationResult',
    ) -> 'BrowserVerificationResult':
        return cls(state='validated', session_id=session_id, validation=validation)


@dataclass(frozen=True)
class BrowserRelayTicket:
    session_id: str
    token: str
    relay_port: int


class BrowserSessionDriver(Protocol):
    async def start(self, *, profile_dir: Path, initial_url: str, allowed_origins: set[str]) -> Any:
        raise NotImplementedError

    async def automatic_probe(self, handle: Any) -> BrowserAttemptResult:
        raise NotImplementedError

    async def close(self, handle: Any) -> None:
        raise NotImplementedError


class InteractiveBrowserUnavailableError(RuntimeError):
    pass


class InteractiveBrowserValidationConflictError(ValueError):
    pass


class InteractiveBrowserValidationAcceptanceError(ValueError):
    pass


class InteractiveBrowserService:
    def __init__(
        self,
        *,
        repo,
        driver: BrowserSessionDriver,
        settings,
        profile_root: Path | str,
        probe_runner=None,
        token_factory=token_urlsafe,
        clock=None,
        expiry_sleep=asyncio.sleep,
        probe_waiter=asyncio.wait_for,
    ):
        self._repo = repo
        self._driver = driver
        self._settings = settings
        self._profile_root = Path(profile_root)
        self._handles: dict[str, Any] = {}
        self._probe_runner = probe_runner or self._run_browser_probe
        self._token_factory = token_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._expiry_sleep = expiry_sleep
        self._expiry_tasks: dict[str, asyncio.Task] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._probe_waiter = probe_waiter
        self._expire_persisted_sessions_after_restart()

    async def start_or_resume(
        self,
        *,
        source_version_id: str,
        owner_id: str,
        target_url: str,
    ) -> InteractiveBrowserSession:
        await self._expire_due_sessions()
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

        now = self._now()
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
        return await self._attempt_automatic(
            session,
            target_url=target_url,
            run_automatic_probe=bool(config.get('automatic_enabled', True)),
        )

    async def attempt_automatic(
        self,
        *,
        source_version_id: str,
        owner_id: str,
        source_rule: dict,
        keyword: str,
    ) -> BrowserVerificationResult:
        target_url = str(source_rule.get('bookSourceUrl') or '').strip()
        if not target_url:
            return BrowserVerificationResult.unavailable('missing_source_url')
        try:
            session = await self.start_or_resume(
                source_version_id=source_version_id,
                owner_id=owner_id,
                target_url=target_url,
            )
        except InteractiveBrowserUnavailableError as exc:
            return BrowserVerificationResult.unavailable(str(exc))
        if session.state == InteractiveBrowserState.AWAITING_MANUAL:
            return BrowserVerificationResult.needs_manual(
                session.id,
                session.terminal_reason or 'verification_required',
            )
        if session.state == InteractiveBrowserState.SUCCEEDED:
            async with self._session_lock(session.id):
                current = self._repo.get(session.id)
                if current is None or current.state != InteractiveBrowserState.SUCCEEDED or current.closed_at is not None:
                    return BrowserVerificationResult.unavailable('browser_session_unavailable')
                handle = self._handles.get(current.id)
                if handle is None:
                    return BrowserVerificationResult.unavailable('browser_session_unavailable')
                remaining_seconds = self._remaining_session_seconds(current)
                if remaining_seconds <= 0:
                    await self._expire_locked(current)
                    return BrowserVerificationResult.unavailable('interactive_browser_session_expired')
                try:
                    validation = await self._probe_waiter(
                        self._probe_runner(handle, source_rule, keyword),
                        remaining_seconds,
                    )
                except asyncio.TimeoutError:
                    latest = self._repo.get(current.id)
                    if latest is not None and self._is_open(latest):
                        await self._expire_locked(latest)
                    return BrowserVerificationResult.unavailable('interactive_browser_session_expired')

                latest = self._repo.get(current.id)
                if latest is None or latest.state != InteractiveBrowserState.SUCCEEDED or latest.closed_at is not None:
                    return BrowserVerificationResult.unavailable('browser_session_unavailable')
                if validation.passed:
                    completed = self._repo.transition_state(
                        current.id,
                        expected_states=(InteractiveBrowserState.SUCCEEDED,),
                        state=InteractiveBrowserState.SUCCEEDED,
                        closed_at=self._now(),
                    )
                    if completed is None:
                        return BrowserVerificationResult.unavailable('interactive_browser_session_state_conflict')
                    await self._close_handle(current.id)
                    self._repo.record_event(
                        session_id=completed.id,
                        event_type='automatic_validation_succeeded',
                        actor_id=completed.owner_id,
                        detail={'stages': validation.stages or {}},
                    )
                    return BrowserVerificationResult.validated(completed.id, validation)
                if validation.reason == 'verification_required':
                    awaiting = self._repo.transition_state(
                        current.id,
                        expected_states=(InteractiveBrowserState.SUCCEEDED,),
                        state=InteractiveBrowserState.AWAITING_MANUAL,
                        terminal_reason=validation.reason,
                    )
                    if awaiting is None:
                        return BrowserVerificationResult.unavailable('interactive_browser_session_state_conflict')
                    return BrowserVerificationResult.needs_manual(
                        awaiting.id,
                        awaiting.terminal_reason or validation.reason,
                    )
                failed = self._repo.transition_state(
                    current.id,
                    expected_states=(InteractiveBrowserState.SUCCEEDED,),
                    state=InteractiveBrowserState.FAILED,
                    terminal_reason=validation.reason or 'browser_validation_failed',
                    closed_at=self._now(),
                )
                if failed is None:
                    return BrowserVerificationResult.unavailable('interactive_browser_session_state_conflict')
                await self._close_handle(current.id)
                return BrowserVerificationResult.unavailable(failed.terminal_reason or 'browser_validation_failed')
        return BrowserVerificationResult.unavailable(session.terminal_reason or 'browser_unavailable')

    def get_for_owner(self, session_id: str, *, owner_id: str) -> InteractiveBrowserSession | None:
        session = self._repo.get_for_owner(session_id, owner_id)
        if session is not None and session.state == InteractiveBrowserState.EXPIRED:
            return None
        if session is not None and self._is_expired(session):
            self._expire_from_sync_access(session)
            return None
        if session is not None:
            return session
        stored = self._repo.get(session_id)
        if stored is not None and stored.owner_id == owner_id and self._is_expired(stored):
            self._expire_from_sync_access(stored)
        return None

    async def cancel(self, session_id: str, *, owner_id: str) -> InteractiveBrowserSession:
        lock = self._session_lock(session_id)
        if lock.locked():
            current = self._repo.get_for_owner(session_id, owner_id)
            if current is not None and current.state == InteractiveBrowserState.VALIDATING:
                raise InteractiveBrowserValidationConflictError('interactive_browser_validation_in_progress')
        async with lock:
            session = self.get_for_owner(session_id, owner_id=owner_id)
            if session is None:
                raise KeyError(session_id)
            if session.state == InteractiveBrowserState.VALIDATING:
                raise InteractiveBrowserValidationConflictError('interactive_browser_validation_in_progress')
            if session.state != InteractiveBrowserState.AWAITING_MANUAL:
                raise InteractiveBrowserValidationConflictError(
                    'interactive_browser_not_awaiting_manual_verification'
                )
            cancelled = self._repo.transition_state(
                session.id,
                expected_states=(InteractiveBrowserState.AWAITING_MANUAL,),
                state=InteractiveBrowserState.CANCELLED,
                terminal_reason='cancelled_by_owner',
                closed_at=self._now(),
            )
            if cancelled is None:
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
            await self._close_handle(session.id)
            self._repo.record_event(
                session_id=cancelled.id,
                event_type='session_cancelled',
                actor_id=owner_id,
                detail={},
            )
            return cancelled

    def issue_relay_ticket(self, session_id: str, *, owner_id: str) -> BrowserRelayTicket:
        session = self.get_for_owner(session_id, owner_id=owner_id)
        if session is None:
            raise KeyError(session_id)
        if session.state != InteractiveBrowserState.AWAITING_MANUAL:
            raise ValueError('interactive_browser_not_awaiting_manual_verification')
        handle = self._handles.get(session.id)
        relay_port = getattr(handle, 'relay_port', None)
        if handle is None or not isinstance(relay_port, int) or relay_port < 1:
            raise InteractiveBrowserUnavailableError('browser_session_unavailable')
        token = str(self._token_factory())
        expires_at = session.expires_at or (self._now() + timedelta(minutes=1))
        self._repo.issue_relay_token(
            session_id=session.id,
            owner_id=owner_id,
            raw_token=token,
            expires_at=expires_at,
        )
        self._repo.record_event(
            session_id=session.id,
            event_type='relay_ticket_issued',
            actor_id=owner_id,
            detail={},
        )
        return BrowserRelayTicket(session_id=session.id, token=token, relay_port=relay_port)

    def consume_relay_ticket(self, token: str, *, owner_id: str) -> BrowserRelayTicket:
        session = self._repo.consume_relay_token(token, owner_id=owner_id)
        if session is not None and self._is_expired(session):
            self._expire_from_sync_access(session)
            session = None
        if session is None or session.state != InteractiveBrowserState.AWAITING_MANUAL:
            raise KeyError('interactive browser relay token')
        handle = self._handles.get(session.id)
        relay_port = getattr(handle, 'relay_port', None)
        if handle is None or not isinstance(relay_port, int) or relay_port < 1:
            raise InteractiveBrowserUnavailableError('browser_session_unavailable')
        self._repo.record_event(
            session_id=session.id,
            event_type='relay_ticket_consumed',
            actor_id=owner_id,
            detail={},
        )
        return BrowserRelayTicket(session_id=session.id, token='', relay_port=relay_port)

    async def continue_validation(
        self,
        session_id: str,
        *,
        owner_id: str,
        source_rule: dict,
        keyword: str,
        on_success=None,
    ) -> BrowserValidationResult:
        async with self._session_lock(session_id):
            session = self.get_for_owner(session_id, owner_id=owner_id)
            if session is None:
                raise KeyError(session_id)
            if session.state != InteractiveBrowserState.AWAITING_MANUAL:
                raise InteractiveBrowserValidationConflictError(
                    'interactive_browser_not_awaiting_manual_verification'
                )
            handle = self._handles.get(session.id)
            if handle is None:
                raise InteractiveBrowserUnavailableError('browser_session_unavailable')
            validating = self._repo.transition_state(
                session.id,
                expected_states=(InteractiveBrowserState.AWAITING_MANUAL,),
                state=InteractiveBrowserState.VALIDATING,
            )
            if validating is None:
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
            remaining_seconds = self._remaining_session_seconds(validating)
            if remaining_seconds <= 0:
                await self._expire_locked(validating)
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_expired')
            try:
                validation = await self._probe_waiter(
                    self._probe_runner(handle, source_rule, keyword),
                    remaining_seconds,
                )
            except asyncio.TimeoutError as exc:
                current = self._repo.get(session.id)
                if current is not None and current.state == InteractiveBrowserState.VALIDATING:
                    await self._expire_locked(current)
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_expired') from exc

            current = self._repo.get(session.id)
            if current is None or current.state != InteractiveBrowserState.VALIDATING:
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
            if validation.passed:
                if on_success is not None:
                    try:
                        acceptance = on_success(validation)
                        if inspect.isawaitable(acceptance):
                            await acceptance
                    except Exception as exc:
                        restored = self._repo.transition_state(
                            session.id,
                            expected_states=(InteractiveBrowserState.VALIDATING,),
                            state=InteractiveBrowserState.AWAITING_MANUAL,
                            terminal_reason=session.terminal_reason,
                        )
                        if restored is None:
                            raise InteractiveBrowserValidationConflictError(
                                'interactive_browser_session_state_conflict'
                            ) from exc
                        raise InteractiveBrowserValidationAcceptanceError(
                            'source_audit_acceptance_failed'
                        ) from exc
                completed = self._repo.transition_state(
                    session.id,
                    expected_states=(InteractiveBrowserState.VALIDATING,),
                    state=InteractiveBrowserState.SUCCEEDED,
                    closed_at=self._now(),
                )
                if completed is None:
                    raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
                await self._close_handle(session.id)
                self._repo.record_event(
                    session_id=completed.id,
                    event_type='manual_validation_succeeded',
                    actor_id=owner_id,
                    detail={'stages': validation.stages or {}},
                )
                return validation
            if validation.reason == 'verification_required':
                awaiting = self._repo.transition_state(
                    session.id,
                    expected_states=(InteractiveBrowserState.VALIDATING,),
                    state=InteractiveBrowserState.AWAITING_MANUAL,
                    terminal_reason=validation.reason,
                )
                if awaiting is None:
                    raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
                return validation
            failed = self._repo.transition_state(
                session.id,
                expected_states=(InteractiveBrowserState.VALIDATING,),
                state=InteractiveBrowserState.FAILED,
                terminal_reason=validation.reason or 'browser_validation_failed',
                closed_at=self._now(),
            )
            if failed is None:
                raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
            await self._close_handle(session.id)
            self._repo.record_event(
                session_id=failed.id,
                event_type='manual_validation_failed',
                actor_id=owner_id,
                detail={'reason': failed.terminal_reason},
            )
            return validation

    async def expire_session(self, session_id: str, *, reason: str = 'session_expired') -> InteractiveBrowserSession:
        async with self._session_lock(session_id):
            session = self._repo.get(session_id)
            if session is None:
                raise KeyError(session_id)
            return await self._expire_locked(session, reason=reason)

    async def _expire_locked(
        self,
        session: InteractiveBrowserSession,
        *,
        reason: str = 'session_expired',
    ) -> InteractiveBrowserSession:
        if not self._is_open(session):
            return session
        expired = self._mark_expired(session, reason=reason)
        if expired is None:
            current = self._repo.get(session.id)
            if current is not None:
                return current
            raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
        await self._close_handle(session.id)
        return expired

    async def _expire_due_sessions(self) -> None:
        list_active = getattr(self._repo, 'list_active', None)
        if not callable(list_active):
            return
        for session in list_active():
            if self._is_expired(session):
                await self.expire_session(session.id)

    def _expire_persisted_sessions_after_restart(self) -> None:
        list_active = getattr(self._repo, 'list_active', None)
        if not callable(list_active):
            return
        for session in list_active():
            if not self._is_open(session):
                continue
            if self._mark_expired(session, reason='service_restarted') is not None:
                self._remove_profile(session.id)

    def _expire_from_sync_access(self, session: InteractiveBrowserSession) -> None:
        if not self._is_open(session):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if session.state != InteractiveBrowserState.VALIDATING:
                if self._mark_expired(session, reason='session_expired') is not None:
                    self._remove_profile(session.id)
            return
        loop.create_task(self.expire_session(session.id))

    def _mark_expired(self, session: InteractiveBrowserSession, *, reason: str) -> InteractiveBrowserSession | None:
        expired = self._repo.transition_state(
            session.id,
            expected_states=(session.state,),
            state=InteractiveBrowserState.EXPIRED,
            terminal_reason=reason,
            closed_at=self._now(),
        )
        if expired is None:
            return None
        self._repo.record_event(
            session_id=expired.id,
            event_type='session_expired',
            actor_id='',
            detail={'reason': reason},
        )
        return expired

    def _schedule_expiry(self, session: InteractiveBrowserSession) -> None:
        if session.expires_at is None:
            return
        self._cancel_expiry_task(session.id)
        self._expiry_tasks[session.id] = asyncio.create_task(
            self._expire_when_due(session.id, session.expires_at)
        )

    async def _expire_when_due(self, session_id: str, expires_at: datetime) -> None:
        try:
            delay = max(0.0, (self._as_utc(expires_at) - self._now()).total_seconds())
            await self._expiry_sleep(delay)
            await self.expire_session(session_id)
        except asyncio.CancelledError:
            return
        finally:
            try:
                current = asyncio.current_task()
            except RuntimeError:
                return
            if self._expiry_tasks.get(session_id) is current:
                self._expiry_tasks.pop(session_id, None)

    def _cancel_expiry_task(self, session_id: str) -> None:
        task = self._expiry_tasks.pop(session_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def _remaining_session_seconds(self, session: InteractiveBrowserSession) -> float:
        if session.expires_at is None:
            return 0.0
        return max(0.0, (self._as_utc(session.expires_at) - self._now()).total_seconds())

    def _is_expired(self, session: InteractiveBrowserSession) -> bool:
        return session.expires_at is not None and self._as_utc(session.expires_at) <= self._now()

    @staticmethod
    def _is_open(session: InteractiveBrowserSession) -> bool:
        return session.state in ACTIVE_BROWSER_STATES or (
            session.state == InteractiveBrowserState.SUCCEEDED and session.closed_at is None
        )

    def _now(self) -> datetime:
        return self._as_utc(self._clock())

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def _remove_profile(self, session_id: str) -> None:
        profile_dir = self._profile_root / session_id
        if profile_dir.parent == self._profile_root:
            shutil.rmtree(profile_dir, ignore_errors=True)

    async def _attempt_automatic(
        self,
        session: InteractiveBrowserSession,
        *,
        target_url: str,
        run_automatic_probe: bool = True,
    ) -> InteractiveBrowserSession:
        running = self._repo.transition_state(
            session.id,
            expected_states=(InteractiveBrowserState.PENDING,),
            state=InteractiveBrowserState.AUTOMATIC_RUNNING,
            automatic_attempted=True,
        )
        if running is None:
            raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
        profile_dir = self._profile_root / running.id
        profile_dir.mkdir(parents=True, exist_ok=False)
        self._schedule_expiry(running)
        handle = None
        try:
            handle = await self._driver.start(
                profile_dir=profile_dir,
                initial_url=target_url,
                allowed_origins=set(running.allowed_origins),
            )
            self._handles[running.id] = handle
            if not run_automatic_probe:
                return self._await_manual(running, reason='automatic_attempt_disabled')
            result = await self._driver.automatic_probe(handle)
        except Exception as exc:
            await self._close_handle(running.id)
            current = self._repo.get(running.id)
            if current is not None and not self._is_open(current):
                return current
            failed = self._repo.transition_state(
                running.id,
                expected_states=(InteractiveBrowserState.AUTOMATIC_RUNNING,),
                state=InteractiveBrowserState.FAILED,
                terminal_reason='browser_unavailable',
                closed_at=self._now(),
            )
            if failed is None:
                latest = self._repo.get(running.id)
                return latest or running
            self._repo.record_event(
                session_id=failed.id,
                event_type='automatic_attempt_failed',
                actor_id=failed.owner_id,
                detail={'reason': 'browser_unavailable'},
            )
            return failed

        current = self._repo.get(running.id)
        if current is None or not self._is_open(current):
            await self._close_handle(running.id)
            return current or running
        if result.state == 'needs_manual':
            return self._await_manual(current, reason=result.reason or 'verification_required')
        succeeded = self._repo.transition_state(
            current.id,
            expected_states=(InteractiveBrowserState.AUTOMATIC_RUNNING,),
            state=InteractiveBrowserState.SUCCEEDED,
            terminal_reason=None,
        )
        if succeeded is None:
            latest = self._repo.get(current.id)
            return latest or current
        self._repo.record_event(
            session_id=succeeded.id,
            event_type='automatic_attempt_succeeded',
            actor_id=succeeded.owner_id,
            detail={},
        )
        return succeeded

    def _await_manual(self, session: InteractiveBrowserSession, *, reason: str) -> InteractiveBrowserSession:
        awaiting = self._repo.transition_state(
            session.id,
            expected_states=(session.state,),
            state=InteractiveBrowserState.AWAITING_MANUAL,
            automatic_attempted=True,
            terminal_reason=reason,
        )
        if awaiting is None:
            raise InteractiveBrowserValidationConflictError('interactive_browser_session_state_conflict')
        self._repo.record_event(
            session_id=awaiting.id,
            event_type='manual_verification_required',
            actor_id=awaiting.owner_id,
            detail={'reason': reason},
        )
        return awaiting

    async def _close_handle(self, session_id: str) -> None:
        self._cancel_expiry_task(session_id)
        handle = self._handles.pop(session_id, None)
        try:
            if handle is not None:
                await self._driver.close(handle)
        finally:
            self._remove_profile(session_id)

    @staticmethod
    async def _run_browser_probe(handle: Any, source_rule: dict, keyword: str) -> BrowserValidationResult:
        raise InteractiveBrowserUnavailableError("interactive browser probe adapter is not configured")

    @staticmethod
    def _allowed_origins(target_url: str) -> set[str]:
        parsed = urlsplit(target_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('target_url must be an absolute HTTP URL')
        return {f'{parsed.scheme}://{parsed.netloc}'}

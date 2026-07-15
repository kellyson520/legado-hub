from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from secrets import token_urlsafe
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
class BrowserValidationResult:
    passed: bool
    reason: str = ''
    stages: dict[str, dict] | None = None

    @classmethod
    def passed(cls, stages: dict[str, dict]) -> 'BrowserValidationResult':
        return cls(passed=True, stages=stages)

    @classmethod
    def failed(cls, reason: str, stages: dict[str, dict]) -> 'BrowserValidationResult':
        return cls(passed=False, reason=reason, stages=stages)


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
    ):
        self._repo = repo
        self._driver = driver
        self._settings = settings
        self._profile_root = Path(profile_root)
        self._handles: dict[str, Any] = {}
        self._probe_runner = probe_runner or self._run_browser_probe
        self._token_factory = token_factory

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
            handle = self._handles.get(session.id)
            if handle is None:
                return BrowserVerificationResult.unavailable('browser_session_unavailable')
            validation = await self._probe_runner(handle, source_rule, keyword)
            if validation.passed:
                await self._close_handle(session.id)
                completed = self._repo.update_state(
                    session.id,
                    state=InteractiveBrowserState.SUCCEEDED,
                    closed_at=datetime.now(timezone.utc),
                )
                self._repo.record_event(
                    session_id=completed.id,
                    event_type='automatic_validation_succeeded',
                    actor_id=completed.owner_id,
                    detail={'stages': validation.stages or {}},
                )
                return BrowserVerificationResult.validated(completed.id, validation)
            if validation.reason == 'verification_required':
                awaiting = self._await_manual(session, reason=validation.reason)
                return BrowserVerificationResult.needs_manual(awaiting.id, awaiting.terminal_reason or validation.reason)
            await self._close_handle(session.id)
            failed = self._repo.update_state(
                session.id,
                state=InteractiveBrowserState.FAILED,
                terminal_reason=validation.reason or 'browser_validation_failed',
                closed_at=datetime.now(timezone.utc),
            )
            return BrowserVerificationResult.unavailable(failed.terminal_reason or 'browser_validation_failed')
        return BrowserVerificationResult.unavailable(session.terminal_reason or 'browser_unavailable')

    def get_for_owner(self, session_id: str, *, owner_id: str) -> InteractiveBrowserSession | None:
        return self._repo.get_for_owner(session_id, owner_id)

    async def cancel(self, session_id: str, *, owner_id: str) -> InteractiveBrowserSession:
        session = self._repo.get_for_owner(session_id, owner_id)
        if session is None:
            raise KeyError(session_id)
        await self._close_handle(session.id)
        cancelled = self._repo.update_state(
            session.id,
            state=InteractiveBrowserState.CANCELLED,
            terminal_reason='cancelled_by_owner',
            closed_at=datetime.now(timezone.utc),
        )
        self._repo.record_event(
            session_id=cancelled.id,
            event_type='session_cancelled',
            actor_id=owner_id,
            detail={},
        )
        return cancelled

    def issue_relay_ticket(self, session_id: str, *, owner_id: str) -> BrowserRelayTicket:
        session = self._repo.get_for_owner(session_id, owner_id)
        if session is None:
            raise KeyError(session_id)
        if session.state != InteractiveBrowserState.AWAITING_MANUAL:
            raise ValueError('interactive_browser_not_awaiting_manual_verification')
        handle = self._handles.get(session.id)
        relay_port = getattr(handle, 'relay_port', None)
        if handle is None or not isinstance(relay_port, int) or relay_port < 1:
            raise InteractiveBrowserUnavailableError('browser_session_unavailable')
        token = str(self._token_factory())
        expires_at = session.expires_at or (datetime.now(timezone.utc) + timedelta(minutes=1))
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
    ) -> BrowserValidationResult:
        session = self._repo.get_for_owner(session_id, owner_id)
        if session is None:
            raise KeyError(session_id)
        if session.state != InteractiveBrowserState.AWAITING_MANUAL:
            raise ValueError('interactive_browser_not_awaiting_manual_verification')
        handle = self._handles.get(session.id)
        if handle is None:
            raise InteractiveBrowserUnavailableError('browser_session_unavailable')
        self._repo.update_state(session.id, state=InteractiveBrowserState.VALIDATING)
        validation = await self._probe_runner(handle, source_rule, keyword)
        if validation.passed:
            await self._close_handle(session.id)
            completed = self._repo.update_state(
                session.id,
                state=InteractiveBrowserState.SUCCEEDED,
                closed_at=datetime.now(timezone.utc),
            )
            self._repo.record_event(
                session_id=completed.id,
                event_type='manual_validation_succeeded',
                actor_id=owner_id,
                detail={'stages': validation.stages or {}},
            )
            return validation
        if validation.reason == 'verification_required':
            self._repo.update_state(
                session.id,
                state=InteractiveBrowserState.AWAITING_MANUAL,
                terminal_reason=validation.reason,
            )
            return validation
        await self._close_handle(session.id)
        failed = self._repo.update_state(
            session.id,
            state=InteractiveBrowserState.FAILED,
            terminal_reason=validation.reason or 'browser_validation_failed',
            closed_at=datetime.now(timezone.utc),
        )
        self._repo.record_event(
            session_id=failed.id,
            event_type='manual_validation_failed',
            actor_id=owner_id,
            detail={'reason': failed.terminal_reason},
        )
        return validation

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
    async def _run_browser_probe(handle: Any, source_rule: dict, keyword: str) -> BrowserValidationResult:
        from app.application.services.source_probe_service import SourceProbeService
        from app.infrastructure.browser.browser_http_client import BrowserHttpClient
        from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher

        source = {**source_rule}
        source.setdefault('id', 0)
        probe = SourceProbeService(
            fetcher=LegadoBookSourceFetcher(
                http_client=BrowserHttpClient(
                    page=handle.page,
                    allowed_origins=set(handle.allowed_origins),
                )
            )
        )
        try:
            evidence = await probe.probe_source(source, keyword_samples=[keyword], probe_mode='full_chain')
        finally:
            await probe.aclose()
        stages = {
            'search': {'status': evidence.search.status, 'hit_count': evidence.search.hit_count},
            'toc': {'status': evidence.toc.status, 'hit_count': evidence.toc.hit_count},
            'content': {
                'status': evidence.content.status,
                'content_length': int(evidence.content.detail.get('content_length', 0) or 0),
            },
        }
        if evidence.content.detail.get('block_reason') == 'verification_wall':
            return BrowserValidationResult.failed('verification_required', stages)
        if evidence.search.status != 'ok' or evidence.search.hit_count < 1:
            return BrowserValidationResult.failed('search_failed', stages)
        if evidence.toc.status != 'ok' or evidence.toc.hit_count < 1:
            return BrowserValidationResult.failed('toc_failed', stages)
        if evidence.content.status != 'ok' or stages['content']['content_length'] < 80:
            return BrowserValidationResult.failed('content_failed', stages)
        return BrowserValidationResult.passed(stages)

    @staticmethod
    def _allowed_origins(target_url: str) -> set[str]:
        parsed = urlsplit(target_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('target_url must be an absolute HTTP URL')
        return {f'{parsed.scheme}://{parsed.netloc}'}

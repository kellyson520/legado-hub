import pytest


class RecordingDriver:
    def __init__(self):
        self.start_calls = []
        self.closed_handles = []

    async def start(self, *, profile_dir, initial_url, allowed_origins):
        handle = type('Handle', (), {'id': 'browser-handle-1', 'profile_dir': profile_dir, 'relay_port': 43003})()
        self.start_calls.append({
            'profile_dir': profile_dir,
            'initial_url': initial_url,
            'allowed_origins': allowed_origins,
            'handle': handle,
        })
        return handle

    async def automatic_probe(self, handle):
        from app.application.services.interactive_browser_service import BrowserAttemptResult

        return BrowserAttemptResult.needs_manual('verification_required')

    async def close(self, handle):
        self.closed_handles.append(handle.id)


class FakeSessionRepository:
    def __init__(self):
        self.sessions = {}
        self.events = []

    def create(self, session):
        self.sessions[session.id] = session
        return session

    def find_active_for_source(self, source_version_id, owner_id):
        return next(
            (
                session for session in self.sessions.values()
                if session.source_version_id == source_version_id
                and session.owner_id == owner_id
                and session.state.value in {'pending', 'automatic_running', 'awaiting_manual_verification', 'validating'}
            ),
            None,
        )

    def get_for_owner(self, session_id, owner_id):
        session = self.sessions.get(session_id)
        return session if session is not None and session.owner_id == owner_id else None

    def issue_relay_token(self, *, session_id, owner_id, raw_token, expires_at):
        self.relay_token = (session_id, owner_id, raw_token, expires_at)

    def count_active(self):
        return sum(
            session.state.value in {'pending', 'automatic_running', 'awaiting_manual_verification', 'validating'}
            for session in self.sessions.values()
        )

    def update_state(self, session_id, *, state, automatic_attempted=None, terminal_reason=None, closed_at=None):
        session = self.sessions[session_id]
        updated = type(session)(
            id=session.id,
            source_version_id=session.source_version_id,
            owner_id=session.owner_id,
            allowed_origins=session.allowed_origins,
            state=state,
            automatic_attempted=session.automatic_attempted if automatic_attempted is None else automatic_attempted,
            expires_at=session.expires_at,
            closed_at=closed_at,
            terminal_reason=terminal_reason,
            created_at=session.created_at,
        )
        self.sessions[session_id] = updated
        return updated

    def record_event(self, **kwargs):
        self.events.append(kwargs)


class EnabledSettings:
    def get_interactive_browser_settings(self):
        return {
            'enabled': True,
            'automatic_enabled': True,
            'max_sessions': 1,
            'session_timeout_seconds': 300,
        }


class OneSessionSettings(EnabledSettings):
    def get_interactive_browser_settings(self):
        return {**super().get_interactive_browser_settings(), 'max_sessions': 1}


class SuccessfulDriver(RecordingDriver):
    async def automatic_probe(self, handle):
        from app.application.services.interactive_browser_service import BrowserAttemptResult

        return BrowserAttemptResult.succeeded()


@pytest.mark.asyncio
async def test_start_or_resume_uses_one_standard_browser_then_waits_for_manual(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
    )

    session = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )
    repeated = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    assert session.state == InteractiveBrowserState.AWAITING_MANUAL
    assert repeated.id == session.id
    assert len(driver.start_calls) == 1
    assert driver.start_calls[0]['allowed_origins'] == {'https://books.example.test'}
    assert repo.events[-1]['event_type'] == 'manual_verification_required'


@pytest.mark.asyncio
async def test_start_or_resume_rejects_a_second_candidate_when_session_capacity_is_reached(tmp_path):
    from app.application.services.interactive_browser_service import (
        InteractiveBrowserService,
        InteractiveBrowserUnavailableError,
    )

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=OneSessionSettings(),
        profile_root=tmp_path,
    )

    await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    with pytest.raises(InteractiveBrowserUnavailableError, match='interactive_browser_capacity_reached'):
        await service.start_or_resume(
            source_version_id='source-version-2',
            owner_id='42',
            target_url='https://books.example.test/book/2',
        )

    assert len(driver.start_calls) == 1


@pytest.mark.asyncio
async def test_attempt_automatic_returns_validated_only_after_browser_context_full_chain_passes(tmp_path):
    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )

    calls = []

    async def probe_runner(handle, source_rule, keyword):
        calls.append((handle.id, source_rule, keyword))
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 100},
        })

    service = InteractiveBrowserService(
        repo=FakeSessionRepository(),
        driver=SuccessfulDriver(),
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
    )

    result = await service.attempt_automatic(
        source_version_id='source-version-1',
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    )

    assert result.state == 'validated'
    assert result.validation is not None and result.validation.passed is True
    assert calls == [(
        'browser-handle-1',
        {'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        'sample',
    )]


@pytest.mark.asyncio
async def test_cancel_destroys_manual_browser_session_and_marks_it_cancelled(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
    )
    session = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    cancelled = await service.cancel(session.id, owner_id='42')

    assert cancelled.state == InteractiveBrowserState.CANCELLED
    assert driver.closed_handles == ['browser-handle-1']
    assert repo.events[-1]['event_type'] == 'session_cancelled'


@pytest.mark.asyncio
async def test_continue_validation_uses_manual_browser_context_then_destroys_session(tmp_path):
    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )

    async def probe_runner(_handle, _source_rule, _keyword):
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 120},
        })

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
    )
    session = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    validation = await service.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    )

    assert validation.passed is True
    assert repo.sessions[session.id].state.value == 'succeeded'
    assert driver.closed_handles == ['browser-handle-1']
    assert repo.events[-1]['event_type'] == 'manual_validation_succeeded'


def test_manual_session_issues_a_short_lived_relay_ticket_without_exposing_browser_storage(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        token_factory=lambda: 'relay-secret',
    )

    import asyncio

    session = asyncio.run(service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    ))
    ticket = service.issue_relay_ticket(session.id, owner_id='42')

    assert ticket.token == 'relay-secret'
    assert ticket.relay_port == 43003
    assert repo.relay_token[0:3] == (session.id, '42', 'relay-secret')

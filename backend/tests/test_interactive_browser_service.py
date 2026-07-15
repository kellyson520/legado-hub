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

    def get(self, session_id):
        return self.sessions.get(session_id)

    def list_active(self):
        return [
            session for session in self.sessions.values()
            if session.state.value in {'pending', 'automatic_running', 'awaiting_manual_verification', 'validating'}
        ]

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

    def transition_state(self, session_id, *, expected_states, state, automatic_attempted=None, terminal_reason=None, closed_at=None):
        session = self.sessions[session_id]
        if session.state not in set(expected_states):
            return None
        return self.update_state(
            session_id,
            state=state,
            automatic_attempted=automatic_attempted,
            terminal_reason=terminal_reason,
            closed_at=closed_at,
        )

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


class ManualOnlySettings(EnabledSettings):
    def get_interactive_browser_settings(self):
        return {**super().get_interactive_browser_settings(), 'automatic_enabled': False}


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
async def test_disabled_automatic_attempt_still_starts_standard_browser_for_manual_verification(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    class Driver(RecordingDriver):
        def __init__(self):
            super().__init__()
            self.automatic_probe_calls = 0

        async def automatic_probe(self, handle):
            self.automatic_probe_calls += 1
            return await super().automatic_probe(handle)

    repo = FakeSessionRepository()
    driver = Driver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=ManualOnlySettings(),
        profile_root=tmp_path,
    )

    session = await service.start_or_resume(
        source_version_id='source-version-manual-only',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    assert session.state == InteractiveBrowserState.AWAITING_MANUAL
    assert len(driver.start_calls) == 1
    assert driver.automatic_probe_calls == 0
    assert session.id in service._handles
    assert driver.start_calls[0]['profile_dir'].exists() is True

    await service.cancel(session.id, owner_id='42')


@pytest.mark.asyncio
async def test_automatic_session_lifecycle_uses_compare_and_set_transitions(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService

    class CasOnlyRepository(FakeSessionRepository):
        def update_state(self, *_args, **_kwargs):
            raise AssertionError('automatic lifecycle must use transition_state')

        def transition_state(self, session_id, *, expected_states, state, automatic_attempted=None, terminal_reason=None, closed_at=None):
            session = self.sessions[session_id]
            if session.state not in set(expected_states):
                return None
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

    repo = CasOnlyRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
    )

    session = await service.start_or_resume(
        source_version_id='source-version-cas-auto',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    assert session.state.value == 'awaiting_manual_verification'
    await service.cancel(session.id, owner_id='42')


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
async def test_expiry_during_deferred_automatic_full_chain_cannot_be_overwritten_as_succeeded(tmp_path):
    import asyncio

    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    probe_started = asyncio.Event()
    release_probe = asyncio.Event()

    async def probe_runner(_handle, _source_rule, _keyword):
        probe_started.set()
        await release_probe.wait()
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 120},
        })

    repo = FakeSessionRepository()
    driver = SuccessfulDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
    )
    attempting = asyncio.create_task(service.attempt_automatic(
        source_version_id='source-version-auto-expiry',
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    ))
    await probe_started.wait()
    session_id = next(iter(repo.sessions))

    expiring = asyncio.create_task(service.expire_session(session_id))
    await asyncio.sleep(0)

    try:
        assert expiring.done() is False
    finally:
        release_probe.set()
    result = await attempting
    expired = await expiring

    assert expired.state == InteractiveBrowserState.SUCCEEDED
    assert result.state == 'validated'
    assert repo.sessions[session_id].state == InteractiveBrowserState.SUCCEEDED


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
    profile_dir = driver.start_calls[0]['profile_dir']

    cancelled = await service.cancel(session.id, owner_id='42')

    assert cancelled.state == InteractiveBrowserState.CANCELLED
    assert driver.closed_handles == ['browser-handle-1']
    assert profile_dir.exists() is False
    assert session.id not in service._expiry_tasks
    assert repo.events[-1]['event_type'] == 'session_cancelled'


@pytest.mark.asyncio
async def test_cancel_only_allows_awaiting_manual_sessions(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService

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
    await service.cancel(session.id, owner_id='42')

    with pytest.raises(ValueError, match='interactive_browser_not_awaiting_manual_verification'):
        await service.cancel(session.id, owner_id='42')

    assert repo.sessions[session.id].state.value == 'cancelled'
    assert driver.closed_handles == ['browser-handle-1']


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
    profile_dir = driver.start_calls[0]['profile_dir']

    validation = await service.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    )

    assert validation.passed is True
    assert repo.sessions[session.id].state.value == 'succeeded'
    assert driver.closed_handles == ['browser-handle-1']
    assert profile_dir.exists() is False
    assert session.id not in service._expiry_tasks
    assert repo.events[-1]['event_type'] == 'manual_validation_succeeded'


@pytest.mark.asyncio
async def test_failed_manual_validation_cleans_up_browser_profile_and_expiry_task(tmp_path):
    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    async def probe_runner(_handle, _source_rule, _keyword):
        return BrowserValidationResult.failed('content_failed', {
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'failed', 'content_length': 0},
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
    profile_dir = driver.start_calls[0]['profile_dir']

    validation = await service.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    )

    assert validation.passed is False
    assert repo.sessions[session.id].state == InteractiveBrowserState.FAILED
    assert driver.closed_handles == ['browser-handle-1']
    assert profile_dir.exists() is False
    assert session.id not in service._expiry_tasks


@pytest.mark.asyncio
async def test_audit_acceptance_failure_keeps_manual_browser_session_open_for_retry(tmp_path):
    from copy import deepcopy

    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
        InteractiveBrowserValidationAcceptanceError,
    )
    from app.application.services.source_build_audit_service import SourceBuildAuditService
    from app.domain.entities.source_runtime import SourceVersion

    class Runtime:
        def __init__(self, version):
            self.version = version
            self.fail_test_runs = 1
            self.runs = []

        def get_version(self, version_id):
            return self.version if version_id == self.version.id else None

        def update_version_payload(self, version_id, payload):
            assert version_id == self.version.id
            self.version.payload = deepcopy(payload)
            return self.version

        def record_test_run(self, **kwargs):
            if self.fail_test_runs:
                self.fail_test_runs -= 1
                raise RuntimeError('test run persistence unavailable')
            self.runs.append(kwargs)

        def list_test_runs(self, source_version_id=None):
            return [
                run for run in self.runs
                if source_version_id is None or run['source_version_id'] == source_version_id
            ]

    async def probe_runner(_handle, _source_rule, _keyword):
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 120},
        })

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    browser = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
    )
    session = await browser.start_or_resume(
        source_version_id='candidate-manual-retry',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )
    profile_dir = driver.start_calls[0]['profile_dir']
    version = SourceVersion(
        id=session.source_version_id,
        source_definition_id=17,
        source_type='book',
        source_id='https://books.example.test',
        status='candidate',
        payload={
            'source_audit': {
                'status': 'awaiting_manual_verification',
                'attempt': 1,
                'max_attempts': 5,
                'browser_session_id': session.id,
                'history': [],
            },
        },
    )
    runtime = Runtime(version)
    audit = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=None,
        build_service=None,
        review_service=None,
    )

    def accept(validation):
        return audit.accept_manual_browser_validation(
            version.id,
            browser_session_id=session.id,
            validation=validation,
        )

    with pytest.raises(InteractiveBrowserValidationAcceptanceError, match='source_audit_acceptance_failed'):
        await browser.continue_validation(
            session.id,
            owner_id='42',
            source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            keyword='sample',
            on_success=accept,
        )

    assert repo.sessions[session.id].state.value == 'awaiting_manual_verification'
    assert session.id in browser._handles
    assert driver.closed_handles == []
    assert profile_dir.exists() is True
    assert version.payload['source_audit']['status'] == 'awaiting_manual_verification'

    validation = await browser.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
        on_success=accept,
    )

    assert validation.passed is True
    assert repo.sessions[session.id].state.value == 'succeeded'
    assert version.payload['source_audit']['status'] == 'passed'
    assert driver.closed_handles == ['browser-handle-1']


@pytest.mark.asyncio
async def test_recovery_pending_audit_callback_completes_manual_browser_session_instead_of_restoring_awaiting(tmp_path):
    from copy import deepcopy

    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )
    from app.application.services.source_build_audit_service import (
        ManualBrowserValidationRecoveryPending,
        SourceBuildAuditService,
    )
    from app.domain.entities.source_runtime import SourceVersion

    class Runtime:
        def __init__(self, version):
            self.version = version
            self.runs = []
            self.payload_update_count = 0

        def get_version(self, version_id):
            return self.version if version_id == self.version.id else None

        def update_version_payload(self, version_id, payload):
            assert version_id == self.version.id
            self.payload_update_count += 1
            if self.payload_update_count == 2:
                raise RuntimeError('rollback persistence unavailable')
            self.version.payload = deepcopy(payload)
            return self.version

        def record_test_run(self, **_kwargs):
            raise RuntimeError('test run persistence unavailable')

        def list_test_runs(self, _source_version_id=None):
            return list(self.runs)

    async def probe_runner(_handle, _source_rule, _keyword):
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 120},
        })

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    browser = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
    )
    session = await browser.start_or_resume(
        source_version_id='candidate-manual-recovery-pending',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )
    version = SourceVersion(
        id=session.source_version_id,
        source_definition_id=17,
        source_type='book',
        source_id='https://books.example.test',
        status='candidate',
        payload={
            'source_audit': {
                'status': 'awaiting_manual_verification',
                'attempt': 1,
                'max_attempts': 5,
                'browser_session_id': session.id,
                'history': [],
            },
        },
    )
    audit = SourceBuildAuditService(
        runtime_repo=Runtime(version),
        probe_service_factory=None,
        build_service=None,
        review_service=None,
    )
    callback_result = {}

    def accept_in_router_callback(validation):
        try:
            callback_result['audit'] = audit.accept_manual_browser_validation(
                version.id,
                browser_session_id=session.id,
                validation=validation,
            )
        except ManualBrowserValidationRecoveryPending as outcome:
            callback_result['audit'] = outcome.audit_result
            callback_result['recovery_pending'] = True

    validation = await browser.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
        on_success=accept_in_router_callback,
    )

    assert validation.passed is True
    assert callback_result['recovery_pending'] is True
    assert callback_result['audit']['recovery_pending'] is True
    assert repo.sessions[session.id].state.value == 'succeeded'
    assert session.id not in browser._handles
    assert driver.closed_handles == ['browser-handle-1']


@pytest.mark.asyncio
async def test_cancel_during_deferred_manual_probe_returns_conflict_without_overwriting_validation(tmp_path):
    import asyncio

    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )

    probe_started = asyncio.Event()
    release_probe = asyncio.Event()

    async def probe_runner(_handle, _source_rule, _keyword):
        probe_started.set()
        await release_probe.wait()
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
    continuing = asyncio.create_task(service.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    ))
    await probe_started.wait()

    with pytest.raises(ValueError, match='interactive_browser_validation_in_progress'):
        await service.cancel(session.id, owner_id='42')

    release_probe.set()
    validation = await continuing

    assert validation.passed is True
    assert repo.sessions[session.id].state.value == 'succeeded'


@pytest.mark.asyncio
async def test_expiry_waits_for_deferred_manual_probe_and_does_not_overwrite_it(tmp_path):
    import asyncio

    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )

    probe_started = asyncio.Event()
    release_probe = asyncio.Event()

    async def probe_runner(_handle, _source_rule, _keyword):
        probe_started.set()
        await release_probe.wait()
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
    continuing = asyncio.create_task(service.continue_validation(
        session.id,
        owner_id='42',
        source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        keyword='sample',
    ))
    await probe_started.wait()
    expiring = asyncio.create_task(service.expire_session(session.id))
    await asyncio.sleep(0)

    assert expiring.done() is False
    release_probe.set()
    validation = await continuing
    expired = await expiring

    assert validation.passed is True
    assert expired.state.value == 'succeeded'
    assert repo.sessions[session.id].state.value == 'succeeded'


@pytest.mark.asyncio
async def test_manual_validation_timeout_expires_and_cleans_up_without_long_sleep(tmp_path):
    import asyncio

    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    async def never_completes(_handle, _source_rule, _keyword):
        await asyncio.Event().wait()

    async def immediate_timeout(awaitable, _timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=never_completes,
        probe_waiter=immediate_timeout,
    )
    session = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )

    with pytest.raises(ValueError, match='interactive_browser_session_expired'):
        await service.continue_validation(
            session.id,
            owner_id='42',
            source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            keyword='sample',
        )

    assert repo.sessions[session.id].state == InteractiveBrowserState.EXPIRED
    assert driver.closed_handles == ['browser-handle-1']
    assert session.id not in service._expiry_tasks


@pytest.mark.asyncio
async def test_expiring_manual_session_closes_browser_removes_profile_and_rejects_further_use(tmp_path):
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
    profile_dir = driver.start_calls[0]['profile_dir']

    expired = await service.expire_session(session.id)

    assert expired.state == InteractiveBrowserState.EXPIRED
    assert expired.terminal_reason == 'session_expired'
    assert driver.closed_handles == ['browser-handle-1']
    assert profile_dir.exists() is False
    assert repo.events[-1]['event_type'] == 'session_expired'
    with pytest.raises(KeyError):
        service.issue_relay_ticket(session.id, owner_id='42')
    with pytest.raises(KeyError):
        await service.continue_validation(
            session.id,
            owner_id='42',
            source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            keyword='sample',
        )


@pytest.mark.asyncio
async def test_new_session_schedules_expiry_without_waiting_for_wall_clock(tmp_path):
    import asyncio
    from datetime import datetime, timezone

    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    release_expiry = asyncio.Event()
    sleep_calls = []

    async def controlled_sleep(delay):
        sleep_calls.append(delay)
        await release_expiry.wait()

    repo = FakeSessionRepository()
    driver = RecordingDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        expiry_sleep=controlled_sleep,
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    session = await service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )
    await asyncio.sleep(0)

    assert sleep_calls == [300]
    release_expiry.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert repo.sessions[session.id].state == InteractiveBrowserState.EXPIRED
    assert driver.closed_handles == ['browser-handle-1']


@pytest.mark.asyncio
async def test_expiry_during_browser_start_cannot_be_overwritten_by_automatic_flow(tmp_path):
    import asyncio

    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    allow_browser_start = asyncio.Event()
    expiry_waiting = asyncio.Event()
    trigger_expiry = asyncio.Event()

    class DelayedStartDriver(RecordingDriver):
        async def start(self, *, profile_dir, initial_url, allowed_origins):
            await allow_browser_start.wait()
            return await super().start(
                profile_dir=profile_dir,
                initial_url=initial_url,
                allowed_origins=allowed_origins,
            )

    async def controlled_sleep(_delay):
        expiry_waiting.set()
        await trigger_expiry.wait()

    repo = FakeSessionRepository()
    driver = DelayedStartDriver()
    service = InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        expiry_sleep=controlled_sleep,
    )
    starting = asyncio.create_task(service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    ))
    await expiry_waiting.wait()
    trigger_expiry.set()
    await asyncio.sleep(0)
    assert next(iter(repo.sessions.values())).state == InteractiveBrowserState.EXPIRED

    allow_browser_start.set()
    session = await starting

    assert session.state == InteractiveBrowserState.EXPIRED
    assert repo.sessions[session.id].state == InteractiveBrowserState.EXPIRED
    assert driver.closed_handles == ['browser-handle-1']


@pytest.mark.asyncio
async def test_rebuilt_service_expires_persisted_open_session_and_removes_profile(tmp_path):
    from app.application.services.interactive_browser_service import InteractiveBrowserService
    from app.domain.entities.interactive_browser import InteractiveBrowserState

    repo = FakeSessionRepository()
    first_driver = RecordingDriver()
    first_service = InteractiveBrowserService(
        repo=repo,
        driver=first_driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
    )
    session = await first_service.start_or_resume(
        source_version_id='source-version-1',
        owner_id='42',
        target_url='https://books.example.test/book/1',
    )
    profile_dir = first_driver.start_calls[0]['profile_dir']

    InteractiveBrowserService(
        repo=repo,
        driver=RecordingDriver(),
        settings=EnabledSettings(),
        profile_root=tmp_path,
    )

    assert repo.sessions[session.id].state == InteractiveBrowserState.EXPIRED
    assert repo.sessions[session.id].terminal_reason == 'service_restarted'
    assert profile_dir.exists() is False
    assert repo.events[-1]['event_type'] == 'session_expired'
    first_service._cancel_expiry_task(session.id)


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

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _headers(user_id: str, permissions: list[str]) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token({'sub': user_id, 'permissions': permissions, 'sid': f'browser-{user_id}'})
    return {'Authorization': f'Bearer {token}'}


def test_owner_can_read_and_cancel_only_their_interactive_browser_session(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-api.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.application.services.interactive_browser_service import BrowserValidationResult
    from app.application.services.interactive_browser_service import BrowserRelayTicket
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    source_version = SQLiteSourceRuntimeRepository().create_candidate_version(
        source_type='book',
        source_id='https://books.example.test',
        payload={
            'keyword': 'sample',
            'source_rule': {'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            'source_audit': {
                'status': 'awaiting_manual_verification',
                'attempt': 1,
                'max_attempts': 5,
                'browser_session_id': 'browser-session-1',
                'history': [],
            },
        },
        created_by='console:42',
    )

    class BrowserService:
        def __init__(self):
            self.session = InteractiveBrowserSession.new(
                source_version_id=source_version.id,
                owner_id='42',
                allowed_origins=['https://books.example.test'],
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            self.session = type(self.session)(
                **{**self.session.__dict__, 'id': 'browser-session-1', 'state': InteractiveBrowserState.AWAITING_MANUAL}
            )
            self.cancel_calls = []
            self.cancel_conflict = False
            self.continue_calls = []
            self.success_callbacks = []
            self.continue_unavailable = False
            self.relay_calls = []
            self.relay_unavailable = False

        async def get_for_owner(self, session_id, *, owner_id):
            if session_id == self.session.id and owner_id == self.session.owner_id:
                return self.session
            return None

        async def cancel(self, session_id, *, owner_id):
            if self.cancel_conflict:
                raise ValueError('interactive_browser_validation_in_progress')
            self.cancel_calls.append((session_id, owner_id))
            return type(self.session)(
                **{**self.session.__dict__, 'state': InteractiveBrowserState.CANCELLED}
            )

        async def continue_validation(self, session_id, *, owner_id, source_rule, keyword, on_success=None):
            if self.continue_unavailable:
                from app.application.services.interactive_browser_service import InteractiveBrowserUnavailableError

                raise InteractiveBrowserUnavailableError('browser_session_unavailable')
            self.continue_calls.append((session_id, owner_id, source_rule, keyword))
            self.success_callbacks.append(on_success)
            validation = BrowserValidationResult.passed({
                'search': {'status': 'ok', 'hit_count': 1},
                'toc': {'status': 'ok', 'hit_count': 1},
                'content': {'status': 'ok', 'content_length': 120},
            })
            if on_success is not None:
                on_success(validation)
            return validation

        async def issue_relay_ticket(self, session_id, *, owner_id):
            if self.relay_unavailable:
                from app.application.services.interactive_browser_service import InteractiveBrowserUnavailableError

                raise InteractiveBrowserUnavailableError('browser_session_unavailable')
            self.relay_calls.append((session_id, owner_id))
            return BrowserRelayTicket(session_id=session_id, token='relay-secret', relay_port=43003)

    service = BrowserService()
    monkeypatch.setattr(
        'app.interfaces.http.interactive_browser.build_interactive_browser_service',
        lambda: service,
    )
    client = TestClient(app, raise_server_exceptions=False)
    owner_headers = _headers('42', ['engine.test'])
    other_headers = _headers('99', ['engine.test'])

    owner = client.get('/api/interactive-browser/sessions/browser-session-1', headers=owner_headers)
    other = client.get('/api/interactive-browser/sessions/browser-session-1', headers=other_headers)
    service.relay_unavailable = True
    unavailable_relay = client.post('/api/interactive-browser/sessions/browser-session-1/relay-ticket', headers=owner_headers)
    service.relay_unavailable = False
    relay = client.post('/api/interactive-browser/sessions/browser-session-1/relay-ticket', headers=owner_headers)
    service.continue_unavailable = True
    unavailable_continue = client.post('/api/interactive-browser/sessions/browser-session-1/continue', headers=owner_headers)
    service.continue_unavailable = False
    continued = client.post('/api/interactive-browser/sessions/browser-session-1/continue', headers=owner_headers)
    repeated_continue = client.post('/api/interactive-browser/sessions/browser-session-1/continue', headers=owner_headers)
    service.cancel_conflict = True
    cancelled_during_validation = client.delete('/api/interactive-browser/sessions/browser-session-1', headers=owner_headers)
    service.cancel_conflict = False
    cancelled = client.delete('/api/interactive-browser/sessions/browser-session-1', headers=owner_headers)

    assert owner.status_code == 200
    assert owner.json()['data']['state'] == 'awaiting_manual_verification'
    assert other.status_code == 404
    assert unavailable_relay.status_code == 409
    assert unavailable_relay.json()['detail'] == 'browser_session_unavailable'
    assert relay.status_code == 200
    assert relay.json()['data']['relay_path'].endswith('token=relay-secret&owner_id=42')
    assert continued.status_code == 200
    assert unavailable_continue.status_code == 409
    assert unavailable_continue.json()['detail'] == 'browser_session_unavailable'
    assert continued.json()['data']['validation']['passed'] is True
    assert continued.json()['data']['audit']['status'] == 'passed'
    accepted_version = SQLiteSourceRuntimeRepository().get_version(source_version.id)
    assert accepted_version.payload['source_audit']['status'] == 'passed'
    accepted_runs = SQLiteSourceRuntimeRepository().list_test_runs(source_version.id)
    assert len(accepted_runs) == 1
    assert accepted_runs[0].grade == 'A'
    assert service.success_callbacks[0] is not None
    assert repeated_continue.status_code == 409
    assert repeated_continue.json()['detail'] == 'source_audit_not_awaiting_manual_verification'
    assert cancelled_during_validation.status_code == 409
    assert cancelled_during_validation.json()['detail'] == 'interactive_browser_validation_in_progress'
    assert cancelled.status_code == 200
    assert cancelled.json()['data']['state'] == 'cancelled'
    assert service.cancel_calls == [('browser-session-1', '42')]
    assert service.relay_calls == [('browser-session-1', '42')]
    assert service.continue_calls == [(
        'browser-session-1',
        '42',
        {'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        'sample',
    )] * 2


def test_continue_returns_recovery_pending_after_a_persisted_manual_audit_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-recovery-api.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.interactive_browser_service import BrowserValidationResult
    from app.application.services.source_build_audit_service import ManualBrowserValidationRecoveryPending
    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    source_version = SQLiteSourceRuntimeRepository().create_candidate_version(
        source_type='book',
        source_id='https://books.example.test',
        payload={
            'keyword': 'sample',
            'source_rule': {'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            'source_audit': {
                'status': 'awaiting_manual_verification',
                'attempt': 1,
                'max_attempts': 5,
                'browser_session_id': 'browser-session-recovery',
                'history': [],
            },
        },
        created_by='console:42',
    )

    class BrowserService:
        def __init__(self):
            session = InteractiveBrowserSession.new(
                source_version_id=source_version.id,
                owner_id='42',
                allowed_origins=['https://books.example.test'],
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            self.session = type(session)(
                **{
                    **session.__dict__,
                    'id': 'browser-session-recovery',
                    'state': InteractiveBrowserState.AWAITING_MANUAL,
                }
            )

        async def get_for_owner(self, session_id, *, owner_id):
            if session_id == self.session.id and owner_id == self.session.owner_id:
                return self.session
            return None

        async def continue_validation(self, session_id, *, owner_id, source_rule, keyword, on_success=None):
            assert session_id == self.session.id
            assert owner_id == self.session.owner_id
            assert source_rule['id'] == 17
            assert keyword == 'sample'
            validation = BrowserValidationResult.passed({
                'search': {'status': 'ok', 'hit_count': 1},
                'toc': {'status': 'ok', 'hit_count': 1},
                'content': {'status': 'ok', 'content_length': 120},
            })
            on_success(validation)
            self.session = type(self.session)(
                **{**self.session.__dict__, 'state': InteractiveBrowserState.SUCCEEDED}
            )
            return validation

    class RecoveryAuditService:
        def accept_manual_browser_validation(self, source_version_id, *, browser_session_id, validation):
            assert source_version_id == source_version.id
            assert browser_session_id == 'browser-session-recovery'
            assert validation.passed is True
            raise ManualBrowserValidationRecoveryPending({
                'source_version_id': source_version.id,
                'status': 'passed',
                'score': 100,
                'grade': 'A',
                'report': {'browser_validation': True},
                'recovery_pending': True,
            })

    service = BrowserService()
    monkeypatch.setattr(
        'app.interfaces.http.interactive_browser.build_interactive_browser_service',
        lambda: service,
    )
    monkeypatch.setattr(
        'app.interfaces.http.interactive_browser.build_source_build_audit_service',
        RecoveryAuditService,
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        '/api/interactive-browser/sessions/browser-session-recovery/continue',
        headers=_headers('42', ['engine.test']),
    )

    assert response.status_code == 202
    assert response.json()['data']['recovery_pending'] is True
    assert response.json()['data']['audit']['status'] == 'passed'
    assert response.json()['data']['session']['state'] == 'succeeded'

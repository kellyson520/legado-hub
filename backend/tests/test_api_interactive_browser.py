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
            self.continue_calls = []
            self.relay_calls = []

        def get_for_owner(self, session_id, *, owner_id):
            if session_id == self.session.id and owner_id == self.session.owner_id:
                return self.session
            return None

        async def cancel(self, session_id, *, owner_id):
            self.cancel_calls.append((session_id, owner_id))
            return type(self.session)(
                **{**self.session.__dict__, 'state': InteractiveBrowserState.CANCELLED}
            )

        async def continue_validation(self, session_id, *, owner_id, source_rule, keyword):
            self.continue_calls.append((session_id, owner_id, source_rule, keyword))
            return BrowserValidationResult.passed({
                'search': {'status': 'ok', 'hit_count': 1},
                'toc': {'status': 'ok', 'hit_count': 1},
                'content': {'status': 'ok', 'content_length': 120},
            })

        def issue_relay_ticket(self, session_id, *, owner_id):
            self.relay_calls.append((session_id, owner_id))
            return BrowserRelayTicket(session_id=session_id, token='relay-secret', relay_port=43003)

    service = BrowserService()
    monkeypatch.setattr(
        'app.interfaces.http.interactive_browser.build_interactive_browser_service',
        lambda: service,
    )
    client = TestClient(app)
    owner_headers = _headers('42', ['engine.test'])
    other_headers = _headers('99', ['engine.test'])

    owner = client.get('/api/interactive-browser/sessions/browser-session-1', headers=owner_headers)
    other = client.get('/api/interactive-browser/sessions/browser-session-1', headers=other_headers)
    relay = client.post('/api/interactive-browser/sessions/browser-session-1/relay-ticket', headers=owner_headers)
    continued = client.post('/api/interactive-browser/sessions/browser-session-1/continue', headers=owner_headers)
    cancelled = client.delete('/api/interactive-browser/sessions/browser-session-1', headers=owner_headers)

    assert owner.status_code == 200
    assert owner.json()['data']['state'] == 'awaiting_manual_verification'
    assert other.status_code == 404
    assert relay.status_code == 200
    assert relay.json()['data']['relay_path'].endswith('token=relay-secret&owner_id=42')
    assert continued.status_code == 200
    assert continued.json()['data']['validation']['passed'] is True
    assert cancelled.status_code == 200
    assert cancelled.json()['data']['state'] == 'cancelled'
    assert service.cancel_calls == [('browser-session-1', '42')]
    assert service.relay_calls == [('browser-session-1', '42')]
    assert service.continue_calls == [(
        'browser-session-1',
        '42',
        {'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
        'sample',
    )]

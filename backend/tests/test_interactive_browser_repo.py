from datetime import datetime, timedelta, timezone
import threading


def test_interactive_browser_session_is_owner_scoped_and_relay_token_is_single_use(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import (
        SQLiteInteractiveBrowserRepository,
    )
    from app.infrastructure.persistence.sqlite.schema import InteractiveBrowserSessionModel

    bootstrap_sqlite()
    repo = SQLiteInteractiveBrowserRepository()
    session = repo.create(
        InteractiveBrowserSession.new(
            source_version_id='source-version-1',
            owner_id='42',
            allowed_origins=['https://books.example.test'],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )

    repo.issue_relay_token(
        session_id=session.id,
        owner_id='42',
        raw_token='one-time-token',
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    assert session.state == InteractiveBrowserState.PENDING
    assert repo.get_for_owner(session.id, '42').id == session.id
    assert repo.get_for_owner(session.id, '99') is None
    assert repo.consume_relay_token('one-time-token', owner_id='42').id == session.id
    assert repo.consume_relay_token('one-time-token', owner_id='42') is None
    assert 'relay_token_digest' in InteractiveBrowserSessionModel.__table__.columns.keys()
    assert 'cookie' not in InteractiveBrowserSessionModel.__table__.columns.keys()
    assert 'page_html' not in InteractiveBrowserSessionModel.__table__.columns.keys()


def test_interactive_browser_repository_tracks_one_active_session_state(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-state.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import (
        SQLiteInteractiveBrowserRepository,
    )

    bootstrap_sqlite()
    repo = SQLiteInteractiveBrowserRepository()
    created = repo.create(
        InteractiveBrowserSession.new(
            source_version_id='source-version-1',
            owner_id='42',
            allowed_origins=['https://books.example.test'],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )

    updated = repo.update_state(
        created.id,
        state=InteractiveBrowserState.AWAITING_MANUAL,
        automatic_attempted=True,
    )

    assert updated.state == InteractiveBrowserState.AWAITING_MANUAL
    assert updated.automatic_attempted is True
    assert repo.find_active_for_source('source-version-1', '42').id == created.id


def test_expired_session_is_excluded_from_active_owner_lookup_capacity_and_source_resume(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-expired.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import (
        SQLiteInteractiveBrowserRepository,
    )

    bootstrap_sqlite()
    repo = SQLiteInteractiveBrowserRepository()
    expired = repo.create(
        InteractiveBrowserSession.new(
            source_version_id='source-version-expired',
            owner_id='42',
            allowed_origins=['https://books.example.test'],
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )

    assert repo.get_for_owner(expired.id, '42') is None
    assert repo.find_active_for_source('source-version-expired', '42') is None
    assert repo.count_active() == 0
    assert [session.id for session in repo.list_active()] == [expired.id]


def test_session_transition_compares_expected_state_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-transition.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import (
        SQLiteInteractiveBrowserRepository,
    )

    bootstrap_sqlite()
    repo = SQLiteInteractiveBrowserRepository()
    created = repo.create(
        InteractiveBrowserSession.new(
            source_version_id='source-version-transition',
            owner_id='42',
            allowed_origins=['https://books.example.test'],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    repo.update_state(created.id, state=InteractiveBrowserState.AWAITING_MANUAL)

    validating = repo.transition_state(
        created.id,
        expected_states=(InteractiveBrowserState.AWAITING_MANUAL,),
        state=InteractiveBrowserState.VALIDATING,
    )
    stale_transition = repo.transition_state(
        created.id,
        expected_states=(InteractiveBrowserState.AWAITING_MANUAL,),
        state=InteractiveBrowserState.CANCELLED,
    )

    assert validating is not None and validating.state == InteractiveBrowserState.VALIDATING
    assert stale_transition is None


def test_relay_token_consumption_is_single_winner_across_independent_transactions(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'interactive-browser-relay-race.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.domain.entities.interactive_browser import InteractiveBrowserSession, InteractiveBrowserState
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import (
        SQLiteInteractiveBrowserRepository,
    )

    bootstrap_sqlite()
    setup = SQLiteInteractiveBrowserRepository()
    session = setup.create(
        InteractiveBrowserSession.new(
            source_version_id='source-version-relay-race',
            owner_id='42',
            allowed_origins=['https://books.example.test'],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    setup.update_state(session.id, state=InteractiveBrowserState.AWAITING_MANUAL)
    setup.issue_relay_token(
        session_id=session.id,
        owner_id='42',
        raw_token='shared-relay-token',
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    barrier = threading.Barrier(2)
    results = []

    def consume():
        barrier.wait(timeout=3)
        results.append(
            SQLiteInteractiveBrowserRepository().consume_relay_token('shared-relay-token', owner_id='42')
        )

    first = threading.Thread(target=consume)
    second = threading.Thread(target=consume)
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.is_alive() is False
    assert second.is_alive() is False
    assert sum(result is not None for result in results) == 1

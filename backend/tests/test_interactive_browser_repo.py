from datetime import datetime, timedelta, timezone


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

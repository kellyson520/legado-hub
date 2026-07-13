import asyncio

from fastapi.testclient import TestClient


def _source_payload(**overrides):
    payload = {
        "bookSourceName": "示例书源",
        "bookSourceUrl": "https://example.test/books",
        "ruleSearch": {"bookList": ".book"},
        "ruleBookInfo": {"name": "h1"},
        "ruleToc": {"chapterList": ".chapter"},
        "ruleContent": {"content": "#content"},
    }
    payload.update(overrides)
    return payload


def test_source_rule_editor_api_requires_write_permission_and_blocks_verification_wall(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-editor-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    original = repo.create_candidate_version(
        "book",
        "https://example.test/books",
        _source_payload(),
        "7",
    )
    client = TestClient(app)
    reader = create_access_token({"sub": "7", "permissions": ["book_sources.read"], "roles": []})
    writer = create_access_token(
        {"sub": "7", "permissions": ["book_sources.read", "book_sources.write"], "roles": []}
    )

    detail = client.get(
        f"/api/sources/versions/{original.id}",
        headers={"Authorization": f"Bearer {reader}"},
    )
    assert detail.status_code == 200

    denied = client.post(
        f"/api/sources/versions/{original.id}/drafts",
        headers={"Authorization": f"Bearer {reader}"},
        json=_source_payload(content_status="verification_wall"),
    )
    assert denied.status_code == 403

    draft = client.post(
        f"/api/sources/versions/{original.id}/drafts",
        headers={"Authorization": f"Bearer {writer}"},
        json=_source_payload(content_status="verification_wall"),
    )
    assert draft.status_code == 200
    draft_id = draft.json()["data"]["source_version_id"]

    validation = client.post(
        f"/api/sources/versions/{draft_id}/validate",
        headers={"Authorization": f"Bearer {writer}"},
    )
    assert validation.status_code == 200
    assert validation.json()["data"]["content_status"] == "verification_wall"

    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository

    audit_events = asyncio.run(SQLiteAuthRepository().list_audit_events())
    assert [event.action for event in audit_events] == ["source_rule.validate", "source_rule.draft"]

    publish = client.post(
        f"/api/sources/versions/{draft_id}/publish",
        headers={"Authorization": f"Bearer {writer}"},
    )
    assert publish.status_code == 422
    assert "verification_wall" in publish.json()["message"]

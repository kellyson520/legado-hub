import asyncio

import pytest
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

    draft_version = repo.get_version(draft_id)
    repo.update_version_payload(
        draft_id,
        {**draft_version.payload, "source_audit": {"status": "approved_for_publish"}},
    )

    from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository

    audit_events = asyncio.run(SQLiteAuthRepository().list_audit_events())
    assert {event.action for event in audit_events if event.resource == "source_rule"} == {
        "source_rule.validate",
        "source_rule.draft",
    }

    publish = client.post(
        f"/api/sources/versions/{draft_id}/publish",
        headers={"Authorization": f"Bearer {writer}"},
    )
    assert publish.status_code == 422
    assert "verification_wall" in publish.json()["message"]


@pytest.mark.parametrize(
    "source_audit",
    [
        {"status": "pending", "attempt": 0},
        {"status": "failed", "attempt": 5},
        {"status": "retry_queued", "attempt": 1},
        {"status": "passed", "attempt": 1, "test_run_pending": True},
    ],
    ids=["pending", "failed", "retry", "pending-checkpoint"],
)
def test_direct_rule_publish_rejects_unsettled_source_audit(tmp_path, monkeypatch, source_audit):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / f"source-rule-audit-{source_audit['status']}.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    version = repo.create_candidate_version(
        "book",
        "https://example.test/audit-blocked",
        _source_payload(source_audit=source_audit),
        "7",
    )
    repo.record_test_run(
        source_version_id=version.id,
        trigger="source_audit",
        score=100,
        grade="A",
        step_results={
            "search": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "toc": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "content": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "source_audit": {"passed": True, "status": "recorded", "elapsed_ms": 0},
        },
    )
    writer = create_access_token({"sub": "7", "permissions": ["book_sources.write"], "roles": []})

    response = TestClient(app).post(
        f"/api/sources/versions/{version.id}/publish",
        headers={"Authorization": f"Bearer {writer}"},
    )

    assert response.status_code == 422
    assert "source audit" in response.json()["message"].lower()
    assert repo.get_version(version.id).status == "candidate"


def test_direct_rule_publish_allows_passed_settled_source_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-audit-passed.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.main import app

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    version = repo.create_candidate_version(
        "book",
        "https://example.test/audit-passed",
        _source_payload(source_audit={"status": "passed", "attempt": 1, "test_run_pending": False}),
        "7",
    )
    repo.record_test_run(
        source_version_id=version.id,
        trigger="source_audit",
        score=100,
        grade="A",
        step_results={
            "search": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "toc": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "content": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "source_audit": {"passed": True, "status": "recorded", "elapsed_ms": 0},
        },
    )
    writer = create_access_token({"sub": "7", "permissions": ["book_sources.write"], "roles": []})

    response = TestClient(app).post(
        f"/api/sources/versions/{version.id}/publish",
        headers={"Authorization": f"Bearer {writer}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "published"

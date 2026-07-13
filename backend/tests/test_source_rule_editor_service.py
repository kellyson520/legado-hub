import pytest


class AuditRecorder:
    def __init__(self):
        self.events = []

    async def record_audit(self, event):
        self.events.append(event)


def _valid_source_payload(**overrides):
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


@pytest.mark.asyncio
async def test_rule_draft_creates_new_candidate_and_verification_wall_blocks_publish(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-editor.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    original = repo.create_candidate_version(
        "book",
        "https://example.test/books",
        _valid_source_payload(),
        "7",
    )
    service = SourceRuntimeService(repo)
    draft = await service.create_rule_draft(
        original.id,
        _valid_source_payload(bookSourceName="受阻书源", content_status="verification_wall"),
        "7",
    )

    assert draft["source_version_id"] != original.id
    assert repo.get_version(original.id).payload["bookSourceName"] == "示例书源"

    validation = await service.validate_rule_version(draft["source_version_id"], "7")

    assert validation["content_status"] == "verification_wall"
    assert validation["publish_allowed"] is False
    with pytest.raises(ValidationException, match="verification_wall"):
        await service.publish_rule_version(draft["source_version_id"], "7")


@pytest.mark.asyncio
async def test_rule_publish_requires_validation_and_supersedes_published_version_with_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-publish.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    original = repo.create_candidate_version(
        "book",
        "https://example.test/books",
        _valid_source_payload(),
        "7",
    )
    repo.update_version_status(original.id, "published")
    audit = AuditRecorder()
    service = SourceRuntimeService(repo, audit=audit)
    draft = await service.create_rule_draft(original.id, _valid_source_payload(bookSourceName="新版书源"), "7")

    validation = await service.validate_rule_version(draft["source_version_id"], "7")
    published = await service.publish_rule_version(draft["source_version_id"], "7")

    assert validation["grade"] == "A"
    assert published["status"] == "published"
    assert repo.get_version(original.id).status == "superseded"
    assert repo.list_deployments(draft["source_version_id"])[0].action == "source_rule.publish"
    assert [event.action for event in audit.events] == ["source_rule.draft", "source_rule.validate", "source_rule.publish"]

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
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
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
    source_repo = SQLiteSourceRepository()
    service = SourceRuntimeService(repo, audit=audit, source_repo=source_repo)
    draft = await service.create_rule_draft(original.id, _valid_source_payload(bookSourceName="新版书源"), "7")

    validation = await service.validate_rule_version(draft["source_version_id"], "7")
    published = await service.publish_rule_version(draft["source_version_id"], "7")

    assert validation["grade"] == "A"
    assert published["status"] == "published"
    assert repo.get_version(original.id).status == "superseded"
    assert repo.list_deployments(draft["source_version_id"])[0].action == "source_rule.publish"
    assert [event.action for event in audit.events] == ["source_rule.draft", "source_rule.validate", "source_rule.publish"]
    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "新版书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://example.test/books"


@pytest.mark.asyncio
async def test_review_publish_registers_valid_book_source_for_legacy_health_probes(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-review-publish-bridge.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    candidate = runtime_repo.create_candidate_version(
        "book",
        "https://review.example.test/books",
        _valid_source_payload(
            bookSourceName="审核发布书源",
            bookSourceUrl="https://review.example.test/books",
        ),
        "7",
    )

    published = await SourceRuntimeService(
        runtime_repo,
        source_repo=source_repo,
    ).resolve_review(candidate.id, reviewer_id="7", action="publish")

    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert published["status"] == "published"
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "审核发布书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://review.example.test/books"


@pytest.mark.asyncio
async def test_register_published_book_sources_ignores_invalid_and_non_published_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-bridge.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    candidate = runtime_repo.create_candidate_version(
        "book",
        "https://candidate.example.test/books",
        _valid_source_payload(bookSourceUrl="https://candidate.example.test/books"),
        "7",
    )
    failed = runtime_repo.create_candidate_version(
        "book",
        "https://failed.example.test/books",
        _valid_source_payload(bookSourceUrl="https://failed.example.test/books"),
        "7",
    )
    runtime_repo.update_version_status(failed.id, "failed")
    other_type = runtime_repo.create_candidate_version(
        "rss",
        "https://rss.example.test/feed",
        _valid_source_payload(bookSourceUrl="https://rss.example.test/feed"),
        "7",
    )
    runtime_repo.update_version_status(other_type.id, "published")
    invalid = runtime_repo.create_candidate_version(
        "book",
        "https://invalid.example.test/books",
        {"bookSourceName": "", "bookSourceUrl": "https://invalid.example.test/books"},
        "7",
    )
    runtime_repo.update_version_status(invalid.id, "published")
    published = runtime_repo.create_candidate_version(
        "book",
        "https://published.example.test/books",
        _valid_source_payload(
            bookSourceName="已发布书源",
            bookSourceUrl="https://published.example.test/books",
        ),
        "7",
    )
    runtime_repo.update_version_status(published.id, "published")
    service = SourceRuntimeService(runtime_repo, source_repo=source_repo)

    await service.register_published_book_sources()
    await service.register_published_book_sources()

    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "已发布书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://published.example.test/books"
    assert runtime_repo.get_version(candidate.id).status == "candidate"
    assert runtime_repo.get_version(failed.id).status == "failed"
    assert runtime_repo.get_version(other_type.id).status == "published"
    assert runtime_repo.get_version(invalid.id).payload == {
        "bookSourceName": "",
        "bookSourceUrl": "https://invalid.example.test/books",
    }


@pytest.mark.asyncio
async def test_register_published_book_sources_preserves_existing_health_state(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-health-state.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from datetime import datetime

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    source_url = "https://health.example.test/books"
    legacy_source = await source_repo.create_book_source(
        _valid_source_payload(bookSourceName="旧书源名称", bookSourceUrl=source_url),
        actor_id=7,
    )
    await source_repo.update_book_source_health_fields(
        legacy_source["id"],
        source_status="error",
        error_msg="上次探测超时",
        last_check_time=datetime(2026, 7, 15, 10, 30, 0),
    )
    before, _ = await source_repo.list_book_sources(page=1, page_size=10)
    health_before = {
        key: before[0][key]
        for key in ("sourceStatus", "errorMsg", "lastCheckTime")
    }
    published = runtime_repo.create_candidate_version(
        "book",
        source_url,
        _valid_source_payload(bookSourceName="更新后书源", bookSourceUrl=source_url),
        "7",
    )
    runtime_repo.update_version_status(published.id, "published")

    await SourceRuntimeService(runtime_repo, source_repo=source_repo).register_published_book_sources()

    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "更新后书源"
    assert {
        key: legacy_sources[0][key]
        for key in ("sourceStatus", "errorMsg", "lastCheckTime")
    } == health_before


@pytest.mark.asyncio
async def test_register_published_book_sources_normalizes_nested_source_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-nested-rule.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    nested_rule = _valid_source_payload(
        bookSourceName="构建产物书源",
        bookSourceUrl="https://nested.example.test/books",
    )
    published = runtime_repo.create_candidate_version(
        "book",
        "https://nested.example.test",
        {
            "keyword": "剑来",
            "canonical_url": "https://nested.example.test",
            "source_rule": nested_rule,
        },
        "7",
    )
    runtime_repo.update_version_status(published.id, "published")

    await SourceRuntimeService(runtime_repo, source_repo=source_repo).register_published_book_sources()

    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "构建产物书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://nested.example.test/books"
    assert legacy_sources[0]["ruleSearch"] == nested_rule["ruleSearch"]
    assert legacy_sources[0]["ruleBookInfo"] == nested_rule["ruleBookInfo"]
    assert legacy_sources[0]["ruleToc"] == nested_rule["ruleToc"]
    assert legacy_sources[0]["ruleContent"] == nested_rule["ruleContent"]
    assert runtime_repo.get_version(published.id).payload == {
        "keyword": "剑来",
        "canonical_url": "https://nested.example.test",
        "source_rule": nested_rule,
    }


@pytest.mark.asyncio
async def test_register_published_book_sources_falls_back_when_nested_rule_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-nested-rule-fallback.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    source_repo = SQLiteSourceRepository()
    top_level_rule = _valid_source_payload(
        bookSourceName="顶层书源",
        bookSourceUrl="https://fallback.example.test/books",
    )
    nested_rule = _valid_source_payload(
        bookSourceName="无效嵌套书源",
        bookSourceUrl="https://invalid-nested.example.test/books",
        ruleContent="bad",
    )
    published = runtime_repo.create_candidate_version(
        "book",
        "https://fallback.example.test",
        {
            **top_level_rule,
            "source_rule": nested_rule,
        },
        "7",
    )
    runtime_repo.update_version_status(published.id, "published")

    await SourceRuntimeService(runtime_repo, source_repo=source_repo).register_published_book_sources()

    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "顶层书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://fallback.example.test/books"
    assert legacy_sources[0]["ruleContent"] == top_level_rule["ruleContent"]

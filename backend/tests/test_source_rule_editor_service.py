import json

import pytest


class AuditRecorder:
    def __init__(self):
        self.events = []

    async def record_audit(self, event):
        self.events.append(event)


class PassingLiveProbe:
    def __init__(self):
        self.calls = []

    async def probe_source(self, source, keyword_samples, probe_mode):
        from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult

        self.calls.append((source, keyword_samples, probe_mode))
        return SourceProbeEvidence(
            source_id=source["id"],
            source_name=source["bookSourceName"],
            source_url=source["bookSourceUrl"],
            probe_mode=probe_mode,
            keyword=keyword_samples[0],
            search=StageProbeResult(stage="search", status="ok", elapsed_ms=12, hit_count=1),
            toc=StageProbeResult(stage="toc", status="ok", elapsed_ms=18, hit_count=3),
            content=StageProbeResult(
                stage="content",
                status="ok",
                elapsed_ms=24,
                detail={"content_length": 120},
            ),
        )


class SensitiveLiveProbe:
    async def probe_source(self, source, keyword_samples, probe_mode):
        from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult

        return SourceProbeEvidence(
            source_id=source["id"],
            source_name=source["bookSourceName"],
            source_url=source["bookSourceUrl"],
            probe_mode=probe_mode,
            keyword=keyword_samples[0],
            search=StageProbeResult(
                stage="search",
                status="failed",
                elapsed_ms=12,
                request_preview="https://example.test/search?token=top-secret BODY=password=top-secret",
                error_message="authorization: Bearer top-secret",
                detail={
                    "http_status": 401,
                    "response_kind": "network_error",
                    "response_preview": "<input value='top-secret'>",
                    "http_error": "cookie=top-secret",
                },
            ),
            toc=StageProbeResult(stage="toc", status="skipped"),
            content=StageProbeResult(stage="content", status="skipped"),
        )


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


def _approve_source_audit(repo, version_id: str) -> None:
    version = repo.get_version(version_id)
    repo.update_version_payload(
        version_id,
        {**version.payload, "source_audit": {"status": "approved_for_publish"}},
    )


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
    draft_version = repo.get_version(draft["source_version_id"])
    repo.update_version_payload(
        draft["source_version_id"],
        {**draft_version.payload, "source_audit": {"status": "approved_for_publish"}},
    )
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
    probe = PassingLiveProbe()
    service = SourceRuntimeService(repo, audit=audit, source_repo=source_repo, source_probe=probe)
    draft = await service.create_rule_draft(original.id, _valid_source_payload(bookSourceName="新版书源"), "7")

    validation = await service.validate_rule_version(draft["source_version_id"], "7")
    _approve_source_audit(repo, draft["source_version_id"])
    published = await service.publish_rule_version(draft["source_version_id"], "7")

    assert validation["grade"] == "A"
    assert repo.list_test_runs(draft["source_version_id"])[0].trigger == "rule_editor_live_probe"
    assert probe.calls[0][2] == "full_chain"
    assert published["status"] == "published"
    assert repo.get_version(original.id).status == "superseded"
    assert repo.list_deployments(draft["source_version_id"])[0].action == "source_rule.publish"
    assert [event.action for event in audit.events] == ["source_rule.draft", "source_rule.validate", "source_rule.publish"]
    legacy_sources, total = await source_repo.list_book_sources(page=1, page_size=10)
    assert total == 1
    assert legacy_sources[0]["bookSourceName"] == "新版书源"
    assert legacy_sources[0]["bookSourceUrl"] == "https://example.test/books"


@pytest.mark.asyncio
async def test_rule_publish_rejects_shape_only_validation_without_live_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-shape-only.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    candidate = repo.create_candidate_version(
        "book",
        "https://example.test/shape-only",
        _valid_source_payload(bookSourceUrl="https://example.test/shape-only"),
        "7",
    )
    repo.record_test_run(
        source_version_id=candidate.id,
        trigger="rule_editor",
        score=100,
        grade="A",
        step_results={
            "search": {"passed": True, "status": "ready"},
            "toc": {"passed": True, "status": "ready"},
            "content": {"passed": True, "status": "ready"},
        },
    )
    _approve_source_audit(repo, candidate.id)

    with pytest.raises(ValidationException, match="live probe"):
        await SourceRuntimeService(repo).publish_rule_version(candidate.id, "7")

    assert repo.get_version(candidate.id).status == "candidate"


@pytest.mark.asyncio
async def test_rule_publish_rejects_candidate_without_unified_audit_record(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-missing-audit.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    candidate = repo.create_candidate_version(
        "book",
        "https://example.test/missing-audit",
        _valid_source_payload(bookSourceUrl="https://example.test/missing-audit"),
        "7",
    )

    with pytest.raises(ValidationException, match="source audit is missing"):
        await SourceRuntimeService(repo).publish_rule_version(candidate.id, "7")


@pytest.mark.asyncio
async def test_live_probe_validation_persists_only_safe_evidence_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-rule-safe-evidence.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    candidate = repo.create_candidate_version(
        "book",
        "https://example.test/safe-evidence",
        _valid_source_payload(bookSourceUrl="https://example.test/safe-evidence"),
        "7",
    )
    service = SourceRuntimeService(repo, source_probe=SensitiveLiveProbe())

    validation = await service.validate_rule_version(candidate.id, "7")
    detail = await service.get_version_detail(candidate.id)

    for result in (validation, detail):
        rendered = json.dumps(result, ensure_ascii=False)
        assert "top-secret" not in rendered
        assert "request_preview" not in rendered
        assert "response_preview" not in rendered
        assert "http_error" not in rendered
        assert "error_message" not in rendered

    assert validation["step_results"]["search"]["http_status"] == 401
    assert validation["step_results"]["search"]["response_kind"] == "network_error"


@pytest.mark.asyncio
async def test_review_publish_rejects_shape_only_validation_without_live_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-review-shape-only.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    candidate = repo.create_candidate_version(
        "book",
        "https://example.test/review-shape-only",
        _valid_source_payload(bookSourceUrl="https://example.test/review-shape-only"),
        "7",
    )
    repo.record_test_run(
        source_version_id=candidate.id,
        trigger="rule_editor",
        score=100,
        grade="A",
        step_results={
            "search": {"passed": True, "status": "ready"},
            "toc": {"passed": True, "status": "ready"},
            "content": {"passed": True, "status": "ready"},
        },
    )
    _approve_source_audit(repo, candidate.id)

    with pytest.raises(ValidationException, match="live probe"):
        await SourceRuntimeService(repo).resolve_review(candidate.id, reviewer_id="7", action="publish")

    assert repo.get_version(candidate.id).status == "candidate"


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

    service = SourceRuntimeService(
        runtime_repo,
        source_repo=source_repo,
        source_probe=PassingLiveProbe(),
    )
    await service.validate_rule_version(candidate.id, "7")
    _approve_source_audit(runtime_repo, candidate.id)
    published = await service.resolve_review(candidate.id, reviewer_id="7", action="publish")

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

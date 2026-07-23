import asyncio

import pytest


class FakeProbeService:
    async def probe_source(self, source, keyword_samples, probe_mode="full_chain"):
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
                request_preview="https://www.qidian.com/search?token=undefined",
            ),
            toc=StageProbeResult(stage="toc", status="skipped"),
            content=StageProbeResult(stage="content", status="skipped"),
        )


@pytest.mark.asyncio
async def test_health_inventory_includes_unprobed_sources_without_creating_snapshots(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-inventory.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    unprobed_first = await source_repo.create_book_source(
        {"bookSourceName": "未探测一", "bookSourceUrl": "https://unprobed-one.example", "enabled": True},
        actor_id=1,
    )
    probed = await source_repo.create_book_source(
        {"bookSourceName": "原始名称", "bookSourceUrl": "https://original.example", "enabled": True},
        actor_id=1,
    )
    unprobed_last = await source_repo.create_book_source(
        {"bookSourceName": "未探测二", "bookSourceUrl": "https://unprobed-two.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=probed["id"],
            source_name="已探测快照名称",
            source_url="https://snapshot.example",
            health_status="healthy",
            search_status="healthy",
            toc_status="degraded",
            content_status="healthy",
            failure_reason="",
            decision_confidence="high",
            route_policy="allow",
            route_score=87.5,
            metadata={"from": "snapshot"},
        )
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    first_page = await service.list_book_source_health(page=1, page_size=2)
    unknown_second_page = await service.list_book_source_health(page=2, page_size=1, statuses=["unprobed"])
    searched = await service.list_book_source_health(page=1, page_size=10, search="unprobed-two")
    snapshots, snapshot_total = health_repo.list_snapshots(limit=100)

    assert first_page["meta"] == {
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
        "search": "",
        "status_counts": {
            "total": 3,
            "healthy": 1,
            "degraded": 0,
            "blocked": 0,
            "dead": 0,
            "unprobed": 2,
            "unknown": 0,
            "disabled": 0,
        },
    }
    assert [item["source_id"] for item in first_page["items"]] == [unprobed_first["id"], probed["id"]]
    assert first_page["items"][0] == {
        "source_id": unprobed_first["id"],
        "source_name": "未探测一",
        "source_url": "https://unprobed-one.example",
        "health_status": "unknown",
        "search_status": "unknown",
        "toc_status": "unknown",
        "content_status": "unknown",
        "failure_reason": "not_probed",
        "decision_confidence": "low",
        "route_policy": "probe_only",
        "route_score": 10.0,
        "last_probe_at": None,
        "next_probe_at": None,
        "metadata": {},
    }
    assert first_page["items"][1]["source_name"] == "已探测快照名称"
    assert first_page["items"][1]["source_url"] == "https://snapshot.example"
    assert first_page["items"][1]["toc_status"] == "degraded"
    assert first_page["items"][1]["route_score"] == 87.5
    assert first_page["items"][1]["metadata"] == {"from": "snapshot"}
    assert first_page["meta"]["status_counts"] == {
        "total": 3,
        "healthy": 1,
        "degraded": 0,
        "blocked": 0,
        "dead": 0,
        "unprobed": 2,
        "unknown": 0,
        "disabled": 0,
    }
    assert unknown_second_page["meta"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
        "search": "",
        "status_counts": {
            "total": 2,
            "healthy": 0,
            "degraded": 0,
            "blocked": 0,
            "dead": 0,
            "unprobed": 2,
            "unknown": 0,
            "disabled": 0,
        },
    }
    assert [item["source_id"] for item in unknown_second_page["items"]] == [unprobed_last["id"]]
    assert searched["meta"] == {
        "page": 1,
        "page_size": 10,
        "total": 1,
        "total_pages": 1,
        "search": "unprobed-two",
        "status_counts": {
            "total": 1,
            "healthy": 0,
            "degraded": 0,
            "blocked": 0,
            "dead": 0,
            "unprobed": 1,
            "unknown": 0,
            "disabled": 0,
        },
    }
    assert [item["source_id"] for item in searched["items"]] == [unprobed_last["id"]]
    assert snapshot_total == 1
    assert [snapshot.source_id for snapshot in snapshots] == [probed["id"]]


@pytest.mark.asyncio
async def test_health_inventory_counts_unknown_failures_separately_from_unprobed(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-status-counts.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    await source_repo.create_book_source(
        {"bookSourceName": "尚未探测", "bookSourceUrl": "https://unprobed.example", "enabled": True},
        actor_id=1,
    )
    unknown = await source_repo.create_book_source(
        {"bookSourceName": "未知错误", "bookSourceUrl": "https://unknown-error.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=unknown["id"],
            source_name="未知错误",
            source_url="https://unknown-error.example",
            health_status="unknown",
            failure_reason="parser_unknown",
        )
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    result = await service.list_book_source_health(page=1, page_size=20)

    assert result["meta"]["status_counts"] == {
        "total": 2,
        "healthy": 0,
        "degraded": 0,
        "blocked": 0,
        "dead": 0,
        "unprobed": 1,
        "unknown": 1,
        "disabled": 0,
    }
    assert [item["failure_reason"] for item in result["items"]] == ["not_probed", "parser_unknown"]


@pytest.mark.asyncio
async def test_health_inventory_does_not_count_disabled_sources_as_unprobed(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-disabled.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    await source_repo.create_book_source(
        {"bookSourceName": "启用未探测", "bookSourceUrl": "https://enabled.example", "enabled": True},
        actor_id=1,
    )
    disabled = await source_repo.create_book_source(
        {"bookSourceName": "已禁用未探测", "bookSourceUrl": "https://disabled.example", "enabled": False},
        actor_id=1,
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    result = await service.list_book_source_health(page=1, page_size=20)

    assert result["meta"]["status_counts"]["unprobed"] == 1
    assert result["meta"]["status_counts"]["disabled"] == 1
    disabled_row = next(item for item in result["items"] if item["source_id"] == disabled["id"])
    assert disabled_row["health_status"] == "disabled"
    assert disabled_row["failure_reason"] == "disabled"


@pytest.mark.asyncio
async def test_admin_service_prioritizes_unprobed_enabled_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-candidates.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    first = await source_repo.create_book_source(
        {"bookSourceName": "未探测 A", "bookSourceUrl": "https://a.example", "enabled": True},
        actor_id=1,
    )
    second = await source_repo.create_book_source(
        {"bookSourceName": "已探测 B", "bookSourceUrl": "https://b.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=second["id"],
            source_name=second["bookSourceName"],
            source_url=second["bookSourceUrl"],
            health_status="healthy",
            search_status="ok",
            toc_status="ok",
            content_status="ok",
        )
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    assert service.list_probe_candidate_ids(limit=1) == [first["id"]]


@pytest.mark.asyncio
async def test_admin_service_skips_sources_before_next_probe_at(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-candidate-cooldown.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    unprobed = await source_repo.create_book_source(
        {"bookSourceName": "未探测", "bookSourceUrl": "https://unprobed.example", "enabled": True},
        actor_id=1,
    )
    due = await source_repo.create_book_source(
        {"bookSourceName": "到期重测", "bookSourceUrl": "https://due.example", "enabled": True},
        actor_id=1,
    )
    cooling = await source_repo.create_book_source(
        {"bookSourceName": "冷却中", "bookSourceUrl": "https://cooling.example", "enabled": True},
        actor_id=1,
    )
    now = datetime.now(timezone.utc)
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=due["id"],
            source_name=due["bookSourceName"],
            source_url=due["bookSourceUrl"],
            health_status="degraded",
            last_probe_at=now - timedelta(minutes=45),
            next_probe_at=now - timedelta(minutes=1),
        )
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=cooling["id"],
            source_name=cooling["bookSourceName"],
            source_url=cooling["bookSourceUrl"],
            health_status="blocked",
            failure_reason="waf_blocked",
            last_probe_at=now,
            next_probe_at=now + timedelta(minutes=30),
        )
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    assert service.list_probe_candidate_ids(limit=None) == [unprobed["id"], due["id"]]


@pytest.mark.asyncio
async def test_health_inventory_paginates_in_repository_without_loading_full_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-inventory-page.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from sqlalchemy import event

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.database import engine
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    first_unprobed = await source_repo.create_book_source(
        {
            "bookSourceName": "未探测一",
            "bookSourceUrl": "https://unprobed-page-one.example",
            "enabled": True,
            "ruleSearch": "x" * 10000,
        },
        actor_id=1,
    )
    probed = await source_repo.create_book_source(
        {"bookSourceName": "已探测", "bookSourceUrl": "https://probed-page.example", "enabled": True},
        actor_id=1,
    )
    second_unprobed = await source_repo.create_book_source(
        {"bookSourceName": "未探测二", "bookSourceUrl": "https://unprobed-page-two.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=probed["id"],
            source_name=probed["bookSourceName"],
            source_url=probed["bookSourceUrl"],
            health_status="healthy",
            route_policy="allow",
            route_score=100.0,
        )
    )

    async def fail_full_book_source_load(*args, **kwargs):
        pytest.fail("paginated health inventory must not load full book sources")

    def fail_unbounded_snapshot_read(*args, **kwargs):
        pytest.fail("paginated health inventory must not call list_snapshots")

    monkeypatch.setattr(source_repo, "list_book_sources_full", fail_full_book_source_load)
    monkeypatch.setattr(health_repo, "list_snapshots", fail_unbounded_snapshot_read)
    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )
    statements = []

    def capture_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        result = await service.list_book_source_health(page=2, page_size=1, statuses=["unprobed"])
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert result["meta"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
        "search": "",
        "status_counts": {
            "total": 2,
            "healthy": 0,
            "degraded": 0,
            "blocked": 0,
            "dead": 0,
            "unprobed": 2,
            "unknown": 0,
            "disabled": 0,
        },
    }
    assert [item["source_id"] for item in result["items"]] == [second_unprobed["id"]]
    health_queries = [statement.lower() for statement in statements if "source_health_snapshots" in statement.lower()]
    assert health_queries
    assert all("payload" not in statement.lower() for statement in statements)
    assert all(" limit " in statement for statement in health_queries if "count(" not in statement)
    assert first_unprobed["id"] < second_unprobed["id"]


@pytest.mark.asyncio
async def test_admin_service_persists_snapshot_and_mirrors_book_source_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-admin.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    created = await source_repo.create_book_source(
        {
            "bookSourceName": "起点读书限免+本章说",
            "bookSourceUrl": "https://www.qidian.com",
            "enabled": True,
        },
        actor_id=1,
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=FakeProbeService(),
        classifier=SourceHealthClassifierService(),
    )

    result = await service.probe_book_source(created["id"], keyword_samples=["捞尸人"], probe_mode="full_chain")
    source_row = (await source_repo.list_book_sources_full(ids=[created["id"]]))[0]
    snapshot = health_repo.get_snapshot(created["id"])

    assert result["snapshot"]["health_status"] == "blocked"
    assert source_row["sourceStatus"] == "blocked"
    assert "token_missing" in (source_row["errorMsg"] or "")
    assert snapshot is not None
    assert snapshot.route_policy == "skip"

    detail = await service.get_book_source_health(created["id"])
    assert detail["route_decision"] == {
        "policy": "skip",
        "score": 0.0,
        "reason": "token_missing",
    }
    assert detail["failure_timeline"][0]["stage"] == "search"
    assert detail["failure_timeline"][0]["reason"] == "token_missing"


@pytest.mark.asyncio
async def test_admin_service_keeps_single_transient_transport_failure_unknown_then_confirms_it(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-transient.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService
    from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    class TransientProbeService:
        async def probe_source(self, source, keyword_samples, probe_mode="full_chain"):
            return SourceProbeEvidence(
                source_id=source["id"],
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                probe_mode=probe_mode,
                keyword=keyword_samples[0],
                search=StageProbeResult(stage="search", status="failed", detail={"http_status": 503}),
                toc=StageProbeResult(stage="toc", status="skipped"),
                content=StageProbeResult(stage="content", status="skipped"),
            )

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "瞬时错误书源", "bookSourceUrl": "https://transient.example", "enabled": True},
        actor_id=1,
    )
    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=TransientProbeService(),
        classifier=SourceHealthClassifierService(),
    )

    first = await service.probe_book_source(source["id"], keyword_samples=["捞尸人"])
    second = await service.probe_book_source(source["id"], keyword_samples=["捞尸人"])

    assert first["snapshot"]["health_status"] == "unknown"
    assert first["snapshot"]["failure_reason"] == "http_status_error"
    assert second["snapshot"]["health_status"] == "blocked"


@pytest.mark.asyncio
async def test_admin_service_keeps_single_waf_failure_unknown_then_confirms_it(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-waf-stability.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService
    from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    class WafProbeService:
        async def probe_source(self, source, keyword_samples, probe_mode="full_chain"):
            return SourceProbeEvidence(
                source_id=source["id"],
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                probe_mode=probe_mode,
                keyword=keyword_samples[0],
                search=StageProbeResult(
                    stage="search",
                    status="failed",
                    detail={"http_status": 403, "response_kind": "html", "response_preview": "captcha"},
                ),
                toc=StageProbeResult(stage="toc", status="skipped"),
                content=StageProbeResult(stage="content", status="skipped"),
            )

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "WAF 瞬时拦截", "bookSourceUrl": "https://waf.example", "enabled": True},
        actor_id=1,
    )
    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=WafProbeService(),
        classifier=SourceHealthClassifierService(),
    )

    first = await service.probe_book_source(source["id"], keyword_samples=["捞尸人"])
    second = await service.probe_book_source(source["id"], keyword_samples=["捞尸人"])

    assert first["snapshot"]["health_status"] == "unknown"
    assert first["snapshot"]["failure_reason"] == "waf_blocked"
    assert second["snapshot"]["health_status"] == "blocked"


@pytest.mark.asyncio
async def test_admin_service_continues_batch_after_one_source_failure():
    from app.application.services.source_health_admin_service import SourceHealthAdminService

    service = SourceHealthAdminService(
        source_repo=None,
        health_repo=None,
        probe_service=None,
        classifier=None,
    )
    calls = []

    async def probe_book_source(source_id, keyword_samples, probe_mode="full_chain"):
        calls.append(source_id)
        if source_id == 1:
            raise RuntimeError("broken source")
        return {"snapshot": {"source_id": source_id, "health_status": "healthy"}}

    service.probe_book_source = probe_book_source

    result = await service.probe_book_sources([1, 2], keyword_samples=["捞尸人"])

    assert calls == [1, 2]
    assert result["total"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert result["results"][0] == {
        "source_id": 1,
        "status": "failed",
        "error": "broken source",
    }
    assert result["results"][1]["snapshot"]["source_id"] == 2


@pytest.mark.asyncio
async def test_admin_service_records_unexpected_probe_exception_as_unknown_not_unprobed(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-exception.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "异常书源", "bookSourceUrl": "https://exception.example", "enabled": True},
        actor_id=1,
    )
    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )

    async def fail_probe(source_id, keyword_samples, probe_mode="full_chain"):
        raise RuntimeError("unexpected parser failure")

    service.probe_book_source = fail_probe
    result = await service.probe_book_sources([source["id"]], keyword_samples=["捞尸人"])
    snapshot = health_repo.get_snapshot(source["id"])
    inventory = await service.list_book_source_health(page=1, page_size=20)

    assert result["failed"] == 1
    assert snapshot is not None
    assert snapshot.health_status == "unknown"
    assert snapshot.failure_reason == "probe_exception"
    assert snapshot.last_probe_at is not None
    assert inventory["meta"]["status_counts"]["unknown"] == 1
    assert inventory["meta"]["status_counts"]["unprobed"] == 0


@pytest.mark.asyncio
async def test_admin_service_defers_remaining_sources_when_batch_deadline_expires():
    from app.application.services.source_health_admin_service import SourceHealthAdminService

    service = SourceHealthAdminService(
        source_repo=None,
        health_repo=None,
        probe_service=None,
        classifier=None,
    )
    calls = []

    async def probe_book_source(source_id, keyword_samples, probe_mode="full_chain"):
        calls.append(source_id)
        return {"snapshot": {"source_id": source_id}}

    service.probe_book_source = probe_book_source

    result = await service.probe_book_sources(
        [1, 2],
        keyword_samples=["捞尸人"],
        timeout_seconds=0,
    )

    assert calls == []
    assert result["total"] == 2
    assert result["succeeded"] == 0
    assert result["failed"] == 0
    assert result["deferred"] == 2


@pytest.mark.asyncio
async def test_admin_service_bounds_timeout_failure_persistence_by_batch_deadline():
    from time import monotonic

    from app.application.services.source_health_admin_service import SourceHealthAdminService

    service = SourceHealthAdminService(
        source_repo=None,
        health_repo=None,
        probe_service=None,
        classifier=None,
    )
    calls = []

    async def slow_probe(source_id, keyword_samples, probe_mode="full_chain"):
        calls.append(source_id)
        await asyncio.sleep(0.2)
        return {"snapshot": {"source_id": source_id}}

    async def slow_failure_persistence(*args, **kwargs):
        await asyncio.sleep(0.2)

    service.probe_book_source = slow_probe
    service._record_probe_failure = slow_failure_persistence

    started = monotonic()
    result = await service.probe_book_sources(
        [1, 2],
        keyword_samples=["捞尸人"],
        timeout_seconds=0.1,
    )
    elapsed = monotonic() - started

    assert elapsed < 0.18
    assert calls == [1]
    assert result["failed"] == 1
    assert result["deferred_source_ids"] == [2]


@pytest.mark.asyncio
async def test_admin_service_recover_source_resets_blocked_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-recover.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    created = await source_repo.create_book_source(
        {"bookSourceName": "八叉书库", "bookSourceUrl": "https://www.8cha.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=created["id"],
            source_name=created["bookSourceName"],
            source_url=created["bookSourceUrl"],
            health_status="blocked",
            failure_reason="waf_blocked",
            route_policy="skip",
        )
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=None,
        classifier=None,
    )
    result = await service.recover_source(created["id"])

    assert result["health_status"] == "unknown"
    assert result["failure_reason"] == "not_probed"
    assert result["route_policy"] == "probe_only"

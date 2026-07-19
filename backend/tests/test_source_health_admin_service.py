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
    unknown_second_page = await service.list_book_source_health(page=2, page_size=1, statuses=["unknown"])
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
    }
    assert [item["failure_reason"] for item in result["items"]] == ["not_probed", "parser_unknown"]


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
        result = await service.list_book_source_health(page=2, page_size=1, statuses=["unknown"])
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

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
    assert result["route_policy"] == "probe_only"

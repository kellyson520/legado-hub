from datetime import datetime, timezone


def test_source_health_repository_persists_snapshot_and_probe_history(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-repo.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_health_repository()

    snapshot = repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=7,
            source_name="起点读书限免+本章说",
            source_url="https://www.qidian.com",
            health_status="blocked",
            search_status="failed",
            toc_status="skipped",
            content_status="skipped",
            failure_reason="token_missing",
            decision_confidence="high",
            route_policy="skip",
            route_score=0.0,
            consecutive_failures=2,
            consecutive_successes=0,
            last_probe_at=datetime.now(timezone.utc),
            metadata={"keyword": "捞尸人"},
        )
    )

    repo.record_probe_run(
        SourceProbeRun(
            source_id=7,
            source_name="起点读书限免+本章说",
            probe_mode="full_chain",
            keyword="捞尸人",
            overall_status="blocked",
            failure_reason="token_missing",
            search_result={"request_preview": "https://www.qidian.com/search?token=undefined"},
            toc_result={},
            content_result={},
            summary={"hit_count": 0},
        )
    )

    loaded = repo.get_snapshot(7)
    rows, total = repo.list_snapshots(statuses=["blocked"], limit=10, offset=0)
    runs = repo.list_probe_runs(7, limit=5)

    assert snapshot.source_id == 7
    assert loaded is not None
    assert loaded.failure_reason == "token_missing"
    assert total == 1
    assert rows[0].route_policy == "skip"
    assert runs[0].overall_status == "blocked"
    assert runs[0].search_result["request_preview"].endswith("token=undefined")


async def test_source_repository_keeps_ephemeral_sources_tenant_scoped_and_expiring(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ephemeral-sources.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_repository()
    source = {
        "bookSourceName": "临时源",
        "bookSourceUrl": "https://tenant.example",
        "searchUrl": "https://tenant.example/search?wd={{key}}",
    }

    ids = await repo.create_ephemeral_book_sources([source], "tenant-a")
    assert ids
    assert len(await repo.list_ephemeral_book_sources("tenant-a", ids=ids)) == 1
    assert await repo.list_ephemeral_book_sources("tenant-b", ids=ids) == []
    assert await repo.list_book_sources_full(urls=[source["bookSourceUrl"]]) == []

    await repo.delete_ephemeral_book_sources("tenant-a", ids)
    assert await repo.list_ephemeral_book_sources("tenant-a", ids=ids) == []

from datetime import datetime, timezone

import pytest


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


def test_source_health_repository_normalizes_legacy_no_match_snapshots(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-legacy-no-match.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.schema import BookSourceModel
    from app.infrastructure.persistence.sqlite.session import SessionLocal

    bootstrap_sqlite()
    db = SessionLocal()
    try:
        db.add(
            BookSourceModel(
                id=1,
                bookSourceName="旧无命中源",
                bookSourceUrl="https://legacy-no-match.example",
                payload="{}",
                enabled=True,
            )
        )
        db.commit()
    finally:
        db.close()

    repo = build_source_health_repository()
    repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=1,
            source_name="旧无命中源",
            source_url="https://legacy-no-match.example",
            health_status="degraded",
            failure_reason="keyword_no_result",
            route_policy="deprioritize",
            route_score=45.0,
            decision_confidence="medium",
        )
    )

    loaded = repo.get_snapshot(1)
    rows, total = repo.list_book_source_health_inventory(limit=10, offset=0)
    counts = repo.count_book_source_health_statuses()

    assert loaded is not None
    assert loaded.health_status == "unknown"
    assert loaded.route_policy == "probe_only"
    assert loaded.route_score == 10.0
    assert rows[0].health_status == "unknown"
    assert total == 1
    assert counts["unknown"] == 1
    assert counts["degraded"] == 0


async def test_source_health_repository_records_failure_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-failure-atomic.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "原子失败源", "bookSourceUrl": "https://atomic.example", "enabled": True},
        actor_id=1,
    )
    lease = health_repo.claim_probe_source_leases(
        source_ids=[source["id"]],
        worker_id="failure-worker",
        lease_seconds=60,
    )
    lease_token = lease[source["id"]]
    now = datetime.now(timezone.utc)
    snapshot = SourceHealthSnapshot(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        source_url=source["bookSourceUrl"],
        health_status="unknown",
        search_status="failed",
        toc_status="skipped",
        content_status="skipped",
        failure_reason="probe_exception",
        decision_confidence="low",
        route_policy="probe_only",
        route_score=10.0,
        last_probe_at=now,
        next_probe_at=now,
    )
    run = SourceProbeRun(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        probe_mode="full_chain",
        keyword="sample",
        overall_status="unknown",
        failure_reason="probe_exception",
        created_at=now,
    )

    health_repo.record_probe_failure(
        snapshot,
        run,
        worker_id="failure-worker",
        lease_token=lease_token,
        source_status="unknown",
        error_msg="probe_exception:low",
        last_check_time=now,
    )

    loaded = health_repo.get_snapshot(source["id"])
    runs = health_repo.list_probe_runs(source["id"], limit=1)
    source_after = (await source_repo.list_book_sources_full(ids=[source["id"]]))[0]
    assert loaded is not None and loaded.failure_reason == "probe_exception"
    assert runs and runs[0].failure_reason == "probe_exception"
    assert source_after["sourceStatus"] == "unknown"
    assert source_after["errorMsg"] == "probe_exception:low"


async def test_source_health_repository_records_success_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-success-atomic.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "原子成功源", "bookSourceUrl": "https://success-atomic.example", "enabled": True},
        actor_id=1,
    )
    lease = health_repo.claim_probe_source_leases(
        source_ids=[source["id"]],
        worker_id="success-worker",
        lease_seconds=60,
    )
    lease_token = lease[source["id"]]
    now = datetime.now(timezone.utc)
    snapshot = SourceHealthSnapshot(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        source_url=source["bookSourceUrl"],
        health_status="healthy",
        search_status="ok",
        toc_status="ok",
        content_status="ok",
        decision_confidence="high",
        route_policy="allow",
        route_score=100.0,
        last_success_at=now,
        last_probe_at=now,
        next_probe_at=now,
    )
    run = SourceProbeRun(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        probe_mode="full_chain",
        keyword="sample",
        overall_status="healthy",
        failure_reason="",
        created_at=now,
    )

    health_repo.record_probe_result(
        snapshot,
        run,
        worker_id="success-worker",
        lease_token=lease_token,
        source_status="healthy",
        error_msg="",
        last_check_time=now,
    )

    loaded = health_repo.get_snapshot(source["id"])
    runs = health_repo.list_probe_runs(source["id"], limit=1)
    source_after = (await source_repo.list_book_sources_full(ids=[source["id"]]))[0]
    assert loaded is not None and loaded.health_status == "healthy"
    assert runs and runs[0].overall_status == "healthy"
    assert source_after["sourceStatus"] == "healthy"
    assert source_after["errorMsg"] == ""


async def test_source_health_repository_rejects_result_from_wrong_probe_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-lease-token.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "租约源", "bookSourceUrl": "https://lease.example", "enabled": True},
        actor_id=1,
    )
    lease = health_repo.claim_probe_source_leases(
        source_ids=[source["id"]],
        worker_id="current-worker",
        lease_seconds=60,
    )
    now = datetime.now(timezone.utc)
    snapshot = SourceHealthSnapshot(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        source_url=source["bookSourceUrl"],
        health_status="healthy",
        search_status="ok",
        toc_status="ok",
        content_status="ok",
        route_policy="allow",
        route_score=100,
        last_probe_at=now,
        next_probe_at=now,
    )
    run = SourceProbeRun(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        probe_mode="full_chain",
        keyword="sample",
        overall_status="healthy",
        failure_reason="",
        created_at=now,
    )

    with pytest.raises(PermissionError, match="lease"):
        health_repo.record_probe_result(
            snapshot,
            run,
            worker_id="stale-worker",
            lease_token=lease[source["id"]],
            source_status="healthy",
            error_msg="",
            last_check_time=now,
        )


async def test_source_health_repository_does_not_claim_disabled_source_for_probe(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-disabled-lease.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    disabled = await source_repo.create_book_source(
        {"bookSourceName": "禁用源", "bookSourceUrl": "https://disabled-lease.example", "enabled": False},
        actor_id=1,
    )

    assert health_repo.claim_probe_source_leases(
        [disabled["id"]],
        worker_id="disabled-worker",
        lease_seconds=60,
    ) == {}


async def test_source_health_repository_rejects_probe_write_after_deadline(monkeypatch, tmp_path):
    import time

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-write-deadline.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    source = await source_repo.create_book_source(
        {"bookSourceName": "截止源", "bookSourceUrl": "https://deadline.example", "enabled": True},
        actor_id=1,
    )
    lease = health_repo.claim_probe_source_leases(
        [source["id"]],
        worker_id="deadline-worker",
        lease_seconds=60,
    )
    now = datetime.now(timezone.utc)
    snapshot = SourceHealthSnapshot(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        source_url=source["bookSourceUrl"],
        health_status="healthy",
        search_status="ok",
        toc_status="ok",
        content_status="ok",
        route_policy="allow",
        route_score=100,
        last_probe_at=now,
        next_probe_at=now,
    )
    run = SourceProbeRun(
        source_id=source["id"],
        source_name=source["bookSourceName"],
        probe_mode="full_chain",
        keyword="sample",
        overall_status="healthy",
        failure_reason="",
        created_at=now,
    )

    with pytest.raises(TimeoutError, match="deadline"):
        health_repo.record_probe_result(
            snapshot,
            run,
            worker_id="deadline-worker",
            lease_token=lease[source["id"]],
            write_deadline=time.monotonic() - 1,
            source_status="healthy",
            error_msg="",
            last_check_time=now,
        )

    assert health_repo.get_snapshot(source["id"]) is None


async def test_source_health_repository_claims_due_candidates_without_overlap(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-claims.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    first = await source_repo.create_book_source(
        {"bookSourceName": "抢占一", "bookSourceUrl": "https://claim-one.example", "enabled": True},
        actor_id=1,
    )
    second = await source_repo.create_book_source(
        {"bookSourceName": "抢占二", "bookSourceUrl": "https://claim-two.example", "enabled": True},
        actor_id=1,
    )

    claimed_by_a = health_repo.claim_probe_candidate_ids(
        limit=2,
        worker_id="worker-a",
        lease_seconds=60,
    )
    claimed_by_b = health_repo.claim_probe_candidate_ids(
        limit=2,
        worker_id="worker-b",
        lease_seconds=60,
    )

    assert claimed_by_a == [first["id"], second["id"]]
    assert claimed_by_b == []

    health_repo.release_probe_claims(claimed_by_a, worker_id="worker-a")
    claimed_after_release = health_repo.claim_probe_candidate_ids(
        limit=2,
        worker_id="worker-b",
        lease_seconds=60,
    )
    assert claimed_after_release == claimed_by_a


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


async def test_source_repository_disables_only_stale_error_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "stale-sources.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.schema import BookSourceModel
    from app.infrastructure.persistence.sqlite.session import SessionLocal

    bootstrap_sqlite()
    db = SessionLocal()
    try:
        from datetime import datetime, timedelta

        old = BookSourceModel(
            bookSourceName="旧失败源",
            bookSourceUrl="https://old.example",
            payload="{}",
            sourceStatus="error",
            lastCheckTime=datetime.utcnow() - timedelta(days=8),
            enabled=True,
        )
        recent = BookSourceModel(
            bookSourceName="近期失败源",
            bookSourceUrl="https://recent.example",
            payload="{}",
            sourceStatus="error",
            lastCheckTime=datetime.utcnow() - timedelta(days=1),
            enabled=True,
        )
        db.add_all([old, recent])
        db.commit()
    finally:
        db.close()

    disabled = await build_source_repository().disable_stale_sources(
        datetime.utcnow() - timedelta(days=7),
    )

    assert [item["source_url"] for item in disabled] == ["https://old.example"]

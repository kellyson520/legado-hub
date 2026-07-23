import pytest


def test_source_health_probe_uses_thirty_minute_schedule_and_batch_default():
    from app.core.config import Settings
    from app.tasks.scheduler import JOBS

    probe_job = next(item for item in JOBS if item[0] == "probe_source_health")

    assert probe_job[1] == "*/30 * * * *"
    assert Settings().SOURCE_HEALTH_PROBE_BATCH_SIZE == 50
    assert Settings().SOURCE_HEALTH_PROBE_BATCH_TIMEOUT_SECONDS == 1500


@pytest.mark.asyncio
async def test_health_service_quarantines_and_rolls_back_unstable_version(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import (
        build_job_service,
        build_source_health_service,
        build_source_review_repository,
        build_source_runtime_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.com/source",
        payload={"ruleSearch": {"bookList": ".book"}},
        created_by="admin",
    )
    repo.update_version_status(version.id, "published")
    repo.record_test_run(
        source_version_id=version.id,
        trigger="health_check",
        score=20,
        grade="D",
        step_results={"search": {"passed": False, "elapsed_ms": 120}},
        diagnostics=["search failed"],
    )

    service = build_source_health_service()
    result = await service.verify_published_versions()
    review_items = build_source_review_repository().list_items(status='candidate')
    jobs = build_job_service().list_jobs()
    candidate_versions = [
        item for item in repo.list_versions('book', 'https://example.com/source')
        if item.status == 'candidate'
    ]

    assert result[0]["action"] == "rollback"
    assert result[0]["new_status"] == "rolled_back"
    assert result[0]['discovery_submission']['job_id'] == jobs[0].id
    assert review_items[0].review_type == 'health_regression'
    assert review_items[0].source_version_id == version.id
    assert review_items[0].payload['action'] == 'rollback'
    assert jobs[0].kind == 'source.build'
    assert jobs[0].payload['trigger'] == 'health_regression'
    assert jobs[0].payload['baseline_source_version_id'] == version.id
    assert candidate_versions[0].payload['discovery']['reason'] == 'rollback'


@pytest.mark.asyncio
async def test_scheduler_health_job_runs_runtime_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-job.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import (
        build_job_service,
        build_source_review_repository,
        build_source_runtime_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_runtime_repository()
    version = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.com/source",
        payload={"ruleSearch": {"bookList": ".book"}},
        created_by="admin",
    )
    repo.update_version_status(version.id, "published")
    repo.record_test_run(
        source_version_id=version.id,
        trigger="health_check",
        score=20,
        grade="D",
        step_results={"search": {"passed": False, "elapsed_ms": 120}},
        diagnostics=["search failed"],
    )

    from app.tasks.scheduler import run_source_runtime_health_job

    result = await run_source_runtime_health_job()
    review_items = build_source_review_repository().list_items(status='candidate')
    jobs = build_job_service().list_jobs()
    assert result[0]["action"] == "rollback"
    assert review_items[0].review_type == 'health_regression'
    assert jobs[0].payload['trigger'] == 'health_regression'


@pytest.mark.asyncio
async def test_run_source_health_probe_job_invokes_admin_service(monkeypatch):
    from app.tasks import scheduler

    class FakeAdminService:
        async def probe_book_sources(self, source_ids, keyword_samples, probe_mode="full_chain"):
            return {
                "results": [{"snapshot": {"health_status": "healthy", "source_id": 7}}],
                "total": 1,
            }

    monkeypatch.setattr(scheduler, "build_source_health_admin_service", lambda: FakeAdminService())

    result = await scheduler.run_source_health_probe_job(source_ids=[7], keyword_samples=["斗罗大陆"])

    assert result["total"] == 1
    assert result["results"][0]["snapshot"]["health_status"] == "healthy"


@pytest.mark.asyncio
async def test_smart_source_health_probe_uses_bounded_unprobed_candidates(monkeypatch):
    from app.tasks import scheduler

    class FakeAdminService:
        def list_probe_candidate_ids(self, limit):
            assert limit == 3
            return [4, 7, 8]

        async def probe_book_sources(self, source_ids, keyword_samples, probe_mode="full_chain", **kwargs):
            return {
                "results": [{"snapshot": {"source_id": source_id}} for source_id in source_ids],
                "total": len(source_ids),
                "keyword_samples": keyword_samples,
            }

    monkeypatch.setattr(scheduler, "build_source_health_admin_service", lambda: FakeAdminService())

    result = await scheduler.run_smart_source_health_probe_job(
        limit=3,
        keyword_samples=["捞尸人", "斗罗大陆"],
    )

    assert result["total"] == 3
    assert [item["snapshot"]["source_id"] for item in result["results"]] == [4, 7, 8]
    assert result["keyword_samples"] == ["捞尸人", "斗罗大陆"]


@pytest.mark.asyncio
async def test_smart_source_health_probe_closes_probe_service(monkeypatch):
    from app.tasks import scheduler

    class FakeAdminService:
        def __init__(self):
            self.closed = False

        def list_probe_candidate_ids(self, limit):
            return []

        async def aclose(self):
            self.closed = True

    service = FakeAdminService()
    monkeypatch.setattr(scheduler, "build_source_health_admin_service", lambda: service)

    result = await scheduler.run_smart_source_health_probe_job(limit=3)

    assert result["total"] == 0
    assert service.closed is True


@pytest.mark.asyncio
async def test_run_catalog_source_discovery_job_enqueues_enabled_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-catalog-discovery.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import (
        build_job_service,
        build_source_repository,
        build_source_runtime_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.tasks.scheduler import run_catalog_source_discovery_job

    bootstrap_sqlite()
    repo = build_source_repository()
    await repo.upsert_book_sources(
        [
            {
                'bookSourceName': 'Catalog Alpha',
                'bookSourceUrl': 'https://alpha.test/books/',
                'bookSourceGroup': 'seed',
                'enabled': True,
            },
            {
                'bookSourceName': 'Catalog Beta',
                'bookSourceUrl': 'https://beta.test/books/',
                'bookSourceGroup': 'seed',
                'enabled': True,
            },
            {
                'bookSourceName': 'Catalog Disabled',
                'bookSourceUrl': 'https://disabled.test/books/',
                'bookSourceGroup': 'seed',
                'enabled': False,
            },
        ],
        actor_id=1,
    )

    result = await run_catalog_source_discovery_job(limit=10)
    jobs = build_job_service().list_jobs()
    runtime_repo = build_source_runtime_repository()

    assert result['total'] == 2
    assert {item['catalog_source_name'] for item in result['items']} == {'Catalog Alpha', 'Catalog Beta'}
    assert all(job.payload['trigger'] == 'configured_catalog' for job in jobs)
    alpha_versions = runtime_repo.list_versions('book', 'https://alpha.test/books')
    assert alpha_versions[0].payload['discovery']['catalog_source_name'] == 'Catalog Alpha'


@pytest.mark.asyncio
async def test_run_catalog_source_discovery_job_respects_origin_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-catalog-origin-budget.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import (
        build_job_service,
        build_source_repository,
        build_source_runtime_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.tasks.scheduler import run_catalog_source_discovery_job

    bootstrap_sqlite()
    repo = build_source_repository()
    await repo.upsert_book_sources(
        [
            {
                'bookSourceName': 'Same Origin A',
                'bookSourceUrl': 'https://same.test/books/a',
                'bookSourceGroup': 'seed',
                'enabled': True,
            },
            {
                'bookSourceName': 'Same Origin B',
                'bookSourceUrl': 'https://same.test/books/b',
                'bookSourceGroup': 'seed',
                'enabled': True,
            },
            {
                'bookSourceName': 'Other Origin',
                'bookSourceUrl': 'https://other.test/books/c',
                'bookSourceGroup': 'seed',
                'enabled': True,
            },
        ],
        actor_id=1,
    )

    result = await run_catalog_source_discovery_job(limit=10, origin_budget=1)
    jobs = build_job_service().list_jobs()
    runtime_repo = build_source_runtime_repository()

    assert result['selected_urls'] == [
        'https://same.test/books/a',
        'https://other.test/books/c',
    ]
    assert result['total'] == 2
    assert len(jobs) == 2
    assert runtime_repo.list_versions('book', 'https://same.test/books/b') == []


@pytest.mark.asyncio
async def test_run_catalog_source_discovery_job_prioritizes_regressed_sources_within_origin_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-catalog-priority.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import (
        build_source_repository,
        build_source_runtime_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.tasks.scheduler import run_catalog_source_discovery_job

    bootstrap_sqlite()
    repo = build_source_repository()
    await repo.upsert_book_sources(
        [
            {
                'bookSourceName': 'Healthy Same Origin',
                'bookSourceUrl': 'https://same.test/books/healthy',
                'bookSourceGroup': 'seed',
                'enabled': True,
                'sourceStatus': 'ok',
            },
            {
                'bookSourceName': 'Regressed Same Origin',
                'bookSourceUrl': 'https://same.test/books/regressed',
                'bookSourceGroup': 'seed',
                'enabled': True,
                'sourceStatus': 'error',
                'errorMsg': 'search failed',
            },
            {
                'bookSourceName': 'Other Origin',
                'bookSourceUrl': 'https://other.test/books/normal',
                'bookSourceGroup': 'seed',
                'enabled': True,
                'sourceStatus': 'ok',
            },
        ],
        actor_id=1,
    )

    result = await run_catalog_source_discovery_job(limit=10, origin_budget=1)
    runtime_repo = build_source_runtime_repository()

    assert result['selected_urls'] == [
        'https://same.test/books/regressed',
        'https://other.test/books/normal',
    ]
    assert runtime_repo.list_versions('book', 'https://same.test/books/healthy') == []
    regressed_versions = runtime_repo.list_versions('book', 'https://same.test/books/regressed')
    assert regressed_versions[0].payload['discovery']['catalog_source_name'] == 'Regressed Same Origin'

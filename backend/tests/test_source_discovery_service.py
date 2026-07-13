from datetime import datetime, timedelta, timezone


def test_discovery_skips_open_circuit_and_respects_origin_budget():
    from app.application.services.source_discovery_service import SourceDiscoveryService

    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    discovery = SourceDiscoveryService(origin_budget=1, cooldown_seconds=60)
    discovery.enqueue_candidate('https://blocked.test/books')
    discovery.mark_origin_blocked('https://blocked.test/books', now=now)

    assert discovery.next_jobs(now=now) == []


def test_discovery_limits_jobs_per_origin_in_one_poll():
    from app.application.services.source_discovery_service import SourceDiscoveryService

    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    discovery = SourceDiscoveryService(origin_budget=1, cooldown_seconds=60)
    discovery.enqueue_candidate('https://same.test/books/a')
    discovery.enqueue_candidate('https://same.test/books/b')
    discovery.enqueue_candidate('https://other.test/books/c')

    assert discovery.next_jobs(now=now) == [
        'https://same.test/books/a',
        'https://other.test/books/c',
    ]


def test_discovery_prioritizes_higher_priority_candidates_before_origin_budget():
    from app.application.services.source_discovery_service import SourceDiscoveryService

    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    discovery = SourceDiscoveryService(origin_budget=1, cooldown_seconds=60)
    discovery.enqueue_candidate('https://same.test/books/healthy', priority=10)
    discovery.enqueue_candidate('https://same.test/books/regressed', priority=90)
    discovery.enqueue_candidate('https://other.test/books/normal', priority=20)

    assert discovery.next_jobs(now=now) == [
        'https://same.test/books/regressed',
        'https://other.test/books/normal',
    ]


def test_discovery_requeues_failed_job_with_exponential_backoff():
    from app.application.services.source_discovery_service import SourceDiscoveryService

    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    discovery = SourceDiscoveryService(origin_budget=1, cooldown_seconds=60, retry_base_seconds=30)
    discovery.enqueue_candidate('https://retry.test/books')

    assert discovery.next_jobs(now=now) == ['https://retry.test/books']
    discovery.record_result('https://retry.test/books', success=False, now=now)

    assert discovery.next_jobs(now=now + timedelta(seconds=29)) == []
    assert discovery.next_jobs(now=now + timedelta(seconds=30)) == ['https://retry.test/books']

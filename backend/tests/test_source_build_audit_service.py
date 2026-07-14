from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
from app.domain.entities.source_runtime import SourceVersion


class FakeRuntimeRepository:
    def __init__(self, version):
        self.version = version
        self.runs = []

    def get_version(self, version_id):
        return self.version if version_id == self.version.id else None

    def update_version_payload(self, version_id, payload):
        assert version_id == self.version.id
        self.version.payload = payload
        return self.version

    def update_version_status(self, version_id, status):
        assert version_id == self.version.id
        self.version.status = status
        return self.version

    def record_test_run(self, **kwargs):
        self.runs.append(kwargs)


class PassingProbe:
    def __init__(self):
        self.closed = False

    async def probe_source(self, source, keyword_samples, probe_mode):
        assert source['id'] == 17
        assert keyword_samples == ['sample']
        assert probe_mode == 'full_chain'
        return SourceProbeEvidence(
            source_id=17,
            source_name='Example',
            source_url='https://example.test',
            probe_mode='full_chain',
            keyword='sample',
            search=StageProbeResult(
                stage='search', status='ok', elapsed_ms=12, hit_count=1, sample_title='Sample Book'
            ),
            toc=StageProbeResult(
                stage='toc', status='ok', elapsed_ms=15, hit_count=2, sample_title='Chapter 1'
            ),
            content=StageProbeResult(
                stage='content', status='ok', elapsed_ms=25, sample_title='Chapter 1',
                detail={'content_length': 120},
            ),
        )

    async def aclose(self):
        self.closed = True


class ShortContentProbe(PassingProbe):
    async def probe_source(self, source, keyword_samples, probe_mode):
        evidence = await super().probe_source(source, keyword_samples, probe_mode)
        evidence.content.detail['content_length'] = 79
        return evidence


class CrashingProbe(PassingProbe):
    async def probe_source(self, source, keyword_samples, probe_mode):
        raise RuntimeError('upstream page body must never be persisted')


class FakeBuildService:
    def __init__(self):
        self.repairs = []

    def submit_audit_repair(self, **kwargs):
        self.repairs.append(kwargs)


class FakeReviewService:
    def __init__(self):
        self.failures = []

    def enqueue_audit_failure(self, **kwargs):
        self.failures.append(kwargs)


class FakeReviewRepository:
    def __init__(self):
        self.items = []

    def save_item(self, item):
        self.items.append(item)
        return item


async def test_audit_candidate_passes_with_compact_report_and_closes_fresh_probe():
    from app.application.services.source_build_audit_service import SourceBuildAuditService

    version = SourceVersion(
        id='candidate-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='candidate',
        payload={
            'keyword': 'sample',
            'source_rule': {'bookSourceUrl': 'https://example.test'},
            'source_audit': {'status': 'pending', 'attempt': 0, 'max_attempts': 5, 'history': []},
        },
    )
    runtime = FakeRuntimeRepository(version)
    probes = []

    def probe_factory():
        probe = PassingProbe()
        probes.append(probe)
        return probe

    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=probe_factory,
        build_service=None,
        review_service=None,
    )

    result = await service.audit('candidate-1')

    assert result['status'] == 'passed'
    assert version.status == 'candidate'
    assert len(probes) == 1
    assert probes[0].closed is True
    audit = version.payload['source_audit']
    assert audit['status'] == 'passed'
    assert audit['attempt'] == 1
    assert audit['max_attempts'] == 5
    assert audit['report'] == {
        'status': 'passed',
        'attempt': 1,
        'max_attempts': 5,
        'score': 100,
        'grade': 'A',
        'total_elapsed_ms': 52,
        'stages': {
            'search': {'status': 'ok', 'elapsed_ms': 12, 'hit_count': 1, 'title': 'Sample Book'},
            'toc': {'status': 'ok', 'elapsed_ms': 15, 'hit_count': 2, 'title': 'Chapter 1'},
            'content': {'status': 'ok', 'elapsed_ms': 25, 'content_length': 120, 'title': 'Chapter 1'},
        },
    }
    assert result['score'] == 100
    assert result['grade'] == 'A'
    assert runtime.runs == [{
        'source_version_id': 'candidate-1',
        'trigger': 'source_audit',
        'score': 100,
        'grade': 'A',
        'step_results': {
            'search': {'passed': True, 'status': 'ok', 'elapsed_ms': 12},
            'toc': {'passed': True, 'status': 'ok', 'elapsed_ms': 15},
            'content': {'passed': True, 'status': 'ok', 'elapsed_ms': 25},
        },
        'diagnostics': [],
    }]


async def test_failed_audit_queues_same_version_repair_through_attempt_four():
    from app.application.services.source_build_audit_service import SourceBuildAuditService

    version = SourceVersion(
        id='candidate-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='candidate',
        created_by='tenant-1',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test',
            'source_rule': {'bookSourceUrl': 'https://example.test'},
            'source_audit': {'status': 'pending', 'attempt': 0, 'max_attempts': 5, 'history': []},
        },
    )
    runtime = FakeRuntimeRepository(version)
    build = FakeBuildService()
    review = FakeReviewService()
    probes = []

    def probe_factory():
        probe = ShortContentProbe()
        probes.append(probe)
        return probe

    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=probe_factory,
        build_service=build,
        review_service=review,
    )

    result = await service.audit('candidate-1')

    assert result['status'] == 'retry_queued'
    assert version.status == 'candidate'
    assert probes[0].closed is True
    assert version.payload['source_audit']['status'] == 'retry_queued'
    assert version.payload['source_audit']['attempt'] == 1
    assert version.payload['source_audit']['report']['reason'] == 'content_too_short'
    assert build.repairs == [{
        'tenant_id': 'tenant-1',
        'source_version_id': 'candidate-1',
        'url': 'https://example.test',
        'keyword': 'sample',
        'next_attempt': 2,
    }]
    assert review.failures == []
    assert runtime.runs[0]['score'] == 0
    assert runtime.runs[0]['grade'] == 'F'
    assert runtime.runs[0]['step_results']['search']['passed'] is True
    assert runtime.runs[0]['step_results']['toc']['passed'] is True
    assert runtime.runs[0]['step_results']['content']['passed'] is False


async def test_fifth_failed_audit_marks_candidate_failed_and_enqueues_one_review():
    from app.application.services.source_build_audit_service import SourceBuildAuditService
    from app.application.services.source_review_service import SourceReviewService

    version = SourceVersion(
        id='candidate-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='candidate',
        created_by='tenant-1',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test',
            'source_rule': {'bookSourceUrl': 'https://example.test'},
            'source_audit': {'status': 'retry_queued', 'attempt': 4, 'max_attempts': 5, 'history': []},
        },
    )
    runtime = FakeRuntimeRepository(version)
    build = FakeBuildService()
    review_repo = FakeReviewRepository()
    review = SourceReviewService(review_repo)
    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=ShortContentProbe,
        build_service=build,
        review_service=review,
    )

    result = await service.audit('candidate-1')

    assert result['status'] == 'failed'
    assert version.status == 'failed'
    assert version.payload['source_audit']['status'] == 'failed'
    assert version.payload['source_audit']['attempt'] == 5
    assert build.repairs == []
    assert len(review_repo.items) == 1
    item = review_repo.items[0]
    assert item.review_type == 'source_audit_failed'
    assert item.source_version_id == 'candidate-1'
    assert item.source_url == 'https://example.test'
    assert item.created_by == 'system'
    assert item.payload['audit_report'] == version.payload['source_audit']['report']


async def test_missing_source_rule_retries_without_creating_a_probe():
    from app.application.services.source_build_audit_service import SourceBuildAuditService

    version = SourceVersion(
        id='candidate-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='candidate',
        created_by='tenant-1',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test',
            'source_audit': {'status': 'pending', 'attempt': 0, 'max_attempts': 5, 'history': []},
        },
    )
    runtime = FakeRuntimeRepository(version)
    build = FakeBuildService()

    def forbidden_probe_factory():
        raise AssertionError('missing source rules must not be probed')

    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=forbidden_probe_factory,
        build_service=build,
        review_service=FakeReviewService(),
    )

    result = await service.audit('candidate-1')

    assert result['status'] == 'retry_queued'
    assert version.payload['source_audit']['report']['reason'] == 'missing_source_rule'
    assert build.repairs == [{
        'tenant_id': 'tenant-1',
        'source_version_id': 'candidate-1',
        'url': 'https://example.test',
        'keyword': 'sample',
        'next_attempt': 2,
    }]


async def test_audit_ignores_non_candidate_versions_before_creating_probe():
    from app.application.services.source_build_audit_service import SourceBuildAuditService

    version = SourceVersion(
        id='published-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='published',
        payload={'source_rule': {'bookSourceUrl': 'https://example.test'}},
    )
    runtime = FakeRuntimeRepository(version)
    build = FakeBuildService()
    review = FakeReviewService()

    def forbidden_probe_factory():
        raise AssertionError('only candidate versions may be probed')

    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=forbidden_probe_factory,
        build_service=build,
        review_service=review,
    )

    result = await service.audit('published-1')

    assert result == {
        'source_version_id': 'published-1',
        'status': 'skipped',
        'reason': 'not_candidate',
    }
    assert runtime.runs == []
    assert build.repairs == []
    assert review.failures == []


async def test_probe_exception_creates_compact_failed_evidence_and_queues_repair():
    from app.application.services.source_build_audit_service import SourceBuildAuditService

    version = SourceVersion(
        id='candidate-1',
        source_definition_id=17,
        source_type='book',
        source_id='https://example.test',
        status='candidate',
        created_by='tenant-1',
        payload={
            'keyword': 'sample',
            'canonical_url': 'https://example.test',
            'source_rule': {'bookSourceUrl': 'https://example.test'},
            'source_audit': {'status': 'pending', 'attempt': 0, 'max_attempts': 5, 'history': []},
        },
    )
    runtime = FakeRuntimeRepository(version)
    build = FakeBuildService()
    probes = []

    def probe_factory():
        probe = CrashingProbe()
        probes.append(probe)
        return probe

    service = SourceBuildAuditService(
        runtime_repo=runtime,
        probe_service_factory=probe_factory,
        build_service=build,
        review_service=FakeReviewService(),
    )

    result = await service.audit('candidate-1')

    assert result['status'] == 'retry_queued'
    assert result['score'] == 0
    assert result['grade'] == 'F'
    assert probes[0].closed is True
    report = version.payload['source_audit']['report']
    assert report['reason'] == 'probe_error'
    assert report['stages']['search']['status'] == 'failed'
    assert 'body' not in str(report)
    assert build.repairs[0]['next_attempt'] == 2

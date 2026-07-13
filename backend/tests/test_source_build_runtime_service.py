import asyncio


def test_compatibility_engine_generates_bqgiu_template():
    from app.core.compatibility import CompatibilityEngine

    engine = CompatibilityEngine()
    source = engine.generate_from_url("https://www.bqgiu.cc/", source_name="bqgiu")

    assert engine.match_site("https://www.bqgiu.cc/") == "bqgiu"
    assert source["bookSourceName"] == "bqgiu"
    assert source["searchUrl"] == "https://www.bqgiu.cc/"
    assert source["ruleSearch"]["bookList"] == "class.hot@class.item"
    assert source["ruleToc"]["chapterList"].startswith("id.list")
    assert "chaptercontent" in source["ruleContent"]["content"]


def test_source_build_runtime_service_records_agent_run_and_updates_candidate_version(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-runtime.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.factory import build_source_build_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.infrastructure.persistence.factory import build_agent_runtime_service

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://example.test/books',
            'source_version_id': version.id,
            'site_profile': {
                'site_id': 'example.test',
                'dom_signatures': ['sig-1'],
                'template_patch': {'selector': '#book-list'},
                'fixture_coverage': 0.95,
                'confidence': 0.92,
                'risk_level': 'low',
            },
            'evidence': {
                'dom_signature': 'sig-1',
                'patch_candidate': {'selector': '#book-list'},
            },
            'fixture_validation_passed': True,
            'sample_validation_passed': True,
            'budget_remaining': 600,
            'trigger': 'configured_catalog',
        },
    )

    result = build_source_build_runtime_service().handle_job(job)

    agent_runtime = build_agent_runtime_service()
    history = agent_runtime.get_tool_history(result['agent_run_id'], tenant_id='system')
    updated = runtime_repo.get_version(version.id)

    assert result['decision'] == 'canary'
    assert history is not None
    assert [item.tool_name for item in history] == ['source.inspect', 'rule.validate']
    assert history[1].result is not None
    assert history[1].result.data['decision'] == 'canary'
    assert updated is not None
    assert updated.payload['autonomous_build']['agent_run_id'] == result['agent_run_id']
    assert updated.payload['autonomous_build']['decision'] == 'canary'
    assert updated.payload['autonomous_build']['trigger'] == 'configured_catalog'


def test_source_build_runtime_service_uses_live_probe_when_payload_context_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-runtime-probe.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
    from app.infrastructure.persistence.factory import (
        build_agent_runtime_service,
        build_source_build_agent,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class FakeProbeService:
        async def probe_source(self, source, keyword_samples, probe_mode='full_chain'):
            return SourceProbeEvidence(
                source_id=source['id'],
                source_name=source.get('bookSourceName', ''),
                source_url=source.get('bookSourceUrl', ''),
                probe_mode=probe_mode,
                keyword=keyword_samples[0],
                search=StageProbeResult(
                    stage='search',
                    status='ok',
                    elapsed_ms=120,
                    request_preview='https://example.test/books/search?keyword=novel',
                    hit_count=1,
                    sample_title='Sample Book',
                    detail={
                        'top_hit': {
                            'name': 'Sample Book',
                            'bookUrl': 'https://example.test/books/1',
                        }
                    },
                ),
                toc=StageProbeResult(
                    stage='toc',
                    status='ok',
                    elapsed_ms=80,
                    hit_count=12,
                    sample_title='Chapter 1',
                    detail={
                        'first_chapter': {
                            'title': 'Chapter 1',
                            'url': 'https://example.test/books/1/1',
                        }
                    },
                ),
                content=StageProbeResult(
                    stage='content',
                    status='ok',
                    elapsed_ms=65,
                    sample_title='Chapter 1',
                    detail={'content_length': 2048},
                ),
            )

        async def aclose(self):
            return None

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://example.test/books',
            'source_version_id': version.id,
            'trigger': 'configured_catalog',
        },
    )

    service = SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=build_source_build_agent(),
        probe_factory=lambda: FakeProbeService(),
    )
    result = service.handle_job(job)

    history = build_agent_runtime_service().get_tool_history(result['agent_run_id'], tenant_id='system')
    updated = runtime_repo.get_version(version.id)

    assert result['decision'] == 'canary'
    assert history is not None
    assert history[0].result is not None
    assert history[0].result.data['inspection_mode'] == 'live_probe'
    assert history[0].result.data['probe_summary']['search_status'] == 'ok'
    assert history[0].result.data['probe_summary']['content_length'] == 2048
    assert history[0].result.data['source_rule']['bookSourceUrl'] == 'https://example.test/books'
    assert history[0].result.data['rule_patch']['operations'][0]['op'] in {
        'apply_fallback_rules',
        'apply_site_template',
    }
    assert history[0].evidence[0].payload['probe_summary']['sample_title'] == 'Chapter 1'
    assert history[1].tool_name == 'rule.validate'
    assert history[1].result is not None
    assert history[1].result.data['decision'] == 'canary'
    assert history[1].result.data['validation']['search']['passed'] is True
    assert history[1].result.data['validation']['toc']['passed'] is True
    assert history[1].result.data['validation']['content']['passed'] is True
    assert updated is not None
    assert updated.payload['source_rule']['bookSourceUrl'] == 'https://example.test/books'
    assert updated.payload['rule_patch']['operations'][0]['field'] == 'ruleSearch'
    assert updated.payload['autonomous_build']['validation']['fixture_validation_passed'] is True
    assert updated.payload['autonomous_build']['validation']['sample_validation_passed'] is True
    assert updated.payload['autonomous_build']['inspection_mode'] == 'live_probe'
    assert updated.payload['autonomous_build']['probe']['search_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['toc_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['content_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['sample_title'] == 'Chapter 1'


def test_source_build_runtime_service_escalation_persists_review_queue_and_agent_trace(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-runtime-escalate.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.factory import (
        build_agent_runtime_service,
        build_source_build_runtime_service,
        build_source_review_repository,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://blocked.test/books',
        payload={'canonical_url': 'https://blocked.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://blocked.test/books',
            'source_version_id': version.id,
            'site_profile': {
                'site_id': 'blocked.test',
                'fixture_coverage': 0.1,
                'confidence': 0.2,
                'risk_level': 'high',
            },
            'evidence': {
                'dom_signature': 'sig-9',
                'sampled_content': '<html>blocked</html>',
            },
            'fixture_validation_passed': False,
            'sample_validation_passed': False,
            'budget_remaining': 0,
            'trigger': 'health_regression',
            'reason': 'rollback',
        },
    )

    result = build_source_build_runtime_service().handle_job(job)

    agent_runtime = build_agent_runtime_service()
    history = agent_runtime.get_tool_history(result['agent_run_id'], tenant_id='system')
    updated = runtime_repo.get_version(version.id)
    review_item = build_source_review_repository().get_item(result['review_item']['id'])

    assert result['decision'] == 'escalate'
    assert history is not None
    assert [item.tool_name for item in history] == ['source.inspect', 'review.request']
    assert history[1].evidence[0].resource_id == result['review_item']['id']
    assert updated is not None
    assert updated.payload['autonomous_build']['decision'] == 'escalate'
    assert updated.payload['autonomous_build']['review_item_id'] == result['review_item']['id']
    assert review_item is not None
    assert review_item.review_type == 'build_escalation'


def test_run_source_build_job_processes_queued_build_and_returns_backflow_summary(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-runtime-job.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
    from app.tasks.scheduler import run_source_build_job

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book',
        source_id='https://queue.test/books',
        payload={'canonical_url': 'https://queue.test/books'},
        created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build',
        tenant_id='system',
        payload={
            'url': 'https://queue.test/books',
            'source_version_id': version.id,
            'site_profile': {
                'site_id': 'queue.test',
                'dom_signatures': ['sig-queue'],
                'template_patch': {'selector': '#queue'},
                'fixture_coverage': 0.9,
                'confidence': 0.9,
                'risk_level': 'low',
            },
            'evidence': {
                'dom_signature': 'sig-queue',
                'patch_candidate': {'selector': '#queue'},
            },
            'fixture_validation_passed': True,
            'sample_validation_passed': True,
        },
    )

    result = asyncio.run(run_source_build_job(limit=1))

    updated = runtime_repo.get_version(version.id)
    history = build_agent_runtime_service().get_tool_history(
        result['jobs'][0]['build_result']['agent_run_id'],
        tenant_id='system',
    )

    assert result['processed'] == 1
    assert result['jobs'][0]['job_id'] == job.id
    assert result['jobs'][0]['status'] == 'succeeded'
    assert result['jobs'][0]['build_result']['decision'] == 'canary'
    assert updated is not None
    assert updated.payload['autonomous_build']['decision'] == 'canary'
    assert history is not None
    assert history[0].tool_name == 'source.inspect'

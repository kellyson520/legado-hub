import asyncio

import pytest


def test_source_build_runtime_deterministic_success_never_starts_agent(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-deterministic.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_agent import SourceBuildAgentResult
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class DeterministicBuildAgent:
        def attempt_repair(self, **_kwargs):
            return SourceBuildAgentResult(
                decision='canary', strategy='deterministic_patch', review_required=False, attempt_count=1,
            )

    class EnabledSettings:
        def get_source_build_agent_settings(self):
            return {'enabled': True, 'provider_configured': True}

    class FailingRepairService:
        async def repair(self, **_kwargs):
            raise AssertionError('deterministic success must not call the source-build agent')

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'}, created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={
            'url': 'https://example.test/books', 'source_version_id': version.id,
            'site_profile': {'site_id': 'example.test', 'dom_signatures': ['sig'], 'template_patch': {'x': 1}},
            'evidence': {'dom_signature': 'sig', 'patch_candidate': {'x': 1}},
            'fixture_validation_passed': True, 'sample_validation_passed': True,
        },
    )

    result = SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=DeterministicBuildAgent(),
        system_settings_service=EnabledSettings(),
        ai_repair_service=FailingRepairService(),
    ).handle_job(job)

    updated = runtime_repo.get_version(version.id)
    assert result['decision'] == 'canary'
    assert updated is not None
    assert updated.payload['autonomous_build']['agent'] == {
        'state': 'not_requested',
        'status': 'not_requested',
        'reason': 'deterministic_success',
    }


def test_source_build_runtime_skips_llm_repair_when_agent_setting_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-disabled.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_agent import SourceBuildAgentResult
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class LlmRepairBuildAgent:
        def attempt_repair(self, **_kwargs):
            return SourceBuildAgentResult(
                decision='defer', strategy='llm_repair', review_required=False, attempt_count=1,
            )

    class DisabledSettings:
        def get_source_build_agent_settings(self):
            return {'enabled': False, 'provider_configured': True}

    class RecordingRepairService:
        calls = 0

        async def repair(self, **_kwargs):
            self.calls += 1
            return {}

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'}, created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={
            'url': 'https://example.test/books', 'source_version_id': version.id,
            'site_profile': {'site_id': 'example.test', 'dom_signatures': ['sig'], 'template_patch': {'x': 1}},
            'evidence': {'dom_signature': 'sig', 'patch_candidate': {'x': 1}},
        },
    )
    repair = RecordingRepairService()

    result = SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=LlmRepairBuildAgent(),
        system_settings_service=DisabledSettings(),
        ai_repair_service=repair,
    ).handle_job(job)

    updated = runtime_repo.get_version(version.id)
    assert result['decision'] == 'defer'
    assert repair.calls == 0
    assert updated is not None
    assert updated.payload['autonomous_build']['agent'] == {
        'state': 'not_requested',
        'status': 'skipped_not_configured',
        'reason': 'disabled',
    }


def test_source_build_runtime_skips_llm_repair_without_configured_provider(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-no-provider.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_agent import SourceBuildAgentResult
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class LlmRepairBuildAgent:
        def attempt_repair(self, **_kwargs):
            return SourceBuildAgentResult(
                decision='defer', strategy='llm_repair', review_required=False, attempt_count=1,
            )

    class NoProviderSettings:
        def get_source_build_agent_settings(self):
            return {'enabled': True, 'provider_configured': False}

    class FailingRepairService:
        async def repair(self, **_kwargs):
            raise AssertionError('agent must not run without a configured provider')

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'}, created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={
            'url': 'https://example.test/books', 'source_version_id': version.id,
            'site_profile': {'site_id': 'example.test', 'dom_signatures': ['sig'], 'template_patch': {'x': 1}},
            'evidence': {'dom_signature': 'sig', 'patch_candidate': {'x': 1}},
        },
    )

    SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=LlmRepairBuildAgent(),
        system_settings_service=NoProviderSettings(),
        ai_repair_service=FailingRepairService(),
    ).handle_job(job)

    updated = runtime_repo.get_version(version.id)
    assert updated is not None
    assert updated.payload['autonomous_build']['agent'] == {
        'state': 'not_requested',
        'status': 'skipped_not_configured',
        'reason': 'provider_not_configured',
    }


def test_source_build_runtime_persists_validated_agent_patch_for_review_only(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-review.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_agent import SourceBuildAgentResult
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
    from app.application.services.source_review_service import SourceReviewService
    from app.domain.entities.agent_runtime import ToolResult
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_review_repo_impl import SQLiteSourceReviewRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class LlmRepairBuildAgent:
        def attempt_repair(self, **_kwargs):
            return SourceBuildAgentResult(
                decision='defer', strategy='llm_repair', review_required=False, attempt_count=1,
            )

    class EnabledSettings:
        def get_source_build_agent_settings(self):
            return {'enabled': True, 'provider_configured': True}

    class FakePageTools:
        created_for = []
        closed = 0

        def __init__(self, url):
            self.created_for.append(url)

        def handlers(self):
            async def inspect(arguments):
                assert arguments == {'url': 'https://example.test/books'}
                return ToolResult(status='accepted', data={'url': arguments['url']})
            return {'page.inspect': inspect}

        async def aclose(self):
            type(self).closed += 1

    class FakeProbeService:
        instances = []

        def __init__(self):
            self.source = None
            self.closed = False
            self.instances.append(self)

        async def probe_source(self, source, keyword_samples, probe_mode='full_chain'):
            self.source = source
            assert source['searchUrl'] == 'https://example.test/search?q={{key}}'
            assert source['ruleContent'] == {'content': '#chapter@text'}
            return SourceProbeEvidence(
                source_id=source['id'], source_name='example', source_url='https://example.test/books',
                probe_mode=probe_mode, keyword=keyword_samples[0],
                search=StageProbeResult(stage='search', status='ok', hit_count=1),
                toc=StageProbeResult(stage='toc', status='ok', hit_count=1),
                content=StageProbeResult(stage='content', status='ok', detail={'content_length': 200}),
            )

        async def aclose(self):
            self.closed = True

    class ValidatingRepairService:
        async def repair(self, *, registry, **_kwargs):
            await registry.ainvoke(
                agent_kind='source_build', tool_name='page.inspect',
                arguments={'url': 'https://example.test/books'}, tenant_id='system',
            )
            patch = {
                'searchUrl': 'https://example.test/search?q={{key}}',
                'ruleContent': {'content': '#chapter@text'},
            }
            await registry.ainvoke(
                agent_kind='source_build', tool_name='rule.propose',
                arguments={'patch': patch}, tenant_id='system',
            )
            validation = await registry.ainvoke(
                agent_kind='source_build', tool_name='rule.validate',
                arguments={'patch': patch}, tenant_id='system',
            )
            review = await registry.ainvoke(
                agent_kind='source_build', tool_name='review.request',
                arguments={'reason': 'full chain passed'}, tenant_id='system',
            )
            return {
                'id': 'ai-task-1', 'status': 'succeeded', 'provider': 'test-provider', 'model': 'test-model',
                'result': {
                    'repair': {
                        'state': 'validated_for_review', 'patch': patch,
                        'validation': validation.data, 'review': review.data,
                    },
                },
            }

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    base_rule = {
        'bookSourceName': 'example', 'bookSourceUrl': 'https://example.test/books',
        'searchUrl': 'https://example.test/old?q={{key}}',
        'ruleSearch': {'bookList': '.book', 'name': 'a@text', 'bookUrl': 'a@href'},
        'ruleToc': {'chapterList': '#list a', 'chapterName': 'text', 'chapterUrl': 'href'},
        'ruleContent': {'content': '#old@text'},
    }
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books', 'source_rule': base_rule}, created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={
            'url': 'https://example.test/books', 'source_version_id': version.id,
            'site_profile': {'site_id': 'example.test', 'dom_signatures': ['sig'], 'template_patch': {'x': 1}},
            'evidence': {'dom_signature': 'sig', 'patch_candidate': {'x': 1}}, 'keyword': 'novel',
        },
    )

    result = SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=LlmRepairBuildAgent(),
        system_settings_service=EnabledSettings(),
        ai_repair_service=ValidatingRepairService(),
        page_tool_factory=FakePageTools,
        probe_factory=FakeProbeService,
        review_service=SourceReviewService(SQLiteSourceReviewRepository()),
    ).handle_job(job)

    updated = runtime_repo.get_version(version.id)
    assert result['decision'] == 'review'
    assert result['strategy'] == 'agent_tool_loop'
    assert result['review_required'] is True
    assert result['review_item']['id']
    assert updated is not None
    assert updated.payload['source_rule']['searchUrl'] == 'https://example.test/search?q={{key}}'
    assert updated.payload['source_rule']['ruleContent'] == {'content': '#chapter@text'}
    assert updated.payload['autonomous_build']['agent']['state'] == 'validated_for_review'
    assert updated.payload['autonomous_build']['agent']['status'] == 'succeeded'
    assert updated.status == 'candidate'
    assert FakePageTools.created_for == ['https://example.test/books']
    assert FakePageTools.closed == 1
    assert len(FakeProbeService.instances) == 1
    assert all(item.closed for item in FakeProbeService.instances)


def test_source_build_runtime_keeps_policy_decision_when_page_tools_cannot_start(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-page-tools-failed.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_agent import SourceBuildAgentResult
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.infrastructure.persistence.factory import build_agent_runtime_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    class LlmRepairBuildAgent:
        def attempt_repair(self, **_kwargs):
            return SourceBuildAgentResult(
                decision='defer', strategy='llm_repair', review_required=False, attempt_count=1,
            )

    class EnabledSettings:
        def get_source_build_agent_settings(self):
            return {'enabled': True, 'provider_configured': True}

    class NeverCalledRepairService:
        async def repair(self, **_kwargs):
            raise AssertionError('page tool startup failure must stop before agent invocation')

    def failing_page_factory(_url):
        raise RuntimeError('page tool client unavailable')

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'}, created_by='system',
    )
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={
            'url': 'https://example.test/books', 'source_version_id': version.id,
            'site_profile': {'site_id': 'example.test', 'dom_signatures': ['sig'], 'template_patch': {'x': 1}},
            'evidence': {'dom_signature': 'sig', 'patch_candidate': {'x': 1}},
        },
    )

    result = SourceBuildRuntimeService(
        runtime_repo=runtime_repo,
        agent_runtime=build_agent_runtime_service(),
        build_agent=LlmRepairBuildAgent(),
        system_settings_service=EnabledSettings(),
        ai_repair_service=NeverCalledRepairService(),
        page_tool_factory=failing_page_factory,
    ).handle_job(job)

    updated = runtime_repo.get_version(version.id)
    assert result['decision'] == 'defer'
    assert updated is not None
    assert updated.payload['autonomous_build']['agent'] == {
        'state': 'failed',
        'status': 'failed',
        'reason': 'agent_not_validated',
    }


def test_source_build_runtime_rejects_published_versions_before_agent_execution(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'source-build-agent-published.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.application.services.job_service import JobService
    from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
    from app.infrastructure.persistence.factory import build_agent_runtime_service, build_source_build_agent
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    runtime_repo = SQLiteSourceRuntimeRepository()
    version = runtime_repo.create_candidate_version(
        source_type='book', source_id='https://example.test/books',
        payload={'canonical_url': 'https://example.test/books'}, created_by='system',
    )
    runtime_repo.update_version_status(version.id, 'published')
    job = JobService(SQLiteJobRepository()).enqueue(
        kind='source.build', tenant_id='system',
        payload={'url': 'https://example.test/books', 'source_version_id': version.id},
    )

    with pytest.raises(ValueError, match='candidate source version'):
        SourceBuildRuntimeService(
            runtime_repo=runtime_repo,
            agent_runtime=build_agent_runtime_service(),
            build_agent=build_source_build_agent(),
        ).handle_job(job)

    stored = runtime_repo.get_version(version.id)
    assert stored is not None
    assert stored.status == 'published'
    assert 'autonomous_build' not in stored.payload


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


def test_source_build_runtime_service_verifies_synthesized_rules_in_a_fresh_probe_session(tmp_path, monkeypatch):
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
        instances = []

        def __init__(self):
            self.synthesized_sources = []
            self.synthesis_loop = None
            self.probe_loop = None
            self.closed = False
            self.instances.append(self)

        async def synthesize_source_rule(self, *, source, entry_url, keyword):
            self.synthesis_loop = asyncio.get_running_loop()
            self.synthesized_sources.append({
                'source': source,
                'entry_url': entry_url,
                'keyword': keyword,
            })
            return {
                **source,
                'searchUrl': 'https://example.test/generated-search?key={{key}}',
            }

        async def probe_source(self, source, keyword_samples, probe_mode='full_chain'):
            self.probe_loop = asyncio.get_running_loop()
            synthesis_loop = self.synthesis_loop or self.instances[0].synthesis_loop
            assert self.probe_loop is synthesis_loop
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
            self.closed = True

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
    assert updated.payload['source_rule']['searchUrl'] == 'https://example.test/generated-search?key={{key}}'
    assert updated.payload['rule_patch']['operations'][0]['field'] == 'ruleSearch'
    assert updated.payload['autonomous_build']['validation']['fixture_validation_passed'] is True
    assert updated.payload['autonomous_build']['validation']['sample_validation_passed'] is True
    assert updated.payload['autonomous_build']['inspection_mode'] == 'live_probe'
    assert updated.payload['autonomous_build']['probe']['search_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['toc_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['content_status'] == 'ok'
    assert updated.payload['autonomous_build']['probe']['sample_title'] == 'Chapter 1'
    assert len(FakeProbeService.instances) == 2
    assert FakeProbeService.instances[0].synthesis_loop is FakeProbeService.instances[1].probe_loop
    assert all(instance.closed for instance in FakeProbeService.instances)


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

import asyncio
import concurrent.futures
import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from app.application.services.agent_runtime_service import AgentRuntimeService
from app.application.services.agent_tool_registry import AgentToolRegistry
from app.application.services.source_build_tool_executor import SourceBuildToolContext, SourceBuildToolExecutor
from app.application.services.site_profile_service import SiteProfile
from app.application.services.source_build_agent import SourceBuildAgent
from app.core.compatibility import CompatibilityEngine
from app.domain.entities.job import Job
from app.domain.repositories.source_runtime_repo import SourceRuntimeRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceBuildRuntimeService:
    _ACTIONABLE_EVIDENCE_KEYS = frozenset(
        {
            'dom_signature',
            'request_summary',
            'response_summary',
            'sampled_content',
            'patch_candidate',
        }
    )

    def __init__(
        self,
        *,
        runtime_repo: SourceRuntimeRepository,
        agent_runtime: AgentRuntimeService,
        build_agent: SourceBuildAgent,
        probe_factory: Callable[[], Any] | None = None,
        compatibility_engine: CompatibilityEngine | None = None,
        ai_repair_service=None,
    ):
        self._runtime_repo = runtime_repo
        self._agent_runtime = agent_runtime
        self._build_agent = build_agent
        self._probe_factory = probe_factory
        self._compatibility = compatibility_engine or CompatibilityEngine()
        self._ai_repair = ai_repair_service

    def handle_job(self, job: Job) -> dict:
        source_version_id = str(job.payload.get('source_version_id') or '').strip()
        if not source_version_id:
            raise ValueError('source_version_id is required')

        version = self._runtime_repo.get_version(source_version_id)
        if version is None:
            raise ValueError('source version not found')

        candidate_url = str(job.payload.get('url') or version.source_id or '').strip()
        if not candidate_url:
            raise ValueError('candidate url is required')

        tenant_id = job.tenant_id
        run = self._agent_runtime.create_run(
            tenant_id=tenant_id,
            agent_kind='source_build',
            input_payload=job.payload,
        )
        inspect_invocation = self._agent_runtime.record_tool_invocation(
            run_id=run.id,
            tenant_id=tenant_id,
            tool_name='source.inspect',
            category='operate',
            arguments={
                'url': candidate_url,
                'source_version_id': source_version_id,
                'trigger': job.payload.get('trigger', 'manual'),
            },
        )
        evidence = self._seed_evidence(version.payload, job.payload)
        raw_profile = job.payload.get('site_profile')
        inspect_payload = {
            'url': candidate_url,
            'source_version_id': source_version_id,
            'trigger': job.payload.get('trigger', 'manual'),
            'reason': job.payload.get('reason'),
            'inspection_mode': 'payload',
        }
        live_probe_context = None
        if self._needs_live_probe(raw_profile, evidence):
            live_probe_context = self._collect_live_probe_context(
                candidate_url=candidate_url,
                source_version_id=source_version_id,
                version_payload=version.payload,
                job_payload=job.payload,
            )
            if live_probe_context is not None:
                evidence = {
                    **live_probe_context.get('evidence', {}),
                    **evidence,
                }
                raw_profile = self._merge_profile_payload(
                    live_probe_context.get('profile'),
                    raw_profile,
                )
                inspect_payload |= live_probe_context.get('inspect_result', {})
        self._agent_runtime.record_tool_result(
            invocation_id=inspect_invocation.id,
            tenant_id=tenant_id,
            status='accepted',
            data=inspect_payload,
        )
        self._agent_runtime.record_tool_evidence(
            invocation_id=inspect_invocation.id,
            tenant_id=tenant_id,
            evidence_type='source_version',
            resource_id=source_version_id,
            payload={
                'url': candidate_url,
                **(
                    {'probe_summary': live_probe_context['probe_summary']}
                    if live_probe_context is not None and live_probe_context.get('probe_summary')
                    else {}
                ),
            },
        )

        profile = self._build_profile(candidate_url, raw_profile)
        live_validation = (
            live_probe_context.get('validation', {})
            if live_probe_context is not None
            else {}
        )
        fixture_validation_passed = self._validation_flag_from_payload(
            job.payload,
            'fixture_validation_passed',
            live_validation.get('fixture_validation_passed', False),
        )
        sample_validation_passed = self._validation_flag_from_payload(
            job.payload,
            'sample_validation_passed',
            live_validation.get('sample_validation_passed', False),
        )

        result = self._build_agent.attempt_repair(
            candidate_url=candidate_url,
            profile=profile,
            evidence=evidence,
            budget_remaining=int(job.payload.get('budget_remaining', 600) or 0),
            fixture_validation_passed=fixture_validation_passed,
            sample_validation_passed=sample_validation_passed,
            source_version_id=source_version_id,
            actor_id=tenant_id,
        )

        ai_task = None
        if result.strategy == 'llm_repair' and self._ai_repair is not None:
            source_rule = (
                live_probe_context.get('source_rule', {})
                if live_probe_context is not None else dict(version.payload.get('source_rule') or {})
            )
            validation = (
                live_probe_context.get('validation', {})
                if live_probe_context is not None else {}
            )
            executor = SourceBuildToolExecutor(SourceBuildToolContext(
                source_version_id=source_version_id,
                source_url=candidate_url,
                source_rule=source_rule,
                inspect_data=(live_probe_context.get('inspect_result', {}) if live_probe_context else {}),
                validate_patch=lambda _patch: validation,
                request_review=lambda arguments: {
                    'requested': True,
                    'source_version_id': source_version_id,
                    'reason': arguments.get('reason', 'ai_repair_failed'),
                },
            ))
            registry = AgentToolRegistry(source_build_handlers=executor.handlers())
            ai_task = self._run_async(self._ai_repair.repair(
                tenant_id=tenant_id,
                run_id=run.id,
                source_version_id=source_version_id,
                url=candidate_url,
                model=str(job.payload.get('model') or 'gpt-4.1-mini'),
                registry=registry,
            ))

        decision_tool_name = 'review.request' if result.review_required else 'rule.validate'
        decision_category = 'propose' if result.review_required else 'operate'
        decision_invocation = self._agent_runtime.record_tool_invocation(
            run_id=run.id,
            tenant_id=tenant_id,
            tool_name=decision_tool_name,
            category=decision_category,
            arguments={
                'decision': result.decision,
                'strategy': result.strategy,
                'source_version_id': source_version_id,
            },
        )
        decision_payload = {
            'decision': result.decision,
            'strategy': result.strategy,
            'review_required': result.review_required,
            'attempt_count': result.attempt_count,
            'review_item': result.review_item,
        }
        if live_probe_context is not None:
            decision_payload['validation'] = live_probe_context.get('validation')
            decision_payload['rule_patch'] = live_probe_context.get('rule_patch')
        self._agent_runtime.record_tool_result(
            invocation_id=decision_invocation.id,
            tenant_id=tenant_id,
            status='accepted',
            data=decision_payload,
        )
        if result.review_item and result.review_item.get('id'):
            self._agent_runtime.record_tool_evidence(
                invocation_id=decision_invocation.id,
                tenant_id=tenant_id,
                evidence_type='source_review_item',
                resource_id=str(result.review_item['id']),
                payload={'source_version_id': source_version_id},
            )

        updated_payload = dict(version.payload)
        updated_payload['autonomous_build'] = {
            'agent_run_id': run.id,
            'decision': result.decision,
            'strategy': result.strategy,
            'review_required': result.review_required,
            'attempt_count': result.attempt_count,
            'review_item_id': (
                str(result.review_item.get('id'))
                if result.review_item and result.review_item.get('id')
                else None
            ),
            'updated_at': _utcnow().isoformat(),
        }
        if ai_task is not None:
            updated_payload['autonomous_build']['ai_task_id'] = ai_task['id']
            updated_payload['autonomous_build']['ai'] = {
                'status': ai_task['status'],
                'provider': ai_task['provider'],
                'model': ai_task['model'],
                'result': ai_task['result'],
            }
        if job.payload.get('trigger'):
            updated_payload['autonomous_build']['trigger'] = job.payload['trigger']
        if job.payload.get('reason'):
            updated_payload['autonomous_build']['reason'] = job.payload['reason']
        if live_probe_context is not None and live_probe_context.get('probe_summary'):
            updated_payload['autonomous_build']['inspection_mode'] = 'live_probe'
            updated_payload['autonomous_build']['probe'] = live_probe_context['probe_summary']
            updated_payload['autonomous_build']['validation'] = live_probe_context.get('validation')
            updated_payload['source_rule'] = live_probe_context.get('source_rule')
            updated_payload['rule_patch'] = live_probe_context.get('rule_patch')
        self._runtime_repo.update_version_payload(source_version_id, updated_payload)

        return {
            'agent_run_id': run.id,
            'source_version_id': source_version_id,
            'decision': result.decision,
            'strategy': result.strategy,
            'review_required': result.review_required,
            'review_item': result.review_item,
            'ai_task_id': ai_task['id'] if ai_task is not None else None,
        }

    @staticmethod
    def _build_profile(candidate_url: str, raw_profile: dict | None) -> SiteProfile:
        profile = raw_profile or {}
        site_id = str(profile.get('site_id') or candidate_url)
        dom_signatures = {
            str(item)
            for item in profile.get('dom_signatures', [])
            if str(item).strip()
        }
        template_patch = profile.get('template_patch')
        fixture_coverage = float(profile.get('fixture_coverage', 0.0) or 0.0)
        confidence = float(profile.get('confidence', 0.0) or 0.0)
        risk_level = str(profile.get('risk_level') or 'medium')
        outcome_tags = tuple(str(tag) for tag in profile.get('outcome_tags', []) if str(tag).strip())
        return SiteProfile(
            site_id=site_id,
            dom_signatures=dom_signatures,
            template_patch=template_patch,
            fixture_coverage=fixture_coverage,
            confidence=confidence,
            risk_level=risk_level,
            outcome_tags=outcome_tags,
        )

    @classmethod
    def _has_value(cls, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    @classmethod
    def _seed_evidence(cls, version_payload: dict, job_payload: dict) -> dict:
        evidence: dict = {}
        version_evidence = version_payload.get('evidence')
        if isinstance(version_evidence, dict):
            evidence.update(version_evidence)
        job_evidence = job_payload.get('evidence')
        if isinstance(job_evidence, dict):
            evidence.update(job_evidence)
        return evidence

    @classmethod
    def _needs_live_probe(cls, raw_profile: dict | None, evidence: dict) -> bool:
        profile = raw_profile or {}
        profile_ready = any(
            cls._has_value(profile.get(key))
            for key in ('site_id', 'dom_signatures', 'template_patch')
        )
        evidence_ready = any(
            cls._has_value(evidence.get(key))
            for key in cls._ACTIONABLE_EVIDENCE_KEYS
        )
        return not (profile_ready and evidence_ready)

    @classmethod
    def _merge_profile_payload(cls, derived_profile: dict | None, explicit_profile: dict | None) -> dict:
        merged = dict(derived_profile or {})
        explicit = explicit_profile or {}
        for key, value in explicit.items():
            if key in {'dom_signatures', 'outcome_tags'}:
                existing = list(merged.get(key) or [])
                additions = [
                    str(item)
                    for item in value or []
                    if cls._has_value(item)
                ]
                merged[key] = list(dict.fromkeys([*existing, *additions]))
                continue
            if cls._has_value(value):
                merged[key] = value
        return merged

    @staticmethod
    def _validation_flag_from_payload(payload: dict, key: str, default: bool) -> bool:
        if key in payload:
            return bool(payload.get(key))
        return bool(default)

    def _collect_live_probe_context(
        self,
        *,
        candidate_url: str,
        source_version_id: str,
        version_payload: dict,
        job_payload: dict,
    ) -> dict | None:
        if self._probe_factory is None:
            return None

        source_name = self._resolve_source_name(candidate_url, version_payload, job_payload)
        generated_source = self._compatibility.generate_from_url(candidate_url, source_name=source_name)
        generated_source['id'] = source_version_id
        compatibility_site = self._compatibility.match_site(candidate_url)
        compatibility_score = self._compatibility.get_compatibility_score(generated_source)
        source_rule = self._sanitize_source_rule(generated_source)
        rule_patch = self._build_rule_patch(
            generated_source,
            compatibility_site=compatibility_site,
            compatibility_score=compatibility_score,
        )
        probe_service = self._probe_factory()
        probe_summary: dict
        try:
            probe = self._run_async(
                self._probe_candidate(
                    probe_service=probe_service,
                    source=generated_source,
                    keyword_samples=self._build_keyword_samples(
                        candidate_url=candidate_url,
                        source_name=source_name,
                        version_payload=version_payload,
                        job_payload=job_payload,
                    ),
                )
            )
            probe_summary = self._build_probe_summary(
                probe,
                compatibility_site=compatibility_site,
                compatibility_score=compatibility_score,
            )
        except Exception as exc:
            probe_summary = {
                'source_name': source_name,
                'source_url': candidate_url,
                'keyword': self._build_keyword_samples(
                    candidate_url=candidate_url,
                    source_name=source_name,
                    version_payload=version_payload,
                    job_payload=job_payload,
                )[0],
                'probe_mode': 'full_chain',
                'search_status': 'failed',
                'toc_status': 'skipped',
                'content_status': 'skipped',
                'failure_reason': str(exc),
                'compatibility': {
                    'matched_site': compatibility_site,
                    'score': compatibility_score.get('score'),
                    'grade': compatibility_score.get('grade'),
                    'is_usable': compatibility_score.get('is_usable'),
                },
            }
        validation = self._build_rule_validation(
            probe_summary,
            compatibility_score=compatibility_score,
            source_rule=source_rule,
        )

        request_summary = {
            'source_url': candidate_url,
            'search_request': probe_summary.get('search_request'),
            'probe_mode': probe_summary.get('probe_mode'),
            'keyword': probe_summary.get('keyword'),
        }
        response_summary = {
            'search': probe_summary.get('search'),
            'toc': probe_summary.get('toc'),
            'content': probe_summary.get('content'),
            'failure_reason': probe_summary.get('failure_reason'),
        }
        dom_signature = f"compat:{compatibility_site or urlparse(candidate_url).hostname or 'unknown'}"
        evidence = {
            'dom_signature': dom_signature,
            'request_summary': request_summary,
            'response_summary': response_summary,
            'sampled_content': self._build_sampled_content(probe_summary),
            'patch_candidate': rule_patch,
            'probe_summary': probe_summary,
        }
        profile = self._build_probe_profile(
            candidate_url=candidate_url,
            dom_signature=dom_signature,
            compatibility_site=compatibility_site,
            compatibility_score=compatibility_score,
            probe_summary=probe_summary,
            rule_patch=rule_patch,
        )
        return {
            'profile': profile,
            'evidence': evidence,
            'probe_summary': probe_summary,
            'source_rule': source_rule,
            'rule_patch': rule_patch,
            'validation': validation,
            'inspect_result': {
                'inspection_mode': 'live_probe',
                'probe_summary': probe_summary,
                'source_rule': source_rule,
                'rule_patch': rule_patch,
                'validation': validation,
                'request_summary': request_summary,
                'response_summary': response_summary,
            },
        }

    async def _probe_candidate(
        self,
        *,
        probe_service,
        source: dict,
        keyword_samples: list[str],
    ):
        try:
            return await probe_service.probe_source(
                source=source,
                keyword_samples=keyword_samples,
                probe_mode='full_chain',
            )
        finally:
            close = getattr(probe_service, 'aclose', None)
            if callable(close):
                await close()

    @staticmethod
    def _run_async(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)

    @classmethod
    def _resolve_source_name(cls, candidate_url: str, version_payload: dict, job_payload: dict) -> str:
        for value in (
            job_payload.get('catalog_source_name'),
            version_payload.get('catalog_source_name'),
            (version_payload.get('discovery') or {}).get('catalog_source_name')
            if isinstance(version_payload.get('discovery'), dict)
            else None,
            (version_payload.get('sample') or {}).get('title')
            if isinstance(version_payload.get('sample'), dict)
            else None,
        ):
            if cls._has_value(value):
                return str(value).strip()
        return urlparse(candidate_url).hostname or candidate_url

    @classmethod
    def _build_keyword_samples(
        cls,
        *,
        candidate_url: str,
        source_name: str,
        version_payload: dict,
        job_payload: dict,
    ) -> list[str]:
        samples: list[str] = []
        for value in (
            job_payload.get('keyword'),
            version_payload.get('keyword'),
            version_payload.get('sample')
            if isinstance(version_payload.get('sample'), str)
            else None,
        ):
            if cls._has_value(value):
                samples.append(str(value).strip())

        fallback = '小说' if ('.cn' in candidate_url.lower() or cls._contains_cjk(source_name)) else 'novel'
        samples.append(fallback)
        return list(dict.fromkeys(samples))

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return any('\u4e00' <= char <= '\u9fff' for char in value or '')

    @classmethod
    def _build_probe_profile(
        cls,
        *,
        candidate_url: str,
        dom_signature: str,
        compatibility_site: str | None,
        compatibility_score: dict,
        probe_summary: dict,
        rule_patch: dict,
    ) -> dict:
        stage_statuses = [
            str(probe_summary.get('search_status') or ''),
            str(probe_summary.get('toc_status') or ''),
            str(probe_summary.get('content_status') or ''),
        ]
        success_count = sum(status == 'ok' for status in stage_statuses)
        failure_count = sum(status == 'failed' for status in stage_statuses)

        if success_count >= 2 and failure_count == 0:
            risk_level = 'low'
        elif success_count == 0 and failure_count >= 1:
            risk_level = 'high'
        else:
            risk_level = 'medium'

        base_confidence = float(compatibility_score.get('score', 0) or 0) / 100.0
        confidence = max(base_confidence, 0.35 if success_count == 0 else 0.65)
        if success_count >= 2:
            confidence = max(confidence, 0.8)

        fixture_coverage = success_count / 3.0

        return {
            'site_id': compatibility_site or (urlparse(candidate_url).hostname or candidate_url),
            'dom_signatures': [dom_signature],
            'template_patch': rule_patch,
            'fixture_coverage': fixture_coverage,
            'confidence': min(confidence, 0.95),
            'risk_level': risk_level,
            'outcome_tags': [
                f"probe:search_{probe_summary.get('search_status', 'unknown')}",
                f"probe:toc_{probe_summary.get('toc_status', 'unknown')}",
                f"probe:content_{probe_summary.get('content_status', 'unknown')}",
                'probe:live',
            ],
        }

    @staticmethod
    def _sanitize_source_rule(source: dict) -> dict:
        blocked_keys = {'_fixes'}
        rule = {
            key: value
            for key, value in source.items()
            if not key.startswith('_') and key not in blocked_keys
        }
        if 'id' in rule:
            rule['sourceVersionId'] = str(rule.pop('id'))
        return rule

    @staticmethod
    def _build_rule_patch(
        source: dict,
        *,
        compatibility_site: str | None,
        compatibility_score: dict,
    ) -> dict:
        operation = 'apply_site_template' if compatibility_site else 'apply_fallback_rules'
        operations = []
        for field in ('ruleSearch', 'ruleBookInfo', 'ruleToc', 'ruleContent'):
            value = source.get(field)
            if value:
                operations.append(
                    {
                        'op': operation if not operations else 'set_rule',
                        'field': field,
                        'value': value,
                    }
                )
        if source.get('searchUrl'):
            operations.append(
                {
                    'op': 'set_search_url',
                    'field': 'searchUrl',
                    'value': source['searchUrl'],
                }
            )

        return {
            'source': 'compatibility.generate_from_url',
            'matched_site': compatibility_site,
            'compatibility_score': compatibility_score.get('score'),
            'compatibility_grade': compatibility_score.get('grade'),
            'operations': operations,
        }

    @staticmethod
    def _build_rule_validation(
        probe_summary: dict,
        *,
        compatibility_score: dict,
        source_rule: dict,
    ) -> dict:
        search = SourceBuildRuntimeService._stage_validation(
            probe_summary,
            'search',
            requires_hits=True,
        )
        toc = SourceBuildRuntimeService._stage_validation(
            probe_summary,
            'toc',
            requires_hits=True,
        )
        content = SourceBuildRuntimeService._stage_validation(
            probe_summary,
            'content',
            requires_content=True,
        )
        required_fields = [
            'bookSourceUrl',
            'bookSourceName',
            'ruleSearch',
            'ruleToc',
            'ruleContent',
            'searchUrl',
        ]
        missing_fields = [
            field for field in required_fields
            if source_rule.get(field) in (None, '', {}, [])
        ]
        source_shape_passed = not missing_fields
        stage_pass_count = sum(1 for stage in (search, toc, content) if stage['passed'])
        quality_score = int(
            (float(compatibility_score.get('score', 0) or 0) * 0.4)
            + ((stage_pass_count / 3.0) * 60)
        )
        fixture_validation_passed = source_shape_passed and search['passed'] and toc['passed']
        sample_validation_passed = content['passed']
        return {
            'source_shape': {
                'passed': source_shape_passed,
                'missing_fields': missing_fields,
            },
            'search': search,
            'toc': toc,
            'content': content,
            'fixture_validation_passed': fixture_validation_passed,
            'sample_validation_passed': sample_validation_passed,
            'quality_score': quality_score,
            'grade': 'A' if quality_score >= 90 else 'B' if quality_score >= 75 else 'C' if quality_score >= 60 else 'D',
        }

    @staticmethod
    def _stage_validation(
        probe_summary: dict,
        stage_name: str,
        *,
        requires_hits: bool = False,
        requires_content: bool = False,
    ) -> dict:
        stage = probe_summary.get(stage_name)
        status = probe_summary.get(f'{stage_name}_status')
        if not isinstance(stage, dict):
            stage = {}
        hit_count = int(stage.get('hit_count') or 0)
        content_length = int(probe_summary.get('content_length') or 0)
        passed = status == 'ok'
        if requires_hits:
            passed = passed and hit_count > 0
        if requires_content:
            passed = passed and content_length > 0
        return {
            'passed': passed,
            'status': status,
            'hit_count': hit_count,
            'content_length': content_length if stage_name == 'content' else None,
            'elapsed_ms': stage.get('elapsed_ms'),
            'error_message': stage.get('error_message') or probe_summary.get('failure_reason') or '',
        }

    @staticmethod
    def _build_probe_summary(probe, *, compatibility_site: str | None, compatibility_score: dict) -> dict:
        search = SourceBuildRuntimeService._stage_summary(probe.search)
        toc = SourceBuildRuntimeService._stage_summary(probe.toc)
        content = SourceBuildRuntimeService._stage_summary(probe.content)
        failure_reason = SourceBuildRuntimeService._first_non_empty(
            probe.content.error_message,
            probe.content.detail.get('http_error') if isinstance(probe.content.detail, dict) else None,
            probe.toc.error_message,
            probe.toc.detail.get('http_error') if isinstance(probe.toc.detail, dict) else None,
            probe.search.error_message,
            probe.search.detail.get('http_error') if isinstance(probe.search.detail, dict) else None,
        )
        top_hit = probe.search.detail.get('top_hit') if isinstance(probe.search.detail, dict) else None
        first_chapter = probe.toc.detail.get('first_chapter') if isinstance(probe.toc.detail, dict) else None
        content_length = 0
        if isinstance(probe.content.detail, dict):
            content_length = int(probe.content.detail.get('content_length') or 0)
        sample_title = SourceBuildRuntimeService._first_non_empty(
            probe.content.sample_title,
            probe.toc.sample_title,
            probe.search.sample_title,
        )
        return {
            'source_name': probe.source_name,
            'source_url': probe.source_url,
            'keyword': probe.keyword,
            'probe_mode': probe.probe_mode,
            'search_status': probe.search.status,
            'toc_status': probe.toc.status,
            'content_status': probe.content.status,
            'search_request': probe.search.request_preview or '',
            'sample_title': sample_title,
            'content_length': content_length,
            'top_hit': top_hit,
            'first_chapter': first_chapter,
            'failure_reason': failure_reason,
            'compatibility': {
                'matched_site': compatibility_site,
                'score': compatibility_score.get('score'),
                'grade': compatibility_score.get('grade'),
                'is_usable': compatibility_score.get('is_usable'),
            },
            'search': search,
            'toc': toc,
            'content': content,
        }

    @staticmethod
    def _stage_summary(stage) -> dict:
        detail = dict(stage.detail or {})
        return {
            'status': stage.status,
            'elapsed_ms': stage.elapsed_ms,
            'hit_count': stage.hit_count,
            'sample_title': stage.sample_title or None,
            'request_preview': stage.request_preview or None,
            'error_message': stage.error_message or None,
            'http_status': detail.get('http_status'),
            'http_error': detail.get('http_error'),
            'response_kind': detail.get('response_kind'),
            'response_preview': detail.get('response_preview'),
            'parse_status': detail.get('parse_status'),
        }

    @staticmethod
    def _build_sampled_content(probe_summary: dict) -> str:
        for key in ('content', 'toc', 'search'):
            stage = probe_summary.get(key)
            if not isinstance(stage, dict):
                continue
            preview = stage.get('response_preview')
            if isinstance(preview, str) and preview.strip():
                return preview.strip()[:500]

        top_hit = probe_summary.get('top_hit')
        if isinstance(top_hit, dict) and top_hit:
            return json.dumps(top_hit, ensure_ascii=False)[:500]

        first_chapter = probe_summary.get('first_chapter')
        if isinstance(first_chapter, dict) and first_chapter:
            return json.dumps(first_chapter, ensure_ascii=False)[:500]

        sample_title = str(probe_summary.get('sample_title') or '').strip()
        content_length = int(probe_summary.get('content_length') or 0)
        if sample_title and content_length > 0:
            return f'{sample_title} (content_length={content_length})'
        if sample_title:
            return sample_title
        return str(probe_summary.get('failure_reason') or '').strip()

    @staticmethod
    def _first_non_empty(*values) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ''

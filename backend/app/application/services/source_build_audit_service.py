from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy


class SourceAuditRecoveryError(RuntimeError):
    pass


class SourceBuildAuditService:
    MAX_ATTEMPTS = 5
    MAX_STAGE_ELAPSED_MS = 10_000
    MAX_TOTAL_ELAPSED_MS = 25_000

    def __init__(self, *, runtime_repo, probe_service_factory, build_service, review_service):
        self._runtime = runtime_repo
        self._probe_service_factory = probe_service_factory
        self._build_service = build_service
        self._review_service = review_service

    async def audit(self, source_version_id: str) -> dict:
        version = self._runtime.get_version(source_version_id)
        if version is None:
            return {'status': 'missing'}
        if version.status != 'candidate':
            return {
                'source_version_id': version.id,
                'status': 'skipped',
                'reason': 'not_candidate',
            }

        payload = deepcopy(version.payload)
        existing_audit = dict(payload.get('source_audit') or {})
        if existing_audit.get('status') == 'retry_pending':
            return self._recover_retry_pending(version, payload, existing_audit)
        if existing_audit.get('status') == 'terminal_review_pending':
            return self._recover_terminal_review_pending(version, payload, existing_audit)
        raw_source_rule = payload.get('source_rule')
        source_rule = dict(raw_source_rule) if isinstance(raw_source_rule, dict) else {}
        keyword = str(payload.get('keyword') or 'sample')
        if source_rule:
            source_rule.setdefault('id', version.source_definition_id)
            probe = None
            try:
                probe = self._probe_service_factory()
                evidence = await asyncio.wait_for(
                    probe.probe_source(
                        source_rule,
                        keyword_samples=[keyword],
                        probe_mode='full_chain',
                    ),
                    timeout=self.MAX_TOTAL_ELAPSED_MS / 1000,
                )
            except asyncio.TimeoutError:
                report, passed, diagnostics, step_passes = self._probe_timeout_evaluation()
            except Exception:
                report, passed, diagnostics, step_passes = self._probe_error_evaluation()
            else:
                report, passed, diagnostics, step_passes = self._evaluate(evidence)
            finally:
                close = getattr(probe, 'aclose', None) if probe is not None else None
                if callable(close):
                    try:
                        result = close()
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        pass
        else:
            report, passed, diagnostics, step_passes = self._missing_rule_evaluation()
        audit = dict(payload.get('source_audit') or {})
        attempt = int(audit.get('attempt', 0) or 0) + 1
        score = 100 if passed else 0
        grade = 'A' if passed else 'F'
        report.update({
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'score': score,
            'grade': grade,
        })
        audit_status = 'passed' if passed else 'failed'
        queued_repair = None
        recovery_error = None
        if not passed and attempt < self.MAX_ATTEMPTS:
            try:
                queued_repair = self._submit_repair(
                    version=version,
                    payload=payload,
                    source_rule=source_rule,
                    keyword=keyword,
                    next_attempt=attempt + 1,
                )
                audit_status = 'retry_queued'
            except Exception as error:
                audit_status = 'retry_pending'
                report['recovery_state'] = 'retry_pending'
                recovery_error = error
        elif not passed:
            audit_status = 'terminal_review_pending'
            report['recovery_state'] = 'terminal_review_pending'
        audit.update({
            'status': audit_status,
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'report': report,
            'history': list(audit.get('history') or [])[-4:] + [report],
        })
        if not passed and attempt < self.MAX_ATTEMPTS:
            audit['repair_next_attempt'] = attempt + 1
            repair_job_id = self._job_id(queued_repair)
            if repair_job_id:
                audit['repair_job_id'] = repair_job_id
        payload['source_audit'] = audit
        self._runtime.update_version_payload(version.id, payload)
        if recovery_error is not None:
            self._record_test_run(version, score, grade, report, step_passes, diagnostics)
            raise SourceAuditRecoveryError('source audit repair enqueue requires recovery') from recovery_error
        if not passed and attempt >= self.MAX_ATTEMPTS:
            terminal_report = {**report, 'recovery_state': 'failed'}
            try:
                review_item = self._review_service.enqueue_audit_failure(
                    source_version_id=version.id,
                    source_url=str(payload.get('canonical_url') or source_rule.get('bookSourceUrl') or version.source_id),
                    audit_report=terminal_report,
                    created_by='system',
                )
            except Exception as error:
                self._record_test_run(version, score, grade, report, step_passes, diagnostics)
                raise SourceAuditRecoveryError('source audit terminal review requires recovery') from error
            audit['status'] = 'failed'
            report = terminal_report
            review_item_id = self._job_id(review_item)
            if review_item_id:
                audit['review_item_id'] = review_item_id
            audit['report'] = report
            payload['source_audit'] = audit
            self._runtime.update_version_payload(version.id, payload)
            self._runtime.update_version_status(version.id, 'failed')
        self._record_test_run(version, score, grade, report, step_passes, diagnostics)
        return {
            'source_version_id': version.id,
            'status': audit['status'],
            'score': score,
            'grade': grade,
            'report': report,
        }

    def _recover_retry_pending(self, version, payload: dict, audit: dict) -> dict:
        report = dict(audit.get('report') or {})
        source_rule = payload.get('source_rule')
        source_rule = dict(source_rule) if isinstance(source_rule, dict) else {}
        keyword = str(payload.get('keyword') or 'sample')
        next_attempt = int(audit.get('repair_next_attempt') or int(audit.get('attempt', 0) or 0) + 1)
        try:
            queued_repair = self._submit_repair(
                version=version,
                payload=payload,
                source_rule=source_rule,
                keyword=keyword,
                next_attempt=next_attempt,
            )
        except Exception as error:
            self._runtime.update_version_payload(version.id, payload)
            raise SourceAuditRecoveryError('source audit repair enqueue requires recovery') from error

        audit['status'] = 'retry_queued'
        report['recovery_state'] = 'retry_queued'
        audit['report'] = report
        repair_job_id = self._job_id(queued_repair)
        if repair_job_id:
            audit['repair_job_id'] = repair_job_id
        payload['source_audit'] = audit
        self._runtime.update_version_payload(version.id, payload)
        return {
            'source_version_id': version.id,
            'status': 'retry_queued',
            'score': int(report.get('score', 0) or 0),
            'grade': str(report.get('grade') or 'F'),
            'report': report,
        }

    def _recover_terminal_review_pending(self, version, payload: dict, audit: dict) -> dict:
        report = dict(audit.get('report') or {})
        source_rule = payload.get('source_rule')
        source_rule = dict(source_rule) if isinstance(source_rule, dict) else {}
        terminal_report = {**report, 'recovery_state': 'failed'}
        try:
            review_item = self._review_service.enqueue_audit_failure(
                source_version_id=version.id,
                source_url=str(payload.get('canonical_url') or source_rule.get('bookSourceUrl') or version.source_id),
                audit_report=terminal_report,
                created_by='system',
            )
        except Exception as error:
            self._runtime.update_version_payload(version.id, payload)
            raise SourceAuditRecoveryError('source audit terminal review requires recovery') from error

        audit['status'] = 'failed'
        report = terminal_report
        audit['report'] = report
        review_item_id = self._job_id(review_item)
        if review_item_id:
            audit['review_item_id'] = review_item_id
        payload['source_audit'] = audit
        self._runtime.update_version_payload(version.id, payload)
        self._runtime.update_version_status(version.id, 'failed')
        return {
            'source_version_id': version.id,
            'status': 'failed',
            'score': int(report.get('score', 0) or 0),
            'grade': str(report.get('grade') or 'F'),
            'report': report,
        }

    def _submit_repair(self, *, version, payload: dict, source_rule: dict, keyword: str, next_attempt: int):
        return self._build_service.submit_audit_repair(
            tenant_id=version.created_by or 'system',
            source_version_id=version.id,
            url=str(payload.get('canonical_url') or source_rule.get('bookSourceUrl') or version.source_id),
            keyword=keyword,
            next_attempt=next_attempt,
        )

    @staticmethod
    def _job_id(job) -> str:
        return str(getattr(job, 'id', '') or '')

    def _record_test_run(self, version, score: int, grade: str, report: dict, step_passes: dict, diagnostics: list[str]):
        self._runtime.record_test_run(
            source_version_id=version.id,
            trigger='source_audit',
            score=score,
            grade=grade,
            step_results={
                name: {
                    'passed': step_passes[name],
                    'status': stage['status'],
                    'elapsed_ms': stage['elapsed_ms'],
                }
                for name, stage in report['stages'].items()
            },
            diagnostics=diagnostics,
        )

    def _evaluate(self, evidence):
        search = evidence.search
        toc = evidence.toc
        content = evidence.content
        stages = {
            'search': {
                'status': search.status,
                'elapsed_ms': search.elapsed_ms,
                'hit_count': search.hit_count,
                'title': search.sample_title,
            },
            'toc': {
                'status': toc.status,
                'elapsed_ms': toc.elapsed_ms,
                'hit_count': toc.hit_count,
                'title': toc.sample_title,
            },
            'content': {
                'status': content.status,
                'elapsed_ms': content.elapsed_ms,
                'content_length': int(content.detail.get('content_length', 0) or 0),
                'title': content.sample_title,
            },
        }
        total_elapsed_ms = sum(stage['elapsed_ms'] for stage in stages.values())
        step_passes = {
            'search': search.status == 'ok' and search.hit_count > 0 and bool(search.sample_title),
            'toc': toc.status == 'ok' and toc.hit_count > 0 and bool(toc.sample_title),
            'content': content.status == 'ok' and stages['content']['content_length'] >= 80,
        }
        stage_within_budget = all(
            stage['elapsed_ms'] <= self.MAX_STAGE_ELAPSED_MS for stage in stages.values()
        )
        passed = all(step_passes.values()) and stage_within_budget and total_elapsed_ms <= self.MAX_TOTAL_ELAPSED_MS
        reason = ''
        if not step_passes['search']:
            reason = 'search_failed'
        elif not step_passes['toc']:
            reason = 'toc_failed'
        elif content.status == 'ok' and stages['content']['content_length'] < 80:
            reason = 'content_too_short'
        elif not step_passes['content']:
            reason = 'content_failed'
        elif not stage_within_budget:
            reason = 'stage_timeout'
        elif total_elapsed_ms > self.MAX_TOTAL_ELAPSED_MS:
            reason = 'total_timeout'
        diagnostics = [] if passed else [reason]
        report = {
            'status': 'passed' if passed else 'failed',
            'total_elapsed_ms': total_elapsed_ms,
            'stages': stages,
        }
        if reason:
            report['reason'] = reason
        return report, passed, diagnostics, step_passes

    @staticmethod
    def _missing_rule_evaluation():
        stages = {
            'search': {'status': 'skipped', 'elapsed_ms': 0, 'hit_count': 0, 'title': ''},
            'toc': {'status': 'skipped', 'elapsed_ms': 0, 'hit_count': 0, 'title': ''},
            'content': {'status': 'skipped', 'elapsed_ms': 0, 'content_length': 0, 'title': ''},
        }
        return (
            {
                'status': 'failed',
                'reason': 'missing_source_rule',
                'total_elapsed_ms': 0,
                'stages': stages,
            },
            False,
            ['missing_source_rule'],
            {'search': False, 'toc': False, 'content': False},
        )

    @staticmethod
    def _probe_error_evaluation():
        stages = {
            'search': {'status': 'failed', 'elapsed_ms': 0, 'hit_count': 0, 'title': ''},
            'toc': {'status': 'skipped', 'elapsed_ms': 0, 'hit_count': 0, 'title': ''},
            'content': {'status': 'skipped', 'elapsed_ms': 0, 'content_length': 0, 'title': ''},
        }
        return (
            {
                'status': 'failed',
                'reason': 'probe_error',
                'total_elapsed_ms': 0,
                'stages': stages,
            },
            False,
            ['probe_error'],
            {'search': False, 'toc': False, 'content': False},
        )

    def _probe_timeout_evaluation(self):
        stages = {
            'search': {'status': 'failed', 'elapsed_ms': self.MAX_TOTAL_ELAPSED_MS, 'hit_count': 0, 'title': ''},
            'toc': {'status': 'skipped', 'elapsed_ms': 0, 'hit_count': 0, 'title': ''},
            'content': {'status': 'skipped', 'elapsed_ms': 0, 'content_length': 0, 'title': ''},
        }
        return (
            {
                'status': 'failed',
                'reason': 'probe_timeout',
                'total_elapsed_ms': self.MAX_TOTAL_ELAPSED_MS,
                'stages': stages,
            },
            False,
            ['probe_timeout'],
            {'search': False, 'toc': False, 'content': False},
        )

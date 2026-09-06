from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy


class SourceAuditRecoveryError(RuntimeError):
    pass


class ManualBrowserValidationAcceptanceError(ValueError):
    pass


class ManualBrowserValidationRecoveryPending(RuntimeError):
    """The manual validation checkpoint is durable, but its final run needs recovery."""

    def __init__(self, audit_result: dict):
        super().__init__('manual_browser_validation_recovery_pending')
        self.audit_result = deepcopy(audit_result)


class SourceBuildAuditService:
    MAX_ATTEMPTS = 5

    @staticmethod
    def _review_gate_passed(*, audit: dict, autonomous_build: dict | None) -> bool:
        if not isinstance(audit, dict) or audit.get('workflow') != 'unified':
            return False
        agent_review = autonomous_build.get('ai') if isinstance(autonomous_build, dict) else None
        if isinstance(agent_review, dict) and agent_review.get('status') == 'succeeded':
            return True
        agent = autonomous_build.get('agent') if isinstance(autonomous_build, dict) else None
        return isinstance(agent, dict) and agent.get('reason') == 'deterministic_success'
    MAX_STAGE_ELAPSED_MS = 10_000
    MAX_TOTAL_ELAPSED_MS = 25_000
    MIN_CLOSE_TIMEOUT_SECONDS = 0.001

    def __init__(
        self,
        *,
        runtime_repo,
        probe_service_factory,
        build_service,
        review_service,
        interactive_browser_service=None,
    ):
        self._runtime = runtime_repo
        self._probe_service_factory = probe_service_factory
        self._build_service = build_service
        self._review_service = review_service
        self._interactive_browser = interactive_browser_service

    async def audit(
        self,
        source_version_id: str,
        completed_repair_attempt: int | None = None,
    ) -> dict:
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
        if existing_audit.get('test_run_pending'):
            pending_result = self._recover_pending_test_run(
                version,
                payload,
                existing_audit,
                completed_repair_attempt=completed_repair_attempt,
            )
            if pending_result is not None:
                return pending_result
            existing_audit = dict(payload.get('source_audit') or {})
        if existing_audit.get('status') == 'retry_pending':
            pending_attempt = int(existing_audit.get('repair_next_attempt', 0) or 0)
            if completed_repair_attempt != pending_attempt:
                return self._recover_retry_pending(version, payload, existing_audit)
        if existing_audit.get('status') == 'terminal_review_pending':
            return self._recover_terminal_review_pending(version, payload, existing_audit)
        if existing_audit.get('status') == 'terminal_finalizing':
            return self._recover_terminal_finalizing(version, payload, existing_audit)
        if existing_audit.get('status') == 'failed' and existing_audit.get('finalization_pending'):
            return self._finish_terminal_status(version, existing_audit)
        raw_source_rule = payload.get('source_rule')
        source_rule = dict(raw_source_rule) if isinstance(raw_source_rule, dict) else {}
        keyword = str(payload.get('keyword') or 'sample')
        if source_rule:
            source_rule.setdefault('id', version.source_definition_id)
            probe = None
            close_timed_out = False
            deadline = time.monotonic() + (self.MAX_TOTAL_ELAPSED_MS / 1000)
            set_execution_deadline = None
            try:
                probe = self._probe_service_factory()
                set_execution_deadline = getattr(probe, 'set_execution_deadline', None)
                if callable(set_execution_deadline):
                    set_execution_deadline(deadline)
                evidence = await asyncio.wait_for(
                    probe.probe_source(
                        source_rule,
                        keyword_samples=[keyword],
                        probe_mode='full_chain',
                    ),
                    timeout=self._remaining_seconds(deadline),
                )
            except asyncio.TimeoutError:
                report, passed, diagnostics, step_passes = self._probe_timeout_evaluation()
            except Exception:
                report, passed, diagnostics, step_passes = self._probe_error_evaluation()
            else:
                report, passed, diagnostics, step_passes = self._evaluate(evidence)
            finally:
                if callable(set_execution_deadline):
                    try:
                        set_execution_deadline(None)
                    except Exception:
                        pass
                close = None
                if probe is not None:
                    close = getattr(probe, 'aclose', None) or getattr(probe, 'close', None)
                if callable(close):
                    try:
                        result = close()
                        if inspect.isawaitable(result):
                            await asyncio.wait_for(
                                result,
                                timeout=max(
                                    self._remaining_seconds(deadline),
                                    self.MIN_CLOSE_TIMEOUT_SECONDS,
                                ),
                            )
                    except asyncio.TimeoutError:
                        close_timed_out = True
                    except Exception:
                        pass
            if close_timed_out:
                report, passed, diagnostics, step_passes = self._probe_timeout_evaluation()
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
        if report.get('reason') == 'verification_required':
            browser_session_id = None
            browser_result = None
            if self._interactive_browser is not None:
                browser_result = await self._interactive_browser.attempt_automatic(
                    source_version_id=version.id,
                    owner_id=version.created_by or 'system',
                    source_rule=source_rule,
                    keyword=keyword,
                )
                browser_session_id = browser_result.session_id
            browser_validation = getattr(browser_result, 'validation', None)
            if getattr(browser_result, 'state', '') == 'validated' and browser_validation is not None and browser_validation.passed:
                report = self._browser_validation_report(browser_validation.stages or {})
                passed = True
                diagnostics = []
                step_passes = {'search': True, 'toc': True, 'content': True}
                score = 100
                grade = 'A'
                report.update({
                    'attempt': attempt,
                    'max_attempts': self.MAX_ATTEMPTS,
                    'score': score,
                    'grade': grade,
                })
                audit.update({
                    'status': 'passed',
                    'attempt': attempt,
                    'max_attempts': self.MAX_ATTEMPTS,
                    'report': report,
                    'history': list(audit.get('history') or [])[-4:] + [report],
                })
                if browser_session_id:
                    audit['browser_session_id'] = browser_session_id
                payload['source_audit'] = audit
                return self._persist_outcome_with_test_run(
                    version=version,
                    payload=payload,
                    audit=audit,
                    report=report,
                    score=score,
                    grade=grade,
                    step_passes=step_passes,
                    diagnostics=diagnostics,
                )
            audit.update({
                'status': 'awaiting_manual_verification',
                'attempt': attempt,
                'max_attempts': self.MAX_ATTEMPTS,
                'report': report,
                'history': list(audit.get('history') or [])[-4:] + [report],
            })
            if browser_session_id:
                audit['browser_session_id'] = browser_session_id
            payload['source_audit'] = audit
            return self._persist_outcome_with_test_run(
                version=version,
                payload=payload,
                audit=audit,
                report=report,
                score=score,
                grade=grade,
                step_passes=step_passes,
                diagnostics=diagnostics,
            )
        if not passed and attempt < self.MAX_ATTEMPTS:
            return self._queue_repair_after_pending(
                version=version,
                payload=payload,
                audit=audit,
                report=report,
                score=score,
                grade=grade,
                step_passes=step_passes,
                diagnostics=diagnostics,
                source_rule=source_rule,
                keyword=keyword,
                attempt=attempt,
            )
        autonomous_build = payload.get('autonomous_build') if isinstance(payload, dict) else None
        agent_review = autonomous_build.get('ai') if isinstance(autonomous_build, dict) else None
        unified_review_ready = self._review_gate_passed(
            audit=existing_audit,
            autonomous_build=autonomous_build,
        )
        audit_status = 'approved_for_publish' if passed and unified_review_ready else ('passed' if passed else 'failed')
        if passed and not unified_review_ready and existing_audit.get('workflow') == 'unified':
            audit_status = 'manual_review_required'
            report['reason_code'] = 'review_agent_unavailable_or_incomplete'
        if not passed:
            audit_status = 'terminal_review_pending'
            report['recovery_state'] = 'terminal_review_pending'
        audit.update({
            'status': audit_status,
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'report': report,
            'history': list(audit.get('history') or [])[-4:] + [report],
        })
        payload['source_audit'] = audit
        if not passed and attempt >= self.MAX_ATTEMPTS:
            try:
                self._runtime.update_version_payload(version.id, payload)
            except Exception as error:
                raise SourceAuditRecoveryError('source audit terminal checkpoint requires recovery') from error
            return self._begin_terminal_finalization(
                version=version,
                payload=payload,
                audit=audit,
                report=report,
                score=score,
                grade=grade,
                step_passes=step_passes,
                diagnostics=diagnostics,
                source_rule=source_rule,
            )
        return self._persist_outcome_with_test_run(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=score,
            grade=grade,
            step_passes=step_passes,
            diagnostics=diagnostics,
        )

    def audit_blocking(
        self,
        source_version_id: str,
        *,
        completed_repair_attempt: int | None = None,
    ) -> dict:
        coroutine = self.audit(
            source_version_id,
            completed_repair_attempt=completed_repair_attempt,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coroutine).result()

    def accept_manual_browser_validation(
        self,
        source_version_id: str,
        *,
        browser_session_id: str,
        validation,
    ) -> dict:
        """Accept a completed manual browser full-chain validation without re-probing."""
        version = self._runtime.get_version(source_version_id)
        if version is None:
            raise ManualBrowserValidationAcceptanceError('source_version_missing')
        if version.status != 'candidate':
            raise ManualBrowserValidationAcceptanceError('source_version_not_candidate')
        if not bool(getattr(validation, 'passed', False)):
            raise ManualBrowserValidationAcceptanceError('browser_validation_not_passed')

        payload = deepcopy(version.payload)
        original_payload = deepcopy(payload)
        audit = dict(payload.get('source_audit') or {})
        if audit.get('status') != 'awaiting_manual_verification':
            raise ManualBrowserValidationAcceptanceError('source_audit_not_awaiting_manual_verification')
        if str(audit.get('browser_session_id') or '') != browser_session_id:
            raise ManualBrowserValidationAcceptanceError('browser_session_mismatch')

        attempt = int(audit.get('attempt', 0) or 0)
        report = self._browser_validation_report(getattr(validation, 'stages', None) or {})
        report.update({
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'score': 100,
            'grade': 'A',
        })
        audit.update({
            'status': 'passed',
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'report': report,
            'history': list(audit.get('history') or [])[-4:] + [report],
        })
        payload['source_audit'] = audit
        try:
            return self._persist_outcome_with_test_run(
                version=version,
                payload=payload,
                audit=audit,
                report=report,
                score=100,
                grade='A',
                step_passes={'search': True, 'toc': True, 'content': True},
                diagnostics=[],
                test_run_kind='manual_browser',
            )
        except Exception:
            persisted_version = self._runtime.get_version(version.id)
            persisted_payload = getattr(persisted_version, 'payload', {}) if persisted_version is not None else {}
            persisted_audit = dict(persisted_payload.get('source_audit') or {}) if isinstance(persisted_payload, dict) else {}
            persisted_checkpoint = (
                persisted_audit.get('status') == 'passed'
                and persisted_audit.get('test_run_pending') is True
                and str(persisted_audit.get('browser_session_id') or '') == browser_session_id
            )
            try:
                self._runtime.update_version_payload(version.id, original_payload)
            except Exception as rollback_error:
                if persisted_checkpoint:
                    audit_result = self._audit_result(persisted_version, persisted_audit)
                    audit_result['recovery_pending'] = True
                    raise ManualBrowserValidationRecoveryPending(audit_result) from rollback_error
                raise SourceAuditRecoveryError('source audit manual acceptance rollback requires recovery') from rollback_error
            raise

    def _queue_repair_after_pending(
        self,
        *,
        version,
        payload: dict,
        audit: dict,
        report: dict,
        score: int,
        grade: str,
        step_passes: dict,
        diagnostics: list[str],
        source_rule: dict,
        keyword: str,
        attempt: int,
    ) -> dict:
        next_attempt = attempt + 1
        report['recovery_state'] = 'retry_pending'
        audit.update({
            'status': 'retry_pending',
            'attempt': attempt,
            'max_attempts': self.MAX_ATTEMPTS,
            'report': report,
            'history': list(audit.get('history') or [])[-4:] + [report],
            'repair_next_attempt': next_attempt,
            'test_run_pending': True,
            'test_run_attempt': attempt,
            'test_run_status': 'retry_pending',
        })
        payload['source_audit'] = audit
        try:
            self._runtime.update_version_payload(version.id, payload)
        except Exception as error:
            raise SourceAuditRecoveryError('source audit repair checkpoint requires recovery') from error

        try:
            queued_repair = self._submit_repair(
                version=version,
                payload=payload,
                source_rule=source_rule,
                keyword=keyword,
                next_attempt=next_attempt,
            )
        except Exception as error:
            try:
                self._settle_pending_test_run(
                    version=version,
                    payload=payload,
                    audit=audit,
                    report=report,
                    score=score,
                    grade=grade,
                    step_passes=step_passes,
                    diagnostics=diagnostics,
                )
            except Exception as record_error:
                raise SourceAuditRecoveryError('source audit test run requires recovery') from record_error
            raise SourceAuditRecoveryError('source audit repair enqueue requires recovery') from error

        audit['status'] = 'retry_queued'
        report['recovery_state'] = 'retry_queued'
        audit['report'] = report
        repair_job_id = self._job_id(queued_repair)
        if repair_job_id:
            audit['repair_job_id'] = repair_job_id
        payload['source_audit'] = audit
        return self._persist_outcome_with_test_run(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=score,
            grade=grade,
            step_passes=step_passes,
            diagnostics=diagnostics,
        )

    def _persist_outcome_with_test_run(
        self,
        *,
        version,
        payload: dict,
        audit: dict,
        report: dict,
        score: int,
        grade: str,
        step_passes: dict,
        diagnostics: list[str],
        test_run_kind: str = 'normal',
    ) -> dict:
        stable_status = str(audit.get('status') or 'failed')
        audit['test_run_pending'] = True
        audit['test_run_attempt'] = int(report.get('attempt', 0) or 0)
        audit['test_run_status'] = stable_status
        audit['test_run_kind'] = test_run_kind
        audit['report'] = report
        payload['source_audit'] = audit
        try:
            self._runtime.update_version_payload(version.id, payload)
        except Exception as error:
            raise SourceAuditRecoveryError('source audit test run checkpoint requires recovery') from error

        self._settle_pending_test_run(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=score,
            grade=grade,
            step_passes=step_passes,
            diagnostics=diagnostics,
        )
        return self._audit_result(version, audit)

    def _recover_pending_test_run(
        self,
        version,
        payload: dict,
        audit: dict,
        *,
        completed_repair_attempt: int | None = None,
    ) -> dict | None:
        report = dict(audit.get('report') or {})
        stable_status = str(audit.get('test_run_status') or audit.get('status') or 'failed')
        self._settle_pending_test_run(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=int(report.get('score', 0) or 0),
            grade=str(report.get('grade') or 'F'),
            step_passes=self._step_passes_from_report(report),
            diagnostics=[str(report.get('reason'))] if report.get('reason') else [],
        )
        audit['status'] = stable_status
        if stable_status in {'retry_pending', 'retry_queued'}:
            pending_attempt = int(audit.get('repair_next_attempt', 0) or 0)
            if completed_repair_attempt == pending_attempt:
                return None
        if stable_status == 'retry_pending':
            return self._recover_retry_pending(version, payload, audit)
        return self._audit_result(version, audit)

    def _settle_pending_test_run(
        self,
        *,
        version,
        payload: dict,
        audit: dict,
        report: dict,
        score: int,
        grade: str,
        step_passes: dict,
        diagnostics: list[str],
    ) -> None:
        attempt = int(audit.get('test_run_attempt', report.get('attempt', 0)) or 0)
        test_run_kind = str(audit.get('test_run_kind') or 'normal')
        if not self._has_recorded_audit_run(version.id, attempt, test_run_kind):
            self._record_test_run(version, score, grade, report, step_passes, diagnostics, test_run_kind)
        audit['report'] = report
        audit.pop('test_run_pending', None)
        audit.pop('test_run_attempt', None)
        audit.pop('test_run_status', None)
        audit.pop('test_run_kind', None)
        payload['source_audit'] = audit
        self._runtime.update_version_payload(version.id, payload)

    @staticmethod
    def _audit_result(version, audit: dict) -> dict:
        report = audit.get('report') or {}
        return {
            'source_version_id': version.id,
            'status': str(audit.get('status') or 'failed'),
            'score': int(report.get('score', 0) or 0),
            'grade': str(report.get('grade') or 'F'),
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
            raise SourceAuditRecoveryError('source audit repair enqueue requires recovery') from error

        audit['status'] = 'retry_queued'
        report['recovery_state'] = 'retry_queued'
        audit['report'] = report
        repair_job_id = self._job_id(queued_repair)
        if repair_job_id:
            audit['repair_job_id'] = repair_job_id
        payload['source_audit'] = audit
        try:
            self._runtime.update_version_payload(version.id, payload)
        except Exception as error:
            raise SourceAuditRecoveryError('source audit repair handoff requires recovery') from error
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
        score = int(report.get('score', 0) or 0)
        grade = str(report.get('grade') or 'F')
        step_passes = self._step_passes_from_report(report)
        diagnostics = [str(report.get('reason') or 'source_audit_failed')]
        return self._begin_terminal_finalization(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=score,
            grade=grade,
            step_passes=step_passes,
            diagnostics=diagnostics,
            source_rule=source_rule,
        )

    def _begin_terminal_finalization(
        self,
        *,
        version,
        payload: dict,
        audit: dict,
        report: dict,
        score: int,
        grade: str,
        step_passes: dict,
        diagnostics: list[str],
        source_rule: dict,
    ) -> dict:
        terminal_report = {**report, 'recovery_state': 'failed'}
        try:
            review_item = self._review_service.enqueue_audit_failure(
                source_version_id=version.id,
                source_url=str(payload.get('canonical_url') or source_rule.get('bookSourceUrl') or version.source_id),
                audit_report=terminal_report,
                created_by='system',
            )
        except Exception as error:
            raise SourceAuditRecoveryError('source audit terminal review requires recovery') from error

        audit['status'] = 'terminal_finalizing'
        audit['report'] = terminal_report
        review_item_id = self._job_id(review_item)
        if review_item_id:
            audit['review_item_id'] = review_item_id
        payload['source_audit'] = audit
        try:
            self._runtime.update_version_payload(version.id, payload)
        except Exception as error:
            raise SourceAuditRecoveryError('source audit terminal finalization requires recovery') from error
        return self._complete_terminal_finalization(
            version=version,
            payload=payload,
            audit=audit,
            report=terminal_report,
            score=score,
            grade=grade,
            step_passes=step_passes,
            diagnostics=diagnostics,
        )

    def _recover_terminal_finalizing(self, version, payload: dict, audit: dict) -> dict:
        report = dict(audit.get('report') or {})
        return self._complete_terminal_finalization(
            version=version,
            payload=payload,
            audit=audit,
            report=report,
            score=int(report.get('score', 0) or 0),
            grade=str(report.get('grade') or 'F'),
            step_passes=self._step_passes_from_report(report),
            diagnostics=[str(report.get('reason') or 'source_audit_failed')],
        )

    def _complete_terminal_finalization(
        self,
        *,
        version,
        payload: dict,
        audit: dict,
        report: dict,
        score: int,
        grade: str,
        step_passes: dict,
        diagnostics: list[str],
    ) -> dict:
        attempt = int(report.get('attempt', 0) or 0)
        if not self._has_recorded_audit_run(version.id, attempt):
            try:
                self._record_test_run(version, score, grade, report, step_passes, diagnostics)
            except Exception as error:
                raise SourceAuditRecoveryError('source audit terminal test run requires recovery') from error

        audit['status'] = 'failed'
        audit['finalization_pending'] = True
        audit['report'] = report
        payload['source_audit'] = audit
        try:
            self._runtime.update_version_payload(version.id, payload)
        except Exception as error:
            raise SourceAuditRecoveryError('source audit terminal finalization requires recovery') from error
        return self._finish_terminal_status(version, audit)

    def _finish_terminal_status(self, version, audit: dict) -> dict:
        try:
            self._runtime.update_version_status(version.id, 'failed')
        except Exception as error:
            raise SourceAuditRecoveryError('source audit terminal status requires recovery') from error
        return {
            'source_version_id': version.id,
            'status': 'failed',
            'score': int(audit.get('report', {}).get('score', 0) or 0),
            'grade': str(audit.get('report', {}).get('grade') or 'F'),
            'report': audit.get('report') or {},
        }

    @staticmethod
    def _step_passes_from_report(report: dict) -> dict:
        stages = report.get('stages') or {}
        return {
            'search': (stages.get('search') or {}).get('status') == 'ok',
            'toc': (stages.get('toc') or {}).get('status') == 'ok',
            'content': (stages.get('content') or {}).get('status') == 'ok'
            and int((stages.get('content') or {}).get('content_length', 0) or 0) >= 80,
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

    @staticmethod
    def _remaining_seconds(deadline: float) -> float:
        return max(0.0, deadline - time.monotonic())

    def _has_recorded_audit_run(self, source_version_id: str, attempt: int, test_run_kind: str = 'normal') -> bool:
        list_runs = getattr(self._runtime, 'list_test_runs', None)
        if not callable(list_runs):
            return False
        for run in list_runs(source_version_id):
            step_results = run.get('step_results', {}) if isinstance(run, dict) else getattr(run, 'step_results', {})
            metadata = step_results.get('source_audit', {}) if isinstance(step_results, dict) else {}
            if (
                int(metadata.get('attempt', -1) or -1) == attempt
                and str(metadata.get('run_kind') or 'normal') == test_run_kind
            ):
                return True
        return False

    def _record_test_run(
        self,
        version,
        score: int,
        grade: str,
        report: dict,
        step_passes: dict,
        diagnostics: list[str],
        test_run_kind: str = 'normal',
    ):
        audit_attempt = int(report.get('attempt', 0) or 0)
        step_results = {
            name: {
                'passed': step_passes[name],
                'status': stage['status'],
                'elapsed_ms': stage['elapsed_ms'],
            }
            for name, stage in report['stages'].items()
        }
        source_audit_result = {
            'passed': True,
            'status': 'recorded',
            'elapsed_ms': 0,
            'attempt': audit_attempt,
        }
        if test_run_kind != 'normal':
            source_audit_result['run_kind'] = test_run_kind
        step_results['source_audit'] = source_audit_result
        self._runtime.record_test_run(
            source_version_id=version.id,
            trigger='source_audit',
            score=score,
            grade=grade,
            step_results=step_results,
            diagnostics=diagnostics,
        )

    def _evaluate(self, evidence):
        search = evidence.search
        toc = evidence.toc
        content = evidence.content
        content_stage = {
            'status': content.status,
            'elapsed_ms': content.elapsed_ms,
            'content_length': int(content.detail.get('content_length', 0) or 0),
            'title': content.sample_title,
        }
        block_reason = content.detail.get('block_reason')
        if isinstance(block_reason, str) and block_reason:
            content_stage['block_reason'] = block_reason
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
            'content': content_stage,
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
        elif block_reason == 'verification_wall':
            reason = 'verification_required'
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
    def _browser_validation_report(stages: dict) -> dict:
        def stage(name: str, *, content: bool = False) -> dict:
            raw = stages.get(name) if isinstance(stages, dict) else {}
            raw = raw if isinstance(raw, dict) else {}
            result = {
                'status': str(raw.get('status') or 'failed'),
                'elapsed_ms': int(raw.get('elapsed_ms', 0) or 0),
                'title': str(raw.get('title') or ''),
            }
            if content:
                result['content_length'] = int(raw.get('content_length', 0) or 0)
            else:
                result['hit_count'] = int(raw.get('hit_count', 0) or 0)
            return result

        normalized = {
            'search': stage('search'),
            'toc': stage('toc'),
            'content': stage('content', content=True),
        }
        return {
            'status': 'passed',
            'total_elapsed_ms': sum(item['elapsed_ms'] for item in normalized.values()),
            'stages': normalized,
            'browser_validation': True,
        }

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

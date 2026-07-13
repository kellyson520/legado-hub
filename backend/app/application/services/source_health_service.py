from app.application.services.source_build_service import SourceBuildService
from app.application.services.source_review_service import SourceReviewService
from app.domain.repositories.source_runtime_repo import SourceRuntimeRepository
from app.infrastructure.legado.engine.quality_gate import evaluate_runtime_health


class SourceHealthService:
    def __init__(
        self,
        repo: SourceRuntimeRepository,
        review_service: SourceReviewService | None = None,
        build_service: SourceBuildService | None = None,
    ):
        self._repo = repo
        self._review_service = review_service
        self._build_service = build_service

    async def verify_published_versions(self) -> list[dict]:
        decisions: list[dict] = []
        for version in self._repo.list_published_versions():
            runs = self._repo.list_test_runs(version.id)
            latest_run = runs[0] if runs else None
            decision = evaluate_runtime_health(version, latest_run)
            decision_payload = decision.to_dict()
            if decision.action in {"rollback", "quarantine"}:
                if self._build_service is not None:
                    discovery_submission = self._build_service.submit_discovery(
                        tenant_id='system',
                        url=version.source_id,
                        baseline_source_version_id=version.id,
                        reason=decision.action,
                        previous_status=version.status,
                    )
                    decision_payload['discovery_submission'] = {
                        'job_id': discovery_submission.job_id,
                        'source_version_id': discovery_submission.source_version_id,
                        'status': discovery_submission.status,
                    }
                self._repo.update_version_status(version.id, decision.new_status)
                self._repo.record_health_event(
                    source_version_id=version.id,
                    event_type=decision.action,
                    detail=decision_payload,
                )
                self._repo.record_deployment(
                    source_version_id=version.id,
                    action=decision.action,
                    status=decision.new_status,
                    quality_gate=decision_payload,
                    actor_id="system",
                )
                if self._review_service is not None:
                    self._review_service.enqueue_health_regression(
                        source_version_id=version.id,
                        source_url=version.source_id,
                        decision=decision_payload,
                        created_by='system',
                    )
            decisions.append(decision_payload)
        return decisions

    async def collect_discovery_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        for version in self._repo.list_published_versions():
            runs = self._repo.list_test_runs(version.id)
            latest_run = runs[0] if runs else None
            decision = evaluate_runtime_health(version, latest_run)
            if decision.action in {'rollback', 'quarantine'}:
                candidates.append(
                    {
                        'source_id': version.source_id,
                        'source_version_id': version.id,
                        'reason': decision.action,
                        'status': version.status,
                    }
                )
        return candidates


class RealSourceSmokeRunner:
    def __init__(self, book_sources: list[dict], rss_sources: list[dict], verifier):
        self._book_sources = book_sources
        self._rss_sources = rss_sources
        self._verifier = verifier

    async def run_all(self) -> dict:
        summary = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "by_type": {
                "book": {"total": 0, "passed": 0, "failed": 0, "results": []},
                "rss": {"total": 0, "passed": 0, "failed": 0, "results": []},
            },
        }
        for source_type, items in (("book", self._book_sources), ("rss", self._rss_sources)):
            for item in items:
                result = await self._verifier.verify(source_type, item)
                bucket = summary["by_type"][source_type]
                bucket["total"] += 1
                bucket["results"].append(result)
                summary["total"] += 1
                if result.get("passed"):
                    bucket["passed"] += 1
                    summary["passed"] += 1
                else:
                    bucket["failed"] += 1
                    summary["failed"] += 1
        return summary

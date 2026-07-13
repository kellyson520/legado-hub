from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthAdminService:
    def __init__(self, source_repo, health_repo, probe_service, classifier):
        self._source_repo = source_repo
        self._health_repo = health_repo
        self._probe_service = probe_service
        self._classifier = classifier

    async def list_book_source_health(
        self,
        page: int = 1,
        page_size: int = 20,
        statuses: list[str] | None = None,
    ) -> dict:
        rows, total = self._health_repo.list_snapshots(
            statuses=statuses,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return {
            "items": [self._snapshot_to_dict(item) for item in rows],
            "meta": {"page": page, "page_size": page_size, "total": total},
        }

    async def get_book_source_health(self, source_id: int) -> dict:
        snapshot = self._health_repo.get_snapshot(source_id)
        runs = self._health_repo.list_probe_runs(source_id, limit=10)
        return {
            "snapshot": self._snapshot_to_dict(snapshot) if snapshot else None,
            "runs": [self._run_to_dict(run) for run in runs],
        }

    async def probe_book_source(
        self,
        source_id: int,
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        evidence = await self._probe_service.probe_source(
            source,
            keyword_samples=keyword_samples,
            probe_mode=probe_mode,
        )
        decision = self._classifier.classify(evidence)
        now = datetime.now(timezone.utc)
        previous = self._health_repo.get_snapshot(source_id)
        is_healthy = decision.health_status == "healthy"
        consecutive_failures = 0 if is_healthy else ((previous.consecutive_failures if previous else 0) + 1)
        consecutive_successes = ((previous.consecutive_successes if previous and is_healthy else 0) + 1) if is_healthy else 0

        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status=decision.health_status,
                search_status=decision.search_status,
                toc_status=decision.toc_status,
                content_status=decision.content_status,
                failure_reason=decision.failure_reason,
                decision_confidence=decision.decision_confidence,
                route_policy=decision.route_policy,
                route_score=decision.route_score,
                consecutive_failures=consecutive_failures,
                consecutive_successes=consecutive_successes,
                last_success_at=now if is_healthy else (previous.last_success_at if previous else None),
                last_probe_at=now,
                next_probe_at=now + timedelta(minutes=decision.metadata.get("next_probe_after_minutes", 15)),
                metadata=decision.metadata,
            )
        )
        self._health_repo.record_probe_run(
            SourceProbeRun(
                source_id=source_id,
                source_name=source["bookSourceName"],
                probe_mode=probe_mode,
                keyword=evidence.keyword,
                overall_status=decision.health_status,
                failure_reason=decision.failure_reason,
                search_result=evidence.search.__dict__,
                toc_result=evidence.toc.__dict__,
                content_result=evidence.content.__dict__,
                summary={"route_policy": decision.route_policy, "route_score": decision.route_score},
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status=decision.health_status,
            error_msg=(
                f"{decision.failure_reason}:{decision.decision_confidence}"
                if decision.failure_reason
                else ""
            ),
            last_check_time=now,
        )
        return {"snapshot": self._snapshot_to_dict(snapshot), "decision": decision.metadata}

    async def probe_book_sources(
        self,
        source_ids: list[int],
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> dict:
        results = []
        for source_id in source_ids:
            results.append(
                await self.probe_book_source(
                    source_id,
                    keyword_samples=keyword_samples,
                    probe_mode=probe_mode,
                )
            )
        return {"results": results, "total": len(results)}

    async def recover_source(self, source_id: int) -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status="unknown",
                search_status="unknown",
                toc_status="unknown",
                content_status="unknown",
                route_policy="probe_only",
                failure_reason="",
                decision_confidence="low",
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status="unknown",
            error_msg="",
            last_check_time=datetime.now(timezone.utc),
        )
        return self._snapshot_to_dict(snapshot)

    async def quarantine_source(self, source_id: int, note: str = "manual_quarantine") -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status="blocked",
                search_status="failed",
                toc_status="skipped",
                content_status="skipped",
                failure_reason=note,
                decision_confidence="high",
                route_policy="skip",
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status="blocked",
            error_msg=note,
            last_check_time=datetime.now(timezone.utc),
        )
        return self._snapshot_to_dict(snapshot)

    @staticmethod
    def _snapshot_to_dict(snapshot: SourceHealthSnapshot) -> dict:
        return {
            "source_id": snapshot.source_id,
            "source_name": snapshot.source_name,
            "source_url": snapshot.source_url,
            "health_status": snapshot.health_status,
            "search_status": snapshot.search_status,
            "toc_status": snapshot.toc_status,
            "content_status": snapshot.content_status,
            "failure_reason": snapshot.failure_reason,
            "decision_confidence": snapshot.decision_confidence,
            "route_policy": snapshot.route_policy,
            "route_score": snapshot.route_score,
            "last_probe_at": snapshot.last_probe_at.isoformat() if snapshot.last_probe_at else None,
            "next_probe_at": snapshot.next_probe_at.isoformat() if snapshot.next_probe_at else None,
            "metadata": snapshot.metadata,
        }

    @staticmethod
    def _run_to_dict(run: SourceProbeRun) -> dict:
        return {
            "id": run.id,
            "source_id": run.source_id,
            "keyword": run.keyword,
            "overall_status": run.overall_status,
            "failure_reason": run.failure_reason,
            "search_result": run.search_result,
            "toc_result": run.toc_result,
            "content_result": run.content_result,
            "summary": run.summary,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

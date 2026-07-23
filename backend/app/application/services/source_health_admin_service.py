from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone

from app.core.pagination import paginated_result
from app.core.logging import get_logger
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthAdminService:
    _PERSISTENCE_RESERVE_SECONDS = 0.05
    _VALID_PROBE_MODES = frozenset({"full_chain", "search_only"})
    _TRANSIENT_BLOCK_REASONS = frozenset(
        {
            "network_unreachable",
            "timeout",
            "tls_or_handshake_error",
            "http_status_error",
            "js_runtime_failure",
            "waf_blocked",
        }
    )

    def __init__(self, source_repo, health_repo, probe_service, classifier):
        self._source_repo = source_repo
        self._health_repo = health_repo
        self._probe_service = probe_service
        self._classifier = classifier
        self._logger = get_logger("source_health_admin_service")

    async def aclose(self):
        close = getattr(self._probe_service, "aclose", None)
        if close is not None:
            await close()

    async def list_book_source_health(
        self,
        page: int = 1,
        page_size: int = 20,
        statuses: list[str] | None = None,
        search: str = "",
    ) -> dict:
        offset = (page - 1) * page_size
        rows, total = self._health_repo.list_book_source_health_inventory(
            statuses=statuses,
            search=search,
            limit=page_size,
            offset=offset,
        )
        status_counts = self._health_repo.count_book_source_health_statuses(
            statuses=statuses,
            search=search,
        )
        return paginated_result(
            [self._snapshot_to_dict(item) for item in rows],
            page=page,
            page_size=page_size,
            total=total,
            search=search,
            status_counts=status_counts,
        )

    async def get_book_source_health(self, source_id: int) -> dict:
        snapshot = self._health_repo.get_snapshot(source_id)
        runs = self._health_repo.list_probe_runs(source_id, limit=10)
        run_items = [self._run_to_dict(run) for run in runs]
        return {
            "snapshot": self._snapshot_to_dict(snapshot) if snapshot else None,
            "runs": run_items,
            "route_decision": self._route_decision(snapshot),
            "failure_timeline": self._failure_timeline(run_items),
        }

    async def probe_book_source(
        self,
        source_id: int,
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> dict:
        probe_mode = self._normalize_probe_mode(probe_mode)
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        evidence = await self._probe_service.probe_source(
            source,
            keyword_samples=keyword_samples,
            probe_mode=probe_mode,
        )
        decision = self._classifier.classify(evidence)
        now = datetime.now(timezone.utc)
        previous = self._health_repo.get_snapshot(source_id)
        raw_is_healthy = decision.health_status == "healthy"
        same_failure = bool(
            previous
            and previous.failure_reason
            and previous.failure_reason == decision.failure_reason
        )
        consecutive_failures = 0 if raw_is_healthy else (
            (previous.consecutive_failures if same_failure else 0) + 1
        )
        effective_health_status = decision.health_status
        effective_route_policy = decision.route_policy
        effective_route_score = decision.route_score
        effective_confidence = decision.decision_confidence
        decision_metadata = dict(decision.metadata or {})
        decision_metadata.update(
            {
                "raw_health_status": decision.health_status,
                "consecutive_failure_count": consecutive_failures,
            }
        )
        if (
            decision.health_status == "blocked"
            and decision.failure_reason in self._TRANSIENT_BLOCK_REASONS
            and consecutive_failures < 2
        ):
            effective_health_status = "unknown"
            effective_route_policy = "probe_only"
            effective_route_score = 10.0
            effective_confidence = "low"
            decision_metadata["stability_guard"] = "awaiting_confirmation"

        is_healthy = effective_health_status == "healthy"
        consecutive_successes = (
            ((previous.consecutive_successes if previous and is_healthy else 0) + 1)
            if is_healthy
            else 0
        )

        snapshot = SourceHealthSnapshot(
            source_id=source_id,
            source_name=source["bookSourceName"],
            source_url=source["bookSourceUrl"],
            health_status=effective_health_status,
            search_status=decision.search_status,
            toc_status=decision.toc_status,
            content_status=decision.content_status,
            failure_reason=decision.failure_reason,
            decision_confidence=effective_confidence,
            route_policy=effective_route_policy,
            route_score=effective_route_score,
            consecutive_failures=consecutive_failures,
            consecutive_successes=consecutive_successes,
            last_success_at=now if is_healthy else (previous.last_success_at if previous else None),
            last_probe_at=now,
            next_probe_at=now + timedelta(minutes=decision_metadata.get("next_probe_after_minutes", 15)),
            metadata=decision_metadata,
        )
        run = SourceProbeRun(
            source_id=source_id,
            source_name=source["bookSourceName"],
            probe_mode=probe_mode,
            keyword=evidence.keyword,
            overall_status=effective_health_status,
            failure_reason=decision.failure_reason,
            search_result=evidence.search.__dict__,
            toc_result=evidence.toc.__dict__,
            content_result=evidence.content.__dict__,
            summary={
                "route_policy": effective_route_policy,
                "route_score": effective_route_score,
                "raw_health_status": decision.health_status,
                "stability_guard": decision_metadata.get("stability_guard", ""),
                "attempted_keywords": evidence.attempted_keywords,
                "attempts": evidence.attempts,
            },
        )
        error_msg = (
            f"{decision.failure_reason}:{effective_confidence}"
            if decision.failure_reason
            else ""
        )
        atomic_writer = getattr(self._health_repo, "record_probe_result", None)
        if callable(atomic_writer):
            snapshot, _ = await asyncio.to_thread(
                atomic_writer,
                snapshot,
                run,
                source_status=effective_health_status,
                error_msg=error_msg,
                last_check_time=now,
            )
        else:
            snapshot = self._health_repo.upsert_snapshot(snapshot)
            self._health_repo.record_probe_run(run)
            await self._source_repo.update_book_source_health_fields(
                source_id=source_id,
                source_status=effective_health_status,
                error_msg=error_msg,
                last_check_time=now,
            )
        return {"snapshot": self._snapshot_to_dict(snapshot), "decision": decision_metadata}

    async def probe_book_sources(
        self,
        source_ids: list[int],
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
        timeout_seconds: float | None = None,
    ) -> dict:
        probe_mode = self._normalize_probe_mode(probe_mode)
        source_ids = list(source_ids or [])
        results = []
        failed = 0
        deferred_source_ids: list[int] = []
        deadline = (
            time.monotonic() + max(float(timeout_seconds), 0.0)
            if timeout_seconds is not None
            else None
        )
        set_deadline = getattr(self._probe_service, "set_execution_deadline", None)
        if deadline is not None and callable(set_deadline):
            set_deadline(deadline)
        try:
            for index, source_id in enumerate(source_ids):
                remaining = deadline - time.monotonic() if deadline is not None else None
                if remaining is not None and remaining <= 0:
                    deferred_source_ids.extend(int(item) for item in source_ids[index:])
                    break
                probe_timeout = remaining
                if remaining is not None:
                    if remaining <= self._PERSISTENCE_RESERVE_SECONDS:
                        deferred_source_ids.extend(int(item) for item in source_ids[index:])
                        break
                    probe_timeout = remaining - self._PERSISTENCE_RESERVE_SECONDS
                try:
                    call = self.probe_book_source(
                        source_id,
                        keyword_samples=keyword_samples,
                        probe_mode=probe_mode,
                    )
                    result = (
                        await asyncio.wait_for(call, timeout=probe_timeout)
                        if probe_timeout is not None
                        else await call
                    )
                    result = dict(result or {})
                    result.setdefault("source_id", int(source_id))
                    result["status"] = "completed"
                    results.append(result)
                except asyncio.TimeoutError:
                    failed += 1
                    await self._record_probe_failure_bounded(
                        source_id,
                        keyword_samples=keyword_samples,
                        probe_mode=probe_mode,
                        failure_reason="probe_timeout",
                        error_message="source probe batch timeout",
                        deadline=deadline,
                    )
                    results.append(
                        {
                            "source_id": int(source_id),
                            "status": "failed",
                            "error": "source probe batch timeout",
                        }
                    )
                except Exception as exc:
                    failed += 1
                    safe_error = self._sanitize_error_message(exc)
                    await self._record_probe_failure_bounded(
                        source_id,
                        keyword_samples=keyword_samples,
                        probe_mode=probe_mode,
                        failure_reason="probe_exception",
                        error_message=safe_error,
                        deadline=deadline,
                    )
                    results.append(
                        {
                            "source_id": int(source_id),
                            "status": "failed",
                            "error": safe_error,
                        }
                    )
        finally:
            if deadline is not None and callable(set_deadline):
                set_deadline(None)
        return {
            "results": results,
            "total": len(source_ids),
            "succeeded": len(results) - failed,
            "failed": failed,
            "deferred": len(deferred_source_ids),
            "deferred_source_ids": deferred_source_ids,
        }

    async def _record_probe_failure_bounded(
        self,
        source_id: int,
        *,
        keyword_samples: list[str],
        probe_mode: str,
        failure_reason: str,
        error_message: str,
        deadline: float | None,
    ) -> None:
        if deadline is None:
            await self._record_probe_failure(
                source_id,
                keyword_samples=keyword_samples,
                probe_mode=probe_mode,
                failure_reason=failure_reason,
                error_message=error_message,
            )
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self._logger.warning(
                "probe failure persistence skipped after batch deadline",
                extra={"source_id": source_id, "failure_reason": failure_reason},
            )
            return
        try:
            await asyncio.wait_for(
                self._record_probe_failure(
                    source_id,
                    keyword_samples=keyword_samples,
                    probe_mode=probe_mode,
                    failure_reason=failure_reason,
                    error_message=error_message,
                ),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "probe failure persistence exceeded batch deadline",
                extra={"source_id": source_id, "failure_reason": failure_reason},
            )

    async def _record_probe_failure(
        self,
        source_id: int,
        *,
        keyword_samples: list[str],
        probe_mode: str,
        failure_reason: str,
        error_message: str,
    ) -> None:
        """Persist an inconclusive probe so it is not reported as never attempted."""
        if self._source_repo is None or self._health_repo is None:
            return
        try:
            sources = await self._source_repo.list_book_sources_full(ids=[source_id])
            if not sources:
                return
            source = sources[0]
            now = datetime.now(timezone.utc)
            previous = await asyncio.to_thread(self._health_repo.get_snapshot, source_id)
            same_failure = bool(previous and previous.failure_reason == failure_reason)
            consecutive_failures = (previous.consecutive_failures if same_failure else 0) + 1
            safe_error = self._sanitize_error_message(error_message or failure_reason)
            snapshot = SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status="unknown",
                search_status="failed",
                toc_status="skipped",
                content_status="skipped",
                failure_reason=failure_reason,
                decision_confidence="low",
                route_policy="probe_only",
                route_score=10.0,
                consecutive_failures=consecutive_failures,
                consecutive_successes=0,
                last_success_at=previous.last_success_at if previous else None,
                last_probe_at=now,
                next_probe_at=now + timedelta(minutes=15),
                metadata={
                    "probe_failure": True,
                    "error_message": safe_error,
                },
            )
            run = SourceProbeRun(
                source_id=source_id,
                source_name=source["bookSourceName"],
                probe_mode=probe_mode,
                keyword=(keyword_samples or [""])[0],
                overall_status="unknown",
                failure_reason=failure_reason,
                search_result={
                    "stage": "search",
                    "status": "failed",
                    "error_message": safe_error,
                },
                toc_result={"stage": "toc", "status": "skipped"},
                content_result={"stage": "content", "status": "skipped"},
                summary={"probe_failure": True},
                created_at=now,
            )
            atomic_writer = getattr(self._health_repo, "record_probe_failure", None)
            if callable(atomic_writer):
                await asyncio.to_thread(
                    atomic_writer,
                    snapshot,
                    run,
                    source_status="unknown",
                    error_msg=f"{failure_reason}:low",
                    last_check_time=now,
                )
            else:
                await asyncio.to_thread(self._health_repo.upsert_snapshot, snapshot)
                await asyncio.to_thread(self._health_repo.record_probe_run, run)
                await self._source_repo.update_book_source_health_fields(
                    source_id=source_id,
                    source_status="unknown",
                    error_msg=f"{failure_reason}:low",
                    last_check_time=now,
                )
        except Exception as exc:
            self._logger.warning(
                "probe failure diagnostics persistence failed",
                extra={
                    "source_id": source_id,
                    "failure_reason": failure_reason,
                    "error_type": type(exc).__name__,
                },
            )
            return

    @staticmethod
    def _sanitize_error_message(error_message: object) -> str:
        text = str(error_message or "")
        text = re.sub(
            r"(?i)((?:token|authorization|cookie|password|api[_-]?key)\s*[:=]\s*)([^&\s,;]+)",
            r"\1[redacted]",
            text,
        )
        return text[:500]

    @classmethod
    def _normalize_probe_mode(cls, probe_mode: str) -> str:
        normalized = str(probe_mode or "").strip()
        if normalized not in cls._VALID_PROBE_MODES:
            raise ValueError(f"unsupported probe_mode: {probe_mode!r}")
        return normalized

    def list_probe_candidate_ids(self, limit: int | None = 20) -> list[int]:
        normalized_limit = None if limit is None else max(int(limit), 0)
        return self._health_repo.list_probe_candidate_ids(limit=normalized_limit)

    def claim_probe_candidate_ids(
        self,
        limit: int | None = 20,
        *,
        worker_id: str,
        lease_seconds: int = 1800,
    ) -> list[int]:
        claim = getattr(self._health_repo, "claim_probe_candidate_ids", None)
        if not callable(claim):
            return self.list_probe_candidate_ids(limit=limit)
        return claim(
            limit=limit,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    def release_probe_claims(self, source_ids: list[int], *, worker_id: str) -> None:
        release = getattr(self._health_repo, "release_probe_claims", None)
        if callable(release):
            release(source_ids, worker_id=worker_id)

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
                route_score=10.0,
                failure_reason="not_probed",
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

    @staticmethod
    def _route_decision(snapshot: SourceHealthSnapshot | None) -> dict:
        if snapshot is None:
            return {"policy": "probe_only", "score": 10.0, "reason": "not_probed"}
        return {
            "policy": snapshot.route_policy,
            "score": snapshot.route_score,
            "reason": snapshot.failure_reason or "healthy",
        }

    @staticmethod
    def _failure_timeline(runs: list[dict]) -> list[dict]:
        events = []
        for run in runs:
            for stage in ("search", "toc", "content"):
                result = run.get(f"{stage}_result", {})
                if result.get("status") not in {"failed", "degraded"}:
                    continue
                detail = result.get("detail", {})
                events.append(
                    {
                        "at": run.get("created_at"),
                        "stage": stage,
                        "status": result.get("status"),
                        "reason": run.get("failure_reason") or "unknown_error",
                        "message": result.get("error_message", ""),
                        "request_preview": result.get("request_preview", ""),
                        "http_status": detail.get("http_status"),
                        "response_kind": detail.get("response_kind", ""),
                    }
                )
        return events

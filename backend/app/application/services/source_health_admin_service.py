from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.pagination import paginated_result
from app.core.logging import get_logger
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthAdminService:
    _PERSISTENCE_RESERVE_SECONDS = 0.05
    _POST_DEADLINE_PERSISTENCE_TIMEOUT_SECONDS = 5.0
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
    _INCONCLUSIVE_DEGRADED_REASONS = frozenset(
        {
            "unknown_error",
            "html_instead_of_json",
            "parse_empty",
        }
    )

    def __init__(self, source_repo, health_repo, probe_service, classifier):
        self._source_repo = source_repo
        self._health_repo = health_repo
        self._probe_service = probe_service
        self._classifier = classifier
        self._logger = get_logger("source_health_admin_service")
        self._probe_lease_context: dict[int, tuple[str, str, float | None]] = {}

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
        *,
        lease_worker_id: str | None = None,
        lease_token: str | None = None,
        lease_seconds: int = 1800,
        write_deadline: float | None = None,
    ) -> dict:
        probe_mode = self._normalize_probe_mode(probe_mode)
        sources = await self._source_repo.list_book_sources_full(ids=[source_id])
        if not sources:
            raise ValueError(f"book source not found: {source_id}")

        context = self._probe_lease_context.get(int(source_id))
        owned_lease = False
        if lease_token is None and context is not None:
            lease_worker_id, lease_token, context_deadline = context
            write_deadline = write_deadline if write_deadline is not None else context_deadline
        if lease_token is None:
            lease_worker_id = lease_worker_id or f"manual-source-health-{uuid4().hex}"
            claimed = self._claim_probe_source_leases(
                [source_id],
                worker_id=lease_worker_id,
                lease_seconds=lease_seconds,
            )
            if claimed is not None:
                lease_token = claimed.get(int(source_id))
                if not lease_token:
                    raise RuntimeError("source probe lease is busy")
                owned_lease = True

        try:
            source = sources[0]
            evidence = await self._probe_service.probe_source(
                source,
                keyword_samples=keyword_samples,
                probe_mode=probe_mode,
            )
            decision = self._classifier.classify(evidence)
            now = datetime.now(timezone.utc)
            previous = self._health_repo.get_snapshot(source_id)
            raw_is_healthy = decision.health_status == "healthy"
            failure_fingerprint = self._failure_fingerprint(evidence, decision.failure_reason)
            previous_fingerprint = str((previous.metadata or {}).get("failure_fingerprint") or "") if previous else ""
            same_failure = bool(
                previous
                and previous.failure_reason
                and previous.failure_reason == decision.failure_reason
                and previous_fingerprint
                and previous_fingerprint == failure_fingerprint
            )
            consecutive_failures = 0 if raw_is_healthy else (
                (previous.consecutive_failures if same_failure else 0) + 1
            )
            effective_health_status = decision.health_status
            effective_route_policy = decision.route_policy
            effective_route_score = decision.route_score
            effective_confidence = decision.decision_confidence
            decision_metadata = dict(decision.metadata or {})
            if failure_fingerprint:
                decision_metadata["failure_fingerprint"] = failure_fingerprint
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
            elif decision.failure_reason == "empty_result":
                # A valid empty response is evidence that the endpoint
                # answered, not evidence that the source is broken.
                effective_health_status = "unknown"
                effective_route_policy = "probe_only"
                effective_route_score = 10.0
                effective_confidence = "low"
                decision_metadata["stability_guard"] = "inconclusive_empty_result"
            elif (
                decision.health_status == "degraded"
                and decision.failure_reason in self._INCONCLUSIVE_DEGRADED_REASONS
                and consecutive_failures < 2
            ):
                # A parser/runtime mismatch or empty upstream response is not
                # enough evidence to call a source degraded on the first try.
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
                writer_kwargs = {
                    "source_status": effective_health_status,
                    "error_msg": error_msg,
                    "last_check_time": now,
                }
                if lease_worker_id and lease_token:
                    writer_kwargs.update(
                        {"worker_id": lease_worker_id, "lease_token": lease_token}
                    )
                    if write_deadline is not None:
                        writer_kwargs["write_deadline"] = write_deadline
                snapshot, _ = await self._run_atomic_writer(
                    atomic_writer,
                    snapshot,
                    run,
                    deadline=write_deadline,
                    **writer_kwargs,
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
        finally:
            if owned_lease and lease_worker_id and lease_token:
                self.release_probe_claims(
                    [source_id],
                    worker_id=lease_worker_id,
                    lease_tokens={int(source_id): lease_token},
                )

    async def probe_book_sources(
        self,
        source_ids: list[int],
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
        timeout_seconds: float | None = None,
        lease_worker_id: str | None = None,
        lease_tokens: dict[int, str] | None = None,
        lease_seconds: int = 1800,
    ) -> dict:
        probe_mode = self._normalize_probe_mode(probe_mode)
        source_ids = list(source_ids or [])
        results = []
        failed = 0
        deferred_source_ids: list[int] = []
        batch_worker_id = lease_worker_id or f"batch-source-health-{uuid4().hex}"
        active_lease_tokens = {int(key): str(value) for key, value in (lease_tokens or {}).items()}
        owned_lease_tokens: dict[int, str] = {}
        claim_method = getattr(self._health_repo, "claim_probe_source_leases", None)
        if callable(claim_method):
            missing_ids = [source_id for source_id in source_ids if source_id not in active_lease_tokens]
            if missing_ids:
                claimed = claim_method(
                    missing_ids,
                    worker_id=batch_worker_id,
                    lease_seconds=lease_seconds,
                )
                active_lease_tokens.update(claimed)
                owned_lease_tokens.update(claimed)
            deferred_source_ids.extend(
                int(source_id)
                for source_id in source_ids
                if source_id not in active_lease_tokens
            )
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
                source_id = int(source_id)
                if source_id not in active_lease_tokens and callable(claim_method):
                    continue
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
                    self._probe_lease_context[source_id] = (
                        batch_worker_id,
                        active_lease_tokens.get(source_id, ""),
                        deadline - self._PERSISTENCE_RESERVE_SECONDS if deadline is not None else None,
                    )
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
                        worker_id=batch_worker_id,
                        lease_token=active_lease_tokens.get(source_id),
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
                        worker_id=batch_worker_id,
                        lease_token=active_lease_tokens.get(source_id),
                    )
                    results.append(
                        {
                            "source_id": int(source_id),
                            "status": "failed",
                            "error": safe_error,
                        }
                    )
                finally:
                    self._probe_lease_context.pop(source_id, None)
        finally:
            if deadline is not None and callable(set_deadline):
                set_deadline(None)
            if owned_lease_tokens:
                self.release_probe_claims(
                    list(owned_lease_tokens),
                    worker_id=batch_worker_id,
                    lease_tokens=owned_lease_tokens,
                )
        return {
            "results": results,
            "total": len(source_ids),
            "succeeded": len(results) - failed,
            "failed": failed,
            "deferred": len(dict.fromkeys(deferred_source_ids)),
            "deferred_source_ids": list(dict.fromkeys(deferred_source_ids)),
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
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> None:
        if deadline is None:
            await self._record_probe_failure(
                source_id,
                keyword_samples=keyword_samples,
                probe_mode=probe_mode,
                failure_reason=failure_reason,
                error_message=error_message,
                worker_id=worker_id,
                lease_token=lease_token,
            )
            return

        remaining = deadline - time.monotonic()
        write_deadline = deadline - self._PERSISTENCE_RESERVE_SECONDS
        write_remaining = write_deadline - time.monotonic()
        if remaining <= 0 or write_remaining <= 0:
            self._logger.warning(
                "probe failure persistence is using post-deadline grace period",
                extra={"source_id": source_id, "failure_reason": failure_reason},
            )
            try:
                await asyncio.wait_for(
                    self._record_probe_failure(
                        source_id,
                        keyword_samples=keyword_samples,
                        probe_mode=probe_mode,
                        failure_reason=failure_reason,
                        error_message=error_message,
                        worker_id=worker_id,
                        lease_token=lease_token,
                        write_deadline=None,
                    ),
                    timeout=self._POST_DEADLINE_PERSISTENCE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                self._logger.error(
                    "probe failure persistence exceeded post-deadline grace period",
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
                    worker_id=worker_id,
                    lease_token=lease_token,
                    write_deadline=write_deadline,
                ),
                timeout=write_remaining,
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
        worker_id: str | None = None,
        lease_token: str | None = None,
        write_deadline: float | None = None,
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
            context = self._probe_lease_context.get(int(source_id))
            worker_id = worker_id or (context[0] if context else None)
            lease_token = lease_token or (context[1] if context else None)
            write_deadline = write_deadline if write_deadline is not None else (context[2] if context else None)
            previous = self._health_repo.get_snapshot(source_id)
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
                writer_kwargs = {
                    "source_status": "unknown",
                    "error_msg": f"{failure_reason}:low",
                    "last_check_time": now,
                }
                if worker_id and lease_token:
                    writer_kwargs.update({"worker_id": worker_id, "lease_token": lease_token})
                    if write_deadline is not None:
                        writer_kwargs["write_deadline"] = write_deadline
                await self._run_atomic_writer(
                    atomic_writer,
                    snapshot,
                    run,
                    deadline=write_deadline,
                    **writer_kwargs,
                )
            else:
                self._health_repo.upsert_snapshot(snapshot)
                self._health_repo.record_probe_run(run)
                await self._source_repo.update_book_source_health_fields(
                    source_id=source_id,
                    source_status="unknown",
                    error_msg=f"{failure_reason}:low",
                    last_check_time=now,
                )
        except TimeoutError:
            raise
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
    async def _run_atomic_writer(writer, snapshot, run, *, deadline: float | None, **kwargs):
        if deadline is not None and time.monotonic() >= deadline:
            raise asyncio.TimeoutError("probe persistence deadline exceeded")
        future = asyncio.create_task(asyncio.to_thread(writer, snapshot, run, **kwargs))
        try:
            if deadline is None:
                return await asyncio.shield(future)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError("probe persistence deadline exceeded")
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=remaining)
            except asyncio.TimeoutError:
                # The repository receives the same deadline and must roll back
                # if SQLite only becomes writable after it has elapsed. Drain
                # the worker so cancellation cannot leave a late DB side effect.
                return await asyncio.shield(future)
        except asyncio.CancelledError:
            try:
                result = await asyncio.shield(future)
            except BaseException:
                raise
            # The database operation may have completed successfully at the
            # timeout boundary. Preserve that committed result instead of
            # recording a second timeout state over it.
            return result

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
    def _failure_fingerprint(cls, evidence, failure_reason: str) -> str:
        if not failure_reason:
            return ""
        parts = [failure_reason]
        for stage in (evidence.search, evidence.toc, evidence.content):
            detail = stage.detail or {}
            parts.extend(
                [
                    stage.stage,
                    stage.status,
                    re.sub(r"\s+", " ", cls._sanitize_error_message(stage.error_message)).strip().lower(),
                    re.sub(r"\s+", " ", cls._sanitize_error_message(detail.get("js_error"))).strip().lower(),
                    str(detail.get("http_status") or ""),
                    str(detail.get("response_kind") or "").strip().lower(),
                    str(detail.get("parse_status") or "").strip().lower(),
                    str(detail.get("block_reason") or "").strip().lower(),
                ]
            )
        payload = "\x1f".join(parts).encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()[:16]

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

    def claim_probe_candidate_leases(
        self,
        limit: int | None = 20,
        *,
        worker_id: str,
        lease_seconds: int = 1800,
    ) -> dict[int, str] | None:
        claim = getattr(self._health_repo, "claim_probe_candidate_leases", None)
        if not callable(claim):
            return None
        return {
            int(source_id): str(token)
            for source_id, token in claim(
                limit=limit,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ).items()
        }

    def release_probe_claims(
        self,
        source_ids: list[int],
        *,
        worker_id: str,
        lease_tokens: dict[int, str] | None = None,
    ) -> None:
        release = getattr(self._health_repo, "release_probe_claims", None)
        if callable(release):
            release(source_ids, worker_id=worker_id, lease_tokens=lease_tokens)

    def _claim_probe_source_leases(
        self,
        source_ids: list[int],
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> dict[int, str] | None:
        claim = getattr(self._health_repo, "claim_probe_source_leases", None)
        if not callable(claim):
            return None
        return {
            int(source_id): str(token)
            for source_id, token in claim(
                source_ids,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ).items()
        }

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

from __future__ import annotations

import time
from typing import Any


REAL_SITE_URLS = [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/",
]


class SourceToInsightAcceptanceService:
    def __init__(
        self,
        *,
        source_build_service,
        source_build_runtime=None,
        reading_service=None,
        complement_service=None,
        character_service=None,
        knowledge_service=None,
        provider_platform=None,
        job_repository=None,
        source_repository=None,
        source_runtime_repository=None,
    ):
        self._source_build_service = source_build_service
        self._source_build_runtime = source_build_runtime
        self._reading_service = reading_service
        self._complement_service = complement_service
        self._character_service = character_service
        self._knowledge_service = knowledge_service
        self._provider_platform = provider_platform
        self._job_repository = job_repository
        self._source_repository = source_repository
        self._source_runtime_repository = source_runtime_repository

    async def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        source_urls = list(scenario.get("source_urls") or REAL_SITE_URLS)
        tenant_id = str(scenario.get("tenant_id") or "source-insight-smoke")
        book_name = str(scenario.get("book_name") or "斗罗大陆")
        author_hint = str(scenario.get("author_hint") or "唐家三少")
        use_ai = bool(scenario.get("use_ai", False))

        steps: list[dict[str, Any]] = []
        source_builds = []
        build_started = time.time()
        for url in source_urls:
            source_builds.append(self._run_source_build(url=url, tenant_id=tenant_id, keyword=book_name))
        steps.append({
            "name": "source_build",
            "status": _step_status(
                passed=sum(1 for item in source_builds if item["status"] == "passed"),
                total=len(source_builds),
            ),
            "elapsed_ms": _elapsed_ms(build_started),
            "summary": {
                "total": len(source_builds),
                "passed": sum(1 for item in source_builds if item["status"] == "passed"),
                "failed": sum(1 for item in source_builds if item["status"] == "failed"),
            },
            "errors": [item["error"] for item in source_builds if item.get("error")],
        })

        usable_builds = [
            item for item in source_builds
            if (
                item.get("status") == "passed"
                and item.get("decision") == "canary"
                and item.get("source_rule")
            )
        ]
        materialize_started = time.time()
        try:
            generated_source_ids = await self._materialize_generated_sources(
                usable_builds,
                actor_id=tenant_id,
            )
            materialize_errors = [
                item["materialization"]["error"]
                for item in usable_builds
                if (item.get("materialization") or {}).get("status") == "failed"
                and (item.get("materialization") or {}).get("error")
            ]
            materialize_failed = False
        except Exception as exc:
            generated_source_ids = []
            materialize_errors = [str(exc) or exc.__class__.__name__]
            materialize_failed = True
            for item in usable_builds:
                item["materialization"] = {
                    "status": "failed",
                    "error": materialize_errors[0],
                }
        steps.append({
            "name": "source_materialization",
            "status": _step_status(
                passed=len(generated_source_ids),
                total=len(usable_builds),
                skipped=self._source_repository is None or not usable_builds,
                failed=materialize_failed,
            ),
            "elapsed_ms": _elapsed_ms(materialize_started),
            "summary": {
                "eligible": len(usable_builds),
                "materialized": len(generated_source_ids),
            },
            "errors": materialize_errors,
        })
        book_candidates = []
        toc_candidates = []
        chapter_candidates = []
        complement = {}
        insights = {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []}

        reading_started = time.time()
        reading_total = len(generated_source_ids)
        reading_passed = 0
        reading_errors: list[str] = []
        if self._reading_service is not None and generated_source_ids:
            for build in source_builds:
                generated_source_id = build.get("generated_source_id")
                if not generated_source_id:
                    if build.get("status") == "passed":
                        build.setdefault("reading", {"status": "skipped", "error": "no generated source"})
                    continue
                try:
                    outcome = await self._read_generated_source(
                        source_id=int(generated_source_id),
                        book_name=book_name,
                        author_hint=author_hint,
                        chapter_index=int(scenario.get("chapter_index", 0) or 0),
                        chapter_title=str(scenario.get("chapter_title") or ""),
                    )
                    book_candidates.extend(outcome["book_candidates"])
                    toc_candidates.extend(outcome["toc_candidates"])
                    chapter_candidates.extend(outcome["chapter_candidates"])
                    build["reading"] = {
                        "status": outcome["status"],
                        "source_id": int(generated_source_id),
                        "book_candidates": len(outcome["book_candidates"]),
                        "toc_candidates": len(outcome["toc_candidates"]),
                        "chapter_candidates": len(outcome["chapter_candidates"]),
                        "content_length": outcome["content_length"],
                        "error": outcome["error"],
                    }
                    if outcome["status"] == "passed":
                        reading_passed += 1
                    elif outcome["error"]:
                        reading_errors.append(outcome["error"])
                except Exception as exc:
                    error = str(exc) or exc.__class__.__name__
                    reading_errors.append(error)
                    build["reading"] = {
                        "status": "failed",
                        "source_id": int(generated_source_id),
                        "book_candidates": 0,
                        "toc_candidates": 0,
                        "chapter_candidates": 0,
                        "content_length": 0,
                        "error": error,
                    }
        steps.append({
            "name": "reading",
            "status": _step_status(
                passed=reading_passed,
                total=reading_total,
                skipped=self._reading_service is None or not generated_source_ids,
            ),
            "elapsed_ms": _elapsed_ms(reading_started),
            "summary": {
                "total": reading_total,
                "passed": reading_passed,
                "failed": max(reading_total - reading_passed, 0),
            },
            "errors": reading_errors,
        })

        complement_started = time.time()
        complement_error = ""
        if self._complement_service is not None and chapter_candidates:
            try:
                content_candidates = [
                    item
                    for item in chapter_candidates
                    if int(item.get("content_length", 0) or 0) > 0
                ]
                items = [
                    {
                        "source_id": item["source_id"],
                        "chapter_url": item["chapter_url"],
                        "source_name": "",
                        "source_url": "",
                    }
                    for item in content_candidates
                ]
                if items:
                    reference_candidate = content_candidates[0]
                    complement = await self._complement_service.complement_chapter_candidates(
                        book_name=book_name,
                        chapter_title=reference_candidate.get("title") or str(scenario.get("chapter_title") or ""),
                        chapter_num=int(scenario.get("chapter_index", 0) or 0) + 1,
                        items=items,
                        reference_content=reference_candidate.get("content", ""),
                        merge_strategy="hybrid",
                    )
                else:
                    complement = {"status": "skipped", "error": "no usable chapter content"}
            except Exception as exc:
                complement_error = str(exc) or exc.__class__.__name__
                complement = {"status": "failed", "error": complement_error}
            finally:
                close = getattr(self._complement_service, "aclose", None)
                if close:
                    try:
                        await close()
                    except Exception as exc:
                        complement_error = complement_error or str(exc) or exc.__class__.__name__
                        complement = {"status": "failed", "error": complement_error}
        steps.append({
            "name": "complement",
            "status": (
                "skipped"
                if self._complement_service is None or not chapter_candidates
                else ("failed" if complement_error else (complement.get("status") or "passed"))
            ),
            "elapsed_ms": _elapsed_ms(complement_started),
            "summary": {
                "chapter_candidates": len(chapter_candidates),
                "content_candidates": sum(1 for item in chapter_candidates if int(item.get("content_length", 0) or 0) > 0),
            },
            "errors": [complement_error] if complement_error else [],
        })

        insight_started = time.time()
        insight_error = ""
        ai_status = "skipped"
        if use_ai and self._character_service is not None and chapter_candidates:
            try:
                character_result = await self._character_service.calibrate(
                    keyword=book_name,
                    items=[
                        {
                            "source_id": item.get("source_id"),
                            "name": book_name,
                            "author": author_hint,
                            "excerpt": item.get("content_preview", ""),
                        }
                        for item in chapter_candidates
                        if int(item.get("content_length", 0) or 0) > 0
                    ],
                    actor_id=tenant_id,
                )
                insights["characters"] = character_result.get("items", [])
                ai_status = "completed"
            except Exception as exc:
                insight_error = str(exc) or exc.__class__.__name__
                ai_status = "failed"
        steps.append({
            "name": "insights",
            "status": "failed" if insight_error else ("passed" if ai_status == "completed" else "skipped"),
            "elapsed_ms": _elapsed_ms(insight_started),
            "summary": {
                "use_ai": use_ai,
                "characters": len(insights["characters"]),
            },
            "errors": [insight_error] if insight_error else [],
        })

        if self._reading_service is None:
            status = "failed"
        else:
            content_usable = sum(
                1
                for item in source_builds
                if (item.get("reading") or {}).get("status") == "passed"
            )
            status = "passed" if content_usable == len(source_urls) else "partial"
            if content_usable == 0:
                status = "failed"
        report = {
            "scenario": {
                "source_urls": source_urls,
                "book_name": book_name,
                "author_hint": author_hint,
                "chapter_index": int(scenario.get("chapter_index", 0) or 0),
                "chapter_title": str(scenario.get("chapter_title") or "第一章"),
                "use_ai": use_ai,
            },
            "status": status,
            "elapsed_ms": _elapsed_ms(started),
            "steps": steps,
            "source_builds": source_builds,
            "book_candidates": book_candidates,
            "toc_candidates": toc_candidates,
            "chapter_candidates": chapter_candidates,
            "complement": complement,
            "insights": insights,
            "knowledge_proposals": [],
            "ai": {"used": ai_status == "completed", "status": ai_status, "provider": "", "model": "", "usage": {}},
        }
        await self._close_reading_service()
        return report

    def _run_source_build(self, *, url: str, tenant_id: str, keyword: str) -> dict[str, Any]:
        started = time.time()
        try:
            submission = self._source_build_service.submit(
                tenant_id=tenant_id,
                url=url,
                keyword=keyword,
            )
            runtime_result = {}
            if self._source_build_runtime is not None:
                if self._job_repository is not None and hasattr(self._source_build_runtime, "handle_job"):
                    job = _get_job(self._job_repository, submission.job_id)
                    runtime_result = self._source_build_runtime.handle_job(job)
                elif hasattr(self._source_build_runtime, "handle_source_version"):
                    runtime_result = self._source_build_runtime.handle_source_version(
                        source_version_id=submission.source_version_id,
                        job_id=submission.job_id,
                        url=submission.normalized_url,
                        tenant_id=tenant_id,
                    )
            persisted_payload = self._load_persisted_source_payload(submission.source_version_id)
            source_rule = runtime_result.get("source_rule") or persisted_payload.get("source_rule") or {}
            if not isinstance(source_rule, dict):
                source_rule = {}
            return {
                "url": url,
                "normalized_url": submission.normalized_url,
                "job_id": submission.job_id,
                "source_version_id": submission.source_version_id,
                "source_version_status": submission.source_version_status,
                "status": "passed",
                "elapsed_ms": _elapsed_ms(started),
                "agent_run_id": runtime_result.get("agent_run_id"),
                "decision": runtime_result.get("decision"),
                "strategy": runtime_result.get("strategy"),
                "review_required": runtime_result.get("review_required"),
                "source_rule": source_rule,
                "autonomous_build": runtime_result.get("autonomous_build") or persisted_payload.get("autonomous_build") or {},
                "error": "",
            }
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "elapsed_ms": _elapsed_ms(started),
                "error": str(exc) or exc.__class__.__name__,
            }

    def _load_persisted_source_payload(self, source_version_id: str) -> dict[str, Any]:
        if self._source_runtime_repository is None:
            return {}
        version = self._source_runtime_repository.get_version(source_version_id)
        payload = getattr(version, "payload", {}) if version is not None else {}
        return payload if isinstance(payload, dict) else {}

    async def _read_generated_source(
        self,
        *,
        source_id: int,
        book_name: str,
        author_hint: str,
        chapter_index: int,
        chapter_title: str,
    ) -> dict[str, Any]:
        book_candidates = []
        toc_candidates = []
        chapter_candidates = []
        search_result = await self._reading_service.search_books(
            book_name,
            source_ids=[source_id],
            limit_per_source=3,
            author_hint=author_hint,
            routing_mode="auto",
            include_health=True,
        )
        book_candidates = search_result.get("items", [])
        selected = book_candidates[: min(3, len(book_candidates))]
        if not selected:
            return {
                "status": "failed",
                "book_candidates": book_candidates,
                "toc_candidates": toc_candidates,
                "chapter_candidates": chapter_candidates,
                "content_length": 0,
                "error": "no book candidates",
            }
        evidence_error = ""
        for book in selected:
            if int(book.get("source_id", -1)) != source_id:
                continue
            toc = await self._reading_service.get_book_toc(
                source_id,
                book["bookUrl"],
                book_name=None,
                author_hint=None,
                routing_mode="auto",
            )
            toc_candidates.append(_toc_report_evidence(toc))
            toc_error = _source_evidence_error(toc, expected_source_id=source_id, stage="toc")
            if toc_error:
                evidence_error = toc_error
                continue
            chapters = toc.get("chapters") or []
            if not chapters:
                continue
            chapter = _select_chapter(chapters, chapter_index, chapter_title)
            content = await self._reading_service.get_chapter_content(
                source_id,
                chapter["url"],
                book_name=None,
                author_hint=None,
                chapter_title=chapter.get("title"),
                chapter_index=chapter.get("index"),
                routing_mode="auto",
            )
            content_error = _source_evidence_error(content, expected_source_id=source_id, stage="content")
            content_length = 0 if content_error else len(content.get("content", "") or "")
            chapter_candidates.append({
                **content,
                "content_preview": _preview(content.get("content", "")),
                "content_length": content_length,
            })
            if content_error:
                evidence_error = content_error
                continue
            if content_length > 0:
                return {
                    "status": "passed",
                    "book_candidates": book_candidates,
                    "toc_candidates": toc_candidates,
                    "chapter_candidates": chapter_candidates,
                    "content_length": content_length,
                    "error": "",
                }
        return {
            "status": "failed",
            "book_candidates": book_candidates,
            "toc_candidates": toc_candidates,
            "chapter_candidates": chapter_candidates,
            "content_length": 0,
            "error": evidence_error or "no usable chapter content",
        }

    async def _materialize_generated_sources(
        self,
        source_builds: list[dict[str, Any]],
        *,
        actor_id: str,
    ) -> list[int]:
        if self._source_repository is None:
            return []
        generated_source_ids = []
        for build in source_builds:
            rule = _normalize_generated_source_rule(build.get("source_rule") or {})
            if not rule:
                build["materialization"] = {
                    "status": "failed",
                    "error": "generated source rule is missing bookSourceUrl",
                }
                continue
            try:
                await self._source_repository.upsert_book_sources(
                    [rule],
                    actor_id=_actor_id(actor_id),
                )
                sources = await self._source_repository.list_book_sources_full(
                    enabled_only=True,
                    urls=[rule["bookSourceUrl"]],
                )
            except Exception as exc:
                build["materialization"] = {
                    "status": "failed",
                    "error": str(exc) or exc.__class__.__name__,
                }
                continue
            source_id = next(
                (
                    int(source["id"])
                    for source in sources
                    if source.get("id") is not None
                    and source.get("bookSourceUrl") == rule["bookSourceUrl"]
                ),
                None,
            )
            if source_id is None:
                build["materialization"] = {
                    "status": "failed",
                    "error": "generated source was not persisted",
                }
                continue
            build["generated_source_id"] = source_id
            build["materialization"] = {
                "status": "passed",
                "source_id": source_id,
            }
            generated_source_ids.append(source_id)
        return generated_source_ids

    async def _close_reading_service(self) -> None:
        close = getattr(self._reading_service, "aclose", None)
        if not callable(close):
            return
        try:
            await close()
        except Exception:
            return


def _elapsed_ms(started: float) -> int:
    return int((time.time() - started) * 1000)


def _select_chapter(chapters: list[dict[str, Any]], chapter_index: int, chapter_title: str) -> dict[str, Any]:
    for item in chapters:
        if int(item.get("index", -1)) == chapter_index:
            return item
    if chapter_title:
        for item in chapters:
            if chapter_title in str(item.get("title", "")):
                return item
    return chapters[0]


def _toc_report_evidence(toc: dict[str, Any]) -> dict[str, Any]:
    report = {
        key: toc[key]
        for key in ("source_id", "resolved_source_id", "book_url", "fallback_used")
        if key in toc
    }
    report["chapters"] = [
        {
            key: chapter[key]
            for key in ("title", "url", "index")
            if key in chapter
        }
        for chapter in toc.get("chapters") or []
        if isinstance(chapter, dict)
    ]
    return report


def _preview(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    return text[:limit]


def _step_status(*, passed: int, total: int, skipped: bool = False, failed: bool = False) -> str:
    if failed:
        return "failed"
    if skipped or total == 0:
        return "skipped"
    if passed == total:
        return "passed"
    if passed > 0:
        return "partial"
    return "failed"


def _get_job(repository, job_id: str):
    getter = getattr(repository, "get", None) or getattr(repository, "get_job", None)
    if not callable(getter):
        raise AttributeError("job repository does not provide get(job_id)")
    job = getter(job_id)
    if job is None:
        raise ValueError(f"source build job not found: {job_id}")
    return job


def _source_evidence_error(evidence: dict[str, Any], *, expected_source_id: int, stage: str) -> str:
    if evidence.get("fallback_used") is True:
        return f"{stage} fallback evidence rejected"
    for key in ("source_id", "resolved_source_id"):
        if key not in evidence or evidence.get(key) is None:
            continue
        if not _same_source_id(evidence.get(key), expected_source_id):
            return f"{stage} {key} {evidence.get(key)} differs from expected source {expected_source_id}"
    return ""


def _same_source_id(value: Any, expected: int) -> bool:
    try:
        return int(value) == int(expected)
    except (TypeError, ValueError):
        return str(value) == str(expected)


def _normalize_generated_source_rule(rule: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rule, dict):
        return {}
    source_url = str(rule.get("bookSourceUrl") or "").strip()
    if not source_url:
        return {}
    source_name = str(rule.get("bookSourceName") or source_url).strip()
    return {
        **rule,
        "bookSourceName": source_name,
        "bookSourceUrl": source_url,
        "bookSourceGroup": rule.get("bookSourceGroup") or "source-build-smoke",
        "enabled": True,
        "sourceOrigin": rule.get("sourceOrigin") or "source_build_acceptance",
    }


def _actor_id(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

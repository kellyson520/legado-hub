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
    ):
        self._source_build_service = source_build_service
        self._source_build_runtime = source_build_runtime
        self._reading_service = reading_service
        self._complement_service = complement_service
        self._character_service = character_service
        self._knowledge_service = knowledge_service
        self._provider_platform = provider_platform
        self._job_repository = job_repository

    async def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        source_urls = list(scenario.get("source_urls") or REAL_SITE_URLS)
        tenant_id = str(scenario.get("tenant_id") or "source-insight-smoke")
        book_name = str(scenario.get("book_name") or "斗罗大陆")
        author_hint = str(scenario.get("author_hint") or "唐家三少")

        steps: list[dict[str, Any]] = []
        source_builds = []
        build_started = time.time()
        for url in source_urls:
            source_builds.append(self._run_source_build(url=url, tenant_id=tenant_id, keyword=book_name))
        steps.append({
            "name": "source_build",
            "status": "passed" if any(item["status"] == "passed" for item in source_builds) else "failed",
            "elapsed_ms": _elapsed_ms(build_started),
            "summary": {
                "total": len(source_builds),
                "passed": sum(1 for item in source_builds if item["status"] == "passed"),
                "failed": sum(1 for item in source_builds if item["status"] == "failed"),
            },
            "errors": [item["error"] for item in source_builds if item.get("error")],
        })

        status = "passed" if steps[-1]["summary"]["passed"] == len(source_urls) else "partial"
        if steps[-1]["summary"]["passed"] == 0:
            status = "failed"
        return {
            "scenario": {
                "source_urls": source_urls,
                "book_name": book_name,
                "author_hint": author_hint,
                "chapter_index": int(scenario.get("chapter_index", 0) or 0),
                "chapter_title": str(scenario.get("chapter_title") or "第一章"),
                "use_ai": bool(scenario.get("use_ai", False)),
            },
            "status": status,
            "elapsed_ms": _elapsed_ms(started),
            "steps": steps,
            "source_builds": source_builds,
            "book_candidates": [],
            "toc_candidates": [],
            "chapter_candidates": [],
            "complement": {},
            "insights": {
                "characters": [],
                "relations": [],
                "plot_events": [],
                "world_rules": [],
                "timeline": [],
            },
            "knowledge_proposals": [],
            "ai": {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}},
        }

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
                    job = self._job_repository.get_job(submission.job_id)
                    runtime_result = self._source_build_runtime.handle_job(job)
                elif hasattr(self._source_build_runtime, "handle_source_version"):
                    runtime_result = self._source_build_runtime.handle_source_version(
                        source_version_id=submission.source_version_id,
                        job_id=submission.job_id,
                        url=submission.normalized_url,
                        tenant_id=tenant_id,
                    )
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
                "source_rule": runtime_result.get("source_rule") or {},
                "autonomous_build": runtime_result.get("autonomous_build") or {},
                "error": "",
            }
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "elapsed_ms": _elapsed_ms(started),
                "error": str(exc) or exc.__class__.__name__,
            }


def _elapsed_ms(started: float) -> int:
    return int((time.time() - started) * 1000)

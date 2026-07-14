# Source Build Engine Real Site Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable smoke runner that submits the four operator-provided real sites to the existing source-writing engine, then verifies search/toc/content/complement/insight behavior from the engine-generated candidates.

**Architecture:** Add a backend acceptance service and script. The service uses `SourceBuildService.submit()` and `SourceBuildRuntimeService.handle_job()` to exercise the current source build engine, records the generated candidate payload, then runs existing reading/complement/knowledge services when generated rules are usable. No final source rules are hand-authored in the smoke path.

**Tech Stack:** Python 3, FastAPI service layer, SQLite repositories, existing source.build job engine, existing Legado fetcher, pytest.

---

## File Structure

- Create: `backend/app/application/services/source_to_insight_acceptance_service.py`
  - Orchestrates source build submissions, job execution, reading verification, complement, deterministic insight candidates, and report shaping.
- Create: `backend/scripts/smoke_source_to_insight.py`
  - CLI entrypoint for fixture and real-site smoke runs.
- Create: `backend/tests/test_source_to_insight_acceptance_service.py`
  - Unit tests with fake source-build, reading, complement, knowledge, and AI dependencies.
- Create: `backend/tests/test_smoke_source_to_insight.py`
  - CLI-level contract tests using a tiny scenario file and fake service.
- Modify: `docs/superpowers/specs/2026-07-14-source-to-insight-acceptance-design.md`
  - Already updated; do not change unless implementation discovers a contradiction.

## Real Site Targets

The default real-site scenario must include:

```python
REAL_SITE_URLS = [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/",
]
```

Default book target:

```python
DEFAULT_BOOK_NAME = "斗罗大陆"
DEFAULT_AUTHOR_HINT = "唐家三少"
DEFAULT_CHAPTER_INDEX = 0
DEFAULT_CHAPTER_TITLE = "第一章"
```

## Task 1: Acceptance report model and source-build engine orchestration

**Files:**
- Create: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Test: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Write the failing unit test for source-build outcomes**

Add this test:

```python
import pytest


class FakeSourceBuildService:
    def __init__(self):
        self.submitted = []

    def submit(self, *, tenant_id, url, keyword='', extra_payload=None, extra_job_payload=None, idempotency_key_prefix='source.build'):
        self.submitted.append({"tenant_id": tenant_id, "url": url, "keyword": keyword})
        return type("Submission", (), {
            "job_id": f"job-{len(self.submitted)}",
            "normalized_url": url.rstrip("/"),
            "status": "candidate",
            "source_version_id": f"version-{len(self.submitted)}",
            "source_version_status": "candidate",
        })()


class FakeBuildRuntime:
    def handle_source_version(self, *, source_version_id, job_id, url, tenant_id):
        return {
            "agent_run_id": f"run-{source_version_id}",
            "source_version_id": source_version_id,
            "decision": "canary",
            "strategy": "deterministic_patch",
            "review_required": False,
            "source_rule": {
                "bookSourceName": url,
                "bookSourceUrl": url,
                "searchUrl": url,
                "ruleSearch": {"bookList": ".item", "name": "a@text", "bookUrl": "a@href"},
                "ruleToc": {"chapterList": "#list a", "chapterName": "text", "chapterUrl": "href"},
                "ruleContent": {"content": "#content@text"},
            },
            "autonomous_build": {
                "decision": "canary",
                "strategy": "deterministic_patch",
                "probe": {"search_status": "ok", "toc_status": "ok", "content_status": "ok"},
            },
        }


@pytest.mark.asyncio
async def test_acceptance_submits_all_urls_to_source_build_engine():
    from app.application.services.source_to_insight_acceptance_service import (
        SourceToInsightAcceptanceService,
    )

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
    )
    report = await service.run({
        "source_urls": ["https://a.test/list", "https://b.test/rank/"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
        "tenant_id": "operator",
    })

    assert report["status"] in {"passed", "partial"}
    assert [item["url"] for item in report["source_builds"]] == ["https://a.test/list", "https://b.test/rank/"]
    assert report["source_builds"][0]["job_id"] == "job-1"
    assert report["source_builds"][0]["agent_run_id"] == "run-version-1"
    assert report["source_builds"][0]["decision"] == "canary"
    assert report["source_builds"][0]["source_rule"]["ruleSearch"]["bookList"] == ".item"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_submits_all_urls_to_source_build_engine -q
```

Expected: FAIL because `source_to_insight_acceptance_service.py` does not exist.

- [ ] **Step 3: Implement the acceptance service skeleton**

Create `backend/app/application/services/source_to_insight_acceptance_service.py`:

```python
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
    ):
        self._source_build_service = source_build_service
        self._source_build_runtime = source_build_runtime
        self._reading_service = reading_service
        self._complement_service = complement_service
        self._character_service = character_service
        self._knowledge_service = knowledge_service
        self._provider_platform = provider_platform

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
                if hasattr(self._source_build_runtime, "handle_source_version"):
                    runtime_result = self._source_build_runtime.handle_source_version(
                        source_version_id=submission.source_version_id,
                        job_id=submission.job_id,
                        url=submission.normalized_url,
                        tenant_id=tenant_id,
                    )
                else:
                    runtime_result = {}
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
```

- [ ] **Step 4: Run the test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_submits_all_urls_to_source_build_engine -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/tests/test_source_to_insight_acceptance_service.py
git commit -m "feat: add source build engine acceptance skeleton"
```

## Task 2: Wire real SourceBuildRuntimeService through existing job objects

**Files:**
- Modify: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Test: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Add a test for job-backed runtime execution**

Append:

```python
class FakeJobRuntime:
    def __init__(self):
        self.seen = []

    def handle_job(self, job):
        self.seen.append(job)
        return {
            "agent_run_id": "run-real",
            "source_version_id": job.payload["source_version_id"],
            "decision": "canary",
            "strategy": "deterministic_patch",
            "review_required": False,
        }


class FakeJobRepository:
    def __init__(self):
        self.jobs = {}

    def get_job(self, job_id):
        return self.jobs[job_id]


@pytest.mark.asyncio
async def test_acceptance_can_execute_runtime_with_job_repository():
    from app.application.services.source_to_insight_acceptance_service import (
        SourceToInsightAcceptanceService,
    )
    from app.domain.entities.job import Job

    job_repo = FakeJobRepository()
    runtime = FakeJobRuntime()
    build = FakeSourceBuildService()
    job_repo.jobs["job-1"] = Job(
        id="job-1",
        kind="source.build",
        tenant_id="operator",
        payload={"url": "https://a.test", "source_version_id": "version-1"},
        status="queued",
    )
    service = SourceToInsightAcceptanceService(
        source_build_service=build,
        source_build_runtime=runtime,
        job_repository=job_repo,
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "tenant_id": "operator",
    })

    assert report["source_builds"][0]["agent_run_id"] == "run-real"
    assert runtime.seen[0].id == "job-1"
```

- [ ] **Step 2: Run the new test to confirm it fails**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py -q
```

Expected: FAIL because the service does not accept `job_repository` and does not call `handle_job()`.

- [ ] **Step 3: Implement job-backed runtime execution**

Update constructor:

```python
        job_repository=None,
```

Store:

```python
        self._job_repository = job_repository
```

Replace the runtime branch in `_run_source_build()` with:

```python
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
```

- [ ] **Step 4: Run tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/tests/test_source_to_insight_acceptance_service.py
git commit -m "feat: execute source build runtime in acceptance smoke"
```

## Task 3: Add reading/complement/insight verification from generated candidates

**Files:**
- Modify: `backend/app/application/services/source_to_insight_acceptance_service.py`
- Test: `backend/tests/test_source_to_insight_acceptance_service.py`

- [ ] **Step 1: Add a test that verifies reading is run only for usable engine output**

Append:

```python
class FakeReadingService:
    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None, routing_mode="auto", include_health=False):
        return {
            "items": [{
                "source_id": 1,
                "name": keyword,
                "author": author_hint,
                "bookUrl": "https://a.test/book/1",
                "sourceName": "Engine Source",
                "sourceUrl": "https://a.test",
            }],
            "route_summary": {"selected_source_ids": [1]},
        }

    async def get_book_toc(self, source_id, book_url, book_name=None, author_hint=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "book_url": book_url,
            "chapters": [{"title": "第一章", "url": "https://a.test/book/1/1", "index": 0}],
            "fallback_used": False,
        }

    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "chapter_url": chapter_url,
            "title": "第一章",
            "content": "唐三来到斗罗大陆，武魂觉醒的世界规则逐渐展开。",
            "fallback_used": False,
        }


class FakeComplementService:
    async def complement_chapter_candidates(self, **kwargs):
        return {
            "book_name": kwargs["book_name"],
            "status": "success",
            "successful_sources": 1,
            "failed_sources": 0,
            "final_content": "唐三来到斗罗大陆，武魂觉醒的世界规则逐渐展开。",
            "source_results": [],
            "merged_from": ["https://a.test"],
        }

    async def aclose(self):
        return None


class FakeCharacterService:
    async def calibrate(self, keyword, items, actor_id="system"):
        return {
            "keyword": keyword,
            "items": [{"characters": ["唐三", "斗罗"]}],
            "pairwise": [],
            "used_provider": False,
            "provider_result": None,
        }


@pytest.mark.asyncio
async def test_acceptance_reads_and_complements_after_canary_source_build():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        reading_service=FakeReadingService(),
        complement_service=FakeComplementService(),
        character_service=FakeCharacterService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
        "chapter_index": 0,
    })

    assert report["book_candidates"][0]["name"] == "斗罗大陆"
    assert report["toc_candidates"][0]["chapters"][0]["title"] == "第一章"
    assert report["chapter_candidates"][0]["content_preview"].startswith("唐三")
    assert report["complement"]["status"] == "success"
    assert report["insights"]["characters"]
```

- [ ] **Step 2: Run failing test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py::test_acceptance_reads_and_complements_after_canary_source_build -q
```

Expected: FAIL because reading/complement are not implemented.

- [ ] **Step 3: Implement reading and complement steps**

In `run()`, after source build:

```python
        usable_builds = [
            item for item in source_builds
            if item.get("status") == "passed" and item.get("decision") in {"canary", None}
        ]
        book_candidates = []
        toc_candidates = []
        chapter_candidates = []
        complement = {}
        insights = {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []}

        if self._reading_service is not None and usable_builds:
            search_result = await self._reading_service.search_books(
                book_name,
                source_ids=None,
                limit_per_source=3,
                author_hint=author_hint,
                routing_mode="auto",
                include_health=True,
            )
            book_candidates = search_result.get("items", [])
            selected = book_candidates[: min(3, len(book_candidates))]
            for book in selected:
                toc = await self._reading_service.get_book_toc(
                    book["source_id"],
                    book["bookUrl"],
                    book_name=book_name,
                    author_hint=author_hint,
                    routing_mode="auto",
                )
                toc_candidates.append(toc)
                chapters = toc.get("chapters") or []
                if not chapters:
                    continue
                chapter = _select_chapter(
                    chapters,
                    int(scenario.get("chapter_index", 0) or 0),
                    str(scenario.get("chapter_title") or ""),
                )
                content = await self._reading_service.get_chapter_content(
                    book["source_id"],
                    chapter["url"],
                    book_name=book_name,
                    author_hint=author_hint,
                    chapter_title=chapter.get("title"),
                    chapter_index=chapter.get("index"),
                    routing_mode="auto",
                )
                chapter_candidates.append({
                    **content,
                    "content_preview": _preview(content.get("content", "")),
                    "content_length": len(content.get("content", "") or ""),
                })
```

Implement helpers:

```python
def _select_chapter(chapters: list[dict[str, Any]], chapter_index: int, chapter_title: str) -> dict[str, Any]:
    for item in chapters:
        if int(item.get("index", -1)) == chapter_index:
            return item
    if chapter_title:
        for item in chapters:
            if chapter_title in str(item.get("title", "")):
                return item
    return chapters[0]


def _preview(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    return text[:limit]
```

After chapter candidates:

```python
        if self._complement_service is not None and chapter_candidates:
            items = [
                {
                    "source_id": item["source_id"],
                    "chapter_url": item["chapter_url"],
                    "source_name": "",
                    "source_url": "",
                }
                for item in chapter_candidates
            ]
            try:
                complement = await self._complement_service.complement_chapter_candidates(
                    book_name=book_name,
                    chapter_title=chapter_candidates[0].get("title") or str(scenario.get("chapter_title") or ""),
                    chapter_num=int(scenario.get("chapter_index", 0) or 0) + 1,
                    items=items,
                    reference_content=chapter_candidates[0].get("content", ""),
                    merge_strategy="hybrid",
                )
            finally:
                close = getattr(self._complement_service, "aclose", None)
                if close:
                    await close()

        if self._character_service is not None:
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
                ],
                actor_id=tenant_id,
            )
            insights["characters"] = character_result.get("items", [])
```

Return these real fields instead of empty lists.

- [ ] **Step 4: Run acceptance service tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_source_to_insight_acceptance_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/app/application/services/source_to_insight_acceptance_service.py backend/tests/test_source_to_insight_acceptance_service.py
git commit -m "feat: verify reading path from source build candidates"
```

## Task 4: Add smoke CLI with fixture and real-source modes

**Files:**
- Create: `backend/scripts/smoke_source_to_insight.py`
- Test: `backend/tests/test_smoke_source_to_insight.py`

- [ ] **Step 1: Write CLI contract test**

Create `backend/tests/test_smoke_source_to_insight.py`:

```python
import json


def test_smoke_cli_writes_report_with_fixture_service(tmp_path, monkeypatch):
    from scripts import smoke_source_to_insight

    report_path = tmp_path / "report.json"

    class FakeService:
        async def run(self, scenario):
            return {
                "scenario": scenario,
                "status": "passed",
                "steps": [],
                "source_builds": [{"url": "https://a.test", "status": "passed"}],
                "book_candidates": [],
                "toc_candidates": [],
                "chapter_candidates": [],
                "complement": {},
                "insights": {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []},
                "knowledge_proposals": [],
                "ai": {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}},
            }

    monkeypatch.setattr(smoke_source_to_insight, "build_acceptance_service", lambda: FakeService())
    exit_code = smoke_source_to_insight.main([
        "--fixture-mode",
        "--output",
        str(report_path),
        "--book-name",
        "斗罗大陆",
        "--source-url",
        "https://a.test",
    ])

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["source_builds"][0]["url"] == "https://a.test"
```

- [ ] **Step 2: Run failing CLI test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_smoke_source_to_insight.py -q
```

Expected: FAIL because script does not exist.

- [ ] **Step 3: Implement CLI**

Create `backend/scripts/smoke_source_to_insight.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


DEFAULT_SOURCE_URLS = [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/",
]


def build_acceptance_service():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService
    from app.infrastructure.persistence.factory import (
        build_job_repository,
        build_source_build_runtime_service,
        build_source_build_service,
        build_source_complement_service,
        build_source_read_service,
        build_character_calibration_service,
        build_work_knowledge_service,
        build_provider_platform_service,
    )

    return SourceToInsightAcceptanceService(
        source_build_service=build_source_build_service(),
        source_build_runtime=build_source_build_runtime_service(),
        job_repository=build_job_repository(),
        reading_service=build_source_read_service(),
        complement_service=build_source_complement_service(),
        character_service=build_character_calibration_service(),
        knowledge_service=build_work_knowledge_service(),
        provider_platform=build_provider_platform_service(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run source-build-engine to insight acceptance smoke.")
    parser.add_argument("--fixture-mode", action="store_true", help="Use caller-provided fake service in tests; production still builds normal service.")
    parser.add_argument("--real-source-mode", action="store_true", help="Run against the default real source URLs.")
    parser.add_argument("--source-url", action="append", default=[], help="Source URL to submit to source.build. May be repeated.")
    parser.add_argument("--book-name", default="斗罗大陆")
    parser.add_argument("--author-hint", default="唐家三少")
    parser.add_argument("--chapter-index", type=int, default=0)
    parser.add_argument("--chapter-title", default="第一章")
    parser.add_argument("--use-ai", action="store_true")
    parser.add_argument("--tenant-id", default="source-insight-smoke")
    parser.add_argument("--output", default="backend/reports/source-to-insight-smoke.json")
    args = parser.parse_args(argv)

    source_urls = args.source_url or (DEFAULT_SOURCE_URLS if args.real_source_mode else DEFAULT_SOURCE_URLS[:1])
    scenario = {
        "source_urls": source_urls,
        "book_name": args.book_name,
        "author_hint": args.author_hint,
        "chapter_index": args.chapter_index,
        "chapter_title": args.chapter_title,
        "use_ai": args.use_ai,
        "tenant_id": args.tenant_id,
    }
    report = asyncio.run(build_acceptance_service().run(scenario))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report.get("status") in {"passed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3b: Add the job repository factory used by the script**

Modify `backend/app/infrastructure/persistence/factory.py` next to `build_job_service()`:

```python
def build_job_repository() -> SQLiteJobRepository:
    bootstrap_sqlite()
    return SQLiteJobRepository()
```

- [ ] **Step 4: Run CLI test**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest tests/test_smoke_source_to_insight.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/scripts/smoke_source_to_insight.py backend/tests/test_smoke_source_to_insight.py backend/app/infrastructure/persistence/factory.py
git commit -m "feat: add source insight smoke runner"
```

## Task 5: Real-site dry run and focused regressions

**Files:**
- No planned source edits unless tests expose an implementation gap.
- Report output: `backend/reports/source-to-insight-real-sites.json` (do not commit unless requested).

- [ ] **Step 1: Install local test dependencies if needed**

If the Linux temp venv is missing dependencies:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pip install -r backend/requirements.txt aiosqlite jieba
npm ci --prefix backend/nodejs
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
/tmp/legado-hub-pytest-venv/bin/python -m pytest \
  tests/test_source_to_insight_acceptance_service.py \
  tests/test_smoke_source_to_insight.py \
  tests/test_source_build_runtime_service.py \
  tests/test_source_read_service.py \
  tests/test_source_complement_app_service.py \
  tests/test_character_calibration_service.py \
  tests/test_work_knowledge_service.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run real-source smoke without AI**

Run from `backend/`:

```bash
/tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py \
  --real-source-mode \
  --book-name "斗罗大陆" \
  --author-hint "唐家三少" \
  --chapter-index 0 \
  --chapter-title "第一章" \
  --output backend/reports/source-to-insight-real-sites.json
```

Expected:

- The report contains all four submitted URLs.
- Each URL has `status` either `passed` or `failed` with a concrete error.
- At least one URL reaches source-build runtime result with `decision`, `agent_run_id`, or `autonomous_build`.
- Reading/complement sections run only when a generated candidate is usable.

- [ ] **Step 4: Inspect report for source-build engine capability**

Open:

```bash
sed -n '1,260p' backend/reports/source-to-insight-real-sites.json
```

Record in final response:

- Which URLs were reachable.
- Which URLs the source-build engine converted into candidate rules.
- Which candidate rules reached search/toc/content.
- Which step blocked each failed URL.

- [ ] **Step 5: Optional AI run after credentials are provided**

After the operator provides provider credentials:

```bash
/tmp/legado-hub-pytest-venv/bin/python scripts/smoke_source_to_insight.py \
  --real-source-mode \
  --use-ai \
  --book-name "斗罗大陆" \
  --author-hint "唐家三少" \
  --output backend/reports/source-to-insight-real-sites-ai.json
```

Expected:

- Source build/search/toc/content/complement still run deterministically.
- Provider usage is recorded only under `ai`.
- AI failure does not erase deterministic evidence.

- [ ] **Step 6: Commit implementation only**

Do not commit `backend/reports/*.json` unless explicitly requested.

```bash
git status --short
git add backend/app/application/services/source_to_insight_acceptance_service.py \
  backend/scripts/smoke_source_to_insight.py \
  backend/tests/test_source_to_insight_acceptance_service.py \
  backend/tests/test_smoke_source_to_insight.py \
  backend/app/infrastructure/persistence/factory.py
git commit -m "feat: smoke test source build engine against real sites"
```

## Self-Review Notes

- This plan covers the updated spec requirement that the four real URLs go through the existing source-writing engine first.
- It avoids hand-authored final source rules.
- It keeps AI optional and isolated to the analysis node.
- It does not stage line-ending drift, the large local source fixture movement, or generated reports.

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

    build_service = FakeSourceBuildService()
    service = SourceToInsightAcceptanceService(
        source_build_service=build_service,
        source_build_runtime=FakeBuildRuntime(),
    )
    report = await service.run({
        "source_urls": ["https://a.test/list", "https://b.test/rank/"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
        "tenant_id": "operator",
    })

    assert report["status"] == "failed"
    assert next(step for step in report["steps"] if step["name"] == "source_build")["status"] == "passed"
    assert build_service.submitted == [
        {"tenant_id": "operator", "url": "https://a.test/list", "keyword": "斗罗大陆"},
        {"tenant_id": "operator", "url": "https://b.test/rank/", "keyword": "斗罗大陆"},
    ]
    assert [item["url"] for item in report["source_builds"]] == ["https://a.test/list", "https://b.test/rank/"]
    assert report["source_builds"][0]["job_id"] == "job-1"
    assert report["source_builds"][0]["agent_run_id"] == "run-version-1"
    assert report["source_builds"][0]["decision"] == "canary"
    assert report["source_builds"][0]["source_rule"]["ruleSearch"]["bookList"] == ".item"


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

    def get(self, job_id):
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


class FakeGeneratedSourceRepository:
    def __init__(self):
        self.upserted = []

    async def upsert_book_sources(self, items, actor_id):
        self.upserted.extend(items)
        return len(items)

    async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
        return [
            {
                **item,
                "id": index + 101,
                "enabled": True,
            }
            for index, item in enumerate(self.upserted)
            if not urls or item.get("bookSourceUrl") in urls
        ]


class FakeReadingService:
    def __init__(self):
        self.search_source_ids = []

    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None, routing_mode="auto", include_health=False):
        self.search_source_ids.append(source_ids)
        return {
            "items": [{
                "source_id": source_ids[0],
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
    def __init__(self):
        self.calls = []

    async def calibrate(self, keyword, items, actor_id="system"):
        self.calls.append({"keyword": keyword, "items": items, "actor_id": actor_id})
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

    reading_service = FakeReadingService()
    generated_sources = FakeGeneratedSourceRepository()
    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=generated_sources,
        reading_service=reading_service,
        complement_service=FakeComplementService(),
        character_service=FakeCharacterService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
        "chapter_index": 0,
        "use_ai": True,
    })

    assert report["book_candidates"][0]["name"] == "斗罗大陆"
    assert reading_service.search_source_ids == [[101]]
    assert generated_sources.upserted[0]["bookSourceUrl"] == "https://a.test"
    assert report["toc_candidates"][0]["chapters"][0]["title"] == "第一章"
    assert report["chapter_candidates"][0]["content_preview"].startswith("唐三")
    assert report["complement"]["status"] == "success"
    assert report["insights"]["characters"]


class FakeTwoCanaryBuildRuntime:
    def handle_source_version(self, *, source_version_id, job_id, url, tenant_id):
        return {
            "agent_run_id": f"run-{source_version_id}",
            "decision": "canary",
            "strategy": "deterministic_patch",
            "review_required": False,
            "source_rule": {
                "bookSourceName": url,
                "bookSourceUrl": url,
                "ruleSearch": {"bookList": ".item"},
                "ruleToc": {"chapterList": "#list a"},
                "ruleContent": {"content": "#content@text"},
            },
        }


class FakePerSourceReadingService:
    def __init__(self, *, empty_content_source_ids=None):
        self.search_source_ids = []
        self.empty_content_source_ids = set(empty_content_source_ids or [])

    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None, routing_mode="auto", include_health=False):
        self.search_source_ids.append(list(source_ids or []))
        source_id = source_ids[0]
        return {
            "items": [{
                "source_id": source_id,
                "name": keyword,
                "author": author_hint,
                "bookUrl": f"https://source-{source_id}.test/book/1",
                "sourceName": f"Source {source_id}",
                "sourceUrl": f"https://source-{source_id}.test",
            }],
            "route_summary": {"selected_source_ids": [source_id]},
        }

    async def get_book_toc(self, source_id, book_url, book_name=None, author_hint=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "book_url": book_url,
            "chapters": [{"title": "第一章", "url": f"{book_url}/1", "index": 0}],
            "fallback_used": False,
        }

    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        content = "" if source_id in self.empty_content_source_ids else f"{source_id} 唐三来到斗罗大陆。"
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "chapter_url": chapter_url,
            "title": "第一章",
            "content": content,
            "fallback_used": False,
        }


class FakeNoRuleJobRuntime:
    def handle_job(self, job):
        return {
            "agent_run_id": "run-real",
            "source_version_id": job.payload["source_version_id"],
            "decision": "canary",
            "strategy": "deterministic_patch",
            "review_required": False,
        }


class FakeSourceRuntimeRepository:
    def __init__(self):
        self.payloads = {}
        self.requested = []

    def get_version(self, version_id):
        self.requested.append(version_id)
        payload = self.payloads.get(version_id)
        if payload is None:
            return None
        return type("SourceVersion", (), {"payload": payload})()


class ExplodingCharacterService:
    async def calibrate(self, *args, **kwargs):
        raise AssertionError("character calibration should be skipped unless use_ai=True")


class FailingTocReadingService(FakePerSourceReadingService):
    async def get_book_toc(self, source_id, book_url, book_name=None, author_hint=None, routing_mode="auto"):
        raise RuntimeError("toc exploded")


class FallbackSensitiveReadingService(FakePerSourceReadingService):
    def __init__(self):
        super().__init__()
        self.toc_calls = []
        self.content_calls = []

    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None, routing_mode="auto", include_health=False):
        self.search_source_ids.append(list(source_ids or []))
        expected_source_id = source_ids[0]
        return {
            "items": [
                {
                    "source_id": 999,
                    "name": keyword,
                    "author": author_hint,
                    "bookUrl": "https://wrong.test/book/1",
                    "sourceName": "Wrong Source",
                    "sourceUrl": "https://wrong.test",
                },
                {
                    "source_id": expected_source_id,
                    "name": keyword,
                    "author": author_hint,
                    "bookUrl": "https://a.test/book/1",
                    "sourceName": "Expected Source",
                    "sourceUrl": "https://a.test",
                },
            ],
            "route_summary": {"selected_source_ids": [expected_source_id]},
        }

    async def get_book_toc(self, source_id, book_url, book_name=None, author_hint=None, routing_mode="auto"):
        self.toc_calls.append({
            "source_id": source_id,
            "book_name": book_name,
            "author_hint": author_hint,
        })
        if source_id != 101 or book_name is not None or author_hint is not None:
            raise RuntimeError("fallback-sensitive toc call used wrong source or fallback hints")
        return await super().get_book_toc(source_id, book_url, book_name=book_name, author_hint=author_hint, routing_mode=routing_mode)

    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        self.content_calls.append({
            "source_id": source_id,
            "book_name": book_name,
            "author_hint": author_hint,
        })
        if source_id != 101 or book_name is not None or author_hint is not None:
            raise RuntimeError("fallback-sensitive content call used wrong source or fallback hints")
        return await super().get_chapter_content(
            source_id,
            chapter_url,
            book_name=book_name,
            author_hint=author_hint,
            chapter_title=chapter_title,
            chapter_index=chapter_index,
            routing_mode=routing_mode,
        )


class MalformedContentReadingService(FakePerSourceReadingService):
    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "title": "第一章",
            "content": "唐三来到斗罗大陆。",
            "fallback_used": False,
        }


class FallbackContentReadingService(FakePerSourceReadingService):
    async def get_chapter_content(self, source_id, chapter_url, book_name=None, author_hint=None, chapter_title=None, chapter_index=None, routing_mode="auto"):
        return {
            "source_id": source_id,
            "resolved_source_id": 202,
            "chapter_url": "https://other.test/book/1/1",
            "title": "第一章",
            "content": "这是其它书源 fallback 回来的正文，不能算作当前书源验证成功。",
            "fallback_used": True,
        }


class ReferenceCheckingComplementService:
    async def complement_chapter_candidates(self, **kwargs):
        if not kwargs["reference_content"].startswith("102 "):
            raise RuntimeError("reference content did not use first content-bearing candidate")
        return {
            "book_name": kwargs["book_name"],
            "status": "success",
            "successful_sources": len(kwargs["items"]),
            "failed_sources": 0,
            "final_content": kwargs["reference_content"],
            "source_results": [],
            "merged_from": [],
        }

    async def aclose(self):
        return None


class PartiallyFailingGeneratedSourceRepository(FakeGeneratedSourceRepository):
    async def upsert_book_sources(self, items, actor_id):
        item = items[0]
        if item.get("bookSourceUrl") == "https://b.test":
            raise RuntimeError("repository rejected b.test")
        self.upserted.append(item)
        return 1


@pytest.mark.asyncio
async def test_acceptance_reads_each_generated_canary_source_independently_and_marks_partial_content():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    reading_service = FakePerSourceReadingService(empty_content_source_ids={102})
    generated_sources = FakeGeneratedSourceRepository()
    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeTwoCanaryBuildRuntime(),
        source_repository=generated_sources,
        reading_service=reading_service,
        complement_service=FakeComplementService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test", "https://b.test"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
        "chapter_index": 0,
    })

    assert reading_service.search_source_ids == [[101], [102]]
    assert report["status"] == "partial"
    assert report["source_builds"][0]["generated_source_id"] == 101
    assert report["source_builds"][0]["reading"]["status"] == "passed"
    assert report["source_builds"][1]["generated_source_id"] == 102
    assert report["source_builds"][1]["reading"]["status"] == "failed"
    assert any(step["name"] == "reading" and step["status"] == "partial" for step in report["steps"])


@pytest.mark.asyncio
async def test_acceptance_prevents_read_service_fallback_during_per_source_verification():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    reading_service = FallbackSensitiveReadingService()
    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=reading_service,
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "author_hint": "唐家三少",
    })

    assert report["status"] == "passed"
    assert reading_service.toc_calls == [{"source_id": 101, "book_name": None, "author_hint": None}]
    assert reading_service.content_calls == [{"source_id": 101, "book_name": None, "author_hint": None}]


@pytest.mark.asyncio
async def test_acceptance_retrieves_persisted_source_rule_after_handle_job():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService
    from app.domain.entities.job import Job

    job_repo = FakeJobRepository()
    runtime_repo = FakeSourceRuntimeRepository()
    generated_sources = FakeGeneratedSourceRepository()
    job_repo.jobs["job-1"] = Job(
        id="job-1",
        kind="source.build",
        tenant_id="operator",
        payload={"url": "https://a.test", "source_version_id": "version-1"},
        status="queued",
    )
    runtime_repo.payloads["version-1"] = {
        "source_rule": {
            "bookSourceName": "Persisted Source",
            "bookSourceUrl": "https://persisted.test",
            "ruleSearch": {"bookList": ".item"},
            "ruleToc": {"chapterList": "#list a"},
            "ruleContent": {"content": "#content@text"},
        }
    }
    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeNoRuleJobRuntime(),
        job_repository=job_repo,
        source_runtime_repository=runtime_repo,
        source_repository=generated_sources,
        reading_service=FakePerSourceReadingService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "tenant_id": "operator",
    })

    assert runtime_repo.requested == ["version-1"]
    assert report["source_builds"][0]["source_rule"]["bookSourceUrl"] == "https://persisted.test"
    assert generated_sources.upserted[0]["bookSourceUrl"] == "https://persisted.test"


@pytest.mark.asyncio
async def test_acceptance_skips_character_calibration_by_default():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=FakePerSourceReadingService(),
        character_service=ExplodingCharacterService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })

    assert report["ai"]["status"] == "skipped"
    assert report["insights"]["characters"] == []
    assert any(step["name"] == "insights" and step["status"] == "skipped" for step in report["steps"])


@pytest.mark.asyncio
async def test_acceptance_reports_downstream_reading_failure_without_raising():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=FailingTocReadingService(),
        complement_service=FakeComplementService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })

    assert report["status"] == "failed"
    assert report["source_builds"][0]["reading"]["status"] == "failed"
    assert "toc exploded" in report["source_builds"][0]["reading"]["error"]
    assert any(
        step["name"] == "reading"
        and step["status"] == "failed"
        and step["errors"]
        for step in report["steps"]
    )


@pytest.mark.asyncio
async def test_acceptance_reports_malformed_complement_candidate_without_raising():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=MalformedContentReadingService(),
        complement_service=FakeComplementService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })

    complement_step = next(step for step in report["steps"] if step["name"] == "complement")
    assert report["status"] == "passed"
    assert complement_step["status"] == "failed"
    assert complement_step["errors"]
    assert report["complement"]["status"] == "failed"


@pytest.mark.asyncio
async def test_acceptance_complement_uses_first_content_bearing_candidate_as_reference():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeTwoCanaryBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=FakePerSourceReadingService(empty_content_source_ids={101}),
        complement_service=ReferenceCheckingComplementService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test", "https://b.test"],
        "book_name": "斗罗大陆",
    })

    assert report["status"] == "partial"
    assert report["complement"]["status"] == "success"


@pytest.mark.asyncio
async def test_acceptance_materializes_canary_rules_independently_when_one_repo_upsert_fails():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    reading_service = FakePerSourceReadingService()
    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeTwoCanaryBuildRuntime(),
        source_repository=PartiallyFailingGeneratedSourceRepository(),
        reading_service=reading_service,
    )

    report = await service.run({
        "source_urls": ["https://a.test", "https://b.test"],
        "book_name": "斗罗大陆",
    })

    assert reading_service.search_source_ids == [[101]]
    assert report["status"] == "partial"
    assert report["source_builds"][0]["materialization"]["status"] == "passed"
    assert report["source_builds"][1]["materialization"]["status"] == "failed"
    assert "repository rejected b.test" in report["source_builds"][1]["materialization"]["error"]
    assert any(step["name"] == "source_materialization" and step["status"] == "partial" for step in report["steps"])


@pytest.mark.asyncio
async def test_acceptance_rejects_fallback_or_mismatched_content_evidence():
    from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService

    service = SourceToInsightAcceptanceService(
        source_build_service=FakeSourceBuildService(),
        source_build_runtime=FakeBuildRuntime(),
        source_repository=FakeGeneratedSourceRepository(),
        reading_service=FallbackContentReadingService(),
    )

    report = await service.run({
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })

    assert report["status"] == "failed"
    assert report["source_builds"][0]["reading"]["status"] == "failed"
    assert "fallback" in report["source_builds"][0]["reading"]["error"]

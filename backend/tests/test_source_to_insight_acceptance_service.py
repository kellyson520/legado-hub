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

    assert report["status"] == "passed"
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

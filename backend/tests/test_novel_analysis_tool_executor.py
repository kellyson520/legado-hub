import pytest

from tests.test_work_ingestion_service import ingestion_service


@pytest.fixture
def executor(ingestion_service):
    from app.application.services.novel_analysis_tool_executor import NovelAnalysisToolExecutor
    from app.infrastructure.persistence.factory import build_agent_runtime_service, build_evidence_service

    return NovelAnalysisToolExecutor(
        ingestion_service=ingestion_service,
        evidence_service=build_evidence_service(),
        agent_runtime=build_agent_runtime_service(),
    )


@pytest.mark.asyncio
async def test_chapter_fetch_tool_records_evidence_and_limits_preview(executor):
    result = await executor.ainvoke("chapter.fetch", {
        "tenant_id": "tenant-1",
        "source_id": 7,
        "book_url": "https://source.test/book/1",
        "chapter_index": 0,
        "book_name": "测试书",
    })

    assert result.status == "accepted"
    assert result.data["evidence_span_ids"]
    assert len(result.data["content_preview"]) <= 1200


@pytest.mark.asyncio
async def test_knowledge_read_tools_follow_search_toc_chapter_and_evidence_boundaries(executor):
    search = await executor.ainvoke("source.search", {"tenant_id": "tenant-1", "keyword": "测试书"})
    toc = await executor.ainvoke("toc.get", {
        "tenant_id": "tenant-1",
        "source_id": 7,
        "book_url": "https://source.test/book/1",
        "book_name": "测试书",
    })
    chapter = await executor.ainvoke("chapter.fetch", {
        "tenant_id": "tenant-1",
        "source_id": 7,
        "book_url": "https://source.test/book/1",
        "chapter_index": 0,
        "book_name": "测试书",
    })
    evidence = await executor.ainvoke("evidence.get", {
        "tenant_id": "tenant-1",
        "evidence_id": chapter.data["evidence_span_ids"][0],
    })

    assert search.data["items"][0]["book_url"] == "https://source.test/book/1"
    assert toc.data["chapters"] == [{"index": 0, "title": "第一章 入世"}]
    assert "content_preview" not in evidence.data
    assert evidence.data["excerpt"]


def test_factory_binds_all_novel_analysis_handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-analysis-tools.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.factory import build_novel_analysis_tool_registry

    registry = build_novel_analysis_tool_registry()

    assert registry.get("chapter.fetch").handler is not None
    assert registry.get("evidence.get").handler is not None


@pytest.mark.asyncio
async def test_changed_chapter_variant_queues_only_its_linked_claims_for_reaudit(ingestion_service):
    from app.application.services.novel_analysis_tool_executor import NovelAnalysisToolExecutor
    from app.infrastructure.persistence.factory import (
        build_agent_runtime_service,
        build_evidence_service,
        build_narrative_knowledge_service,
        build_novel_analysis_audit_service,
        build_novel_analysis_task_service,
    )

    class Settings:
        def get_section(self, _domain, tab):
            values = {
                "automation": {"background_incremental_enabled": True},
                "budgets": {"max_tokens_per_task": 3000},
            }
            return {"value": values[tab]}

    executor = NovelAnalysisToolExecutor(
        ingestion_service=ingestion_service,
        evidence_service=build_evidence_service(),
        agent_runtime=build_agent_runtime_service(),
        audit_service=build_novel_analysis_audit_service(),
        settings_service=Settings(),
    )
    first = await executor.ainvoke("chapter.fetch", {
        "tenant_id": "tenant-1", "source_id": 7, "book_url": "https://source.test/book/1", "chapter_index": 0, "book_name": "测试书",
    })
    claim = build_narrative_knowledge_service().create_claim(
        first.data["canonical_work_id"], "ningyao", "alive", scalar_value=True, epistemic="explicit", evidence_ids=[first.data["evidence_span_ids"][0]],
    )
    ingestion_service._reader.content = "宁姚在雨中救下少年。"

    second = await executor.ainvoke("chapter.fetch", {
        "tenant_id": "tenant-1", "source_id": 7, "book_url": "https://source.test/book/1", "chapter_index": 0, "book_name": "测试书",
    })

    assert second.data["reaudit_task_ids"]
    tasks = build_novel_analysis_task_service().list_for_work(first.data["canonical_work_id"], tenant_id="tenant-1")
    assert tasks[0].checkpoint["reaudit_claim_ids"] == [claim.id]

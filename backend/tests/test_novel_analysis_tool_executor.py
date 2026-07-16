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

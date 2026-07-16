"""Opt-in acceptance for a user-approved published source and configured provider routes."""

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_PROVIDER_TESTS") != "1",
    reason="requires user-configured provider credentials and an approved healthy published source",
)


@pytest.mark.asyncio
async def test_real_source_to_evidence_to_adjudicated_claim():
    source_id = int(os.environ["REAL_NOVEL_SOURCE_ID"])
    keyword = os.environ.get("REAL_NOVEL_KEYWORD", "剑来")
    chapter_index = int(os.environ.get("REAL_NOVEL_CHAPTER_INDEX", "0"))
    tenant_id = os.environ.get("REAL_NOVEL_TENANT_ID", "real-provider-acceptance")

    from app.infrastructure.persistence.factory import (
        build_novel_analysis_pipeline_service,
        build_novel_analysis_task_service,
        build_work_ingestion_service,
    )

    ingestion = build_work_ingestion_service()
    search = await ingestion.search_sources(keyword=keyword, source_ids=[source_id])
    matches = [
        item for item in search.get("items", [])
        if int(item.get("source_id") or source_id) == source_id and str(item.get("bookUrl") or "").strip()
    ]
    assert matches, "approved source did not return a readable work; inspect source health and runtime rules"
    match = matches[0]
    chapter = await ingestion.fetch_and_ingest_chapter(
        source_id=source_id,
        book_url=str(match["bookUrl"]),
        chapter_index=chapter_index,
        book_name=str(match.get("name") or keyword),
        author_hint=str(match.get("author") or "") or None,
    )
    task = build_novel_analysis_task_service().create_task(
        chapter.canonical_work_id,
        tenant_id,
        "识别本章中有直接证据支持的人物与事件关系",
        selected_evidence_ids=chapter.evidence_span_ids[:8],
    )

    result = await build_novel_analysis_pipeline_service().process_task(task, tenant_id=tenant_id)

    assert chapter.evidence_span_ids
    assert result.claim_ids
    assert result.outcomes
    assert result.token_count > 0

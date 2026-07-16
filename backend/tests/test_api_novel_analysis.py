from fastapi.testclient import TestClient


def build_client_with_analysis(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-analysis-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import (
        build_canonical_content_repository,
        build_evidence_service,
        build_narrative_knowledge_service,
    )
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    canonical = build_canonical_content_repository()
    work = canonical.create_canonical_work(title="测试书", author="作者")
    chapter = canonical.add_canonical_chapter(canonical_work_id=work.id, chapter_index=0, title="第一章")
    source_work = canonical.create_source_work(canonical_work_id=work.id, source_id="7", title="测试书", author="作者")
    source_chapter = canonical.add_source_chapter(
        source_work_id=source_work.id,
        canonical_chapter_id=chapter.id,
        chapter_index=0,
        title="第一章",
        chapter_url="https://source.test/book/1",
    )
    variant = canonical.add_content_variant(
        canonical_chapter_id=chapter.id,
        source_chapter_id=source_chapter.id,
        source_id="7",
        content="宁姚在雨中救下少年。",
        health_status="healthy",
        quality_score=1,
        coverage_score=1,
        freshness_score=1,
        latency_ms=0,
        is_verified=True,
    )
    evidence = build_evidence_service()
    span = evidence.create_spans(
        content_variant_id=variant.id,
        canonical_chapter_id=chapter.id,
        content=variant.content,
        max_chars=100,
    )[0]
    knowledge = build_narrative_knowledge_service()
    published = knowledge.create_claim(
        work.id,
        "ningyao",
        "alive",
        scalar_value=True,
        epistemic="explicit",
        evidence_ids=[span.id],
    )
    knowledge.publish_claim(published.id, actor_id="reviewer")
    candidate = knowledge.create_claim(
        work.id,
        "ningyao",
        "alive",
        scalar_value=False,
        epistemic="explicit",
        evidence_ids=[span.id],
    )
    knowledge.detect_conflicts(candidate.id)

    token = create_access_token({"sub": "1", "permissions": ["novel.manage"], "sid": "novel-analysis-api"})
    return TestClient(app), {"Authorization": f"Bearer {token}"}, work.id, span.id


def test_snapshot_returns_published_claims_and_open_conflicts(monkeypatch, tmp_path):
    client, headers, work_id, _ = build_client_with_analysis(monkeypatch, tmp_path)

    response = client.get(f"/api/novel-analysis/works/{work_id}/snapshot?chapter_limit=8", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["published_claims"]
    assert response.json()["data"]["candidate_claims"]
    assert response.json()["data"]["open_conflicts"]


def test_evidence_read_returns_excerpt_and_provenance(monkeypatch, tmp_path):
    client, headers, _, span_id = build_client_with_analysis(monkeypatch, tmp_path)

    response = client.get(f"/api/novel-analysis/evidence/{span_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["excerpt"]
    assert response.json()["data"]["content_sha256"]

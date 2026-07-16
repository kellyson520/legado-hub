import pytest


@pytest.fixture
def service_and_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "narrative-knowledge.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.evidence_service import EvidenceService
    from app.application.services.narrative_knowledge_service import NarrativeKnowledgeService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.canonical_content_repo_impl import SQLiteCanonicalContentRepository
    from app.infrastructure.persistence.sqlite.evidence_repo_impl import SQLiteEvidenceRepository
    from app.infrastructure.persistence.sqlite.narrative_knowledge_repo_impl import SQLiteNarrativeKnowledgeRepository

    bootstrap_sqlite()
    canonical = SQLiteCanonicalContentRepository()
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
        content="宁姚在雨中救下少年。宁姚信任少年。",
        health_status="healthy",
        quality_score=1,
        coverage_score=1,
        freshness_score=1,
        latency_ms=0,
        is_verified=True,
    )
    evidence = EvidenceService(SQLiteEvidenceRepository(), canonical)
    spans = evidence.create_spans(
        content_variant_id=variant.id,
        canonical_chapter_id=chapter.id,
        content=variant.content,
        max_chars=8,
    )
    return NarrativeKnowledgeService(SQLiteNarrativeKnowledgeRepository(), evidence), work.id, [span.id for span in spans]


def test_conflict_does_not_overwrite_published_claim(service_and_evidence):
    service, work_id, evidence_ids = service_and_evidence
    published = service.create_claim(
        work_id,
        "entity-a",
        "alive",
        scalar_value=True,
        epistemic="explicit",
        evidence_ids=evidence_ids,
    )
    service.publish_claim(published.id, actor_id="adjudicator")
    candidate = service.create_claim(
        work_id,
        "entity-a",
        "alive",
        scalar_value=False,
        epistemic="explicit",
        evidence_ids=evidence_ids,
    )

    conflict = service.detect_conflicts(candidate.id)

    assert conflict.status == "open"
    assert service.get_claim(published.id).status == "published"
    assert service.get_claim(candidate.id).status == "candidate"


def test_inferred_claim_with_one_span_is_not_publishable(service_and_evidence):
    service, work_id, evidence_ids = service_and_evidence
    claim = service.create_claim(
        work_id,
        "entity-a",
        "trusts",
        object_entity_id="entity-b",
        epistemic="inferred",
        evidence_ids=[evidence_ids[0]],
    )

    assert service.publishability(claim.id).allowed is False

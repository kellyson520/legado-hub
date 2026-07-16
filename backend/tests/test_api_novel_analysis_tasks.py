from fastapi.testclient import TestClient


def build_client_with_analysis(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-analysis-task-work-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import (
        build_canonical_content_repository,
        build_evidence_service,
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
    span = build_evidence_service().create_spans(
        content_variant_id=variant.id,
        canonical_chapter_id=chapter.id,
        content=variant.content,
        max_chars=100,
    )[0]
    token = create_access_token({"sub": "1", "permissions": ["novel.manage"], "sid": "analysis-task-work-api"})
    return TestClient(app), {"Authorization": f"Bearer {token}"}, work.id, span.id


def test_pause_preserves_checkpoint_and_blocks_new_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "novel-analysis-task-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.infrastructure.persistence.factory import build_novel_analysis_task_service
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.main import app

    bootstrap_sqlite()
    task = build_novel_analysis_task_service().create_task("work-1", "1", "分析关系", {"max_tool_calls_per_task": 2})
    token = create_access_token({"sub": "1", "permissions": ["novel.manage"], "sid": "analysis-task-api"})
    client = TestClient(app)

    paused = client.post(f"/api/novel-analysis/tasks/{task.id}/pause", headers={"Authorization": f"Bearer {token}"})

    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"


def test_analysis_task_creation_accepts_only_verified_evidence_from_the_selected_work(monkeypatch, tmp_path):
    client, headers, work_id, evidence_id = build_client_with_analysis(monkeypatch, tmp_path)

    created = client.post(
        f"/api/novel-analysis/works/{work_id}/tasks",
        headers=headers,
        json={"goal": "识别本章人物关系", "evidence_ids": [evidence_id]},
    )
    listed = client.get(f"/api/novel-analysis/works/{work_id}/tasks", headers=headers)

    assert created.status_code == 200
    assert created.json()["data"]["status"] == "queued"
    assert created.json()["data"]["checkpoint"]["selected_evidence_ids"] == [evidence_id]
    assert [task["id"] for task in listed.json()["data"]["items"]] == [created.json()["data"]["id"]]


def test_user_can_run_a_queued_analysis_task_without_enabling_background_automation(monkeypatch, tmp_path):
    client, headers, work_id, evidence_id = build_client_with_analysis(monkeypatch, tmp_path)

    from app.domain.entities.novel_analysis_task import AdjudicationOutcome, TaskProcessingResult
    from app.infrastructure.persistence.factory import build_novel_analysis_task_service

    task = build_novel_analysis_task_service().create_task(
        work_id,
        "1",
        "分析关系",
        selected_evidence_ids=[evidence_id],
    )

    class Settings:
        def get_section(self, domain, tab):
            assert (domain, tab) == ("agents", "automation")
            return {"value": {"enabled": True, "background_incremental_enabled": False, "emergency_pause": False}}

    class Pipeline:
        async def process_task(self, leased_task, *, tenant_id):
            assert leased_task.id == task.id
            assert tenant_id == "1"
            return TaskProcessingResult(
                claim_ids=("claim-1",),
                outcomes=(AdjudicationOutcome("publish", "published", ("safe",)),),
                token_count=9,
            )

    monkeypatch.setattr("app.interfaces.http.novel_analysis.build_system_settings_service", lambda: Settings())
    monkeypatch.setattr(
        "app.interfaces.http.novel_analysis.build_novel_analysis_pipeline_service",
        lambda: Pipeline(),
        raising=False,
    )

    response = client.post(f"/api/novel-analysis/tasks/{task.id}/run", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["checkpoint"]["outcomes"][0]["reasons"] == ["safe"]

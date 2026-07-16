def test_task_pauses_at_tool_budget_and_resumes_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "analysis-tasks.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.novel_analysis_task_service import NovelAnalysisTaskService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_analysis_task_repo_impl import SQLiteNovelAnalysisTaskRepository

    bootstrap_sqlite()
    service = NovelAnalysisTaskService(SQLiteNovelAnalysisTaskRepository())
    task = service.create_task("work-1", "tenant-1", "分析主角关系", {"max_tool_calls_per_task": 2})
    service.record_tool_progress(task.id, ["span-1"])
    service.record_tool_progress(task.id, ["span-2"])

    paused = service.get_task(task.id, tenant_id="tenant-1")
    resumed = service.resume(task.id, tenant_id="tenant-1")

    assert paused.status == "paused"
    assert paused.checkpoint["selected_evidence_ids"] == ["span-1", "span-2"]
    assert resumed.status == "queued"


def test_adjudication_record_keeps_route_model_prompt_and_evidence_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "analysis-decisions.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_analysis_task_repo_impl import SQLiteNovelAnalysisTaskRepository

    bootstrap_sqlite()
    repo = SQLiteNovelAnalysisTaskRepository()
    recorded = repo.record_adjudication(
        claim_id="claim-1",
        tenant_id="tenant-1",
        role="adjudicator",
        verdict="publish",
        reasons=("safe explicit fact",),
        evidence_ids=["span-1"],
        provider_group="novel_adjudicate",
        provider_name="openai-compatible",
        model="gpt-test",
        prompt_version="evidence-first-v1",
    )

    decisions = repo.list_adjudications("claim-1", tenant_id="tenant-1")

    assert decisions == [recorded]
    assert recorded["role"] == "adjudicator"
    assert recorded["evidence_ids"] == ["span-1"]
    assert recorded["provider_group"] == "novel_adjudicate"
    assert recorded["model"] == "gpt-test"


def test_task_service_leases_queued_task_and_keeps_a_completion_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "analysis-task-lease.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.novel_analysis_task_service import NovelAnalysisTaskService
    from app.domain.entities.novel_analysis_task import AdjudicationOutcome, TaskProcessingResult
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.novel_analysis_task_repo_impl import SQLiteNovelAnalysisTaskRepository

    bootstrap_sqlite()
    service = NovelAnalysisTaskService(SQLiteNovelAnalysisTaskRepository())
    created = service.create_task("work-1", "tenant-1", "分析人物关系")

    leased = service.lease_next()
    completed = service.complete(
        created.id,
        tenant_id="tenant-1",
        result=TaskProcessingResult(
            claim_ids=("claim-1",),
            outcomes=(AdjudicationOutcome("publish", "published", ("safe explicit fact",)),),
            token_count=21,
        ),
    )

    assert leased is not None and leased.id == created.id
    assert leased.status == "running"
    assert completed.status == "completed"
    assert completed.checkpoint["claim_ids"] == ["claim-1"]
    assert completed.checkpoint["token_count"] == 21
    assert completed.checkpoint["outcomes"] == [{
        "claim_id": "claim-1", "verdict": "publish", "claim_status": "published", "reasons": ["safe explicit fact"],
    }]

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

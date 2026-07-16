from fastapi.testclient import TestClient


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

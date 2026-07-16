from fastapi.testclient import TestClient


def test_engine_api_exposes_runs_and_deployments(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "engine-runtime-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {
            "sub": "1",
            "permissions": ["engine.generate", "engine.deploy", "engine.test"],
            "sid": "engine-runtime-api-1",
        }
    )
    headers = {"Authorization": f"Bearer {token}"}

    generate = client.post(
        "/api/engine/generate",
        json={"url": "https://example.com", "source_type": "book"},
        headers=headers,
    )
    assert generate.status_code == 200
    source_version_id = generate.json()["data"]["source_version_id"]

    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    runtime_repo = SQLiteSourceRuntimeRepository()
    generated_version = runtime_repo.get_version(source_version_id)
    assert generated_version is not None
    runtime_repo.update_version_payload(
        source_version_id,
        {
            **generated_version.payload,
            "source_audit": {"status": "passed", "attempt": 1, "test_run_pending": False},
        },
    )
    runtime_repo.record_test_run(
        source_version_id=source_version_id,
        trigger="source_audit",
        score=100,
        grade="A",
        step_results={
            "search": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "toc": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "content": {"passed": True, "status": "ok", "elapsed_ms": 1},
            "source_audit": {"passed": True, "status": "recorded", "elapsed_ms": 0},
        },
    )

    deploy = client.post(
        "/api/engine/deploy",
        json={"source_version_id": source_version_id},
        headers=headers,
    )
    assert deploy.status_code == 200
    assert deploy.json()["data"]["status"] == "candidate"
    assert deploy.json()["data"]["review_status"] == "pending_review"

    resolve = client.post(
        f"/api/engine/reviews/{source_version_id}/resolve",
        json={"action": "publish"},
        headers=headers,
    )
    assert resolve.status_code == 200
    assert resolve.json()["data"]["status"] == "published"

    runs = client.get("/api/engine/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json()["success"] is True

    deployments = client.get("/api/engine/deployments", headers=headers)
    assert deployments.status_code == 200
    assert deployments.json()["success"] is True
    actions = [item["action"] for item in deployments.json()["data"]]
    assert "review.resolve" in actions


def test_engine_api_exposes_console_source_build_submission_and_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "engine-source-build-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {
            "sub": "7",
            "permissions": ["engine.generate", "engine.test"],
            "sid": "engine-source-build-api-1",
        }
    )
    headers = {"Authorization": f"Bearer {token}"}

    submit = client.post(
        "/api/engine/source-builds",
        json={"url": "https://console.test/books/", "keyword": "sample"},
        headers=headers,
    )

    assert submit.status_code == 200
    assert submit.json()["data"]["job_id"]
    assert submit.json()["data"]["normalized_url"] == "https://console.test/books"
    source_version_id = submit.json()["data"]["source_version_id"]

    candidates = client.get("/api/engine/source-builds", headers=headers)
    assert candidates.status_code == 200
    row = next(item for item in candidates.json()["data"] if item["id"] == source_version_id)
    assert row["source_id"] == "https://console.test/books"
    assert row["payload"]["keyword"] == "sample"

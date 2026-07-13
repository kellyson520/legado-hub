def test_create_candidate_version_and_run_record(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    version = repo.create_candidate_version(
        source_type="book",
        source_id="source-1",
        payload={"ruleSearch": {"bookList": ".book"}},
        created_by="admin",
    )
    run = repo.record_test_run(
        source_version_id=version.id,
        trigger="manual",
        score=92,
        grade="A",
        step_results={"search": {"passed": True, "elapsed_ms": 120}},
    )

    assert version.status == "candidate"
    assert run.step_results["search"]["passed"] is True


def test_list_recent_versions_filters_by_status_and_orders_latest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-recent.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    first = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.test/source-a",
        payload={"keyword": "sample-a"},
        created_by="tenant-a",
    )
    second = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.test/source-b",
        payload={"keyword": "sample-b"},
        created_by="tenant-b",
    )
    published = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.test/source-c",
        payload={"keyword": "sample-c"},
        created_by="tenant-c",
    )
    repo.update_version_status(published.id, "published")

    recent_candidates = repo.list_recent_versions(status="candidate", limit=10)
    published_row = repo.get_version(published.id)

    assert [item.id for item in recent_candidates] == [second.id, first.id]
    assert all(item.status == "candidate" for item in recent_candidates)
    assert published_row is not None
    assert published_row.published_at is not None


def test_update_version_payload_persists_autonomous_build_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-runtime-payload.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository

    bootstrap_sqlite()
    repo = SQLiteSourceRuntimeRepository()
    version = repo.create_candidate_version(
        source_type="book",
        source_id="https://example.test/source",
        payload={"keyword": "sample"},
        created_by="tenant-a",
    )

    updated = repo.update_version_payload(
        version.id,
        {
            "keyword": "sample",
            "autonomous_build": {
                "agent_run_id": "run-1",
                "decision": "canary",
            },
        },
    )

    assert updated.payload["autonomous_build"]["agent_run_id"] == "run-1"

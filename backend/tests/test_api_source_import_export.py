from fastapi.testclient import TestClient


def _client_and_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "legado-import-export.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    token = create_access_token(
        {"sub": "7", "permissions": ["book_sources.write", "book_sources.read"], "sid": "source-import-export"}
    )
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_json_import_creates_sanitized_candidate_and_reports_item_errors(tmp_path, monkeypatch):
    client, headers = _client_and_headers(tmp_path, monkeypatch)

    response = client.post(
        "/api/sources/import",
        json=[
            {
                "bookSourceName": "示例源",
                "bookSourceUrl": "https://example.test/books",
                "ruleSearch": {"bookList": ".book"},
                "cookie": "secret",
                "header": {"Authorization": "Bearer secret", "User-Agent": "Legado"},
            },
            {"bookSourceName": "缺少地址"},
            {"bookSourceName": "重复源", "bookSourceUrl": "https://example.test/books"},
        ],
        headers=headers,
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["status"] for item in items] == ["created", "invalid", "skipped_duplicate"]

    from app.infrastructure.persistence.factory import build_source_runtime_repository

    version = build_source_runtime_repository().get_version(items[0]["source_version_id"])
    assert version is not None
    assert version.status == "candidate"
    assert version.created_by == "7"
    assert version.payload["ruleSearch"] == {"bookList": ".book"}
    assert "cookie" not in version.payload
    assert version.payload["header"] == {"User-Agent": "Legado"}


def test_export_is_whitelisted_and_only_includes_own_candidates_or_published(tmp_path, monkeypatch):
    client, headers = _client_and_headers(tmp_path, monkeypatch)
    from app.infrastructure.persistence.factory import build_source_runtime_repository

    repo = build_source_runtime_repository()
    own = repo.create_candidate_version(
        "book",
        "https://own.test/books",
        {"bookSourceName": "我的候选", "bookSourceUrl": "https://own.test/books", "ruleSearch": {"bookList": ".x"}, "apiKey": "no"},
        "7",
    )
    other = repo.create_candidate_version(
        "book",
        "https://other.test/books",
        {"bookSourceName": "其他候选", "bookSourceUrl": "https://other.test/books"},
        "8",
    )
    published = repo.create_candidate_version(
        "book",
        "https://published.test/books",
        {"bookSourceName": "已发布", "bookSourceUrl": "https://published.test/books", "ruleContent": {"content": "#content"}},
        "8",
    )
    repo.update_version_status(published.id, "published")

    response = client.get("/api/sources/export", headers=headers)

    assert response.status_code == 200
    exported = {item["bookSourceUrl"]: item for item in response.json()["data"]}
    assert set(exported) == {own.source_id, published.source_id}
    assert other.source_id not in exported
    assert exported[own.source_id] == {
        "bookSourceName": "我的候选",
        "bookSourceUrl": own.source_id,
        "ruleSearch": {"bookList": ".x"},
    }
    assert "apiKey" not in exported[own.source_id]


def test_visible_source_inventory_matches_agent_visible_candidates_and_published_sources(tmp_path, monkeypatch):
    client, headers = _client_and_headers(tmp_path, monkeypatch)
    from app.infrastructure.persistence.factory import build_source_runtime_repository

    repo = build_source_runtime_repository()
    own = repo.create_candidate_version(
        "book",
        "https://own-visible.test/books",
        {"bookSourceName": "我的候选", "bookSourceUrl": "https://own-visible.test/books"},
        "7",
    )
    hidden = repo.create_candidate_version(
        "book",
        "https://other-visible.test/books",
        {"bookSourceName": "他人的候选", "bookSourceUrl": "https://other-visible.test/books"},
        "8",
    )
    published = repo.create_candidate_version(
        "book",
        "https://published-visible.test/books",
        {"bookSourceName": "已发布书源", "bookSourceUrl": "https://published-visible.test/books"},
        "8",
    )
    failed = repo.create_candidate_version(
        "book",
        "https://failed-visible.test/books",
        {"bookSourceName": "失败书源", "bookSourceUrl": "https://failed-visible.test/books"},
        "7",
    )
    superseded = repo.create_candidate_version(
        "book",
        "https://superseded-visible.test/books",
        {"bookSourceName": "已替代书源", "bookSourceUrl": "https://superseded-visible.test/books"},
        "7",
    )
    repo.update_version_status(published.id, "published")
    repo.update_version_status(failed.id, "failed")
    repo.update_version_status(superseded.id, "superseded")

    response = client.get("/api/sources/visible", headers=headers)

    assert response.status_code == 200
    rows = {item["id"]: item for item in response.json()["data"]}
    assert set(rows) == {own.id, published.id}
    assert hidden.id not in rows
    assert failed.id not in rows
    assert superseded.id not in rows
    assert rows[own.id]["bookSourceName"] == "我的候选"
    assert rows[own.id]["bookSourceUrl"] == own.source_id
    assert rows[own.id]["sourceStatus"] == "candidate"
    assert rows[own.id]["sourceOrigin"] == "runtime_version"
    assert rows[published.id]["sourceStatus"] == "published"

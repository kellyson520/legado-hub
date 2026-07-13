from fastapi.testclient import TestClient


def test_import_book_sources_from_local_file_persists_legado_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-import.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    sample_file = tmp_path / "shareBookSource.json"
    sample_file.write_text(
        """
        [
          {
            "bookSourceName": "测试源A",
            "bookSourceUrl": "https://a.example.com",
            "bookSourceGroup": "本地导入",
            "enabled": true,
            "searchUrl": "https://a.example.com/search?key={{key}}",
            "ruleSearch": {"bookList": ".book", "name": ".title", "bookUrl": "a@href"},
            "ruleToc": {"chapterList": "#list a", "chapterName": "text", "chapterUrl": "href"},
            "ruleContent": {"content": "#content"}
          }
        ]
        """,
        encoding="utf-8",
    )

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token(
        {"sub": "1", "permissions": ["book_sources.write", "book_sources.read"], "sid": "src-import-1"}
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/sources/book_sources/import",
        json={"file_path": str(sample_file), "replace_existing": True},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["book_count"] == 1
    assert payload["file_path"] == str(sample_file)

    listed = client.get("/api/sources/book_sources", headers=headers)
    assert listed.status_code == 200
    first = listed.json()["data"][0]
    assert first["searchUrl"] == "https://a.example.com/search?key={{key}}"
    assert first["ruleSearch"]["bookList"] == ".book"
    assert first["ruleToc"]["chapterList"] == "#list a"
    assert first["ruleContent"]["content"] == "#content"

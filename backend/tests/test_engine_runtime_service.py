import pytest


@pytest.mark.asyncio
async def test_runtime_service_requires_source_audit_before_publishing_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "engine-runtime.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_runtime_service import SourceRuntimeService
    from app.core.exceptions import ValidationException
    from app.infrastructure.persistence.factory import build_source_runtime_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    service = SourceRuntimeService(build_source_runtime_repository())
    candidate = await service.generate({"url": "https://example.com", "source_type": "book"}, actor_id="admin")
    decision = await service.deploy(candidate["source_version_id"], actor_id="admin")
    with pytest.raises(ValidationException, match="source audit is missing"):
        await service.resolve_review(candidate["source_version_id"], reviewer_id="reviewer-1", action="publish")

    assert decision["status"] == "candidate"
    assert decision["quality_gate"]["allowed"] is True
    assert decision["review_status"] == "pending_review"
    assert decision["publish_allowed"] is False
    assert candidate["source_version_id"]

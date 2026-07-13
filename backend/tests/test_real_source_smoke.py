import pytest


class FakeVerifier:
    async def verify(self, source_type: str, source: dict) -> dict:
        return {"passed": True, "source_type": source_type, "source_id": source["id"]}


@pytest.mark.asyncio
async def test_real_source_smoke_suite_returns_structured_failures():
    from app.application.services.source_health_service import RealSourceSmokeRunner

    runner = RealSourceSmokeRunner(
        book_sources=[{"id": "book-1"}],
        rss_sources=[{"id": "rss-1"}],
        verifier=FakeVerifier(),
    )
    summary = await runner.run_all()

    assert "book" in summary["by_type"]
    assert "rss" in summary["by_type"]
    assert summary["by_type"]["book"]["total"] == 1
    assert summary["by_type"]["rss"]["total"] == 1

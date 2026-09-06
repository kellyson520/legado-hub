import pytest

from app.application.services.source_runtime_service import SourceRuntimeService
from app.domain.entities.source_runtime import SourceVersion


class FakeRuntimeRepo:
    def __init__(self):
        self.calls = []
        self.version = SourceVersion(
            id="v1",
            source_type="book",
            source_id="https://example.invalid",
            status="candidate",
            payload={
                "bookSourceName": "fixture",
                "bookSourceUrl": "https://example.invalid",
                "searchUrl": "https://example.invalid/search?q={{key}}",
                "ruleSearch": {"bookList": ".book", "name": "a@text", "bookUrl": "a@href"},
                "ruleToc": {"chapterList": ".chapter", "chapterName": "@text", "chapterUrl": "@href"},
                "ruleContent": {"content": ".content@text"},
            },
        )

    def get_version(self, version_id):
        return self.version

    def record_test_run(self, **kwargs):
        self.calls.append(kwargs)
        return type("Run", (), {"id": "run-1", "score": 0, "grade": "F", "step_results": kwargs["step_results"], "diagnostics": kwargs["diagnostics"]})()


class FakeProbe:
    async def probe_source(self, source, keyword_samples, probe_mode):
        self.keywords = keyword_samples
        stage = type("Stage", (), {"status": "ok", "detail": {}, "elapsed_ms": 1, "hit_count": 1})()
        return type("Evidence", (), {"search": stage, "toc": stage, "content": stage})()


@pytest.mark.asyncio
async def test_validation_uses_multiple_probe_keywords():
    repo = FakeRuntimeRepo()
    probe = FakeProbe()
    service = SourceRuntimeService(repo, source_probe=probe)
    await service.validate_rule_version("v1", "1")
    assert probe.keywords == ["斗罗大陆", "捞尸人", "剑来"]

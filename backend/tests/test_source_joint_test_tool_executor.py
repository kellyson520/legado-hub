import pytest


@pytest.mark.asyncio
async def test_executor_injects_tenant_and_returns_compact_report():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    seen = []

    class Acceptance:
        async def run(self, scenario):
            seen.append(scenario)
            return {
                "status": "partial",
                "steps": [{"name": "content", "status": "passed"}],
                "chapter_candidates": [],
            }

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
        "chapter_index": 0,
    })

    assert result.status == "accepted"
    assert seen[0]["tenant_id"] == "tenant-1"
    assert seen[0]["agent_joint_test"] is True
    assert result.data["report"]["status"] == "partial"
    assert result.data["summary"]["content_passed"] == 1
    assert result.data["agent_joint_test"]["tool_name"] == "source.joint_test"


@pytest.mark.asyncio
async def test_executor_rejects_more_than_four_urls_without_running():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    class Acceptance:
        async def run(self, _scenario):
            raise AssertionError("acceptance must not run")

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": [f"https://{index}.test" for index in range(5)],
        "book_name": "斗罗大陆",
    })

    assert result.status == "rejected"
    assert result.error_code == "source_urls_limit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "error_code"),
    [
        ({"source_urls": ["https://a.test"], "book_name": "斗罗大陆"}, "tenant_id_required"),
        ({"tenant_id": "tenant-1", "source_urls": ["ftp://a.test"], "book_name": "斗罗大陆"}, "source_url_invalid"),
        ({"tenant_id": "tenant-1", "source_urls": ["https://a.test"], "book_name": "斗罗大陆", "chapter_index": -1}, "chapter_index_invalid"),
        ({"tenant_id": "tenant-1", "source_urls": ["https://a.test"], "book_name": "斗罗大陆", "use_ai": "yes"}, "use_ai_invalid"),
    ],
)
async def test_executor_rejects_invalid_arguments(arguments, error_code):
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    class Acceptance:
        async def run(self, _scenario):
            raise AssertionError("acceptance must not run")

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke(arguments)

    assert result.status == "rejected"
    assert result.error_code == error_code


@pytest.mark.asyncio
async def test_executor_converts_acceptance_exception_to_stable_error():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    class Acceptance:
        async def run(self, _scenario):
            raise RuntimeError("provider secret must not leak")

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })

    assert result.status == "rejected"
    assert result.error_code == "acceptance_failed"
    assert result.data == {}


@pytest.mark.asyncio
async def test_executor_removes_full_chapter_body_but_keeps_original_length():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    body = "正文" * 1000

    class Acceptance:
        async def run(self, _scenario):
            return {
                "status": "passed",
                "steps": [],
                "chapter_candidates": [{"content": body}],
            }

    result = await SourceJointTestToolExecutor(Acceptance()).ainvoke({
        "tenant_id": "tenant-1",
        "source_urls": ["https://a.test"],
        "book_name": "斗罗大陆",
    })
    chapter = result.data["report"]["chapter_candidates"][0]

    assert "content" not in chapter
    assert chapter["content_length"] == len(body)
    assert len(chapter["content_preview"]) <= 1200


def test_executor_exposes_registry_handler():
    from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor

    handlers = SourceJointTestToolExecutor(object()).handlers()

    assert set(handlers) == {"source.joint_test"}


def test_factory_exposes_joint_test_executor_builder(monkeypatch):
    import app.infrastructure.persistence.factory as factory

    acceptance = object()
    monkeypatch.setattr(factory, "build_source_to_insight_acceptance_service", lambda: acceptance)

    executor = factory.build_source_joint_test_tool_executor()

    assert executor._acceptance_service is acceptance

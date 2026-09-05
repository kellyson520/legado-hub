from app.application.services.novel_analysis_task_service import NovelAnalysisTaskService
from app.application.services.novel_analysis_pipeline_service import select_analysis_evidence
from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService


def test_analysis_policy_clamps_tokens_tools_and_chapters():
    policy = NovelAnalysisTaskService.normalize_policy({
        "max_tokens_per_task": 999999,
        "max_tool_calls_per_task": 0,
        "max_chapters_per_task": 999,
    })
    assert policy == {
        "max_tokens_per_task": 200000,
        "max_tool_calls_per_task": 1,
        "max_chapters_per_task": 50,
    }


def test_evidence_selection_respects_chapter_and_span_limits():
    report = NovelCodeAnalysisService().analyze(
        "budget-work",
        [
            {"chapter_id": "c1", "chapter_index": 1, "title": "一", "content": "林默进入长安。"},
            {"chapter_id": "c2", "chapter_index": 2, "title": "二", "content": "苏晚在子时离开。"},
            {"chapter_id": "c3", "chapter_index": 3, "title": "三", "content": "林默与苏晚重逢。"},
        ],
    )
    selected = select_analysis_evidence(report, max_chapters=2, max_spans=3)
    assert len(selected) <= 3
    assert len({item["chapter_id"] for item in selected}) <= 2
    assert all(item["evidence_id"] for item in selected)
    assert all(item["start_offset"] < item["end_offset"] for item in selected)


def test_pipeline_refuses_model_call_after_token_budget_is_exhausted():
    class Platform:
        calls = 0

        async def invoke_chat(self, **kwargs):
            self.calls += 1
            return {"output": {"text": "{}"}, "usage": {"total_tokens": 1}}

    platform = Platform()
    pipeline = NovelAnalysisPipelineService(knowledge_service=None, evidence_service=object(), platform=platform)

    async def invoke():
        try:
            await pipeline._invoke_role(
                role="extractor", tenant_id="tenant-1", payload={"text": "x"},
                token_count=10, token_budget=10,
            )
        except RuntimeError as exc:
            assert str(exc) == "analysis task token budget exhausted"
        else:
            raise AssertionError("expected budget exhaustion")

    import asyncio
    asyncio.run(invoke())
    assert platform.calls == 0

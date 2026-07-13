import pytest


@pytest.mark.asyncio
async def test_character_calibration_service_uses_heuristic_overlap():
    from app.application.services.character_calibration_service import CharacterCalibrationService

    service = CharacterCalibrationService(ai_service=None)
    result = await service.calibrate(
        keyword="捞尸人",
        items=[
            {
                "source_id": 7,
                "name": "捞尸人",
                "author": "陈十三",
                "excerpt": "张三和李四来到黄河边，张三看见了一具尸体，李四很紧张。",
            },
            {
                "source_id": 12,
                "name": "捞尸人",
                "author": "陈十三",
                "excerpt": "张三与李四在河边发现尸体，张三决定下水，李四负责报警。",
            },
        ],
    )

    assert result["used_provider"] is False
    assert result["items"][0]["characters"]
    assert result["pairwise"][0]["overlap_score"] > 0


@pytest.mark.asyncio
async def test_character_calibration_service_includes_provider_result_when_available():
    from app.application.services.character_calibration_service import CharacterCalibrationService

    class FakeAIService:
        async def run_character_analysis(self, payload: dict, actor_id: str = "system") -> dict:
            return {
                "id": "task_1",
                "result": {"text": "provider-summary"},
                "status": "succeeded",
            }

    service = CharacterCalibrationService(ai_service=FakeAIService())
    result = await service.calibrate(
        keyword="斗罗大陆",
        items=[
            {
                "source_id": 7,
                "name": "斗罗大陆",
                "author": "唐家三少",
                "excerpt": "唐三和小舞在史莱克学院修炼，戴沐白也在场。",
            }
        ],
    )

    assert result["used_provider"] is True
    assert result["provider_result"]["result"]["text"] == "provider-summary"

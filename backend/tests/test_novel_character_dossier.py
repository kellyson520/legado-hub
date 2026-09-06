import pytest
from app.application.services.novel_character_dossier_service import NovelCharacterDossierService


@pytest.mark.asyncio
async def test_character_dossier_service_builds_complete_profile():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "第1章 循环与面具",
            "content": "林弦戴上了奥特曼面具，神色从容而冷静。小林向大脸猫收下了C4炸药，准备进行精密计算。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "第2章 爆炸与危机",
            "content": "突如其来的剧烈爆炸震撼了整个金库！林弦脸色惨白冷汗直冒，陷入绝望与危机。但他立刻咬牙使用引爆器摧毁了保险柜！",
        },
        {
            "chapter_id": "c3",
            "chapter_index": 3,
            "title": "第3章 破局",
            "content": "林弦站在高楼天台上，目光冷冽而自信，嘴角浮现从容的微笑。弦哥已经彻底掌握了时空的规律。",
        },
    ]

    service = NovelCharacterDossierService()
    dossier = await service.build_dossier(
        book_id=1,
        character_name="林弦",
        chapters=chapters,
    )

    assert dossier["character_name"] == "林弦"
    assert "aliases" in dossier
    assert any(a in ("小林", "弦哥") for a in dossier["aliases"])
    assert dossier["overall_tier"] in ("S", "A")

    # Items tracked
    items = dossier["items"]
    assert len(items) >= 2
    item_names = [i["item_name"] for i in items]
    assert any("面具" in name for name in item_names)
    assert any("炸药" in name or "C4" in name for name in item_names)

    # Emotional arc
    arc = dossier["emotional_arc"]
    assert len(arc["turning_points"]) >= 1

    # Scoring & Radar
    scoring = dossier["scoring"]
    assert scoring["plot_impact"] >= 30.0
    assert scoring["mental_score"] >= 60.0
    assert "radar" in scoring

    # Summary card markdown
    summary_card = dossier["summary_card"]
    assert "林弦" in summary_card
    assert "综合评级" in summary_card
    assert "持有物品" in summary_card

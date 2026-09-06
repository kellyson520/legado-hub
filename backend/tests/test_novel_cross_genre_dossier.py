import pytest
from app.application.services.novel_character_dossier_service import NovelCharacterDossierService


@pytest.mark.asyncio
async def test_cross_genre_character_dossier_classical_and_modern():
    # 1. Classical: Three Kingdoms - Guan Yu
    three_kingdoms_chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "温酒斩华雄",
            "content": "关羽造得一柄青龙偃月刀。华雄在关前斩将。关公笑曰：酒且斟下，某便去也！关羽提刀纵马出阵，斩华雄首级回帐。曹操大喜。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "白马之围赠赤兔",
            "content": "曹操将一匹赤兔马赠予关羽。关羽正色言曰：吾受玄德厚恩，誓以死报，忠义之心不可移！关将军跨坐赤兔马，飞马杀入万军之中刺颜良。",
        },
    ]

    service = NovelCharacterDossierService()
    dossier_guan = await service.build_dossier(
        book_id=901,
        character_name="关羽",
        chapters=three_kingdoms_chapters,
    )

    # Assertions on Guan Yu
    assert dossier_guan["character_name"] == "关羽"
    assert "云长" in dossier_guan["aliases"] or "关公" in dossier_guan["aliases"] or "关将军" in dossier_guan["aliases"]
    assert dossier_guan["overall_tier"] in ("SSS", "SS", "S", "A")

    # Check 6D matrix
    assert "capability_matrix" in dossier_guan["scoring"]
    matrix = dossier_guan["scoring"]["capability_matrix"]
    assert matrix["武勇绝杀"]["score"] >= 65.0
    assert matrix["气节风骨"]["score"] >= 60.0
    assert matrix["宝器神兵"]["score"] >= 75.0

    # Check items
    item_names = [i["item_name"] for i in dossier_guan["items"]]
    assert any("青龙偃月刀" in n for n in item_names)
    assert any("赤兔马" in n for n in item_names)

    # Check summary card mentions 6D matrix and items
    summary_card = dossier_guan["summary_card"]
    assert "青龙偃月刀" in summary_card
    assert "赤兔马" in summary_card
    assert "武勇绝杀" in summary_card
    assert "气节风骨" in summary_card


@pytest.mark.asyncio
async def test_cross_genre_character_dossier_modern_urban():
    # 2. Modern Urban Mystery: Lin Xian
    modern_chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "开场",
            "content": "林弦戴上奥特曼面具，神色从容而冷静。他收下大脸猫递来的C4炸药，坐在保险柜前破译密码。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "引爆",
            "content": "林弦按下引爆按钮，C4炸药轰然爆炸！火光吞没了银行金库。弦哥冷静地指挥撤离。",
        },
    ]

    service = NovelCharacterDossierService()
    dossier_lin = await service.build_dossier(
        book_id=902,
        character_name="林弦",
        chapters=modern_chapters,
    )

    assert dossier_lin["character_name"] == "林弦"
    assert dossier_lin["overall_tier"] in ("S", "A")
    item_names = [i["item_name"] for i in dossier_lin["items"]]
    assert any("面具" in n for n in item_names)
    assert any("C4炸药" in n or "炸药" in n for n in item_names)

from app.application.services.novel_scene_tension_service import NovelSceneTensionService


def test_calculate_tension_differentiates_tranquil_and_combat_scenes():
    service = NovelSceneTensionService()
    peaceful_text = "窗外的阳光柔和地洒在木桌上，微风吹拂着窗帘，林弦端起热茶慢慢啜饮，享受着难得的闲暇午后时光。"
    action_text = "大脸猫突然举枪顶住后脑勺，扣动扳机！嘭！枪声炸裂，鲜血四溅！仓库密码门上的C4炸药开始急速倒计时：3、2、1，轰然爆炸！"

    peaceful_score = service.score_passage(peaceful_text)
    action_score = service.score_passage(action_text)

    assert action_score > peaceful_score
    assert action_score >= 10.0
    assert peaceful_score < 3.0


def test_extract_climax_scenes_returns_top_conflict_fragments():
    service = NovelSceneTensionService()
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "平静的开场",
            "content": "林弦每天都过着普通上班族的生活。打卡、上班、喝咖啡，同事们闲聊着日常。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "生死时刻",
            "content": "猛烈的爆炸将整面墙体撕裂，黑烟弥漫，火焰冲天！杀手举枪扫射，子弹呼啸穿梭，林弦伏地翻滚，在千钧一发之际引爆了炸药，火光瞬间吞没了一切！",
        },
        {
            "chapter_id": "c3",
            "chapter_index": 3,
            "title": "余波",
            "content": "救援人员赶到了现场。废墟已经冷却，林弦在救护车旁默默坐着包扎伤口。",
        },
    ]

    climaxes = service.extract_climax_scenes(chapters, top_k=1)
    assert len(climaxes) == 1
    top_scene = climaxes[0]
    assert top_scene["chapter_title"] == "生死时刻"
    assert top_scene["chapter_index"] == 2
    assert "爆炸" in top_scene["excerpt"] or "炸药" in top_scene["excerpt"]
    assert top_scene["tension_score"] > 8.0

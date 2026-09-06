from app.application.services.novel_item_tracker_service import NovelItemTrackerService


def test_item_tracker_extracts_items_and_actions_for_characters():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "第1章 开场",
            "content": "林弦收下了大脸猫递来的C4炸药。随后，他扶正脸上的奥特曼面具。大脸猫把弹夹推进手枪上了膛。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "第2章 仓库",
            "content": "林弦走到保险柜前，将贴在密码门上的C4炸药引爆！轰隆一声巨响！",
        },
    ]

    service = NovelItemTrackerService()
    results = service.track_items(chapters, character_names=["林弦", "大脸猫"])

    assert "林弦" in results
    lin_items = results["林弦"]
    item_names = [i["item_name"] for i in lin_items]

    assert any("C4炸药" in name or "炸药" in name for name in item_names)
    assert any("面具" in name for name in item_names)

    c4_record = next(i for i in lin_items if "炸药" in i["item_name"])
    assert c4_record["chapter_index"] in (1, 2)
    assert c4_record["action"] in ("acquired", "used")

    assert "大脸猫" in results
    cat_items = results["大脸猫"]
    assert any("手枪" in i["item_name"] or "枪" in i["item_name"] for i in cat_items)

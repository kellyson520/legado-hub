from app.application.services.novel_item_tracker_service import NovelItemTrackerService


def test_open_vocabulary_item_extraction_with_classifiers_and_syntax():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "桃园结义",
            "content": "关羽造得一柄青龙偃月刀，又名冷艳锯，重八十二斤。张飞造就一口丈八蛇矛。刘备造了一双雌雄双股剑。曹操腰悬七星宝刀，刺杀董卓未果。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "白马之围",
            "content": "曹操指着远处一匹赤兔马，将赤兔马赠予关羽。关羽大喜拜谢。关公随即跨坐赤兔马，倒提青龙偃月刀，直冲彼军阵前，斩颜良于万众之中！",
        },
    ]

    service = NovelItemTrackerService()
    results = service.track_items(chapters, character_names=["关羽", "关公", "张飞", "刘备", "曹操"])

    # Guan Yu checks
    guan_items = results["关羽"] + results["关公"]
    item_names = [i["item_name"] for i in guan_items]

    # Open-vocabulary extracted weapons & mounts
    assert any("青龙偃月刀" in name for name in item_names)
    assert any("赤兔马" in name for name in item_names)

    c2_blade = next(i for i in guan_items if "青龙偃月刀" in i["item_name"])
    assert c2_blade["category"] == "weapon"

    c2_horse = next(i for i in guan_items if "赤兔马" in i["item_name"])
    assert c2_horse["category"] == "mount"
    assert c2_horse["action"] in ("acquired", "used")

    # Zhang Fei checks
    zhang_items = results["张飞"]
    assert any("丈八蛇矛" in i["item_name"] for i in zhang_items)

    # Cao Cao checks
    cao_items = results["曹操"]
    assert any("七星宝刀" in i["item_name"] for i in cao_items)

from app.application.services.novel_emotional_arc_service import NovelEmotionalArcService


def test_compute_arc_tracks_sentiment_shift_and_turning_points():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "平静生活",
            "content": "林弦端起咖啡，神色从容而从容地看着窗外阳光，内心一片平静与从容，享受这悠闲的下午。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "噩梦与绝望",
            "content": "突如其来的剧烈震动打破了安宁！林弦浑身冷汗直冒，心跳骤停，脸色惨白如纸，陷入了极度的绝望与恐惧之中，眼睁睁看着一切崩塌！",
        },
        {
            "chapter_id": "c3",
            "chapter_index": 3,
            "title": "绝地反击",
            "content": "林弦深吸一口气强行镇定下来，眼神变得冷冽果断，嘴角泛起从容自信的微笑，迅速分析战局开始反击。",
        },
    ]

    service = NovelEmotionalArcService()
    arc = service.compute_arc(chapters, character_name="林弦")

    assert "trajectory" in arc
    traj = arc["trajectory"]
    assert len(traj) == 3

    # Chapter 1 is tranquil/positive
    assert traj[0]["sentiment_score"] > 0.0
    assert traj[0]["dominant_emotion"] in ("平静", "从容", "自信", "悠闲")

    # Chapter 2 is negative/fear/despair
    assert traj[1]["sentiment_score"] < 0.0
    assert traj[1]["dominant_emotion"] in ("恐惧", "绝望", "紧张")

    # Chapter 3 recovers / resolute
    assert traj[2]["sentiment_score"] > 0.0

    # Turning points should capture the sharp drop and recovery
    assert "turning_points" in arc
    tp = arc["turning_points"]
    assert len(tp) >= 1
    assert any(p["chapter_index"] == 2 for p in tp)

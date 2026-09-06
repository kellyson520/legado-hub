from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService


def test_character_analysis_filters_common_noise_words():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "第一章",
            "content": "林弦站在街头。不要看他，可是现在他必须决定离开。然而林弦发现了端倪，继续向前走。",
        }
    ]
    service = NovelCodeAnalysisService()
    report = service.analyze("work-noise-test", chapters)

    names = [c.name for c in report.characters]
    assert "林弦" in names
    assert "不要" not in names
    assert "可是现" not in names
    assert "然而" not in names
    assert "继续" not in names


def test_character_analysis_clusters_aliases_and_assigns_tiers():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "第一章",
            "content": "林弦和赵英珺在办公室碰面。小林向赵总汇报进度，弦哥笑着倒了杯咖啡。赵英珺赞许地点头。旁边实习生周正也走了过来。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "第二章",
            "content": "林弦与赵英珺再次商讨。小林展示了新的方案。大脸猫突然推门而入，大喊一声。",
        },
    ]
    service = NovelCodeAnalysisService()
    report = service.analyze("work-alias-test", chapters)

    char_dict = {c.name: c for c in report.characters}
    assert "林弦" in char_dict
    lin = char_dict["林弦"]

    # "小林" or "弦哥" should be identified as aliases of "林弦"
    assert any(alias in ("小林", "弦哥") for alias in lin.aliases)
    # 林弦 is central character
    assert lin.importance_tier in ("protagonist", "major")
    assert lin.centrality > 0.0

    # Report has character graph
    assert hasattr(report, "character_graph")
    assert "nodes" in report.character_graph
    assert "edges" in report.character_graph

from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService


def test_classical_character_extraction_and_alias_clustering():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "温酒斩华雄",
            "content": "华雄在汜水关前斩鲍忠、败孙坚。忽探子来报：华雄引铁骑下关。曹操笑曰：谁敢去战？袁术叱曰：汝欺吾众诸侯无大将耶？关羽按剑高叫：某愿往斩华雄！云长笑曰：酒且斟下，某便去也！关公纵马提刀出阵，鸾铃响处，提华雄首级掷于地上。酒尚温。曹操大喜，玄德与关羽相视而笑。",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "三英战吕布",
            "content": "吕布飞马杀入阵中，张飞圆睁环眼大喝曰：三姓家奴休走！张翼德在此！关将军拍马舞刀来夹攻吕布。刘备亦掣双股剑拍马刺来。曹丞相大惊失色，急令鸣金。",
        },
    ]

    service = NovelCodeAnalysisService()
    report = service.analyze("three-kingdoms-test", chapters)

    char_dict = {c.name: c for c in report.characters}

    # 1. Classical characters correctly identified
    assert "关羽" in char_dict
    guan = char_dict["关羽"]

    # 2. Courtesy names and titles clustered into aliases
    assert any(alias in ("云长", "关公", "关将军") for alias in guan.aliases)
    assert guan.importance_tier in ("protagonist", "major")

    # 3. Liu Bei & Cao Cao & Lu Bu
    assert "曹操" in char_dict
    assert "刘备" in char_dict or "玄德" in char_dict
    assert "吕布" in char_dict

    # 4. Noise suppression in classical texts
    names = set(char_dict.keys())
    assert "忽探子" not in names
    assert "左右" not in names
    assert "诸侯" not in names

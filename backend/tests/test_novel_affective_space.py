from app.application.services.novel_emotional_arc_service import NovelEmotionalArcService


def test_eight_dimensional_affective_space_and_tension_tensor():
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "忠义千秋",
            "content": "关羽按剑傲然而立，威风凛凛，傲视群雄。曹操厚礼相赠，关羽正色言曰：吾受刘皇叔厚恩，誓以死报，忠义之心不可移也！",
        },
        {
            "chapter_id": "c2",
            "chapter_index": 2,
            "title": "怒斩与惊溃",
            "content": "关公大怒，厉声叱曰：鼠辈敢尔！纵马提刀，杀气凛然冲入阵中。敌军大骇，胆裂惊恐，望风大溃！",
        },
    ]

    service = NovelEmotionalArcService()
    arc = service.compute_arc(chapters, character_name="关羽")

    assert "affective_tensor" in arc
    tensor = arc["affective_tensor"]

    # Chapter 1: high in 忠 (loyalty) and 雄 (dominance)
    assert tensor["忠"] > 0.0
    assert tensor["雄"] > 0.0

    # Chapter 2: high in 怒 (anger)
    assert tensor["怒"] > 0.0

    # Verify per-chapter affective vector is present
    c1_traj = arc["trajectory"][0]
    assert "affective_vector" in c1_traj
    assert c1_traj["affective_vector"]["忠"] > 0.0

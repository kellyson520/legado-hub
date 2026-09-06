from app.application.services.novel_character_scoring_service import NovelCharacterScoringService
from app.domain.entities.novel_code_analysis import CharacterCandidate, EvidenceLocation


def test_six_dimensional_capability_matrix_for_legendary_hero():
    # Guan Yu representation in Three Kingdoms
    guan_yu = CharacterCandidate(
        name="关羽",
        normalized="关羽",
        count=45,
        confidence=0.95,
        aliases=["云长", "关公", "关将军", "汉寿亭侯"],
        importance_tier="protagonist",
        centrality=15.0,
        evidence=[EvidenceLocation("c1", 0, 10, "关羽")] * 45,
    )
    items_guan = [
        {"item_name": "青龙偃月刀", "category": "weapon", "action": "used", "chapter_index": 1},
        {"item_name": "赤兔马", "category": "mount", "action": "used", "chapter_index": 2},
    ]
    arc_guan = {
        "trajectory": [
            {"sentiment_score": 2.0, "dominant_emotion": "从容"},
            {"sentiment_score": 1.5, "dominant_emotion": "雄傲"},
        ],
        "turning_points": [{"chapter_index": 2, "delta": 1.5, "shift": "surge"}],
        "affective_tensor": {"喜": 3.0, "怒": 6.0, "哀": 0.0, "惧": 0.0, "忠": 10.0, "雄": 10.0, "疑": 0.0, "溃": 0.0},
    }

    service = NovelCharacterScoringService()
    result = service.evaluate(guan_yu, items_guan, arc_guan)

    # 1. Six-dimensional matrix presence
    assert "capability_matrix" in result
    matrix = result["capability_matrix"]

    assert "武勇绝杀" in matrix
    assert "智谋策论" in matrix
    assert "统御声望" in matrix
    assert "气节风骨" in matrix
    assert "宝器神兵" in matrix
    assert "命途支配" in matrix

    # Guan Yu should excel in combat, loyalty, artifact, and plot centrality
    assert matrix["武勇绝杀"]["score"] >= 85.0
    assert matrix["气节风骨"]["score"] >= 85.0
    assert matrix["宝器神兵"]["score"] >= 80.0
    assert matrix["命途支配"]["score"] >= 85.0

    # 2. Overall tier should achieve SS or SSS
    assert result["overall_tier"] in ("SSS", "SS", "S")

    # 3. Backwards compatibility fields
    assert "plot_impact" in result
    assert "power_score" in result
    assert "mental_score" in result
    assert "radar" in result

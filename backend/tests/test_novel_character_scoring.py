from app.application.services.novel_character_scoring_service import NovelCharacterScoringService
from app.domain.entities.novel_code_analysis import CharacterCandidate, EvidenceLocation


def test_character_scoring_differentiates_protagonist_and_minor_character():
    protagonist = CharacterCandidate(
        name="林弦",
        normalized="林弦",
        count=38,
        confidence=0.9,
        aliases=["小林", "弦哥"],
        importance_tier="protagonist",
        centrality=12.5,
        evidence=[EvidenceLocation("c1", 0, 10, "林弦")] * 38,
    )
    items_lin = [
        {"item_name": "C4炸药", "action": "used", "chapter_index": 2},
        {"item_name": "奥特曼面具", "action": "acquired", "chapter_index": 1},
        {"item_name": "手枪", "action": "used", "chapter_index": 3},
    ]
    arc_lin = {
        "trajectory": [
            {"sentiment_score": 1.5, "dominant_emotion": "从容"},
            {"sentiment_score": -2.0, "dominant_emotion": "恐惧"},
            {"sentiment_score": 2.5, "dominant_emotion": "自信"},
        ],
        "turning_points": [{"chapter_index": 2, "delta": -3.5}, {"chapter_index": 3, "delta": 4.5}],
    }

    minor = CharacterCandidate(
        name="路人甲",
        normalized="路人甲",
        count=2,
        confidence=0.6,
        aliases=[],
        importance_tier="minor",
        centrality=0.5,
        evidence=[EvidenceLocation("c1", 0, 10, "路人甲")] * 2,
    )
    items_minor = []
    arc_minor = {"trajectory": [{"sentiment_score": 0.0, "dominant_emotion": "平静"}], "turning_points": []}

    service = NovelCharacterScoringService()
    score_lin = service.evaluate(protagonist, items_lin, arc_lin)
    score_minor = service.evaluate(minor, items_minor, arc_minor)

    # Protagonist validations
    assert score_lin["overall_tier"] in ("S", "A")
    assert score_lin["plot_impact"] >= 80.0
    assert score_lin["power_score"] >= 65.0
    assert score_lin["mental_score"] >= 70.0

    # Minor validations
    assert score_minor["overall_tier"] in ("C", "B")
    assert score_minor["plot_impact"] < 40.0
    assert score_minor["power_score"] < 40.0

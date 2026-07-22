from app.domain.entities.novel import (
    EntityType,
    EventType,
    NovelEntity,
    NovelEvent,
    NovelStateChange,
    StateField,
)


def test_entity_memory_card_contains_bounded_identity_attributes_and_evidence():
    from app.application.services.novel_understanding.memory_cards import entity_memory_card

    card = entity_memory_card(
        NovelEntity(
            name="玄天剑",
            entity_type=EntityType.ITEM,
            aliases=["古剑"],
            first_appearance_ch=0,
            last_appearance_ch=8,
            appearance_count=4,
            importance_score=5,
            attributes={
                "subtype": "weapon",
                "confidence": 0.91,
                "evidence": [{"chapter_id": 0, "text": "江轩取出玄天剑"}],
            },
        )
    )

    assert "玄天剑" in card
    assert "古剑" in card
    assert "item" in card
    assert "0-8" in card
    assert "江轩取出玄天剑" in card
    assert len(card) <= 1200


def test_event_and_state_memory_cards_keep_chapter_and_evidence_context():
    from app.application.services.novel_understanding.memory_cards import (
        event_memory_card,
        state_memory_card,
    )

    event_card = event_memory_card(
        NovelEvent(
            chapter_id=0,
            chapter_num=0,
            event_type=EventType.DISCOVERY,
            description="江轩发现玄天剑",
            participants=["江轩"],
            evidence=[{"chapter_id": 0, "text": "石匣中露出剑柄"}],
        )
    )
    state_card = state_memory_card(
        NovelStateChange(
            entity_name="玄天剑",
            chapter_id=0,
            chapter_num=0,
            field_name=StateField.POSSESSION,
            before_value="无人持有",
            after_value="江轩",
            trigger_event="发现",
            evidence=[{"chapter_id": 0, "text": "江轩握住剑柄"}],
        )
    )

    assert "第0章" in event_card
    assert "石匣中露出剑柄" in event_card
    assert "玄天剑" in state_card
    assert "无人持有" in state_card and "江轩" in state_card
    assert "江轩握住剑柄" in state_card

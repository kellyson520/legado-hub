from app.domain.entities.novel import EntityType


def test_local_extractor_rejects_sentence_fragments_and_keeps_evidence_backed_name():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        0,
        "序章",
        "江轩赶到门前。江轩很谨慎，江轩说：‘先等等。’周宁看向江轩。",
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert "江轩" in names
    assert "江轩很" not in names
    assert "江轩赶" not in names
    assert "周围的" not in names


def test_local_extractor_recognizes_an_item_from_name_and_action_context():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        1,
        "得剑",
        "江轩从石匣中取出玄天剑，剑身泛起寒光。他握住玄天剑冲向黑衣人。",
    )

    item = next(entity for entity in entities if entity.name == "玄天剑")
    assert item.entity_type == EntityType.ITEM
    assert item.appearance_count == 2
    assert item.attributes["evidence"]


def test_local_extractor_does_not_create_cartesian_relationships():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    _, relationships = AutoExtractor().extract_from_chapter(
        8,
        1,
        "会面",
        "江轩与周宁并肩作战。赵明在远处观望。",
    )

    pairs = {(item.source_entity, item.target_entity) for item in relationships}
    assert ("江轩", "周宁") in pairs or ("周宁", "江轩") in pairs
    assert ("江轩", "赵明") not in pairs
    assert all(getattr(item, "evidence", []) for item in relationships)

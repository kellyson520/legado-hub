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


def test_learning_profile_applies_aliases_negative_terms_and_bounded_feature_weights():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    extractor = AutoExtractor(
        {
            "profile_version": "learning-v1:test",
            "aliases": {"小轩": "江轩"},
            "negative_terms": ["江边"],
            "feature_weights": {"explicit_name": 1.5},
        }
    )
    entities, _ = extractor.extract_from_chapter(
        8,
        1,
        "人物",
        "他自称小轩，随后江边没有回应。",
    )

    names = {item.name for item in entities}
    assert "江轩" in names
    assert "小轩" not in names
    assert "江边" not in names
    entity = next(item for item in entities if item.name == "江轩")
    assert entity.aliases == ["小轩"]
    assert entity.attributes["learning_profile_version"] == "learning-v1:test"
    assert entity.attributes["confidence"] == 1.0


def test_local_extractor_keeps_explicit_names_and_rejects_embedded_fragments_and_titles():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        0,
        "第一章",
        (
            "侍女名为沈秋奴，女帝让生下的儿子随父姓，取名江轩。"
            "沈秋奴也算这座宅邸的半个女主人，与江轩算是处在兄妹与恋人之间。"
            "容颜清丽的少女被当作江轩的贴身侍卫培育，江轩很谨慎。"
            "这般好郎君坐在府中，诞下一子后便离开。"
        ),
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert {"沈秋奴", "江轩"}.issubset(names)
    assert not names.intersection(
        {
            "卫培育",
            "颜清丽",
            "江轩算",
            "郎君",
            "诞下一子",
            "的臭婊子",
        }
    )


def test_relationship_evidence_uses_the_real_chapter_and_cue_window():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    _, relationships = AutoExtractor().extract_with_evidence(
        8,
        0,
        "第一章",
        "侍女名为沈秋奴。为了保护孩子，女帝让生下的儿子取名江轩。沈秋奴与江轩算是兄妹与恋人。",
        chapter_id=803,
    )

    pairs = {(item.source_entity, item.target_entity) for item in relationships}
    assert ("沈秋奴", "江轩") in pairs or ("江轩", "沈秋奴") in pairs
    assert ("保护孩子", "江轩") not in pairs
    for relationship in relationships:
        assert relationship.evidence[0]["chapter_id"] == 803


def test_relationship_extraction_ignores_distant_cues_in_the_same_sentence():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    _, relationships = AutoExtractor().extract_with_evidence(
        8,
        0,
        "第一章",
        "江轩轻声说道纳兰孤寒既是女帝的师傅也是他的师傅随后叶青鸾赶到。",
        chapter_id=803,
    )

    pairs = {(item.source_entity, item.target_entity) for item in relationships}
    assert ("江轩", "叶青鸾") not in pairs
    assert ("叶青鸾", "江轩") not in pairs


def test_repeated_long_names_are_not_persisted_as_short_prefixes():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        0,
        "第一章",
        (
            "叶青鸾走进医馆，叶青鸾看向江轩。周大牛随后赶到，周大牛没有说话。"
            "秦厌离正在巡视边境，秦厌离神情威严。叶姑娘与秦元帅都在府中，任由风吹过。"
            "江轩不愿久留，江轩面向城门，江轩无声地离开。江轩不愿回头，江轩面向远方，江轩无声等待。"
            "平日里风平浪静，平日里无人来访。"
        ),
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert {"叶青鸾", "周大牛", "秦厌离", "江轩"}.issubset(names)
    assert not names.intersection(
        {
            "叶青",
            "周大",
            "秦厌",
            "叶姑",
            "秦元帅",
            "任由",
            "江轩不",
            "江轩面",
            "江轩无",
            "平日里",
        }
    )


def test_single_weak_surname_hits_are_dropped_before_adjudication():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        0,
        "第一章",
        "方才风停了，高呼声从远处传来，明天再出发，凌辱二字写在纸上。",
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert not names.intersection({"方才", "高呼", "明天", "凌辱"})


def test_repeated_non_names_do_not_survive_surname_scanning_or_prefix_fallback():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8,
        0,
        "第一章",
        (
            "方才风停了，方才无人回应。平日里生意火爆，平日里少有人来。"
            "江兄请留步，江兄稍候。与寻常百姓无异，与寻常百姓无异。"
            "他姓李白，李白点头。"
        ),
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert "李白" in names
    assert not names.intersection({"方才", "平日里", "平日", "江兄", "无异"})

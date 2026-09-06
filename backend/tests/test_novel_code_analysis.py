from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService


def test_code_analysis_extracts_characters_time_mentions_and_evidence():
    report = NovelCodeAnalysisService().analyze(
        "work-1",
        [
            {
                "chapter_id": "c1",
                "chapter_index": 1,
                "title": "雨夜",
                "content": "林默在子时抵达长安。苏晚看见林默，三天后他们在城门重逢。",
            }
        ],
    )

    assert "林默" in [item.name for item in report.characters]
    assert any(item.normalized == "子时" for item in report.time_mentions)
    assert any(
        item.normalized == "三天后" and item.anchor_status == "unresolved"
        for item in report.time_mentions
    )
    assert report.characters[0].evidence[0].chapter_id == "c1"
    assert report.characters[0].evidence[0].start_offset == 0
    assert report.characters[0].evidence[0].end_offset == 2
    assert report.cooccurrences[0].count >= 1
    assert any(event.trigger == "重逢" for event in report.events)


def test_same_content_hash_returns_cached_report_without_reextracting():
    service = NovelCodeAnalysisService()
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "一",
            "content": "林默进入长安。",
        }
    ]

    first = service.analyze("work-1", chapters)
    second = service.analyze("work-1", chapters)

    assert first.content_sha256 == second.content_sha256
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.characters == first.characters


def test_cached_report_isolated_from_mutating_first_result_lists():
    service = NovelCodeAnalysisService()
    chapters = [
        {
            "chapter_id": "c1",
            "chapter_index": 1,
            "title": "一",
            "content": "林默进入长安。",
        }
    ]

    first = service.analyze("cache-isolation", chapters)
    first.characters[0].evidence.append(first.characters[0].evidence[0])
    first.characters.append(first.characters[0])
    second = service.analyze("cache-isolation", chapters)

    assert second.cache_hit is True
    assert len(second.characters) == 1
    assert len(second.characters[0].evidence) == 1


def test_year_mention_keeps_full_text_and_starts_at_digit_boundary():
    report = NovelCodeAnalysisService().analyze(
        "absolute-year",
        [
            {
                "chapter_id": "c1",
                "chapter_index": 1,
                "title": "一",
                "content": "2024年，林默进入长安。",
            }
        ],
    )

    mention = next(item for item in report.time_mentions if item.normalized == "2024年")
    assert mention.evidence[0].start_offset == 0
    assert mention.evidence[0].end_offset == 5
    assert not any(item.normalized == "24年" for item in report.time_mentions)


def test_cooccurrences_use_repeated_fixed_windows_not_whole_chapter():
    report = NovelCodeAnalysisService().analyze(
        "windowed-cooccurrence",
        [
            {
                "chapter_id": "c1",
                "chapter_index": 1,
                "title": "一",
                "content": (
                    "林默进入长安。" + "甲" * 90 + "苏晚离开城门。"
                    + "林默与苏晚战斗。"
                ),
            }
        ],
    )

    pair = next(item for item in report.cooccurrences if item.left == "林默" and item.right == "苏晚")
    assert pair.count == 1
    assert all(item.start_offset >= 100 for item in pair.evidence)
    assert all(item.end_offset <= 116 for item in pair.evidence)


def test_analysis_extracts_events_and_time_offsets_deterministically():
    report = NovelCodeAnalysisService().analyze(
        "work-2",
        [
            {
                "chapter_id": "c9",
                "chapter_index": 9,
                "title": "决战",
                "content": "翌日，沈砚决定离开。半刻后，沈砚与顾宁战斗。",
            }
        ],
    )

    assert report.content_sha256
    assert {event.trigger for event in report.events} >= {"决定", "离开", "战斗"}
    assert all(item.evidence for item in report.events)
    assert all(item.evidence for item in report.time_mentions)
    assert all(item.evidence[0].chapter_id == "c9" for item in report.time_mentions)
    assert any(pair.left == "沈砚" and pair.right == "顾宁" for pair in report.cooccurrences)

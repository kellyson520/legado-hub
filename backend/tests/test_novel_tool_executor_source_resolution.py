import pytest
from app.application.services.novel_analysis_tool_executor import NovelAnalysisToolExecutor


def test_optional_source_ids_accepts_strings_and_ints():
    # Should accept mixed list of ints, string numbers, and UUID strings without throwing ValueError
    raw = [1, "2", "341a4b2671be489f912de3b540deac8b", 341]
    parsed = NovelAnalysisToolExecutor._optional_source_ids(raw)
    assert parsed == [1, 2, "341a4b2671be489f912de3b540deac8b", 341]


def test_optional_source_ids_single_item_or_none():
    assert NovelAnalysisToolExecutor._optional_source_ids(None) is None
    assert NovelAnalysisToolExecutor._optional_source_ids(42) == [42]
    assert NovelAnalysisToolExecutor._optional_source_ids("42") == [42]

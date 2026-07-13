"""
ChapterTitleParser + ChapterCanonicalMapper + ChapterAligner + SourceHealth + QualityGates 测试
"""

import pytest

from app.domain.value_objects import (
    ParsedChapterTitle, ChapterType, QualityGateResult, AlignmentResult
)
from app.domain.services.chapter_parser import ChapterTitleParser
from app.domain.services.chapter_mapper import ChapterCanonicalMapper
from app.domain.services.chapter_aligner import CrossSourceChapterAligner
from app.domain.services.source_health import SourceHealthScore
from app.domain.services.quality_gates import QualityGates
from app.domain.entities.novel import NovelChapter, NovelSourceMirror


class TestChapterTitleParser:
    """章节标题解析器测试"""

    def test_arabic_chapter(self):
        r = ChapterTitleParser.parse("第1章 初入宗门")
        assert r.is_valid
        assert r.num == 1
        assert r.core_title == "初入宗门"
        assert r.chapter_type == ChapterType.MAIN

    def test_chinese_chapter(self):
        r = ChapterTitleParser.parse("第一百章 大结局")
        assert r.is_valid
        assert r.num == 100
        assert r.raw_num_str == "一百"

    def test_chapter_complex_chinese(self):
        r = ChapterTitleParser.parse("第一千零五章 突破")
        assert r.is_valid
        assert r.num == 1005

    def test_prologue(self):
        r = ChapterTitleParser.parse("楔子 命运的齿轮")
        assert r.is_valid
        assert r.chapter_type == ChapterType.PROLOGUE
        assert r.num == 0

    def test_extra(self):
        r = ChapterTitleParser.parse("番外一 婚后生活")
        assert r.is_valid
        assert r.chapter_type == ChapterType.EXTRA
        assert r.num == 1

    def test_epilogue(self):
        r = ChapterTitleParser.parse("后记")
        assert r.is_valid
        assert r.chapter_type == ChapterType.EPILOGUE

    def test_split_chapter(self):
        r = ChapterTitleParser.parse("第100章（上）")
        assert r.is_valid
        assert r.num == 100
        assert r.raw_num_str == "100-上"

    def test_volume_chapter(self):
        r = ChapterTitleParser.parse("第二卷 第10章 新的挑战")
        assert r.is_valid
        assert r.volume == "二"
        assert r.num == 10

    def test_pure_arabic(self):
        r = ChapterTitleParser.parse("123 这是标题")
        assert r.is_valid
        assert r.num == 123
        assert r.core_title == "这是标题"

    def test_empty_title(self):
        r = ChapterTitleParser.parse("")
        assert not r.is_valid

    def test_unknown_title(self):
        r = ChapterTitleParser.parse("一些无关文字")
        assert not r.is_valid

    def test_chinese_to_int(self):
        assert ChapterTitleParser.chinese_to_int("一") == 1
        assert ChapterTitleParser.chinese_to_int("十") == 10
        assert ChapterTitleParser.chinese_to_int("十一") == 11
        assert ChapterTitleParser.chinese_to_int("一百二十三") == 123
        assert ChapterTitleParser.chinese_to_int("一千零五") == 1005
        assert ChapterTitleParser.chinese_to_int("一万") == 10000


class TestChapterCanonicalMapper:
    """章节标准化映射测试"""

    def test_map_simple_chapter(self):
        ch = ChapterCanonicalMapper.map_single("第1章 初入宗门")
        assert ch.canonical_type == "C"
        assert ch.canonical_num == 1
        assert ch.canonical_full == "C1"
        assert ch.chapter_title == "初入宗门"

    def test_map_prologue(self):
        ch = ChapterCanonicalMapper.map_single("楔子")
        assert ch.canonical_type == "P"
        assert ch.canonical_num == 0
        assert ch.canonical_full == "P0"

    def test_map_extra(self):
        ch = ChapterCanonicalMapper.map_single("番外三")
        assert ch.canonical_type == "X"
        assert ch.canonical_num == 3
        assert ch.canonical_full == "X3"

    def test_map_volume_chapter(self):
        ch = ChapterCanonicalMapper.map_single("第二卷 第5章 修炼")
        assert ch.canonical_type == "C"
        assert ch.canonical_num == 55  # 50 + 5
        assert ch.canonical_full == "C55"

    def test_map_batch(self):
        titles = ["第1章 A", "第2章 B", "楔子"]
        chapters = ChapterCanonicalMapper.map_batch(titles)
        assert len(chapters) == 3
        assert chapters[0].canonical_full == "C1"
        assert chapters[1].canonical_full == "C2"
        assert chapters[2].canonical_full == "P0"


class TestCrossSourceChapterAligner:
    """跨书源对齐测试"""

    def test_perfect_match(self):
        source = [
            NovelChapter(chapter_num=1, canonical_full="C1", parsed_title_core="初入宗门", word_count=3000),
            NovelChapter(chapter_num=2, canonical_full="C2", parsed_title_core="修炼", word_count=3200),
        ]
        target = [
            NovelChapter(chapter_num=1, canonical_full="C1", parsed_title_core="初入宗门", word_count=3000),
            NovelChapter(chapter_num=2, canonical_full="C2", parsed_title_core="修炼", word_count=3200),
        ]
        result = CrossSourceChapterAligner.align(source, target)
        assert len(result.matches) == 2
        assert result.matches[0][2] == 1.0  # confidence 1.0

    def test_title_match(self):
        source = [NovelChapter(chapter_num=1, canonical_full="", parsed_title_core="突破", word_count=0)]
        target = [NovelChapter(chapter_num=1, canonical_full="", parsed_title_core="突破", word_count=0)]
        result = CrossSourceChapterAligner.align(source, target)
        assert len(result.matches) == 1
        assert result.matches[0][2] == 0.9

    def test_partial_match(self):
        source = [
            NovelChapter(chapter_num=1, canonical_full="C1", parsed_title_core="A", word_count=3000),
            NovelChapter(chapter_num=2, canonical_full="C2", parsed_title_core="B", word_count=3100),
        ]
        target = [
            NovelChapter(chapter_num=1, canonical_full="C1", parsed_title_core="A", word_count=3000),
        ]
        result = CrossSourceChapterAligner.align(source, target)
        assert len(result.matches) == 1
        assert result.unmatched_source == [1]
        assert result.unmatched_target == []

    def test_no_match(self):
        source = [NovelChapter(chapter_num=1, canonical_full="C1", parsed_title_core="A", word_count=3000)]
        target = [NovelChapter(chapter_num=100, canonical_full="C100", parsed_title_core="Z", word_count=500)]
        result = CrossSourceChapterAligner.align(source, target)
        assert len(result.matches) == 0


class TestSourceHealthScore:
    """书源健康评分测试"""

    def test_perfect_source(self):
        mirror = NovelSourceMirror(
            total_chapters_available=100, chapters_fetched=100,
            avg_response_ms=500, failure_count=0
        )
        assert SourceHealthScore.calculate(mirror) == 100.0
        assert SourceHealthScore.determine_status(mirror) == "active"

    def test_degraded_source(self):
        mirror = NovelSourceMirror(
            total_chapters_available=100, chapters_fetched=50,
            avg_response_ms=2000, failure_count=6
        )
        score = SourceHealthScore.calculate(mirror)
        assert score < 50
        assert SourceHealthScore.determine_status(mirror) == "degraded"

    def test_failed_source(self):
        mirror = NovelSourceMirror(
            total_chapters_available=100, chapters_fetched=10,
            avg_response_ms=10000, failure_count=12
        )
        assert SourceHealthScore.determine_status(mirror) == "failed"


class TestQualityGates:
    """五道质量门测试"""

    def test_g1_short_text(self):
        result = QualityGates.g1_fetch_gate("短")
        assert not result.passed
        assert any("过短" in i for i in result.issues)

    def test_g1_garbled(self):
        result = QualityGates.g1_fetch_gate("内容��有��乱码�字��符")
        assert not result.passed
        assert any("乱码" in i for i in result.issues)

    def test_g2_ad_detection(self):
        result = QualityGates.g2_clean_gate("正文\n加入书签\n下一章")
        assert not result.passed
        assert any("广告" in i for i in result.issues)

    def test_g2_water(self):
        text = "重复\n" * 20 + "正文\n"
        result = QualityGates.g2_clean_gate(text)
        assert not result.passed
        assert any("重复" in i for i in result.issues)

    def test_g3_title_missing(self):
        ch = NovelChapter(chapter_title="不存在的标题")
        result = QualityGates.g3_parse_gate(ch, "完全不同的正文内容")
        assert not result.passed

    def test_g4_short_chapter(self):
        ch = NovelChapter(word_count=100)
        result = QualityGates.g4_fingerprint_gate(ch)
        assert not result.passed
        assert any("字数" in i for i in result.issues)

    def test_g5_invalid_canonical(self):
        ch = NovelChapter(canonical_num=0, canonical_type="C")
        result = QualityGates.g5_global_gate(ch)
        assert not result.passed

    def test_all_gates_pass(self):
        ch = NovelChapter(canonical_num=1, canonical_type="C", chapter_title="第一章")
        results = QualityGates.run_all(ch, "第一章 这是正文内容，足够长，没有任何问题。" * 50)
        assert all(r.passed for r in results)

    def test_all_gates_some_fail(self):
        ch = NovelChapter(canonical_num=0, canonical_type="C")
        results = QualityGates.run_all(ch, "短")
        assert not all(r.passed for r in results)

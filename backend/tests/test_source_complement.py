"""
书源互补功能单元测试

覆盖：
- ContentComparator 内容相似度计算
- ContentQualityEstimator 内容质量评估
- ContentMerger 多源内容合并（三种策略）
- SourceComplementService 书源互补服务
- 领域事件定义
"""

import pytest
import asyncio
from typing import Dict, Any

from app.domain.services.content_merger import (
    ContentComparator,
    ContentQualityEstimator,
    ContentMerger,
    ContentMergeResult,
    ContentQuality,
)
from app.domain.services.source_complement import (
    SourceComplementService,
    SourceFetchResult,
    ComplementResult,
)
from app.core.events import (
    ChapterComplementRequestedEvent,
    ChapterFetchedFromSourceEvent,
    ChapterComplementCompletedEvent,
    SourceComplementProgressEvent,
)


# ==================== ContentComparator 测试 ====================

class TestContentComparator:
    """内容对比器测试"""

    def test_identical_text_similarity_is_one(self):
        """相同文本相似度应为 1.0"""
        text = "这是一段测试文本。它有多个句子。每个句子都有意义。"
        assert ContentComparator.similarity(text, text) == pytest.approx(1.0, abs=0.01)

    def test_empty_text_similarity_is_zero(self):
        """空文本相似度应为 0"""
        assert ContentComparator.similarity("", "") == 0.0
        assert ContentComparator.similarity("hello", "") == 0.0
        assert ContentComparator.similarity("", "world") == 0.0

    def test_similar_texts_high_similarity(self):
        """相似文本应有较高相似度"""
        text_a = "张三走在街上，看到了李四。两人寒暄了几句。"
        text_b = "张三走在街上，看到了李四。两人聊了几句。"
        sim = ContentComparator.similarity(text_a, text_b)
        assert sim > 0.5

    def test_different_texts_low_similarity(self):
        """完全不同的文本应有较低相似度"""
        text_a = "今天天气真好，阳光明媚，适合出去散步。"
        text_b = "量子力学是物理学的一个分支，研究微观粒子的运动规律。"
        sim = ContentComparator.similarity(text_a, text_b)
        assert sim < 0.3

    def test_ngram_jaccard(self):
        """n-gram Jaccard 相似度"""
        sim = ContentComparator._ngram_jaccard("abcde", "abxyz", 2)
        # "ab", "bc", "cd", "de" vs "ab", "bx", "xy", "yz"
        # intersection: {"ab"}, union: 7
        assert 0 < sim < 0.5

    def test_sentence_overlap(self):
        """句子重叠率"""
        text_a = "今天天气真好。我们一起出去玩。晚上再回来吃饭。明天继续工作。"
        text_b = "今天天气真好。我们在家看书。晚上再回来吃饭。后天去旅行。"
        sim = ContentComparator._sentence_overlap(text_a, text_b)
        assert sim >= 0.3


# ==================== ContentQualityEstimator 测试 ====================

class TestContentQualityEstimator:
    """内容质量评估器测试"""

    def test_empty_content_zero_score(self):
        """空内容质量分为 0"""
        q = ContentQualityEstimator.evaluate("")
        assert q.score == 0.0
        assert q.word_count == 0

    def test_normal_chapter_good_score(self):
        """正常章节应有较高分数"""
        content = (
            "第一章 初入江湖\n\n"
            "张三背着行囊，踏上了去往京城的路。\n\n"
            "他心中充满了对未来的憧憬，也带着一丝忐忑不安。\n\n"
            "走了三天三夜，终于看到了京城的城墙。\n\n"
            "城门口人来人往，热闹非凡。张三深吸一口气，迈步走了进去。\n\n"
            "这是一个新的开始，他的江湖生涯从此刻正式开启。\n\n"
            "（本章完）"
        )
        q = ContentQualityEstimator.evaluate(content)
        assert q.score > 50.0
        assert q.word_count > 100
        assert q.paragraph_count >= 5
        assert q.completeness > 0.5

    def test_short_content_low_score(self):
        """极短内容完整度低"""
        q = ContentQualityEstimator.evaluate("太短了")
        # 短内容字数分低，但完整性也低
        assert q.completeness < 0.8
        assert q.word_count < 10

    def test_ad_content_penalty(self):
        """含广告内容分数降低"""
        clean_text = (
            "张三走在街上。他看到了一家书店。书店里有很多书。"
            "他走了进去，挑选了一本小说。付了钱之后，他高兴地离开了。"
        ) * 10
        ad_text = clean_text + "\n\n百度搜索 最快更新 笔趣阁 https://example.com"
        q_clean = ContentQualityEstimator.evaluate(clean_text)
        q_ad = ContentQualityEstimator.evaluate(ad_text)
        assert q_ad.score < q_clean.score

    def test_quality_has_all_fields(self):
        """质量评估返回所有字段"""
        q = ContentQualityEstimator.evaluate("测试内容。这是一个段落。")
        assert isinstance(q.score, float)
        assert isinstance(q.word_count, int)
        assert isinstance(q.paragraph_count, int)
        assert isinstance(q.error_estimate, float)
        assert isinstance(q.completeness, float)
        assert 0.0 <= q.score <= 100.0


# ==================== ContentMerger 测试 ====================

SAMPLE_SOURCES = [
    {
        "source_url": "https://source-a.com",
        "source_name": "源A",
        "content": (
            "第一章 测试\n\n"
            "张三走在街上，看到了李四。两人寒暄了几句，然后各自离去。\n\n"
            "张三继续往前走，心里想着刚才的对话。\n\n"
            "这是一段完整的章节内容，有开头有结尾。\n\n"
            "（本章完）"
        ),
        "word_count": 100,
    },
    {
        "source_url": "https://source-b.com",
        "source_name": "源B",
        "content": (
            "第一章 测试\n\n"
            "张三走在街上，看到了李四。两人寒暄了几句，然后各自离去。\n\n"
            "张三继续往前走，心里想着刚才的对话。\n\n"
            "这是一段完整的章节内容，有开头有结尾。\n\n"
            "（本章完）"
        ),
        "word_count": 100,
    },
    {
        "source_url": "https://source-c.com",
        "source_name": "源C",
        "content": (
            "第一章 测试\n\n"
            "张三走在街上看见李四，两人聊了几句就走了。\n\n"
            "张三继续走，想着刚才的话。\n\n"
            "本章完。"
        ),
        "word_count": 60,
    },
]


class TestContentMerger:
    """内容合并器测试"""

    def test_merge_empty_sources(self):
        """空来源返回空结果"""
        result = ContentMerger.merge([])
        assert result.content == ""
        assert result.quality_score == 0.0
        assert result.word_count == 0

    def test_merge_single_source(self):
        """单源直接返回"""
        sources = [SAMPLE_SOURCES[0]]
        result = ContentMerger.merge(sources)
        assert result.content == SAMPLE_SOURCES[0]["content"]
        assert result.merged_from == [SAMPLE_SOURCES[0]["source_url"]]
        assert result.word_count > 0

    def test_best_strategy_picks_highest_quality(self):
        """best 策略取质量最高的"""
        result = ContentMerger.merge(SAMPLE_SOURCES, strategy="best")
        assert result.merge_strategy == "best"
        assert result.merged_from
        assert len(result.merged_from) == 1
        assert result.word_count > 0

    def test_majority_strategy(self):
        """majority 策略：相似内容聚类"""
        result = ContentMerger.merge(SAMPLE_SOURCES, strategy="majority")
        assert result.merge_strategy == "majority"
        # 源A和源B内容相同，应该在同一聚类
        assert len(result.merged_from) >= 2
        assert "https://source-a.com" in result.merged_from
        assert "https://source-b.com" in result.merged_from

    def test_hybrid_strategy(self):
        """hybrid 策略默认使用"""
        result = ContentMerger.merge(SAMPLE_SOURCES, strategy="hybrid")
        assert result.merge_strategy in ("majority", "hybrid")
        assert result.quality_score > 0

    def test_merge_result_has_all_fields(self):
        """合并结果包含所有字段"""
        result = ContentMerger.merge(SAMPLE_SOURCES)
        assert isinstance(result, ContentMergeResult)
        assert isinstance(result.content, str)
        assert isinstance(result.quality_score, float)
        assert isinstance(result.word_count, int)
        assert isinstance(result.merged_from, list)
        assert isinstance(result.source_scores, dict)
        assert isinstance(result.merge_strategy, str)

    def test_source_scores_populated(self):
        """source_scores 包含所有来源"""
        result = ContentMerger.merge(SAMPLE_SOURCES, strategy="best")
        for s in SAMPLE_SOURCES:
            assert s["source_url"] in result.source_scores


# ==================== SourceComplementService 测试 ====================

async def mock_fetch_success(source_url: str, chapter_info: Dict[str, Any]):
    """模拟成功抓取"""
    await asyncio.sleep(0.01)
    content = (
        f"第{chapter_info.get('chapter_num', 0)}章 "
        f"{chapter_info.get('chapter_title', '')}\n\n"
        f"来自 {source_url} 的章节正文。张三走在街上，看到了李四。\n\n"
        f"两人寒暄了几句。然后各自离去。\n\n"
        f"张三继续往前走，心里想着刚才的对话。\n\n"
        f"（本章完）"
    )
    return SourceFetchResult(
        source_url=source_url,
        source_name=f"书源_{source_url[-6:]}",
        success=True,
        content=content,
        word_count=len(content),
        chapter_title=chapter_info.get("chapter_title", ""),
        chapter_num=chapter_info.get("chapter_num", 0),
    )


async def mock_fetch_fail(source_url: str, chapter_info: Dict[str, Any]):
    """模拟失败抓取"""
    await asyncio.sleep(0.01)
    return SourceFetchResult(
        source_url=source_url,
        success=False,
        error="Connection refused",
        chapter_title=chapter_info.get("chapter_title", ""),
        chapter_num=chapter_info.get("chapter_num", 0),
    )


async def mock_fetch_mixed(source_url: str, chapter_info: Dict[str, Any]):
    """混合模式：部分源成功部分失败"""
    if "fail" in source_url:
        return await mock_fetch_fail(source_url, chapter_info)
    return await mock_fetch_success(source_url, chapter_info)


class TestSourceComplementService:
    """书源互补服务测试"""

    def test_complement_with_multiple_sources(self):
        """多源互补测试"""
        service = SourceComplementService(
            fetch_fn=mock_fetch_success,
            max_concurrent=3,
            merge_strategy="hybrid",
        )

        async def _run():
            return await service.complement_chapter(
                book_name="测试小说",
                chapter_title="初入江湖",
                chapter_num=1,
                source_urls=[
                    "https://source-a.com",
                    "https://source-b.com",
                    "https://source-c.com",
                ],
                publish_events=False,
            )

        result = asyncio.run(_run())

        assert isinstance(result, ComplementResult)
        assert result.book_name == "测试小说"
        assert result.chapter_title == "初入江湖"
        assert result.chapter_num == 1
        assert result.total_sources == 3
        assert result.successful_sources == 3
        assert result.failed_sources == 0
        assert result.final_content
        assert result.final_word_count > 0
        assert result.quality_score > 0
        assert result.status == "success"
        assert len(result.source_results) == 3
        assert result.elapsed_ms >= 0

    def test_complement_with_reference_content(self):
        """带参考内容的互补"""
        service = SourceComplementService(fetch_fn=mock_fetch_success)

        ref_content = (
            "第一章 初入江湖\n\n"
            "张三走在街上，看到了李四。两人寒暄了几句。\n\n"
            "（本章完）"
        )

        async def _run():
            return await service.complement_chapter(
                book_name="测试小说",
                chapter_title="初入江湖",
                chapter_num=1,
                source_urls=["https://source-a.com"],
                reference_content=ref_content,
                publish_events=False,
            )

        result = asyncio.run(_run())

        assert result.status == "success"
        assert result.final_content
        assert "reference" in result.merged_from or len(result.merged_from) >= 1

    def test_complement_with_failed_sources(self):
        """部分源失败的情况"""
        service = SourceComplementService(fetch_fn=mock_fetch_mixed)

        async def _run():
            return await service.complement_chapter(
                book_name="测试小说",
                chapter_title="测试章节",
                chapter_num=5,
                source_urls=[
                    "https://good-1.com",
                    "https://fail-1.com",
                    "https://good-2.com",
                    "https://fail-2.com",
                ],
                publish_events=False,
            )

        result = asyncio.run(_run())

        assert result.total_sources == 4
        assert result.successful_sources == 2
        assert result.failed_sources == 2
        assert result.status == "partial"
        assert result.final_content

    def test_complement_all_failed(self):
        """所有源都失败且无参考内容"""
        service = SourceComplementService(fetch_fn=mock_fetch_fail)

        async def _run():
            return await service.complement_chapter(
                book_name="测试小说",
                chapter_title="测试章节",
                chapter_num=3,
                source_urls=[
                    "https://fail-1.com",
                    "https://fail-2.com",
                ],
                publish_events=False,
            )

        result = asyncio.run(_run())

        assert result.status == "failed"
        assert result.successful_sources == 0
        assert result.final_content == ""

    def test_concurrency_control(self):
        """并发控制：最大并发数限制"""
        service = SourceComplementService(
            fetch_fn=mock_fetch_success,
            max_concurrent=2,
        )

        async def _run():
            return await service.complement_chapter(
                book_name="测试",
                chapter_title="测试",
                chapter_num=1,
                source_urls=[f"https://src-{i}.com" for i in range(5)],
                publish_events=False,
            )

        result = asyncio.run(_run())

        assert result.total_sources == 5
        assert result.successful_sources == 5

    def test_complement_result_has_job_id(self):
        """每个任务有唯一 job_id"""
        service = SourceComplementService(fetch_fn=mock_fetch_success)

        async def _run():
            r1 = await service.complement_chapter(
                "测试", "章节1", 1, ["https://a.com"], publish_events=False,
            )
            r2 = await service.complement_chapter(
                "测试", "章节2", 2, ["https://b.com"], publish_events=False,
            )
            return r1, r2

        r1, r2 = asyncio.run(_run())

        assert r1.job_id != r2.job_id
        assert r1.job_id.startswith("comp_")

    def test_align_chapters_across_sources(self):
        """多源章节目录对齐"""
        from app.domain.entities.novel import NovelChapter

        source_a = [
            NovelChapter(chapter_num=1, chapter_title="第一章", raw_title="第一章 初入"),
            NovelChapter(chapter_num=2, chapter_title="第二章", raw_title="第二章 相遇"),
            NovelChapter(chapter_num=3, chapter_title="第三章", raw_title="第三章 离别"),
        ]
        source_b = [
            NovelChapter(chapter_num=1, chapter_title="第1章", raw_title="第1章 初入江湖"),
            NovelChapter(chapter_num=2, chapter_title="第2章", raw_title="第2章 不期而遇"),
            NovelChapter(chapter_num=3, chapter_title="第3章", raw_title="第3章 分别"),
            NovelChapter(chapter_num=4, chapter_title="第4章", raw_title="第4章 番外"),
        ]

        aligned = SourceComplementService.align_chapters_across_sources({
            "source_a": source_a,
            "source_b": source_b,
        })

        assert isinstance(aligned, dict)
        assert len(aligned) >= 3  # 至少对齐3章


# ==================== 领域事件测试 ====================

class TestComplementEvents:
    """书源互补领域事件测试"""

    def test_request_event_creation(self):
        """请求事件创建"""
        evt = ChapterComplementRequestedEvent(
            job_id="test_001",
            book_name="测试小说",
            chapter_title="第一章",
            chapter_num=1,
            source_urls=["https://a.com", "https://b.com"],
        )
        assert evt.event_type() == "ChapterComplementRequestedEvent"
        assert evt.job_id == "test_001"
        assert len(evt.source_urls) == 2
        assert evt.event_id
        assert evt.timestamp

    def test_fetch_event_creation(self):
        """单源抓取事件"""
        evt = ChapterFetchedFromSourceEvent(
            job_id="test_001",
            source_url="https://a.com",
            source_name="源A",
            chapter_title="第一章",
            chapter_num=1,
            content="测试内容",
            word_count=100,
            success=True,
            response_time_ms=150,
        )
        assert evt.success is True
        assert evt.word_count == 100

    def test_completed_event_creation(self):
        """完成事件"""
        evt = ChapterComplementCompletedEvent(
            job_id="test_001",
            book_name="测试",
            chapter_title="第一章",
            chapter_num=1,
            total_sources=3,
            successful_sources=2,
            final_content="合并后的内容",
            final_word_count=500,
            quality_score=85.5,
            status="partial",
            merged_from=["https://a.com", "https://b.com"],
        )
        assert evt.status == "partial"
        assert evt.successful_sources == 2
        assert len(evt.merged_from) == 2

    def test_progress_event_creation(self):
        """进度事件"""
        evt = SourceComplementProgressEvent(
            job_id="test_001",
            total_sources=10,
            completed_sources=5,
            failed_sources=1,
            progress=0.5,
            status="running",
        )
        assert evt.progress == 0.5
        assert evt.status == "running"

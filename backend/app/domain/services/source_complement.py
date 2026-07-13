"""
书源互补服务 - 领域服务

职责：
- 接收书源传入的内容
- 并行请求其他书源对应章节
- 多源内容对比与合并
- 输出补全后的高质量内容

设计：
- 基于事件总线解耦：请求事件 → 并行 worker → 完成事件
- 支持同步调用和异步事件驱动两种模式
"""

import asyncio
import time
import uuid
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from ..entities.novel import NovelChapter
from ..value_objects import AlignmentResult
from .chapter_aligner import CrossSourceChapterAligner
from .content_merger import ContentMerger, ContentMergeResult
from ...core.logging import get_logger
from ...core.events import (
    ChapterComplementRequestedEvent,
    ChapterFetchedFromSourceEvent,
    ChapterComplementCompletedEvent,
    SourceComplementProgressEvent,
    publish_event,
)

logger = get_logger("source_complement")


@dataclass
class SourceFetchResult:
    """单源抓取结果"""
    source_url: str
    source_name: str = ""
    success: bool = False
    content: str = ""
    word_count: int = 0
    chapter_title: str = ""
    chapter_num: int = 0
    error: Optional[str] = None
    response_time_ms: int = 0


@dataclass
class ComplementResult:
    """书源互补结果"""
    job_id: str
    book_name: str
    chapter_title: str
    chapter_num: int
    total_sources: int
    successful_sources: int
    failed_sources: int
    final_content: str
    final_word_count: int
    quality_score: float
    merge_strategy: str
    source_results: List[SourceFetchResult] = field(default_factory=list)
    merged_from: List[str] = field(default_factory=list)
    status: str = "success"  # success / partial / failed
    elapsed_ms: int = 0


class SourceComplementService:
    """
    书源互补服务

    核心流程：
    1. 接收输入：来自某个书源的章节内容 + 其他可用书源列表
    2. 并行请求：向所有其他书源发起章节内容请求
    3. 章节对齐：将各来源的章节标题进行对齐匹配
    4. 内容对比：多源内容相似度计算
    5. 合并输出：基于质量评分和相似度合并出最优内容
    """

    def __init__(
        self,
        fetch_fn: Optional[Callable] = None,
        max_concurrent: int = 5,
        timeout_per_source: int = 30,
        merge_strategy: str = "hybrid",
    ):
        """
        Args:
            fetch_fn: 异步抓取函数 (source_url, chapter_info) -> SourceFetchResult
                      若不提供，则使用 mock 模式（仅测试用）
            max_concurrent: 最大并发请求数
            timeout_per_source: 单源超时时间（秒）
            merge_strategy: 合并策略 best / majority / hybrid
        """
        self._fetch_fn = fetch_fn or self._mock_fetch
        self._max_concurrent = max_concurrent
        self._timeout_per_source = timeout_per_source
        self._merge_strategy = merge_strategy
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def complement_chapter(
        self,
        book_name: str,
        chapter_title: str,
        chapter_num: int,
        source_urls: List[str],
        reference_content: str = "",
        publish_events: bool = True,
    ) -> ComplementResult:
        """
        执行章节互补

        Args:
            book_name: 书名
            chapter_title: 章节标题
            chapter_num: 章节序号
            source_urls: 需要请求的书源 URL 列表
            reference_content: 参考内容（来自当前书源）
            publish_events: 是否发布领域事件

        Returns:
            ComplementResult
        """
        start_time = time.time()
        job_id = f"comp_{uuid.uuid4().hex[:12]}"

        logger.info(
            f"[SourceComplement] 开始章节互补 job={job_id} "
            f"book={book_name} chapter={chapter_title}({chapter_num}) "
            f"sources={len(source_urls)}"
        )

        if publish_events:
            await publish_event(ChapterComplementRequestedEvent(
                job_id=job_id,
                book_name=book_name,
                chapter_title=chapter_title,
                chapter_num=chapter_num,
                source_urls=source_urls,
            ))

        # 1. 并行抓取所有书源
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        tasks = [
            self._fetch_single_source(job_id, url, book_name, chapter_title, chapter_num, publish_events)
            for url in source_urls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2. 整理结果
        fetch_results: List[SourceFetchResult] = []
        success_count = 0
        fail_count = 0

        for i, res in enumerate(results):
            if isinstance(res, Exception):
                fail_count += 1
                fetch_results.append(SourceFetchResult(
                    source_url=source_urls[i],
                    success=False,
                    error=str(res),
                ))
            else:
                fetch_results.append(res)
                if res.success:
                    success_count += 1
                else:
                    fail_count += 1

        # 3. 如果有参考内容，也加入合并
        merge_sources = []
        if reference_content.strip():
            merge_sources.append({
                "source_url": "reference",
                "source_name": "参考源",
                "content": reference_content,
                "word_count": len(reference_content),
            })

        for fr in fetch_results:
            if fr.success and fr.content.strip():
                merge_sources.append({
                    "source_url": fr.source_url,
                    "source_name": fr.source_name,
                    "content": fr.content,
                    "word_count": fr.word_count,
                })

        # 4. 内容合并
        if merge_sources:
            merge_result: ContentMergeResult = ContentMerger.merge(
                merge_sources,
                strategy=self._merge_strategy,
            )
            final_content = merge_result.content
            final_word_count = merge_result.word_count
            quality_score = merge_result.quality_score
            merged_from = merge_result.merged_from
            merge_strategy_used = merge_result.merge_strategy
        else:
            final_content = ""
            final_word_count = 0
            quality_score = 0.0
            merged_from = []
            merge_strategy_used = self._merge_strategy

        # 5. 状态判断
        if success_count == 0 and not reference_content.strip():
            status = "failed"
        elif success_count < len(source_urls):
            status = "partial"
        else:
            status = "success"

        elapsed = int((time.time() - start_time) * 1000)

        result = ComplementResult(
            job_id=job_id,
            book_name=book_name,
            chapter_title=chapter_title,
            chapter_num=chapter_num,
            total_sources=len(source_urls),
            successful_sources=success_count,
            failed_sources=fail_count,
            final_content=final_content,
            final_word_count=final_word_count,
            quality_score=quality_score,
            merge_strategy=merge_strategy_used,
            source_results=fetch_results,
            merged_from=merged_from,
            status=status,
            elapsed_ms=elapsed,
        )

        logger.info(
            f"[SourceComplement] 完成 job={job_id} "
            f"status={status} success={success_count}/{len(source_urls)} "
            f"quality={quality_score:.1f} elapsed={elapsed}ms"
        )

        if publish_events:
            await publish_event(ChapterComplementCompletedEvent(
                job_id=job_id,
                book_name=book_name,
                chapter_title=chapter_title,
                chapter_num=chapter_num,
                total_sources=len(source_urls),
                successful_sources=success_count,
                final_content=final_content,
                final_word_count=final_word_count,
                quality_score=quality_score,
                source_contributions=[
                    {
                        "source_url": r.source_url,
                        "success": r.success,
                        "word_count": r.word_count,
                        "response_time_ms": r.response_time_ms,
                    }
                    for r in fetch_results
                ],
                status=status,
                merged_from=merged_from,
            ))

        return result

    async def _fetch_single_source(
        self,
        job_id: str,
        source_url: str,
        book_name: str,
        chapter_title: str,
        chapter_num: int,
        publish_events: bool,
    ) -> SourceFetchResult:
        """从单个书源抓取章节（带并发控制和超时）"""
        async with self._semaphore:
            try:
                start = time.time()
                result = await asyncio.wait_for(
                    self._fetch_fn(source_url, {
                        "book_name": book_name,
                        "chapter_title": chapter_title,
                        "chapter_num": chapter_num,
                    }),
                    timeout=self._timeout_per_source,
                )
                elapsed = int((time.time() - start) * 1000)

                if isinstance(result, SourceFetchResult):
                    result.response_time_ms = elapsed
                else:
                    result = SourceFetchResult(
                        source_url=source_url,
                        success=True,
                        content=result.get("content", ""),
                        word_count=result.get("word_count", 0),
                        chapter_title=result.get("chapter_title", chapter_title),
                        chapter_num=result.get("chapter_num", chapter_num),
                        source_name=result.get("source_name", ""),
                        response_time_ms=elapsed,
                    )

                if publish_events:
                    await publish_event(ChapterFetchedFromSourceEvent(
                        job_id=job_id,
                        source_url=source_url,
                        source_name=result.source_name,
                        chapter_title=result.chapter_title,
                        chapter_num=result.chapter_num,
                        content=result.content if result.success else "",
                        word_count=result.word_count,
                        success=result.success,
                        error=result.error,
                        response_time_ms=result.response_time_ms,
                    ))

                return result

            except asyncio.TimeoutError:
                return SourceFetchResult(
                    source_url=source_url,
                    success=False,
                    error=f"超时 ({self._timeout_per_source}s)",
                    chapter_title=chapter_title,
                    chapter_num=chapter_num,
                )
            except Exception as e:
                logger.warning(f"[SourceComplement] 抓取失败 source={source_url} error={e}")
                return SourceFetchResult(
                    source_url=source_url,
                    success=False,
                    error=str(e),
                    chapter_title=chapter_title,
                    chapter_num=chapter_num,
                )

    @staticmethod
    async def _mock_fetch(source_url: str, chapter_info: Dict[str, Any]) -> SourceFetchResult:
        """
        Mock 抓取函数 - 仅用于测试和演示

        实际使用时应传入真实的 fetch_fn。
        """
        await asyncio.sleep(0.01)  # 模拟网络延迟
        content = (
            f"这是来自 {source_url} 的章节内容\n\n"
            f"书名：{chapter_info.get('book_name', '')}\n"
            f"章节：{chapter_info.get('chapter_title', '')}\n\n"
            f"正文内容第一段落。张三走在街上，看到了李四。\n\n"
            f"正文内容第二段落。两人寒暄了几句，然后各自离去。\n\n"
            f"（本章完）"
        )
        return SourceFetchResult(
            source_url=source_url,
            source_name=f"书源_{source_url[-8:]}" if len(source_url) > 8 else source_url,
            success=True,
            content=content,
            word_count=len(content),
            chapter_title=chapter_info.get("chapter_title", ""),
            chapter_num=chapter_info.get("chapter_num", 0),
        )

    @staticmethod
    def align_chapters_across_sources(
        source_chapters_map: Dict[str, List[NovelChapter]],
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        多源章节目录对齐

        Args:
            source_chapters_map: { source_url: [NovelChapter, ...] }

        Returns:
            { chapter_num: [{"source_url": ..., "chapter": NovelChapter}, ...] }
        """
        if not source_chapters_map:
            return {}

        # 取第一个源作为基准
        sources = list(source_chapters_map.keys())
        base_source = sources[0]
        base_chapters = source_chapters_map[base_source]

        aligned: Dict[int, List[Dict[str, Any]]] = {}

        for ch in base_chapters:
            aligned.setdefault(ch.chapter_num, []).append({
                "source_url": base_source,
                "chapter": ch,
            })

        # 对齐其他源
        for source in sources[1:]:
            chapters = source_chapters_map[source]
            align_result: AlignmentResult = CrossSourceChapterAligner.align(
                base_chapters, chapters,
            )
            for base_idx, target_idx, conf in align_result.matches:
                base_ch = base_chapters[base_idx]
                target_ch = chapters[target_idx]
                aligned.setdefault(base_ch.chapter_num, []).append({
                    "source_url": source,
                    "chapter": target_ch,
                    "confidence": conf,
                })

        return aligned

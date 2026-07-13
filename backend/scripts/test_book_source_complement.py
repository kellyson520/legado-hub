#!/usr/bin/env python3
"""
书源互补真实测试脚本 - V2

使用 Legado 书源进行真实测试：
1. 从 shareBookSource.json 加载书源
2. 筛选出可解析的简单 API 书源
3. 搜索三本书：捞尸人 / 斗罗大陆 / 大奉打更人
4. 拉取目录和正文
5. 测试书源互补（多源并行 + 内容合并）
"""

import sys
import os
import json
import time
import asyncio
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher
from app.domain.services.source_complement import SourceComplementService, SourceFetchResult
from app.domain.services.content_merger import ContentMerger, ContentQualityEstimator
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("test_complement")

BOOK_SOURCE_FILE = "/workspace/shareBookSource.json"
TEST_BOOKS = ["捞尸人", "斗罗大陆", "大奉打更人"]
MAX_SOURCES_PER_BOOK = 6
MAX_TEST_SOURCES = 80  # 最多测试多少个书源


def load_and_filter_sources(filepath: str) -> List[Dict[str, Any]]:
    """加载并筛选可解析的书源"""
    print(f"\n{'='*60}")
    print(f"[1/6] 加载书源文件: {filepath}")
    print(f"{'='*60}")

    with open(filepath, 'r', encoding='utf-8') as f:
        sources = json.load(f)

    print(f"  总书源数: {len(sources)}")

    # 过滤启用的文本源
    enabled = [s for s in sources if s.get('enabled') and s.get('bookSourceType') == 0]
    print(f"  启用的文本源: {len(enabled)}")

    # 筛选有简单 searchUrl（非 @js: 开头）且有 http baseUrl 的
    simple_sources = []
    for s in enabled:
        base_url = s.get('bookSourceUrl', '')
        search_url = s.get('searchUrl', '')
        if not base_url.startswith('http'):
            continue
        if not search_url:
            continue
        if search_url.strip().startswith('@js:') or search_url.strip().startswith('@JS:'):
            continue
        # ruleSearch 必须有 bookList
        rs = s.get('ruleSearch', {})
        if isinstance(rs, str):
            continue
        if not rs or not rs.get('bookList'):
            continue
        simple_sources.append(s)

    print(f"  可直接解析的 API 书源: {len(simple_sources)}")
    return simple_sources


async def find_book_from_sources(
    fetcher: LegadoBookSourceFetcher,
    sources: List[Dict[str, Any]],
    keyword: str,
    max_sources: int = MAX_SOURCES_PER_BOOK,
) -> List[Dict[str, Any]]:
    """从多个书源中搜索某本书，返回匹配的书籍（来自不同书源）"""
    print(f"\n  正在搜索 '{keyword}'，测试 {min(len(sources), MAX_TEST_SOURCES)} 个书源...")

    test_sources = sources[:MAX_TEST_SOURCES]

    async def search_one(source):
        try:
            results = await fetcher.search(source, keyword)
            # 过滤书名匹配的
            matches = []
            for r in results:
                name = r.get('name', '')
                if keyword in name or name in keyword:
                    matches.append(r)
            return source, matches
        except Exception as e:
            return source, []

    tasks = [search_one(s) for s in test_sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    matched_books = []
    success_count = 0
    fail_count = 0

    for res in results:
        if isinstance(res, Exception):
            fail_count += 1
            continue
        source, books = res
        if books:
            success_count += 1
            matched_books.extend(books)
        else:
            fail_count += 1

    print(f"  搜索完成: 成功 {success_count} 源, 失败 {fail_count} 源, 共匹配 {len(matched_books)} 条")

    # 去重 + 限制数量
    seen_urls = set()
    unique = []
    for book in matched_books:
        url = book.get('bookUrl', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(book)
            if len(unique) >= max_sources:
                break

    print(f"  去重后: {len(unique)} 本（来自不同书源）")
    for i, b in enumerate(unique):
        print(f"    {i+1}. [{b.get('sourceName', '')[:15]}] {b.get('name', '')} ({b.get('author', '')})")

    return unique


async def fetch_toc_and_chapter(
    fetcher: LegadoBookSourceFetcher,
    book: Dict[str, Any],
    chapter_idx: int = 3,
) -> Dict[str, Any]:
    """获取某本书的目录和指定章节内容"""
    source = book.get('_source_config', {})
    book_url = book.get('bookUrl', '')

    result = {
        'source_name': book.get('sourceName', ''),
        'source_url': book.get('sourceUrl', ''),
        'book_name': book.get('name', ''),
        'book_url': book_url,
        'author': book.get('author', ''),
        'toc_count': 0,
        'chapter_title': '',
        'chapter_content': '',
        'chapter_word_count': 0,
        'quality_score': 0.0,
        'success': False,
        'error': '',
    }

    try:
        # 获取目录
        toc = await fetcher.get_toc(source, book_url)
        result['toc_count'] = len(toc)

        if not toc:
            result['error'] = '无目录'
            return result

        # 取指定章节
        idx = min(chapter_idx, len(toc) - 1)
        chapter = toc[idx]
        result['chapter_title'] = chapter.get('title', '')

        # 获取正文
        content_result = await fetcher.get_content(source, chapter['url'])
        content = content_result.get('content', '')

        if content and len(content) > 100:
            result['chapter_content'] = content
            result['chapter_word_count'] = len(content)
            quality = ContentQualityEstimator.evaluate(content)
            result['quality_score'] = quality.score
            result['success'] = True
        else:
            result['error'] = f'内容太短 ({len(content)} 字)'

    except Exception as e:
        result['error'] = str(e)

    return result


async def test_book_complement(
    fetcher: LegadoBookSourceFetcher,
    sources: List[Dict[str, Any]],
    keyword: str,
) -> Dict[str, Any]:
    """完整测试一本书的书源互补"""
    print(f"\n{'='*60}")
    print(f"  测试书籍: {keyword}")
    print(f"{'='*60}")

    # 1. 搜索
    books = await find_book_from_sources(fetcher, sources, keyword)
    if not books:
        print(f"  ❌ 未找到匹配的书源")
        return {"book": keyword, "status": "not_found"}

    # 2. 拉取章节内容
    print(f"\n  [2] 拉取章节内容（共 {len(books)} 本书）...")
    chapter_results = []

    toc_tasks = [fetch_toc_and_chapter(fetcher, b, chapter_idx=3) for b in books]
    results = await asyncio.gather(*toc_tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            continue
        source_name = res['source_name']
        if res['success']:
            print(f"    ✓ [{source_name[:15]}] {res['toc_count']}章 | "
                  f"第4章 {res['chapter_word_count']}字 | 质量{res['quality_score']:.0f}分")
            chapter_results.append(res)
        else:
            print(f"    ✗ [{source_name[:15]}] {res['error']}")

    if not chapter_results:
        print(f"  ❌ 没有书源能获取有效正文")
        return {
            "book": keyword,
            "status": "no_content",
            "sources_matched": len(books),
        }

    # 3. 书源互补测试
    print(f"\n  [3] 书源互补测试（{len(chapter_results)} 个源并行）...")

    content_map = {r['source_url']: r for r in chapter_results}

    async def mock_fetch(source_url: str, chapter_info: Dict[str, Any]) -> SourceFetchResult:
        await asyncio.sleep(0.05)
        data = content_map.get(source_url)
        if not data:
            return SourceFetchResult(source_url=source_url, success=False, error="无数据")
        return SourceFetchResult(
            source_url=source_url,
            source_name=data['source_name'],
            success=True,
            content=data['chapter_content'],
            word_count=data['chapter_word_count'],
            chapter_title=data['chapter_title'],
            chapter_num=3,
        )

    service = SourceComplementService(
        fetch_fn=mock_fetch,
        max_concurrent=5,
        merge_strategy="hybrid",
    )

    ref = chapter_results[0]

    start = time.time()
    comp_result = await service.complement_chapter(
        book_name=ref['book_name'],
        chapter_title=ref['chapter_title'],
        chapter_num=3,
        source_urls=[r['source_url'] for r in chapter_results],
        reference_content=ref['chapter_content'],
        publish_events=False,
    )
    elapsed = (time.time() - start) * 1000

    # 输出结果
    print(f"\n  📊 互补结果:")
    print(f"    状态: {comp_result.status}")
    print(f"    成功源数: {comp_result.successful_sources}/{comp_result.total_sources}")
    print(f"    合并策略: {comp_result.merge_strategy}")
    print(f"    最终字数: {comp_result.final_word_count}")
    print(f"    质量评分: {comp_result.quality_score:.1f}")
    print(f"    参与合并: {len(comp_result.merged_from)} 个源")
    for src_url in comp_result.merged_from:
        data = content_map.get(src_url, {})
        if data:
            print(f"      - {data.get('source_name', src_url)[:20]} "
                  f"({data.get('chapter_word_count', 0)}字, 质量{data.get('quality_score', 0):.0f}分)")
    print(f"    耗时: {elapsed:.0f}ms")

    # 内容预览
    preview = comp_result.final_content[:120].replace('\n', ' ')
    print(f"\n    内容预览: {preview}...")

    return {
        "book": keyword,
        "status": "success",
        "sources_matched": len(books),
        "sources_with_content": len(chapter_results),
        "complement": {
            "status": comp_result.status,
            "total_sources": comp_result.total_sources,
            "successful_sources": comp_result.successful_sources,
            "merge_strategy": comp_result.merge_strategy,
            "final_word_count": comp_result.final_word_count,
            "quality_score": round(comp_result.quality_score, 1),
            "merged_from_count": len(comp_result.merged_from),
            "elapsed_ms": round(elapsed),
        },
        "source_details": [
            {
                "source_name": r['source_name'],
                "toc_count": r['toc_count'],
                "word_count": r['chapter_word_count'],
                "quality_score": round(r['quality_score'], 1),
            }
            for r in chapter_results
        ],
    }


async def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         书源互补功能 - 真实环境测试                         ║
║   书籍: 捞尸人 / 斗罗大陆 / 大奉打更人                      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # 1. 加载书源
    sources = load_and_filter_sources(BOOK_SOURCE_FILE)

    # 2. 初始化
    print(f"\n{'='*60}")
    print(f"[2/6] 初始化 Legado 书源抓取器")
    print(f"{'='*60}")
    fetcher = LegadoBookSourceFetcher()
    print("  ✓ 抓取器初始化完成")

    # 3-5. 测试每本书
    print(f"\n{'='*60}")
    print(f"[3-5/6] 搜索 + 目录 + 正文 + 互补测试")
    print(f"{'='*60}")

    all_results = []
    for book_name in TEST_BOOKS:
        result = await test_book_complement(fetcher, sources, book_name)
        all_results.append(result)
        await asyncio.sleep(0.3)

    # 6. 汇总报告
    print(f"\n\n{'='*60}")
    print(f"[6/6] 测试报告汇总")
    print(f"{'='*60}")

    print(f"\n{'书名':<12} {'状态':<12} {'匹配源':<8} {'有正文':<8} {'质量分':<8} {'合并源':<8} {'耗时ms':<8}")
    print("-" * 70)

    success_count = 0
    for r in all_results:
        status = r.get('status', '')
        comp = r.get('complement', {})
        print(
            f"{r['book']:<12} "
            f"{status:<12} "
            f"{r.get('sources_matched', '-'):<8} "
            f"{r.get('sources_with_content', '-'):<8} "
            f"{comp.get('quality_score', '-'):<8} "
            f"{comp.get('merged_from_count', '-'):<8} "
            f"{comp.get('elapsed_ms', '-'):<8}"
        )
        if status == 'success':
            success_count += 1

    print(f"\n✓ {success_count}/{len(all_results)} 本书完成书源互补测试")

    # 保存详细报告
    report_path = "/workspace/legado-proxy/legado-hub/backend/test_complement_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告: {report_path}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())

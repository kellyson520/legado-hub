#!/usr/bin/env python3
"""
Legado 引擎真实端到端测试

完整流程：加载书源 → 并发测活 → 搜索 → 目录 → 正文 → 互补
测试书籍：捞尸人 / 斗罗大陆 / 大奉打更人
"""

import sys
import os
import json
import asyncio
import time
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.legado import LegadoBookSourceFetcher
from app.infrastructure.legado.engine import LegadoHttpClient
import logging

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

BOOK_SOURCE_FILE = "/workspace/shareBookSource.json"
TEST_BOOKS = ["捞尸人", "斗罗大陆", "大奉打更人"]


def load_and_filter_sources() -> List[Dict[str, Any]]:
    """加载并筛选可用的 API 书源"""
    with open(BOOK_SOURCE_FILE, 'r', encoding='utf-8') as f:
        all_sources = json.load(f)

    enabled = [s for s in all_sources if s.get('enabled') and s.get('bookSourceType') == 0]

    # 筛选条件：有 searchUrl、非 JS、有 bookList 规则
    candidates = []
    for s in enabled:
        su = s.get('searchUrl', '')
        if not su or su.strip().startswith('@js:'):
            continue
        rs = s.get('ruleSearch', {})
        if not isinstance(rs, dict):
            continue
        if not rs.get('bookList') or not rs.get('name'):
            continue
        candidates.append(s)

    return candidates


async def probe_source(fetcher: LegadoBookSourceFetcher, source: Dict) -> Dict:
    """探测单个书源是否可用（搜索测试）"""
    name = source.get('bookSourceName', '')[:20]
    url = source.get('bookSourceUrl', '')
    try:
        results = await asyncio.wait_for(
            fetcher.search(source, "斗罗大陆", page=1),
            timeout=15,
        )
        return {
            'source': source,
            'name': name,
            'url': url,
            'alive': len(results) > 0,
            'result_count': len(results),
        }
    except asyncio.TimeoutError:
        return {'source': source, 'name': name, 'url': url, 'alive': False, 'result_count': 0}
    except Exception as e:
        return {'source': source, 'name': name, 'url': url, 'alive': False, 'result_count': 0, 'error': str(e)[:50]}


async def probe_sources_parallel(sources: List[Dict], batch_size: int = 15) -> List[Dict]:
    """并发探测书源"""
    print(f"  并发探测 {len(sources)} 个书源（每批 {batch_size} 个）...")

    alive_sources = []
    total = len(sources)

    async with LegadoBookSourceFetcher(timeout=12, verify_ssl=False, max_concurrent=batch_size) as fetcher:
        for start in range(0, total, batch_size):
            batch = sources[start:start + batch_size]
            tasks = [probe_source(fetcher, s) for s in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, dict) and r.get('alive'):
                    alive_sources.append(r)

            done = min(start + batch_size, total)
            print(f"    进度: {done}/{total}  |  可用: {len(alive_sources)}", end='\r')

    print()
    return alive_sources


async def test_search(fetcher: LegadoBookSourceFetcher, source: Dict, keyword: str) -> Dict:
    """测试搜索"""
    start = time.time()
    try:
        results = await asyncio.wait_for(
            fetcher.search(source, keyword, page=1),
            timeout=15,
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            'success': len(results) > 0,
            'count': len(results),
            'elapsed_ms': elapsed,
            'books': results[:3],  # 只取前3本
        }
    except asyncio.TimeoutError:
        return {'success': False, 'count': 0, 'elapsed_ms': 15000, 'books': []}
    except Exception as e:
        return {'success': False, 'count': 0, 'elapsed_ms': 0, 'books': [], 'error': str(e)[:50]}


async def test_toc(fetcher: LegadoBookSourceFetcher, source: Dict, book_url: str) -> Dict:
    """测试目录获取"""
    start = time.time()
    try:
        chapters = await asyncio.wait_for(
            fetcher.get_toc(source, book_url),
            timeout=15,
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            'success': len(chapters) > 0,
            'count': len(chapters),
            'elapsed_ms': elapsed,
            'chapters': chapters[:5],
        }
    except asyncio.TimeoutError:
        return {'success': False, 'count': 0, 'elapsed_ms': 15000, 'chapters': []}
    except Exception as e:
        return {'success': False, 'count': 0, 'elapsed_ms': 0, 'chapters': [], 'error': str(e)[:50]}


async def test_content(fetcher: LegadoBookSourceFetcher, source: Dict, chapter_url: str) -> Dict:
    """测试正文获取"""
    start = time.time()
    try:
        result = await asyncio.wait_for(
            fetcher.get_content(source, chapter_url),
            timeout=15,
        )
        elapsed = int((time.time() - start) * 1000)
        content = result.get('content', '')
        return {
            'success': len(content) > 50,
            'word_count': len(content),
            'elapsed_ms': elapsed,
            'title': result.get('title', ''),
            'preview': content[:100].replace('\n', ' ') if content else '',
        }
    except asyncio.TimeoutError:
        return {'success': False, 'word_count': 0, 'elapsed_ms': 15000, 'title': '', 'preview': ''}
    except Exception as e:
        return {'success': False, 'word_count': 0, 'elapsed_ms': 0, 'title': '', 'preview': '', 'error': str(e)[:50]}


async def test_book_full_flow(fetcher: LegadoBookSourceFetcher, source: Dict, keyword: str) -> Dict:
    """测试单源的完整流程：搜索→目录→正文"""
    result = {
        'source_name': source.get('bookSourceName', '')[:20],
        'source_url': source.get('bookSourceUrl', ''),
        'keyword': keyword,
        'search': None,
        'toc': None,
        'content': None,
    }

    # 1. 搜索
    search_result = await test_search(fetcher, source, keyword)
    result['search'] = search_result
    if not search_result['success']:
        return result

    # 2. 目录
    book = search_result['books'][0]
    book_url = book.get('bookUrl', '')
    if not book_url:
        result['toc'] = {'success': False, 'error': 'no bookUrl'}
        return result

    result['book_name'] = book.get('name', '')
    result['book_author'] = book.get('author', '')

    toc_result = await test_toc(fetcher, source, book_url)
    result['toc'] = toc_result
    if not toc_result['success']:
        return result

    # 3. 正文（取第一章）
    if toc_result['chapters']:
        chapter = toc_result['chapters'][0]
        chapter_url = chapter.get('url', '')
        if chapter_url:
            content_result = await test_content(fetcher, source, chapter_url)
            result['content'] = content_result
            result['chapter_title'] = chapter.get('title', '')

    return result


async def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║     Legado 解析引擎 - 真实端到端测试                      ║
║                                                           ║
║  流程: 加载书源 → 并发测活 → 搜索 → 目录 → 正文         ║
║  书籍: 捞尸人 / 斗罗大陆 / 大奉打更人                     ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # ===================== 阶段 1: 加载书源 =====================
    print(f"\n{'='*65}")
    print(f"  [阶段 1] 加载书源")
    print(f"{'='*65}")

    candidates = load_and_filter_sources()
    print(f"  总书源: 2385")
    print(f"  候选 API 书源: {len(candidates)}")

    # 取前 80 个来探测（覆盖不同类型）
    test_sources = candidates[:80]
    print(f"  本次探测: {len(test_sources)} 个")

    # ===================== 阶段 2: 并发测活 =====================
    print(f"\n{'='*65}")
    print(f"  [阶段 2] 并发探测可用书源")
    print(f"{'='*65}")

    t0 = time.time()
    alive = await probe_sources_parallel(test_sources, batch_size=15)
    t1 = time.time()

    print(f"\n  ✓ 探测完成，耗时 {t1-t0:.1f}s")
    print(f"  ✓ 可用书源: {len(alive)}/{len(test_sources)}")
    print(f"\n  可用书源列表:")
    for i, a in enumerate(alive[:20]):
        print(f"    {i+1:2d}. {a['name']:<20} | {a['result_count']:>2}本 | {a['url'][:40]}")

    if not alive:
        print("  ✗ 没有可用书源，测试终止")
        return

    # ===================== 阶段 3: 完整流程测试 =====================
    print(f"\n{'='*65}")
    print(f"  [阶段 3] 完整流程测试（搜索→目录→正文）")
    print(f"{'='*65}")

    # 选取前 12 个可用书源做完整测试（覆盖更多类型）
    test_sources_alive = [a['source'] for a in alive[:12]]
    print(f"  选取 {len(test_sources_alive)} 个书源进行完整流程测试")

    all_results = []

    async with LegadoBookSourceFetcher(timeout=15, verify_ssl=False, max_concurrent=5) as fetcher:
        for book_name in TEST_BOOKS:
            print(f"\n  {'─'*60}")
            print(f"  📖 测试书籍: {book_name}")
            print(f"  {'─'*60}")

            for source in test_sources_alive:
                src_name = source.get('bookSourceName', '')[:20]
                print(f"\n    [{src_name}]")

                result = await test_book_full_flow(fetcher, source, book_name)
                all_results.append(result)

                # 输出结果
                s = result['search']
                t = result['toc']
                c = result['content']

                if s and s['success']:
                    print(f"    ✓ 搜索: {s['count']}本 ({s['elapsed_ms']}ms)")
                    if result.get('book_name'):
                        print(f"      → 《{result['book_name']}》 {result.get('book_author','')}")
                else:
                    print(f"    ✗ 搜索失败")
                    continue

                if t and t['success']:
                    print(f"    ✓ 目录: {t['count']}章 ({t['elapsed_ms']}ms)")
                else:
                    print(f"    ✗ 目录失败")
                    continue

                if c and c['success']:
                    print(f"    ✓ 正文: {c['word_count']}字 ({c['elapsed_ms']}ms)")
                    print(f"      标题: {c['title']}")
                    print(f"      预览: {c['preview'][:60]}...")
                else:
                    err = c.get('error','') if c else 'no content result'
                    prev = c.get('preview','')[:60] if c else ''
                    print(f"    ✗ 正文获取失败 ({err}) {prev}")

    # ===================== 阶段 4: 汇总报告 =====================
    print(f"\n\n{'='*65}")
    print(f"  [阶段 4] 测试汇总报告")
    print(f"{'='*65}")

    # 按书籍统计
    print(f"\n  按书籍统计:")
    print(f"  {'书名':<12} {'搜索成功':<8} {'目录成功':<8} {'正文成功':<8} {'平均耗时':<10}")
    print(f"  {'-'*55}")

    for book in TEST_BOOKS:
        book_results = [r for r in all_results if r['keyword'] == book]
        search_ok = sum(1 for r in book_results if r['search'] and r['search']['success'])
        toc_ok = sum(1 for r in book_results if r['toc'] and r['toc']['success'])
        content_ok = sum(1 for r in book_results if r['content'] and r['content']['success'])

        times = [r['search']['elapsed_ms'] for r in book_results if r['search']]
        avg_time = sum(times) / len(times) if times else 0

        print(f"  {book:<12} {search_ok}/{len(book_results):<7} {toc_ok}/{len(book_results):<7} "
              f"{content_ok}/{len(book_results):<7} {avg_time:.0f}ms")

    # 按书源统计
    print(f"\n  按书源统计:")
    print(f"  {'书源':<20} {'搜索':<6} {'目录':<6} {'正文':<6}")
    print(f"  {'-'*45}")

    source_names = list(set(r['source_name'] for r in all_results))
    for sn in sorted(source_names):
        sr = [r for r in all_results if r['source_name'] == sn]
        s_ok = sum(1 for r in sr if r['search'] and r['search']['success'])
        t_ok = sum(1 for r in sr if r['toc'] and r['toc']['success'])
        c_ok = sum(1 for r in sr if r['content'] and r['content']['success'])
        print(f"  {sn:<20} {s_ok}/{len(sr):<5} {t_ok}/{len(sr):<5} {c_ok}/{len(sr):<5}")

    # 成功的完整流程
    full_success = [r for r in all_results if r['content'] and r['content']['success']]
    print(f"\n  完整流程成功: {len(full_success)}/{len(all_results)}")

    if full_success:
        print(f"\n  成功案例:")
        for r in full_success[:3]:
            print(f"    📖 《{r.get('book_name','')}》 {r.get('book_author','')}")
            print(f"       源: {r['source_name']}")
            print(f"       章: {r.get('chapter_title','')} ({r['content']['word_count']}字)")
            print(f"       预览: {r['content']['preview'][:50]}...")
            print()

    # 保存报告
    report_path = "/workspace/legado-proxy/legado-hub/backend/test_real_e2e_report.json"
    report = {
        'test_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_sources_tested': len(test_sources),
        'alive_sources': len(alive),
        'books_tested': TEST_BOOKS,
        'results': [{
            'source': r['source_name'],
            'book': r['keyword'],
            'book_name': r.get('book_name', ''),
            'author': r.get('book_author', ''),
            'search_success': r['search']['success'] if r['search'] else False,
            'search_count': r['search']['count'] if r['search'] else 0,
            'toc_success': r['toc']['success'] if r['toc'] else False,
            'toc_count': r['toc']['count'] if r['toc'] else 0,
            'content_success': r['content']['success'] if r['content'] else False,
            'content_words': r['content']['word_count'] if r['content'] else 0,
            'chapter_title': r.get('chapter_title', ''),
        } for r in all_results],
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 报告已保存: {report_path}")

    print(f"\n{'='*65}")
    print(f"  测试完成!")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())

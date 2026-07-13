#!/usr/bin/env python3
"""
书源搜索脚本 - 用真实书源搜索"斗罗大陆"

用法:
    cd backend
    python scripts/search_douluo.py

依赖: pip install beautifulsoup4 lxml
"""

import asyncio
import json
import os
import sys
import time

# 确保 app 包可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("REPO_BACKEND", "sqlite")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.domain.entities.source import BookSource
from app.services.book_searcher import BookSearcher


def load_real_sources():
    """加载真实书源数据"""
    return [
        {
            "bookSourceGroup": "精选",
            "bookSourceName": "APP测试源",
            "bookSourceType": 0,
            "bookSourceUrl": "https://quapp.shenbabao.com",
            "bookUrlPattern": "https://quapp.shenbabao.com/book/.*",
            "enabled": True,
            "ruleContent": {"content": "$..content"},
            "ruleSearch": {
                "author": "$.Author",
                "bookList": "$..data",
                "bookUrl": "https://quapp.shenbabao.com/book/{$.Id}/",
                "coverUrl": "$.Img",
                "intro": "$.Desc",
                "kind": "$.CName&&$.BookStatus",
                "lastChapter": "$.LastChapter",
                "name": "$.Name",
            },
            "ruleToc": {
                "chapterList": "$..list",
                "chapterName": "$.name",
                "chapterUrl": "https://quapp.shenbabao.com/book/{{$.id}}.html"
            },
            "searchUrl": "https://sou.jiaston.com/search.aspx?key={{key}}&page=Page&siteid=app2",
        },
        {
            "bookSourceGroup": "精选",
            "bookSourceName": "无错小说网",
            "bookSourceType": 0,
            "bookSourceUrl": "http://www.xquledu.com",
            "enabled": True,
            "ruleContent": {"content": "id.contents@textNodes"},
            "ruleSearch": {
                "author": "class.c_value.0@text",
                "bookList": "class.c_row",
                "bookUrl": "class.c_subject@tag.a@href",
                "coverUrl": "class.fl.0@tag.a@tag.img@src",
                "kind": "class.c_value.1@text",
                "lastChapter": "class.c_value.5@tag.a@text",
                "name": "class.c_subject@tag.a@text",
            },
            "ruleToc": {
                "chapterList": "id.list@tag.dd",
                "chapterName": "tag.a@text",
                "chapterUrl": "tag.a@href",
            },
            "searchUrl": "http://www.xquledu.com/modules/article/search.php?action=search&searchtype=all&searchkey={{key}},{\"charset\": \"gbk\"}",
        },
        {
            "bookSourceGroup": "精选",
            "bookSourceName": "饭饭中文",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.fanfanzw.com",
            "enabled": True,
            "ruleContent": {"content": "id.content@html##喜欢.*速度最快。"},
            "ruleSearch": {
                "author": "class.book_other.0@tag.span.0@text",
                "bookList": "id.sitembox@dl",
                "bookUrl": "tag.a.0@href",
                "coverUrl": "img@src",
                "intro": "class.book_des@text",
                "kind": "class.book_other.0@tag.span.2@text",
                "lastChapter": "class.book_other@a@text",
                "name": "h3@text",
            },
            "ruleToc": {
                "chapterList": "//*[@id='list']//dd/a",
                "chapterName": "text",
                "chapterUrl": "href",
            },
            "searchUrl": "https://www.fanfanzw.com/search.html,{\"method\": \"POST\", \"body\": \"searchkey={{key}}\"}",
        },
        {
            "bookSourceGroup": "精选",
            "bookSourceName": "墨斋小说",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.mozhai123.net",
            "enabled": True,
            "ruleContent": {"content": "class.txt_tcontent@html"},
            "ruleSearch": {
                "author": "class.newlist-zz@tag.a@text",
                "bookList": "class.newlist.0@tag.li",
                "bookUrl": "class.newlist-title@tag.a@href",
                "kind": "class.newlist-type@tag.a@title",
                "lastChapter": "class.newlist-zj@tag.a@title",
                "name": "class.newlist-title@tag.a@text",
            },
            "ruleToc": {
                "chapterList": "class.dirlist.1@tag.li",
                "chapterName": "a@text",
                "chapterUrl": "a@href",
            },
            "searchUrl": "https://www.mozhai123.net/modules/article/search.php,{\"charset\": \"gbk\", \"method\": \"POST\", \"body\": \"submit=搜索&searchtype=articlename&searchkey={{key}}&action=login\"}",
        },
        {
            "bookSourceGroup": "精选",
            "bookSourceName": "久久小说",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.txt909.cc",
            "enabled": True,
            "ruleContent": {"content": "id.view_content_txt@textNodes"},
            "ruleSearch": {
                "author": "class.mainGreen@text",
                "bookList": "id.searchList@tag.div!0",
                "bookUrl": "class.searchTopic@tag.a.0@href",
                "coverUrl": "class.listbg@tag.span.1@text",
                "kind": "class.listbg@tag.span.2@text",
                "lastChapter": "class.searchTopic@tag.a.0@text",
                "name": "class.searchTopic@tag.a.0@text",
            },
            "ruleToc": {
                "chapterList": "class.read_list@tag.a",
                "chapterName": "tag.a@text",
                "chapterUrl": "tag.a@href",
            },
            "searchUrl": "https://www.txt909.cc/search.html,{\"charset\": \"utf-8\", \"method\": \"POST\", \"body\": \"searchkey={{key}}&Submit22=搜索\"}",
        },
    ]


async def search_one_source(source: BookSource, keyword: str, timeout: int = 20):
    """搜索单个书源"""
    try:
        searcher = BookSearcher(source)
        start = time.time()
        results = await searcher.search(keyword, timeout=timeout)
        elapsed = time.time() - start
        return results, elapsed, None
    except Exception as e:
        return [], 0, str(e)


async def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "斗罗大陆"
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    print(f"\n{'='*60}")
    print(f"  书源搜索: \"{keyword}\"  (超时: {timeout}s)")
    print(f"{'='*60}\n")

    raw_sources = load_real_sources()
    all_results = []
    success_count = 0
    error_count = 0

    for raw in raw_sources:
        entity = BookSource.from_dict(raw)
        if not entity.searchUrl or not entity.ruleSearch:
            print(f"  [跳过] {entity.bookSourceName} - 无搜索规则")
            continue

        url_info = ""
        method = "GET"
        if ",{" in entity.searchUrl:
            opts = entity.searchUrl.split(",{", 1)[1]
            if '"method"' in opts:
                method = "POST"
            if '"charset"' in opts:
                cs = opts.split('"charset"')[1].split('"')[1]
                url_info += f" charset={cs}"
        url_info = f"{method}{url_info}"

        print(f"  [搜索] {entity.bookSourceName} ({url_info})...")

        results, elapsed, error = await search_one_source(entity, keyword, timeout)

        if error:
            print(f"         失败: {error}")
            error_count += 1
        elif results:
            print(f"         成功: {len(results)} 条结果 ({elapsed:.1f}s)")
            for r in results[:5]:
                author = f" | {r.author}" if r.author else ""
                intro = f" - {r.intro[:40]}" if r.intro else ""
                print(f"           * 《{r.name}》{author}{intro}")
            if len(results) > 5:
                print(f"           ... 还有 {len(results) - 5} 条")
            success_count += 1
            all_results.extend(results)
        else:
            print(f"         无结果 ({elapsed:.1f}s)")

        # 防止请求过快
        await asyncio.sleep(1)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  搜索汇总")
    print(f"{'='*60}")
    print(f"  搜索关键词: {keyword}")
    print(f"  书源总数:   {len(raw_sources)}")
    print(f"  成功:       {success_count}")
    print(f"  失败:       {error_count}")
    print(f"  总结果数:   {len(all_results)}")

    # 按相关度排序（名称包含关键词的排前面）
    douluo_results = sorted(
        [r for r in all_results if keyword in r.name],
        key=lambda r: r.name.find(keyword)
    )
    other_results = [r for r in all_results if keyword not in r.name]

    if douluo_results:
        print(f"\n  精确匹配 \"{keyword}\" ({len(douluo_results)} 条):")
        seen = set()
        for r in douluo_results:
            key = r.name + r.sourceName
            if key in seen:
                continue
            seen.add(key)
            author = f" - {r.author}" if r.author else ""
            print(f"    * 《{r.name}》{author}  [{r.sourceName}]")

    if other_results:
        print(f"\n  相关推荐 ({len(other_results)} 条):")
        seen = set()
        for r in other_results[:10]:
            key = r.name + r.sourceName
            if key in seen:
                continue
            seen.add(key)
            author = f" - {r.author}" if r.author else ""
            print(f"    * 《{r.name}》{author}  [{r.sourceName}]")

    # 输出 JSON（可选）
    output_file = os.environ.get("SEARCH_OUTPUT", "")
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([{
                "name": r.name, "author": r.author, "bookUrl": r.bookUrl,
                "intro": r.intro, "coverUrl": r.coverUrl,
                "lastChapter": r.lastChapter, "kind": r.kind,
                "sourceName": r.sourceName, "sourceUrl": r.sourceUrl,
            } for r in all_results], f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存到: {output_file}")

    print()


if __name__ == "__main__":
    asyncio.run(main())

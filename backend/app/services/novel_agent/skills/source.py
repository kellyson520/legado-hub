"""
书源技能 - Book Source Skill

专精小说书源的查找、爬取、编写。
调用底层 CrawlerEngine + SourceEngine 基础设施。

核心能力：
- 书源查找：从书源站、GitHub 仓库搜索可用书源
- 书源爬虫：自动分析小说站点，提取规则
- 书源编写：辅助用户编写/调试书源规则
- 书源管理：导入、导出、验证、分组
"""

from typing import List, Dict, Any, Optional
from ..registry import BaseSkill, ToolDefinition
from ..infrastructure import crawler_engine, source_engine, BookSource


class SourceSkill(BaseSkill):
    """书源技能 - 小说书源的查找、爬取、编写

    这是 Agent 的核心技能之一，专注于小说领域的书源生态。
    调用底层 CrawlerEngine + SourceEngine 基础设施。
    """

    name = "source"

    def get_tools(self) -> List[ToolDefinition]:
        return [
            # 书源查找
            ToolDefinition(
                name="source_search",
                description="搜索可用的小说书源。支持按书名、作者、站点名称搜索，从书源站和开源仓库中查找。",
                parameters={
                    "keyword": {"type": "string", "required": True, "desc": "搜索关键词（书名/作者/站点名）"},
                    "source_type": {"type": "string", "default": "text", "desc": "书源类型：text/audio/image"},
                    "limit": {"type": "integer", "default": 10, "desc": "返回数量限制"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_list",
                description="列出已添加的所有书源，支持按分组、类型、关键词过滤。",
                parameters={
                    "group": {"type": "string", "default": "", "desc": "书源分组"},
                    "source_type": {"type": "string", "default": "", "desc": "类型：text/audio/image"},
                    "keyword": {"type": "string", "default": "", "desc": "关键词过滤"},
                    "enabled_only": {"type": "boolean", "default": True, "desc": "只显示启用的书源"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_groups",
                description="列出所有书源分组。",
                parameters={},
                skill=self.name,
            ),
            # 书源爬虫
            ToolDefinition(
                name="source_crawl_site",
                description="自动分析一个小说网站，尝试提取搜索规则、目录规则、正文规则。输入网站首页或搜索页 URL。",
                parameters={
                    "site_url": {"type": "string", "required": True, "desc": "小说网站 URL（首页或搜索页）"},
                    "site_name": {"type": "string", "default": "", "desc": "站点名称（可选）"},
                    "test_keyword": {"type": "string", "default": "斗破苍穹", "desc": "测试搜索关键词"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_analyze_search",
                description="分析搜索页面结构，提取搜索结果的书名、作者、封面、链接等元素的选择器。",
                parameters={
                    "search_url": {"type": "string", "required": True, "desc": "搜索结果页面 URL"},
                    "keyword": {"type": "string", "default": "斗破苍穹", "desc": "搜索关键词"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_analyze_toc",
                description="分析小说目录页结构，提取章节列表的选择器。",
                parameters={
                    "toc_url": {"type": "string", "required": True, "desc": "小说目录页 URL"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_analyze_content",
                description="分析小说正文页结构，提取正文内容的选择器。",
                parameters={
                    "content_url": {"type": "string", "required": True, "desc": "正文页 URL"},
                },
                skill=self.name,
            ),
            # 书源编写
            ToolDefinition(
                name="source_create",
                description="创建一个新书源，可指定基本信息和规则。创建后可用 source_validate 验证。",
                parameters={
                    "bookSourceName": {"type": "string", "required": True, "desc": "书源名称"},
                    "bookSourceUrl": {"type": "string", "required": True, "desc": "书源地址（首页或搜索页）"},
                    "bookSourceGroup": {"type": "string", "default": "未分组", "desc": "书源分组"},
                    "bookSourceType": {"type": "integer", "default": 0, "desc": "类型：0文本/1音频/2图片"},
                    "ruleSearchUrl": {"type": "string", "default": "", "desc": "搜索规则 URL 模板"},
                    "ruleChapterName": {"type": "string", "default": "", "desc": "章节名称选择器"},
                    "ruleContent": {"type": "string", "default": "", "desc": "正文内容选择器"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_validate",
                description="验证书源是否有效，检查必填字段和规则完整性。",
                parameters={
                    "bookSourceUrl": {"type": "string", "required": True, "desc": "书源地址"},
                    "test_search": {"type": "boolean", "default": True, "desc": "是否测试搜索功能"},
                    "test_keyword": {"type": "string", "default": "斗破苍穹", "desc": "测试关键词"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_template",
                description="生成书源模板，可作为编写起点。",
                parameters={
                    "source_type": {"type": "string", "default": "text", "desc": "类型：text/audio/image"},
                },
                skill=self.name,
            ),
            # 书源管理
            ToolDefinition(
                name="source_import",
                description="导入书源（JSON 格式，支持 Legado 格式）。",
                parameters={
                    "json_data": {"type": "string", "required": True, "desc": "书源 JSON 数据"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_export",
                description="导出书源为 JSON 格式，可被 Legado 等阅读器导入。",
                parameters={
                    "group": {"type": "string", "default": "", "desc": "导出指定分组（空则导出全部）"},
                    "enabled_only": {"type": "boolean", "default": False, "desc": "只导出启用的"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="source_remove",
                description="删除指定书源。",
                parameters={
                    "bookSourceUrl": {"type": "string", "required": True, "desc": "书源地址"},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        src_engine = source_engine()
        crawler = crawler_engine()

        # 查找
        if tool_name == "source_search":
            return self._search(crawler, params)
        elif tool_name == "source_list":
            return self._list(src_engine, params)
        elif tool_name == "source_groups":
            return self._groups(src_engine)

        # 爬虫
        elif tool_name == "source_crawl_site":
            return self._crawl_site(crawler, src_engine, params)
        elif tool_name == "source_analyze_search":
            return self._analyze_search(crawler, params)
        elif tool_name == "source_analyze_toc":
            return self._analyze_toc(crawler, params)
        elif tool_name == "source_analyze_content":
            return self._analyze_content(crawler, params)

        # 编写
        elif tool_name == "source_create":
            return self._create(src_engine, params)
        elif tool_name == "source_validate":
            return self._validate(crawler, src_engine, params)
        elif tool_name == "source_template":
            return self._template(src_engine, params)

        # 管理
        elif tool_name == "source_import":
            return self._import(src_engine, params)
        elif tool_name == "source_export":
            return self._export(src_engine, params)
        elif tool_name == "source_remove":
            return self._remove(src_engine, params)

        return {"error": f"Unknown tool: {tool_name}", "tool": tool_name}

    # ===== 书源查找 =====

    def _search(self, crawler, params) -> Dict[str, Any]:
        keyword = params.get("keyword", "")
        source_type = params.get("source_type", "text")
        limit = params.get("limit", 10)

        search_urls = [
            f"https://www.google.com/search?q={keyword}+书源+legado",
        ]

        results = []
        for url in search_urls[:1]:
            crawl_result = crawler.fetch(url)
            if crawl_result.success:
                # 简化：从页面提取相关链接
                for link in crawl_result.links[:limit]:
                    if "source" in link.lower() or "book" in link.lower() or "legado" in link.lower():
                        results.append({
                            "url": link,
                            "title": f"书源相关链接: {link[:60]}",
                            "from": "web_search",
                        })
                break

        return {
            "keyword": keyword,
            "source_type": source_type,
            "total": min(len(results), limit),
            "results": results[:limit],
            "note": "搜索结果来自网络，需进一步验证书源可用性。",
        }

    def _list(self, src_engine, params) -> Dict[str, Any]:
        sources = src_engine.list_sources(
            group=params.get("group", ""),
            source_type=None if not params.get("source_type") else self._type_to_int(params["source_type"]),
            enabled_only=params.get("enabled_only", True),
            keyword=params.get("keyword", ""),
        )
        return {
            "total": len(sources),
            "sources": [
                {
                    "name": s.bookSourceName,
                    "url": s.bookSourceUrl,
                    "group": s.bookSourceGroup,
                    "type": self._type_to_str(s.bookSourceType),
                    "enabled": s.enabled,
                }
                for s in sources
            ],
        }

    def _groups(self, src_engine) -> Dict[str, Any]:
        groups = src_engine.list_groups()
        return {"groups": groups, "total": len(groups)}

    # ===== 书源爬虫 =====

    def _crawl_site(self, crawler, src_engine, params) -> Dict[str, Any]:
        site_url = params.get("site_url", "")
        site_name = params.get("site_name", "")
        test_keyword = params.get("test_keyword", "斗破苍穹")

        home = crawler.fetch(site_url)
        if not home.success:
            return {"error": f"无法访问站点: {home.error}", "url": site_url}

        # 尝试推测搜索 URL 模式
        search_patterns = self._guess_search_patterns(home, site_url, test_keyword)

        # 尝试推测目录和正文选择器
        suggested = {
            "ruleSearchUrl": search_patterns[0] if search_patterns else "",
            "ruleSearchList": ".search-result .item, ul.result-list li",
            "ruleSearchName": "h3 a, .title a",
            "ruleSearchAuthor": ".author, .writer",
            "ruleSearchCover": "img@src",
            "ruleSearchResultUrl": "a@href",
            "ruleChapterUrl": "#list a@href, .chapter-list a@href",
            "ruleChapterName": "#list a, .chapter-list a",
            "ruleContent": "#content, .content, .read-content",
        }

        source = BookSource(
            bookSourceName=site_name or f"自动分析 - {site_url[:30]}",
            bookSourceUrl=site_url,
            bookSourceGroup="自动分析",
            bookSourceType=0,
            **{k: v for k, v in suggested.items() if v},
        )

        valid, errors = src_engine.validate_source(source)

        return {
            "site_url": site_url,
            "site_title": home.title,
            "suggested_source": source.to_dict(),
            "search_patterns": search_patterns,
            "validation": {
                "valid": valid,
                "errors": errors,
            },
            "note": "自动分析结果仅供参考，建议手动调整选择器。",
        }

    def _guess_search_patterns(self, home_result, base_url, keyword) -> List[str]:
        patterns = []
        # 常见搜索 URL 模式
        common_patterns = [
            f"{base_url.rstrip('/')}/search?q={keyword}",
            f"{base_url.rstrip('/')}/search?keyword={keyword}",
            f"{base_url.rstrip('/')}/search.php?keyword={keyword}",
            f"{base_url.rstrip('/')}/s?wd={keyword}",
        ]
        patterns.extend(common_patterns)

        # 从页面查找搜索表单
        import re
        form_actions = re.findall(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>', home_result.html, re.IGNORECASE)
        for action in form_actions:
            if "search" in action.lower() or "s?" in action.lower():
                patterns.append(action)

        return patterns[:5]

    def _analyze_search(self, crawler, params) -> Dict[str, Any]:
        search_url = params.get("search_url", "")
        result = crawler.fetch(search_url)
        if not result.success:
            return {"error": f"无法访问: {result.error}"}

        return {
            "url": search_url,
            "title": result.title,
            "links_count": len(result.links),
            "sample_links": result.links[:10],
            "suggested_selectors": {
                "result_item": ".search-result li, .book-item, ul li",
                "book_name": "h3 a, .title",
                "book_author": ".author, .writer",
                "book_cover": "img@src",
                "book_url": "a@href",
            },
            "note": "请根据实际页面结构调整选择器。支持 CSS 选择器和 @attr 语法。",
        }

    def _analyze_toc(self, crawler, params) -> Dict[str, Any]:
        toc_url = params.get("toc_url", "")
        result = crawler.fetch(toc_url)
        if not result.success:
            return {"error": f"无法访问: {result.error}"}

        # 统计链接数量，推测目录区域
        import re
        all_links = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', result.html)

        return {
            "url": toc_url,
            "title": result.title,
            "total_links": len(all_links),
            "sample_chapters": [{"name": name.strip(), "url": url} for url, name in all_links[:20]],
            "suggested_selectors": {
                "chapter_list": "#list dl, .chapter-list ul, .listmain dl",
                "chapter_name": "dd a, .chapter a",
                "chapter_url": "dd a@href, .chapter a@href",
            },
            "note": "请根据实际页面结构调整选择器。",
        }

    def _analyze_content(self, crawler, params) -> Dict[str, Any]:
        content_url = params.get("content_url", "")
        result = crawler.fetch(content_url)
        if not result.success:
            return {"error": f"无法访问: {result.error}"}

        # 提取可能的正文区域
        import re
        text_blocks = re.findall(r'<div[^>]*id=["\'](content|content1|nr1|booktext)["\'][^>]*>(.*?)</div>', result.html, re.IGNORECASE | re.DOTALL)

        return {
            "url": content_url,
            "title": result.title,
            "text_length": len(result.text),
            "content_candidates": [bid for bid, _ in text_blocks],
            "suggested_selectors": {
                "content": "#content, .read-content, #nr1",
                "next_url": "#next_url@href, .next a@href",
            },
            "preview": result.text[:500],
            "note": "请根据实际页面结构调整正文选择器。",
        }

    # ===== 书源编写 =====

    def _create(self, src_engine, params) -> Dict[str, Any]:
        source = BookSource(
            bookSourceName=params.get("bookSourceName", ""),
            bookSourceUrl=params.get("bookSourceUrl", ""),
            bookSourceGroup=params.get("bookSourceGroup", "未分组"),
            bookSourceType=params.get("bookSourceType", 0),
            ruleSearchUrl=params.get("ruleSearchUrl", ""),
            ruleChapterName=params.get("ruleChapterName", ""),
            ruleContent=params.get("ruleContent", ""),
        )

        added = src_engine.add_source(source)
        valid, errors = src_engine.validate_source(source)

        return {
            "success": added,
            "source": source.to_dict(),
            "validation": {
                "valid": valid,
                "errors": errors,
            },
            "total_sources": src_engine.count,
        }

    def _validate(self, crawler, src_engine, params) -> Dict[str, Any]:
        bookSourceUrl = params.get("bookSourceUrl", "")
        source = src_engine.get_source(bookSourceUrl)
        if not source:
            return {"error": f"书源不存在: {bookSourceUrl}"}

        valid, errors = src_engine.validate_source(source)

        # 测试搜索
        test_search = params.get("test_search", True)
        test_result = None
        if test_search and source.ruleSearchUrl:
            test_keyword = params.get("test_keyword", "斗破苍穹")
            search_url = source.ruleSearchUrl.replace("{keyword}", test_keyword).replace("{key}", test_keyword)
            crawl_result = crawler.fetch(search_url)
            test_result = {
                "url": search_url,
                "status": crawl_result.status,
                "success": crawl_result.success,
                "title": crawl_result.title,
            }

        return {
            "source": source.to_dict(),
            "validation": {
                "valid": valid,
                "errors": errors,
            },
            "search_test": test_result,
        }

    def _template(self, src_engine, params) -> Dict[str, Any]:
        source_type = params.get("source_type", "text")
        template = src_engine.generate_source_template(source_type)
        return {
            "template": template.to_dict(),
            "type": source_type,
            "note": "修改模板后调用 source_create 创建书源。",
        }

    # ===== 书源管理 =====

    def _import(self, src_engine, params) -> Dict[str, Any]:
        json_data = params.get("json_data", "")
        count = src_engine.import_from_json(json_data)
        return {"imported": count, "total_sources": src_engine.count}

    def _export(self, src_engine, params) -> Dict[str, Any]:
        group = params.get("group", "")
        enabled_only = params.get("enabled_only", False)
        sources = src_engine.list_sources(group=group, enabled_only=enabled_only)
        json_str = src_engine.export_to_json(sources)
        return {"exported": len(sources), "json": json_str}

    def _remove(self, src_engine, params) -> Dict[str, Any]:
        bookSourceUrl = params.get("bookSourceUrl", "")
        removed = src_engine.remove_source(bookSourceUrl)
        return {"removed": removed, "total_sources": src_engine.count}

    # ===== 工具方法 =====

    def _type_to_int(self, type_str: str) -> int:
        return {"text": 0, "audio": 1, "image": 2}.get(type_str, 0)

    def _type_to_str(self, type_int: int) -> str:
        return {0: "text", 1: "audio", 2: "image"}.get(type_int, "text")

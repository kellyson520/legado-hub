"""
源兼容性规则集与兜底机制

当自动写源引擎无法完美解析时，使用预定义的网站规则模板进行兜底。
同时提供常见书源网站的兼容性修复规则。
"""

import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse


# ==================== 网站兼容性规则模板 ====================

SITE_COMPATIBILITY_RULES: Dict[str, Dict[str, Any]] = {
    "qidian.com": {
        "bookSourceName": "起点中文网",
        "bookSourceGroup": "官方正版",
        "header": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ruleSearch": {
            "bookList": "class.book-list@tag.li",
            "name": "class.book-info@tag.h4@tag.a@text",
            "author": "class.book-info@class.author@tag.a@text",
            "intro": "class.book-info@class.intro@text",
            "coverUrl": "class.book-img@tag.img@src",
            "bookUrl": "class.book-info@tag.h4@tag.a@href"
        },
        "ruleBookInfo": {
            "name": "class.book-info@tag.h1@text",
            "author": "class.book-info@class.writer@text",
            "intro": "class.book-intro@text",
            "coverUrl": "class.book-img@tag.img@src",
            "lastChapter": "class.chapter-item@text",
            "wordCount": "class.book-info@tag.em@text"
        },
        "ruleToc": {
            "chapterList": "class.chapter-item",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "class.read-content@html",
            "nextContentUrl": "class.chapter-control@tag.a.1@href"
        }
    },
    "bqgiu": {
        "_pattern": r"(?:^|\.)bqgiu\.cc$",
        "bookSourceName": "笔趣阁 bqgiu",
        "bookSourceGroup": "笔趣阁系列",
        "header": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        # The public search page hydrates through browser-side ajax and can
        # return a sentinel to server-side clients. Use the server-rendered
        # hot/recommend cards as a deterministic source-build probe entrypoint;
        # operators can refine the generated rule after validation.
        "searchUrl": "https://www.bqgiu.cc/",
        "ruleSearch": {
            "bookList": "class.hot@class.item",
            "name": "tag.dt@tag.a@text",
            "author": "tag.dt@tag.span@text",
            "intro": "tag.dd@text",
            "coverUrl": "class.image@tag.img@src",
            "bookUrl": "tag.dt@tag.a@href"
        },
        "ruleBookInfo": {
            "name": "id.info@tag.h1@text || class.info@tag.h1@text || property.og:novel:book_name@content",
            "author": "id.info@tag.p.0@text##作者： || property.og:novel:author@content",
            "intro": "id.intro@text || class.intro@text || property.og:description@content",
            "coverUrl": "id.fmimg@tag.img@src || class.cover@tag.img@src || property.og:image@content",
            "lastChapter": "id.info@tag.p.3@tag.a@text || property.og:novel:latest_chapter_name@content"
        },
        "ruleToc": {
            "chapterList": "id.list@tag.dd || class.listmain@tag.dd || class.book_list@tag.dd",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "id.chaptercontent@html || id.content@html || class.Readarea@html",
            "title": "id.title@text || class.bookname@tag.h1@text || tag.h1@text",
            "nextContentUrl": "class.bottem2@tag.a.2@href || class.page_chapter@tag.a.-1@href"
        }
    },
    "biquge": {
        "_pattern": r"biquge\d*\.(cc|com|net|org)",
        "bookSourceGroup": "笔趣阁系列",
        "header": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "ruleSearch": {
            "bookList": "class.result-list@tag.div",
            "name": "class.result-item-title@tag.a@text",
            "author": "class.result-game-item-info.0@tag.p.0@tag.span.1@text",
            "intro": "class.result-game-item-desc@text",
            "coverUrl": "class.result-game-item-pic@tag.img@src",
            "bookUrl": "class.result-item-title@tag.a@href"
        },
        "ruleBookInfo": {
            "name": "id.info@tag.h1@text",
            "author": "id.info@tag.p.0@text##作.*?者：",
            "intro": "id.intro@text",
            "coverUrl": "id.fmimg@tag.img@src",
            "lastChapter": "id.info@tag.p.3@tag.a@text"
        },
        "ruleToc": {
            "chapterList": "id.list@tag.dd",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "id.content@html",
            "nextContentUrl": "class.bottem2@tag.a.2@href"
        }
    },
    "69shu": {
        "_pattern": r"69shu\.(top|com)",
        "bookSourceGroup": "69书吧",
        "header": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "ruleSearch": {
            "bookList": "class.newbox@tag.ul@tag.li",
            "name": "class.ellipsis@text",
            "author": "tag.span.1@text",
            "bookUrl": "tag.a@href"
        },
        "ruleBookInfo": {
            "name": "class.booknav2@tag.h1@text##/.*",
            "author": "class.booknav2@tag.a.0@text",
            "intro": "class.navtxt@text",
            "coverUrl": "class.bookimg@tag.img@src"
        },
        "ruleToc": {
            "chapterList": "class.catalog@tag.ul@tag.li",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "class.txtnav@html",
            "nextContentUrl": "class.page2@tag.a.-1@href"
        }
    },
    "zongheng.com": {
        "bookSourceName": "纵横中文网",
        "bookSourceGroup": "官方正版",
        "header": "User-Agent: Mozilla/5.0",
        "ruleSearch": {
            "bookList": "class.search-result-list@tag.li",
            "name": "class.bookname@tag.a@text",
            "author": "class.bookinfo@tag.a.0@text",
            "intro": "class.bookintro@text",
            "coverUrl": "class.bookimg@tag.img@src",
            "bookUrl": "class.bookname@tag.a@href"
        },
        "ruleBookInfo": {
            "name": "class.book-name@text",
            "author": "class.book-author@tag.a@text",
            "intro": "class.book-dec@text",
            "coverUrl": "class.book-img@tag.img@src"
        },
        "ruleToc": {
            "chapterList": "class.chapter-list@tag.li",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "class.content@html"
        }
    },
    "jx.la": {
        "bookSourceName": "晋江文学城",
        "bookSourceGroup": "官方正版",
        "header": "User-Agent: Mozilla/5.0",
        "ruleSearch": {
            "bookList": "class.grid@tag.tr!0",
            "name": "tag.td.1@tag.a@text",
            "author": "tag.td.2@text",
            "bookUrl": "tag.td.1@tag.a@href"
        },
        "ruleBookInfo": {
            "name": "class.noveltitle@text",
            "author": "class.noveleditor@text",
            "intro": "class.novelintro@text"
        },
        "ruleToc": {
            "chapterList": "class.noveltextlist@tag.li",
            "chapterName": "tag.a@text",
            "chapterUrl": "tag.a@href"
        },
        "ruleContent": {
            "content": "class.noveltext@html"
        }
    }
}


# ==================== 通用兜底规则 ====================

FALLBACK_RULES = {
    "ruleSearch": {
        "bookList": "tag.article || class.book-item || class.result-item || tag.li",
        "name": "tag.h2@text || tag.h3@text || class.title@text || tag.a@text",
        "author": "class.author@text || tag.span@text",
        "intro": "class.desc@text || class.summary@text || class.intro@text",
        "coverUrl": "tag.img@src",
        "bookUrl": "tag.a@href"
    },
    "ruleBookInfo": {
        "name": "tag.h1@text",
        "author": "class.author@text || tag.a@text",
        "intro": "class.intro@text || class.summary@text || id.intro@text",
        "coverUrl": "tag.img@src",
        "lastChapter": "class.last-chapter@text || tag.a.-1@text"
    },
    "ruleToc": {
        "chapterList": "class.chapter-list@tag.a || id.list@tag.a || tag.ul@tag.li",
        "chapterName": "tag.a@text",
        "chapterUrl": "tag.a@href"
    },
    "ruleContent": {
        "content": "class.content@html || id.content@html || article@html || class.text@html",
        "nextContentUrl": "class.next@tag.a@href || tag.a.-1@href"
    }
}


class CompatibilityEngine:
    """书源兼容性引擎 - 提供规则匹配、修复和兜底功能"""
    
    @staticmethod
    def match_site(url: str) -> Optional[str]:
        """根据 URL 匹配网站规则"""
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        
        for site_key, rules in SITE_COMPATIBILITY_RULES.items():
            # 直接匹配域名
            if site_key in hostname:
                return site_key
            # 正则匹配
            pattern = rules.get("_pattern")
            if pattern and re.search(pattern, hostname):
                return site_key
        
        return None
    
    @staticmethod
    def get_site_rules(site_key: str) -> Dict[str, Any]:
        """获取网站的完整规则模板"""
        rules = SITE_COMPATIBILITY_RULES.get(site_key, {})
        # 移除内部字段
        return {k: v for k, v in rules.items() if not k.startswith("_")}
    
    @staticmethod
    def apply_fallback(source: Dict[str, Any]) -> Dict[str, Any]:
        """对不完整的书源应用兜底规则"""
        result = source.copy()
        
        # 补充缺失的规则字段
        for rule_key, rule_value in FALLBACK_RULES.items():
            if not result.get(rule_key):
                result[rule_key] = rule_value
        
        # 补充基础字段
        if not result.get("header"):
            result["header"] = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        if not result.get("enabled"):
            result["enabled"] = True
        
        if not result.get("enabledCookieJar"):
            result["enabledCookieJar"] = True
        
        # 搜索URL兜底
        if not result.get("searchUrl"):
            base_url = result.get("bookSourceUrl", "")
            if base_url:
                result["searchUrl"] = f"{base_url}/search?keyword={{key}}"
        
        return result
    
    @staticmethod
    def generate_from_url(url: str, source_name: Optional[str] = None) -> Dict[str, Any]:
        """
        从 URL 自动生成书源（带兼容性规则）
        这是写源引擎的最终兜底手段
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or "unknown"
        
        # 尝试匹配已知网站
        site_key = CompatibilityEngine.match_site(url)
        
        base_source = {
            "bookSourceUrl": url,
            "bookSourceName": source_name or hostname,
            "bookSourceType": 0,
            "enabled": True,
            "enabledCookieJar": True,
            "header": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "concurrentRate": "500",
            "respondTime": 180000
        }
        
        if site_key:
            # 应用已知网站规则
            site_rules = CompatibilityEngine.get_site_rules(site_key)
            base_source.update(site_rules)
            if source_name:
                base_source["bookSourceName"] = source_name
            base_source["bookSourceComment"] = f"[兼容性规则] 基于 {site_key} 模板生成"
        else:
            # 未知网站，应用通用兜底规则
            base_source.update(FALLBACK_RULES)
            base_source["bookSourceComment"] = "[兜底规则] 未知网站，使用通用选择器，可能需要手动调整"
        
        # 构建搜索URL（如果缺失）
        if not base_source.get("searchUrl"):
            base_source["searchUrl"] = f"{url}/search?keyword={{key}}"
        
        return base_source
    
    @staticmethod
    def repair_source(source: Dict[str, Any]) -> Dict[str, Any]:
        """修复已有书源的常见问题"""
        repaired = source.copy()
        fixes = []
        
        # 修复 1: 相对路径问题
        if repaired.get("ruleToc", {}).get("chapterUrl", "").startswith("/"):
            if "@@" not in repaired["ruleToc"]["chapterUrl"]:
                repaired["ruleToc"]["chapterUrl"] += "##$##$"
                fixes.append("修复章节链接相对路径")
        
        # 修复 2: 缺少 header
        if not repaired.get("header"):
            repaired["header"] = "User-Agent: Mozilla/5.0"
            fixes.append("添加默认请求头")
        
        # 修复 3: content 规则缺少 html 标记
        content_rule = repaired.get("ruleContent", {}).get("content", "")
        if content_rule and "@html" not in content_rule and "@text" not in content_rule:
            repaired["ruleContent"]["content"] += "@html"
            fixes.append("内容规则添加@html标记")
        
        # 修复 4: searchUrl 缺少占位符
        search_url = repaired.get("searchUrl", "")
        if search_url and "{" not in search_url:
            if "?" in search_url:
                repaired["searchUrl"] += "&keyword={key}"
            else:
                repaired["searchUrl"] += "?keyword={key}"
            fixes.append("搜索URL添加关键词占位符")
        
        # 修复 5: 超时时间不合理
        respond_time = repaired.get("respondTime", 0)
        if respond_time < 5000:
            repaired["respondTime"] = 180000
            fixes.append("响应超时时间调整为180秒")
        
        repaired["_fixes"] = fixes
        return repaired
    
    @staticmethod
    def get_compatibility_score(source: Dict[str, Any]) -> Dict[str, Any]:
        """评估书源的兼容性得分"""
        score = 100
        issues = []
        
        required_fields = ["bookSourceUrl", "bookSourceName", "ruleSearch", "ruleToc", "ruleContent"]
        for field in required_fields:
            if not source.get(field):
                score -= 15
                issues.append(f"缺少必要字段: {field}")
        
        if not source.get("header"):
            score -= 5
            issues.append("缺少请求头")
        
        if not source.get("searchUrl"):
            score -= 10
            issues.append("缺少搜索URL")
        
        search_url = source.get("searchUrl", "")
        if search_url and "{" not in search_url:
            score -= 10
            issues.append("搜索URL缺少关键词占位符")
        
        return {
            "score": max(0, score),
            "grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D",
            "issues": issues,
            "is_usable": score >= 50
        }


# 全局实例
compat_engine = CompatibilityEngine()

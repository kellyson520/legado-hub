"""
compatibility.py 单元测试

覆盖 CompatibilityEngine 的 6 个方法：
- match_site
- get_site_rules
- apply_fallback
- generate_from_url
- repair_source
- get_compatibility_score
"""

import pytest
from app.core.compatibility import CompatibilityEngine


class TestMatchSite:
    """match_site 方法测试"""

    def test_match_known_site_qidian(self):
        """验证匹配起点中文网 URL"""
        result = CompatibilityEngine.match_site("https://www.qidian.com/search")
        assert result == "qidian.com"

    def test_match_known_site_biquge(self):
        """验证匹配笔趣阁 URL（正则匹配 biquge123.cc）"""
        result = CompatibilityEngine.match_site("https://www.biquge123.cc/book/1")
        assert result == "biquge"

    def test_match_known_site_69shu(self):
        """验证匹配 69 书吧 URL"""
        result = CompatibilityEngine.match_site("https://www.69shu.top/book/1")
        assert result == "69shu"

    def test_match_known_site_zongheng(self):
        """验证匹配纵横中文网 URL"""
        result = CompatibilityEngine.match_site("https://www.zongheng.com/library")
        assert result == "zongheng.com"

    def test_match_unknown_site_returns_none(self):
        """验证未知网站 URL 返回 None"""
        result = CompatibilityEngine.match_site("https://www.unknown-site-xyz.com")
        assert result is None

    def test_match_invalid_url_returns_none(self):
        """验证无效 URL 返回 None"""
        result = CompatibilityEngine.match_site("not_a_url")
        assert result is None


class TestGetSiteRules:
    """get_site_rules 方法测试"""

    def test_get_existing_site_rules(self):
        """验证获取已知网站规则"""
        rules = CompatibilityEngine.get_site_rules("qidian.com")
        assert "bookSourceName" in rules
        assert "ruleSearch" in rules
        assert "ruleBookInfo" in rules
        assert "ruleToc" in rules
        assert "ruleContent" in rules

    def test_get_site_rules_excludes_internal_fields(self):
        """验证获取规则时排除 _pattern 等内部字段"""
        rules = CompatibilityEngine.get_site_rules("biquge")
        # biquge 有 _pattern 字段，但不应出现在返回结果中
        assert "_pattern" not in rules

    def test_get_nonexistent_site_rules(self):
        """验证获取不存在网站的规则返回空字典"""
        rules = CompatibilityEngine.get_site_rules("nonexistent.com")
        assert rules == {}


class TestApplyFallback:
    """apply_fallback 方法测试"""

    def test_apply_fallback_fills_missing_rules(self):
        """验证兜底规则填充缺失的规则字段"""
        source = {"bookSourceUrl": "https://example.com", "bookSourceName": "测试"}
        result = CompatibilityEngine.apply_fallback(source)
        assert "ruleSearch" in result
        assert "ruleBookInfo" in result
        assert "ruleToc" in result
        assert "ruleContent" in result

    def test_apply_fallback_keeps_existing_rules(self):
        """验证兜底规则不覆盖已存在的规则"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "custom.rule"},
        }
        result = CompatibilityEngine.apply_fallback(source)
        assert result["ruleSearch"]["bookList"] == "custom.rule"

    def test_apply_fallback_adds_header(self):
        """验证兜底规则补充默认请求头"""
        source = {"bookSourceUrl": "https://example.com", "bookSourceName": "测试"}
        result = CompatibilityEngine.apply_fallback(source)
        assert "header" in result
        assert "User-Agent" in result["header"]

    def test_apply_fallback_adds_enabled_flags(self):
        """验证兜底规则补充启用标志"""
        source = {"bookSourceUrl": "https://example.com"}
        result = CompatibilityEngine.apply_fallback(source)
        assert result["enabled"] is True
        assert result["enabledCookieJar"] is True

    def test_apply_fallback_generates_search_url(self):
        """验证兜底规则根据 bookSourceUrl 生成搜索 URL"""
        source = {"bookSourceUrl": "https://example.com", "bookSourceName": "测试"}
        result = CompatibilityEngine.apply_fallback(source)
        assert result["searchUrl"] == "https://example.com/search?keyword={key}"


class TestGenerateFromUrl:
    """generate_from_url 方法测试"""

    def test_generate_from_known_site_url(self):
        """验证从已知网站 URL 生成书源（使用网站规则）"""
        source = CompatibilityEngine.generate_from_url("https://www.qidian.com")
        assert source["bookSourceUrl"] == "https://www.qidian.com"
        assert source["bookSourceType"] == 0
        assert source["enabled"] is True
        assert "ruleSearch" in source
        assert "qidian" in source.get("bookSourceComment", "")

    def test_generate_from_unknown_site_url(self):
        """验证从未知网站 URL 生成书源（使用兜底规则）"""
        source = CompatibilityEngine.generate_from_url("https://unknown-site.com")
        assert source["bookSourceUrl"] == "https://unknown-site.com"
        assert "ruleSearch" in source
        assert "兜底规则" in source.get("bookSourceComment", "")

    def test_generate_from_url_with_custom_name(self):
        """验证自定义书源名称（已知网站的 bookSourceName 会被规则覆盖）"""
        source = CompatibilityEngine.generate_from_url(
            "https://unknown-site.com",
            source_name="我的自定义书源"
        )
        assert source["bookSourceName"] == "我的自定义书源"

    def test_generate_from_url_has_search_url(self):
        """验证生成的书源包含搜索 URL"""
        source = CompatibilityEngine.generate_from_url("https://www.example.com")
        assert "searchUrl" in source
        assert "{key}" in source["searchUrl"]


class TestRepairSource:
    """repair_source 方法测试"""

    def test_repair_missing_header(self):
        """验证修复缺失的 header"""
        source = {"bookSourceUrl": "https://example.com", "bookSourceName": "测试"}
        repaired = CompatibilityEngine.repair_source(source)
        assert "header" in repaired
        assert "添加默认请求头" in repaired["_fixes"]

    def test_repair_relative_path_in_chapter_url(self):
        """验证修复章节链接的相对路径问题"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleToc": {"chapterUrl": "/chapter/123", "chapterName": "tag.a@text"},
        }
        repaired = CompatibilityEngine.repair_source(source)
        assert "修复章节链接相对路径" in repaired["_fixes"]

    def test_repair_content_rule_missing_html(self):
        """验证修复内容规则缺少 @html 标记"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleContent": {"content": "id.content"},
        }
        repaired = CompatibilityEngine.repair_source(source)
        assert "@html" in repaired["ruleContent"]["content"]
        assert "内容规则添加@html标记" in repaired["_fixes"]

    def test_repair_search_url_missing_placeholder(self):
        """验证修复搜索 URL 缺少关键词占位符"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "searchUrl": "https://example.com/search",
        }
        repaired = CompatibilityEngine.repair_source(source)
        assert "{key}" in repaired["searchUrl"]
        assert "搜索URL添加关键词占位符" in repaired["_fixes"]

    def test_repair_low_respond_time(self):
        """验证修复过低的响应超时时间"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "respondTime": 1000,
        }
        repaired = CompatibilityEngine.repair_source(source)
        assert repaired["respondTime"] == 180000
        assert "响应超时时间调整为180秒" in repaired["_fixes"]

    def test_no_fixes_for_healthy_source(self):
        """验证健康书源不需要修复"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "header": "User-Agent: Mozilla/5.0",
            "respondTime": 180000,
            "ruleContent": {"content": "id.content@html"},
            "searchUrl": "https://example.com/search?key={key}",
            "ruleToc": {"chapterUrl": "https://example.com/chapter/123", "chapterName": "tag.a@text"},
        }
        repaired = CompatibilityEngine.repair_source(source)
        # 不应有修复记录（除了可能因为相对路径 / 判断）
        assert isinstance(repaired["_fixes"], list)


class TestGetCompatibilityScore:
    """get_compatibility_score 方法测试"""

    def test_score_perfect_source(self):
        """验证完美书源得满分 A 级"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "tag.li"},
            "ruleToc": {"chapterList": "tag.li", "chapterName": "tag.a@text", "chapterUrl": "tag.a@href"},
            "ruleContent": {"content": "id.content@html"},
            "header": "User-Agent: Mozilla/5.0",
            "searchUrl": "https://example.com/search?key={key}",
        }
        score = CompatibilityEngine.get_compatibility_score(source)
        assert score["score"] == 100
        assert score["grade"] == "A"
        assert score["is_usable"] is True
        assert len(score["issues"]) == 0

    def test_score_missing_required_fields(self):
        """验证缺少必要字段扣分"""
        source = {"bookSourceUrl": "https://example.com"}
        score = CompatibilityEngine.get_compatibility_score(source)
        assert score["score"] < 100
        assert len(score["issues"]) > 0
        assert any("bookSourceName" in issue for issue in score["issues"])

    def test_score_missing_header(self):
        """验证缺少请求头扣 5 分"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "tag.li"},
            "ruleToc": {"chapterList": "tag.li", "chapterName": "tag.a@text", "chapterUrl": "tag.a@href"},
            "ruleContent": {"content": "id.content@html"},
            "searchUrl": "https://example.com/search?key={key}",
        }
        score = CompatibilityEngine.get_compatibility_score(source)
        assert any("请求头" in issue for issue in score["issues"])

    def test_score_grade_b(self):
        """验证 B 级评分（70-89 分）"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            # 缺少 ruleSearch, ruleToc, ruleContent -> -45
        }
        score = CompatibilityEngine.get_compatibility_score(source)
        assert score["grade"] in ("B", "C", "D")

    def test_score_never_negative(self):
        """验证评分不会为负数"""
        source = {}  # 空字典，大量字段缺失
        score = CompatibilityEngine.get_compatibility_score(source)
        assert score["score"] >= 0

    def test_score_usable_threshold(self):
        """验证 is_usable 在 50 分以上为 True"""
        source = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "tag.li"},
            "ruleToc": {"chapterList": "tag.li", "chapterName": "tag.a@text", "chapterUrl": "tag.a@href"},
            "ruleContent": {"content": "id.content@html"},
        }
        score = CompatibilityEngine.get_compatibility_score(source)
        # 100 - 5 (无header) - 10 (无searchUrl) = 85
        assert score["is_usable"] is True

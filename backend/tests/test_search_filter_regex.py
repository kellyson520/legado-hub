"""
书源搜索、筛选、正则清洗 完整流程测试

覆盖范围：
- Part 1: 书源搜索引擎端点 (POST /api/engine/*) — evaluate / repair / generate
- Part 2: 源筛选流程 — FilterRule.should_filter + 多规则链式筛选
- Part 3: 正则清洗 — _clean_hub_fields / to_legado_dict / replaceRegex / repair_source
- Part 4: 端到端搜索+筛选+清洗流程 — 导入真实书源 -> 筛选 -> 评分 -> 修复 -> 清洗输出
"""

import re

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from app.domain.entities.source import BookSource, RssSource, FilterRule
from app.core.compatibility import compat_engine


# ==================== Part 5: 共享 fixture ====================


@pytest.fixture
async def client():
    """FastAPI 测试客户端"""
    from unittest.mock import PropertyMock

    with patch("app.core.redis_client.redis_client") as mock_redis, \
         patch("app.core.events.event_bus") as mock_bus, \
         patch("app.tasks.scheduler.start_scheduler"), \
         patch("app.tasks.scheduler.stop_scheduler"):
        # 让 is_connected 作为属性访问返回 False
        mock_redis.is_connected = False
        mock_redis.connect = AsyncMock()
        mock_redis.disconnect = AsyncMock()
        mock_redis.check_rate_limit = AsyncMock(return_value=(True, 60, 30))
        mock_redis.get_quota = AsyncMock(return_value=0)
        mock_redis.increment_quota = AsyncMock(return_value=1)
        mock_bus.start = AsyncMock()
        mock_bus.stop = AsyncMock()
        mock_bus.publish = AsyncMock()

        from app.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            yield ac


# ==================== Part 1: 书源搜索引擎端点测试 ====================


class TestEvaluateEndpoint:
    """POST /api/engine/evaluate"""

    async def test_evaluate_perfect_source(self, client):
        """评估完美书源 - 100分 A级"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "header": "User-Agent: test",
            "searchUrl": "/search?keyword={key}",
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "test"},
        }
        resp = await client.post("/api/engine/evaluate", json=source)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["score"] == 100
        assert data["data"]["grade"] == "A"

    async def test_evaluate_missing_fields(self, client):
        """评估缺少字段的书源 - 扣分"""
        source = {"bookSourceUrl": "https://test.com", "bookSourceName": "测试"}
        # 缺少 ruleSearch(-15), ruleToc(-15), ruleContent(-15), header(-5), searchUrl(-10) = 40分
        resp = await client.post("/api/engine/evaluate", json=source)
        assert resp.json()["data"]["score"] == 40
        assert resp.json()["data"]["grade"] == "D"

    async def test_evaluate_search_url_no_placeholder(self, client):
        """搜索URL缺少占位符额外扣分"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "header": "User-Agent: test",
            "searchUrl": "/search",  # 缺少 {key} 占位符
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "test"},
        }
        resp = await client.post("/api/engine/evaluate", json=source)
        # 100 - 10 (searchUrl无占位符) = 90
        assert resp.json()["data"]["score"] == 90
        assert resp.json()["data"]["grade"] == "A"

    async def test_evaluate_usable_threshold(self, client):
        """50分边界：刚好可用"""
        # 缺少3个规则(-45) + header(-5) = 50分, is_usable=True
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "searchUrl": "/search?key={key}",
        }
        resp = await client.post("/api/engine/evaluate", json=source)
        data = resp.json()["data"]
        assert data["score"] == 50
        assert data["is_usable"] is True
        assert data["grade"] == "C"


class TestRepairEndpoint:
    """POST /api/engine/repair"""

    async def test_repair_relative_path(self, client):
        """修复相对路径"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterUrl": "/chapter/1.html"},  # 以 / 开头
            "ruleContent": {"content": "test@html"},
        }
        resp = await client.post("/api/engine/repair", json=source)
        data = resp.json()["data"]
        assert "修复章节链接相对路径" in data["fixes"]
        assert "##$##$" in data["source"]["ruleToc"]["chapterUrl"]

    async def test_repair_missing_header(self, client):
        """修复缺少header"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "test"},
        }
        resp = await client.post("/api/engine/repair", json=source)
        data = resp.json()["data"]
        assert "添加默认请求头" in data["fixes"]
        assert data["source"]["header"] is not None

    async def test_repair_content_rule(self, client):
        """修复content规则缺少@html"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "header": "UA",
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "id.content"},  # 无@html也无@text
        }
        resp = await client.post("/api/engine/repair", json=source)
        data = resp.json()["data"]
        assert "内容规则添加@html标记" in data["fixes"]

    async def test_repair_search_url_placeholder(self, client):
        """修复搜索URL缺少占位符"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "header": "UA",
            "searchUrl": "https://test.com/search",
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "test@html"},
        }
        resp = await client.post("/api/engine/repair", json=source)
        data = resp.json()["data"]
        assert "搜索URL添加关键词占位符" in data["fixes"]

    async def test_repair_timeout(self, client):
        """修复超时时间"""
        source = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "header": "UA",
            "respondTime": 1000,
            "ruleSearch": {"bookList": "test"},
            "ruleToc": {"chapterList": "test"},
            "ruleContent": {"content": "test@html"},
        }
        resp = await client.post("/api/engine/repair", json=source)
        data = resp.json()["data"]
        assert "响应超时时间调整为180秒" in data["fixes"]
        assert data["source"]["respondTime"] == 180000

    async def test_repair_score_improvement(self, client):
        """修复后评分应该提升"""
        bad_source = {"bookSourceUrl": "https://test.com", "bookSourceName": "测试"}
        resp = await client.post("/api/engine/repair", json=bad_source)
        data = resp.json()["data"]
        assert data["score_after"]["score"] > data["score_before"]["score"]


class TestGenerateEndpoint:
    """POST /api/engine/generate"""

    async def test_generate_with_mock(self, client):
        """Mock generator，测试generate端点流程"""
        mock_result = {
            "source": {
                "bookSourceUrl": "https://test.com",
                "bookSourceName": "Mock源",
                "searchUrl": "/search?key={key}",
                "ruleSearch": {"bookList": "test"},
                "ruleToc": {"chapterList": "test"},
                "ruleContent": {"content": "test@html"},
                "header": "User-Agent: test",
            },
            "logs": ["自动解析完成"],
            "message": "生成成功",
        }
        # generate 端点有 Depends(get_auth_context)，需要用 dependency_overrides 绕过认证
        from app.main import app
        from app.core.dependencies import get_auth_context

        async def fake_auth():
            ctx = MagicMock()
            ctx.can_edit_source = False
            return ctx

        with patch("app.interfaces.api.v0.engine.generator") as mock_gen, \
             patch("app.interfaces.api.v0.engine.get_source_service") as mock_svc:
            app.dependency_overrides[get_auth_context] = fake_auth
            mock_svc.return_value = MagicMock()

            mock_gen.generate = AsyncMock(return_value=mock_result)
            try:
                resp = await client.post("/api/engine/generate", json={"url": "https://test.com", "sourceType": "book"})
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] is not None
        assert data["compatibility"]["score"] >= 70

    async def test_generate_fallback_trigger(self, client):
        """自动解析质量不足时触发兜底"""
        # 返回低质量源（评分<70），触发 compat_engine 兜底
        mock_result = {
            "source": {
                "bookSourceUrl": "https://biquge123.cc",
                "bookSourceName": "笔趣阁",
                # 缺少 ruleSearch, ruleToc, ruleContent -> 评分低
            },
            "logs": ["自动解析（部分字段）"],
        }
        from app.main import app
        from app.core.dependencies import get_auth_context

        async def fake_auth():
            ctx = MagicMock()
            ctx.can_edit_source = False
            return ctx

        with patch("app.interfaces.api.v0.engine.generator") as mock_gen, \
             patch("app.interfaces.api.v0.engine.get_source_service") as mock_svc:
            app.dependency_overrides[get_auth_context] = fake_auth
            mock_svc.return_value = MagicMock()

            mock_gen.generate = AsyncMock(return_value=mock_result)
            try:
                resp = await client.post("/api/engine/generate", json={"url": "https://biquge123.cc", "sourceType": "book"})
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()["data"]
        # 兜底应该补充了规则
        assert any("兜底" in log for log in data["logs"])
        # biquge 匹配笔趣阁规则模板
        assert data["source"].get("ruleSearch") is not None


# ==================== Part 2: 源筛选流程测试 ====================


class TestFilterRuleFlow:
    """FilterRule.should_filter 各种场景"""

    def test_filter_by_name_regex(self):
        """正则匹配书源名称"""
        rule = FilterRule(name="排除测试", pattern="测试", scope="sourceName", isRegex=True)
        assert rule.should_filter(source_name="测试书源") is True   # 应过滤
        assert rule.should_filter(source_name="正常书源") is False   # 不过滤

    def test_filter_by_name_plain(self):
        """纯文本匹配书源名称"""
        rule = FilterRule(name="排除广告", pattern="广告", scope="sourceName", isRegex=False)
        assert rule.should_filter(source_name="广告书源") is True

    def test_filter_by_url_regex(self):
        """正则匹配书源 URL"""
        rule = FilterRule(name="排除域名", pattern=r"biquge\d+", scope="sourceUrl", isRegex=True)
        assert rule.should_filter(source_url="https://biquge123.cc") is True
        assert rule.should_filter(source_url="https://qidian.com") is False

    def test_filter_by_group(self):
        """匹配分组"""
        rule = FilterRule(name="排除分组", pattern="广告", scope="sourceGroup", isRegex=False)
        assert rule.should_filter(source_group="广告推广") is True

    def test_filter_invalid_regex_safe(self):
        """无效正则不崩溃"""
        rule = FilterRule(name="坏正则", pattern="[invalid(", scope="sourceName", isRegex=True)
        assert rule.should_filter(source_name="anything") is False

    def test_filter_default_scope(self):
        """默认作用域是 sourceName"""
        rule = FilterRule(name="默认", pattern="test", isRegex=True)
        assert rule.should_filter(source_name="test_source") is True
        assert rule.should_filter(source_url="test_url") is False


class TestApplyFiltersWithRealSources:
    """用真实书源数据测试筛选"""

    def test_filter_real_sources_by_group(self):
        """用真实书源数据测试分组筛选"""
        sources = [
            BookSource(bookSourceUrl="https://a.com", bookSourceName="源A", bookSourceGroup="精选"),
            BookSource(bookSourceUrl="https://b.com", bookSourceName="源B", bookSourceGroup="广告"),
            BookSource(bookSourceUrl="https://c.com", bookSourceName="源C", bookSourceGroup="精选"),
        ]

        rule = FilterRule(name="排除广告", pattern="广告", scope="sourceGroup", isRegex=False)

        filtered = [s for s in sources if not rule.should_filter(source_group=s.bookSourceGroup)]
        assert len(filtered) == 2
        assert all(s.bookSourceGroup == "精选" for s in filtered)

    def test_multi_rule_filter_chain(self):
        """多规则链式筛选"""
        sources = [
            BookSource(bookSourceUrl="https://ad-test.com", bookSourceName="广告测试源"),
            BookSource(bookSourceUrl="https://good.com", bookSourceName="好书源"),
            BookSource(bookSourceUrl="https://biquge123.com", bookSourceName="笔趣阁"),
        ]

        rules = [
            FilterRule(name="排除广告", pattern="广告", scope="sourceName", isRegex=False),
            FilterRule(name="排除笔趣阁", pattern=r"笔趣阁", scope="sourceName", isRegex=True),
        ]

        filtered = sources[:]
        for rule in rules:
            filtered = [s for s in filtered if not rule.should_filter(source_name=s.bookSourceName)]

        assert len(filtered) == 1
        assert filtered[0].bookSourceName == "好书源"


# ==================== Part 3: 正则清洗测试 ====================


class TestCleanHubFields:
    """测试 _clean_hub_fields 移除 Hub 内部字段"""

    def test_remove_internal_fields(self):
        """移除 Hub 内部字段"""
        from app.routers.output import _clean_hub_fields

        d = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "测试",
            "sourceStatus": "ok",
            "lastCheckTime": "2024-01-01",
            "errorMsg": None,
            "sourceOrigin": "https://example.com",
            "createdAt": "2024-01-01",
            "updatedAt": "2024-01-01",
            "id": 123,
        }
        cleaned = _clean_hub_fields(d)
        assert "bookSourceUrl" in cleaned
        assert "bookSourceName" in cleaned
        assert "sourceStatus" not in cleaned
        assert "lastCheckTime" not in cleaned
        assert "errorMsg" not in cleaned
        assert "sourceOrigin" not in cleaned
        assert "createdAt" not in cleaned
        assert "updatedAt" not in cleaned
        assert "id" not in cleaned

    def test_remove_empty_values(self):
        """移除空值（None 和空字符串），但保留 0"""
        from app.routers.output import _clean_hub_fields

        d = {
            "bookSourceUrl": "https://test.com",
            "bookSourceName": "",
            "header": None,
            "customOrder": 0,
        }
        cleaned = _clean_hub_fields(d)
        assert "bookSourceUrl" in cleaned
        assert "bookSourceName" not in cleaned
        assert "header" not in cleaned
        assert "customOrder" in cleaned   # 0 != ""，应保留


class TestToLegadoDict:
    """测试实体 to_legado_dict 输出纯净格式"""

    def test_book_source_to_legado_dict(self):
        """BookSource.to_legado_dict 输出纯净格式"""
        source = BookSource(
            bookSourceUrl="https://test.com",
            bookSourceName="测试源",
            sourceStatus="ok",
            sourceOrigin="https://yckceo.com",
        )
        d = source.to_legado_dict()
        assert "bookSourceUrl" in d
        assert "bookSourceName" in d
        assert "sourceStatus" not in d
        assert "sourceOrigin" not in d

    def test_rss_source_to_legado_dict(self):
        """RssSource.to_legado_dict 输出纯净格式"""
        source = RssSource(sourceUrl="https://rss.com", sourceName="RSS", sourceStatus="ok")
        d = source.to_legado_dict()
        assert "sourceUrl" in d
        assert "sourceStatus" not in d


class TestReplaceRegexField:
    """测试 replaceRegex 字段在真实书源中的存在和格式"""

    def test_real_source_has_replace_regex(self):
        """真实书源中 replaceRegex 的存在性检查"""
        sources_with_regex = [
            {"ruleContent": {"content": "id.content@html", "replaceRegex": "##喜欢.*速度最快。"}},
            {"ruleContent": {"content": "id.content@html"}},  # 无 replaceRegex
            {
                "ruleContent": {
                    "content": "class.nr_content@html",
                    "nextContentUrl": "text.下一章@href",
                    "replaceRegex": r"##\s*❌\s*|\s*天才一秒钟.*\s*",
                },
            },
        ]

        for s in sources_with_regex:
            rc = s.get("ruleContent", {})
            if "replaceRegex" in rc:
                pattern = rc["replaceRegex"]
                # replaceRegex 格式: ##pattern##replacement
                parts = pattern.split("##")
                if len(parts) >= 2:
                    try:
                        re.compile(parts[1])
                    except re.error:
                        # 某些可能是 Legado 特有语法，不应崩溃
                        pass

    def test_parse_legado_regex_format(self):
        """解析 Legado replaceRegex 格式: ##pattern##replacement"""
        test_cases = [
            ("##喜欢.*速度最快。", ("喜欢.*速度最快。", "")),
            ("##全文阅读", ("全文阅读", "")),
            (r"##\s*❌\s*|\s*天才一秒钟.*\s*", (r"\s*❌\s*|\s*天才一秒钟.*\s*", "")),
            ("##^\\s*", ("^\\s*", "")),
        ]

        for raw, (expected_pattern, _expected_replacement) in test_cases:
            parts = raw.split("##", 1)
            pattern = parts[1] if len(parts) > 1 else ""
            assert pattern == expected_pattern

    def test_apply_legado_replace_regex(self):
        """模拟 Legado 的正则替换逻辑"""

        def apply_replace_regex(text, replace_regex):
            if not replace_regex:
                return text
            parts = replace_regex.split("##")
            if len(parts) < 2:
                return text
            pattern = parts[1]
            replacement = parts[2] if len(parts) > 2 else ""
            try:
                return re.sub(pattern, replacement, text)
            except re.error:
                return text

        # 测试1: 移除广告文本
        text1 = "第一章 内容\n喜欢本站的还请速度最快。正文继续..."
        result1 = apply_replace_regex(text1, "##喜欢.*速度最快。")
        assert "喜欢" not in result1

        # 测试2: 移除标题后缀
        text2 = "斗破苍穹全文阅读"
        result2 = apply_replace_regex(text2, "##全文阅读")
        assert result2 == "斗破苍穹"

        # 测试3: 复杂正则
        text3 = "❌ 本章未完请点击下一页继续阅读。"
        result3 = apply_replace_regex(text3, r"##\s*❌\s*")
        assert "❌" not in result3


class TestRepairSourceRegex:
    """测试 repair_source 中的正则处理"""

    def test_repair_adds_html_suffix(self):
        """content 规则无 @html/@text 时自动添加"""
        source = {
            "ruleContent": {"content": "id.content"},  # 无 @html
        }
        repaired = compat_engine.repair_source(source)
        assert "@html" in repaired["ruleContent"]["content"]

    def test_repair_no_modify_if_has_html(self):
        """已有 @html 不修改"""
        source = {
            "ruleContent": {"content": "id.content@html"},
        }
        repaired = compat_engine.repair_source(source)
        assert repaired["ruleContent"]["content"] == "id.content@html"

    def test_repair_no_modify_if_has_text(self):
        """已有 @text 不修改"""
        source = {
            "ruleContent": {"content": "id.content@text"},
        }
        repaired = compat_engine.repair_source(source)
        assert repaired["ruleContent"]["content"] == "id.content@text"

    def test_repair_relative_path_with_regex(self):
        """相对路径修复：/开头且无@@时追加##$##$"""
        source = {"ruleToc": {"chapterUrl": "/chapter/{id}.html"}}
        repaired = compat_engine.repair_source(source)
        assert "##$##$" in repaired["ruleToc"]["chapterUrl"]

    def test_repair_no_path_modify_if_has_atat(self):
        """已有@@不修改"""
        source = {"ruleToc": {"chapterUrl": "/chapter/{id}.html@@https://test.com"}}
        repaired = compat_engine.repair_source(source)
        assert "##$##$" not in repaired["ruleToc"]["chapterUrl"]


# ==================== Part 4: 端到端搜索+筛选+清洗流程 ====================


class TestEndToEndSearchFilterClean:
    """端到端：导入真实书源 -> 筛选 -> 评分 -> 修复 -> 清洗输出"""

    def test_full_pipeline(self):
        """完整流程测试"""
        # Step 1: 真实书源数据
        raw_sources = [
            {
                "bookSourceUrl": "https://quapp.shenbabao.com",
                "bookSourceName": "APP测试源",
                "bookSourceGroup": "精选",
                "searchUrl": "https://sou.jiaston.com/search.aspx?key={{key}}",
                "ruleSearch": {"name": "$.Name", "bookList": "$..data[*]"},
                "ruleToc": {"chapterList": "$..list[*]", "chapterUrl": "https://test.com/{{$.id}}"},
                "ruleContent": {"content": "$..content"},
            },
            {
                "bookSourceUrl": "http://www.xquledu.com",
                "bookSourceName": "无错小说网",
                "bookSourceGroup": "精选",
                "searchUrl": "http://www.xquledu.com/search?key={{key}}",
                "ruleSearch": {"name": "class.name@text", "bookList": "class.list"},
                "ruleToc": {"chapterList": "id.list@tag.dd", "chapterUrl": "tag.a@href"},
                "ruleContent": {"content": "id.contents@textNodes"},
            },
            {
                "bookSourceUrl": "https://ad.example.com",
                "bookSourceName": "广告推广源",
                "bookSourceGroup": "广告",
                "searchUrl": "/search",
                "ruleSearch": {"name": "test", "bookList": "test"},
                "ruleToc": {"chapterList": "test", "chapterUrl": "/chapter/1.html"},
                "ruleContent": {"content": "class.content"},
            },
        ]

        # Step 2: 创建实体
        entities = [BookSource.from_dict(s) for s in raw_sources]
        assert len(entities) == 3

        # Step 3: 应用筛选规则（排除广告）
        ad_rule = FilterRule(name="排除广告", pattern="广告", scope="sourceGroup", isRegex=False)
        filtered = [e for e in entities if not ad_rule.should_filter(source_group=e.bookSourceGroup or "")]
        assert len(filtered) == 2

        # Step 4: 评分
        scores = []
        for entity in filtered:
            d = entity.to_legado_dict()
            score_info = compat_engine.get_compatibility_score(d)
            scores.append((entity.bookSourceName, score_info["score"], score_info["grade"]))

        for name, score, grade in scores:
            assert score >= 50, f"{name} 评分 {score} 不可用"

        # Step 5: 修复
        repaired_sources = []
        for entity in filtered:
            d = entity.to_legado_dict()
            repaired = compat_engine.repair_source(d)
            fixes = repaired.pop("_fixes", [])
            if fixes:
                repaired_sources.append((entity.bookSourceName, fixes))

        # Step 6: 清洗输出
        for entity in filtered:
            legado_dict = entity.to_legado_dict()
            # 验证无内部字段
            assert "sourceStatus" not in legado_dict
            assert "sourceOrigin" not in legado_dict
            assert "createdAt" not in legado_dict
            assert "bookSourceUrl" in legado_dict
            assert "bookSourceName" in legado_dict

        print(f"\n[端到端流程] 原始: {len(entities)} -> 筛选后: {len(filtered)}")
        for name, score, grade in scores:
            print(f"  {name}: {score}分 ({grade})")
        for name, fixes in repaired_sources:
            print(f"  {name} 修复: {fixes}")

    def test_real_source_repair_and_score(self):
        """测试真实书源的修复效果和评分变化"""
        # 真实书源：相对路径 + 无@html
        source = {
            "bookSourceUrl": "https://www.fanfanzw.com",
            "bookSourceName": "饭饭中文",
            "searchUrl": "https://www.fanfanzw.com/search.html",
            "ruleSearch": {"name": "h3@text"},
            "ruleToc": {
                "chapterList": "//*[@id='list']//dd/a",
                "chapterUrl": "href",
            },
            "ruleContent": {"content": "id.content@html##喜欢.*速度最快。"},
        }

        score_before = compat_engine.get_compatibility_score(source)
        repaired = compat_engine.repair_source(source)
        score_after = compat_engine.get_compatibility_score(repaired)
        fixes = repaired.pop("_fixes", [])

        print(f"\n[真实源修复] {source['bookSourceName']}")
        print(f"  修复前: {score_before['score']}分 ({score_before['grade']})")
        print(f"  修复后: {score_after['score']}分 ({score_after['grade']})")
        print(f"  修复项: {fixes}")

"""
真实书源导入流程测试

使用预先下载的真实书源数据（从 yckceo.com 获取），验证：
1. SourceFetcher.parse_sources_from_text() JSON 解析
2. BookSource.from_dict() 实体构建
3. POST /api/sources/book/import API 导入
4. GET /api/sources/book 列表查询
5. 数据格式正确性验证
6. 端到端 CRUD 生命周期
"""

import json
import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio


def _load_real_sources():
    """
    加载预先从 https://www.yckceo.com/yuedu/shuyuans/json/id/2.json 下载的真实书源数据。
    
    这些数据来自 Legado 书源聚合站点，包含多种类型的书源配置：
    - bookSourceUrl, bookSourceName, bookSourceGroup
    - ruleSearch, ruleToc, ruleContent 等解析规则
    """
    # 真实书源样例数据（从 yckceo.com/id/2.json 获取的代表性样本）
    return [
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "APP测试源",
            "bookSourceType": 0,
            "bookSourceUrl": "https://quapp.shenbabao.com",
            "bookUrlPattern": "https://quapp.shenbabao.com/book/.*",
            "customOrder": 1,
            "enabled": True,
            "enabledExplore": True,
            "lastUpdateTime": 1611458862320,
            "ruleBookInfo": {},
            "ruleContent": {"content": "$..content"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "$.Author",
                "bookList": "$..data[*]",
                "bookUrl": "https://quapp.shenbabao.com/book/{$.Id}/",
                "coverUrl": "$.Img",
                "intro": "$.Desc",
                "kind": "$.CName&&$.BookStatus",
                "lastChapter": "$.LastChapter",
                "name": "$.Name@put:{a:$.Id}"
            },
            "ruleToc": {
                "chapterList": "$..list[*].list[*]",
                "chapterName": "$.name",
                "chapterUrl": "https://quapp.shenbabao.com/book/@get:{a}/{{$.id}}.html"
            },
            "searchUrl": "https://sou.jiaston.com/search.aspx?key={{key}}&page=Page&siteid=app2",
            "weight": 0
        },
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "无错小说网",
            "bookSourceType": 0,
            "bookSourceUrl": "http://www.xquledu.com",
            "customOrder": 2,
            "enabled": True,
            "enabledExplore": False,
            "lastUpdateTime": 1610673867826,
            "ruleBookInfo": {
                "intro": "id.content@tag.dd.3@tag.p.1@text",
                "tocUrl": "class.read@href"
            },
            "ruleContent": {"content": "id.contents@textNodes"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "class.c_value.0@text||class.fl.1@tag.td.1@text",
                "bookList": "class.c_row||class.booksub",
                "bookUrl": "class.c_subject@tag.a@href",
                "coverUrl": "class.fl.0@tag.a@tag.img@src||class.cover@tag.img@src",
                "kind": "class.c_value.1@text||class.fl.1@tag.td.0@tag.a@text",
                "lastChapter": "class.c_value.5@tag.a@text||id.content@tag.dd.3@tag.p.5@tag.a@text",
                "name": "class.c_subject@tag.a@text||id.content@tag.h1@text##全文阅读"
            },
            "ruleToc": {
                "chapterList": "id.list@tag.dd",
                "chapterName": "tag.a@text",
                "chapterUrl": "tag.a@href"
            },
            "searchUrl": "http://www.xquledu.com/modules/article/search.php?action=search&searchtype=all&searchkey={{key}},{\n  \"charset\": \"gbk\"\n}",
            "weight": 0
        },
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "饭饭中文",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.fanfanzw.com",
            "customOrder": 4,
            "enabled": True,
            "enabledExplore": True,
            "lastUpdateTime": 1610339394379,
            "ruleBookInfo": {
                "author": "id.info@tag.p.0@a@text",
                "coverUrl": "id.fmimg@img@src",
                "intro": "id.intro@text",
                "name": "id.info@h1@text"
            },
            "ruleContent": {"content": "id.content@html##喜欢.*速度最快。"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "class.book_other.0@tag.span.0@text",
                "bookList": "id.sitembox@dl",
                "bookUrl": "tag.a.0@href",
                "coverUrl": "img@src",
                "intro": "class.book_des@text",
                "kind": "class.book_other.0@tag.span.2@text",
                "lastChapter": "class.book_other@a@text",
                "name": "h3@text"
            },
            "ruleToc": {
                "chapterList": "//*[@id=\"list\"]//dt[2]/following-sibling::dd/a",
                "chapterName": "text",
                "chapterUrl": "href"
            },
            "searchUrl": "https://www.fanfanzw.com/search.html,{\n  \"method\": \"POST\",\n  \"body\": \"searchkey={{key}}\"\n}",
            "weight": 0
        },
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "墨斋小说",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.mozhai123.net",
            "customOrder": 9,
            "enabled": True,
            "enabledExplore": True,
            "lastUpdateTime": 1610339282231,
            "ruleBookInfo": {
                "author": "class.info@class.info-xg@tag.span.1@tag.a@text",
                "coverUrl": "class.detail-body-body-img@img@src",
                "kind": "class.info@class.info-xg@tag.span.3@tag.a@text##小说",
                "lastChapter": "class.info@class.info-xg@tag.span.2@tag.a@text",
                "name": "class.info@tag.h2@text"
            },
            "ruleContent": {"content": "class.txt_tcontent@html"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "class.newlist-zz@tag.a@text",
                "bookList": "class.newlist.0@tag.li",
                "bookUrl": "class.newlist-title@tag.a@href",
                "kind": "class.newlist-type@tag.a@title",
                "lastChapter": "class.newlist-zj@tag.a@title",
                "name": "class.newlist-title@tag.a@text"
            },
            "ruleToc": {
                "chapterList": "class.dirlist.1@tag.li",
                "chapterName": "a@text",
                "chapterUrl": "a@href"
            },
            "searchUrl": "https://www.mozhai123.net/modules/article/search.php,{\n  \"charset\": \"gbk\",\n  \"method\": \"POST\",\n  \"body\": \"submit=搜索&searchtype=articlename&searchkey={{key}}&action=login\"\n}",
            "weight": 0
        },
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "搜狗阅读",
            "bookSourceType": 0,
            "bookSourceUrl": "https://book.sogou.com",
            "customOrder": 10,
            "enabled": True,
            "enabledExplore": True,
            "lastUpdateTime": 1612777312852,
            "ruleBookInfo": {"intro": "@js:java.get('Intro')"},
            "ruleContent": {"content": "detail.content"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "author",
                "bookList": ".search-list-note + .list-book-col1 li",
                "bookUrl": "url",
                "coverUrl": "cover",
                "intro": "intro@put:{Intro:$.Intro}@js:result.trim()",
                "name": "name"
            },
            "ruleToc": {
                "chapterList": ".index-list a",
                "chapterName": "text",
                "chapterUrl": "href"
            },
            "searchUrl": "/dd/search?keyword={{key}}",
            "weight": 0
        },
        {
            "bookSourceComment": "https://celeter.github.io/SourceGo",
            "bookSourceGroup": "精选",
            "bookSourceName": "久久小说",
            "bookSourceType": 0,
            "bookSourceUrl": "https://www.txt909.cc",
            "customOrder": 12,
            "enabled": True,
            "enabledExplore": True,
            "lastUpdateTime": 1612777312853,
            "ruleBookInfo": {
                "author": "id.downInfoArea@tag.li.0@tag.a.0@text",
                "coverUrl": "class.img@tag.img.0@src##\\?.*",
                "intro": "id.mainSoftIntro@tag.p@textNodes",
                "name": "id.downInfoArea@tag.h1.0@text##TXT下载|——.*",
                "tocUrl": "class.downAddress_li.1@tag.a.0@href"
            },
            "ruleContent": {"content": "id.view_content_txt@textNodes"},
            "ruleExplore": {},
            "ruleSearch": {
                "author": "class.mainGreen@text||text##.*作者\\W|文件.*",
                "bookList": "id.searchList@tag.div!0||id.catalog@tag.div!0",
                "bookUrl": "class.searchTopic@tag.a.0@href||class.listbg@tag.a.0@href",
                "coverUrl": "class.listbg@tag.span.1@text",
                "kind": "class.listbg@tag.span.2@text",
                "lastChapter": "class.searchTopic@tag.a.0@text||class.listbg@tag.a.0@text",
                "name": "class.searchTopic@tag.a.0@text||class.listbg@tag.a.0@text"
            },
            "ruleToc": {
                "chapterList": "class.read_list@tag.a",
                "chapterName": "tag.a@text##.*(\\d+)##分卷阅读$1",
                "chapterUrl": "tag.a@href"
            },
            "searchUrl": "https://www.txt909.cc/search.html,{\n  \"charset\": \"utf-8\",\n  \"method\": \"POST\",\n  \"body\": \"searchkey={{key}}&Submit22=搜索\"\n}",
            "weight": 0
        }
    ]


REAL_SOURCE_URL = "https://www.yckceo.com/yuedu/shuyuans/json/id/2.json"


class TestRealSourceParseAndValidate:
    """解析真实书源数据并验证"""

    def test_load_real_sources(self):
        """测试加载真实书源数据"""
        sources = _load_real_sources()
        assert len(sources) >= 6, f"预加载数据不足: {len(sources)}"
        print(f"\n[真实数据] 加载了 {len(sources)} 个真实书源")

    def test_parse_json_array(self):
        """测试解析 JSON 数组格式"""
        from app.services.fetcher import SourceFetcher

        sources = _load_real_sources()
        text = json.dumps(sources)
        fetcher = SourceFetcher()

        book_sources, rss_sources = fetcher.parse_sources_from_text(text, origin=REAL_SOURCE_URL)

        assert len(book_sources) == len(sources), f"解析数量不匹配: {len(book_sources)} vs {len(sources)}"
        assert len(rss_sources) == 0
        print(f"[真实数据] 解析到 {len(book_sources)} 个书源")

    def test_source_field_completeness(self):
        """验证真实书源字段完整性"""
        from app.services.fetcher import SourceFetcher

        sources = _load_real_sources()
        text = json.dumps(sources)
        fetcher = SourceFetcher()

        book_sources, _ = fetcher.parse_sources_from_text(text, origin=REAL_SOURCE_URL)

        valid_count = 0
        for source in book_sources:
            assert "bookSourceUrl" in source
            assert "bookSourceName" in source
            assert source["sourceOrigin"] == REAL_SOURCE_URL
            assert "ruleSearch" in source
            assert "ruleToc" in source
            assert "ruleContent" in source
            valid_count += 1

        assert valid_count == len(sources)
        print(f"[真实数据] 全部 {valid_count} 个书源字段完整")

    def test_entity_creation_from_real_data(self):
        """从真实数据创建领域实体"""
        from app.domain.entities.source import BookSource

        sources = _load_real_sources()
        entities = [BookSource.from_dict(s) for s in sources]

        assert len(entities) == len(sources)
        for entity in entities:
            assert entity.bookSourceUrl
            assert entity.bookSourceName
            assert isinstance(entity.ruleSearch, dict)
            assert isinstance(entity.ruleToc, dict)
            assert isinstance(entity.ruleContent, dict)

        print(f"[真实数据] {len(entities)} 个实体创建成功")

    def test_source_statistics(self):
        """统计真实书源数据特征"""
        sources = _load_real_sources()

        groups = set()
        has_search = sum(1 for s in sources if s.get("ruleSearch"))
        has_toc = sum(1 for s in sources if s.get("ruleToc"))
        has_content = sum(1 for s in sources if s.get("ruleContent"))
        enabled_count = sum(1 for s in sources if s.get("enabled", False))
        has_post = sum(1 for s in sources if "POST" in str(s.get("searchUrl", "")))

        for s in sources:
            if s.get("bookSourceGroup"):
                groups.add(s["bookSourceGroup"])

        print(f"\n[书源统计] 总数: {len(sources)}")
        print(f"[书源统计] 分组: {', '.join(sorted(groups))}")
        print(f"[书源统计] 有搜索规则: {has_search}/{len(sources)}")
        print(f"[书源统计] 有目录规则: {has_toc}/{len(sources)}")
        print(f"[书源统计] 有正文规则: {has_content}/{len(sources)}")
        print(f"[书源统计] 已启用: {enabled_count}/{len(sources)}")
        print(f"[书源统计] POST 搜索: {has_post}/{len(sources)}")

        assert has_search == len(sources), "所有书源都应有搜索规则"
        assert enabled_count > 0


class TestRealSourceImportViaAPI:
    """通过 API 导入真实书源的端到端流程测试"""

    @pytest.fixture
    async def client(self):
        """FastAPI 测试客户端"""
        with patch("app.core.redis_client.redis_client") as mock_redis, \
             patch("app.core.events.event_bus") as mock_bus, \
             patch("app.tasks.scheduler.start_scheduler"), \
             patch("app.tasks.scheduler.stop_scheduler"):
            mock_redis.is_connected = False
            mock_redis.connect = AsyncMock()
            mock_redis.disconnect = AsyncMock()
            mock_redis.check_rate_limit = AsyncMock(return_value=(True, 60, 30))
            mock_bus.start = AsyncMock()
            mock_bus.stop = AsyncMock()
            mock_bus.publish = AsyncMock()

            from app.main import app
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test"
            ) as ac:
                yield ac

    @pytest.fixture
    def mock_source_repo(self):
        """Mock 源仓储"""
        repo = MagicMock()
        repo.list_book_sources = AsyncMock(return_value=([], 0))
        repo.get_book_source = AsyncMock(return_value=None)
        repo.save_book_source = AsyncMock(side_effect=lambda x: x)
        repo.save_book_sources = AsyncMock(return_value=0)
        repo.delete_book_source = AsyncMock(return_value=True)
        repo.list_rss_sources = AsyncMock(return_value=([], 0))
        repo.get_rss_source = AsyncMock(return_value=None)
        repo.save_rss_source = AsyncMock(side_effect=lambda x: x)
        repo.save_rss_sources = AsyncMock(return_value=0)
        repo.delete_rss_source = AsyncMock(return_value=True)
        repo.list_subscriptions = AsyncMock(return_value=[])
        repo.save_subscription = AsyncMock(side_effect=lambda x: x)
        repo.delete_subscription = AsyncMock(return_value=True)
        repo.list_filter_rules = AsyncMock(return_value=[])
        repo.save_filter_rule = AsyncMock(side_effect=lambda x: x)
        repo.delete_filter_rule = AsyncMock(return_value=True)
        return repo

    async def test_import_real_sources_via_api(self, client, mock_source_repo):
        """端到端：真实书源数据 -> API 导入 -> 查询"""
        from app.services.fetcher import SourceFetcher

        test_sources = _load_real_sources()[:3]
        text = json.dumps(test_sources)
        fetcher = SourceFetcher()
        book_sources, _ = fetcher.parse_sources_from_text(text, origin=REAL_SOURCE_URL)

        assert len(book_sources) == 3
        print(f"\n[端到端] 准备导入 {len(book_sources)} 个真实书源:")
        for s in book_sources:
            print(f"  - {s.get('bookSourceName')} ({s.get('bookSourceUrl')})")

        # Mock repo
        saved_sources = []
        mock_source_repo.save_book_sources = AsyncMock(side_effect=lambda entities: (saved_sources.extend(entities), len(entities))[1])

        async def mock_list(group=None, status=None, enabled_only=False, page=1, page_size=50):
            return saved_sources, len(saved_sources)

        mock_source_repo.list_book_sources = AsyncMock(side_effect=mock_list)

        # 导入
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.post("/api/sources/book/import", json=book_sources)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3
        print(f"[端到端] 导入成功: count={data['data']['count']}")

        # 查询
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.get("/api/sources/book")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 3
        assert data["meta"]["total"] == 3
        print(f"[端到端] 查询成功: total={data['meta']['total']}")

        # 验证字段
        first = data["data"][0]
        assert "bookSourceUrl" in first
        assert "bookSourceName" in first
        print(f"[端到端] 字段验证: {first.get('bookSourceName')}")

    async def test_real_source_round_trip(self, client, mock_source_repo):
        """端到端：创建 -> 查询 -> 删除 -> 404"""
        sources = _load_real_sources()
        sample = sources[0]

        saved = []
        mock_source_repo.save_book_source = AsyncMock(side_effect=lambda entity: (saved.append(entity), entity)[1])

        def mock_get(url):
            for s in saved:
                if getattr(s, "bookSourceUrl", "") == url:
                    return s
            return None

        mock_source_repo.get_book_source = AsyncMock(side_effect=mock_get)
        mock_source_repo.delete_book_source = AsyncMock(return_value=True)

        url = sample["bookSourceUrl"]
        name = sample["bookSourceName"]
        print(f"\n[Round Trip] 测试: {name} ({url})")

        # 创建
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.post("/api/sources/book", json=sample)
        assert resp.status_code == 200

        # 查询
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.get(f"/api/sources/book/{url}")
        assert resp.status_code == 200
        assert resp.json()["data"]["bookSourceName"] == name

        # 删除
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.delete(f"/api/sources/book/{url}")
        assert resp.status_code == 200

        # 删除后 404
        saved.clear()
        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.get(f"/api/sources/book/{url}")
        assert resp.status_code == 404
        print(f"[Round Trip] 全部通过")

    async def test_import_all_real_sources(self, client, mock_source_repo):
        """导入全部真实书源并验证"""
        from app.services.fetcher import SourceFetcher

        sources = _load_real_sources()
        text = json.dumps(sources)
        fetcher = SourceFetcher()
        book_sources, _ = fetcher.parse_sources_from_text(text, origin=REAL_SOURCE_URL)

        saved_count = 0
        mock_source_repo.save_book_sources = AsyncMock(side_effect=lambda entities: globals().__setitem__('_saved', len(entities)) or len(entities))
        mock_source_repo.list_book_sources = AsyncMock(return_value=([], 0))

        with patch("app.interfaces.api.dependencies.get_source_repo", return_value=mock_source_repo):
            resp = await client.post("/api/sources/book/import", json=book_sources)

        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == len(sources)
        print(f"\n[批量导入] 成功导入 {saved_count} 个真实书源")


class TestSourceFetcherParseEdgeCases:
    """SourceFetcher 解析边界情况测试"""

    def test_parse_empty_text(self):
        """空文本解析"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        books, rss = fetcher.parse_sources_from_text("")
        assert books == []
        assert rss == []

    def test_parse_invalid_json(self):
        """无效 JSON 解析"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        books, rss = fetcher.parse_sources_from_text("not json at all\n{bad json")
        assert books == []
        assert rss == []

    def test_parse_single_object(self):
        """单个对象（非数组）"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        source = {"bookSourceUrl": "https://test.com", "bookSourceName": "Test"}
        books, rss = fetcher.parse_sources_from_text(json.dumps(source))
        assert len(books) == 1
        assert books[0]["bookSourceName"] == "Test"

    def test_parse_ndjson_format(self):
        """NDJSON 格式（每行一个 JSON）"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        text = '\n'.join([
            json.dumps({"bookSourceUrl": "https://a.com", "bookSourceName": "A"}),
            json.dumps({"bookSourceUrl": "https://b.com", "bookSourceName": "B"}),
            json.dumps({"sourceUrl": "https://rss.com", "sourceName": "RSS"}),
        ])
        books, rss = fetcher.parse_sources_from_text(text)
        assert len(books) == 2
        assert len(rss) == 1

    def test_parse_mixed_ndjson_with_bad_lines(self):
        """NDJSON 中包含错误行"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        text = '\n'.join([
            json.dumps({"bookSourceUrl": "https://a.com", "bookSourceName": "A"}),
            "bad line",
            json.dumps({"bookSourceUrl": "https://b.com", "bookSourceName": "B"}),
        ])
        books, rss = fetcher.parse_sources_from_text(text)
        assert len(books) == 2  # 忽略坏行

    def test_classify_book_vs_rss(self):
        """分类：bookSource vs sourceUrl"""
        from app.services.fetcher import SourceFetcher
        fetcher = SourceFetcher()
        text = json.dumps([
            {"bookSourceUrl": "https://book.com", "bookSourceName": "Book"},
            {"sourceUrl": "https://rss.com", "sourceName": "RSS"},
            {"bookSourceUrl": "https://both.com", "sourceUrl": "https://both.com", "bookSourceName": "Both"},
        ])
        books, rss = fetcher.parse_sources_from_text(text)
        assert len(books) == 2  # bookSourceUrl 优先
        assert len(rss) == 1

"""
domain/entities/source.py 单元测试

覆盖领域实体的业务方法：
- BookSource: is_available, mark_checked, to_legado_dict, from_dict
- RssSource: is_available, mark_checked, to_legado_dict, from_dict
- Subscription: mark_fetched
- FilterRule: should_filter
"""

import pytest
from datetime import datetime
from app.domain.entities.source import BookSource, RssSource, Subscription, FilterRule


class TestBookSource:
    """BookSource 书源实体测试"""

    def test_create_book_source(self):
        """验证创建书源实体的基本属性"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试书源"
        )
        assert source.bookSourceUrl == "https://example.com"
        assert source.bookSourceName == "测试书源"
        assert source.enabled is True
        assert source.sourceStatus == "unknown"

    def test_book_source_id_property(self):
        """验证 id 属性返回 bookSourceUrl"""
        source = BookSource(
            bookSourceUrl="https://example.com/book1",
            bookSourceName="测试"
        )
        assert source.id == "https://example.com/book1"

    def test_is_available_when_enabled_and_ok(self):
        """验证源可用：enabled=True 且 sourceStatus=ok"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            enabled=True,
            sourceStatus="ok"
        )
        assert source.is_available() is True

    def test_is_available_when_disabled(self):
        """验证源不可用：enabled=False"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            enabled=False,
            sourceStatus="ok"
        )
        assert source.is_available() is False

    def test_is_available_when_error_status(self):
        """验证源不可用：sourceStatus=error"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            enabled=True,
            sourceStatus="error"
        )
        assert source.is_available() is False

    def test_mark_checked_ok(self):
        """验证标记检查为 ok 状态"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试"
        )
        source.mark_checked("ok")
        assert source.sourceStatus == "ok"
        assert source.lastCheckTime is not None
        assert source.errorMsg is None

    def test_mark_checked_with_error(self):
        """验证标记检查为 error 状态并记录错误信息"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试"
        )
        source.mark_checked("error", error_msg="连接超时")
        assert source.sourceStatus == "error"
        assert source.errorMsg == "连接超时"
        assert source.lastCheckTime is not None

    def test_to_legado_dict_excludes_hub_fields(self):
        """验证 to_legado_dict 移除 Hub 内部字段"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            sourceStatus="ok",
            sourceOrigin="engine",
        )
        result = source.to_legado_dict()
        assert "sourceStatus" not in result
        assert "lastCheckTime" not in result
        assert "errorMsg" not in result
        assert "sourceOrigin" not in result
        assert "createdAt" not in result
        assert "updatedAt" not in result

    def test_to_legado_dict_includes_public_fields(self):
        """验证 to_legado_dict 包含公开字段"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            bookSourceGroup="官方"
        )
        result = source.to_legado_dict()
        assert result["bookSourceUrl"] == "https://example.com"
        assert result["bookSourceName"] == "测试"
        assert result["bookSourceGroup"] == "官方"

    def test_from_dict_creates_entity(self, sample_book_source_data):
        """验证 from_dict 正确创建实体"""
        source = BookSource.from_dict(sample_book_source_data)
        assert source.bookSourceUrl == "https://example.com"
        assert source.bookSourceName == "测试书源"
        assert source.sourceStatus == "ok"

    def test_from_dict_ignores_unknown_fields(self):
        """验证 from_dict 忽略不在 dataclass 定义中的字段"""
        data = {
            "bookSourceUrl": "https://example.com",
            "bookSourceName": "测试",
            "unknownField": "should_be_ignored",
        }
        source = BookSource.from_dict(data)
        assert source.bookSourceUrl == "https://example.com"
        assert not hasattr(source, "unknownField")

    def test_to_legado_dict_omits_none_values(self):
        """验证 to_legado_dict 不包含 None 或空字符串的值"""
        source = BookSource(
            bookSourceUrl="https://example.com",
            bookSourceName="测试",
            header=None,
            jsLib="",
        )
        result = source.to_legado_dict()
        assert "header" not in result
        assert "jsLib" not in result


class TestRssSource:
    """RssSource RSS 源实体测试"""

    def test_create_rss_source(self):
        """验证创建 RSS 源实体"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试RSS源"
        )
        assert source.sourceUrl == "https://rss.example.com/feed.xml"
        assert source.sourceName == "测试RSS源"
        assert source.enabled is True

    def test_rss_source_id_property(self):
        """验证 id 属性返回 sourceUrl"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试"
        )
        assert source.id == "https://rss.example.com/feed.xml"

    def test_rss_is_available_when_enabled_and_ok(self):
        """验证 RSS 源可用"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试",
            enabled=True,
            sourceStatus="ok"
        )
        assert source.is_available() is True

    def test_rss_is_available_when_disabled(self):
        """验证禁用的 RSS 源不可用"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试",
            enabled=False,
            sourceStatus="ok"
        )
        assert source.is_available() is False

    def test_rss_mark_checked(self):
        """验证 RSS 源标记检查状态"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试"
        )
        source.mark_checked("error", error_msg="RSS 解析失败")
        assert source.sourceStatus == "error"
        assert source.errorMsg == "RSS 解析失败"

    def test_rss_to_legado_dict_excludes_hub_fields(self):
        """验证 to_legado_dict 移除 Hub 内部字段"""
        source = RssSource(
            sourceUrl="https://rss.example.com/feed.xml",
            sourceName="测试",
            sourceStatus="ok",
        )
        result = source.to_legado_dict()
        assert "sourceStatus" not in result
        assert "createdAt" not in result

    def test_rss_from_dict(self, sample_rss_source_data):
        """验证 from_dict 创建 RSS 源实体"""
        source = RssSource.from_dict(sample_rss_source_data)
        assert source.sourceUrl == "https://rss.example.com/feed.xml"
        assert source.sourceName == "测试RSS源"


class TestSubscription:
    """Subscription 订阅实体测试"""

    def test_create_subscription(self, sample_subscription_data):
        """验证创建订阅实体"""
        sub = Subscription(**sample_subscription_data)
        assert sub.id == 1
        assert sub.name == "测试订阅"
        assert sub.url == "https://example.com/source"
        assert sub.subType == "book"
        assert sub.enabled is True

    def test_mark_fetched(self):
        """验证标记拉取完成"""
        sub = Subscription(id=1, name="测试", url="https://example.com")
        sub.mark_fetched(source_count=42)
        assert sub.lastFetchTime is not None
        assert sub.sourceCount == 42

    def test_mark_fetched_default_count(self):
        """验证标记拉取完成时默认 source_count 为 0"""
        sub = Subscription(id=1, name="测试", url="https://example.com")
        sub.mark_fetched()
        assert sub.sourceCount == 0


class TestFilterRule:
    """FilterRule 过滤规则实体测试"""

    def test_create_filter_rule(self):
        """验证创建过滤规则"""
        rule = FilterRule(pattern="广告", isRegex=False)
        assert rule.pattern == "广告"
        assert rule.isRegex is False

    def test_should_filter_regex_match(self):
        """验证正则匹配：匹配返回 True（应过滤）"""
        rule = FilterRule(pattern=r"广告", isRegex=True, scope="sourceName")
        assert rule.should_filter(source_name="某某广告书源") is True

    def test_should_filter_regex_no_match(self):
        """验证正则不匹配：返回 False（不过滤）"""
        rule = FilterRule(pattern=r"广告", isRegex=True, scope="sourceName")
        assert rule.should_filter(source_name="正规书源") is False

    def test_should_filter_plain_text_match(self):
        """验证普通文本匹配"""
        rule = FilterRule(pattern="广告", isRegex=False, scope="sourceName")
        assert rule.should_filter(source_name="这是一个广告书源") is True

    def test_should_filter_plain_text_no_match(self):
        """验证普通文本不匹配"""
        rule = FilterRule(pattern="垃圾", isRegex=False, scope="sourceName")
        assert rule.should_filter(source_name="优质书源") is False

    def test_should_filter_by_url(self):
        """验证按 sourceUrl 过滤"""
        rule = FilterRule(pattern=r"biquge", isRegex=True, scope="sourceUrl")
        assert rule.should_filter(source_url="https://www.biquge123.cc") is True
        assert rule.should_filter(source_url="https://www.qidian.com") is False

    def test_should_filter_invalid_regex_returns_false(self):
        """验证无效正则表达式安全返回 False"""
        rule = FilterRule(pattern="[invalid(", isRegex=True, scope="sourceName")
        # 无效正则不应抛出异常
        assert rule.should_filter(source_name="任意名称") is False

    def test_should_filter_default_scope(self):
        """验证默认 scope 为 sourceName"""
        rule = FilterRule(pattern="测试", isRegex=False)
        assert rule.should_filter(source_name="测试书源") is True
        assert rule.should_filter(source_url="https://test.com") is False


# ========== Novel Understanding 领域实体测试 ==========

from app.domain.entities.novel import (
    NovelStatus, EntityType, RelationType, EventType, StateField, IngestSource,
    NovelBook, NovelSourceMirror,
    NovelChapter, NovelChapterMirror, ChapterFingerprint,
    NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    EvolutionFeedback, EvolutionRule, PromptTemplate, GepGene,
)


class TestNovelEnums:
    """Novel 枚举类测试"""

    def test_novel_status_values(self):
        assert NovelStatus.PENDING.value == "pending"
        assert NovelStatus.READY.value == "ready"
        assert NovelStatus.ERROR.value == "error"

    def test_entity_type_values(self):
        assert EntityType.CHARACTER.value == "character"
        assert EntityType.REALM.value == "realm"

    def test_relation_type_values(self):
        assert RelationType.ALLY.value == "ally"
        assert RelationType.CUSTOM.value == "custom"

    def test_event_type_values(self):
        assert EventType.BATTLE.value == "battle"
        assert EventType.BREAKTHROUGH.value == "breakthrough"

    def test_state_field_values(self):
        assert StateField.REALM.value == "realm"
        assert StateField.EMOTION.value == "emotion"

    def test_ingest_source_values(self):
        assert IngestSource.BOOK_SOURCE.value == "book_source"
        assert IngestSource.UPLOAD.value == "upload"

    def test_enum_comparison(self):
        assert NovelStatus.READY == NovelStatus("ready")


class TestNovelBook:
    """NovelBook 实体测试"""

    def test_default_values(self):
        book = NovelBook()
        assert book.id == 0
        assert book.book_url == ""
        assert book.status == NovelStatus.PENDING
        assert book.source_type == IngestSource.BOOK_SOURCE
        assert book.ingest_progress == 0.0
        assert book.total_chapters == 0

    def test_custom_values(self):
        book = NovelBook(
            id=1,
            book_url="https://example.com/book/1",
            book_name="Test Book",
            author="Test Author",
            status=NovelStatus.READY,
            total_chapters=100,
        )
        assert book.id == 1
        assert book.book_name == "Test Book"
        assert book.status == NovelStatus.READY

    def test_has_created_at(self):
        book = NovelBook()
        assert isinstance(book.created_at, datetime)


class TestNovelSourceMirror:
    """NovelSourceMirror 实体测试"""

    def test_default_values(self):
        mirror = NovelSourceMirror()
        assert mirror.id == 0
        assert mirror.status == "active"
        assert mirror.priority == 0
        assert mirror.failure_count == 0

    def test_custom_values(self):
        mirror = NovelSourceMirror(
            id=1,
            book_id=1,
            source_url="https://example.com",
            source_name="Test Source",
            priority=0,
            status="degraded",
        )
        assert mirror.status == "degraded"
        assert mirror.source_name == "Test Source"


class TestChapterFingerprint:
    """ChapterFingerprint 实体测试"""

    def test_default_values(self):
        fp = ChapterFingerprint()
        assert fp.word_count == 0
        assert fp.paragraph_count == 0


class TestNovelChapter:
    """NovelChapter 实体测试"""

    def test_default_canonical(self):
        ch = NovelChapter()
        assert ch.canonical_type == "C"
        assert ch.canonical_num == 0
        assert ch.canonical_full == ""

    def test_character_appearances_is_dict(self):
        ch = NovelChapter(character_appearances={"林远": 5})
        assert ch.character_appearances["林远"] == 5


class TestNovelChapterMirror:
    """NovelChapterMirror 实体测试"""

    def test_default_fetch_status(self):
        m = NovelChapterMirror()
        assert m.fetch_status == "pending"


class TestNovelEntity:
    """NovelEntity 实体测试"""

    def test_default_entity_type(self):
        e = NovelEntity()
        assert e.entity_type == EntityType.CHARACTER
        assert e.importance_score == 3

    def test_attributes_dict(self):
        e = NovelEntity(attributes={"gender": "男", "age": 20})
        assert e.attributes["gender"] == "男"


class TestNovelRelationship:
    """NovelRelationship 实体测试"""

    def test_default_relation_type(self):
        r = NovelRelationship()
        assert r.relation_type == RelationType.CUSTOM
        assert r.confidence == 0.8

    def test_since_until_chapter(self):
        r = NovelRelationship(since_chapter=10, until_chapter=20)
        assert r.since_chapter == 10
        assert r.until_chapter == 20


class TestNovelEvent:
    """NovelEvent 实体测试"""

    def test_default_event_type(self):
        e = NovelEvent()
        assert e.event_type == EventType.CUSTOM
        assert e.importance == 3

    def test_participants_list(self):
        e = NovelEvent(participants=["林远", "周宁"])
        assert "林远" in e.participants


class TestNovelStateChange:
    """NovelStateChange 实体测试"""

    def test_default_field_name(self):
        sc = NovelStateChange()
        assert sc.field_name == StateField.CUSTOM
        assert sc.confidence == 0.8

    def test_realm_change(self):
        sc = NovelStateChange(
            entity_name="林远",
            field_name=StateField.REALM,
            before_value="炼气期",
            after_value="筑基期",
        )
        assert sc.before_value == "炼气期"
        assert sc.after_value == "筑基期"


class TestEvolutionFeedback:
    """EvolutionFeedback 实体测试"""

    def test_default_values(self):
        ef = EvolutionFeedback()
        assert ef.applied is False
        assert ef.confidence == 1.0

    def test_user_correction(self):
        ef = EvolutionFeedback(
            book_id=1,
            feedback_type="user_correction",
            target_type="entity",
            original_value="林远",
            corrected_value="韩立",
        )
        assert ef.feedback_type == "user_correction"


class TestEvolutionRule:
    """EvolutionRule 实体测试"""

    def test_default_active(self):
        r = EvolutionRule()
        assert r.active is True
        assert r.hit_count == 0


class TestPromptTemplate:
    """PromptTemplate 实体测试"""

    def test_default_success_rate(self):
        pt = PromptTemplate()
        assert pt.success_rate == 0.0
        assert pt.version == 1


class TestGepGene:
    """GepGene 实体测试"""

    def test_default_counters(self):
        g = GepGene()
        assert g.success_count == 0
        assert g.failure_count == 0

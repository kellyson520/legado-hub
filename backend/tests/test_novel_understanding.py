"""
NovelUnderstanding 核心引擎测试

覆盖：
- EntityExtractor: Prompt构建 + LLM响应解析
- HierarchicalSummarizer: 摘要结构 + Prompt构建 + Token估算
- StateTracker: 状态追踪 + 突破检测 + 摘要生成
"""

import pytest

from app.services.novel_understanding.entity_extractor import EntityExtractor
from app.services.novel_understanding.summarizer import HierarchicalSummarizer, HierarchicalSummary
from app.services.novel_understanding.state_tracker import StateTracker
from app.domain.entities.novel import (
    NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    EntityType, RelationType, EventType, StateField,
)


class TestEntityExtractor:
    """实体提取器测试"""

    def test_build_prompt(self):
        prompt = EntityExtractor.build_prompt("这是测试章节内容")
        assert "小说分析助手" in prompt
        assert "测试章节内容" in prompt
        assert "JSON 格式" in prompt

    def test_build_prompt_with_known_entities(self):
        prompt = EntityExtractor.build_prompt("内容", known_entities=["林远", "周宁"])
        assert "林远" in prompt
        assert "周宁" in prompt

    def test_extract_json_direct(self):
        text = '{"characters": [{"name": "林远"}]}'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        assert len(result["entities"]) == 1
        assert result["entities"][0].name == "林远"
        assert result["entities"][0].entity_type == EntityType.CHARACTER

    def test_extract_json_with_code_block(self):
        text = '```json\n{"characters": [{"name": "韩立", "aliases": ["韩跑跑"]}]}\n```'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        assert len(result["entities"]) == 1
        assert result["entities"][0].name == "韩立"

    def test_extract_all_types(self):
        text = '''{"characters": [{"name": "A"}], "locations": [{"name": "B"}],
                   "items": [{"name": "C"}], "factions": [{"name": "D"}],
                   "realms": [{"name": "E"}], "concepts": [{"name": "F"}]}'''
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        types = [e.entity_type for e in result["entities"]]
        assert EntityType.CHARACTER in types
        assert EntityType.LOCATION in types
        assert EntityType.ITEM in types
        assert EntityType.FACTION in types
        assert EntityType.REALM in types
        assert EntityType.CONCEPT in types

    def test_extract_relationships(self):
        text = '{"relationships": [{"source": "A", "target": "B", "relation_type": "ally"}]}'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        assert len(result["relationships"]) == 1
        assert result["relationships"][0].relation_type == RelationType.ALLY

    def test_extract_events(self):
        text = '{"events": [{"event_type": "battle", "description": "大战", "participants": ["A"], "importance": 5}]}'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        assert len(result["events"]) == 1
        assert result["events"][0].event_type == EventType.BATTLE
        assert result["events"][0].importance == 5

    def test_extract_state_changes(self):
        text = '{"state_changes": [{"entity_name": "A", "field_name": "realm", "before_value": "炼气", "after_value": "筑基"}]}'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_num=1)
        assert len(result["state_changes"]) == 1
        assert result["state_changes"][0].field_name == StateField.REALM

    def test_extract_invalid_json(self):
        result = EntityExtractor.parse_llm_response("not json", book_id=1)
        assert result["entities"] == []

    def test_chapter_num_passed_correctly(self):
        text = '{"characters": [{"name": "X"}]}'
        result = EntityExtractor.parse_llm_response(text, book_id=1, chapter_id=5, chapter_num=10)
        assert result["entities"][0].first_appearance_ch == 10


class TestHierarchicalSummarizer:
    """分层摘要生成器测试"""

    def test_build_chapter_summary_prompt(self):
        prompt = HierarchicalSummarizer.build_chapter_summary_prompt("章节内容")
        assert "摘要" in prompt
        assert "章节内容" in prompt

    def test_parse_chapter_summary(self):
        text = '{"summary": "这是摘要", "key_events": ["事件1"], "characters": ["A"]}'
        result = HierarchicalSummarizer.parse_chapter_summary(text)
        assert result["summary"] == "这是摘要"
        assert result["key_events"] == ["事件1"]

    def test_parse_chapter_summary_code_block(self):
        text = '```json\n{"summary": "摘要", "key_events": [], "characters": []}\n```'
        result = HierarchicalSummarizer.parse_chapter_summary(text)
        assert result["summary"] == "摘要"

    def test_estimate_tokens_chinese(self):
        tokens = HierarchicalSummarizer.estimate_tokens("中文测试")
        assert tokens == 6  # 4 中文字 * 1.5 = 6

    def test_estimate_tokens_mixed(self):
        tokens = HierarchicalSummarizer.estimate_tokens("中文abc")
        assert tokens == 3  # 2*1.5 + 3*0.25 = 3.75 -> int(3.75) = 3

    def test_build_entity_cards(self):
        entities = [
            NovelEntity(name="林远", entity_type=EntityType.CHARACTER, importance_score=5, description="主角"),
            NovelEntity(name="周宁", entity_type=EntityType.CHARACTER, importance_score=3, description="配角"),
        ]
        cards = HierarchicalSummarizer.build_entity_cards(entities)
        assert len(cards) == 2
        assert cards[0]["name"] == "林远"  # importance_score 高排前

    def test_build_global_summary_prompt(self):
        entities = [NovelEntity(name="林远", entity_type=EntityType.CHARACTER, description="主角")]
        events = [NovelEvent(chapter_num=1, description="开篇")]
        prompt = HierarchicalSummarizer.build_global_summary_prompt(entities, events)
        assert "林远" in prompt
        assert "开篇" in prompt

    def test_hierarchical_summary_to_prompt_context(self):
        summary = HierarchicalSummary(
            book_id=1,
            global_summary="全书概要",
            entity_cards=[{"name": "A", "description": "desc"}],
            chapter_summaries=[{"chapter_num": 1, "summary": "第一章"}],
        )
        context = summary.to_prompt_context()
        assert "全书概要" in context
        assert "A" in context
        assert "第一章" in context

    def test_hierarchical_summary_priority_filter(self):
        summary = HierarchicalSummary(
            book_id=1,
            global_summary="全局",
            entity_cards=[{"name": "A"}],
        )
        ctx_p3 = summary.to_prompt_context(priority="p3")
        assert "全局" in ctx_p3
        assert "A" not in ctx_p3

        ctx_p0 = summary.to_prompt_context(priority="p0")
        assert "全局" not in ctx_p0
        assert "A" in ctx_p0


class TestStateTracker:
    """状态变迁追踪器测试"""

    def test_track_entity_states(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, before_value="炼气", after_value="筑基"),
            NovelStateChange(entity_name="林远", chapter_num=5, field_name=StateField.REALM, before_value="筑基", after_value="金丹"),
            NovelStateChange(entity_name="周宁", chapter_num=2, field_name=StateField.REALM, before_value="炼气", after_value="筑基"),
        ]
        result = StateTracker.track_entity_states(changes)
        assert len(result["林远"]) == 2
        assert len(result["周宁"]) == 1

    def test_track_entity_states_filtered(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, before_value="A", after_value="B"),
            NovelStateChange(entity_name="周宁", chapter_num=2, field_name=StateField.REALM, before_value="C", after_value="D"),
        ]
        result = StateTracker.track_entity_states(changes, entity_name="林远")
        assert "林远" in result
        assert "周宁" not in result

    def test_get_current_state(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, after_value="筑基"),
            NovelStateChange(entity_name="林远", chapter_num=5, field_name=StateField.REALM, after_value="金丹"),
            NovelStateChange(entity_name="林远", chapter_num=3, field_name=StateField.EMOTION, after_value="愤怒"),
        ]
        current = StateTracker.get_current_state(changes, "林远")
        assert current["realm"] == "金丹"
        assert current["emotion"] == "愤怒"

    def test_get_current_state_filtered(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, after_value="筑基"),
            NovelStateChange(entity_name="林远", chapter_num=3, field_name=StateField.EMOTION, after_value="愤怒"),
        ]
        current = StateTracker.get_current_state(changes, "林远", field_name=StateField.REALM)
        assert current["realm"] == "筑基"
        assert "emotion" not in current

    def test_detect_major_breakthroughs(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, before_value="炼气", after_value="筑基"),
            NovelStateChange(entity_name="林远", chapter_num=5, field_name=StateField.ABILITY, before_value="无", after_value="火球术"),
            NovelStateChange(entity_name="林远", chapter_num=3, field_name=StateField.EMOTION, before_value="平静", after_value="愤怒"),
        ]
        breakthroughs = StateTracker.detect_major_breakthroughs(changes)
        assert len(breakthroughs) == 2
        assert breakthroughs[0]["type"] == "realm_breakthrough"
        assert breakthroughs[1]["type"] == "ability_awakening"

    def test_generate_state_summary(self):
        changes = [
            NovelStateChange(entity_name="林远", chapter_num=1, field_name=StateField.REALM, before_value="炼气", after_value="筑基"),
        ]
        summary = StateTracker.generate_state_summary(changes, "林远")
        assert "林远" in summary
        assert "炼气" in summary
        assert "筑基" in summary

    def test_generate_state_summary_empty(self):
        summary = StateTracker.generate_state_summary([], "不存在")
        assert "暂无状态记录" in summary

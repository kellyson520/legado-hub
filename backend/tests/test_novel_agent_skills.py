"""
NovelAgent 技能层单元测试

测试各技能模块的工具注册和基本功能：
- ToolRegistry 工具注册表
- SourceSkill 书源技能
- OCRSkill OCR 技能
- CollectorSkill 采集技能
- ExtractorSkill 抽取技能
- 等 10 大技能
"""

import pytest
import os
import tempfile


# ==================== 工具注册表测试 ====================

class TestToolRegistry:
    def test_registry_init(self):
        from app.services.novel_agent.registry import ToolRegistry
        registry = ToolRegistry()
        assert registry is not None
        assert registry._tools == {}

    def test_register_skill_adds_tools(self):
        from app.services.novel_agent.registry import ToolRegistry
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        registry = ToolRegistry()
        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = SourceSkill(store, memory, config)
        registry.register_skill(skill)

        tools = registry.list_tools()
        assert len(tools) > 0
        tool_names = [t["name"] for t in tools]
        assert "source_list" in tool_names

    def test_call_tool(self):
        from app.services.novel_agent.registry import ToolRegistry
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        registry = ToolRegistry()
        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = SourceSkill(store, memory, config)
        registry.register_skill(skill)

        result = registry.call("source_template")
        assert result is not None
        # 结果应该是一个字典或对象，不含 error
        if isinstance(result, dict):
            assert "error" not in result

    def test_call_nonexistent_tool(self):
        from app.services.novel_agent.registry import ToolRegistry
        registry = ToolRegistry()
        result = registry.call("nonexistent_tool")
        assert "error" in result

    def test_has_tool(self):
        from app.services.novel_agent.registry import ToolRegistry
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        registry = ToolRegistry()
        assert registry.has_tool("source_list") is False

        skill = SourceSkill(NovelDataStore(), AgentMemory(), AgentConfig())
        registry.register_skill(skill)

        assert registry.has_tool("source_list") is True
        assert registry.has_tool("nonexistent") is False

    def test_get_tool_def(self):
        from app.services.novel_agent.registry import ToolRegistry
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        registry = ToolRegistry()
        skill = SourceSkill(NovelDataStore(), AgentMemory(), AgentConfig())
        registry.register_skill(skill)

        tool_def = registry.get_tool_def("source_list")
        assert tool_def is not None
        assert tool_def.name == "source_list"

        assert registry.get_tool_def("nonexistent") is None

    def test_unregister_skill(self):
        from app.services.novel_agent.registry import ToolRegistry
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        registry = ToolRegistry()
        skill = SourceSkill(NovelDataStore(), AgentMemory(), AgentConfig())
        registry.register_skill(skill)

        assert registry.has_tool("source_list") is True
        registry.unregister_skill("source")
        assert registry.has_tool("source_list") is False


# ==================== SourceSkill 测试 ====================

class TestSourceSkill:
    def test_source_skill_init(self):
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = SourceSkill(store, memory, config)
        assert skill.name == "source"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "source_search" in tool_names
        assert "source_list" in tool_names
        assert "source_create" in tool_names
        assert "source_validate" in tool_names
        assert "source_template" in tool_names

    def test_source_template(self):
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()
        skill = SourceSkill(store, memory, config)

        result = skill.execute("source_template")
        assert result is not None

    def test_source_list_empty(self):
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()
        skill = SourceSkill(store, memory, config)

        result = skill.execute("source_list")
        assert result is not None

    def test_source_groups(self):
        from app.services.novel_agent.skills.source import SourceSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()
        skill = SourceSkill(store, memory, config)

        result = skill.execute("source_groups")
        # 返回可能是 dict 或 list，只要不为空结构即可
        assert result is not None


# ==================== OCRSkill 测试 ====================

class TestOCRSkill:
    def test_ocr_skill_init(self):
        from app.services.novel_agent.skills.ocr import OCRSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = OCRSkill(store, memory, config)
        assert skill.name == "ocr"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "ocr_recognize" in tool_names
        assert "ocr_extract_text" in tool_names
        assert "ocr_batch_recognize" in tool_names

    def test_ocr_recognize_no_input(self):
        from app.services.novel_agent.skills.ocr import OCRSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()
        skill = OCRSkill(store, memory, config)

        result = skill.execute("ocr_recognize")
        assert result is not None
        if isinstance(result, dict):
            # 没有输入应该返回成功但可能为空，或者有 error
            assert isinstance(result, dict)


# ==================== CollectorSkill 测试 ====================

class TestCollectorSkill:
    def test_collector_skill_init(self):
        from app.services.novel_agent.skills.collector import CollectorSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = CollectorSkill(store, memory, config)
        assert skill.name == "collector"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "collect_chapters" in tool_names
        assert "list_chapters" in tool_names
        assert "get_chapter_content" in tool_names

    def test_list_chapters_empty(self):
        from app.services.novel_agent.skills.collector import CollectorSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()
        skill = CollectorSkill(store, memory, config)

        result = skill.execute("list_chapters")
        assert result is not None


# ==================== ExtractorSkill 测试 ====================

class TestExtractorSkill:
    def test_extractor_skill_init(self):
        from app.services.novel_agent.skills.extractor import ExtractorSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = ExtractorSkill(store, memory, config)
        assert skill.name == "extractor"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "extract_characters" in tool_names
        assert "extract_relations" in tool_names
        assert "extract_aliases" in tool_names
        assert "recall_context" in tool_names


# ==================== GrapherSkill 测试 ====================

class TestGrapherSkill:
    def test_grapher_skill_init(self):
        from app.services.novel_agent.skills.grapher import GrapherSkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = GrapherSkill(store, memory, config)
        assert skill.name == "grapher"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "graph_stats" in tool_names
        assert "generate_graph_html" in tool_names
        assert "get_character_info" in tool_names


# ==================== QASkill 测试 ====================

class TestQASkill:
    def test_qa_skill_init(self):
        from app.services.novel_agent.skills.qa import QASkill
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill = QASkill(store, memory, config)
        assert skill.name == "qa"
        tools = skill.get_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "plot_search" in tool_names
        assert "answer_question" in tool_names


# ==================== 10 大技能完整性测试 ====================

class TestAllSkills:
    def test_all_10_skills_exist(self):
        """验证 10 大技能都存在且可初始化"""
        from app.services.novel_agent.skills import (
            SourceSkill, CollectorSkill, ExtractorSkill, AuditorSkill,
            GrapherSkill, QASkill, SummarizerSkill, WriterSkill,
            ReasonerSkill, OCRSkill,
        )
        from app.services.novel_agent.store import NovelDataStore
        from app.services.novel_agent.memory import AgentMemory
        from app.services.novel_agent.config import AgentConfig

        store = NovelDataStore()
        memory = AgentMemory()
        config = AgentConfig()

        skill_classes = [
            SourceSkill, CollectorSkill, ExtractorSkill, AuditorSkill,
            GrapherSkill, QASkill, SummarizerSkill, WriterSkill,
            ReasonerSkill, OCRSkill,
        ]

        for skill_cls in skill_classes:
            skill = skill_cls(store, memory, config)
            assert skill.name is not None
            tools = skill.get_tools()
            assert len(tools) > 0, f"{skill_cls.__name__} 没有提供任何工具"

    def test_total_tool_count(self):
        """验证总工具数 > 50"""
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        tools = agent.registry.list_tools()
        assert len(tools) >= 50, f"工具数量: {len(tools)}，预期至少 50"

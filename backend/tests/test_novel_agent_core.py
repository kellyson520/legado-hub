"""
NovelAgent 核心单元测试

测试：
- AgentConfig 配置
- NovelDataStore 数据存储
- AgentMemory 记忆系统
- NovelAgent 规划器/执行器
- 各技能工具的基本可用性
"""

import pytest
import os
import tempfile


# ==================== AgentConfig 测试 ====================

class TestAgentConfig:
    def test_config_defaults(self):
        from app.services.novel_agent.config import AgentConfig
        config = AgentConfig()
        assert config.get("agent.name") is not None
        assert config.get("agent.version") is not None
        assert config.skill_enabled("collector") is True
        assert config.skill_enabled("nonexistent_skill_xyz") is False

    def test_config_override(self):
        from app.services.novel_agent.config import AgentConfig
        config = AgentConfig(config_dict={
            "agent": {"name": "TestAgent"},
            "skills": {"collector": False},
        })
        assert config.get("agent.name") == "TestAgent"
        assert config.skill_enabled("collector") is False

    def test_config_nested_get(self):
        from app.services.novel_agent.config import AgentConfig
        config = AgentConfig(config_dict={
            "a": {"b": {"c": "deep_value"}},
        })
        assert config.get("a.b.c") == "deep_value"
        assert config.get("a.b.nonexistent", "default") == "default"

    def test_tool_enabled(self):
        from app.services.novel_agent.config import AgentConfig
        config = AgentConfig()
        assert config.tool_enabled("any_tool") is True

    def test_from_toml(self):
        """从 toml 文件加载配置"""
        toml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services", "novel_agent", "novel_agent.toml"
        )
        if os.path.exists(toml_path):
            from app.services.novel_agent.config import AgentConfig
            config = AgentConfig(config_path=toml_path)
            assert config is not None
            assert isinstance(config, AgentConfig)
        else:
            pytest.skip("toml 配置文件不存在")


# ==================== NovelDataStore 测试 ====================

class TestNovelDataStore:
    def test_store_init(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        assert store is not None
        assert isinstance(store.chapters, list)
        assert isinstance(store.all_chars, set)

    def test_load_from_json(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        chapters_data = [
            {"index": 1, "title": "第一章 测试", "content": "张三和李四是朋友"},
            {"index": 2, "title": "第二章 继续", "content": "王五出现了"},
        ]
        graph_data = {
            "nodes": [{"id": "张三"}, {"id": "李四"}],
            "links": [{"source": "张三", "target": "李四", "type": "朋友"}],
        }
        store.load_from_json(chapters_data, graph_data)
        assert len(store.chapters) == 2
        assert store.chapters[0].title == "第一章 测试"

    def test_get_chapter(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        store.load_from_json([
            {"index": 1, "title": "第一章", "content": "内容1"},
            {"index": 2, "title": "第二章", "content": "内容2"},
        ])
        ch = store.get_chapter(0)
        assert ch is not None
        assert ch.title == "第一章"
        assert store.get_chapter(99) is None

    def test_search_text(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        store.load_from_json([
            {"index": 1, "title": "第一章", "content": "张三和李四在说话"},
            {"index": 2, "title": "第二章", "content": "王五出现了"},
        ])
        results = store.search_text("张三")
        assert len(results) >= 1

    def test_stats(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        store.load_from_json([
            {"index": 1, "title": "第一章", "content": "内容1"},
        ])
        stats = store.stats()
        assert isinstance(stats, dict)
        assert "chapters" in stats

    def test_get_sentences(self):
        from app.services.novel_agent.store import NovelDataStore
        store = NovelDataStore()
        store.load_from_json([
            {"index": 1, "title": "第一章", "content": "张三和李四是好朋友。他们一起长大。"},
        ])
        sentences = store.get_sentences("张三", "李四", limit=5)
        assert isinstance(sentences, list)


# ==================== AgentMemory 测试 ====================

class TestAgentMemory:
    def test_memory_init(self):
        from app.services.novel_agent.memory import AgentMemory
        memory = AgentMemory()
        assert memory is not None

    def test_add_qa(self):
        from app.services.novel_agent.memory import AgentMemory
        memory = AgentMemory()
        memory.add_qa("问题1", "回答1", "证据1", ["tool1", "tool2"])
        recent = memory.get_recent_qa(limit=5)
        assert len(recent) >= 1
        assert recent[0]["question"] == "问题1"

    def test_log_tool_call(self):
        from app.services.novel_agent.memory import AgentMemory
        memory = AgentMemory()
        memory.log_tool_call("test_tool", {"x": 1}, {"result": "ok"}, True, 100.0)
        stats = memory.stats()
        assert isinstance(stats, dict)

    def test_project_memory(self):
        from app.services.novel_agent.memory import AgentMemory
        memory = AgentMemory()
        memory.update_project_memory("test_key", "test_value", category="test")
        result = memory.get_project_memory("test_key")
        assert result is not None

    def test_stats(self):
        from app.services.novel_agent.memory import AgentMemory
        memory = AgentMemory()
        stats = memory.stats()
        assert isinstance(stats, dict)
        assert "qa_count" in stats or "tool_calls" in stats


# ==================== NovelAgent 基础测试 ====================

class TestNovelAgent:
    def test_agent_init(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        assert agent is not None
        assert agent.registry is not None
        assert agent.store is not None
        assert agent.memory is not None

    def test_agent_tools_registered(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        tools = agent.registry.list_tools()
        assert len(tools) >= 50
        # 核心工具应该都注册了
        tool_names = [t["name"] for t in tools]
        assert "source_list" in tool_names
        assert "ocr_recognize" in tool_names
        assert "graph_stats" in tool_names
        assert "extract_characters" in tool_names

    def test_agent_think_returns_plan(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        plan = agent.think("统计一下数据")
        assert plan is not None
        assert "thought" in plan
        assert "steps" in plan
        assert isinstance(plan["steps"], list)

    def test_agent_think_source_intent(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        plan = agent.think("帮我找斗破苍穹的书源")
        assert plan is not None
        assert "steps" in plan
        # 应该至少有一步是 source_search 或 source_list
        step_tools = [s.get("tool", "") for s in plan["steps"]]
        assert any("source" in t for t in step_tools)

    def test_agent_run_health(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        resp = agent.run("统计一下")
        assert resp is not None
        assert hasattr(resp, "success")
        assert hasattr(resp, "answer")
        assert hasattr(resp, "tools_used")

    def test_agent_run_graph_stats(self):
        from app.services.novel_agent import NovelAgent, AgentConfig
        config = AgentConfig()
        agent = NovelAgent(config)
        # 预置数据
        agent.store.load_from_json(
            [
                {"index": 1, "title": "第一章", "content": "张三和李四是朋友"},
            ],
            {
                "nodes": [{"id": "张三"}, {"id": "李四"}],
                "links": [{"source": "张三", "target": "李四", "type": "朋友"}],
            }
        )
        resp = agent.run("统计一下有多少节点")
        assert resp is not None
        assert resp.success is True


# ==================== ToolDefinition 测试 ====================

class TestToolDefinition:
    def test_tool_definition_creation(self):
        from app.services.novel_agent.registry import ToolDefinition
        tool = ToolDefinition(
            name="test_tool",
            description="测试工具",
            parameters={"param1": {"type": "string"}},
            skill="test",
        )
        assert tool.name == "test_tool"
        assert tool.description == "测试工具"
        assert tool.skill == "test"


# ==================== BaseSkill 抽象基类测试 ====================

class TestBaseSkill:
    def test_base_skill_cannot_instantiate(self):
        from app.services.novel_agent.registry import BaseSkill
        with pytest.raises(TypeError):
            BaseSkill()

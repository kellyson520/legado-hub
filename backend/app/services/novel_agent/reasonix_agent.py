"""
Reasonix 风格 Agent 运行时 - 缓存优先 + 双模型协作 + 自动压缩

参考 DeepSeek-Reasonix 核心设计：
- 缓存优先循环：历史消息只追加不重写，最大化 prefix-cache 命中
- 双模型协作：planner 做规划，executor 做执行
- 自动上下文压缩：接近窗口上限时自动压缩历史
- 增量思维链：stream_delta 解析，增量推理
"""
from __future__ import annotations

import re
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .config import AgentConfig
from .store import NovelDataStore
from .memory import AgentMemory
from .registry import ToolRegistry
from .providers import (
    ProviderRegistry, ProviderConfig, Message, ToolCall,
    ToolSchema, Usage, BaseProvider,
)
from .skills import (
    SourceSkill, CollectorSkill, ExtractorSkill, AuditorSkill, GrapherSkill,
    QASkill, SummarizerSkill, WriterSkill, ReasonerSkill, OCRSkill,
)


SYSTEM_PROMPT = """你是一个专业的小说领域智能体（NovelAgent）——小说专家。

你的核心定位：
你是专精小说领域的 AI 智能体，精通书源生态、小说分析、漫画 OCR。

核心能力：
1. 书源查找 - 从网络搜索可用小说书源，支持 Legado 格式
2. 书源爬虫 - 自动分析小说网站结构，提取搜索/目录/正文规则
3. 书源编写 - 辅助编写、调试、验证书源规则
4. 小说采集 - 爬取章节内容，批量下载
5. 人物关系抽取 - 自动识别角色关系
6. 关系图谱可视化 - 生成交互式图谱
7. 质量审计 - 自动检测冲突和问题
8. 情节问答 - 基于原文回答问题
9. 内容生成 - 续写、对话、创作
10. OCR 识别 - 漫画/图片文字提取

工作方式：
- 先理解用户目标，制定计划
- 优先使用书源相关工具解决小说获取问题
- 需要分析时调用抽取/推理/图谱工具
- 涉及图片时使用 OCR 工具
- 回答清晰、准确、结构化

记住：你是小说领域的专家大脑，工具是你的手。"""


@dataclass
class AgentStep:
    step: int
    thought: str = ""
    tool: str = ""
    tool_args: Dict = field(default_factory=dict)
    tool_result: str = ""
    error: str = ""


@dataclass
class AgentResponse:
    success: bool
    goal: str
    answer: str
    iterations: int
    steps: List[AgentStep] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    confidence: float = 0.0
    usage: Usage = field(default_factory=Usage)
    cache_hit_rate: float = 0.0


class ReasonixAgent:
    """Reasonix 风格 Agent - 缓存优先 + 双模型协作

    核心特性（参考 DeepSeek-Reasonix）：
    1. 缓存优先循环：历史只追加不重写，最大化 prefix-cache
    2. 双模型协作：planner + executor 分离
    3. 自动上下文压缩：recent_keep + 历史摘要
    4. 增量解析：流式解析 tool_calls 和文本
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        store: Optional[NovelDataStore] = None,
        memory: Optional[AgentMemory] = None,
    ):
        self.config = config or AgentConfig()
        self.store = store or NovelDataStore(self.config)
        self.memory = memory or AgentMemory(self.config)

        self.registry = ToolRegistry(self.store, self.memory, self.config)
        self._register_skills()

        self._init_providers()

        self.messages: List[Message] = []
        self.iteration = 0
        self.total_usage = Usage()

    def _register_skills(self):
        skill_classes = [
            SourceSkill,
            CollectorSkill, ExtractorSkill, AuditorSkill, GrapherSkill,
            QASkill, SummarizerSkill, WriterSkill, ReasonerSkill, OCRSkill,
        ]
        for skill_cls in skill_classes:
            if self.config.skill_enabled(skill_cls.name):
                skill = skill_cls(self.store, self.memory, self.config)
                self.registry.register_skill(skill)

    def _init_providers(self):
        """初始化所有 Provider"""
        for p_cfg in self.config.get_provider_configs():
            try:
                ProviderRegistry.create(p_cfg)
            except Exception:
                pass

    @property
    def primary_provider(self) -> BaseProvider:
        """主 Provider（执行模型）"""
        model_ref = self.config.get("agent.default_model", "deepseek-flash")
        p_cfg = self.config.resolve_model(model_ref)
        return ProviderRegistry.get(p_cfg.name) or ProviderRegistry.create(p_cfg)

    @property
    def planner_provider(self) -> Optional[BaseProvider]:
        """规划模型（可选）"""
        planner_model = self.config.get("agent.planner_model", "")
        if not planner_model:
            return None
        p_cfg = self.config.resolve_model(planner_model)
        try:
            return ProviderRegistry.get(p_cfg.name) or ProviderRegistry.create(p_cfg)
        except Exception:
            return None

    async def run(self, goal: str, max_iterations: Optional[int] = None) -> AgentResponse:
        """执行 Agent 主循环（异步）

        Reasonix 缓存优先循环：
        1. 用户消息入队
        2. 构建请求（system + 历史 messages + tools）
        3. 流式获取响应
        4. 如果有 tool_calls → 执行工具 → 结果入队 → 回到步骤2
        5. 如果无 tool_calls → 返回最终回答
        """
        self.iteration += 1
        max_iter = max_iterations or self.config.get("agent.max_iterations", 20)

        self.messages.append(Message(role="user", content=goal))

        steps: List[AgentStep] = []
        tools_used: List[str] = []
        step_count = 0

        for i in range(max_iter):
            await self._compact_if_needed()

            tools = self._build_tool_schemas()
            provider = self.primary_provider

            full_text = ""
            tool_calls: List[ToolCall] = []
            usage = Usage()
            thought = ""

            try:
                async for chunk in provider.stream(
                    self.messages,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    temperature=self.config.get("llm.temperature", 0.7),
                    max_tokens=self.config.get("llm.max_tokens", 4096),
                ):
                    if chunk.error:
                        raise Exception(chunk.error)
                    if chunk.text:
                        full_text += chunk.text
                    if chunk.tool_calls:
                        tool_calls = chunk.tool_calls
                    if chunk.usage:
                        usage = chunk.usage
                        self.total_usage.prompt_tokens += usage.prompt_tokens
                        self.total_usage.completion_tokens += usage.completion_tokens
                        self.total_usage.total_tokens += usage.total_tokens
                        self.total_usage.cache_hit_tokens += usage.cache_hit_tokens
                        self.total_usage.cache_miss_tokens += usage.cache_miss_tokens
            except Exception as e:
                return AgentResponse(
                    success=False,
                    goal=goal,
                    answer=f"执行出错: {e}",
                    iterations=step_count,
                    steps=steps,
                    tools_used=tools_used,
                    confidence=0.0,
                    usage=self.total_usage,
                    cache_hit_rate=self.total_usage.cache_hit_rate,
                )

            if tool_calls:
                assistant_msg = Message(role="assistant", content=full_text, tool_calls=tool_calls)
                self.messages.append(assistant_msg)

                for tc in tool_calls:
                    step_count += 1
                    step = AgentStep(
                        step=step_count,
                        thought=thought or full_text[:200],
                        tool=tc.name,
                        tool_args=json.loads(tc.arguments) if tc.arguments else {},
                    )

                    try:
                        args_dict = json.loads(tc.arguments) if tc.arguments else {}
                        result = self.registry.call(tc.name, **args_dict)
                        step.tool_result = json.dumps(result, ensure_ascii=False, indent=2)[:2000]
                    except Exception as e:
                        step.error = str(e)
                        step.tool_result = f"ERROR: {e}"

                    steps.append(step)
                    if tc.name not in tools_used:
                        tools_used.append(tc.name)

                    tool_msg = Message(
                        role="tool",
                        content=step.tool_result,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                    self.messages.append(tool_msg)

                await asyncio.sleep(0)
            else:
                self.messages.append(Message(role="assistant", content=full_text))
                break

        answer = full_text if full_text else self._synthesize_from_steps(goal, steps)

        confidence = self._calc_confidence(steps)

        self.memory.add_qa(goal, answer, "", tools_used)

        return AgentResponse(
            success=True,
            goal=goal,
            answer=answer,
            iterations=step_count,
            steps=steps,
            tools_used=tools_used,
            confidence=confidence,
            usage=self.total_usage,
            cache_hit_rate=self.total_usage.cache_hit_rate,
        )

    def run_sync(self, goal: str, max_iterations: Optional[int] = None) -> AgentResponse:
        """同步版本的 run"""
        return asyncio.run(self.run(goal, max_iterations))

    async def _compact_if_needed(self):
        """自动上下文压缩（参考 Reasonix 的 compact_ratio）

        策略：保留最近 N 轮对话，将更早的对话压缩成摘要
        这样前面的历史仍在系统提示词里，prefix-cache 命中率更高
        """
        recent_keep = self.config.get("agent.recent_keep", 8)
        compact_ratio = self.config.get("agent.compact_ratio", 0.8)
        context_window = self.primary_provider.context_window

        if context_window == 0 or len(self.messages) <= recent_keep:
            return

        estimated_tokens = self._estimate_tokens(self.messages)
        threshold = int(context_window * compact_ratio)

        if estimated_tokens < threshold:
            return

        recent_start = len(self.messages) - recent_keep
        old_messages = self.messages[:recent_start]
        recent_messages = self.messages[recent_start:]

        summary = self._summarize_history(old_messages)

        self.messages = [Message(role="system", content=f"{SYSTEM_PROMPT}\n\n[历史对话摘要]\n{summary}")]
        self.messages.extend(recent_messages)

    def _estimate_tokens(self, messages: List[Message]) -> int:
        """粗略估算 token 数"""
        total = 0
        for msg in messages:
            total += len(msg.content) // 2
            for tc in msg.tool_calls:
                total += len(tc.arguments) // 2
        return total

    def _summarize_history(self, messages: List[Message]) -> str:
        """生成历史摘要"""
        lines = ["之前的对话摘要："]
        for msg in messages:
            if msg.role == "user":
                lines.append(f"- 用户: {msg.content[:100]}...")
            elif msg.role == "assistant" and msg.content:
                lines.append(f"- 助手: {msg.content[:100]}...")
            elif msg.role == "tool" and msg.name:
                lines.append(f"- 工具[{msg.name}]: {msg.content[:80]}...")
        return "\n".join(lines)

    def _build_tool_schemas(self) -> List[ToolSchema]:
        """构建工具 Schema 列表"""
        schemas = []
        for tool_name, tool_info in self.registry.tools.items():
            if not self.config.tool_enabled(tool_name):
                continue
            schemas.append(ToolSchema(
                name=tool_name,
                description=tool_info.get("description", ""),
                parameters=tool_info.get("parameters", {"type": "object", "properties": {}}),
            ))
        return schemas

    def _synthesize_from_steps(self, goal: str, steps: List[AgentStep]) -> str:
        """从工具执行步骤中综合回答（兜底用）"""
        if not steps:
            return "未找到相关信息。"

        parts = [f"关于「{goal}」的分析结果："]
        for step in steps:
            if step.error:
                parts.append(f"⚠️ [{step.tool}] {step.error}")
                continue
            parts.append(f"[{step.tool}] {step.tool_result[:200]}")

        return "\n\n".join(parts)

    def _calc_confidence(self, steps: List[AgentStep]) -> float:
        if not steps:
            return 0.5
        success = sum(1 for s in steps if not s.error)
        return round(min(1.0, success / len(steps) + 0.1), 2)

    def reset(self):
        """重置对话"""
        self.messages = []
        self.total_usage = Usage()

    def list_available_tools(self) -> List[Dict]:
        return self.registry.list_tools()

    def list_available_skills(self) -> List[str]:
        return self.registry.skills

    def get_stats(self) -> Dict:
        return {
            "agent": {
                "name": self.config.get("agent.name"),
                "version": self.config.get("agent.version"),
                "iteration": self.iteration,
            },
            "skills": self.list_available_skills(),
            "tools": len(self.list_available_tools()),
            "memory": self.memory.stats() if self.memory else {},
            "data": self.store.stats() if self.store else {},
            "usage": {
                "total_tokens": self.total_usage.total_tokens,
                "cache_hit_rate": self.total_usage.cache_hit_rate,
            },
        }

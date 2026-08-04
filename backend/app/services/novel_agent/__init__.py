"""
NovelAgent - 小说领域智能体系统

专精小说领域的 AI 智能体，精通书源生态、小说分析、漫画 OCR。

架构参考（DeepSeek-Reasonix / OpenClaw / Hermes）：
- 配置驱动 (Config-driven)
- 三层架构 (Agent → Skills → Infrastructure)
- 缓存优先循环 (Cache-first loop)
- 双模型协作 (Planner + Executor)
- 四层记忆 (Tiered Memory)
- 渐进式披露 (Progressive Disclosure)
- MCP 兼容工具接口
- 插件化技能 (Plugin-driven skills)
- 窄腰架构 (Narrow Waist)

三层架构：
  ┌─────────────────────────────────────┐
  │          Agent Layer                │  大脑：规划、推理、决策
  │  (NovelAgent / ReasonixAgent)       │
  └──────────────────┬──────────────────┘
                     │
  ┌──────────────────▼──────────────────┐
  │          Skills Layer               │  技能：领域能力封装
  │  (10 大技能模块)                     │
  │  source / collector / extractor     │
  │  auditor / grapher / qa / summary   │
  │  writer / reasoner / ocr            │
  └──────────────────┬──────────────────┘
                     │
  ┌──────────────────▼──────────────────┐
  │     Infrastructure Layer            │  底层设施：可复用能力
  │  ┌─────┐  ┌───────┐  ┌──────────┐  │
  │  │ OCR │  │Crawler│  │  Source  │  │
  │  └─────┘  └───────┘  └──────────┘  │
  └─────────────────────────────────────┘
"""

from .config import AgentConfig
from .agent import NovelAgent
from .reasonix_agent import ReasonixAgent
from .memory import AgentMemory
from .registry import ToolRegistry
from .store import NovelDataStore, NovelDataStoreError
from .mcp import MCPInterface
from .providers import (
    ProviderConfig, ProviderRegistry, BaseProvider,
    Message, ToolCall, ToolSchema, Usage,
)
from .infrastructure import (
    OCREngine, OCRResult, OCRLine,
    CrawlerEngine, CrawlResult,
    BookSource, SourceEngine,
)

__all__ = [
    # Agent
    'AgentConfig',
    'NovelAgent',
    'ReasonixAgent',
    'AgentMemory',
    'ToolRegistry',
    'NovelDataStore',
    'NovelDataStoreError',
    'MCPInterface',
    # Providers
    'ProviderConfig',
    'ProviderRegistry',
    'BaseProvider',
    'Message',
    'ToolCall',
    'ToolSchema',
    'Usage',
    # Infrastructure
    'OCREngine',
    'OCRResult',
    'OCRLine',
    'CrawlerEngine',
    'CrawlResult',
    'BookSource',
    'SourceEngine',
]

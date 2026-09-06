# NovelAgent 架构文档

## 设计哲学

参考 DeepSeek-Reasonix、OpenClaw、Hermes 三大编程智能体方案，遵循以下核心原则：

1. **配置即契约 (Config-Driven)** - 所有行为通过配置声明，零硬编码
2. **缓存神圣不可侵犯 (Cache-First)** - 系统提示冻结快照，历史只追加不重写
3. **窄腰架构 (Narrow Waist)** - 核心 Agent 循环极简，扩展在边缘发生
4. **渐进式披露 (Progressive Disclosure)** - 技能按需加载，避免上下文膨胀
5. **分层记忆 (Tiered Memory)** - 热/温/冷记忆分层，显式权衡成本与召回

## 架构概览

```
                    ┌─────────────────┐
                    │   API Gateway   │
                    │  (FastAPI)      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼──────┐ ┌────▼────┐ ┌──────▼──────┐
       │ NovelAgent  │ │Reasonix │ │  OCR Skill  │
       │ (Rule-based │ │ Agent   │ │ (Plugin)    │
       │  planner)   │ │(LLM-    │ │             │
       │             │ │ driven) │ │             │
       └──────┬──────┘ └────┬────┘ └──────┬──────┘
              │             │             │
              └─────────────┼─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │       Agent Runtime       │
              │  ┌─────────────────────┐  │
              │  │  ReAct Loop         │  │
              │  │  ┌─────┐ ┌─────┐   │  │
              │  │  │Think│→│ Act │→  │  │
              │  │  └──┬──┘ └──┬──┘   │  │
              │  │     ↑      │       │  │
              │  │  ┌──┴──────┴──┐    │  │
              │  │  │  Observe   │    │  │
              │  │  └────────────┘    │  │
              │  └─────────────────────┘  │
              │  ┌─────────────────────┐  │
              │  │  Context Compression│  │
              │  │  - compact_ratio    │  │
              │  │  - recent_keep      │  │
              │  └─────────────────────┘  │
              │  ┌─────────────────────┐  │
              │  │  Double Caching     │  │
              │  │  - Prompt cache     │  │
              │  │  - Semantic cache   │  │
              │  └─────────────────────┘  │
              └───────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
  ┌─────▼─────┐     ┌───────▼───────┐   ┌──────▼──────┐
  │  Skill    │     │  Tool Registry│   │   Memory    │
  │  System   │     │               │   │   System    │
  │           │     │  ┌─────────┐  │   │             │
  │ Collector │     │  │ Built-in│  │   │  Tier 1:   │
  │ Extractor │     │  │ Plugins │  │   │  System    │
  │ Auditor   │     │  └─────────┘  │   │  Memory    │
  │ Grapher   │     │  ┌─────────┐  │   │             │
  │ QA        │     │  │  MCP    │  │   │  Tier 2:   │
  │ Summarizer│     │  │ Servers │  │   │  Session   │
  │ Writer    │     │  └─────────┘  │   │  Search    │
  │ Reasoner  │     │               │   │             │
  │ OCR       │     │               │   │  Tier 3:   │
  │           │     │               │   │  Project   │
  └───────────┘     └───────────────┘   │  Memory    │
                                        │             │
                                        │  Tier 4:   │
                                        │  Vector DB │
                                        └─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │      Provider Layer       │
              │  ┌─────────────────────┐  │
              │  │  Provider Registry  │  │
              │  │  ┌───┐ ┌───┐ ┌──┐ │  │
              │  │  │OAI│ │DSK│ │...│ │  │
              │  │  └───┘ └───┘ └──┘ │  │
              │  └─────────────────────┘  │
              │  ┌─────────────────────┐  │
              │  │  Dual Model         │  │
              │  │  Planner + Executor │  │
              │  └─────────────────────┘  │
              └───────────────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │     NovelDataStore        │
              │  ┌─────┐ ┌────┐ ┌──────┐ │
              │  │Chap │ │Char│ │ Rel  │ │
              │  └─────┘ └────┘ └──────┘ │
              │  ┌─────┐ ┌────┐ ┌──────┐ │
              │  │Comm │ │Idx │ │Alias │ │
              │  └─────┘ └────┘ └──────┘ │
              └───────────────────────────┘
```

## 核心组件

### 1. Agent Runtime (agent.py / reasonix_agent.py)

两种运行模式：

- **NovelAgent** - 基于规则的规划器，确定性高，适合已知任务模式
- **ReasonixAgent** - LLM 驱动的规划器，灵活性强，适合开放域任务

循环模式（ReAct）：
```
User Input → Think (Plan) → Act (Tool Call) → Observe (Result) → Synthesize
                                      ↑
                                      └── 工具调用结果回注上下文
```

### 2. Provider Layer (providers/)

```python
class BaseProvider(ABC):
    @abstractmethod
    def stream(self, messages, system, tools) -> AsyncIterator[StreamChunk]
    @abstractmethod
    def complete(self, messages, system, tools) -> (text, tool_calls, usage)

class ProviderRegistry:
    @classmethod
    def register(kind: str, factory: type)
    @classmethod
    def create(config: ProviderConfig) -> BaseProvider
```

支持多模型并发配置，默认使用 OpenAI 兼容接口。

### 3. Skill System (skills/)

8 大技能模块，通过 `@register_skill` 装饰器自注册：

| 技能 | 职责 | 工具数 |
|------|------|--------|
| Collector | 数据采集、章节管理、搜索 | 4 |
| Extractor | 实体抽取、模式匹配、人物识别 | 3 |
| Auditor | 质量审计、冲突检测、别名验证 | 3 |
| Grapher | 关系图谱、社区发现、可视化 | 3 |
| QA | 情节问答、上下文召回、证据提取 | 4 |
| Summarizer | 章节摘要、全书概要、主题分析 | 3 |
| Writer | 续写生成、角色对话、诗歌创作 | 3 |
| Reasoner | 关系推理、演变分析、对比 | 4 |
| **OCR (New)** | **漫画识别、文字提取、翻译** | **3** |

### 4. Tool Registry (registry.py)

- 自注册模式：工具模块导入时自动注册，无需中央导入列表
- 动态过滤：基于配置启用/禁用，支持 `check_fn` 条件暴露
- MCP 兼容：标准化工具接口，可桥接外部 MCP Server

### 5. Memory System (memory.py)

四层记忆架构（参考 Hermes）：

```
Tier 1: System Memory (热)
  - AGENTS.md 项目级记忆
  - 冻结快照，会话开始时注入
  - 保护前缀缓存，运行时不变

Tier 2: Session Search (温)
  - SQLite + FTS5 全文本索引
  - 查询延迟 ~20ms
  - Agent 主动搜索历史对话

Tier 3: Project Memory (温)
  - 对话历史 + 工具调用日志
  - 按 session_id 索引
  - 支持按角色/工具/关键词过滤

Tier 4: Vector DB (冷)
  - 语义检索，存储知识图谱
  - 按需加载，零 token 税
```

### 6. Context Compression

自动压缩策略（参考 Reasonix + 行业最佳实践）：

```
触发条件: 上下文长度 > context_window * compact_ratio
策略:
  1. 保留最近 N 轮对话 (recent_keep)
  2. 将更早的对话压缩为结构化摘要
  3. 摘要注入系统提示，保持前缀缓存
  4. 工具调用/结果对不拆分
```

### 7. Double Caching

```
Prompt Caching (前缀匹配):
  - 系统提示 + 技能 Schema 前置，最大化命中
  - DeepSeek 支持 128K 上下文，缓存命中率 >80%
  - 缓存写惩罚可接受

Semantic Caching (语义匹配):
  - 存储查询-答案向量对
  - 相似查询直接返回缓存结果
  - 无需 LLM 调用，零成本
```

## 接口契约

### Agent 接口

```python
class Agent:
    async def run(self, goal: str) -> AgentResponse
    def run_sync(self, goal: str) -> AgentResponse
    def reset(self) -> None
    def get_stats(self) -> dict
```

### Provider 接口

```python
class BaseProvider(ABC):
    @property
    def name(self) -> str
    @property
    def model(self) -> str
    @property
    def context_window(self) -> int

    async def stream(self, messages, system, tools, temperature, max_tokens) -> AsyncIterator[StreamChunk]
    async def complete(self, messages, system, tools, temperature, max_tokens) -> (str, List[ToolCall], Usage)
```

### Skill 接口

```python
class BaseSkill(ABC):
    @property
    @abstractmethod
    def name(self) -> str

    @property
    @abstractmethod
    def description(self) -> str

    @property
    @abstractmethod
    def tools(self) -> List[Dict]

    @abstractmethod
    def execute(self, tool_name: str, params: Dict) -> Dict
```

### Tool 接口

```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str

    @property
    @abstractmethod
    def description(self) -> str

    @property
    @abstractmethod
    def parameters(self) -> Dict  # JSON Schema

    @property
    @abstractmethod
    def read_only(self) -> bool

    @abstractmethod
    def execute(self, params: Dict) -> Dict
```

## 安全设计

参考 OpenClaw 的多层安全边界：

1. **工具级 ACL** - per-agent 的 allow/deny 列表
2. **只读工具白名单** - read_only=True 的工具无需审批
3. **危险操作检测** - write_file 等操作触发审批回调
4. **沙箱隔离** - MCP Server 进程隔离，异常不影响主 Agent

## 扩展机制

### 新增 Skill

```python
from novel_agent import BaseSkill, register_skill

@register_skill
class MySkill(BaseSkill):
    name = "my_skill"
    description = "我的自定义技能"

    def tools(self):
        return [{
            "name": "my_tool",
            "description": "...",
            "parameters": {"type": "object", "properties": {...}}
        }]

    def execute(self, tool_name, params):
        if tool_name == "my_tool":
            return {"result": "ok"}
```

### 新增 Provider

```python
from novel_agent import BaseProvider, register_provider

@register_provider("my_provider")
class MyProvider(BaseProvider):
    async def stream(self, messages, system, tools, **kwargs):
        # 实现流式生成
        ...

    async def complete(self, messages, system, tools, **kwargs):
        # 实现非流式生成
        ...
```

### 新增 Tool

```python
from novel_agent import BaseTool, register_tool

@register_tool
class MyTool(BaseTool):
    name = "my_tool"
    description = "..."
    parameters = {"type": "object", "properties": {...}}
    read_only = True

    def execute(self, params):
        return {"result": "ok"}
```

## 配置规范

所有配置通过 TOML/JSON 声明，无硬编码：

```toml
# novel_agent.toml
[agent]
name = "NovelAgent"
version = "2.1.0"
default_model = "deepseek-flash"
planner_model = "deepseek-pro"
max_iterations = 20
compact_ratio = 0.8
recent_keep = 8

[[providers]]
name = "deepseek-flash"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
context_window = 128000

[[providers]]
name = "deepseek-pro"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-pro"
api_key_env = "DEEPSEEK_API_KEY"

[skills]
collector = true
extractor = true
auditor = true
grapher = true
qa = true
summarizer = true
writer = true
reasoner = true
ocr = true

[permissions]
mode = "ask"  # ask / allow / deny
allow = ["read_file", "novel_stats", "find_relation"]
ask = ["write_file", "generate_graph_html"]
deny = ["execute_code", "delete_file"]

[memory]
sqlite_path = "data/novel_agent.db"
max_history = 100
enable_project_memory = true
enable_semantic_cache = true

[compression]
protect_last_n = 8
strategy = "summary"  # summary / truncate / hybrid
```

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.1.0 | 2026-07 | 接入 OCR 技能，完善架构文档，增强基础设施 |
| 2.0.0 | 2026-06 | 参考 Reasonix 重构，新增 Provider 抽象、缓存优先循环 |
| 1.0.0 | 2026-05 | 初始版本，8 大技能，41 个工具 |

# 小说深度分析流水线设计

## 目标

让用户投入一份 TXT 小说后，可以稳定完成：TXT 预览/导入 → 章节解析 → 代码索引 → 人物与关系 → 时间表达与时间线 → 情节/伏笔候选 → 有证据的深析；写源、搜索和下载也必须有可重复的验收路径。LLM 只处理代码无法可靠判定的歧义，并受任务级 token/tool-call 预算约束。

## 背景与约束

- 现有 TXT 导入已经支持预览、章节切分、大小限制和导入复用。
- 现有书源搜索器支持 HTML/JSON 规则和搜索 URL，但需要本地 fixture 验证，不依赖公网站点。
- 现有 NovelAgent/analysis task 已有证据、任务、角色路由和预算字段，但没有一条验收测试证明“单本小说到深析”的完整闭环。
- 所有 LLM 结论必须绑定章节/evidence span；没有证据不得发布。
- 默认分析必须可以在没有 LLM provider 的情况下完成代码索引和候选结果。

## 方案

### 1. 代码优先分析层

对每章建立可复用索引：规范化文本、词频/句段位置、人物候选、人物别名候选、人物共现窗口、章节首尾、时间表达、相对时间表达、地点和事件触发词。分析结果使用确定性规则生成置信度与证据范围。

### 2. 分层任务

- `index`: 只运行代码，产生章节/人物/时间/事件候选。
- `structure`: 只运行代码，产生人物图、时间线、情节节点、伏笔候选。
- `explain`: 先检索少量高价值证据，再按角色路由调用 LLM；每个任务有 `max_tokens_per_task`、`max_tool_calls_per_task` 和章节上限。
- `audit`: 检查证据 hash、重复结论、冲突和模型预算，冲突进入人工复核。

### 3. 成本控制

- 代码索引结果缓存并按内容 hash 复用。
- LLM 输入只包含候选相关章节窗口，而不是整本小说。
- 同一任务超过 token/tool-call 预算立即暂停或阻断。
- 对高置信度显式信息不调用 LLM；只对别名、关系语义、时间归一化冲突、主题解释调用。
- 每次调用保存 provider/model/usage/route group 和证据 ID。

### 4. 写源与下载验收

使用本地 aiohttp fixture 提供搜索 JSON、书籍详情、目录和章节正文；通过真实 `BookSearcher` 与 ingestion service 验证搜索、书籍解析、目录、正文下载和 evidence span 生成。fixture 不代表生产书源，仅用于确定性回归。

## 接口与数据流

```text
TXT upload preview/import
  -> ParsedNovelDocument
  -> canonical work/chapter/content variant
  -> code index (characters/times/events)
  -> structure report
  -> selected evidence
  -> optional bounded LLM explain
  -> audited report
```

写源路径：

```text
source build submit
  -> candidate SourceRuleVersion
  -> source build worker
  -> search/detail/toc/content evidence
  -> audit report
  -> candidate/published decision
```

## 模块划分

- `backend/app/application/services/novel_code_analysis_service.py`: 纯代码分析、hash 缓存、人物/时间/事件候选。
- `backend/app/domain/entities/novel_code_analysis.py`: 可序列化分析报告和候选证据模型。
- `backend/app/interfaces/http/novel_analysis.py`: 暴露代码分析报告和受预算约束的深析任务接口。
- `backend/tests/test_novel_code_analysis.py`: 单元测试人物、时间、共现、缓存和证据位置。
- `backend/tests/test_novel_source_fixture_flow.py`: 本地 fixture 端到端搜索/下载/解析测试。
- `backend/tests/test_novel_deep_analysis_contract.py`: 任务预算、无 LLM fallback、证据绑定和报告契约。

## 边界

- 本阶段不引入向量数据库、不要求新的外部模型、不自动发布低置信度人物归并。
- 本阶段不声称能理解所有隐喻；隐喻与复杂时间矛盾必须标记为候选或人工复核。
- 不把整本小说发送给 LLM。

## 风险与缓解

- 人物同名/别名误合并：保留 alias candidate 和置信度，默认不自动合并。
- “三天后/当晚”等相对时间缺少绝对锚点：记录原文、章节位置和 unresolved 状态。
- 超长小说：分章处理、hash 缓存、章节窗口和硬预算。
- 书源规则变化：fixture 回归 + source audit evidence，不自动覆盖已发布版本。

## 验收标准

1. 本地 fixture 可以搜索到测试书、解析详情、读取目录并下载至少两章正文。
2. TXT 导入可生成章节和 canonical evidence。
3. 代码分析在无 LLM provider 时返回人物、共现、时间表达、时间线节点、事件候选和证据位置。
4. 相同内容 hash 重跑命中缓存，不增加 LLM/token 调用。
5. 深析任务超过预算时暂停/阻断，且不泄漏整本正文。
6. 所有结论包含 evidence IDs；冲突或低置信度结果不自动发布。
7. 后端全量测试、前端测试、Docker/Compose 验证保持通过。

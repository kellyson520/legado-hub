# Agent 与 TXT/书源工作台设计文档

## 目标

把现有小说上传、Agent 对话、书源写源能力收敛为一个可观察、可回滚、可审计的工作台：TXT 先解析预览再入库，Agent 通过受限工具读取证据并驱动写源步骤，任何自动修改都必须经过验证或进入人工审核。

## 背景与约束

- 仓库当前架构是 FastAPI application/domain/infrastructure/interfaces 分层，前端是 React/Vite；不得新增第二套 API client、分页、日志或 Provider 适配器。
- `NovelDocumentParser` 已支持 TXT、Markdown、HTML、EPUB，但上传路由直接调用 `import_upload`，缺少预览和质量反馈。
- `AgentToolRegistry` 已有 allowlist、agent kind 和 tenant scope 校验；新工具必须复用该注册表，不得绕过租户校验。
- `SourceBuildAgent` 目前只做 repair decision，需补足可追踪的 plan/attempt/validation/review 状态，但不允许自动发布未经审核的书源。
- 兼容现有 `POST /api/novel/books/import/upload`，新接口采用增量方式加入。

## 方案

### 1. 文本摄入两阶段协议

新增 `POST /api/novel/books/import/preview`：接收上传文件，返回解析后的标题、编码、章节列表摘要、每章字数、空章节/重复标题/异常长章等 warnings，以及 content hash。服务层新增不可变的 `NovelImportPreview` 与校验结果，preview 不创建书籍、不写原文件。

现有 upload 端点保留兼容行为，但内部复用同一 parser/validator；新增可选字段 `title`、`author`、`split_mode`、`min_chapter_chars`。提交后响应返回 preview 摘要、warnings、task_id，前端可展示真实进度与失败原因。

TXT 分章策略支持 `heading`、`blank-line`、`fixed-size` 三种模式，其中默认 heading：识别中文“第X章/序章/番外”等和英文 Chapter。没有标题时不伪造很多章节，而是返回单章并明确 `no_heading_detected` warning。所有模式限制最大文件字节数和最大章节数。

### 2. Agent 交互与配套工具

在现有小说 Agent 工具集合上补充只读工具：`novel.import_preview`、`novel.chapter_quality`、`source.build_status`、`source.validation_report`。工具返回结构化数据和 evidence refs，不直接写数据库。Agent 对话响应增加 `steps`/`tool_calls`/`citations` 的稳定 envelope，前端用已有 ToolResultRenderer 与 timeline 组件展示“正在读取、验证、建议、等待审核”。

写操作继续分级：`rule.propose` 只产生候选补丁；`rule.validate` 运行 fixture/sample/joint test；只有人工审核或已有发布流水线才能发布。每一步写入 AgentRuntime audit，错误也以结构化 error_code 返回。

### 3. Agent 写源流程

把 `SourceBuildAgent` 的单次 `attempt_repair` 扩展为可序列化的状态机：`planned -> collecting -> proposed -> validating -> canary|deferred|escalated`。状态机输入包含 candidate URL、profile、evidence、budget 和 actor；输出包含 attempt id、reason tags、validation checks、review item。每次自动修复最多生成候选版本，不直接修改正式 source_versions。

## 关键决策

- 不在本阶段升级 React、FastAPI 或数据库；先补契约和核心服务，降低回归面。
- Preview 不持久化原始上传，避免用户未确认的文件污染数据；正式提交后仍按现有 content hash 存储。
- 分章质量使用 warnings 而非硬失败，只有空文档、超限、危险归档和无法解码才拒绝；这样旧 TXT 仍能导入。
- Agent 不能自行发布书源；高风险或验证失败必须进入 review queue。

## 边界

- 不实现通用网页爬虫、不绕过站点登录/验证码、不保证任意站点自动写源成功。
- 不把 LLM 输出当作事实；所有章节分析和书源修改都必须带 evidence/validation。
- 不在本阶段迁移 SQLite schema；若已有 runtime repo 可复用则只增加字段映射，必要时采用内存/响应级状态。

## 风险与缓解

- 大文件耗尽内存：增加请求大小、解码后字符数、章节数上限，并在路由层尽早拒绝。
- 规则误改：候选补丁与正式版本隔离，验证不通过只能 escalate。
- Agent 工具越权：所有工具继续经过 AgentToolRegistry 的 agent kind 和 tenant_id 递归检查。
- 前后端契约漂移：先写 API/服务测试，再接入 UI，并保持旧 upload 响应字段。

## 验收标准

1. TXT/MD/HTML/EPUB 上传可以先 preview，返回稳定章节摘要和 warnings。
2. 无标题 TXT 返回单章和 `no_heading_detected`，不会伪造章节；空文件和超限文件有明确 error code。
3. 正式导入复用 preview 逻辑，重复 content hash 幂等，任务状态可追踪。
4. Agent 工具列表包含预览/质量/写源状态工具，跨租户参数被拒绝，工具结果可审计。
5. SourceBuildAgent 输出可序列化状态和验证结果，失败不会自动发布。
6. 后端 focused tests、全量 pytest、前端 tests/build（在依赖可用时）通过，`git diff --check` 无错误。

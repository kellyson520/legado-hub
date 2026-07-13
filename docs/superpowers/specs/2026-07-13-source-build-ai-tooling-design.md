# Source Build AI Tooling Design

## 目标

将规则引擎的书源构建任务接入已保存的 OpenAI-compatible provider，使每次构建都能创建可见、可审计的 AI 任务；让 AI 通过受限工具检查、探测、提案和验证候选书源；并且只在确定性验证通过后更新 candidate source version，绝不自动发布正式书源。

## 已验证的问题

1. `OpenAICompatibleProvider` 对 `https://api.deepseek.com/v1` 额外拼接 `/v1`，产生错误 endpoint：`https://api.deepseek.com/v1/v1/chat/completions`。
2. `SourceBuildRuntimeService` 仅执行兼容性模板、probe 和固定策略，未依赖 `AIService` 或 `ProviderPlatformService`，因此不创建 `ai_tasks`。
3. `AgentToolRegistry` 中 `source.inspect`、`source.probe`、`rule.propose`、`rule.validate` 与 `review.request` 没有 handler；现有 source-build 只是直接写入审计记录，未运行工具。
4. `https://www.bqgiu.cc/` 的 search 与 toc 可成功，但正文 URL 被重定向到 `/user/verify.html#/book/66/1.html`，响应是验证 shell（标题“加载中……”），不是可解析正文。

## 架构

### Provider endpoint normalization

`OpenAICompatibleProvider` 统一将以下 provider `base_url` 解析为一个 endpoint：

- `https://api.deepseek.com` → `https://api.deepseek.com/v1/chat/completions`
- `https://api.deepseek.com/v1` → `https://api.deepseek.com/v1/chat/completions`
- `https://api.deepseek.com/v1/chat/completions` → 不变

调用 payload 透传 OpenAI-compatible 的 `tools`、`tool_choice`、`temperature` 和 `max_tokens`。provider 返回中保留标准化的 assistant message 与 tool calls，API key 永远不会进入任务、日志、异常或审计数据。

### AI task 生命周期

source build 在完成 deterministic inspect/probe 后创建 `AITask(kind="source_build_repair")`。任务结果必须包含：

- `source_version_id`、`agent_run_id`、URL 与 probe 摘要；
- provider、model、usage、cost；
- `succeeded`、`failed` 或 `skipped` 状态；
- 可安全展示的 error code/message（不含凭证）。

`source_versions.payload.autonomous_build.ai_task_id` 保存关联；source-build API 返回该 ID。provider 或模型不可用时，任务仍持久化为 `failed`，规则构建转入可审查状态，而非使 AI 页面为空。

### 受控工具执行

建立 source-build 专用执行器，为下列 allowlisted 工具提供 handler：

- `source.inspect`：返回 URL、当前 candidate 规则、已收集的探测摘要；
- `source.probe`：对 candidate source rule 执行一次受限的 `SourceProbeService` full-chain probe；
- `rule.propose`：仅校验和暂存符合 schema 的 patch，不能改变 published source；
- `rule.validate`：将暂存 patch 应用到内存中的 candidate rule，执行 deterministic probe，并返回三阶段 validation；
- `review.request`：创建或返回 source review queue item。

每一次执行必须先经 `AgentToolRegistry.invoke` 做 tool name、agent kind 与 tenant scope 验证，再通过 `AgentRuntimeService` 持久化 invocation、result、evidence。AI 不具备 shell、任意网络、数据库 SQL 或直接发布工具。

### Tool-call loop 与安全边界

`SourceBuildAIRepairService` 使用 provider 的 `tool_calls` 进行最多四轮循环：模型请求工具 → 执行 allowlisted handler → 将 JSON tool result 回送模型。每轮限制输入大小、工具数量和总超时。

若 provider 无 `tool_calls` 能力或返回无效调用，使用一次严格 JSON candidate-patch 输出请求；无效 JSON 或非法字段使 AI task 失败并请求人工 review。

接受的 patch 只允许变更：`searchUrl`、`header`、`ruleSearch`、`ruleBookInfo`、`ruleToc`、`ruleContent`、`replaceRule`。patch 先在内存验证；只有 search、toc、content 都通过 deterministic probe 才写回 `source_versions.payload.source_rule`，并将 decision 标记为 `canary`。正式发布仍由现有 deploy/review 流程处理。

### 重试语义

规则引擎的 console 提交对已完成、失败、escalate 的相同 URL/keyword 创建新的 candidate source version 与新 job；仅对仍 queued/running 的同一输入复用 idempotency job。响应明确返回 `job_id`、`source_version_id`、`agent_run_id`（完成后）和 `ai_task_id`（完成后）。

### bqgiu 处理

probe 诊断将正文验证页面识别为 `content_access_blocked` 与 `verification_wall`，携带安全的 final URL、title 和响应类型。该状态不是 selector failure，也不会被标为可发布或 `canary`。

本次不实现绕过验证页、伪造浏览器验证或规避访问控制。只有出现稳定、可访问且可合法使用的公开正文 endpoint 时，才为其增加独立、带 fixture 的站点 adapter。

## 数据流

```text
POST /api/engine/source-builds
  -> fresh candidate version + source.build job
  -> SourceBuildRuntimeService
  -> real source.inspect + deterministic probe
  -> create agent run + source_build_repair AI task
  -> provider tool-call loop
  -> real source.probe/rule.propose/rule.validate tools
  -> deterministic validation
  -> candidate payload update OR review queue
  -> GET /api/ai/tasks + GET /api/engine/runs show linked audit data
```

## 错误处理

- endpoint/model/auth/network 失败：AI task `failed`，记录脱敏错误、候选保留、创建 review。
- tool 参数错误、越 tenant、未 allowlist：tool result `rejected`，不执行任何副作用。
- patch 字段超出 allowlist、不是 object、超尺寸：`rule.propose` 拒绝。
- full-chain validation 任何阶段失败：patch 不写入 candidate rule，任务结果保留 validation 和证据。
- bqgiu 验证页：probe 给出明确 block 分类，禁止 canary。

## 测试与验收标准

1. provider base URL 的三种输入都生成正确 endpoint，tool fields 被传给 provider，返回 tool calls 被标准化。
2. source-build provider 失败时仍保存失败 AI task，并在 candidate payload 记录 `ai_task_id`。
3. mock provider 发起 `source.inspect` / `rule.propose` / `rule.validate` 时，agent tool history 包含真实 handler 的结果和 evidence。
4. 跨 tenant tool 参数被拒绝，未 allowlist 字段 patch 被拒绝。
5. validation 成功只更新 candidate 的 `source_rule`；验证失败不写 candidate rule，也不发布 source。
6. 同一已完成 source-build 重试得到新 job 和新 source version。
7. bqgiu 验证页被报告为 `verification_wall`，不被误判为 selector mismatch 或 canary。
8. 以真实本地服务执行一次规则引擎构建，确认 AI task、agent run、tool audit 和 candidate version 关联可查询；若 provider 凭证或模型无效，任务必须以可见 `failed` 状态结束。

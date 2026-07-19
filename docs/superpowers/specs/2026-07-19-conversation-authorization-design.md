# Legado Hub 对话内工具授权设计

日期：2026-07-19
状态：设计已获用户批准，待书面复核
范围：AI 工作台中 Agent 对书源搜索、目录和正文读取工具的授权

## 1. 背景与目标

AI 工作台目前已经具备 RBAC、受限工具注册、工具结果审计和重复调用终止能力，但正文读取工具仍只由 HTTP 层的 `book_sources.read` 决定。用户希望采用 Hermes/OpenClaw 类的对话内授权：Agent 在需要额外能力时暂停，向用户解释将要做什么，用户在对话中选择授权范围，系统再恢复原任务。

本设计的目标是：

1. 在执行正文读取前获得明确的用户同意。
2. 保留后端 RBAC 作为不可绕过的硬门槛。
3. 支持本次、本对话和记住此选择三种范围，并可撤销、过期和审计。
4. 重启、刷新、重复点击或模型重试都不能导致重复执行。
5. 拒绝、过期、无健康书源和工具失败时立即结束本轮，不陷入工具循环。
6. 不把凭证、Cookie、Authorization 头或未经净化的网页内容写入授权状态。

不在本设计范围内：写源、发布书源、任意 URL 抓取、代码执行、浏览器控制和全局管理员授权。这些能力继续遵循各自的权限与审核流程。

## 2. 授权边界

### 2.1 两层门槛

第一层是现有 RBAC：请求主体必须拥有 `book_sources.read`，否则无论用户如何点击授权都不能调用正文工具。未来可以在同一边界上细分 `read.work`、`read.toc` 和 `read.chapter`，但本次不改变已有 `book_sources.read` 的兼容行为。

第二层是会话授权：即使 RBAC 通过，以下工具默认仍需对话授权：

- `source.search`：在启用、发布且健康的书源中搜索作品。
- `toc.get`：读取已解析作品的目录。
- `chapter.fetch`：读取单章并保存可验证证据。

以下低风险只读工具仍可在现有 RBAC 下直接使用：

- `list_visible_sources`
- `get_source_rule_summary`
- `get_source_validation_summary`
- `list_ai_analysis_results`

正文授权不会扩大到 `create_source_rule_draft`、`source.joint_test` 或任何未列出的工具。

### 2.2 授权范围与有效期

| 选项 | 作用 | 持久化 | 默认有效期 |
| --- | --- | --- | --- |
| 本次 | 当前待恢复的分析任务；允许该任务内的正文读取链完成 | 仅请求记录的续跑状态 | 15 分钟，任务完成后立即消费 |
| 本对话 | 当前用户在当前对话中允许正文读取 | grant 记录 | 最长 24 小时，用户可提前撤销 |
| 记住此选择 | 当前用户后续对话默认允许正文读取 | 用户级 grant 记录 | 最长 30 天，用户可在授权管理中撤销 |
| 拒绝 | 不执行任何待授权工具 | 记录决策 | 立即终止 |

“本次”是当前分析任务级授权，不是单个模型 tool call 级授权，因此搜索、目录和选定章节可以在同一轮中连续完成；它不会自动授权下一条用户消息。

任何 grant 都必须重新通过 RBAC 检查。用户失去 `book_sources.read`、账户被禁用或 grant 被撤销后，grant 立即失效。

## 3. 状态机

授权请求状态：

```text
pending
  ├── approved_once       -> consumed
  ├── approved_conversation -> consumed + conversation grant active
  ├── approved_remembered   -> consumed + user grant active
  ├── denied
  └── expired
```

已批准的请求不能再次执行。授权决策使用数据库条件更新（`WHERE status = 'pending'`）完成原子领取；重复点击只返回第一次决策及其续跑结果。

grant 状态：`active -> revoked | expired`。撤销和过期只影响后续工具调用，不修改历史消息或已经保存的证据。

## 4. 数据模型与存储

### 4.1 `ai_authorization_requests`

字段：

- `id`：不可猜测的 UUID。
- `actor_id`、`conversation_id`、`message_id`：归属关系。
- `requested_tools_json`：去重后的正文工具名。
- `requested_calls_json`：工具名和经过校验/净化的参数。
- `purpose`：由服务端根据模式和工具集合生成的固定说明，不能使用模型提供的任意权限描述。
- `continuation_json`：恢复模型循环所需的消息、已执行工具结果、待处理调用和证据要求；必须经过边界净化并限制总大小。
- `status`、`decision`、`resolved_at`、`resolved_by`、`expires_at`、`created_at`。
- `result_message_id`：续跑或拒绝产生的最终消息，支持幂等返回。

### 4.2 `ai_authorization_grants`

字段：

- `id`、`actor_id`、可空的 `conversation_id`。
- `scope`：`conversation` 或 `remembered`。
- `tool_names_json`：固定只能是正文读取工具的子集。
- `expires_at`、`revoked_at`、`created_at`、`updated_at`。

同一用户/对话/范围最多一条活动 grant；写入和撤销使用条件更新避免竞态。

### 4.3 对话消息

`AIConversationMessage` 增加 `metadata` JSON 字段，用于保存 `authorization_request_id`、授权状态和展示版本。历史消息仍采用追加方式，不为了更新卡片而改写正文。现有 SQLite bootstrap 使用 `CREATE TABLE` 和增量补列兼容旧库。

### 4.4 净化和容量

授权请求只保存结构化工具参数和截断后的模型续跑上下文。禁止保存密钥、Cookie、Authorization、Provider 配置和任意内部字段；网页正文在授权请求创建前不会进入续跑状态。请求参数、上下文和工具列表都有明确大小上限，超过上限时返回可理解的失败消息并结束本轮。

## 5. 服务端数据流

### 5.1 发送消息

1. API 验证用户拥有 `ai.run`，服务加载对话并追加用户消息。
2. 服务计算当前 RBAC 工具上限，加载有效 grant；过期 grant 先标记过期。
3. 低风险显式工具请求可直接执行。正文显式请求先进入授权门，不得由客户端绕过。
4. 模型循环可以向模型暴露 RBAC 允许、但仍受授权门保护的正文工具 schema；当模型请求未获 grant 的正文工具时，服务在 `_execute_model_tool_call` 之前创建授权请求并挂起循环。schema 暴露不等于执行许可。
5. 服务追加一条 `status=authorization_required` 的助手消息，返回授权请求展示数据，不执行被拦截调用。

### 5.2 决策与恢复

1. 决策 API 校验请求归属、状态、过期时间、RBAC 和范围枚举。
2. 服务以原子条件更新领取 `pending` 请求；已解决请求直接返回其 `result_message_id` 对应结果。
3. 对话/用户范围的批准先建立 grant；本次范围只注入当前恢复上下文。
4. 服务恢复保存的模型消息和待处理调用，执行工具并继续现有最大轮数、fingerprint 去重和 rejected 立即终止规则。
5. 追加最终助手消息，更新请求为 `consumed`，保存结果消息 ID，并记录工具证据和审计事件。
6. 拒绝不调用模型或正文工具，追加一条说明拒绝原因的助手消息并将请求置为 `denied`。

### 5.3 并发、重启和失联

- 同一对话同时只有一个活动授权请求；若已有 pending，请求接口返回已有卡片而不是创建第二条。
- 进程重启后，未过期 pending 可继续决策；过期请求由读取或后台清理逻辑标记 `expired`。
- 前端超时可以安全重试决策接口，服务不会重复抓取、重复写证据或重复扣模型额度。
- 恢复失败会记录失败消息和审计，不自动重新创建授权请求。

## 6. HTTP API

### 6.1 发送消息

`POST /ai/conversations/{conversation_id}/messages`

成功响应仍返回消息对象，新增：

```json
{
  "status": "authorization_required",
  "authorization_request": {
    "id": "…",
    "tools": ["source.search", "toc.get", "chapter.fetch"],
    "purpose": "读取书源内容以便基于原文分析人物和剧情",
    "expires_at": "…",
    "choices": ["once", "conversation", "remember", "deny"]
  }
}
```

### 6.2 决策

`POST /ai/conversations/{conversation_id}/authorization-requests/{request_id}/decision`

请求体：

```json
{"decision": "once"}
```

允许值为 `once`、`conversation`、`remember`、`deny`。响应返回授权请求当前状态和续跑产生的助手消息（若有）。接口幂等，重复决策不会改变已解决状态。

### 6.3 查询和撤销

- `GET /ai/conversations/{conversation_id}/authorization-requests?status=pending`：返回当前用户在该对话的待处理请求。
- `GET /ai/authorization-grants`：返回当前用户可见的活动 grant，敏感字段不出现在响应中。
- `POST /ai/authorization-grants/{grant_id}/revoke`：仅允许归属用户或管理员撤销；撤销立即影响后续工具调用。

所有接口都要求 `ai.run`，并重新检查对话归属和 `book_sources.read`；请求 ID、工具名和决策枚举严格校验。

## 7. 前端交互

### 7.1 授权卡片

助手消息状态为 `authorization_required` 时显示卡片，包含固定用途、工具名称、数据边界、来源限制、过期时间和四个操作按钮。工具名称采用中文/英文本地化标签，不直接把模型描述当作权限说明。

卡片处理期间按钮禁用并显示进度；成功后追加真实助手消息，卡片变为“已批准”；拒绝、过期和失败显示明确原因。工具结果仍以现有可折叠引用展示。

### 7.2 活动授权

对话头部显示当前对话 grant；用户可以撤销。记住的用户级 grant 在 AI 设置/授权管理中列出并可撤销。刷新或重新登录后，页面调用 pending 和 grants 接口恢复卡片和状态，不依赖浏览器内存。

### 7.3 国际化与可访问性

所有新增文本进入中英文语言表；按钮具备明确的 aria-label、键盘焦点和禁用态。卡片不会阻断历史消息滚动，网络重试不会重复提交已解决请求。

## 8. 错误与安全策略

错误分类包括：`authorization_required`、`authorization_denied`、`authorization_expired`、`authorization_revoked`、`source_unavailable` 和 `tool_rejected`。对用户显示原因，对日志和审计记录结构化错误码；不回显内部 URL、凭证、堆栈或模型原始隐藏字段。

模型输出的工具名、参数和用途都视为不可信输入；服务端只接受固定正文工具集合，并对参数执行现有严格 schema 校验、来源归属校验和同源限制。授权卡片不能批准任意新增工具，也不能改变 `book_sources.read`。

## 9. 验证计划

后端单元测试：

- 无 RBAC 时批准也被拒绝。
- 四种决策范围、过期、撤销和 grant 失效。
- 模型工具调用触发挂起且不执行；批准后只执行一次并恢复循环。
- 显式客户端正文工具请求同样进入授权门。
- 重复点击、并发批准、重启恢复和已有结果幂等。
- 拒绝、无健康发布源、rejected 结果不会换关键词死循环。
- 续跑状态净化、大小上限和敏感字段脱敏。

API 集成测试覆盖响应契约、对话归属、权限和审计。前端测试覆盖卡片显示、四个按钮、刷新恢复、撤销、失败重试和中英文文案。完成后运行现有 AI workspace、工具权限、Provider 和前端 AI 工作台回归测试。

## 10. 验收标准

当用户在人物、剧情或世界观模式提问时，Agent 必须先显示授权卡片；未批准前数据库和书源运行时没有正文工具调用。选择“本次”后可以完成当前证据链，刷新或下一条消息不会自动继承；选择“本对话”或“记住此选择”按有效期继承并可撤销。任意失败路径都能在对话中看到明确状态，不会出现无休止的工具调用或凭记忆编造原文结论。

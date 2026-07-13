# AI 工作台、用户管理与规则编辑器设计

**目标：** 在现有 Legado Hub 权限、审计和候选书源版本机制上，交付可用的 AI 对话工作台、完整用户管理和书源规则编辑发布流程。

## 范围与边界

本阶段包含三个联动模块：

1. AI 工作台：持久化会话、人物介绍、剧情解析、世界观分析和通用问答。
2. 用户管理：创建用户、编辑显示名和角色、启用或停用、重置密码、撤销全部会话。
3. 规则编辑器：编辑候选书源、验证规则、保存新候选版本以及受质量门禁保护的发布。

本阶段不实现任意网络抓取工具、任意命令执行、自动发布、外部知识库接入或新的认证体系。现有 JWT、角色、权限、审计和 `SourceRuntimeService` 是唯一的授权与状态来源。

## 体系结构

### AI 工作台

后端新增 AI 会话和消息的领域实体、仓储接口及 SQLite 实现。会话属于创建者；普通用户只能读取和继续自己的会话，具有 AI 管理权限的管理员可读取全部会话。每条用户消息选择一种 `mode`：`chat`、`character`、`storyline` 或 `world`。

`AIService` 负责将消息、模式和可选书源上下文转为 provider 请求，并保存助手回复、用量、provider、model、受控工具调用记录和失败信息。现有任务型人物分析接口继续保留；工作台使用新的会话接口，不依赖前端临时状态。

工具调用通过白名单注册表执行，且只允许以下只读工具：

- `list_visible_sources`：列出当前用户可见的书源摘要。
- `get_source_rule_summary`：读取指定候选或已发布版本的脱敏规则摘要。
- `list_ai_analysis_results`：读取当前用户可见的既有 AI 分析任务结果。

工具参数必须通过 Pydantic 模型校验；工具执行继承当前身份的权限与可见范围。工具结果在发送给模型前删除 cookie、token、authorization、provider 配置及内部字段。每次工具调用和 AI 会话写入现有审计日志，且模型、工具或 provider 异常仅返回经脱敏的错误文本。

### 用户管理

`AuthAppService` 已具备用户创建、修改、启停、改密和会话撤销能力，现有用户管理 HTTP 端点保持兼容；本阶段重点补齐前端类型、可填写表单和测试，不重复新增同名端点。用户角色保持 `admin` 与 `user` 两种，不新增自定义角色编辑器。

后端继续强制以下不变量：用户不能停用自己；不能停用或降级最后一个已启用管理员；用户停用、密码重置和管理员会话撤销都会使目标用户的 refresh sessions 失效。每次管理操作写入审计日志。

### 规则编辑器

编辑器以 `source_version_id` 为入口，展示书源名称、URL、分组、启用状态、搜索 URL 与四类 Legado 规则字段。复杂规则以格式化 JSON 编辑，表单提交前由前端做 JSON 解析，后端再做 schema 验证和敏感字段剔除。

保存不会覆盖既有版本：服务复制并规范化 payload，再调用现有候选版本创建流程生成新的 `candidate`。规则验证复用现有正则测试 API，并新增针对候选版本的安全验证操作；验证记录 search/toc/content 探针状态、质量等级和失败原因。

发布仅在调用者拥有 `book_sources.write` 权限、目标状态为 `candidate`、验证等级达到既定门槛且 `content_status` 不是 `verification_wall` 时成功；本阶段不新增独立发布权限。否则返回明确的业务错误，前端不渲染发布按钮或显示为禁用并解释原因。AI 工作台的规则摘要工具只能读取脱敏规则，不能保存或发布书源。

## API 设计

所有端点沿用现有 `ApiEnvelope` 响应格式、当前身份依赖和权限守卫。AI 会话使用 `ai.run`；规则读取使用 `book_sources.read`；规则保存、验证和发布使用 `book_sources.write`；所有用户管理写操作使用 `users.write`。

### AI 会话

- `GET /api/ai/conversations`：返回当前用户可见会话，支持 `limit`。
- `POST /api/ai/conversations`：创建会话，输入可选标题和书源版本上下文。
- `GET /api/ai/conversations/{conversation_id}`：返回会话及消息。
- `POST /api/ai/conversations/{conversation_id}/messages`：输入 `content`、`mode`、可选 `source_version_id`；保存用户消息，执行受控工具与 provider，保存助手消息并返回两条新消息。

### 用户管理

- `PATCH /api/admin/users/{user_id}`：更新显示名或角色。
- `POST /api/admin/users/{user_id}/reset-password`：重置密码并撤销目标用户会话。
- `POST /api/admin/users/{user_id}/revoke-sessions`：撤销目标用户全部会话。

现有用户列表、创建、启用、停用、密码重置和会话撤销端点保持兼容；本阶段重点补齐前端调用与测试，不重复新增同名端点。上述端点仅对拥有 `users.write` 权限的用户开放。

### 规则编辑与发布

- `GET /api/sources/versions/{source_version_id}`：返回当前身份可见的脱敏候选或已发布版本。
- `POST /api/sources/versions/{source_version_id}/drafts`：根据提交的规则 payload 创建新的候选版本。
- `POST /api/sources/versions/{source_version_id}/validate`：运行确定性规则验证与探针，返回质量摘要。
- `POST /api/sources/versions/{source_version_id}/publish`：仅在质量门禁通过后发布。

所有写操作返回新版本或目标版本摘要；验证和发布结果均包含 `content_status`，使前端可以明确处理 `verification_wall`。

## 前端体验

新增 AI 工作台页面：左侧会话列表，右侧消息时间线与输入区；模式选择使用中文名称“通用问答、人物介绍、剧情解析、世界观”。工具调用以可展开的只读引用卡片显示，失败时显示重试按钮与安全错误提示。

用户管理页由快速创建替换为表单和用户操作菜单。所有敏感操作要求明确确认；密码输入不在成功状态或用户列表中回显。无权限用户不显示编辑、重置密码或会话撤销操作。

书源列表增加“编辑规则”入口，进入独立规则编辑页。页面提供基本字段、规则 JSON、正则测试、保存候选、验证和发布区块。验证墙状态用“正文访问受阻，禁止发布”显示，发布按钮不可用。

新增和修改文案使用 UTF-8 中文。现有历史乱码文案仅在本阶段触及的页面中修复，不进行无关全仓翻译。

## 错误处理与审计

输入错误返回字段级可读信息；权限不足返回统一权限错误；不存在或不可见资源以不泄露其他用户数据的方式返回未找到。provider、工具与探针错误经过脱敏和长度限制，不记录密钥、cookie、Authorization header 或 provider 配置。

审计事件至少包含：`ai.conversation.create`、`ai.conversation.message`、`ai.tool.invoke`、`user.update`、`user.password_reset`、`session.revoke`、`source_rule.draft`、`source_rule.validate` 和 `source_rule.publish`。审计详情只保存标识符、操作类型和结果摘要。

## 测试与验收

后端测试覆盖：会话所有权与权限、工具白名单和脱敏、AI provider 成功与失败持久化、用户最后管理员保护及会话撤销、候选版本不可覆盖、验证墙禁止发布、非法规则 payload 和审计事件。

前端测试覆盖：中文 AI 模式与消息渲染、工具引用、用户表单及无权限隐藏、规则 JSON 错误、保存候选、验证结果和发布禁用。最终执行后端相关 pytest、前端 Vitest 全量测试和 `npm run build`。

验收条件：管理员可完整管理用户且不能破坏最后管理员保护；授权用户可创建会话并获得持久化的 AI 分析回复；所有工具调用均受限、脱敏且可审计；规则编辑只创建候选版本；出现 `verification_wall` 的版本无法发布。

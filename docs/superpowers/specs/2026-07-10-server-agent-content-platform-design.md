# 服务端 Agent 内容平台设计

## 目标

将 Legado MD3 阅读能力的核心处理链迁移到服务端。平台以内置 Agent、自动化爬虫、书源规则生成与校准基座为生产端，以 API Key、同步阅读 API、异步任务、SSE 和 webhook 为下游分发端。客户端保持轻量，不执行规则、不保存书源凭据、不参与爬取调度。

## 原则

- 服务端是书源、规则、内容版本、路由决策和任务状态的唯一权威。
- Agent 是服务端内部 worker，不向下游客户端下发可执行爬虫规则或凭据。
- 所有自动化结果均保留输入、证据、置信度、版本和审计记录；低置信度结果进入校准队列。
- 下游始终使用 Canonical ID 读取作品、目录、章节及任务结果，不依赖具体站点 URL。
- 同步读取只使用已验证内容；抓取、刷新、翻译和分析以异步任务完成。

## 客户端传输协议

下游 API Key 请求沿用现有 AI 平台的 provider-group、能力、配额和标准化 usage/result 语义，但服务端自身是唯一的 provider owner。客户端以 `Authorization: Bearer lh_*` 提交请求；API Key 只在创建时返回一次，数据库仅保存哈希。

每个下游请求都包含 `request_id`、可选 `idempotency_key`、`capability`、资源 Canonical ID、输入参数和期望交付模式 `sync` 或 `async`。服务端响应统一包含 `trace_id`、`status`、`result`、`usage`、`route_summary` 和异步时的 `job_id`。`usage` 至少包含读取量、爬取量、AI token、模型、成本和配额剩余的适用字段。

服务端提供 `GET /api/capabilities`，按 API Key 返回可用的阅读、抓取、翻译、知识抽取、webhook 和 SSE 能力及限额。同步端点只使用 `read.*` 能力；潜在慢任务统一使用 `jobs.submit` 并在完成时通过查询、SSE 或带 HMAC 签名的 webhook 交付。重试请求必须复用 `idempotency_key`，webhook 消费方必须以事件 ID 去重。

现有 `/api` 主路由作为新协议的唯一入口。旧 `/api/v1` API Key、配额和 AI 接口在迁移期作为适配层保留；新表和服务必须提供映射，禁止两套接口写入彼此独立的任务、配额或审计记录。

## Agent 工具基座

Agent 采用类似 CodeAgent 的受控工具调用循环：计划任务、读取已授权上下文、调用明确 schema 的工具、写入候选输出、接受验证并决定下一步。Agent 不获得任意 shell、任意网络、数据库直写或跨租户读取权限。工具调用必须使用 `ToolInvocation`、`ToolResult`、`ToolEvidence` 和 `AgentRun` 记录输入摘要、资源 ID、调用耗时、输出版本、错误和 trace ID。

第一批内置工具：

- `work.search`、`work.get`、`toc.get`、`chapter.get`：检索统一作品、目录和指定内容版本。
- `character.find`、`character.resolve_alias`、`character.relations`：查找人物、消歧别名并读取关系边及证据。
- `plot.find`、`plot.timeline`、`plot.thread`：检索剧情事件、时间线和情节线索。
- `world.find`、`world.relations`、`world.rules`：查找地点、组织、物品、设定和世界观关系。
- `evidence.search`、`evidence.get`：按章节、实体或关键词返回可授权的证据片段。
- `source.search`、`source.probe`、`rule.propose`、`rule.validate`：面向内部爬取与写源 Agent 的发现、探测、候选规则生成和回归验证工具。
- `knowledge.propose`、`translation.propose`：创建人物、剧情、世界观或翻译候选版本，不能直接发布。
- `review.request`、`review.resolve`：创建人工校准任务并接收审核结果。

工具分为 `read`、`propose`、`operate` 三类。`read` 受 API Key 和租户范围过滤；`propose` 只能生成候选版本；`operate` 包含抓取、规则校准、发布和回滚，只能由具备服务端权限的任务或人工审批触发。所有 Agent 输出必须经过 JSON schema 校验、证据引用校验、去重、置信度评估和策略检查，才可进入候选数据。

Agent 以低 token、高确定性为执行原则。每个任务先运行站点指纹、缓存查找、DOM/JSON 结构提取、规则模板匹配、章节连贯性校验和历史回归等确定性工具；只有在候选规则冲突、语义消歧、错误归因或修复建议无法由确定性结果解决时，才调用 LLM。模型调用使用最小化证据窗口、结构化工具输出、章节抽样摘要、缓存的站点画像和可复用的规则 patch，禁止将整站 HTML、完整书籍或重复 trace 注入上下文。

## 自动写源与持续校准

写源基座提供两条统一入口：

- `discovery`：全天候调度器按站点目录、已有失败源、订阅候选、健康衰退和规则覆盖缺口创建发现任务；它遵守每站点限速、robots/策略配置、预算、退避和熔断，不将失败重试放大为持续高频请求。
- `manual_url`：后台用户或具备 `source.submit` API Key 的下游提交网址、可选站点说明和测试关键词。服务端立即创建候选站点和异步写源任务，不把同步 HTTP 抓取暴露给客户端。

每条写源任务经历：URL 规范化和去重、站点画像、受控页面抓取、页面类型分类、搜索/详情/目录/正文候选识别、规则模板生成、Agent 修复循环、样例验证、跨页面回归、健康评分、候选规则版本保存、人工审批、灰度发布和持续探测。每步产生 `SourceBuildEvidence`；失败项保存根因、可复现样例和下一步建议。

`SourceBuildAgent` 不直接写入生产规则。它只可调用 `source.search`、`source.probe`、`rule.propose`、`rule.validate`、`evidence.search` 与 `review.request`，并以小步 patch 方式修正规则：一次只修改一个 selector、请求参数、JSON path 或 JavaScript rule fragment，然后运行固定 fixture 和实时抽样验证。超过修复预算、触发 WAF、需登录、疑似站点策略冲突或连续低置信度时，自动暂停并创建人工校准任务。

候选规则的发布门槛包括：搜索、详情、目录、正文四类样例的最小成功集；响应类型与解析结果一致；章节序列连贯；安全预览脱敏；与已发布版本的回归差异可解释。发布后采用租户或流量切片灰度；失败率、解析空结果、目录漂移或内容质量下降越过阈值时自动降级、回滚并触发校准 Agent。

## 无人值守自治与人工升级

平台以全天候自治为默认运行方式，而不是要求人工持续在线。每个 Agent 决策由策略引擎根据置信度、影响范围、历史成功率、预算、站点风险、回归结果和当前系统负载决定 `auto_execute`、`canary`、`defer` 或 `escalate`。

低风险、高置信度动作可自动执行：已验证规则的小范围 patch、同站点已知页面模板的补充、健康源的内容预取、失败任务的指数退避重试、通过固定回归集的候选规则灰度、已验证内容版本的路由切换。所有动作仍写入审计、版本与可逆操作日志。

高影响动作必须经过更严格的自动门槛或人工升级：新域名首次发布、跨作品大规模目录重对齐、权限或配额策略变更、跨租户可见性变更、规则需要登录或涉及敏感请求、连续回滚、未知错误激增和预算异常。人工不在线时，策略引擎保持上一个稳定版本、延迟高风险任务并继续处理独立低风险任务。

为降低人工介入频率，系统维护站点画像、规则模板库、修复 pattern 库、历史回归集、失败指纹和 Agent 评测集。每次人工审核的批准、驳回与修正都会沉淀为带适用范围的策略或 fixture；后续相似任务优先检索这些资产。自动化只在离线评测、影子运行和灰度指标均满足阈值后扩展权限范围。

自治控制台提供值守摘要而不是要求实时盯盘：每日健康、自动修复、自动回滚、积压、成本、升级事件和需人工确认的少量高价值项目。告警采用分级、聚合和冷却窗口，防止同一站点或同一根因产生告警风暴。

## 边界

### 控制平面

`Tenant`、`ClientApplication`、`ApiKey`、`ApiKeyPermission` 和 `QuotaPolicy` 管理下游访问。每次调用经过 API Key 鉴权、权限校验、配额、限流、幂等键、审计和 trace ID。后台用户会话与 API Key 相互独立。

`Job`、`JobAttempt`、`JobLease`、`DeadLetterJob` 和 `WebhookDelivery` 构成任务系统。任务有优先级、幂等键、租约、重试预算、取消状态和可版本化结果。服务端 worker 通过数据库或队列领取任务；初期可用数据库队列，接口保持可迁移到 Redis/RabbitMQ。

`Restoring session` 改为显式会话恢复状态：`checking`、`authenticated`、`anonymous`、`failed`。`checking` 超过三秒显示进度和重试；refresh 或 `/auth/me` 失败时清理 refresh token 并路由到登录页。此流程不影响 API Key 客户端。

### 书源与解析基座

定义服务端 `SourceAdapter` 标准能力：`search`、`work`、`toc`、`content`、`probe`。既有 Legado rule runtime 被封装为第一个 adapter，保留 JavaScript 规则执行、请求模板与解析逻辑，但执行环境、请求策略、日志和秘密均由服务端控制。

`SourceRule` 和 `SourceRuleVersion` 保存规则生命周期：草稿、样例、Agent 生成、静态校验、探测证据、评分、审批、发布、灰度、回滚和废弃。`CrawlAgent` 负责站点发现、页面抓取、规则提议、回归探测和异常归因；只能写入候选版本，不能直接覆盖已发布规则。

解析链拆分为 transport、response classification、JavaScript execution、document extraction、structured decode、content cleanup、chapter split 和 quality validation stages。每一 stage 输出 `ParseEvidence`，记录安全的请求摘要、响应类型、耗时、异常分类与截断预览；不保存 Cookie、Authorization 或完整敏感响应。

### 统一内容与多源互补

核心数据模型：

- `CanonicalWork`：统一作品实体、主标题、作者、语言、状态和人工确认状态。
- `SourceWork`：一个书源的作品映射、站点 ID、原始元数据和匹配置信度。
- `WorkAlias`：标题、作者、ISBN、站点别名等检索与匹配证据。
- `CanonicalChapter`：统一章节顺序、规范化标题与对齐状态。
- `SourceChapter`：来源章节、原始标题、序号、URL 和对齐得分。
- `ContentVariant`：同一统一章节的来源正文、哈希、质量评分、抓取时间和可用状态。
- `RouteDecision`：一次请求的候选源、策略、评分、选中版本、回退链和结果。

作品匹配使用标题、作者、别名、站点 ID 和外部标识建立候选；低置信度匹配进入人工校准。章节对齐同时考虑序号、规范化标题、相邻关系、长度与内容锚点，保留多个来源版本。内容路由按照租户策略、健康度、覆盖度、质量、时效、延迟与规则版本选择最佳版本，并在失败后按回退链重新选择。

### 下游分发

同步 API：作品检索、作品详情、统一目录、章节正文、内容版本元数据和路由决策摘要。同步请求只返回验证过且已存在的内容，不触发无限等待的爬取。

异步 API：发现、抓取、目录刷新、章节预取、规则生成、规则校准、导出、翻译、人物关系抽取和世界观抽取。提交接口返回 `job_id`；状态可通过查询 API、SSE 或 webhook 获得。

事件包括 `work.updated`、`toc.updated`、`chapter.ready`、`rule.published`、`task.completed` 与 `task.failed`。Webhook 必须使用签名、投递重试、事件幂等键和失败记录。SSE 只提供经 API Key 授权的租户事件流。

### 智能内容域

`TranslationSegment`、`TranslationVariant`、`TranslationMemory` 和 `TranslationReview` 管理翻译分段、重试、成本、版本与人工修订。翻译任务消费 `CanonicalChapter` 和指定 `ContentVariant`。

`CharacterEntity`、`CharacterAlias`、`CharacterRelation`、`WorldEntity`、`WorldRelation`、`TimelineEvent` 和 `ExtractionEvidence` 组成作品知识层。每个实体和关系必须携带来源章节、文本片段、模型/规则版本、置信度与人工确认状态。自动抽取不能直接修改主正文、统一目录或人工确认的知识版本。

## 管理面

服务端控制台新增或扩展：

- Agent 和 worker：能力、并发、队列延迟、租约、失败、成本和暂停控制。
- 书源与规则：版本、样例、探测、回归、灰度、审批、回滚与校准队列。
- 作品与目录：候选合并、章节对齐、冲突、内容版本、来源覆盖和路由策略。
- 下游管理：API Key、租户、权限、配额、webhook、SSE 连接、使用量和审计。
- 内容任务：抓取、预取、翻译、导出、人物关系与世界观任务的状态、证据、重试和人工确认。

## 分期交付

### Phase 1: 服务端控制平面

完成 API Key、租户权限、会话恢复状态机、任务模型、worker 租约、审计、限流和统一任务管理页。验收条件是下游可通过 API Key 安全提交和查询任务，后台会话不会停留在无限 `Restoring session`。

### Phase 1.5: Agent 工具运行时

完成工具注册表、输入输出 JSON schema、工具授权、`AgentRun`、`ToolInvocation`、证据存储、预算限制和人工审核闸门。验收条件是人物、剧情、世界观和写源 Agent 能在模拟任务中只使用获授权工具，生成可追溯且不可直接发布的候选结果。

### Phase 2: 书源 Agent 与规则基座

完成 `SourceAdapter`、Legado rule runtime 服务端封装、全天候 discovery 调度器、人工 URL 提交、规则版本仓、Agent 规则提议与修复循环、探测证据、审批发布、灰度回滚和书源管理页。验收条件是一个站点可由自动发现或人工 URL 提交进入候选、完成回归验证和灰度发布；出现错误时能自动降级并创建带证据的校准任务。

### Phase 2.5: 自治策略与持续学习

完成风险策略、自动动作权限、站点画像、修复 pattern、影子运行、自动回滚、人工审核反馈学习、摘要与告警聚合。验收条件是常见站点规则漂移可由 Agent 在预算内自动修复、灰度、回滚或保持稳定版本，人工只收到无法安全自治的聚合升级项。

### Phase 3: 统一作品目录与多源路由

完成 Canonical Work/Chapter、来源映射、章节对齐、内容版本、人工校准和路由回退。验收条件是同一作品至少两个来源的目录与正文能统一读取，源失败时有可解释回退。

### Phase 4: 下游同步与异步分发

完成阅读 API、异步抓取/预取、SSE、webhook、配额和下游运营管理。验收条件是客户端可同步读取已验证章节，并异步订阅新内容或任务结果。

### Phase 5: 翻译与作品知识域

完成翻译版本、翻译记忆、人物关系、世界观、证据、人工校准与成本治理。验收条件是下游能够消费特定内容版本的翻译和经确认的作品知识图谱。

## 非目标

本计划不将客户端变成分布式爬虫节点，不向 API Key 客户端开放书源凭据或规则执行环境，不允许 Agent 跳过审批直接发布规则，也不在第一期引入跨租户共享原始内容或自动外部账号登录。

## 验证策略

每一期均先定义 API 契约和数据库迁移测试，再验证 worker 幂等、租约恢复、权限隔离、审计和回退。书源与解析验证使用版本化 fixture、可重放 HTTP 证据与安全脱敏断言。端到端验证覆盖 API Key 客户端、后台用户、同步读取、异步任务、SSE/webhook 和失败重试。

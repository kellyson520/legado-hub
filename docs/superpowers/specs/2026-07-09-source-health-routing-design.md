# 2026-07-09 书源智能判死与分级设计

## 背景

当前项目已经完成以下基础能力：

- 本地 SQLite 书源管理与导入
- 真实书源搜索 / 目录 / 正文抓取
- 多源互补、人物校准、搜索质量排序
- Legado 原生风格 JS 运行时增强，`@js:` 搜索源多数已可执行并产出 request/url

现阶段主要瓶颈已经从“JS 执行不了”转移为“书源状态不稳定且缺乏可判定性”，典型问题包括：

- 站点已改版，上游返回内容与规则预期不一致
- 部分源依赖登录、token、cookie 或 source/login 信息
- 部分源遭遇 WAF、握手中断、重定向或连接被重置
- 部分源只是搜索失败，但目录或正文仍可用
- 当前后端与面板缺乏统一、明确、可用于运行时路由的健康状态模型

因此需要建立一套面向服务端的“书源健康探测、智能判死与分级、运行时智能分流、后台管理与干预”体系。

## 目标

本次子项目目标：

1. 对书源建立 `search / toc / content` 三层健康判定体系
2. 明确区分“暂时不可用”和“高置信失效”
3. 将健康状态直接接入搜索、目录、正文阶段的智能分流
4. 为后台面板提供可视化状态、失败原因、路由决策和人工干预入口
5. 兼容现有真实书源链路，不回退已可用源

## 非目标

本轮不做以下内容：

- 不建设完整账号中心或登录自动化平台
- 不解决所有站点的专有 helper / token 生成逻辑
- 不构建重型机器学习调度系统
- 不替换既有抓取器主链路，只在其上补健康与路由层

## 设计原则

1. **探测与判定分离**：探针只采集证据，分类器负责下结论
2. **分层健康**：search / toc / content 分开判定，允许半失效状态
3. **原因优先**：不仅回答“坏了没有”，还要回答“为什么坏”
4. **可路由**：所有健康结论必须能用于运行时选源与跳过
5. **可恢复**：异常源不能永久沉没，要支持自动恢复探测与人工恢复
6. **兼容现有数据结构**：优先复用 `book_sources` 的现有字段，并增量扩展

## 总体架构

新增四个核心组件：

### 1. SourceProbeService

负责对真实书源执行三层探测：

- `search probe`
- `toc probe`
- `content probe`

输出原始证据，不直接判死。

### 2. SourceHealthClassifier

负责把探测证据转换为：

- 三层状态
- 总体状态
- 失败原因
- 置信度
- 是否应熔断 / 跳过 / 降权
- 下次自动恢复探测时间

### 3. SourceRoutingPolicy

负责运行时分流，按搜索、目录、正文三类请求做选源与跳过。

### 4. SourceHealthAdminFacade

负责对后台管理接口和面板提供统一数据模型与人工干预入口。

## 数据模型设计

### 一、核心状态枚举

总体健康状态 `health_status`：

- `healthy`：整体可用
- `degraded`：部分可用，允许参与但降权
- `blocked`：短期熔断，不参与默认路由
- `dead`：高置信失效，默认跳过
- `unknown`：未探测或证据不足
- `disabled`：管理员禁用

三层阶段状态 `stage_status`：

- `ok`
- `degraded`
- `failed`
- `skipped`
- `unknown`

### 二、失败原因枚举

失败原因 `failure_reason` 至少包含：

- `keyword_no_result`
- `parse_empty`
- `network_unreachable`
- `timeout`
- `http_error`
- `redirect_loop`
- `tls_or_handshake_error`
- `waf_blocked`
- `auth_required`
- `token_missing`
- `cookie_required`
- `upstream_changed`
- `js_incompatible`
- `helper_missing`
- `invalid_source_rule`
- `deprecated_source`
- `unknown_error`

### 三、能力画像

为每个源生成能力画像 `capability_profile`：

- `supports_search`
- `supports_toc`
- `supports_content`
- `requires_js`
- `requires_auth`
- `requires_token`
- `waf_risk`
- `cost_level`（plain / js / heavy）
- `stability_score`

### 四、健康快照与探测历史

建议新增两类持久化对象：

1. `source_health_snapshots`
   - 每个书源一条当前快照
   - 保存总体状态、三层状态、主要失败原因、最后成功时间、下次探测时间、当前路由策略

2. `source_probe_runs`
   - 每次真实探测一条记录
   - 保存输入关键字、阶段结果、HTTP 摘要、JS 执行摘要、异常信息、延迟、样本书名

如果当前轮次希望减少数据库改动，也可以先做“运行时表 + 回写 book_sources 精简字段”的兼容方案：

- `book_sources.sourceStatus`
- `book_sources.errorMsg`
- `book_sources.lastCheckTime`
- 新增 `payload` 内嵌 `health_snapshot`

但推荐仍建立独立表，避免健康信息污染源配置本体。

## 探测设计

### 探测输入

每次探测至少包含：

- `source_id`
- `probe_mode`：`search_only` / `full_chain`
- `keyword_samples`
- `toc_sample_limit`
- `content_sample_strategy`

默认样本策略：

- 搜索样本使用真实书名，如：`捞尸人`、`斗罗大陆`
- 搜索命中后选第一本高分候选
- 目录取前若干章
- 正文优先取中前段一章，避免目录页/最新章空页噪声

### 三层探测流程

#### 1. Search Probe

采集以下证据：

- `js_exec_status`
- `request_build_status`
- `http_status`
- `response_kind`（json/html/text/redirect）
- `parse_status`
- `hit_count`
- `top_hit_name`
- `top_hit_author`
- `elapsed_ms`

#### 2. Toc Probe

在 search 成功基础上继续：

- `book_url_resolved`
- `detail_fetch_status`
- `toc_rule_status`
- `chapter_count`
- `sample_chapter_title`
- `elapsed_ms`

#### 3. Content Probe

在 toc 成功基础上继续：

- `chapter_fetch_status`
- `content_parse_status`
- `content_length`
- `next_url_status`
- `replace_rule_status`
- `elapsed_ms`

## 分类规则设计

分类采用“证据 -> 原因 -> 状态”的两段式判定。

### 一、原因识别优先级

先识别高确定性原因：

1. `token_missing / auth_required / cookie_required`
2. `waf_blocked / tls_or_handshake_error / redirect_loop`
3. `helper_missing / js_incompatible / invalid_source_rule`
4. `upstream_changed`
5. `network_unreachable / timeout / http_error`
6. `parse_empty / keyword_no_result / unknown_error`

### 二、总体状态归并规则

- 三层都 `ok` -> `healthy`
- `search ok + toc failed/content failed` -> `degraded`
- 明确鉴权、token、cookie 缺失 -> `blocked`
- 明确 WAF / 握手问题 -> `blocked`
- 明确 helper 缺失 / 规则错误 / 上游改版且连续高置信复现 -> `dead`
- 连续多次网络失败但原因不稳定 -> `blocked`
- 样本不足或仅一次探测失败 -> `unknown` 或 `degraded`

### 三、置信度与阈值

引入 `decision_confidence`：

- `low`
- `medium`
- `high`

示例：

- 单次 `JSON.parse(<html>)` 不能直接判死，可记 `upstream_changed + medium`
- 连续 3 次相同失败、且跨样本复现，可提升到 `high`
- 明确 `token=undefined`、helper 未定义，可直接高置信 `blocked/dead`

## 恢复与熔断策略

采用你确认的 **混合策略**。

### 短期熔断（自动恢复探测）

适用原因：

- `timeout`
- `network_unreachable`
- `http_error`
- `waf_blocked`
- `tls_or_handshake_error`
- `auth_required`
- `token_missing`
- `cookie_required`

策略：

- 标记 `blocked`
- 在运行时默认跳过
- 设置 `next_probe_at`
- 按指数退避重试，如 15m / 1h / 6h / 24h

### 长期降级 / 人工确认

适用原因：

- `upstream_changed`
- `helper_missing`
- `invalid_source_rule`
- `deprecated_source`
- `js_incompatible`

策略：

- 初期可标记 `degraded` 或 `dead`
- 默认不参与普通路由
- 周期性低频复探
- 面板支持人工恢复、人工重新探测、人工忽略

## 智能分流设计

### 一、搜索路由

在 `SourceReadService.search_books()` 前增加路由层。

默认选择策略：

1. 先过滤 `disabled`
2. 再过滤 `dead`
3. 再过滤处于熔断窗口内的 `blocked`
4. 对 `degraded` 源降权
5. `healthy` 源优先
6. `unknown` 源保留少量探测配额
7. `requires_auth/requires_token` 且当前无凭据时直接跳过
8. `plain` 源优先于 `js` 源，高成本源最后

### 二、目录路由

当搜索结果进入目录阶段时，优先选择：

- `toc=ok` 的源
- 若当前源 `search ok / toc failed`，则允许自动切到同书其他源

### 三、正文路由

当正文失败时：

- 若当前源 `content failed` 且已知 `toc ok`，优先尝试其他 `content=ok` 源
- 对 WAF / token 源不盲目重试，避免浪费配额与时间

### 四、路由决策输出

每次搜索/读取可选地附带：

- `health_status`
- `stage_status`
- `failure_reason`
- `route_decision`
- `route_score`
- `skip_reason`

这样后台和调试脚本都能知道“为什么没选这个源”。

## 后端接口设计

### 一、健康管理接口

建议新增：

- `GET /api/source-health/book-sources`
  - 分页查看健康列表
- `GET /api/source-health/book-sources/{source_id}`
  - 查看单源健康详情
- `POST /api/source-health/book-sources/{source_id}/probe`
  - 手动触发探测
- `POST /api/source-health/book-sources/probe-batch`
  - 批量探测
- `POST /api/source-health/book-sources/{source_id}/recover`
  - 人工恢复
- `POST /api/source-health/book-sources/{source_id}/quarantine`
  - 人工隔离 / 强制跳过

### 二、阅读接口增强

增强现有：

- `POST /api/reading/search`
- `POST /api/reading/toc`
- `POST /api/reading/content`

可增加参数：

- `routing_mode`：`auto / strict / include_blocked`
- `include_health`：是否返回健康信息
- `probe_unknown_sources`：是否允许抽样探测未知源

## 后台管理面板设计

后台面板至少增加以下能力：

### 一、健康总览页

展示：

- 总书源数
- `healthy / degraded / blocked / dead / unknown / disabled` 计数
- 最近 24h 失败 Top 原因
- 最近 24h 自动熔断数、自动恢复数

### 二、书源健康列表

每行展示：

- 书源名 / 分组 / 域名
- 总体状态
- `search/toc/content` 三层状态
- 最近失败原因
- 上次成功时间
- 下次自动探测时间
- 路由策略（优先 / 降权 / 跳过）
- 操作按钮（重探测 / 恢复 / 禁用 / 查看详情）

### 三、健康详情页

展示：

- 最近若干次 probe 结果
- 请求摘要、异常摘要、JS 执行摘要
- 样本书命中情况
- 最近路由决策记录
- 人工备注

## 与现有代码的落点

优先落在以下层：

### 应用服务层

- 新增 `app/application/services/source_probe_service.py`
- 新增 `app/application/services/source_health_classifier_service.py`
- 新增 `app/application/services/source_routing_service.py`
- 改造 `app/application/services/source_read_service.py`

### 领域 / 仓储层

- 新增健康快照与探测历史 repository 抽象
- 扩展 SQLite 实现

### 持久化工厂

- 扩展 `app/infrastructure/persistence/factory.py`

### HTTP 接口层

- 新增 `app/interfaces/http/source_health.py`
- 改造 `app/interfaces/http/reading.py`

### 基础设施层

- 复用 `LegadoBookSourceFetcher`
- 将 `scripts/smoke_js_compat_sources.py` 升级为真实探针脚本
- 将真实脚本输出从 `exec ok/fail` 提升为结构化分类报告

## 与现有字段的兼容策略

保留并继续维护：

- `book_sources.sourceStatus`
- `book_sources.errorMsg`
- `book_sources.lastCheckTime`

但将其作为“摘要镜像字段”，由健康快照回写：

- `sourceStatus` <- 总体状态摘要
- `errorMsg` <- 最近主要失败原因与简要信息
- `lastCheckTime` <- 最近探测完成时间

真实细节以独立健康表为准。

## 测试策略

### 单元测试

覆盖：

- 原因分类器
- 状态归并规则
- 熔断与恢复时间计算
- 路由打分与跳过逻辑

### 集成测试

覆盖：

- `search/toc/content` 三层 probe
- 健康快照持久化
- 阅读接口带健康路由
- 后台健康接口

### 真实源回归

基于：

- `shareBookSource.json`
- 既有真实样本：`捞尸人`、`斗罗大陆`
- JS 源 smoke 列表

要求：

- 已确认可用源不回退
- 明确失败源能被正确分类，而不是只返回空结果
- 路由能自动跳过高置信异常源

## 里程碑建议

### 阶段 1：健康底座

- 建立 probe 模型
- 建立 classifier
- 建立快照持久化
- 输出脚本级报告

### 阶段 2：接入阅读分流

- 改造 `SourceReadService`
- 搜索阶段接路由
- 目录 / 正文失败时接补路由

### 阶段 3：后台面板

- 健康列表
- 健康详情
- 手动重探测 / 恢复 / 隔离

### 阶段 4：真实源调优

- 用真实书源持续标定失败原因
- 逐步补 token/helper/兼容问题

## 方案结论

本次采用“**三层探针 + 健康分级 + 智能分流 + 后台干预**”方案。

它相对于仅打标方案的优势在于：

- 能把“搜不到”和“源失效”区分开
- 能把“JS 执行问题”和“站点/WAF/token 问题”区分开
- 能直接服务运行时选源，而不是只做报表
- 能逐步吸收真实源复杂性，而不污染主抓取链路

该方案是当前项目从“规则兼容”进入“生产化稳定性”的必要台阶。

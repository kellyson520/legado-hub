# 控制台首屏延迟与批量查询优化设计

日期：2026-07-19

## 背景与证据

控制台通过浏览器开发者工具观察到多个页面首屏请求延迟约 3000ms。后端 Trace 日志确认延迟发生在 API 服务内部，而不是浏览器渲染：

- `GET /api/events/review-queue` 实测出现 3505ms、5943ms、7732ms。
- `GET /api/sources/book_sources` 首次出现 4860ms，后续热请求降至 11–95ms。
- 书源版本和健康列表通常为 0.3–1.0s。

根因集中在四个方面：

1. SQLite 读写和后台探测/清理任务共享单文件数据库，缺少 WAL 与 busy timeout，锁等待会直接阻塞同步 SQLAlchemy 查询。
2. FastAPI 异步路由直接调用同步仓储，数据库等待期间会占用事件循环。
3. Provider/系统服务工厂在请求期间重复构造并重复读取 Provider、路由和设置；翻译审核队列即使没有翻译任务也会承担这部分开销。
4. 审核队列为了拼装一个页面，串行查询 knowledge、source version、source review、translation 四个列表，并把分页扩大为 `page * page_size`。

## 目标与非目标

目标：

- 热请求 P95 小于 500ms；冷启动或 SQLite 锁竞争时 P95 小于 1500ms。
- 同一页面首屏默认最多一个聚合 API 请求；聚合内部查询并发且使用明确的权限白名单。
- 保留所有现有权限、分页、搜索和发布安全门禁语义。
- 查询结果可按短 TTL 复用，写入/发布/审核后自动失效相关缓存。
- 在 Trace 响应头和测试中能区分数据库、服务构造、聚合和序列化耗时。

非目标：

- 不改变书源发布门禁、Agent 授权边界或外部网站探测策略。
- 不把所有页面数据合并成一个无界“大接口”。聚合接口只覆盖明确的同页资源。
- 不把 SQLite 改造成新的数据库产品；先完成当前单容器部署下的稳定优化。

## 方案

### 1. SQLite 与同步数据库边界

在唯一的 SQLAlchemy engine 初始化处配置：

- `timeout`/`busy_timeout`，让短暂锁竞争快速重试而不是长时间卡住请求。
- `journal_mode=WAL`、`synchronous=NORMAL`、`foreign_keys=ON`。
- 合理的连接池配置，避免每个仓储调用创建无法复用的连接。

所有异步路由调用同步仓储的入口统一通过受控线程池或 `asyncio.to_thread` 执行，避免同步 SQLite 等待阻塞 FastAPI 事件循环。已有后台写任务保持独立线程，不在请求线程执行网络探测。

### 2. Provider 与只读服务缓存

在 composition root 增加进程级、线程安全的短 TTL 服务快照：

- Provider registry、Provider routes、系统设置只读快照默认 TTL 30 秒。
- 写入 Provider、路由或相关系统设置后立即失效。
- 缓存键按 provider group/设置域拆分，避免配置变更造成全局抖动。

这样 `build_translation_service()`、系统设置页和 Agent 页面不会为每个请求重复扫描 Provider 表。

### 3. 同页聚合 API

新增受控的只读聚合端点（建议 `/api/console/operations/bootstrap`）：

- 输入：`page_size`、`search`，以及可选的资源集合；资源名采用后端白名单。
- 输出：一次 envelope，包含 `review_queue`、`source_builds`、`agent_runs`、`deliveries` 等请求的分页结果和各资源耗时。
- 聚合内部使用 `asyncio.gather`，每个同步仓储调用在受控线程池执行；单个资源失败只返回该资源错误，不拖垮整页。
- 不允许通过该接口执行写操作、任意 URL 或动态方法调用。

首批接入审核队列和运营首屏；书源列表两个库存视图保持独立查询，因为它们拥有不同搜索/分页状态。后续页面只在有两个以上稳定并发请求时接入。

### 4. 审核队列查询批量化

后端直接为审核队列提供统一分页查询：

- 各资源只执行一次 `count` 和一次当前页查询。
- source version 的 latest test run 通过 `IN (...)` 批量加载。
- translation chunks 通过一次 `WHERE task_id IN (...)` 批量加载，消除 N+1。
- 不再用 `page * page_size` 拉取前面所有页面；聚合排序和分页由数据库完成，或明确限制候选窗口。

现有 `publish_allowed` 与阻断原因原样保留，发布门禁仍由发布服务最终裁决。

### 5. 前端请求去重与加载体验

扩展通用 API 查询缓存/请求去重层：

- 相同 URL、参数和认证主体在短 TTL 内复用进行中的 Promise/最近结果。
- 页面卸载时取消失效请求，避免返回旧数据覆盖新搜索。
- 聚合接口优先用于首屏；分页、搜索和手动刷新仍使用明确的单资源请求。
- 所有页面继续显示独立加载、部分失败和重试状态。

## 数据流

```text
页面首屏
  -> console aggregation API
      -> permission check
      -> parallel read tasks (thread pool)
          -> SQLite WAL read transactions / provider snapshot
      -> one response envelope with per-resource timings
  -> page sections render independently
```

## 错误与一致性

- 聚合只读接口不得降低已有权限；资源不可读时返回该资源的权限错误，不泄露数据。
- 短 TTL 只用于读取；发布、审核、导入、Provider 保存等写操作主动失效相关键。
- SQLite 锁超时转换为可识别的 503/重试提示，并记录 trace_id、resource、query duration。
- 聚合结果带 `generated_at` 和 `partial` 标记，前端不把部分结果当成完整成功。

## 验证计划

后端：

- SQLite engine PRAGMA/WAL/busy timeout 单测。
- Provider registry 在 TTL 内只构造一次，写入后失效。
- translation list page 批量加载 chunks，查询次数不随任务数增长。
- review queue 聚合接口权限、部分失败、分页和排序测试。
- 使用真实 SQLite 数据集验证冷/热请求 P50/P95。

前端：

- 同页首屏只发一个聚合请求；重复挂载/刷新不产生重复未完成请求。
- 聚合部分失败仍显示可用区块和资源级重试。
- 搜索、翻页、注销后旧响应不会覆盖当前页面。

验收指标：

- 热审核队列 API P95 < 500ms。
- 热书源列表 API P95 < 300ms。
- 首屏网络请求数量相对当前实现减少至少 30%。
- 完整前端构建、相关 Vitest、后端相关 pytest 全部通过。

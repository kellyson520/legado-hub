# 控制台性能与批量查询优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 将控制台常见首屏 API 从当前的秒级抖动降低到稳定的亚秒级热请求，并减少重复查询与首屏请求数量。

**Architecture:** 先在 SQLite engine 层消除锁等待和连接配置问题，再在 composition root 缓存只读 Provider 快照；随后把审核队列和翻译列表改成批量查询，并通过受控聚合端点减少同页请求。同步仓储调用使用受控线程池，不在 FastAPI 事件循环中等待 SQLite。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、asyncio、React、Axios、Vitest、pytest。

---

## 文件边界

- `backend/app/infrastructure/persistence/sqlite/session.py`：SQLite engine、连接池和 PRAGMA。
- `backend/app/core/async_utils.py`：受控同步仓储线程执行器。
- `backend/app/infrastructure/persistence/factory.py`：Provider registry 及只读服务缓存。
- `backend/app/infrastructure/persistence/sqlite/translation_runtime_repo_impl.py`：翻译任务与 chunk 批量加载。
- `backend/app/interfaces/http/events.py`：审核队列批量/并发读取和聚合接口。
- `backend/app/interfaces/http/console.py`：新增受控首屏聚合路由。
- `frontend/src/api/client.ts`：短 TTL 请求去重与结果缓存。
- `frontend/src/api/modules/console.ts`：聚合接口类型和客户端函数。
- `frontend/src/features/operations/ReviewQueuePage.tsx`：首屏使用聚合数据，分页/搜索回退单资源查询。
- `frontend/src/features/system/SystemSettingsPage.tsx`、`frontend/src/features/operations/Operations` 页面：复用聚合响应，避免重复 Provider 请求。
- `backend/tests/test_sqlite_performance.py`、`backend/tests/test_api_console.py`、`backend/tests/test_api_source_build.py`：后端回归和性能契约。
- `backend/tests/test_translation_runtime_repo.py`：验证 chunk 查询不随任务数增长。
- `frontend/src/api/client.test.tsx`、`frontend/src/features/operations/ReviewQueuePage.test.tsx`：前端去重和首屏请求测试。

## Task 1: 建立性能基线和失败测试

**Files:**
- Create: `backend/tests/test_sqlite_performance.py`
- Create: `backend/tests/test_api_console.py`
- Modify: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: 写基线测试**

  增加以下可重复契约：SQLite 连接执行 `PRAGMA journal_mode` 返回 `wal`、`busy_timeout` 大于 0；审核队列响应保留四类资源且每类只读取当前窗口；聚合 endpoint 只允许白名单资源并返回 `partial`/资源耗时字段。

- [ ] **Step 2: 运行并确认失败**

  运行：

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_sqlite_performance.py backend/tests/test_api_console.py -q
  ```

  预期：新契约因 PRAGMA 和聚合端点尚未实现而失败。

- [ ] **Step 3: 记录真实基线**

  用带权限 token 的 `curl` 连续请求 `/api/events/review-queue`、`/api/sources/book_sources`、`/api/sources/visible` 各 10 次，保存 P50/P95、响应大小和 `X-Process-Time`，作为最终对比样本。

## Task 2: SQLite WAL、busy timeout 和连接复用

**Files:**
- Modify: `backend/app/infrastructure/persistence/sqlite/session.py`
- Test: `backend/tests/test_sqlite_performance.py`

- [ ] **Step 1: 实现 engine connect listener**

  在同一个 engine 上注册连接事件，执行 `PRAGMA journal_mode=WAL`、`PRAGMA synchronous=NORMAL`、`PRAGMA foreign_keys=ON`、`PRAGMA busy_timeout=1500`；`create_engine` 设置 `connect_args={"check_same_thread": False, "timeout": 1.5}`，并为 SQLite 使用有界 `QueuePool`。

- [ ] **Step 2: 运行 SQLite 测试**

  运行：

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_sqlite_performance.py -q
  ```

  预期：PRAGMA、连接关闭和并发读写测试通过。

- [ ] **Step 3: 增加必要索引**

  在 `bootstrap.py` 增加幂等索引：`source_test_runs(source_version_id, created_at)`、`source_versions(status, created_at, id)`、`source_review_items(status, created_at, id)`、`translation_tasks(review_status, created_at, id)`、`translation_chunks(task_id, chunk_index)`。索引创建必须在既有 bootstrap 锁内完成。

- [ ] **Step 4: 重跑基线测试**

  确认旧 API 语义不变，且数据库锁等待不再无限阻塞请求。

## Task 3: 把同步仓储移出事件循环

**Files:**
- Create: `backend/app/core/async_utils.py`
- Modify: `backend/app/interfaces/http/events.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Modify: `backend/app/interfaces/http/source_health.py`
- Modify: `backend/app/interfaces/http/engine.py`
- Test: `backend/tests/test_api_console.py`

- [ ] **Step 1: 写线程边界测试**

  用阻塞仓储 stub（等待 100ms 后返回）调用 async helper，断言事件循环可在等待期间执行另一个 coroutine，并且异常原样传播。

- [ ] **Step 2: 实现受控 helper**

  `run_sync_io(callable, *args, **kwargs)` 使用模块级 `ThreadPoolExecutor(max_workers=8, thread_name_prefix="sqlite-read")`，通过 `asyncio.get_running_loop().run_in_executor` 执行同步仓储；服务关闭时提供 shutdown。

- [ ] **Step 3: 迁移高频 GET**

  对 source list、visible versions、source health、engine runs/source builds、operations list 的同步 repository/service 调用统一包裹 helper；不把网络探测或写操作放入请求线程。

- [ ] **Step 4: 运行 API 回归**

  运行：

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_api_console.py backend/tests/test_api_source_build.py -q
  ```

## Task 4: Provider registry 和系统设置只读快照

**Files:**
- Create: `backend/app/core/ttl_cache.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/application/services/provider_platform_service.py`
- Modify: `backend/app/interfaces/http/system.py`
- Test: `backend/tests/test_provider_platform_repo.py`

- [ ] **Step 1: 写缓存失败测试**

  stub provider repository 计数，连续构造 translation/system service，断言 TTL 内只读取一次；调用保存 Provider 或替换路由后，下一次构造必须重新读取。

- [ ] **Step 2: 实现线程安全 TTL cache**

  缓存值、创建时间和 key 版本；默认 TTL 30 秒；提供 `get_or_set`、`invalidate(prefix)`，不缓存异常。

- [ ] **Step 3: 接入 composition root**

  复用 cached registry/provider snapshots，保持动态配置写入后的主动失效；不得缓存 API key 明文到日志或响应。

- [ ] **Step 4: 运行 provider/settings 测试**

  运行：

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_provider_platform_repo.py backend/tests/test_api_provider_platform.py -q
  ```

## Task 5: 消除翻译列表 N+1

**Files:**
- Modify: `backend/app/infrastructure/persistence/sqlite/translation_runtime_repo_impl.py`
- Test: `backend/tests/test_translation_runtime_repo.py`

- [ ] **Step 1: 写查询数量测试**

  创建 5 个任务、每个任务 2 个 chunk，使用 SQLAlchemy event 统计查询；调用 `list_jobs_page`，断言 chunk 查询为一次 `IN` 查询，而不是每个任务一次。

- [ ] **Step 2: 实现批量 loader**

  先查询当前页 task，再执行一次 `TranslationChunkModel.task_id.in_(task_ids)`，按 `task_id/chunk_index` 分组传给 `_load_job`；保持空任务和坏 JSON 的现有容错。

- [ ] **Step 3: 更新序列化回归**

  运行翻译 API 和服务测试，确认 chunk 顺序、内容和计数不变。

## Task 6: 审核队列批量化和受控聚合接口

**Files:**
- Modify: `backend/app/interfaces/http/events.py`
- Create: `backend/app/interfaces/http/console.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/source_runtime_repo_impl.py`
- Test: `backend/tests/test_api_console.py`
- Test: `backend/tests/test_api_source_build.py`

- [ ] **Step 1: 写失败测试**

  断言审核队列不再使用 `page * page_size` 读取前置页面；测试 source versions 的 latest runs 只发生一次批量查询；聚合接口拒绝未授权资源和所有写方法。

- [ ] **Step 2: 实现批量查询**

  为 source runtime repo 增加当前页版本与 latest test runs 的一次性读取；在 events 服务层用 `asyncio.gather` 并行读取 knowledge/source/source-review/translation，保持每类资源的原有分页 meta。

- [ ] **Step 3: 实现聚合端点**

  新增 `GET /api/console/operations/bootstrap`，资源白名单固定为 `review_queue`、`source_builds`、`agent_runs`、`deliveries`；每个资源使用独立权限检查和受控分页参数，返回 `{generated_at, partial, resources, timings_ms}`。

- [ ] **Step 4: 运行审核队列和权限测试**

  运行：

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_api_console.py backend/tests/test_api_source_build.py backend/tests/test_api_work_knowledge.py -q
  ```

## Task 7: 前端请求去重、聚合首屏和资源级降级

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/modules/console.ts`
- Modify: `frontend/src/features/operations/ReviewQueuePage.tsx`
- Modify: `frontend/src/features/system/SystemSettingsPage.tsx`
- Modify: `frontend/src/features/operations/AgentRunsPage.tsx`
- Test: `frontend/src/api/client.test.tsx`
- Test: `frontend/src/features/operations/ReviewQueuePage.test.tsx`

- [ ] **Step 1: 写失败测试**

  同一 key 的两个并发 `apiClient.get` 只调用 adapter 一次；不同搜索参数不共享结果；缓存过期后重新请求；审核队列首屏只调用聚合 API，分页仍调用原 endpoint。

- [ ] **Step 2: 实现请求去重与短 TTL**

  在 `createApiClient` 内增加可选 `dedupeKey`/稳定参数序列化；缓存进行中的 Promise 和成功结果，默认 TTL 2 秒；401、写请求、异常和注销时清理相关 key。

- [ ] **Step 3: 接入聚合首屏**

  ReviewQueue 首屏请求 `listOperationsBootstrap`，把资源级结果转换为现有 row 类型；聚合失败时回退原分页 API，部分资源失败只显示该资源重试。

- [ ] **Step 4: 运行前端测试与类型检查**

  运行：

  ```bash
  cd frontend
  npm test -- --run src/api/client.test.tsx src/features/operations/ReviewQueuePage.test.tsx
  npx tsc -b --pretty false
  ```

## Task 8: 压测、观测和部署验收

**Files:**
- Modify: `backend/app/core/middleware.py`
- Create: `backend/scripts/benchmark_console_latency.py`
- Test: `backend/tests/test_api_console.py`
- Modify: `docs/superpowers/specs/2026-07-19-console-latency-batch-query-design.md`

- [ ] **Step 1: 增加阶段耗时**

  Trace 记录 `auth_ms`、`factory_ms`、`db_ms`、`serialize_ms`、`total_ms`；不记录请求正文、API key 或书源 cookie。

- [ ] **Step 2: 编写基准脚本**

  对目标 endpoint 预热 2 次，再并发 10 次，输出 P50/P95/P99、错误率、响应字节数和每阶段耗时。

- [ ] **Step 3: 运行完整验收**

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests -q
  cd frontend && npm test -- --run && npx tsc -b --pretty false
  npm run build -- --minify=false
  ```

- [ ] **Step 4: 对比基线并重启服务**

  只有在功能回归通过且 P95 达标后重启后端；保留旧日志和新基准结果，确认公网 `/`、聚合 API 和静态前端资源可访问。

- [ ] **Step 5: 提交实现**

  ```bash
  git add backend frontend docs/superpowers/plans/2026-07-19-console-latency-batch-query-plan.md
  git commit -m "perf: optimize console latency and batched queries"
  ```

## Task 9: 数据库体积治理与安全归档

**Files:**
- Create: `backend/app/application/services/database_maintenance_service.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/bootstrap.py`
- Modify: `backend/app/interfaces/http/system.py`
- Create: `backend/scripts/database_report.py`
- Test: `backend/tests/test_database_maintenance.py`

- [ ] **Step 1: 写体积报告失败测试**

  用临时 SQLite 数据库插入 source version、tool result、audit log 和 refresh token，断言报告返回文件字节数、page_count、freelist、各表行数/字节估算，并把敏感字段只返回计数和大小，不返回 payload 内容。

- [ ] **Step 2: 实现只读数据库报告**

  `database_report.py` 和管理服务统计：文件本体、`-wal`/`-shm`、SQLite page/freelist、按表行数和文本列长度排序的 Top N；当前生产库证据显示约 26MB，其中 `source_versions.payload` 约 19.8MB，2383 个候选版本是主因。

- [ ] **Step 3: 增加安全保留策略**

  只允许删除明确过期的 `ephemeral_book_sources`、已过期 refresh token、已完成且超过保留期的 job events；source versions、审计日志、Agent 工具结果默认只归档不删除。归档前写入压缩 JSONL（按日期分片）并记录校验和，失败不得删除源数据。

- [ ] **Step 4: 防止候选版本无限增长**

  为同一 `source_type/source_id` 的候选版本增加保留窗口配置：保留最新 N 个和最近审计/发布引用版本；清理任务只标记 `superseded`/`failed` 且不再被 review/deployment 引用的旧版本，默认 dry-run，人工确认后才执行。

- [ ] **Step 5: 增加 VACUUM/压缩运维命令**

  在 WAL 空闲且无写事务时提供显式 `database-maintenance compact`，先 checkpoint，再 `VACUUM`；禁止在 HTTP 请求内自动执行，报告中记录执行前后大小和耗时。

- [ ] **Step 6: 运行数据库治理测试**

  ```bash
  /tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_database_maintenance.py -q
  /tmp/legado-hub-pytest-venv/bin/python backend/scripts/database_report.py --db /tmp/legado-hub-ui-20260715.sqlite --top 10
  ```

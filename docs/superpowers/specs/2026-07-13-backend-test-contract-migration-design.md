# 后端测试契约迁移设计

**目标：** 让后端回归测试以当前 `interfaces/http`、应用服务和 SQLite 持久化架构为唯一契约，先修复真实的跨平台与 Legado 运行时缺口，再逐步迁移或退役只针对废弃接口的测试。

## 已确认的根因

当前全量 pytest 同时收集两类测试：

1. 当前架构测试：使用 `app.interfaces.http`、当前权限模型、运行时书源和 AI 工作区服务。
2. 遗留架构测试：依赖旧 `app.routers`、旧 repository、旧 API 无鉴权调用或已经删除的异常类型。

两类测试不能通过恢复旧接口来同时满足。恢复旧接口会绕过当前权限、重复维护数据模型，并与现有架构边界冲突。

另外，已复现三个独立的真实缺口：

- Windows 默认 GBK 打开 UTF-8 的 `novel_schema.sql` 会抛出 `UnicodeDecodeError`。
- `test_core_events.py` 的事件总线行为测试缺少 `fresh_event_bus` 与 `started_event_bus` fixture。
- 规则 harness 使用 `executor_js_rule` 阶段执行 `@js` 规则，而当前 Legado JS 兼容配置未允许该阶段。

## 方案比较

### 方案 A：恢复旧 routers、models 和匿名 API

优点是短期内可减少部分旧测试失败；缺点是引入两套 API 与权限模型，并重新暴露已废弃的匿名访问路径。

### 方案 B：只跳过所有失败测试

优点是实现快；缺点是会掩盖真实的编码、fixture 和 JS runtime 缺口，回归测试不再可信。

### 方案 C：保留当前架构，分批修复真实缺口并迁移遗留测试（采用）

先修复与架构无关的跨平台和运行时问题；随后把旧测试迁移到当前 HTTP/服务契约，或在已有等价覆盖时退役。每批都保留可验证的行为测试。

## 第一批范围

第一批只处理三个可独立验证的问题：

1. 所有读取 `novel_schema.sql` 的活跃测试显式使用 UTF-8。
2. 为现有 `MemoryEventBus` 行为测试提供隔离、可清理的 fixture。
3. 把 `executor_js_rule` 加入 Legado JS 兼容 profile 的允许阶段，使规则 harness 能执行受超时保护的 `@js` 规则。

不修改 `backend/app/routers`，不恢复旧匿名 API，不改变当前 HTTP 权限要求。

## 验收标准

- `test_novel_ingestion_service.py`、`test_novel_repo.py`、`test_rag_retriever.py` 在 Windows 上不会因 SQL 文件编码失败。
- `test_core_events.py` 的事件总线隔离测试可以收集并通过。
- `test_engine_selector_pipeline.py` 的 JS harness 用例可以通过，且既有 JS worker 测试保持通过。
- 修改后运行第一批相关测试；后续批次继续降低全量 pytest 的遗留失败数量，而不恢复废弃架构。

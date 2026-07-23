# 书源健康批量探测设计

## 目标

让书源健康任务稳定地以“每 30 分钟一个批次”的方式持续探测启用书源：一个批次包含多个书源，单个书源失败不影响同批次其余书源；当书源总量较大时按小批次轮转，避免一次性压垮服务器。

## 根因

调度器已经注册 `*/30 * * * *` 的 `probe_source_health` 任务，但 `SourceProbeService._build_search_preflight()` 使用集合判断请求体是否为空：

```python
if request_body not in {None, ""}:
```

当 Legado JS 返回字典请求体时会抛出 `TypeError: unhashable type: 'dict'`。异常从第一个书源向上冒泡，`SourceHealthAdminService.probe_book_sources()` 没有逐源隔离，于是整批停止。

## 设计

### 调度批次

- 调度间隔保持 `*/30 * * * *`。
- `SOURCE_HEALTH_PROBE_BATCH_SIZE` 默认设置为 `50`，作为并发 worker 的小批次大小；在一个 30 分钟窗口内持续领取到期候选，直到窗口结束。
- `SOURCE_HEALTH_PROBE_BATCH_TIMEOUT_SECONDS` 默认设置为 `1740` 秒，并由调度器设置硬截止，给下一次 30 分钟触发预留 1 分钟缓冲。
- 候选领取使用 SQLite 短租约；调度器异常退出或手动探测并发时，租约过期后可自动重试，避免重复探测和旧结果覆盖新结果。
- 候选顺序保持现有策略：没有快照的源优先，其次按 `last_probe_at` 最早的源优先，保证大库存持续轮转。
- 用户可通过配置调小批次；不把数千个书源一次性提交给探测器。

### 批次执行

- `SourceHealthAdminService.probe_book_sources()` 逐源执行一个完整探测链：搜索 → 目录 → 正文。
- 每个 worker 在自己的小批次内逐源执行，不并发调用同一 worker 的共享 JS/HTTP runtime；SQLite 租约保证同一个书源不会被多个 worker/进程同时领取。
- 每个源用独立 `try/except` 包围。异常被转换为该源的失败结果并继续下一个源。
- 当前源使用扣除故障持久化保护时间后的剩余窗口作为 `asyncio.wait_for()` 上限；超时记录失败，尚未开始的候选记为 `deferred`，下一轮重新取候选。
- 调度器对所有 worker 再设置一层绝对截止；即使某个异常 worker 忽略内部 timeout，也会被取消并把未完成源列为 `deferred`。
- 返回结果包含 `total`、`succeeded`、`failed`、`deferred` 和每个源的结果，调度日志记录批次进度。

### 请求体诊断

请求体预览只使用不抛异常的空值判断，字典、列表和字符串都可以安全格式化；不改变实际请求逻辑。

### 时间边界

单批次沿用探测器已有 HTTP/JS 超时能力，并增加 1740 秒批次 deadline，目标是在下一个 30 分钟调度点前完成。单源异常、超时以及故障记录都受剩余 deadline 约束；deadline 到达后剩余候选进入下一轮。

成功探测的 snapshot、probe run 和 `book_sources` 镜像状态在同一个 SQLite 事务中提交，避免只写入其中一部分。

## 数据流

```text
APScheduler */30
        │
        ▼
取最多 50 个启用候选源
        │
        ▼
逐源完整探测 ──失败──► 记录该源失败，继续下一个
        │
        ▼
保存 snapshot / probe_run / source health fields
        │
        ▼
记录批次成功数、失败数、总数
```

## 测试策略

- JS 搜索返回字典 body 时，预检不再抛 `TypeError`。
- 批次中第一个源抛异常时，第二个源仍被探测，结果包含一个失败和一个成功。
- 调度器继续传递批次限制，候选选择保持未探测/最旧优先。
- 现有健康详情、手动探测、调度注册和源探测回归测试必须保持通过。

## 非目标

- 不改变健康分类规则、数据库快照字段或前端状态含义。
- 不把同一个书源拆成并发请求。
- 不引入 Redis 等外部锁服务；使用本地 SQLite 租约满足当前直接运行部署的进程间去重需求。

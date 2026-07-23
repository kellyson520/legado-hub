# 书源健康批量探测修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复书源健康定时探测首源异常导致整批停止的问题，并让每 30 分钟按可控小批次持续探测多个启用书源。

**Architecture:** 保留 APScheduler 的 `*/30` 触发器和现有健康快照持久化。调度器从 SQLite 领取到期候选，按 50 个源拆成小批次并在 1740 秒硬截止内持续轮转；每个 worker 逐源执行完整链路，租约避免重复领取，逐源捕获异常并返回批次汇总。

**Tech Stack:** Python 3.12、FastAPI、APScheduler、SQLite、pytest、Legado source fetcher。

---

### Task 1: 修复 JS 请求体诊断的字典异常

**Files:**
- Modify: `backend/app/application/services/source_probe_service.py:363-365`
- Test: `backend/tests/test_source_probe_service.py`

- [x] **Step 1: Write the failing test**

```python
def test_search_preflight_accepts_structured_request_body():
    service = SourceProbeService(fetcher=FakeFetcherWithJsBody())

    result = service._build_search_preflight(
        {"id": 7, "bookSourceUrl": "https://example.test", "searchUrl": "@js:({url: 'https://example.test/search', body: {q: key}})"},
        "捞尸人",
    )

    assert result["request_preview"] == "https://example.test/search BODY={'q': '捞尸人'}"
```

- [x] **Step 2: Run it to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_probe_service.py -k structured_request_body -q`

Expected: FAIL with `TypeError: unhashable type: 'dict'` at the existing set-membership check.

- [x] **Step 3: Write minimal implementation**

Replace the set membership with a type-safe comparison:

```python
if request_body is not None and request_body != "":
    preview = f"{preview} BODY={request_body}"
```

- [x] **Step 4: Run the test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_probe_service.py -k structured_request_body -q`

Expected: PASS.

### Task 2: 让健康批次逐源容错并返回汇总

**Files:**
- Modify: `backend/app/application/services/source_health_admin_service.py:130-170`
- Test: `backend/tests/test_source_health_admin_service.py`

- [x] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_probe_book_sources_continues_after_one_source_failure():
    service = build_service_with_probe_results(fail_source_ids={1}, success_source_ids={2})

    result = await service.probe_book_sources([1, 2], keyword_samples=["捞尸人"], timeout_seconds=60)

    assert result["total"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert [item["source_id"] for item in result["results"]] == [1, 2]
    assert result["deferred"] == 0
```

- [x] **Step 2: Run it to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_health_admin_service.py -k continues_after_one_source_failure -q`

Expected: FAIL because the current first exception escapes and source 2 is never processed.

- [x] **Step 3: Write minimal implementation**

Wrap each `probe_book_source()` call and keep processing. Use the remaining batch deadline to bound each source; stop before starting more sources when the deadline is exhausted:

```python
deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
results = []
failed = 0
deferred = 0
for source_id in source_ids:
    remaining = deadline - time.monotonic() if deadline is not None else None
    if remaining is not None and remaining <= 0:
        deferred += 1
        continue
    try:
        call = self.probe_book_source(source_id, keyword_samples=keyword_samples, probe_mode=probe_mode)
        item = await asyncio.wait_for(call, timeout=remaining) if remaining is not None else await call
        results.append({"source_id": int(source_id), **item, "status": "completed"})
    except Exception as exc:
        failed += 1
        results.append({"source_id": int(source_id), "status": "failed", "error": str(exc)[:500]})
return {"results": results, "total": len(results), "succeeded": len(results) - failed, "failed": failed, "deferred": deferred}
```

- [x] **Step 4: Run the test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_health_admin_service.py -k continues_after_one_source_failure -q`

Expected: PASS, with both source IDs present.

### Task 3: 配置可控小批次并验证调度传参

**Files:**
- Modify: `backend/app/core/config.py:43-45`
- Modify: `backend/app/tasks/scheduler.py:165-190,454-475`
- Test: `backend/tests/test_source_health_scheduler.py`

- [x] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_smart_probe_uses_configured_small_batch(monkeypatch):
    captured = {}

    class FakeAdminService:
        def list_probe_candidate_ids(self, limit):
            captured["limit"] = limit
            return [1, 2, 3]

        async def probe_book_sources(self, source_ids, keyword_samples, probe_mode="full_chain"):
            return {"results": [], "total": len(source_ids), "succeeded": len(source_ids), "failed": 0}

    monkeypatch.setattr(scheduler, "build_source_health_admin_service", lambda: FakeAdminService())
    result = await scheduler.run_smart_source_health_probe_job(limit=50, keyword_samples=["捞尸人"])

    assert captured["limit"] == 50
    assert result["failed"] == 0
```

- [x] **Step 2: Run it to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_health_scheduler.py -k configured_small_batch -q`

Expected: FAIL because the scheduler result currently has no `failed` field and the batch result contract is incomplete.

- [x] **Step 3: Write minimal implementation**

Set the default batch size and deadline while leaving the cron expression unchanged:

```python
SOURCE_HEALTH_PROBE_BATCH_SIZE: int = 50
SOURCE_HEALTH_PROBE_BATCH_TIMEOUT_SECONDS: int = 1500
```

Keep `run_smart_source_health_probe_job()` passing the configured `limit` and `timeout_seconds` to the service, and merge the service summary into the scheduler result.

- [x] **Step 4: Run the test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_health_scheduler.py -k 'smart_probe' -q`

Expected: PASS, and existing candidate ordering tests remain green.

### Task 4: 回归验证并发布

**Files:**
- No additional source files; deployment uses the validated `frontend/dist` and backend checkout.

- [x] **Step 1: Run focused backend tests**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_source_probe_service.py backend/tests/test_source_health_admin_service.py backend/tests/test_source_health_scheduler.py -q`

Expected: PASS.

- [x] **Step 2: Run frontend build and diff checks**

Run: `npm run build` in `frontend/`, then `git diff --check`.

Expected: Vite build succeeds and diff check is clean.

- [x] **Step 3: Commit and push**

```bash
git add backend/app/application/services/source_probe_service.py backend/app/application/services/source_health_admin_service.py backend/app/core/config.py backend/app/tasks/scheduler.py backend/tests/test_source_probe_service.py backend/tests/test_source_health_admin_service.py backend/tests/test_source_health_scheduler.py docs/superpowers/specs/2026-07-23-source-health-batch-probing-design.md docs/superpowers/plans/2026-07-23-source-health-batch-probing.md
git commit -m "fix: make source health probing batch resilient"
git push origin main
```

- [x] **Step 4: Redeploy and verify**

Sync `frontend/dist` to `/tmp/legado-hub-release/frontend/dist`, reload Nginx, restart the local Uvicorn from `/tmp/legado-hub-main-merge/backend` with the two `/root/legado-hub/backend/data` database environment variables, and verify:

```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:3001/api/health
```

Expected: both return the normal unauthenticated `401` response, the scheduler log reports `probe_source_health` registration, and subsequent 30-minute runs report `total`, `succeeded`, `failed`, and `deferred` counts without aborting at the first source.

### Task 5: 误判与并发边界加固

已补充以下回归保护：

- 合法 JS 请求或合法 JSON 空结果不会因为请求预览/元数据包含文本而被降级或判为验证墙。
- 批次内故障持久化和调度器外层 worker 都受绝对截止时间约束。
- 成功结果的 snapshot、probe run、书源镜像状态在同一 SQLite 事务写入。
- 到期候选通过 SQLite 租约领取，避免并行任务重复探测和旧结果覆盖。

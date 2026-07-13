# 后端测试契约迁移（第二批）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将异常与响应测试迁移到当前后端契约，并修复异常响应码字段不一致。

**Architecture:** 当前 `AppException` 用 `code` 表示业务错误码，异常处理器位于 `app.core.exception_handlers`。测试只覆盖这个公开契约；`from_exception()` 对当前 `code` 优先，对历史 `error_code` 回退。

**Tech Stack:** Python 3.13、pytest、pytest-asyncio、FastAPI、Pydantic。

---

### Task 1: 保留缓存 Provider 测试夹具

**Files:**
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_infra_cache.py`

- [x] **Step 1: 验证当前 fixture 缺失会阻断缓存测试**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_infra_cache.py --tb=short
```

Expected: 历史基线中因 `cache_provider` fixture 缺失报错。

- [x] **Step 2: 添加最小 fixture**

```python
@pytest.fixture
def cache_provider():
    from app.infrastructure.cache.memory_cache import MemoryCacheProvider

    return MemoryCacheProvider()
```

- [x] **Step 3: 验证缓存测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_infra_cache.py --tb=short
```

Expected: `19 passed`。

### Task 2: 为当前异常响应码添加回归测试

**Files:**
- Modify: `backend/tests/test_core_response.py`
- Test: `backend/tests/test_core_response.py::TestFromException`

- [x] **Step 1: 写入当前异常契约测试**

```python
def test_from_app_exception_uses_current_code_attribute(self):
    from app.core.exceptions import NotFoundException
    from app.core.response import from_exception

    response = from_exception(NotFoundException("source not found"))

    assert response["code"] == "NOT_FOUND"
    assert response["message"] == "source not found"
```

- [x] **Step 2: 验证测试在修复前失败**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_response.py::TestFromException::test_from_app_exception_uses_current_code_attribute --tb=short
```

Expected: FAIL，实际 `code` 为 `INTERNAL_ERROR`。

- [x] **Step 3: 写入最小生产修复**

```python
def from_exception(exc) -> Dict:
    return {
        "success": False,
        "code": getattr(exc, "code", getattr(exc, "error_code", "INTERNAL_ERROR")),
        "message": getattr(exc, "message", str(exc)),
        "data": None,
        "trace_id": get_trace_id(),
    }
```

- [x] **Step 4: 验证响应测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_response.py --tb=short
```

Expected: `18 passed`。

### Task 3: 迁移异常和 HTTP handler 测试

**Files:**
- Modify: `backend/tests/test_core_exceptions.py`
- Test: `backend/tests/test_core_exceptions.py`

- [x] **Step 1: 替换废弃类型断言**

使用 `AppException("TEST_ERROR", "test message", 418, {"field": "name"})` 覆盖基础字段和字符串表示，并参数化断言六个当前子类的默认 `status_code`、`code`、`message`。

- [x] **Step 2: 使用实际 Request 构造 handler 测试**

添加一个 `request_factory` fixture，用 `FastAPI(debug=...)` 与 ASGI scope 创建 `starlette.requests.Request`，并设置 `request.state.trace_id`。测试必须从 `app.core.exception_handlers` 导入 handler。

- [x] **Step 3: 覆盖 handler envelope**

分别断言：

```python
response = await app_exception_handler(request_factory(), NotFoundException("missing"))
assert response.status_code == 404
assert json.loads(response.body)["trace_id"] == "trace-test"
```

```python
response = await validation_exception_handler(request_factory(), RequestValidationError([...]))
assert response.status_code == 422
assert json.loads(response.body)["details"]["errors"] == [...]
```

```python
response = await generic_exception_handler(request_factory(debug=False), RuntimeError("secret"))
assert json.loads(response.body)["message"] == "internal server error"
```

并验证 `register_exception_handlers()` 为 `AppException`、`RequestValidationError` 和 `Exception` 注册三个 handler。

- [x] **Step 4: 验证异常测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_exceptions.py --tb=short
```

Expected: 全部通过，不再引用 `BaseAppException`、`QuotaExceededException` 或从 `exceptions` 导入 handler。

### Task 4: 批次验证与提交

**Files:**
- Modify: `backend/app/core/response.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_core_exceptions.py`
- Modify: `backend/tests/test_core_response.py`
- Create: `docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-2-design.md`
- Create: `docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-2.md`

- [x] **Step 1: 运行批次回归**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_infra_cache.py tests\test_core_exceptions.py tests\test_core_response.py --tb=short
```

Expected: 所有收集到的测试通过。

- [x] **Step 2: 检查工作区**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误，变更仅属于本批次。

- [ ] **Step 3: 提交并推送**

Run:

```powershell
git add backend/app/core/response.py backend/tests/conftest.py backend/tests/test_core_exceptions.py backend/tests/test_core_response.py docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-2-design.md docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-2.md
git commit -m "test: migrate backend regression contracts batch 2"
git push origin feat/source-import-rule-center
```

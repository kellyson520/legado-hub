# 后端测试契约迁移（第三批）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将应用服务和领域实体测试迁移至当前后端公开契约，并移除对删除架构的测试依赖。

**Architecture:** 认证与书源服务均通过异步 duck-typed 内存 fake 隔离持久化层。测试调用真实应用服务，fake 保留服务流程需要的状态及副作用；三组共享 fixture 放入测试根目录的 `conftest.py`。

**Tech Stack:** Python 3.13、pytest、pytest-asyncio、FastAPI、dataclasses。

---

### Task 1: 为领域实体提供当前 fixture

**Files:**
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_domain_entities.py`

- [x] **Step 1: 添加失败路径所需的最小完整 fixture**

```python
@pytest.fixture
def sample_book_source_data():
    return {
        "bookSourceUrl": "https://example.com",
        "bookSourceName": "测试书源",
        "enabled": True,
        "sourceStatus": "ok",
    }
```

另外添加同样只包含当前实体构造字段的 `sample_rss_source_data` 和
`sample_subscription_data`。

- [x] **Step 2: 验证领域实体测试**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_domain_entities.py --tb=short
```

Expected: 测试不再因 fixture 缺失而报错。

### Task 2: 重建认证服务回归契约

**Files:**
- Modify: `backend/tests/test_app_services.py`
- Test: `backend/tests/test_app_services.py`

- [x] **Step 1: 用 async duck-typed `FakeAuthRepository` 替换旧仓储 mock**

fake 在内存中保存 `User`、`RefreshSession`、`ApiKey` 与 `AuditEvent`；只实现
当前 `AuthAppService` 调用的方法，例如 `get_user_by_username`、
`save_user`、`assign_roles`、`update_user`、`save_api_key` 和
`record_audit`。

- [x] **Step 2: 写入当前认证服务测试**

覆盖：

```python
created = await service.create_user_admin(
    "reader", "Reader", "user", "password-123", actor_id=1
)
assert created["username"] == "reader"
```

并分别覆盖重复用户名/无效角色、最后管理员保护、禁用后会话撤销、API key
生命周期、成功登录、错误密码和登出。

- [x] **Step 3: 先运行新测试确认旧架构测试不再适用**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_app_services.py --tb=short
```

Expected before replacement: 失败或收集错误来自旧 `UserRepository` 与旧方法。

- [x] **Step 4: 验证认证服务测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_app_services.py --tb=short
```

Expected: 当前认证服务测试通过。

### Task 3: 重建书源服务回归契约

**Files:**
- Modify: `backend/tests/test_app_services.py`
- Test: `backend/tests/test_app_services.py`

- [x] **Step 1: 添加 `FakeSourceRepository`**

fake 提供分页、CRUD、导出、`list_book_sources_full` 和
`upsert_book_sources`，以 `bookSourceUrl` 表示去重身份。

- [x] **Step 2: 写入当前书源服务测试**

覆盖：

```python
result = await service.list_book_sources(page=2, page_size=1)
assert result["meta"] == {"page": 2, "page_size": 1, "total": 2, "total_pages": 2}
```

以及 CRUD、导出计数和临时 JSON 文件导入。在导入测试中传入
`replace_existing=False`，并断言已有 URL 没有再次上送至 upsert。

- [x] **Step 3: 验证应用服务测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_app_services.py --tb=short
```

Expected: 当前认证和书源服务测试全部通过。

### Task 4: 批次验证与提交

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_app_services.py`
- Create: `docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-3-design.md`
- Create: `docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-3.md`

- [x] **Step 1: 运行批次回归**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_app_services.py tests\test_domain_entities.py --tb=short
```

- [x] **Step 2: 检查工作区**

Run:

```powershell
git diff --check
git status --short
```

- [ ] **Step 3: 提交并推送**

Run:

```powershell
git add backend/tests/conftest.py backend/tests/test_app_services.py docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-3-design.md docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-3.md
git commit -m "test: migrate backend regression contracts batch 3"
git push origin feat/source-import-rule-center
```

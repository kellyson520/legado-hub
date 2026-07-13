# 后端测试契约迁移（第四批）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使核心安全测试准确覆盖当前的 API key、JWT 和 bcrypt 契约。

**Architecture:** 不修改 `app.core.security`。测试由旧实现细节转向当前公开输入输出：JWT 由配置定义过期时间，解码失败使用空字典，密码由 bcrypt 校验而非固定摘要长度。

**Tech Stack:** Python 3.13、pytest、python-jose、bcrypt。

---

### Task 1: 迁移 API key 与 JWT 测试

**Files:**
- Modify: `backend/tests/test_core_security.py`
- Test: `backend/tests/test_core_security.py`

- [x] **Step 1: 保留当前失败基线**

Run:

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_security.py --tb=short
```

Expected: 旧固定长度、旧 `expires_delta`、`None` 和 `mask_api_key` 断言失败。

- [x] **Step 2: 将旧断言替换为当前公开契约**

```python
key = generate_api_key()
assert key.startswith("lh_")
assert len(key.removeprefix("lh_")) >= 32
```

```python
payload = decode_access_token(create_access_token({"sub": "test_user"}))
assert payload["aud"] == "access"
assert isinstance(payload["exp"], int)
assert decode_access_token("invalid.jwt.token") == {}
```

删除 `mask_api_key()` 测试和所有 `expires_delta` 调用。

- [x] **Step 3: 验证 API key 与 JWT 测试**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_security.py --tb=short
```

### Task 2: 迁移 bcrypt 密码散列测试

**Files:**
- Modify: `backend/tests/test_core_security.py`
- Test: `backend/tests/test_core_security.py tests/test_core_security_main.py`

- [x] **Step 1: 用 bcrypt 属性替换固定 SHA-256 长度**

```python
hashed = hash_password("my_password")
assert hashed.startswith("$2")
assert hashed != "my_password"
assert verify_password("my_password", hashed) is True
```

保留不同输入生成不同散列，并增加同一密码两次生成不同散列以覆盖随机盐。

- [x] **Step 2: 验证安全模块回归**

Run:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_security.py tests\test_core_security_main.py --tb=short
```

### Task 3: 批次验证与提交

**Files:**
- Modify: `backend/tests/test_core_security.py`
- Create: `docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-4-design.md`
- Create: `docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-4.md`

- [ ] **Step 1: 检查工作区**

Run:

```powershell
git diff --check
git status --short
```

- [ ] **Step 2: 提交并推送**

Run:

```powershell
git add backend/tests/test_core_security.py docs/superpowers/specs/2026-07-13-backend-test-contract-migration-batch-4-design.md docs/superpowers/plans/2026-07-13-backend-test-contract-migration-batch-4.md
git commit -m "test: migrate core security contracts"
git push origin feat/source-import-rule-center
```

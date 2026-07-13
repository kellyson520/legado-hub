# 中文化与用户权限基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现管理员/普通用户的可审计用户管理 API、中文化控制台导航与状态文案，并使前后端权限一致。

**Architecture:** 保留现有 FastAPI `AuthAppService`、SQLite AuthRepository 和 React Router 结构。后端在 `admin` 路由和服务层以当前 identity 的 `admin` role/permission 强制授权；前端通过 `/auth/me` 的角色数据渲染中文导航和用户管理界面，但不承担安全责任。

**Tech Stack:** Python 3.13、FastAPI、Pydantic、SQLAlchemy/SQLite、React 18、TypeScript、React Router、Vitest、pytest。

---

## 文件结构

- 修改 `backend/app/domain/entities/auth.py`：User 增加显示名称和最后登录时间的领域字段。
- 修改 `backend/app/domain/repositories/auth_repo.py`、`backend/app/infrastructure/persistence/sqlite/auth_repo_impl.py`、`backend/app/infrastructure/persistence/sqlite/schema.py`：用户查询/更新、角色赋值和状态变更的存储接口。
- 修改 `backend/app/application/services/auth_service.py`：管理员用户生命周期与最后管理员保护。
- 新建 `backend/app/interfaces/http/admin_users.py`：管理员用户 API 与安全序列化。
- 修改 `backend/app/interfaces/http/router.py`、`backend/app/interfaces/http/auth.py`、`backend/app/interfaces/http/deps.py`：挂载路由、返回 role/display name、集中管理员依赖。
- 新建 `backend/tests/test_api_admin_users.py`：管理员 API、403、最后管理员保护、密码不回显。
- 修改 `frontend/src/api/types.ts`、`frontend/src/api/modules/admin.ts`、`frontend/src/api/modules/auth.ts`：中文化角色/状态类型、用户管理 HTTP client、身份数据。
- 新建 `frontend/src/lib/i18n.ts`：导航、状态、错误码统一中文映射。
- 修改 `frontend/src/app/navigation.tsx`、`frontend/src/app/router.tsx`、`frontend/src/app/providers/AuthProvider.tsx`：中文导航、管理员可见路由和角色状态。
- 修改 `frontend/src/features/admin/AdminUsersPage.tsx`：用户列表、创建、编辑、启停、重置密码中文界面。
- 新建 `frontend/src/features/admin/AdminUsersPage.test.tsx`、`frontend/src/lib/i18n.test.ts`：前端角色导航、中文状态/错误映射、用户管理操作测试。

### Task 1: 扩展用户领域与 SQLite 存储

**Files:**
- Modify: `backend/app/domain/entities/auth.py`
- Modify: `backend/app/domain/repositories/auth_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/auth_repo_impl.py`
- Test: `backend/tests/test_auth_repo_sqlite.py`

- [ ] **Step 1: 写失败的 repository 测试**

```python
@pytest.mark.asyncio
async def test_auth_repository_updates_user_profile_role_and_active_state():
    user = await repo.save_user(User(username='reader', password_hash='hash'))
    updated = await repo.update_user(
        user.id, display_name='读者', is_active=False, role_names=['user'],
    )
    assert updated.display_name == '读者'
    assert updated.is_active is False
    assert updated.role_names == ['user']
```

- [ ] **Step 2: 运行红灯测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_auth_repo_sqlite.py::test_auth_repository_updates_user_profile_role_and_active_state`

Expected: FAIL，因为 `update_user` 尚不存在。

- [ ] **Step 3: 实现最小 repository 合约和字段映射**

```python
async def update_user(self, user_id: int, *, display_name: str | None = None,
                      is_active: bool | None = None, role_names: list[str] | None = None) -> User | None:
    ...
```

数据库迁移兼容现有 SQLite：缺失 `display_name` 与 `last_login_at` 列时用 SQLAlchemy bootstrap 增列或保持 nullable 默认值；`_user_from_model` 一律填充领域字段。

- [ ] **Step 4: 运行 repository 测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_auth_repo_sqlite.py`

Expected: PASS。

### Task 2: 实现管理员用户生命周期服务与 API

**Files:**
- Modify: `backend/app/application/services/auth_service.py`
- Create: `backend/app/interfaces/http/admin_users.py`
- Modify: `backend/app/interfaces/http/deps.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/interfaces/http/auth.py`
- Test: `backend/tests/test_api_admin_users.py`

- [ ] **Step 1: 写管理员创建、普通用户拒绝和安全序列化的失败测试**

```python
def test_admin_can_create_user_but_response_never_contains_password(client, admin_headers):
    response = client.post('/api/admin/users', headers=admin_headers, json={
        'username': 'reader', 'display_name': '读者', 'role': 'user', 'password': 'reader-password',
    })
    assert response.status_code == 200
    assert response.json()['data']['role'] == 'user'
    assert 'password' not in str(response.json()['data'])

def test_regular_user_cannot_list_users(client, user_headers):
    response = client.get('/api/admin/users', headers=user_headers)
    assert response.status_code == 403
    assert response.json()['code'] == 'FORBIDDEN'
```

- [ ] **Step 2: 运行红灯测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_admin_users.py`

Expected: FAIL，因为 `/api/admin/users` 未注册。

- [ ] **Step 3: 添加服务方法、管理员依赖与路由**

实现 `AuthAppService.list_users_admin`、`create_user_admin`、`update_user_admin`、`reset_password_admin`、`set_user_enabled_admin`。API 返回：

```python
{'id': user.id, 'username': user.username, 'display_name': user.display_name,
 'role': user.role_names[0] if user.role_names else 'user',
 'status': 'enabled' if user.is_active else 'disabled',
 'created_at': user.created_at.isoformat(), 'last_login_at': ...}
```

`require_admin` 只接受拥有 `admin` role 或 `admin:users` permission 的 identity。创建仅允许 `admin`/`user`；禁止禁用自己、降级最后一个启用管理员、禁用最后一个启用管理员。每次变更调用现有 `record_audit`。

- [ ] **Step 4: 把角色加入 `/api/auth/me`**

```python
'data': {'user_id': identity.user_id, 'roles': sorted(identity.roles),
         'permissions': sorted(identity.permissions), 'display_name': identity.display_name}
```

- [ ] **Step 5: 运行 API 测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_admin_users.py tests/test_api_auth.py tests/test_api_auth_main.py`

Expected: PASS。

### Task 3: 前端中文文案、权限导航与 API 类型

**Files:**
- Create: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/modules/auth.ts`
- Modify: `frontend/src/api/modules/admin.ts`
- Modify: `frontend/src/app/providers/AuthProvider.tsx`
- Modify: `frontend/src/app/navigation.tsx`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/src/lib/i18n.test.ts`
- Test: `frontend/src/app/router.test.tsx`

- [ ] **Step 1: 写中文状态与角色导航失败测试**

```tsx
it('maps runtime status and forbidden error to Chinese', () => {
  expect(statusText('failed')).toBe('已失败')
  expect(errorText('FORBIDDEN')).toBe('没有执行此操作的权限')
})

it('hides 用户管理 and 系统设置 from a regular user', () => {
  render(<Navigation roles={['user']} />)
  expect(screen.queryByText('用户管理')).not.toBeInTheDocument()
  expect(screen.getByText('AI 工作台')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行红灯测试**

Run: `cd frontend; npm test -- --run src/lib/i18n.test.ts src/app/router.test.tsx`

Expected: FAIL，因为映射和角色导航尚未实现。

- [ ] **Step 3: 建立集中式文案映射并接入 AuthProvider**

`i18n.ts` 仅导出 `statusText`、`errorText`、`roleText`、`navigationText`。AuthProvider 从 `/auth/me` 保存 `roles`，把 `isAdmin` 作为 `roles.includes('admin')`；导航使用中文 title 和 `adminOnly` 条目。

- [ ] **Step 4: 运行前端文案与路由测试**

Run: `cd frontend; npm test -- --run src/lib/i18n.test.ts src/app/router.test.tsx src/app/providers/AuthProvider.test.tsx`

Expected: PASS。

### Task 4: 实现中文用户管理页面

**Files:**
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Create: `frontend/src/features/admin/AdminUsersPage.test.tsx`
- Modify: `frontend/src/api/modules/admin.ts`
- Test: `frontend/src/features/admin/AdminUsersPage.test.tsx`

- [ ] **Step 1: 写用户列表、创建与停用操作的失败组件测试**

```tsx
it('renders Chinese user controls and disables a selected user', async () => {
  render(<AdminUsersPage />)
  expect(await screen.findByText('用户管理')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', {name: '停用'}))
  expect(adminApi.setUserEnabled).toHaveBeenCalledWith(2, false)
})
```

- [ ] **Step 2: 运行红灯测试**

Run: `cd frontend; npm test -- --run src/features/admin/AdminUsersPage.test.tsx`

Expected: FAIL，因为页面没有完整操作接口或中文按钮。

- [ ] **Step 3: 实现管理界面与 API 调用**

页面使用中文列：用户名、显示名称、角色、状态、创建时间、最后登录、操作。创建弹窗含用户名、显示名称、角色和初始密码；编辑只可改显示名称和角色；重置密码使用独立确认弹窗；停用后立即刷新当前列表。所有 API 错误使用 `errorText` 渲染。

- [ ] **Step 4: 运行组件测试与生产构建**

Run: `cd frontend; npm test -- --run src/features/admin/AdminUsersPage.test.tsx; npm run build`

Expected: 测试 PASS，TypeScript/Vite build 成功。

### Task 5: 阶段集成验证

**Files:**
- Modify: `backend/tests/test_api_admin_users.py`
- Modify: `frontend/src/app/AppShell.tsx`
- Test: `backend/tests/test_api_admin_users.py`
- Test: `frontend/src/app/router.test.tsx`

- [ ] **Step 1: 写管理员/普通用户端到端契约测试**

```python
def test_disabled_user_cannot_login_and_admin_audit_records_change(client, admin_headers):
    user = create_user(client, admin_headers, username='disabled-reader')
    client.post(f'/api/admin/users/{user["id"]}/disable', headers=admin_headers)
    login = client.post('/api/auth/login', json={'username': 'disabled-reader', 'password': 'reader-password'})
    assert login.status_code == 401
```

- [ ] **Step 2: 运行红灯或回归确认**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_admin_users.py`

Expected: 测试在实现前失败，完成后 PASS。

- [ ] **Step 3: 添加中文空状态与防御性页面 guard**

AppShell 对非管理员路由重定向到概览；用户管理列表为空时显示“暂无用户”；加载失败显示“加载用户失败，请稍后重试”。

- [ ] **Step 4: 运行完整阶段验证**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_api_admin_users.py tests/test_api_auth.py tests/test_api_auth_main.py tests/test_auth_repo_sqlite.py
cd ..\frontend
npm test -- --run src/lib/i18n.test.ts src/app/router.test.tsx src/app/providers/AuthProvider.test.tsx src/features/admin/AdminUsersPage.test.tsx
npm run build
```

Expected: 所有后端测试、前端测试及前端生产构建通过。

- [ ] **Step 5: 提交变更（仓库恢复 Git 元数据后执行）**

```powershell
git add backend/app backend/tests frontend/src docs/superpowers
git commit -m "feat: add Chinese admin user management"
```

当前目录未检测到 `.git`，不在无 Git 元数据状态下伪造 commit。

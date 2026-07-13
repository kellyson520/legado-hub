# AI 工作台、用户管理与规则编辑器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付持久化 AI 分析工作台、完整中文用户管理，以及书源候选规则编辑、验证和发布流程。

**Architecture:** 仅扩展当前 `interfaces/http`、`application/services`、领域仓储和 SQLite 实现，不修改遗留 `backend/app/routers`。AI 会话采用专用实体和仓储；工具仅允许经过 Pydantic 参数校验的只读白名单。规则编辑复用 `SourceRuntimeService` 的候选版本与 `SourceTestRun`，由确定性质量门禁控制发布。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy/SQLite、pytest、React 18、TypeScript、React Router、Vitest、Testing Library、Tailwind。

---

## 文件结构

- 新建 `backend/app/domain/entities/ai_conversation.py`、`backend/app/domain/repositories/ai_conversation_repo.py`、`backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py`：会话、消息、工具调用与 SQLite 映射。
- 修改 `backend/app/infrastructure/persistence/sqlite/schema.py`、`backend/app/infrastructure/persistence/factory.py`：创建表并注册工作台依赖。
- 新建 `backend/app/application/services/ai_workspace_service.py`；修改 `backend/app/interfaces/http/ai.py`：受控工作台与会话 API。
- 修改 `backend/app/application/services/source_runtime_service.py`、`backend/app/interfaces/http/sources.py`：规则详情、草稿、验证和发布。
- 修改 `frontend/src/api/modules/{ai,admin,sources}.ts`、`frontend/src/app/router.tsx`：请求、类型和权限路由。
- 新建 `frontend/src/features/ai/AIWorkspacePage.tsx`、`frontend/src/features/sources/SourceRuleEditorPage.tsx`；修改用户管理和书源列表页。

### Task 1: AI 会话持久化

**Files:**
- Create: `backend/app/domain/entities/ai_conversation.py`
- Create: `backend/app/domain/repositories/ai_conversation_repo.py`
- Create: `backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Test: `backend/tests/test_ai_conversation_repo.py`

- [ ] **Step 1: 写失败的仓储测试**

```python
def test_conversation_repository_persists_messages_and_owner(session):
    repo = SQLiteAIConversationRepository(session)
    repo.create_conversation(AIConversation(id="c1", actor_id="7", title="人物介绍"))
    repo.append_message(AIConversationMessage(id="m1", conversation_id="c1", role="user", mode="character", content="介绍主角"))
    assert repo.get_conversation("c1", "7").id == "c1"
    assert repo.get_conversation("c1", "8") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python -m pytest tests/test_ai_conversation_repo.py -v`

Expected: FAIL，原因是会话实体和仓储尚不存在。

- [ ] **Step 3: 实现实体、协议、schema 与 SQLite 映射**

```python
@dataclass
class AIConversation:
    id: str
    actor_id: str
    title: str

@dataclass
class AIConversationMessage:
    id: str
    conversation_id: str
    role: str
    mode: str
    content: str
    status: str = "succeeded"
```

为 `ai_conversations` 建 `actor_id` 索引；为 `ai_messages`、`ai_tool_calls` 建 `conversation_id` 索引。仓储提供 `create_conversation`、`list_conversations(actor_id)`、`get_conversation(id, actor_id)`、`append_message`、`list_messages` 和 `save_tool_call`，JSON 使用 `ensure_ascii=False`。

- [ ] **Step 4: 运行仓储测试确认通过**

Run: `cd backend; python -m pytest tests/test_ai_conversation_repo.py -v`

Expected: PASS。

- [ ] **Step 5: 提交持久化基础**

```bash
git add backend/app/domain/entities/ai_conversation.py backend/app/domain/repositories/ai_conversation_repo.py backend/app/infrastructure/persistence/sqlite/ai_conversation_repo_impl.py backend/app/infrastructure/persistence/sqlite/schema.py backend/tests/test_ai_conversation_repo.py
git commit -m "feat: persist ai conversations"
```

### Task 2: AI 工作台服务与受控工具

**Files:**
- Create: `backend/app/application/services/ai_workspace_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_ai_workspace_service.py`

- [ ] **Step 1: 写失败的服务测试**

```python
async def test_message_persists_reply_and_sanitized_tool_result():
    service = AIWorkspaceService(platform=FakePlatform(), conversations=repo, sources=FakeSources(), ai_tasks=FakeTasks(), audit=FakeAudit())
    reply = await service.send_message("c1", "7", "character", "列出书源", [{"name": "list_visible_sources", "arguments": {}}])
    assert reply["content"] == "主角信息"
    assert "cookie" not in str(reply)

async def test_unknown_tool_is_rejected():
    with pytest.raises(ValidationException):
        await service.send_message("c1", "7", "chat", "x", [{"name": "shell", "arguments": {}}])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python -m pytest tests/test_ai_workspace_service.py -v`

Expected: FAIL，原因是 `AIWorkspaceService` 尚不存在。

- [ ] **Step 3: 实现模式、工具、脱敏、provider 与审计**

```python
ALLOWED_TOOLS = {"list_visible_sources", "get_source_rule_summary", "list_ai_analysis_results"}
MODE_PROMPTS = {"chat": "通用问答", "character": "人物介绍", "storyline": "剧情解析", "world": "世界观"}
```

每项工具定义 Pydantic arguments 模型。递归删除 `cookie`、`token`、`authorization`、`provider`、`internal` 字段；工具只读书源摘要和调用者可见任务。先保存 user message，成功保存 assistant message，provider 异常保存 `failed` 消息和 `AIService._sanitize_error` 文本；对 `ai.conversation.create`、`ai.conversation.message`、`ai.tool.invoke` 写现有审计日志。

- [ ] **Step 4: 注册依赖并验证**

```python
def build_ai_workspace_service() -> AIWorkspaceService:
    return AIWorkspaceService(build_provider_platform_service(), SQLiteAIConversationRepository(), build_source_runtime_repository(), build_ai_runtime_repository(), build_auth_repository())
```

Run: `cd backend; python -m pytest tests/test_ai_workspace_service.py tests/test_ai_runtime_service.py -v`

Expected: PASS。

- [ ] **Step 5: 提交 AI 服务**

```bash
git add backend/app/application/services/ai_workspace_service.py backend/app/infrastructure/persistence/factory.py backend/tests/test_ai_workspace_service.py
git commit -m "feat: add guarded ai workspace service"
```

### Task 3: AI 会话 HTTP API

**Files:**
- Modify: `backend/app/interfaces/http/ai.py`
- Test: `backend/tests/test_api_ai_workspace.py`

- [ ] **Step 1: 写失败的 API 测试**

```python
def test_ai_workspace_requires_permission_and_enforces_owner(client, token_for):
    assert client.post("/api/ai/conversations", headers=token_for([]), json={"title": "分析"}).status_code == 403
    response = client.post("/api/ai/conversations", headers=token_for(["ai.run"]), json={"title": "分析"})
    assert response.status_code == 200
    assert client.get(f"/api/ai/conversations/{response.json()['data']['id']}", headers=token_for(["ai.run"], user_id=9)).status_code == 404
```

- [ ] **Step 2: 实现端点**

增加 `GET/POST /api/ai/conversations`、`GET /api/ai/conversations/{id}`、`POST /api/ai/conversations/{id}/messages`。全部使用 `Permission.AI_RUN`；模式限定为 `chat|character|storyline|world`；非所有者返回 404；沿用 envelope。

- [ ] **Step 3: 验证并提交**

Run: `cd backend; python -m pytest tests/test_api_ai_workspace.py tests/test_api_ai.py -v`

Expected: PASS。

```bash
git add backend/app/interfaces/http/ai.py backend/tests/test_api_ai_workspace.py
git commit -m "feat: expose ai workspace api"
```

### Task 4: 规则候选、验证与发布门禁

**Files:**
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Test: `backend/tests/test_source_rule_editor_service.py`
- Test: `backend/tests/test_api_source_rule_editor.py`

- [ ] **Step 1: 写失败的规则测试**

```python
async def test_draft_creates_new_candidate_and_wall_blocks_publish():
    draft = await service.create_rule_draft("v1", payload, "7")
    assert draft["source_version_id"] != "v1"
    validation = await service.validate_rule_version(draft["source_version_id"], "7")
    assert validation["content_status"] == "verification_wall"
    with pytest.raises(ValidationException, match="verification_wall"):
        await service.publish_rule_version(draft["source_version_id"], "7")
```

- [ ] **Step 2: 实现规则服务和端点**

实现 `get_version_detail`、`create_rule_draft`、`validate_rule_version`、`publish_rule_version`。草稿复制原 payload，校验 `bookSourceName`、`bookSourceUrl` 和 `ruleSearch|ruleBookInfo|ruleToc|ruleContent` 为对象后创建新 candidate。验证写入 `SourceTestRun`，缺失 search/toc/content 规则为失败；`content_status="verification_wall"` 必须阻断。发布只接受 candidate、最近 grade 为 `A|B`、且没有验证墙；旧 published 版本设为 `superseded`，并记录 deployment 与 `source_rule.*` 审计。

实现 `GET /api/sources/versions/{id}` 使用 `book_sources.read`，`POST /drafts`、`/validate`、`/publish` 使用 `book_sources.write`。所有结果返回 grade、diagnostics、`content_status`、`publish_allowed`。

- [ ] **Step 3: 验证并提交**

Run: `cd backend; python -m pytest tests/test_source_rule_editor_service.py tests/test_api_source_rule_editor.py tests/test_source_runtime_repo.py -v`

Expected: PASS。

```bash
git add backend/app/application/services/source_runtime_service.py backend/app/interfaces/http/sources.py backend/tests/test_source_rule_editor_service.py backend/tests/test_api_source_rule_editor.py
git commit -m "feat: add source rule validation and publishing"
```

### Task 5: 中文用户管理

**Files:**
- Modify: `frontend/src/api/modules/admin.ts`
- Modify: `frontend/src/features/admin/AdminUsersPage.tsx`
- Create: `frontend/src/features/admin/AdminUsersPage.test.tsx`

- [ ] **Step 1: 写失败的页面测试**

```tsx
test('管理员可填写创建、编辑、改密和撤销会话表单', async () => {
  render(<AdminUsersPage />)
  fireEvent.click(await screen.findByRole('button', { name: '创建用户' }))
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'reader' } })
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'ReaderPass123' } })
  fireEvent.click(screen.getByRole('button', { name: '确认创建' }))
  await waitFor(() => expect(createUser).toHaveBeenCalledWith(expect.objectContaining({ username: 'reader' })))
})
```

- [ ] **Step 2: 实现客户端与页面**

增加 `revokeUserSessions(id)`，请求 `POST /admin/sessions/{id}/revoke`。将用户页改为正确 UTF-8 中文：创建表单含用户名、显示名、角色、密码；行操作含编辑、启停、重置密码、撤销会话。敏感操作使用 `window.confirm`，密码不回显，无 `users.write` 时隐藏写入口。

- [ ] **Step 3: 验证并提交**

Run: `cd frontend; npm test -- --run src/features/admin/AdminUsersPage.test.tsx src/app/router.test.tsx`

Expected: PASS。

```bash
git add frontend/src/api/modules/admin.ts frontend/src/features/admin/AdminUsersPage.tsx frontend/src/features/admin/AdminUsersPage.test.tsx
git commit -m "feat: complete chinese user management"
```

### Task 6: AI 工作台前端

**Files:**
- Modify: `frontend/src/api/modules/ai.ts`
- Create: `frontend/src/features/ai/AIWorkspacePage.tsx`
- Create: `frontend/src/features/ai/AIWorkspacePage.test.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: 写失败的页面测试**

```tsx
test('工作台按中文模式发送消息并显示工具引用', async () => {
  render(<MemoryRouter><AIWorkspacePage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '人物介绍' }))
  fireEvent.change(screen.getByLabelText('输入消息'), { target: { value: '介绍主角' } })
  fireEvent.click(screen.getByRole('button', { name: '发送' }))
  await waitFor(() => expect(sendAIConversationMessage).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ mode: 'character' })))
})
```

- [ ] **Step 2: 实现类型、页面与路由**

添加会话列表、创建、详情、发送 API。页面左侧会话列表，右侧时间线与输入区；模式文本为“通用问答、人物介绍、剧情解析、世界观”；工具结果以“引用的工具结果”只读卡片显示；失败显示安全文本和重试。注册 `/ai/workspace` 到 `ai.run` 守卫下，保留任务页。

- [ ] **Step 3: 验证并提交**

Run: `cd frontend; npm test -- --run src/features/ai/AIWorkspacePage.test.tsx src/app/router.test.tsx`

Expected: PASS。

```bash
git add frontend/src/api/modules/ai.ts frontend/src/features/ai/AIWorkspacePage.tsx frontend/src/features/ai/AIWorkspacePage.test.tsx frontend/src/app/router.tsx
git commit -m "feat: add chinese ai workspace"
```

### Task 7: 规则编辑器与入口

**Files:**
- Modify: `frontend/src/api/modules/sources.ts`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Create: `frontend/src/features/sources/SourceRuleEditorPage.tsx`
- Create: `frontend/src/features/sources/SourceRuleEditorPage.test.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: 写失败的编辑器测试**

```tsx
test('验证墙禁止发布但允许保存候选', async () => {
  render(<MemoryRouter initialEntries={['/sources/rules/v1']}><SourceRuleEditorPage /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '验证规则' }))
  expect(await screen.findByText('正文访问受阻，禁止发布')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '发布版本' })).toBeDisabled()
})
```

- [ ] **Step 2: 实现 API、编辑器、入口和路由**

增加 `getSourceVersion`、`createSourceRuleDraft`、`validateSourceRule`、`publishSourceRule`。页面提供基础字段、规则 JSON、正则文本/模式/替换预览（复用 `testEngineRegex`）、保存候选、验证、发布。JSON 无效时禁止保存；验证墙或质量不足时禁用发布并给出中文原因。修复 `SourceListPage` 的中文乱码并为版本增加“编辑规则”链接；注册 `/sources/rules/:sourceVersionId` 到 `book_sources.read` 守卫下。

- [ ] **Step 3: 验证并提交**

Run: `cd frontend; npm test -- --run src/features/sources/SourceRuleEditorPage.test.tsx src/features/sources/SourceListPage.test.tsx`

Expected: PASS。

```bash
git add frontend/src/api/modules/sources.ts frontend/src/features/sources/SourceListPage.tsx frontend/src/features/sources/SourceRuleEditorPage.tsx frontend/src/features/sources/SourceRuleEditorPage.test.tsx frontend/src/app/router.tsx
git commit -m "feat: add source rule editor"
```

### Task 8: 全量验证

**Files:**
- Modify: `docs/superpowers/specs/2026-07-13-ai-workspace-user-rule-editor-design.md`（仅当最终 API 名称必须同步）

- [ ] **Step 1: 运行后端相关测试和全量回归**

Run: `cd backend; python -m pytest tests/test_ai_conversation_repo.py tests/test_ai_workspace_service.py tests/test_api_ai_workspace.py tests/test_api_admin_users.py tests/test_source_rule_editor_service.py tests/test_api_source_rule_editor.py -v; python -m pytest`

Expected: 全部 PASS。

- [ ] **Step 2: 运行前端测试与生产构建**

Run: `cd frontend; npm test -- --run; npm run build`

Expected: Vitest 全绿，TypeScript 和 Vite 构建成功。

- [ ] **Step 3: 差异检查和最终提交**

Run: `git diff --check; git status --short`

Expected: 无空白错误，只有本功能文件待提交。

```bash
git add backend frontend docs
git commit -m "feat: complete ai workspace and source rule workflow"
```

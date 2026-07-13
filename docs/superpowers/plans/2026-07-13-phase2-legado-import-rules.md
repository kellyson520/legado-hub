# Legado JSON 书源导入导出与规则中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不发布未验证来源的前提下，支持 Legado JSON 书源的安全导入导出，并在规则引擎中提供本地正则表达式测试器。

**Architecture:** 导入/导出复用既有 `SourceRuntimeService` 的候选版本存储：导入始终生成 `candidate`，导出仅从已发布版本和当前用户候选版本产生白名单 Legado payload。正则测试位于 Engine HTTP 层的纯计算服务，不访问网络或执行 JavaScript；前端仅调用新 API 并把验证墙状态明确渲染为“正文访问受阻”。

**Tech Stack:** FastAPI、Pydantic、Python `re`、SQLite/SQLAlchemy、React、TypeScript、Vitest、Testing Library。

---

## 文件结构

- 修改 `backend/app/application/services/source_runtime_service.py`：实现 Legado payload 归一化、敏感字段剔除、候选导入与可见范围导出。
- 修改 `backend/app/interfaces/http/sources.py`：提供 `POST /api/sources/import` 和 `GET /api/sources/export`。
- 修改 `backend/app/interfaces/http/engine.py`：提供 `POST /api/engine/regex-test`，并转换 JavaScript 风格 `$1` 替换引用。
- 新建 `backend/tests/test_api_source_import_export.py`：覆盖候选导入、逐项错误、去重、脱敏和导出范围。
- 新建 `backend/tests/test_api_engine_regex.py`：覆盖匹配、捕获组、替换预览与非法表达式。
- 修改 `frontend/src/api/modules/sources.ts`：定义并调用导入/导出 API。
- 修改 `frontend/src/api/modules/engine.ts`：定义并调用正则测试 API。
- 修改 `frontend/src/features/sources/SourceListPage.tsx`：加入 JSON 导入、下载导出和中文反馈。
- 修改 `frontend/src/features/engine/EngineRunsPage.tsx`：加入正则测试器并显示 verification wall。
- 修改对应前端测试：测试 API 调用、导入/导出交互和正则结果渲染。

### Task 1: 后端 Legado JSON 导入候选版本

**Files:**
- Create: `backend/tests/test_api_source_import_export.py`
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/interfaces/http/sources.py`

- [ ] **Step 1: 写失败 API 测试**

```python
response = client.post('/api/sources/import', json=[{
    'bookSourceName': '示例源', 'bookSourceUrl': 'https://example.test',
    'ruleSearch': {'bookList': '.book'}, 'cookie': 'secret',
}], headers=headers)
assert response.status_code == 200
assert response.json()['data']['items'][0]['status'] == 'created'
assert repo.get_version(response.json()['data']['items'][0]['source_version_id']).status == 'candidate'
assert 'cookie' not in repo.get_version(...).payload
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_source_import_export.py`

Expected: FAIL，原因是 `/api/sources/import` 尚不存在。

- [ ] **Step 3: 实现最小候选导入**

在 `SourceRuntimeService` 新增 `import_legado_sources(payload, actor_id)`：接受 object 或 list；验证 `bookSourceUrl`、`bookSourceName` 为非空字符串及四个 `rule*` 字段为 object；递归移除 key 名含 `cookie`、`authorization`、`bearer`、`api_key`、`apikey`、`token`、`provider`、`internal` 的字段；按 URL 在 batch 和既有版本中去重；通过 `create_candidate_version('book', url, sanitized, actor_id)` 写入。新增 `POST /import` 路由并使用 `BOOK_SOURCES_WRITE`。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_source_import_export.py`

Expected: PASS。

### Task 2: 后端安全导出与正则测试

**Files:**
- Modify: `backend/tests/test_api_source_import_export.py`
- Create: `backend/tests/test_api_engine_regex.py`
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Modify: `backend/app/interfaces/http/engine.py`

- [ ] **Step 1: 写失败测试**

```python
exported = client.get('/api/sources/export', headers=headers).json()['data']
assert exported == [{'bookSourceName': '示例源', 'bookSourceUrl': 'https://example.test', 'ruleSearch': {'bookList': '.book'}}]

regex = client.post('/api/engine/regex-test', json={
    'text': '第12章：开始', 'pattern': r'第(\\d+)章', 'replacement': '章节$1'
}, headers=engine_headers)
assert regex.json()['data']['matches'][0]['groups'] == ['12']
assert regex.json()['data']['replacement_preview'] == '章节12：开始'
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_source_import_export.py tests/test_api_engine_regex.py`

Expected: FAIL，原因是 export / regex-test 尚不存在。

- [ ] **Step 3: 实现白名单导出和本地正则测试**

导出只允许 `bookSourceName`、`bookSourceUrl`、`bookSourceGroup`、`enabled`、`searchUrl`、`exploreUrl`、`ruleSearch`、`ruleBookInfo`、`ruleToc`、`ruleContent`、`header`、`loginUrl`、`weight`。服务只选择所有 published 版本以及 `created_by == actor_id` 的 candidate，按版本创建时间去重。`regex-test` 用 `re.finditer` 返回 `match_count`、`match`、`groups`、`span`；将 `$1` / `${1}` 转成 Python `\\g<1>` 后 `re.sub`；`re.error` 返回 HTTP 200 的 `data.error`，不抛 500。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_source_import_export.py tests/test_api_engine_regex.py`

Expected: PASS。

### Task 3: 前端 API 和书源导入导出界面

**Files:**
- Modify: `frontend/src/api/modules/sources.ts`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.test.tsx`

- [ ] **Step 1: 写失败页面测试**

```tsx
fireEvent.change(screen.getByLabelText('Legado JSON'), { target: { value: '[{"bookSourceName":"示例源","bookSourceUrl":"https://example.test"}]' } })
fireEvent.click(screen.getByRole('button', { name: '导入书源' }))
await waitFor(() => expect(importLegadoSources).toHaveBeenCalled())
expect(await screen.findByText(/已创建 1 个候选书源/)).toBeInTheDocument()
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd frontend; npm test -- --run src/features/sources/SourceListPage.test.tsx`

Expected: FAIL，缺少按钮及 API mock。

- [ ] **Step 3: 实现 API 和页面**

在 API 模块加入 `importLegadoSources(payload)`、`exportLegadoSources()` 及类型。页面提供 textarea、导入按钮、导出按钮，JSON parse 错误显示中文说明，导入结果显示 created/invalid/skipped 数量；导出使用 `Blob` 下载 `legado-book-sources.json`。所有文案改为正常 UTF-8 中文。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `cd frontend; npm test -- --run src/features/sources/SourceListPage.test.tsx`

Expected: PASS。

### Task 4: 前端规则中心与 verification wall

**Files:**
- Modify: `frontend/src/api/modules/engine.ts`
- Modify: `frontend/src/features/engine/EngineRunsPage.tsx`
- Modify: `frontend/src/features/engine/EngineRunsPage.test.tsx`

- [ ] **Step 1: 写失败页面测试**

```tsx
fireEvent.change(screen.getByLabelText('正则表达式'), { target: { value: '第(\\d+)章' } })
fireEvent.click(screen.getByRole('button', { name: '测试正则' }))
expect(await screen.findByText('章节12：开始')).toBeInTheDocument()
expect(screen.getByText('正文访问受阻')).toBeInTheDocument()
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd frontend; npm test -- --run src/features/engine/EngineRunsPage.test.tsx`

Expected: FAIL，缺少 regex UI/API。

- [ ] **Step 3: 实现规则中心 UI**

加入 `testEngineRegex` API 和模式/替换/文本输入。显示匹配数、完整匹配、捕获组、替换预览及服务端语法错误。把 candidate 卡片的 `content_status === 'verification_wall'` 显示为 `正文访问受阻`，并在同一张卡片显示“不可发布”，不提供发布操作。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `cd frontend; npm test -- --run src/features/engine/EngineRunsPage.test.tsx`

Expected: PASS。

### Task 5: 全量验证与 Git 提交

**Files:**
- Modify: 上述实现文件

- [ ] **Step 1: 后端完整相关回归**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_source_import_export.py tests/test_api_engine_regex.py tests/test_api_engine_runtime.py tests/test_api_source_build.py tests/test_source_runtime_repo.py`

Expected: PASS。

- [ ] **Step 2: 前端完整回归和构建**

Run: `cd frontend; npm test -- --run; npm run build`

Expected: 所有测试 PASS，TypeScript/Vite build exit 0。

- [ ] **Step 3: 审查和提交**

Run: `git diff --check; git status --short; git add backend frontend docs; git commit -m "feat: add legado source import and rule center"`

Expected: 无空白错误，产生一个仅包含第二阶段代码、测试和计划的提交。

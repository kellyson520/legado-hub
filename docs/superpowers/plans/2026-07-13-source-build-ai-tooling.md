# Source Build AI Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让规则引擎构建创建可见的 AI 任务，使用真实受控工具修复并验证候选书源，同时修复 OpenAI-compatible endpoint 和明确 bqgiu 正文验证墙。

**Architecture:** `SourceBuildRuntimeService` 保留 deterministic probe 作为权威验证入口，并在需要修复时委托 `SourceBuildAIRepairService`。该服务创建持久化 AI task、驱动 OpenAI-compatible tool-call loop、经 `AgentToolRegistry` 调用受控 source-build 工具，并只把通过 full-chain validation 的规则写入 candidate version。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy/SQLite、httpx、pytest、现有 Legado parser/runtime。

---

## 文件结构

- 修改 `backend/app/infrastructure/providers/openai_compatible.py`：标准化 endpoint，透传工具字段，标准化 assistant tool calls。
- 修改 `backend/app/application/services/ai_service.py`：新增 source-build task 的成功/失败持久化接口。
- 修改 `backend/app/application/services/agent_tool_registry.py`：支持依赖注入的 source-build handler，并保留 allowlist/tenant 检查。
- 新建 `backend/app/application/services/source_build_tool_executor.py`：执行 inspect、probe、propose、validate、review 五个受控工具并写入 agent runtime 审计。
- 新建 `backend/app/application/services/source_build_ai_repair_service.py`：创建 AI task、执行最多四轮 tool-call loop、解析 fallback JSON patch。
- 修改 `backend/app/application/services/source_build_runtime_service.py`：接入真实工具执行器和 AI repair service，保存关联和 candidate-only patch。
- 修改 `backend/app/application/services/source_build_service.py`：为已完成构建生成新的 candidate/job。
- 修改 `backend/app/application/services/source_probe_service.py`：识别正文 verification wall。
- 修改 `backend/app/infrastructure/persistence/factory.py`：组装 provider、AI task repo、工具执行器和 AI repair service。
- 修改 `backend/app/interfaces/http/engine.py`：console submit response 显示 retry attempt 语义；保留不泄漏凭证的响应。
- 修改/新增 `backend/tests/test_openai_compatible_provider.py`、`backend/tests/test_ai_runtime_service.py`、`backend/tests/test_agent_tool_registry.py`、`backend/tests/test_source_build_runtime_service.py`、`backend/tests/test_source_build_service.py`、`backend/tests/test_source_probe_service.py`：覆盖每项行为。

### Task 1: 修复 OpenAI-compatible endpoint 和 tool calls

**Files:**
- Modify: `backend/app/infrastructure/providers/openai_compatible.py`
- Test: `backend/tests/test_openai_compatible_provider.py`

- [ ] **Step 1: 写入 endpoint normalization 的失败测试**

```python
@pytest.mark.parametrize(
    ('base_url', 'expected'),
    [
        ('https://api.deepseek.com', 'https://api.deepseek.com/v1/chat/completions'),
        ('https://api.deepseek.com/v1', 'https://api.deepseek.com/v1/chat/completions'),
        ('https://api.deepseek.com/v1/chat/completions', 'https://api.deepseek.com/v1/chat/completions'),
    ],
)
def test_normalizes_openai_compatible_base_url_once(base_url, expected):
    from app.infrastructure.providers.openai_compatible import _normalize_endpoint_url
    assert _normalize_endpoint_url(base_url) == expected
```

- [ ] **Step 2: 运行失败测试并确认 `/v1/v1` 行为被捕获**

Run:

```powershell
cd C:\Users\lihuo\Desktop\legado-hub\backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_openai_compatible_provider.py::test_normalizes_openai_compatible_base_url_once
```

Expected: FAIL，`https://api.deepseek.com/v1` 目前得到 `/v1/v1/chat/completions`。

- [ ] **Step 3: 写入 payload 透传与 tool-call 标准化的失败测试**

```python
@pytest.mark.asyncio
async def test_provider_forwards_tool_fields_and_returns_tool_calls():
    captured = {}
    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={
            'model': 'deepseek-chat',
            'choices': [{'message': {
                'content': None,
                'tool_calls': [{'id': 'call-1', 'type': 'function', 'function': {
                    'name': 'source.inspect', 'arguments': '{"url":"https://example.test"}'
                }}],
            }}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8},
        })
    provider = OpenAICompatibleProvider('test', 'https://api.example.test/v1', 'key', transport=httpx.MockTransport(handler))
    result = await provider.invoke_chat('deepseek-chat', {'messages': [], 'tools': [{'type': 'function'}], 'tool_choice': 'auto', 'max_tokens': 32})
    assert captured['tools'] == [{'type': 'function'}]
    assert captured['tool_choice'] == 'auto'
    assert result['output']['tool_calls'][0]['function']['name'] == 'source.inspect'
    await provider.aclose()
```

- [ ] **Step 4: 运行测试确认当前 provider 丢弃 tools/tool_calls**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_openai_compatible_provider.py::test_provider_forwards_tool_fields_and_returns_tool_calls
```

Expected: FAIL，当前请求体只有 `model` 和 `messages`，结果无 `tool_calls`。

- [ ] **Step 5: 最小实现 endpoint normalization 和 result normalization**

在 `_normalize_endpoint_url` 中删除末尾 `/chat/completions` 或 `/v1` 后重建单一 `/v1/chat/completions`；在 `invoke_chat()` 的 JSON body 中复制 allowlisted `tools`、`tool_choice`、`temperature`、`max_tokens`；返回 `output` 时包含 `text`、`message`、`tool_calls` 和 raw body。

```python
message = choices[0].get('message', {}) if choices else {}
return {
    'provider_name': self.name,
    'model': body.get('model', model),
    'output': {'text': message.get('content') or '', 'message': message, 'tool_calls': message.get('tool_calls') or [], 'raw': body},
    ...
}
```

- [ ] **Step 6: 运行 provider 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_openai_compatible_provider.py
```

Expected: PASS。

### Task 2: 持久化 source-build AI task 的成功与失败状态

**Files:**
- Modify: `backend/app/application/services/ai_service.py`
- Test: `backend/tests/test_ai_runtime_service.py`

- [ ] **Step 1: 写入失败 task 持久化测试**

```python
@pytest.mark.asyncio
async def test_source_build_failure_is_persisted_without_secret(tmp_path, monkeypatch):
    ...
    service = AIService(platform=FailingPlatform(RuntimeError('401 Bearer super-secret')), repo=SQLiteAIRuntimeRepository())
    task = await service.run_source_build_repair({'source_version_id': 'sv-1', 'agent_run_id': 'run-1', 'url': 'https://example.test'}, actor_id='tenant-1')
    assert task['status'] == 'failed'
    assert task['type'] == 'source_build_repair'
    assert 'super-secret' not in str(task['result'])
```

- [ ] **Step 2: 运行测试确认缺少 `run_source_build_repair`**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_ai_runtime_service.py::test_source_build_failure_is_persisted_without_secret
```

Expected: FAIL，方法不存在。

- [ ] **Step 3: 实现 source-build task API**

新增 `AIService.run_source_build_repair(payload, actor_id, runner)`：先建立 queued task 的内存结构，执行传入的 async runner，成功时保存 provider/model/usage/result，异常时保存 `failed` 和 `_sanitize_error()` 的错误；返回 `_serialize()` 结果。`_sanitize_error()` 删除 authorization/bearer/api-key 片段，并限制长度为 500。

- [ ] **Step 4: 写入成功 task 关联测试**

```python
@pytest.mark.asyncio
async def test_source_build_success_records_linked_ids(tmp_path, monkeypatch):
    ...
    task = await service.run_source_build_repair({'source_version_id': 'sv-2', 'agent_run_id': 'run-2', 'url': 'https://example.test'}, actor_id='tenant-1', runner=successful_runner)
    assert task['status'] == 'succeeded'
    assert task['result']['source_version_id'] == 'sv-2'
    assert task['result']['agent_run_id'] == 'run-2'
```

- [ ] **Step 5: 实现并运行 AI runtime 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_ai_runtime_service.py
```

Expected: PASS。

### Task 3: 实现真实 source-build 工具 handler 和审计执行器

**Files:**
- Modify: `backend/app/application/services/agent_tool_registry.py`
- Create: `backend/app/application/services/source_build_tool_executor.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: 写入真实 handler 及 tenant 拒绝测试**

```python
def test_source_inspect_handler_returns_context_and_registry_rejects_cross_tenant():
    executor = SourceBuildToolExecutor(context=SourceBuildToolContext(...))
    registry = AgentToolRegistry(source_build_handlers=executor.handlers())
    accepted = registry.invoke(agent_kind='source_build', tool_name='source.inspect', arguments={'url': 'https://example.test'}, tenant_id='tenant-1')
    assert accepted.status == 'accepted'
    assert accepted.data['source_version_id'] == 'sv-1'
    with pytest.raises(AuthorizationException):
        registry.invoke(agent_kind='source_build', tool_name='source.inspect', arguments={'tenant_id': 'tenant-2'}, tenant_id='tenant-1')
```

- [ ] **Step 2: 运行测试确认当前 source.inspect 返回 `tool_not_implemented`**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_tool_registry.py::test_source_inspect_handler_returns_context_and_registry_rejects_cross_tenant
```

Expected: FAIL，registry constructor 不接受 handlers，或 inspect 被拒绝。

- [ ] **Step 3: 实现 registry handler 注入**

`AgentToolRegistry.__init__(source_build_handlers: Mapping[str, Callable] | None = None)` 将仅允许的 handler 注入 builtin `AgentTool`；不提供任何 public register 方法。保留既有 tenant 深度检查。

- [ ] **Step 4: 实现 `SourceBuildToolExecutor`**

定义 `SourceBuildToolContext`（tenant、version、source URL、base source rule、probe factory、review service）和 executor：

```python
ALLOWED_PATCH_FIELDS = frozenset({'searchUrl', 'header', 'ruleSearch', 'ruleBookInfo', 'ruleToc', 'ruleContent', 'replaceRule'})

def _propose(self, arguments):
    patch = arguments.get('patch')
    if not isinstance(patch, dict) or set(patch) - ALLOWED_PATCH_FIELDS:
        return ToolResult(status='rejected', error_code='invalid_rule_patch')
    self._pending_patch = deepcopy(patch)
    return ToolResult(status='accepted', data={'patch_fields': sorted(patch)})
```

`source.inspect` 返回 context，`source.probe` 与 `rule.validate` 运行 full-chain probe 并返回统一 validation，`review.request` 走 `SourceReviewService.enqueue_build_escalation`。

- [ ] **Step 5: 写入 patch allowlist 与 validation 不写库测试**

```python
def test_rule_propose_rejects_unallowlisted_field():
    result = executor.handlers()['rule.propose']({'patch': {'enabled': False}})
    assert result.status == 'rejected'
    assert result.error_code == 'invalid_rule_patch'
```

- [ ] **Step 6: 运行 agent registry 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_tool_registry.py
```

Expected: PASS。

### Task 4: 实现 tool-call loop 和 candidate-only AI repair

**Files:**
- Create: `backend/app/application/services/source_build_ai_repair_service.py`
- Modify: `backend/app/application/services/source_build_runtime_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Test: `backend/tests/test_source_build_runtime_service.py`

- [ ] **Step 1: 写入 provider tool call 会产生真实审计和 AI task 的失败测试**

```python
def test_runtime_executes_ai_tool_calls_and_links_task(tmp_path, monkeypatch):
    ...
    result = service.handle_job(job)
    updated = runtime_repo.get_version(version.id)
    history = agent_runtime.get_tool_history(result['agent_run_id'], tenant_id='tenant-1')
    assert result['ai_task_id']
    assert updated.payload['autonomous_build']['ai_task_id'] == result['ai_task_id']
    assert [entry.tool_name for entry in history] == ['source.inspect', 'rule.propose', 'rule.validate']
    assert all(entry.result is not None for entry in history)
```

- [ ] **Step 2: 运行失败测试确认 runtime 尚未创建 AI task 或调用 registry**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_build_runtime_service.py::test_runtime_executes_ai_tool_calls_and_links_task
```

Expected: FAIL，返回值无 `ai_task_id`，且历史仅为人工审计。

- [ ] **Step 3: 实现 `SourceBuildAIRepairService`**

服务接收 platform、AIService、AgentRuntimeService。构建 OpenAI function schemas；最多 4 个 provider round；每次 tool call：JSON decode arguments、限制 16 KiB、调用 registry、持久化 invocation/result/evidence、将 result 作为 role=`tool` message 回送。若模型最后返回 JSON patch，则只接受 `{"patch": {...}}`。超过限制、非法 tool 或无 patch 返回失败结果。

- [ ] **Step 4: 接入 runtime 和 factory**

在 live probe 后建立 `SourceBuildToolExecutor`、`AgentToolRegistry` 和 AI repair service。AI 成功且 validate 通过时才把 executor 的 validated rule 写入 `updated_payload['source_rule']`；否则保留原有 source rule、写入 review item。将 `ai_task_id`、AI status、tool summary 写进 `autonomous_build`，并添加到 `handle_job()` 返回值。

- [ ] **Step 5: 写入 provider 失败仍可见的 runtime 测试**

```python
def test_runtime_persists_failed_ai_task_and_escalates_without_mutating_candidate_rule(...):
    ...
    assert updated.payload['autonomous_build']['ai']['status'] == 'failed'
    assert updated.payload['source_rule'] == original_rule
    assert result['review_required'] is True
```

- [ ] **Step 6: 实现失败处理并运行 runtime 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_build_runtime_service.py tests/test_ai_runtime_service.py tests/test_agent_tool_registry.py
```

Expected: PASS。

### Task 5: 增加 console source-build 重试语义

**Files:**
- Modify: `backend/app/application/services/source_build_service.py`
- Test: `backend/tests/test_source_build_service.py`

- [ ] **Step 1: 写入已完成 candidate 重新提交会产生新 version/job 的失败测试**

```python
def test_console_resubmit_after_completed_build_creates_fresh_attempt(...):
    first = service.submit(tenant_id='console:1', url='https://example.test/', keyword='novel')
    jobs.complete(first.job_id, worker_id='worker', lease_token=lease_token)
    second = service.submit(tenant_id='console:1', url='https://example.test/', keyword='novel')
    assert second.job_id != first.job_id
    assert second.source_version_id != first.source_version_id
```

- [ ] **Step 2: 运行测试确认旧 idempotency key 复用已完成 job**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_build_service.py::test_console_resubmit_after_completed_build_creates_fresh_attempt
```

Expected: FAIL，当前 job/version 相同。

- [ ] **Step 3: 实现 attempt idempotency key**

查询同 URL/keyword 的 candidate version 的 `autonomous_build` 状态；仅 queued/running 复用。其余情况创建 candidate payload `attempt` 递增，并使用 `source.build.console:{url}:{keyword}:attempt-{n}` 作为 job key。

- [ ] **Step 4: 运行 source build service 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_build_service.py
```

Expected: PASS。

### Task 6: 将 bqgiu 正文验证页分类为访问阻断

**Files:**
- Modify: `backend/app/application/services/source_probe_service.py`
- Test: `backend/tests/test_source_probe_service.py`

- [ ] **Step 1: 写入 verification wall 分类失败测试**

```python
@pytest.mark.asyncio
async def test_content_verification_shell_is_classified_as_access_blocked():
    probe = SourceProbeService(fetcher=VerificationWallFetcher())
    evidence = await probe.probe_source(source, ['novel'], probe_mode='full_chain')
    assert evidence.content.detail['block_reason'] == 'verification_wall'
    assert evidence.content.detail['parse_status'] == 'content_access_blocked'
```

- [ ] **Step 2: 运行测试确认当前 content stage 只报告 empty**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_probe_service.py::test_content_verification_shell_is_classified_as_access_blocked
```

Expected: FAIL，缺少 `block_reason`。

- [ ] **Step 3: 实现 verification shell 检测**

在 `_response_diagnostics()` 加入 HTML title/body 检测：响应 URL 或 preview 包含 `/user/verify`、标题包含“加载中”且脚本含 `getCookie("getsite")`，返回 `block_reason='verification_wall'`；content stage 将 parse status 改为 `content_access_blocked`。

- [ ] **Step 4: 运行 probe 测试组**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_probe_service.py
```

Expected: PASS。

### Task 7: 集成验证、运行服务和实际链路检查

**Files:**
- Modify: `backend/app/interfaces/http/engine.py`（仅在测试表明响应缺少 retry/关联信息时）
- Test: `backend/tests/test_api_engine_runtime.py`

- [ ] **Step 1: 写入 API response 包含 fresh build ID 的失败测试**

```python
def test_console_source_build_resubmit_returns_fresh_ids(client, auth_headers):
    first = client.post('/api/engine/source-builds', json={'url': 'https://example.test/', 'keyword': 'novel'}, headers=auth_headers).json()['data']
    mark_build_complete(first['job_id'])
    second = client.post('/api/engine/source-builds', json={'url': 'https://example.test/', 'keyword': 'novel'}, headers=auth_headers).json()['data']
    assert second['job_id'] != first['job_id']
    assert second['source_version_id'] != first['source_version_id']
```

- [ ] **Step 2: 运行 API 测试并最小修改 response（若需要）**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_api_engine_runtime.py::test_console_source_build_resubmit_returns_fresh_ids
```

Expected: PASS after Task 5; only adjust route serialization if it fails due to missing IDs.

- [ ] **Step 3: 运行完整目标回归测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_openai_compatible_provider.py tests/test_ai_runtime_service.py tests/test_agent_tool_registry.py tests/test_source_build_service.py tests/test_source_build_runtime_service.py tests/test_source_probe_service.py tests/test_api_engine_runtime.py tests/test_api_provider_platform.py
```

Expected: PASS with zero failures.

- [ ] **Step 4: 重启本地后端并检查健康状态**

使用当前运行方式停止旧 Uvicorn，然后以 `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 启动。执行：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

Expected: HTTP 200。

- [ ] **Step 5: 使用真实 console build 做最终观察**

以当前登录身份提交 `https://www.bqgiu.cc/`，查询 source build、`/api/ai/tasks` 和 agent run。验收：

- provider URL 不再含 `/v1/v1`；
- AI 任务显示 `succeeded` 或安全可见的 `failed`；
- agent history 只显示真实 handler 结果；
- bqgiu 正文明确显示 `verification_wall`，不显示 selector 成功或 canary；
- candidate source 不自动发布。

- [ ] **Step 6: 提交变更（若仓库获得 Git 元数据）**

当前项目目录没有 `.git`，不能创建 commit。若后续初始化或恢复 Git：

```powershell
git add backend/app backend/tests docs/superpowers
git commit -m "feat: add source build AI repair tooling"
```
